import io
import json
import os
import unittest
import urllib.error
from unittest import mock

import pandas as pd

from pattern_translator.engine import broad_translation
from pattern_translator.engine import line_translation
from pattern_translator.engine import ocr_lines
from pattern_translator.engine import terminology
from pattern_translator.translation_service import (
    TranslateImageRequest,
    prepare_translation_dataframe,
    translate_image,
)


def _ocr_row(text: str, **geometry) -> dict:
    values = {
        "text": text,
        "confidence": 0.95,
        "x": 10.0,
        "global_x": 10.0,
        "y": 10.0,
        "min_x": 0.0,
        "max_x": 40.0,
        "min_y": 0.0,
        "max_y": 20.0,
    }
    values.update(geometry)
    return values


def _valid_units(segments: list[dict[str, str]], translations: list[str]) -> list[dict]:
    return [
        {
            "source_segment_ids": [segment["source_segment_id"]],
            "translation": translation,
        }
        for segment, translation in zip(segments, translations)
    ]


def _keyed_response_from_units(units: list[dict]) -> dict:
    segment_assignments: dict[str, str] = {}
    semantic_units: dict[str, dict[str, str]] = {}
    for index, unit in enumerate(units):
        unit_id = f"unit-{index:04d}"
        semantic_units[unit_id] = {"translated_text": unit["translation"]}
        for source_id in unit["source_segment_ids"]:
            segment_assignments[source_id] = unit_id
    return {
        "segment_assignments": segment_assignments,
        "semantic_units": semantic_units,
    }


def _route_config(source_mode: str, output_mode: str) -> broad_translation._RouteConfig:
    return broad_translation._route_config(source_mode, output_mode)


class BroadValidationRegressionTests(unittest.TestCase):
    def _segments(self, text: str) -> list[dict[str, str]]:
        return [{"source_segment_id": "segment-0000", "text": text}]

    def _assert_rejects(self, source: str, translation: str, *, en_us_source: bool) -> None:
        segments = self._segments(source)
        units = _valid_units(segments, [translation])
        config = _route_config(
            "English — US" if en_us_source else "Simplified Chinese",
            "Traditional Chinese" if en_us_source else "English — US",
        )
        with self.assertRaises(broad_translation.BroadTranslationError):
            broad_translation.validate_semantic_units(units, segments, config)

    def _assert_accepts(self, source: str, translation: str, *, en_us_source: bool) -> None:
        segments = self._segments(source)
        units = _valid_units(segments, [translation])
        config = _route_config(
            "English — US" if en_us_source else "Simplified Chinese",
            "Traditional Chinese" if en_us_source else "English — US",
        )
        broad_translation.validate_semantic_units(units, segments, config)

    def test_blank_translation_rejected(self):
        self._assert_rejects("Materials", "", en_us_source=True)

    def test_round_total_conflation_rejected(self):
        self._assert_rejects("Rnd 2: 6 sc (12)", "第12圈：6短針", en_us_source=True)

    def test_row_cannot_become_round(self):
        self._assert_rejects("Row 2: 2 sc (2)", "第2圈", en_us_source=True)

    def test_measurement_unit_substitution_rejected(self):
        self._assert_rejects("Cut a 5 cm tail", "剪下5英寸線尾", en_us_source=True)

    def test_mm_ascii_preserved_for_traditional_chinese(self):
        self._assert_accepts("Use a 2 mm hook", "使用 2 mm 鉤針", en_us_source=True)

    def test_mm_to_traditional_chinese_millimetres(self):
        self._assert_accepts("Use a 2 mm hook", "使用 2 毫米鉤針", en_us_source=True)

    def test_mm_to_traditional_chinese_gongli(self):
        self._assert_accepts("Use a 2 mm hook", "使用 2 公釐鉤針", en_us_source=True)

    def test_simplified_chinese_mm_to_english_ascii(self):
        self._assert_accepts("使用6毫米钩针", "Use a 6 mm hook", en_us_source=False)

    def test_simplified_chinese_mm_to_english_spelling(self):
        self._assert_accepts("使用6毫米钩针", "Use a 6 millimeters hook", en_us_source=False)

    def test_simplified_chinese_mm_to_english_cm_rejected(self):
        self._assert_rejects("使用6毫米钩针", "Use a 6 cm hook", en_us_source=False)

    def test_english_measurement_to_simplified_chinese_preserves_unit(self):
        segments = self._segments("Use a 2 mm hook")
        units = _valid_units(segments, ["使用 2 毫米钩针"])
        broad_translation.validate_semantic_units(
            units,
            segments,
            _route_config("English — US", "Simplified Chinese"),
        )

    def test_mm_to_cm_rejected(self):
        self._assert_rejects("Use a 2 mm hook", "使用 2 cm 鉤針", en_us_source=True)

    def test_mm_to_inches_rejected(self):
        self._assert_rejects("Use a 2 mm hook", "使用 2 inches 鉤針", en_us_source=True)

    def test_mm_without_unit_rejected(self):
        self._assert_rejects("Use a 2 mm hook", "使用 2 號鉤針", en_us_source=True)

    def test_mm_numeric_value_change_rejected(self):
        self._assert_rejects("Use a 2 mm hook", "使用 3 mm 鉤針", en_us_source=True)

    def test_each_mm_value_must_keep_its_unit(self):
        self._assert_rejects(
            "Use 2 mm and 6 mm pieces",
            "使用 2 cm 和 6 mm 配件",
            en_us_source=True,
        )

    def test_chinese_identity_swap_rejected_for_sc_to_en(self):
        self._assert_rejects(
            "第1圈：6X，共6针",
            "R6: 1 sc total 6",
            en_us_source=False,
        )

    def test_valid_arabic_digit_traditional_chinese_accepted(self):
        self._assert_accepts("Rnd 1: 6 sc", "第 1 圈：6 短針", en_us_source=True)

    def test_trio_may_translate_to_one_arabic_three(self):
        self._assert_accepts("Add a trio of peas", "放入 3 顆豌豆", en_us_source=True)

    def test_trio_may_translate_to_simplified_chinese_three(self):
        segments = self._segments("Add a trio of peas")
        units = _valid_units(segments, ["放入 3 颗豌豆"])
        broad_translation.validate_semantic_units(
            units,
            segments,
            _route_config("English — US", "Simplified Chinese"),
        )

    def test_simplified_trio_counter_remains_invalid_for_traditional_target(self):
        self._assert_rejects("Add a trio of peas", "放入 3 颗豌豆", en_us_source=True)

    def test_peas_mixed_unit_accepts_trio_as_arabic_three(self):
        self._assert_accepts(
            "R4: (2SC, 1INC)x6 [24] R11: 6DEC [6] 4.Put the trio of peas into the pod!",
            "R4：（2SC，1INC）×6 [24] R11：6DEC [6] 4. 將 3 顆豌豆放入豌豆莢中！",
            en_us_source=True,
        )

    def test_extra_three_without_trio_rejected(self):
        self._assert_rejects("Add the peas", "放入 3 顆豌豆", en_us_source=True)

    def test_unrelated_extra_three_with_trio_rejected(self):
        self._assert_rejects(
            "Add a trio of peas",
            "加入三顆豌豆並在第 3 圈縫合",
            en_us_source=True,
        )

    def test_one_trio_cannot_allow_two_extra_threes(self):
        self._assert_rejects(
            "Add a trio of peas",
            "放入 3 顆豌豆和 3 顆豆莢",
            en_us_source=True,
        )

    def test_explicit_three_remains_required_when_source_also_has_trio(self):
        self._assert_rejects(
            "Prepare 3 peas and a trio of pods",
            "準備 4 顆豌豆和三個豆莢",
            en_us_source=True,
        )

    def test_trio_allowance_does_not_hide_other_missing_explicit_digit(self):
        self._assert_rejects(
            "Prepare 2 peas and a trio of pods",
            "準備 3 顆豆莢",
            en_us_source=True,
        )

    def test_trio_allowance_not_applied_to_simplified_chinese_route(self):
        self._assert_rejects("trio", "3 顆", en_us_source=False)

    def test_digit_multiplicity_preserved(self):
        self._assert_rejects("Row 2: 2 sc (2)", "第2行：2短針", en_us_source=True)

    def test_repeat_multiplier_preserved(self):
        self._assert_rejects("Rnd 2: (sc, inc) x6 =12", "第2圈：(短針, 加針)", en_us_source=True)

    def test_range_numbers_preserved(self):
        self._assert_rejects("Rnd 2-4: sc around", "第2圈：短針", en_us_source=True)


class BroadArabicDigitPromptContractTests(unittest.TestCase):
    ROUTES = (
        ("English — US", "Traditional Chinese"),
        ("English — US", "Simplified Chinese"),
        ("Simplified Chinese", "English — US"),
    )

    def _mocked_translation(
        self,
        source_mode: str,
        output_mode: str,
        source: str,
        translation: str,
    ) -> tuple[object, str, list[dict]]:
        rows = pd.DataFrame([_ocr_row(source)])
        segments, _ = broad_translation.build_source_segments(rows)
        response = _keyed_response_from_units(_valid_units(segments, [translation]))
        prompts: list[str] = []
        events: list[dict] = []

        def caller(prompt: str, api_key: str):
            self.assertEqual("test-key", api_key)
            prompts.append(prompt)
            return {
                "output": [
                    {
                        "content": [
                            {"type": "output_text", "text": json.dumps(response)}
                        ]
                    }
                ]
            }, 0.01

        try:
            result = broad_translation.translate_merged_ocr_lines_broad(
                rows,
                source_mode,
                output_mode,
                diagnostic_logger=lambda phase, **fields: events.append(
                    {"phase": phase, **fields}
                ),
                environ={"OPENAI_API_KEY": "test-key"},
                luna_caller=caller,
            )
        except broad_translation.BroadTranslationError:
            self.assertEqual(1, len(prompts))
            return None, prompts[0], events
        self.assertEqual(1, len(prompts))
        return result, prompts[0], events

    def _assert_mocked_passes(
        self,
        source_mode: str,
        output_mode: str,
        source: str,
        translation: str,
    ) -> str:
        result, prompt, _events = self._mocked_translation(
            source_mode,
            output_mode,
            source,
            translation,
        )
        self.assertIsNotNone(result)
        self.assertEqual(translation, result.loc[0, "Translation"])
        return prompt

    def _assert_mocked_rejects(
        self,
        source_mode: str,
        output_mode: str,
        source: str,
        translation: str,
    ) -> None:
        result, _prompt, events = self._mocked_translation(
            source_mode,
            output_mode,
            source,
            translation,
        )
        self.assertIsNone(result)
        failure = next(
            event for event in events if event["phase"] == "objective_validation_failed"
        )
        self.assertEqual("arabic_digit_multiset", failure["failed_rule"])

    def test_one_explicit_digit_contract_is_shared_by_all_three_routes(self):
        required_clauses = (
            "Preserve every explicit Arabic digit from the assigned source segments as "
            "the same Arabic digit in the translation.",
            "Do not spell it out as a number word, ordinal word, or frequency word",
            "do not replace it with language-specific numeric characters or words",
            "source 1 must remain 1, not one, once, first, 一, or 第一",
            "source 2 must remain 2, not two, twice, second, 二, or 兩",
            "Do not infer or invent Arabic digits absent from the assigned source segments.",
            "Natural fluency must never override explicit Arabic-digit preservation.",
        )
        for source_mode, output_mode in self.ROUTES:
            with self.subTest(source_mode=source_mode, output_mode=output_mode):
                prompt = broad_translation.build_prompt(
                    [],
                    [],
                    _route_config(source_mode, output_mode),
                )
                for clause in required_clauses:
                    self.assertIn(clause, prompt)
                self.assertEqual(
                    1,
                    prompt.count(
                        "Preserve every explicit Arabic digit from the assigned source "
                        "segments"
                    ),
                )
                self.assertNotIn("Keep Arabic numerals as Arabic digits", prompt)

    def test_simplified_chinese_to_english_keeps_explicit_arabic_digits(self):
        self._assert_mocked_passes(
            "Simplified Chinese",
            "English — US",
            "第2圈：缠绕1圈，钩14长针",
            "Round 2: wrap the yarn 1 time and work 14 double crochet stitches.",
        )
        rejected = (
            ("缠绕1圈", "Wrap the yarn once."),
            ("重复2次", "Repeat twice."),
            ("钩14长针", "Work double crochet stitches."),
            ("收紧", "Tighten and add 1 marker."),
        )
        for source, translation in rejected:
            with self.subTest(translation=translation):
                self._assert_mocked_rejects(
                    "Simplified Chinese",
                    "English — US",
                    source,
                    translation,
                )

    def test_english_to_traditional_chinese_keeps_explicit_arabic_digits(self):
        self._assert_mocked_passes(
            "English — US",
            "Traditional Chinese",
            "Round 1: work 2 sc and repeat 3 times.",
            "第 1 圈：鉤 2 短針並重複 3 次。",
        )
        rejected = (
            ("Round 1: work sc.", "第一圈：鉤短針。"),
            ("Repeat 2 times.", "重複兩次。"),
            ("Work 14 sc.", "鉤短針。"),
            ("Work sc.", "鉤短針並加 1 個記號。"),
        )
        for source, translation in rejected:
            with self.subTest(translation=translation):
                self._assert_mocked_rejects(
                    "English — US",
                    "Traditional Chinese",
                    source,
                    translation,
                )

    def test_english_to_simplified_chinese_keeps_explicit_arabic_digits(self):
        self._assert_mocked_passes(
            "English — US",
            "Simplified Chinese",
            "Round 1: work 2 sc and repeat 3 times.",
            "第 1 轮：钩 2 短针并重复 3 次。",
        )
        rejected = (
            ("Round 1: work sc.", "第一轮：钩短针。"),
            ("Repeat 2 times.", "重复两次。"),
            ("Work 14 sc.", "钩短针。"),
            ("Work sc.", "钩短针并加 1 个记号。"),
        )
        for source, translation in rejected:
            with self.subTest(translation=translation):
                self._assert_mocked_rejects(
                    "English — US",
                    "Simplified Chinese",
                    source,
                    translation,
                )


class BroadIdCoverageDiagnosticsTests(unittest.TestCase):
    def _reject_with_ids(self, returned_ids: list[list[str]]):
        segments = [
            {"source_segment_id": "segment-0000", "text": "FULL_PATTERN_SECRET_A"},
            {"source_segment_id": "segment-0001", "text": "FULL_PROMPT_SECRET_B"},
            {"source_segment_id": "segment-0002", "text": "API_KEY_SECRET_C"},
        ]
        units = [
            {
                "source_segment_ids": source_ids,
                "translation": f"FULL_RESPONSE_SECRET_{index}",
            }
            for index, source_ids in enumerate(returned_ids)
        ]
        events: list[dict] = []

        def logger(phase: str, **fields: object) -> None:
            events.append({"phase": phase, **fields})

        with self.assertRaises(broad_translation.BroadTranslationError) as ctx:
            broad_translation.validate_semantic_units(
                units,
                segments,
                _route_config("English — US", "Traditional Chinese"),
                diagnostic_logger=logger,
            )

        failures = [
            event for event in events if event["phase"] == "id_coverage_validation_failed"
        ]
        self.assertEqual(1, len(failures))
        self.assertEqual(3, failures[0]["expected_segment_count"])
        self.assertEqual(len(units), failures[0]["semantic_unit_count"])
        return failures[0], ctx.exception, events

    def test_missing_id_diagnostics_and_bare_public_error(self):
        failure, exc, _events = self._reject_with_ids(
            [["segment-0000"], ["segment-0002"]]
        )
        self.assertEqual(
            ["segment-0000", "segment-0001", "segment-0002"],
            failure["expected_source_segment_ids"],
        )
        self.assertEqual(
            ["segment-0000", "segment-0002"], failure["returned_source_segment_ids"]
        )
        self.assertEqual(["segment-0001"], failure["missing_source_segment_ids"])
        self.assertEqual([], failure["duplicate_source_segment_ids"])
        self.assertEqual([], failure["unknown_source_segment_ids"])
        self.assertEqual("", str(exc))

    def test_duplicate_id_diagnostics(self):
        failure, _exc, _events = self._reject_with_ids(
            [["segment-0000"], ["segment-0000"], ["segment-0001", "segment-0002"]]
        )
        self.assertEqual(["segment-0000"], failure["duplicate_source_segment_ids"])
        self.assertEqual([], failure["missing_source_segment_ids"])
        self.assertEqual([], failure["unknown_source_segment_ids"])

    def test_unknown_id_diagnostics_without_content(self):
        failure, _exc, events = self._reject_with_ids(
            [
                ["segment-0000"],
                ["segment-9999"],
                ["segment-0001", "segment-0002"],
            ]
        )
        self.assertEqual(["segment-9999"], failure["unknown_source_segment_ids"])
        self.assertEqual([], failure["missing_source_segment_ids"])
        self.assertEqual([], failure["duplicate_source_segment_ids"])
        serialized = json.dumps(events, ensure_ascii=False)
        self.assertNotIn("FULL_PATTERN_SECRET", serialized)
        self.assertNotIn("FULL_PROMPT_SECRET", serialized)
        self.assertNotIn("FULL_RESPONSE_SECRET", serialized)
        self.assertNotIn("API_KEY_SECRET", serialized)
        self.assertNotIn('"prompt"', serialized.lower())
        self.assertNotIn('"response"', serialized.lower())
        self.assertNotIn('"api_key"', serialized.lower())


class BroadValidationDiagnosticsTests(unittest.TestCase):
    def _reject_with_logger(
        self,
        source: str,
        translation: str,
        *,
        en_us_source: bool = True,
        segment_ids=None,
    ) -> tuple[list[dict], broad_translation.BroadTranslationError]:
        segment_ids = segment_ids or ["segment-0030"]
        segments = [{"source_segment_id": segment_ids[0], "text": source}]
        units = _valid_units(segments, [translation])
        config = _route_config(
            "English — US" if en_us_source else "Simplified Chinese",
            "Traditional Chinese" if en_us_source else "English — US",
        )
        events: list[dict] = []

        def logger(phase: str, **fields: object) -> None:
            events.append({"phase": phase, **fields})

        with self.assertRaises(broad_translation.BroadTranslationError) as ctx:
            broad_translation.validate_semantic_units(
                units,
                segments,
                config,
                diagnostic_logger=logger,
            )
        return events, ctx.exception

    def test_arabic_digit_multiset_logs_structured_differences(self):
        source = "R1: 6SC in MR [6] R9: (2SC, 1DEC)x6 [18] 2.Put the blusher"
        translation = "R1：環狀起針內鉤 6 短針 [6]　R9：（2 短針、1 減針）重複 6 次 [18]"
        events, exc = self._reject_with_logger(source, translation)
        failure = next(event for event in events if event.get("phase") == "objective_validation_failed")
        self.assertEqual("arabic_digit_multiset", failure["failed_rule"])
        self.assertEqual(["segment-0030"], failure["source_segment_ids"])
        self.assertEqual(["2"], failure["missing_digits"])
        self.assertEqual([], failure["extra_digits"])
        self.assertIn("2", failure["source_digit_multiset"])
        self.assertEqual(source, failure["failed_source_excerpt"])
        self.assertEqual(translation.replace("\u3000", " "), failure["failed_translation_excerpt"])
        self.assertFalse(failure["failed_source_excerpt_truncated"])
        self.assertFalse(failure["failed_translation_excerpt_truncated"])
        self.assertEqual("", str(exc))

    def test_only_failing_unit_is_logged_and_public_error_stays_bare(self):
        unrelated_source = "UNRELATED_SECRET FULL_PROMPT FULL_RESPONSE"
        unrelated_translation = "無關內容"
        failing_source = "R1: 2 sc"
        failing_translation = "R1：3 短針"
        segments = [
            {"source_segment_id": "segment-0000", "text": unrelated_source},
            {"source_segment_id": "segment-0001", "text": failing_source},
        ]
        units = _valid_units(segments, [unrelated_translation, failing_translation])
        events: list[dict] = []

        def logger(phase: str, **fields: object) -> None:
            events.append({"phase": phase, **fields})

        with self.assertRaises(broad_translation.BroadTranslationError) as ctx:
            broad_translation.validate_semantic_units(
                units,
                segments,
                _route_config("English — US", "Traditional Chinese"),
                diagnostic_logger=logger,
            )

        failures = [event for event in events if event["phase"] == "objective_validation_failed"]
        self.assertEqual(1, len(failures))
        self.assertEqual(["segment-0001"], failures[0]["source_segment_ids"])
        self.assertEqual(failing_source, failures[0]["failed_source_excerpt"])
        self.assertEqual(failing_translation, failures[0]["failed_translation_excerpt"])
        serialized = json.dumps(events, ensure_ascii=False)
        self.assertNotIn(unrelated_source, serialized)
        self.assertNotIn(unrelated_translation, serialized)
        self.assertNotIn("api_key", serialized.lower())
        self.assertNotIn('"prompt"', serialized.lower())
        self.assertNotIn('"response"', serialized.lower())
        self.assertEqual("", str(ctx.exception))

    def test_failing_unit_diagnostic_text_is_capped(self):
        source = "2 " + ("source-text " * 80)
        translation = "3 " + ("translation-text " * 80)
        events, exc = self._reject_with_logger(source, translation)
        failure = next(event for event in events if event.get("phase") == "objective_validation_failed")
        self.assertTrue(failure["failed_source_excerpt_truncated"])
        self.assertTrue(failure["failed_translation_excerpt_truncated"])
        self.assertLessEqual(len(failure["failed_source_excerpt"]), 401)
        self.assertLessEqual(len(failure["failed_translation_excerpt"]), 401)
        self.assertNotIn(source, json.dumps(events, ensure_ascii=False))
        self.assertNotIn(translation, json.dumps(events, ensure_ascii=False))
        self.assertEqual("", str(exc))

    def test_round_identity_logs_missing_round_numbers(self):
        events, exc = self._reject_with_logger("Rnd 2: 6 sc", "第6圈：2 短針")
        failure = next(event for event in events if event.get("phase") == "objective_validation_failed")
        self.assertEqual("round_identity", failure["failed_rule"])
        self.assertIn("2", failure["required_round_identities"])
        self.assertIn("2", failure["missing_round_identities"])
        self.assertEqual("", str(exc))

    def test_row_identity_logs_missing_row_numbers(self):
        events, exc = self._reject_with_logger("Row 2: 2 sc", "第2圈：2短針")
        failure = next(event for event in events if event.get("phase") == "objective_validation_failed")
        self.assertEqual("row_identity", failure["failed_rule"])
        self.assertIn("2", failure["required_row_identities"])
        self.assertIn("2", failure["missing_row_identities"])
        self.assertEqual("", str(exc))

    def test_measurement_units_logs_compact_measurement_facts(self):
        events, exc = self._reject_with_logger("Cut a 5 cm tail", "剪下5英寸線尾")
        failure = next(event for event in events if event.get("phase") == "objective_validation_failed")
        self.assertEqual("measurement_units", failure["failed_rule"])
        self.assertEqual("5", failure["failed_measurement_number"])
        self.assertEqual("cm", failure["failed_measurement_unit"])
        self.assertEqual("unit_substituted_to_inch", failure["measurement_failure"])
        self.assertEqual("", str(exc))

    def test_translate_path_logs_validation_failure_before_request_end(self):
        rows = pd.DataFrame([_ocr_row("R1: 6SC [6] 2.Put eyes")])
        events: list[dict] = []

        def logger(phase: str, **fields: object) -> None:
            events.append({"phase": phase, **fields})

        def fake_luna(prompt, api_key):
            del prompt, api_key
            return {
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    _keyed_response_from_units(
                                        [
                                            {
                                                "source_segment_ids": ["segment-0000"],
                                                "translation": "R1：6 短針 [6]",
                                            }
                                        ]
                                    )
                                ),
                            }
                        ]
                    }
                ]
            }, 0.01

        with mock.patch.dict(
            os.environ,
            {"PATTERN_BROAD_TRANSLATION_ENABLED": "1", "OPENAI_API_KEY": "test-key"},
            clear=False,
        ):
            with mock.patch.object(broad_translation, "call_luna_once", side_effect=fake_luna):
                with self.assertRaises(broad_translation.BroadTranslationError):
                    broad_translation.translate_merged_ocr_lines_broad(
                        rows,
                        source_mode="English — US",
                        output_mode="Traditional Chinese",
                        diagnostic_logger=logger,
                        environ={"OPENAI_API_KEY": "test-key"},
                    )

        failure = next(event for event in events if event.get("phase") == "objective_validation_failed")
        end = next(event for event in events if event.get("phase") == "ai_request_end")
        self.assertEqual("arabic_digit_multiset", failure["failed_rule"])
        self.assertEqual(["2"], failure["missing_digits"])
        self.assertEqual("validation_rejected", end["outcome"])


class BroadGlossaryTests(unittest.TestCase):
    def test_equivalence_group_aliases_retained(self):
        terms = broad_translation.build_glossary("English — US", "Traditional Chinese")
        by_english = {
            term["english_us"].lower(): term for term in terms
        }
        abbreviations = set()
        for term in terms:
            abbreviations.update(term.get("english_us_abbreviations", []))
        self.assertIn("blo", abbreviations)
        self.assertIn("flo", abbreviations)
        self.assertIn("yoh", abbreviations)
        bobble_terms = [
            term
            for term in terms
            if term.get("english_us", "").lower() == "bobble"
            or "bobble" in [alias.lower() for alias in term.get("english_us_aliases", [])]
        ]
        self.assertTrue(bobble_terms)
        self.assertIn("back loop", by_english)

    def test_simplified_chinese_source_uses_simplified_forms(self):
        terms = broad_translation.build_glossary("Simplified Chinese", "English — US")
        chain = next(term for term in terms if term["english_us"].lower() == "chain")
        self.assertEqual(chain["simplified_chinese_authoritative_term"], "锁针")
        self.assertIn("辫子针", chain.get("simplified_chinese_aliases", []))
        back_loop = next(
            term
            for term in terms
            if any(alias.lower() == "blo" for alias in term.get("english_us_abbreviations", []))
        )
        self.assertEqual(back_loop["simplified_chinese_authoritative_term"], "后半针")
        self.assertIn("内半针", back_loop.get("simplified_chinese_aliases", []))

    def test_simplified_chinese_target_uses_existing_conversion(self):
        terms = broad_translation.build_glossary("English — US", "Simplified Chinese")
        chain = next(term for term in terms if term["english_us"].lower() == "chain")
        self.assertEqual(chain["simplified_chinese_authoritative_term"], "锁针")
        self.assertIn("辫子针", chain.get("simplified_chinese_aliases", []))
        self.assertNotIn("traditional_chinese", chain)


class BroadRequestScopedGlossaryTests(unittest.TestCase):
    def setUp(self):
        self.config = _route_config("English — US", "Traditional Chinese")
        self.route_terms = broad_translation.build_glossary(
            self.config.source_mode, self.config.output_mode
        )

    def _select(self, *texts: str) -> list[dict]:
        segments = [
            {"source_segment_id": f"segment-{index:04d}", "text": text}
            for index, text in enumerate(texts)
        ]
        return broad_translation.select_request_glossary(
            self.route_terms, segments, self.config
        )

    def test_peas_source_selects_direct_and_compound_concepts(self):
        texts = [
            "NOTES",
            "This pattern is written in US terminology",
            "You can sell the products made from this pattern and",
            "by you in LIMITED quantity, but please clearly give CREDIT",
            "amiwacrochet as the pattern designer!",
            "Do not copy or modify this pattern and sell it as your own!",
            "You can use any yarn and color you have!",
            "TOOLS AND MATERIALS: ABBREVIATIONS",
            "Milk cotton yarn 4ply in pea R = round",
            "green and dark green CH = chain",
            "Crochet hook 2mm ST = stitch",
            "6mm black half pearl for SC = single crochet",
            "the eyes INC = increase (2 SC in 1 ST)",
            "Tapestry / yarn needle DEC = invisible decrease (1 SC in 2 ST)",
            "Scissors DC = double crochet",
            "Fiberfill for stuffing SLST = slip stitch",
            "Glue (i used UHU) [_]= a total of ST on that R",
            "Blusher",
        ]
        selected = self._select(*texts)
        selected_ids = {entry["concept_id"] for entry in selected}
        expected_ids = {
            "st_001_chain",
            "st_002_slip_stitch",
            "st_003_single_crochet",
            "st_005_double_crochet",
            "st_009_increase",
            "st_010_single_crochet_increase",
            "st_015_decrease",
            "st_016_single_crochet_decrease",
            "st_036_round",
            "st_078_pattern",
            "st_086_stitch",
            "st_104_hook",
        }
        self.assertEqual(expected_ids, selected_ids)
        self.assertEqual(83, len(self.route_terms))
        self.assertEqual(12, len(selected))
        self.assertEqual(21842, broad_translation._glossary_char_count(self.route_terms))
        self.assertEqual(3147, broad_translation._glossary_char_count(selected))
        segments = [
            {"source_segment_id": f"segment-{index:04d}", "text": text}
            for index, text in enumerate(texts)
        ]
        self.assertEqual(
            25217,
            len(broad_translation.build_prompt(segments, self.route_terms, self.config)),
        )
        self.assertEqual(
            6522,
            len(broad_translation.build_prompt(segments, selected, self.config)),
        )

    def test_compounds_require_components_in_same_segment(self):
        selected = self._select("SC and INC; SC and DEC")
        selected_ids = {entry["concept_id"] for entry in selected}
        self.assertIn("st_010_single_crochet_increase", selected_ids)
        self.assertIn("st_016_single_crochet_decrease", selected_ids)

        separated = self._select("SC only", "later INC")
        separated_ids = {entry["concept_id"] for entry in separated}
        self.assertNotIn("st_010_single_crochet_increase", separated_ids)

    def test_explicit_r_definition_selects_round_not_row(self):
        selected_ids = {entry["concept_id"] for entry in self._select("R = round")}
        self.assertIn("st_036_round", selected_ids)
        self.assertNotIn("st_094_row", selected_ids)

    def test_standalone_r_does_not_match_inside_words(self):
        selected_ids = {
            entry["concept_id"]
            for entry in self._select("CREDIT designer terminology products")
        }
        self.assertNotIn("st_036_round", selected_ids)
        self.assertNotIn("st_094_row", selected_ids)

    def test_ambiguous_r_without_definition_keeps_all_owners(self):
        selected_ids = {entry["concept_id"] for entry in self._select("Work in R next.")}
        self.assertIn("st_036_round", selected_ids)
        self.assertIn("st_094_row", selected_ids)

    def test_unrelated_concepts_are_excluded(self):
        selected_ids = {
            entry["concept_id"]
            for entry in self._select("CH = chain; use a crochet hook")
        }
        self.assertNotIn("st_005_double_crochet", selected_ids)
        self.assertNotIn("st_022_popcorn", selected_ids)
        self.assertNotIn("st_076_marker", selected_ids)

    def test_selected_entry_remains_complete_and_unmodified(self):
        selected = self._select("CH = chain")
        selected_chain = next(
            entry for entry in selected if entry["concept_id"] == "st_001_chain"
        )
        route_chain = next(
            entry for entry in self.route_terms if entry["concept_id"] == "st_001_chain"
        )
        self.assertIs(selected_chain, route_chain)
        self.assertEqual(route_chain, selected_chain)
        self.assertIn("english_us_aliases", selected_chain)
        self.assertIn("traditional_chinese_aliases", selected_chain)

    def test_ordinary_prose_can_produce_empty_glossary(self):
        selected = self._select("Please credit the designer clearly.")
        self.assertEqual([], selected)

    def test_simplified_source_selects_authoritative_chinese_form(self):
        config = _route_config("Simplified Chinese", "English — US")
        route_terms = broad_translation.build_glossary(
            config.source_mode, config.output_mode
        )
        selected = broad_translation.select_request_glossary(
            route_terms,
            [{"source_segment_id": "segment-0000", "text": "锁针"}],
            config,
        )
        self.assertIn("st_001_chain", {entry["concept_id"] for entry in selected})

    def test_english_to_simplified_selects_glossary_from_english_source(self):
        config = _route_config("English — US", "Simplified Chinese")
        route_terms = broad_translation.build_glossary(
            config.source_mode,
            config.output_mode,
        )
        selected = broad_translation.select_request_glossary(
            route_terms,
            [{"source_segment_id": "segment-0000", "text": "ch 6, then sc"}],
            config,
        )
        selected_ids = {entry["concept_id"] for entry in selected}
        self.assertIn("st_001_chain", selected_ids)
        chain = next(
            entry for entry in selected if entry["concept_id"] == "st_001_chain"
        )
        self.assertIn("english_us", chain)
        self.assertLess(len(selected), len(route_terms))

    def test_scope_metrics_are_logged_without_glossary_or_source_content(self):
        rows = pd.DataFrame([_ocr_row("Rnd 1: 6 sc")])
        segments, _ = broad_translation.build_source_segments(rows)
        events = []

        def logger(phase, **fields):
            events.append({"phase": phase, **fields})

        def fake_luna(prompt, api_key):
            del prompt, api_key
            return {
                "output": [{"content": [{"type": "output_text", "text": json.dumps(
                    _keyed_response_from_units(
                        _valid_units(segments, ["第 1 圈：6 短針"])
                    )
                )}]}]
            }, 0.01

        broad_translation.translate_merged_ocr_lines_broad(
            rows,
            self.config.source_mode,
            self.config.output_mode,
            diagnostic_logger=logger,
            environ={"OPENAI_API_KEY": "test-key"},
            luna_caller=fake_luna,
        )
        scope = next(event for event in events if event["phase"] == "broad_glossary_scope")
        self.assertEqual(
            {
                "phase",
                "route_glossary_entry_count",
                "scoped_glossary_entry_count",
                "route_glossary_char_count",
                "scoped_glossary_char_count",
            },
            set(scope),
        )
        self.assertEqual(83, scope["route_glossary_entry_count"])
        self.assertLess(scope["scoped_glossary_entry_count"], 83)
        self.assertLess(scope["scoped_glossary_char_count"], 21842)


class BroadAdapterTests(unittest.TestCase):
    def test_multi_segment_joins_with_newline_and_minimum_confidence(self):
        rows = pd.DataFrame(
            [
                _ocr_row("Rnd 1:", min_x=0, max_x=20, min_y=0, max_y=10, confidence=0.9),
                _ocr_row(
                    "6 sc",
                    min_x=30,
                    max_x=60,
                    min_y=0,
                    max_y=10,
                    confidence=0.5,
                ),
            ]
        )
        segments, segment_rows = broad_translation.build_source_segments(rows)
        units = [
            {
                "source_segment_ids": [
                    segments[0]["source_segment_id"],
                    segments[1]["source_segment_id"],
                ],
                "translation": "第 1 圈：6 短針",
            }
        ]
        line_df = broad_translation.adapt_semantic_units_to_line_df(
            units, segments, segment_rows
        )
        self.assertEqual(line_df.loc[0, "Original"], "Rnd 1:\n6 sc")
        self.assertEqual(line_df.loc[0, "Confidence"], 0.5)
        self.assertEqual(line_df.loc[0, "min_x"], 0.0)
        self.assertEqual(line_df.loc[0, "max_x"], 60.0)

    def test_readable_and_txt_output_remain_compatible(self):
        rows = pd.DataFrame([_ocr_row("Rnd 1: 6 sc")])
        segments, segment_rows = broad_translation.build_source_segments(rows)
        units = [
            {
                "source_segment_ids": [segments[0]["source_segment_id"]],
                "translation": "第 1 圈：6 短針",
            }
        ]
        line_df = broad_translation.adapt_semantic_units_to_line_df(
            units, segments, segment_rows
        )
        readable = line_translation.build_readable_line_translation(line_df)
        txt = line_translation.build_overlay_export_text(line_df)
        self.assertIn("第 1 圈：6 短針", readable)
        self.assertIn("第 1 圈：6 短針", txt)
        required = {"Original", "Translation", "Confidence", "Changed", "min_x", "max_x", "min_y", "max_y"}
        self.assertTrue(required.issubset(set(line_df.columns)))


class BroadRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv("knowledge_base/data/master_stitches.csv")
        cls.english_index = terminology.build_term_index(cls.df, "English — US")
        cls.simplified_index = terminology.build_term_index(cls.df, "Simplified Chinese")
        cls.traditional_index = terminology.build_term_index(cls.df, "Traditional Chinese")

    def _fake_luna(self, segments, translations):
        def caller(prompt, api_key):
            del prompt, api_key
            payload = {
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    _keyed_response_from_units(
                                        _valid_units(segments, translations)
                                    )
                                ),
                            }
                        ]
                    }
                ]
            }
            return payload, 0.01

        return caller

    @mock.patch.dict(os.environ, {"PATTERN_BROAD_TRANSLATION_ENABLED": "0"}, clear=False)
    def test_broad_flag_off_uses_legacy_path(self):
        routes = (
            ("English — US", "Traditional Chinese", self.english_index),
            ("Traditional Chinese", "English — US", self.traditional_index),
            ("English — US", "Simplified Chinese", self.english_index),
            ("Simplified Chinese", "English — US", self.simplified_index),
        )
        for source_mode, output_mode, index in routes:
            with self.subTest(source_mode=source_mode, output_mode=output_mode):
                rows = pd.DataFrame([_ocr_row("Materials")])
                with mock.patch.object(
                    broad_translation,
                    "translate_merged_ocr_lines_broad",
                    side_effect=AssertionError("broad path executed"),
                ) as broad_mock, mock.patch.object(
                    line_translation, "translate_ocr_line", return_value="legacy"
                ) as legacy_mock:
                    result = ocr_lines.build_ocr_line_translations(
                        rows,
                        index,
                        self.df,
                        output_mode,
                        source_mode,
                    )
                broad_mock.assert_not_called()
                legacy_mock.assert_called()
                self.assertEqual(result.loc[0, "Translation"], "legacy")

    def test_supported_core_route_matrix_is_exact(self):
        expected = {
            ("English — US", "Traditional Chinese"),
            ("English — US", "Simplified Chinese"),
            ("Simplified Chinese", "English — US"),
        }
        self.assertEqual(expected, set(broad_translation._ROUTE_CONFIGS))

    @mock.patch.dict(
        os.environ,
        {
            "PATTERN_BROAD_TRANSLATION_ENABLED": "1",
            "OPENAI_API_KEY": "test-key",
        },
        clear=False,
    )
    def test_supported_routes_use_exactly_one_broad_call(self):
        cases = (
            (
                "English — US",
                "Traditional Chinese",
                self.english_index,
                "Rnd 1: (6 sc, 1 inc) x2 =14.",
                "第 1 圈：(6 短針，1 加針)×2，共 14 針。",
                "into natural Traditional Chinese",
                '"traditional_chinese":"短針"',
            ),
            (
                "Simplified Chinese",
                "English — US",
                self.simplified_index,
                "第1圈：(6短针，1加针)×2，共14针。",
                "Rnd 1: (6 sc, 1 inc) x2, 14 stitches total.",
                "from a Simplified Chinese crochet pattern",
                '"simplified_chinese_authoritative_term":"短针"',
            ),
            (
                "English — US",
                "Simplified Chinese",
                self.english_index,
                "Rnd 1: (6 sc, 1 inc) x2 =14. Sew the two pieces together.",
                "第 1 轮：(6 短针，1 加针)×2，共 14 针。将两片缝合在一起。",
                "into natural Simplified Chinese",
                '"simplified_chinese_authoritative_term":"短针"',
            ),
        )
        for (
            source_mode,
            output_mode,
            index,
            source_text,
            translated_text,
            prompt_route,
            prompt_glossary,
        ) in cases:
            with self.subTest(source_mode=source_mode, output_mode=output_mode):
                rows = pd.DataFrame([_ocr_row(source_text)])
                segments, _ = broad_translation.build_source_segments(rows)
                prompts = []

                def caller(prompt, api_key):
                    self.assertEqual("test-key", api_key)
                    prompts.append(prompt)
                    return self._fake_luna(segments, [translated_text])(prompt, api_key)

                with mock.patch.object(
                    broad_translation, "call_luna_once", side_effect=caller
                ) as luna_mock, mock.patch.object(
                    line_translation,
                    "translate_ocr_line",
                    side_effect=AssertionError("legacy fallback executed"),
                ) as legacy_mock:
                    result = ocr_lines.build_ocr_line_translations(
                        rows,
                        index,
                        self.df,
                        output_mode,
                        source_mode,
                    )
                self.assertEqual(1, luna_mock.call_count)
                legacy_mock.assert_not_called()
                self.assertEqual(translated_text, result.loc[0, "Translation"])
                self.assertIn(prompt_route, prompts[0])
                self.assertIn(prompt_glossary, prompts[0])
                self.assertIn("segment_assignments", prompts[0])

    def test_new_routes_keep_keyed_ownership_and_objective_validation(self):
        cases = (
            (
                "English — US",
                "Simplified Chinese",
                ["Rnd 1:", "6 sc", "Sew the two pieces."],
                ["第 1 轮：6 短针", "将两片缝合。"],
                "Rnd 1:\n6 sc",
                "第 1 轮：5 短针",
            ),
        )
        for (
            source_mode,
            output_mode,
            source_lines,
            translations,
            expected_original,
            invalid_translation,
        ) in cases:
            with self.subTest(source_mode=source_mode, output_mode=output_mode):
                rows = pd.DataFrame([_ocr_row(text) for text in source_lines])
                segments, _ = broad_translation.build_source_segments(rows)
                units = [
                    {
                        "source_segment_ids": [
                            segments[0]["source_segment_id"],
                            segments[1]["source_segment_id"],
                        ],
                        "translation": translations[0],
                    },
                    {
                        "source_segment_ids": [segments[2]["source_segment_id"]],
                        "translation": translations[1],
                    },
                ]
                response = _keyed_response_from_units(units)
                calls = 0

                def caller(_prompt, _api_key):
                    nonlocal calls
                    calls += 1
                    return {
                        "output": [{"content": [{"type": "output_text", "text": json.dumps(response)}]}]
                    }, 0.01

                result = broad_translation.translate_merged_ocr_lines_broad(
                    rows,
                    source_mode,
                    output_mode,
                    environ={"OPENAI_API_KEY": "test-key"},
                    luna_caller=caller,
                )
                self.assertEqual(1, calls)
                self.assertEqual(2, len(result))
                self.assertEqual(expected_original, result.loc[0, "Original"])

                response["semantic_units"]["unit-0000"]["translated_text"] = invalid_translation
                events = []
                with self.assertRaises(broad_translation.BroadTranslationError):
                    broad_translation.translate_merged_ocr_lines_broad(
                        rows,
                        source_mode,
                        output_mode,
                        diagnostic_logger=lambda phase, **fields: events.append(
                            {"phase": phase, **fields}
                        ),
                        environ={"OPENAI_API_KEY": "test-key"},
                        luna_caller=caller,
                    )
                failure = next(
                    event for event in events if event["phase"] == "objective_validation_failed"
                )
                self.assertEqual("arabic_digit_multiset", failure["failed_rule"])
                self.assertEqual(2, calls)

    @mock.patch.dict(
        os.environ,
        {
            "PATTERN_BROAD_TRANSLATION_ENABLED": "1",
            "OPENAI_API_KEY": "test-key",
        },
        clear=False,
    )
    def test_new_route_malformed_responses_fail_closed_without_legacy(self):
        cases = (
            ("English — US", "Simplified Chinese", self.english_index, "Rnd 1: 6 sc"),
        )
        malformed = {
            "output": [{"content": [{"type": "output_text", "text": "{not-json"}]}]
        }
        for source_mode, output_mode, index, source_text in cases:
            with self.subTest(source_mode=source_mode, output_mode=output_mode):
                rows = pd.DataFrame([_ocr_row(source_text)])
                with mock.patch.object(
                    broad_translation, "call_luna_once", return_value=(malformed, 0.01)
                ) as luna_mock, mock.patch.object(
                    line_translation,
                    "translate_ocr_line",
                    side_effect=AssertionError("legacy fallback executed"),
                ) as legacy_mock:
                    with self.assertRaises(broad_translation.BroadTranslationError):
                        ocr_lines.build_ocr_line_translations(
                            rows,
                            index,
                            self.df,
                            output_mode,
                            source_mode,
                        )
                self.assertEqual(1, luna_mock.call_count)
                legacy_mock.assert_not_called()

    @mock.patch.dict(
        os.environ,
        {
            "PATTERN_BROAD_TRANSLATION_ENABLED": "1",
            "OPENAI_API_KEY": "test-key",
        },
        clear=False,
    )
    def test_broad_flag_on_en_us_to_tc_uses_broad(self):
        rows = pd.DataFrame([_ocr_row("Rnd 1: 6 sc")])
        segments, _ = broad_translation.build_source_segments(rows)
        with mock.patch.object(
            broad_translation,
            "call_luna_once",
            side_effect=self._fake_luna(segments, ["第 1 圈：6 短針"]),
        ) as luna_mock:
            result = ocr_lines.build_ocr_line_translations(
                rows,
                self.english_index,
                self.df,
                "Traditional Chinese",
                "English — US",
            )
        self.assertEqual(luna_mock.call_count, 1)
        self.assertEqual(result.loc[0, "Translation"], "第 1 圈：6 短針")

    @mock.patch.dict(
        os.environ,
        {
            "PATTERN_BROAD_TRANSLATION_ENABLED": "1",
            "OPENAI_API_KEY": "test-key",
        },
        clear=False,
    )
    def test_broad_success_skips_legacy_paths(self):
        rows = pd.DataFrame([_ocr_row("Rnd 1: 6 sc")])
        segments, _ = broad_translation.build_source_segments(rows)
        with mock.patch.object(
            broad_translation,
            "call_luna_once",
            side_effect=self._fake_luna(segments, ["第 1 圈：6 短針"]),
        ):
            with mock.patch.object(
                line_translation, "translate_ocr_line", side_effect=AssertionError("legacy")
            ):
                ocr_lines.build_ocr_line_translations(
                    rows,
                    self.english_index,
                    self.df,
                    "Traditional Chinese",
                    "English — US",
                )

    @mock.patch.dict(
        os.environ,
        {
            "PATTERN_BROAD_TRANSLATION_ENABLED": "1",
            "OPENAI_API_KEY": "test-key",
        },
        clear=False,
    )
    def test_supported_route_broad_failures_skip_legacy_fallback(self):
        cases = (
            (
                "English — US",
                "Traditional Chinese",
                self.english_index,
                "Rnd 1: 6 sc",
            ),
            (
                "Simplified Chinese",
                "English — US",
                self.simplified_index,
                "第1圈：6短针",
            ),
            (
                "English — US",
                "Simplified Chinese",
                self.english_index,
                "Rnd 1: 6 sc",
            ),
        )
        for source_mode, output_mode, index, source_text in cases:
            with self.subTest(source_mode=source_mode, output_mode=output_mode):
                rows = pd.DataFrame([_ocr_row(source_text)])
                with mock.patch.object(
                    broad_translation,
                    "call_luna_once",
                    side_effect=TimeoutError("timeout"),
                ) as luna_mock, mock.patch.object(
                    line_translation,
                    "translate_ocr_line",
                    side_effect=AssertionError("legacy"),
                ) as legacy_mock:
                    with self.assertRaises(broad_translation.BroadTranslationError):
                        ocr_lines.build_ocr_line_translations(
                            rows,
                            index,
                            self.df,
                            output_mode,
                            source_mode,
                        )
                self.assertEqual(1, luna_mock.call_count)
                legacy_mock.assert_not_called()

    @mock.patch.dict(
        os.environ,
        {
            "PATTERN_BROAD_TRANSLATION_ENABLED": "1",
            "OPENAI_API_KEY": "test-key",
        },
        clear=False,
    )
    def test_traditional_chinese_to_english_uses_legacy(self):
        rows = pd.DataFrame([_ocr_row("第1圈：6短針")])
        with mock.patch.object(
            broad_translation,
            "translate_merged_ocr_lines_broad",
            side_effect=AssertionError("broad path executed"),
        ) as broad_mock, mock.patch.object(
            line_translation,
            "translate_ocr_line",
            return_value="legacy",
        ) as legacy_mock:
            result = ocr_lines.build_ocr_line_translations(
                rows,
                self.traditional_index,
                self.df,
                "English — US",
                "Traditional Chinese",
            )
        broad_mock.assert_not_called()
        legacy_mock.assert_called()
        self.assertEqual("legacy", result.loc[0, "Translation"])

    def test_unsupported_pair_uses_legacy(self):
        rows = pd.DataFrame([_ocr_row("R1: 6X")])
        with mock.patch.object(
            line_translation, "translate_ocr_line", return_value="legacy"
        ) as legacy_mock:
            result = ocr_lines.build_ocr_line_translations(
                rows,
                self.traditional_index,
                self.df,
                "Simplified Chinese",
                "Traditional Chinese",
            )
        legacy_mock.assert_called()
        self.assertEqual(result.loc[0, "Translation"], "legacy")


class BroadKeyedOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.rows = pd.DataFrame(
            [
                _ocr_row("Rnd 1:", min_x=0, max_x=20, min_y=0, max_y=10, confidence=0.9),
                _ocr_row("6 sc", min_x=30, max_x=60, min_y=0, max_y=10, confidence=0.5),
                _ocr_row("Rnd 2: 6 sc", min_x=0, max_x=70, min_y=40, max_y=60),
            ]
        )
        self.segments, self.segment_rows = broad_translation.build_source_segments(self.rows)
        self.expected_ids = [segment["source_segment_id"] for segment in self.segments]

    def _grouped_response(self) -> dict:
        return {
            "segment_assignments": {
                self.expected_ids[0]: "unit-0000",
                self.expected_ids[1]: "unit-0000",
                self.expected_ids[2]: "unit-0001",
            },
            "semantic_units": {
                "unit-0000": {"translated_text": "第 1 圈：6 短針"},
                "unit-0001": {"translated_text": "第 2 圈：6 短針"},
            },
        }

    def _provider_payload(self, response: dict) -> dict:
        return {
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": json.dumps(response)}
                    ]
                }
            ]
        }

    def test_multiple_segments_map_to_one_semantic_unit(self):
        units = broad_translation._parse_semantic_units(
            self._grouped_response(), self.expected_ids
        )
        self.assertEqual(2, len(units))
        self.assertEqual(self.expected_ids[:2], units[0]["source_segment_ids"])
        self.assertEqual("第 1 圈：6 短針", units[0]["translation"])

    def test_prompt_requires_keyed_ownership_without_independent_translation(self):
        prompt = broad_translation.build_prompt(
            self.segments,
            [],
            _route_config("English — US", "Traditional Chinese"),
        )
        self.assertIn("segment_assignments", prompt)
        self.assertIn("Every input source_segment_id must appear exactly once as a key", prompt)
        self.assertIn("Multiple adjacent source segments may map to the same semantic unit", prompt)
        self.assertIn('"translated_text":"..."', prompt)
        self.assertNotIn("array of objects each with source_segment_ids", prompt)

    def test_missing_segment_key_fails_with_coverage_diagnostics(self):
        response = self._grouped_response()
        del response["segment_assignments"][self.expected_ids[1]]
        events: list[dict] = []
        with self.assertRaises(broad_translation.BroadTranslationError):
            broad_translation._parse_semantic_units(
                response,
                self.expected_ids,
                diagnostic_logger=lambda phase, **fields: events.append(
                    {"phase": phase, **fields}
                ),
            )
        failure = next(event for event in events if event["phase"] == "id_coverage_validation_failed")
        self.assertEqual([self.expected_ids[1]], failure["missing_source_segment_ids"])
        self.assertEqual([], failure["duplicate_source_segment_ids"])

    def test_unknown_segment_key_fails_with_coverage_diagnostics(self):
        response = self._grouped_response()
        response["segment_assignments"]["segment-9999"] = "unit-0000"
        events: list[dict] = []
        with self.assertRaises(broad_translation.BroadTranslationError):
            broad_translation._parse_semantic_units(
                response,
                self.expected_ids,
                diagnostic_logger=lambda phase, **fields: events.append(
                    {"phase": phase, **fields}
                ),
            )
        failure = next(event for event in events if event["phase"] == "id_coverage_validation_failed")
        self.assertEqual(["segment-9999"], failure["unknown_source_segment_ids"])

    def test_assignment_to_nonexistent_semantic_unit_fails(self):
        response = self._grouped_response()
        response["segment_assignments"][self.expected_ids[2]] = "unit-9999"
        with self.assertRaises(broad_translation._BroadResponseParsingError) as ctx:
            broad_translation._parse_semantic_units(response, self.expected_ids)
        self.assertEqual(
            "assignment_references_unknown_semantic_unit", ctx.exception.reason
        )

    def test_orphan_semantic_unit_fails(self):
        response = self._grouped_response()
        response["semantic_units"]["unit-orphan"] = {"translated_text": "孤立"}
        with self.assertRaises(broad_translation._BroadResponseParsingError) as ctx:
            broad_translation._parse_semantic_units(response, self.expected_ids)
        self.assertEqual("orphan_semantic_unit", ctx.exception.reason)

    def test_duplicate_ownership_is_unrepresentable_after_json_decode(self):
        raw = (
            '{"segment_assignments":{"segment-0000":"unit-0000",'
            '"segment-0000":"unit-0000"},"semantic_units":'
            '{"unit-0000":{"translated_text":"第 1 圈：6 短針"}}}'
        )
        with self.assertRaises(broad_translation._BroadResponseParsingError) as ctx:
            broad_translation._parse_model_json(raw)
        self.assertEqual("semantic_unit_schema", ctx.exception.stage)
        self.assertEqual("duplicate_json_object_key", ctx.exception.reason)

    def test_grouping_reconstructs_existing_line_df_geometry(self):
        units = broad_translation._parse_semantic_units(
            self._grouped_response(), self.expected_ids
        )
        line_df = broad_translation.adapt_semantic_units_to_line_df(
            units, self.segments, self.segment_rows
        )
        self.assertEqual(2, len(line_df))
        self.assertEqual("Rnd 1:\n6 sc", line_df.loc[0, "Original"])
        self.assertEqual(0.5, line_df.loc[0, "Confidence"])
        self.assertEqual(0.0, line_df.loc[0, "min_x"])
        self.assertEqual(60.0, line_df.loc[0, "max_x"])

    def test_objective_validators_run_after_keyed_reconstruction(self):
        response = self._grouped_response()
        response["semantic_units"]["unit-0000"]["translated_text"] = "第 1 圈：5 短針"
        calls = 0
        events: list[dict] = []

        def caller(_prompt: str, _api_key: str):
            nonlocal calls
            calls += 1
            return self._provider_payload(response), 0.01

        with self.assertRaises(broad_translation.BroadTranslationError):
            broad_translation.translate_merged_ocr_lines_broad(
                self.rows,
                source_mode="English — US",
                output_mode="Traditional Chinese",
                diagnostic_logger=lambda phase, **fields: events.append(
                    {"phase": phase, **fields}
                ),
                environ={"OPENAI_API_KEY": "test-key"},
                luna_caller=caller,
            )
        self.assertEqual(1, calls)
        failure = next(event for event in events if event["phase"] == "objective_validation_failed")
        self.assertEqual("arabic_digit_multiset", failure["failed_rule"])

    def test_normal_broad_path_uses_one_call_and_no_retry_events(self):
        calls = 0
        events: list[dict] = []

        def caller(_prompt: str, _api_key: str):
            nonlocal calls
            calls += 1
            return self._provider_payload(self._grouped_response()), 0.01

        result = broad_translation.translate_merged_ocr_lines_broad(
            self.rows,
            source_mode="English — US",
            output_mode="Traditional Chinese",
            diagnostic_logger=lambda phase, **fields: events.append(
                {"phase": phase, **fields}
            ),
            environ={"OPENAI_API_KEY": "test-key"},
            luna_caller=caller,
        )
        self.assertEqual(1, calls)
        self.assertEqual(2, len(result))
        self.assertFalse(any(event["phase"].startswith("broad_retry") for event in events))
        self.assertFalse(
            hasattr(broad_translation, "_build_duplicate_ownership_correction_prompt")
        )

    @mock.patch.dict(
        os.environ,
        {"PATTERN_BROAD_TRANSLATION_ENABLED": "1", "OPENAI_API_KEY": "test-key"},
        clear=False,
    )
    def test_keyed_broad_path_never_enters_legacy_fallback(self):
        rows = pd.DataFrame([_ocr_row("Rnd 1: 6 sc")])
        segments, _ = broad_translation.build_source_segments(rows)
        response = _keyed_response_from_units(
            _valid_units(segments, ["第 1 圈：6 短針"])
        )
        with mock.patch.object(
            broad_translation,
            "call_luna_once",
            return_value=(self._provider_payload(response), 0.01),
        ) as luna:
            with mock.patch.object(
                line_translation,
                "translate_ocr_line",
                side_effect=AssertionError("legacy fallback executed"),
            ):
                result = ocr_lines.build_ocr_line_translations(
                    rows,
                    {},
                    pd.DataFrame(),
                    "Traditional Chinese",
                    "English — US",
                )
        self.assertEqual(1, luna.call_count)
        self.assertEqual(1, len(result))


class BroadProviderTests(unittest.TestCase):
    def _response_parsing_failure_events(self, payload: object) -> tuple[list[dict], Exception]:
        rows = pd.DataFrame([_ocr_row("SECRET_OCR_SOURCE_Rnd_1: 6 sc")])
        events: list[dict] = []

        def logger(phase: str, **fields: object) -> None:
            events.append({"phase": phase, **fields})

        def fake_luna(prompt: str, api_key: str):
            self.assertIn("SECRET_OCR_SOURCE", prompt)
            self.assertEqual("sk-secret-test-key", api_key)
            return payload, 0.01

        with self.assertRaises(broad_translation.BroadTranslationError) as ctx:
            broad_translation.translate_merged_ocr_lines_broad(
                rows,
                source_mode="English — US",
                output_mode="Traditional Chinese",
                diagnostic_logger=logger,
                environ={"OPENAI_API_KEY": "sk-secret-test-key"},
                luna_caller=fake_luna,
            )
        return events, ctx.exception

    def _parse_failure_event(self, events: list[dict]) -> dict:
        failures = [
            event for event in events if event.get("phase") == "broad_response_parse_failed"
        ]
        self.assertEqual(1, len(failures))
        return failures[0]

    def _assert_safe_parse_events(self, events: list[dict]) -> None:
        blob = json.dumps(events, ensure_ascii=False)
        for forbidden in (
            "SECRET_OCR_SOURCE",
            "SECRET_MODEL_TEXT",
            "sk-secret-test-key",
            "authoritative_crochet_glossary",
            "source_segments",
        ):
            self.assertNotIn(forbidden, blob)

    def test_provider_envelope_failure_has_safe_stage_diagnostics(self):
        events, exc = self._response_parsing_failure_events({"output": "SECRET_MODEL_TEXT"})
        failure = self._parse_failure_event(events)
        self.assertEqual("provider_envelope", failure["stage"])
        self.assertEqual("_BroadResponseParsingError", failure["exception_type"])
        self.assertEqual("provider_output_not_array", failure["reason"])
        self.assertEqual("object_with_output_array", failure["expected_top_level_shape"])
        self.assertEqual("broad", failure["route"])
        self.assertEqual(broad_translation.BROAD_MODEL, failure["model"])
        self.assertEqual(1, failure["call_ordinal"])
        self.assertGreaterEqual(failure["elapsed_seconds"], 0)
        self.assertEqual(type(exc), broad_translation.BroadTranslationError)
        self.assertEqual((), exc.args)
        self._assert_safe_parse_events(events)

    def test_json_decode_failure_has_safe_stage_diagnostics(self):
        payload = {
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": "{SECRET_MODEL_TEXT invalid json"}
                    ]
                }
            ]
        }
        events, exc = self._response_parsing_failure_events(payload)
        failure = self._parse_failure_event(events)
        self.assertEqual("json_decode", failure["stage"])
        self.assertEqual("JSONDecodeError", failure["exception_type"])
        self.assertEqual("model_output_not_valid_json", failure["reason"])
        self.assertEqual("json_object", failure["expected_top_level_shape"])
        self.assertEqual(type(exc), broad_translation.BroadTranslationError)
        self.assertEqual((), exc.args)
        self._assert_safe_parse_events(events)

    def test_semantic_unit_schema_failure_has_safe_stage_diagnostics(self):
        payload = {
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {
                                    "segment_assignments": {
                                        "segment-0000": "unit-0000"
                                    },
                                    "semantic_units": {
                                        "unit-0000": {
                                            "translated_text": "SECRET_MODEL_TEXT",
                                            "unexpected": True,
                                        }
                                    },
                                }
                            ),
                        }
                    ]
                }
            ]
        }
        events, exc = self._response_parsing_failure_events(payload)
        failure = self._parse_failure_event(events)
        self.assertEqual("semantic_unit_schema", failure["stage"])
        self.assertEqual("_BroadResponseParsingError", failure["exception_type"])
        self.assertEqual("semantic_unit_shape_invalid", failure["reason"])
        self.assertEqual(
            "object_with_segment_assignments_and_semantic_units_objects",
            failure["expected_top_level_shape"],
        )
        self.assertEqual("object", failure["actual_top_level_json_type"])
        self.assertEqual(1, failure["semantic_unit_count"])
        self.assertEqual(type(exc), broad_translation.BroadTranslationError)
        self.assertEqual((), exc.args)
        self._assert_safe_parse_events(events)

    def test_decoded_non_object_is_semantic_unit_schema_failure(self):
        payload = {
            "output": [
                {"content": [{"type": "output_text", "text": '["SECRET_MODEL_TEXT"]'}]}
            ]
        }
        events, exc = self._response_parsing_failure_events(payload)
        failure = self._parse_failure_event(events)
        self.assertEqual("semantic_unit_schema", failure["stage"])
        self.assertEqual("decoded_json_not_object", failure["reason"])
        self.assertEqual("array", failure["actual_top_level_json_type"])
        self.assertEqual(type(exc), broad_translation.BroadTranslationError)
        self.assertEqual((), exc.args)
        self._assert_safe_parse_events(events)

    def test_malformed_response_shapes_raise_controlled_error(self):
        segments = [{"source_segment_id": "segment-0000", "text": "Rnd 1: 6 sc"}]
        config = _route_config("English — US", "Traditional Chinese")
        with self.assertRaises(broad_translation.BroadTranslationError):
            broad_translation._parse_response_payload({"output": "bad"})
        with self.assertRaises(broad_translation.BroadTranslationError):
            broad_translation._parse_response_payload(
                {"output": [{"content": [{"type": "other", "text": "{}"}]}]}
            )
        with self.assertRaises(broad_translation.BroadTranslationError):
            broad_translation._parse_semantic_units(
                {"segment_assignments": {}, "semantic_units": "bad"},
                ["segment-0000"],
            )

    def test_malformed_json_raises_controlled_error(self):
        with self.assertRaises(broad_translation.BroadTranslationError):
            broad_translation._parse_model_json("{bad json")

    @mock.patch.dict(
        os.environ,
        {"PATTERN_BROAD_TRANSLATION_ENABLED": "1", "OPENAI_API_KEY": ""},
        clear=False,
    )
    def test_missing_api_key_when_broad_invoked(self):
        rows = pd.DataFrame([_ocr_row("Rnd 1: 6 sc")])
        with self.assertRaises(broad_translation.BroadTranslationError):
            broad_translation.translate_merged_ocr_lines_broad(
                rows,
                source_mode="English — US",
                output_mode="Traditional Chinese",
            )

    def _provider_failure_events(self, error: Exception) -> tuple[list[dict], broad_translation.BroadTranslationError]:
        rows = pd.DataFrame([_ocr_row("SECRET_OCR_SOURCE_Rnd_1: 6 sc")])
        events: list[dict] = []

        def logger(phase: str, **fields: object) -> None:
            events.append({"phase": phase, **fields})

        with mock.patch.object(broad_translation, "call_luna_once", side_effect=error):
            with self.assertRaises(broad_translation.BroadTranslationError) as ctx:
                broad_translation.translate_merged_ocr_lines_broad(
                    rows,
                    source_mode="English — US",
                    output_mode="Traditional Chinese",
                    diagnostic_logger=logger,
                    environ={
                        "OPENAI_API_KEY": "sk-secret-test-key",
                        "PATTERN_BROAD_TRANSLATION_ENABLED": "1",
                    },
                )
        return events, ctx.exception

    def _provider_end_event(self, events: list[dict]) -> dict:
        end_events = [event for event in events if event.get("phase") == "ai_request_end"]
        self.assertEqual(1, len(end_events))
        return end_events[0]

    def _assert_no_sensitive_diagnostics(self, events: list[dict]) -> None:
        blob = json.dumps(events, ensure_ascii=False)
        for forbidden in (
            "SECRET_OCR_SOURCE",
            "sk-secret-test-key",
            "Authorization",
            "authoritative_crochet_glossary",
            "source_segments",
        ):
            self.assertNotIn(forbidden, blob)

    def test_http_error_records_classification_and_raises_controlled_error(self):
        error = urllib.error.HTTPError(
            url="https://api.openai.com/v1/responses",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=io.BytesIO(b""),
        )
        events, exc = self._provider_failure_events(error)
        end_event = self._provider_end_event(events)
        self.assertEqual("provider_error", end_event["outcome"])
        self.assertEqual("http_error", end_event["provider_failure_type"])
        self.assertEqual("HTTPError", end_event["exception_type"])
        self.assertEqual("http_transport_rejected", end_event["failure_classification"])
        self.assertEqual("429", end_event["http_status"])
        self.assertEqual("Too_Many_Requests", end_event["http_reason"])
        self.assertEqual("", str(exc))
        self.assertEqual((), exc.args)
        self._assert_no_sensitive_diagnostics(events)

    def test_url_error_records_classification_and_raises_controlled_error(self):
        events, exc = self._provider_failure_events(urllib.error.URLError("network unreachable"))
        end_event = self._provider_end_event(events)
        self.assertEqual("url_error", end_event["provider_failure_type"])
        self.assertEqual("URLError", end_event["exception_type"])
        self.assertEqual("url_transport_failed", end_event["failure_classification"])
        self.assertEqual("network_unreachable", end_event["url_error_reason"])
        self.assertEqual("", str(exc))
        self._assert_no_sensitive_diagnostics(events)

    def test_timeout_error_records_classification_and_raises_controlled_error(self):
        events, exc = self._provider_failure_events(TimeoutError())
        end_event = self._provider_end_event(events)
        self.assertEqual("timeout", end_event["provider_failure_type"])
        self.assertEqual("TimeoutError", end_event["exception_type"])
        self.assertEqual("request_timeout", end_event["failure_classification"])
        self.assertEqual("", str(exc))
        self._assert_no_sensitive_diagnostics(events)

    def test_json_decode_error_records_classification_and_raises_controlled_error(self):
        events, exc = self._provider_failure_events(
            json.JSONDecodeError("Expecting value", "not-json", 0)
        )
        end_event = self._provider_end_event(events)
        self.assertEqual("json_decode", end_event["provider_failure_type"])
        self.assertEqual("JSONDecodeError", end_event["exception_type"])
        self.assertEqual("response_json_parse_failed", end_event["failure_classification"])
        self.assertEqual("", str(exc))
        self._assert_no_sensitive_diagnostics(events)

    def test_value_error_records_classification_and_raises_controlled_error(self):
        events, exc = self._provider_failure_events(ValueError("bad provider value"))
        end_event = self._provider_end_event(events)
        self.assertEqual("value_error", end_event["provider_failure_type"])
        self.assertEqual("ValueError", end_event["exception_type"])
        self.assertEqual("provider_value_error", end_event["failure_classification"])
        self.assertEqual("", str(exc))
        self.assertNotIn("bad provider value", json.dumps(events))
        self._assert_no_sensitive_diagnostics(events)


class BroadServiceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full_df = pd.read_csv("knowledge_base/data/master_stitches.csv").fillna("")
        cls.df_en, cls.index_en = prepare_translation_dataframe(cls.full_df, "English — US")
        cls.df_sc, cls.index_sc = prepare_translation_dataframe(
            cls.full_df, "Simplified Chinese"
        )

    def _request(self, source_mode, output_mode, index, df, area_mode="Whole Pattern"):
        from PIL import Image

        image = Image.new("RGB", (120, 80), color=(255, 255, 255))
        crop_box = (0, 0, image.size[0], image.size[1])
        return TranslateImageRequest(
            image=image,
            selected_image=image,
            working_image=image,
            source_mode=source_mode,
            output_mode=output_mode,
            area_mode=area_mode,
            crop_box=crop_box,
            df=df,
            index=index,
            diagnostic_request_id="broad-integration",
            diagnostic_session_generation="broad-integration",
            action_started=None,
            image_load_seconds=0.01,
            crop_extraction_seconds=0.02,
            quality_metrics={"width_px": 120, "height_px": 80},
            quality_errors=[],
            quality_warnings=[],
            quality_label="Good",
            experimental_downscale=False,
            downscale_max_height_option="Original / no resize",
            ocr_resize_test="1000 px",
            session_diagnostics={"ocr_started_at": "2026-01-01 00:00:00"},
            diagnostic_events=[],
            diagnostic_platform="unit-test",
            interface_language="English",
            ocr_execution_start=__import__("time").perf_counter() - 0.1,
        )

    @mock.patch("pattern_translator.translation_service.run_primary_ocr")
    @mock.patch.dict(
        os.environ,
        {"PATTERN_BROAD_TRANSLATION_ENABLED": "1", "OPENAI_API_KEY": "test-key"},
        clear=False,
    )
    def test_whole_pattern_compatible(self, mock_run_primary_ocr):
        ocr_rows = pd.DataFrame([_ocr_row("Rnd 1: 6 sc")])
        mock_run_primary_ocr.return_value = {
            "selected_name": "PaddleOCR",
            "selected_text": "Rnd 1: 6 sc",
            "selected_rows": ocr_rows,
            "paddle_inference_seconds": 0.1,
        }
        segments, _ = broad_translation.build_source_segments(ocr_rows)

        def fake_luna(prompt, api_key):
            del prompt, api_key
            return {
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    _keyed_response_from_units(
                                        _valid_units(
                                            segments, ["第 1 圈：6 短針"]
                                        )
                                    )
                                ),
                            }
                        ]
                    }
                ]
            }, 0.01

        with mock.patch.object(broad_translation, "call_luna_once", side_effect=fake_luna):
            result = translate_image(
                self._request(
                    "English — US",
                    "Traditional Chinese",
                    self.index_en,
                    self.df_en,
                )
            )
        primary = result.primary_result
        self.assertEqual(primary["line_df"].loc[0, "Translation"], "第 1 圈：6 短針")
        self.assertIn("overlay_png", primary)


if __name__ == "__main__":
    unittest.main()
