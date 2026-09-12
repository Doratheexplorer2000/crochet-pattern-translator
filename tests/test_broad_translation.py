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
from pattern_translator.engine import shadow_title_classifier


ROUTES = (
    ("English — US", "English — UK"),
    ("English — US", "Traditional Chinese"),
    ("English — US", "Simplified Chinese"),
    ("English — US", "Japanese"),
    ("English — UK", "English — US"),
    ("English — UK", "Traditional Chinese"),
    ("English — UK", "Simplified Chinese"),
    ("English — UK", "Japanese"),
    ("Simplified Chinese", "English — US"),
    ("Simplified Chinese", "English — UK"),
    ("Simplified Chinese", "Traditional Chinese"),
    ("Simplified Chinese", "Japanese"),
    ("Traditional Chinese", "English — US"),
    ("Traditional Chinese", "English — UK"),
    ("Traditional Chinese", "Simplified Chinese"),
    ("Traditional Chinese", "Japanese"),
    ("Japanese", "English — US"),
    ("Japanese", "English — UK"),
    ("Japanese", "Traditional Chinese"),
    ("Japanese", "Simplified Chinese"),
)


def _ocr_row(text: str, **geometry) -> dict:
    values = {
        "text": text,
        "semantic_text": text,
        "confidence": 0.95,
        "x": 10.0,
        "global_x": 10.0,
        "y": 10.0,
        "min_x": 0.0,
        "max_x": 120.0,
        "min_y": 0.0,
        "max_y": 20.0,
    }
    values.update(geometry)
    return values


def _response_text(response: object) -> dict:
    return {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": json.dumps(response, ensure_ascii=False)}
                ]
            }
        ]
    }


def _keyed_response(
    segments: list[dict[str, str]],
    translations: list[str],
) -> dict:
    assignments = {}
    units = {}
    for index, (segment, translation) in enumerate(zip(segments, translations)):
        unit_id = f"unit-{index:04d}"
        assignments[segment["source_segment_id"]] = unit_id
        units[unit_id] = {"translated_text": translation}
    return {"segment_assignments": assignments, "semantic_units": units}


def _translate(
    sources: list[str],
    translations: list[str],
    *,
    source_mode: str = "Simplified Chinese",
    output_mode: str = "Japanese",
    events: list[dict] | None = None,
) -> tuple[pd.DataFrame, mock.Mock, list[str]]:
    rows = pd.DataFrame(
        [
            _ocr_row(
                source,
                y=index * 30.0,
                min_y=index * 30.0,
                max_y=index * 30.0 + 20.0,
            )
            for index, source in enumerate(sources)
        ]
    )
    segments, _ = broad_translation.build_source_segments(rows)
    prompts: list[str] = []

    def call(prompt: str, api_key: str):
        if api_key != "test-key":
            raise AssertionError("unexpected API key")
        prompts.append(prompt)
        return _response_text(_keyed_response(segments, translations)), 0.01

    caller = mock.Mock(side_effect=call)
    result = broad_translation.translate_merged_ocr_lines_broad(
        rows,
        source_mode,
        output_mode,
        diagnostic_logger=(
            None
            if events is None
            else lambda phase, **fields: events.append({"phase": phase, **fields})
        ),
        environ={"OPENAI_API_KEY": "test-key"},
        luna_caller=caller,
    )
    return result, caller, prompts


class LunaPrimaryAcceptanceTests(unittest.TestCase):
    def test_former_false_rejection_classes_are_accepted_without_retry(self):
        cases = (
            ("倒二钩短针", "針から2目めに細編みを編む"),
            ("R2:6v=12", "第2段：増し目を6回行い、合計12目"),
            ("R3:(x,V)*6=18", "3段目は（細編み、増し目）を6回繰り返す"),
            (
                "R15:(2ch4F的泡芙针),x,(5F的泡芙针,x)*5=12",
                "15段目：鎖2目と長編み4目のパフ、細編み、続いて長編み5目のパフと細編みを5回",
            ),
        )
        for source, translation in cases:
            with self.subTest(source=source):
                events: list[dict] = []
                result, caller, _ = _translate([source], [translation], events=events)
                caller.assert_called_once()
                self.assertEqual(translation, result.loc[0, "Translation"])
                self.assertEqual("validated", result.loc[0, "Validation Status"])
                self.assertEqual("", result.loc[0, "Validation Failure Reason"])
                self.assertFalse(
                    any(event["phase"] == "broad_retry_scheduled" for event in events)
                )

    def test_linguistically_suspicious_but_structurally_valid_output_is_accepted(self):
        events: list[dict] = []
        result, caller, _ = _translate(
            ["第4圈：5短针，长度10cm"],
            ["自然な日本語の表現で数量を明示せず説明する"],
            events=events,
        )
        caller.assert_called_once()
        self.assertEqual("validated", result.loc[0, "Validation Status"])
        self.assertFalse(
            any(
                event["phase"] == "unit_integrity_validation_failed"
                for event in events
            )
        )

    def test_normal_success_uses_one_whole_pattern_request(self):
        sources = ["标题", "第1圈：6短针", "缝合部件"]
        translations = ["タイトル", "第1段：細編み6目", "パーツを縫い付ける"]
        result, caller, prompts = _translate(sources, translations)
        caller.assert_called_once()
        self.assertEqual(translations, result["Translation"].tolist())
        payload = json.loads(prompts[0].split("INPUT: ", 1)[1])
        self.assertEqual(
            sources,
            [segment["text"] for segment in payload["source_segments"]],
        )

    def test_new_route_families_accept_structurally_valid_output_once(self):
        cases = (
            ("English — US", "English — UK", "Rnd 1: 6 sc", "Round 1: 6 dc"),
            ("English — UK", "English — US", "Round 1: 6 dc", "Rnd 1: 6 sc"),
            ("English — UK", "Traditional Chinese", "Round 1: 6 dc", "第1圈：6短針"),
            ("English — UK", "Simplified Chinese", "Round 1: 6 dc", "第1圈：6短针"),
            ("English — UK", "Japanese", "Round 1: 6 dc", "第1段：細編み6目"),
            ("Traditional Chinese", "Simplified Chinese", "第1圈：6短針", "第1圈：6短针"),
            ("Simplified Chinese", "Traditional Chinese", "第1圈：6短针", "第1圈：6短針"),
            ("Japanese", "English — US", "第1段：細編み6目", "Rnd 1: 6 sc"),
            ("Japanese", "English — UK", "第1段：細編み6目", "Round 1: 6 dc"),
            ("Japanese", "Traditional Chinese", "第1段：細編み6目", "第1圈：6短針"),
            ("Japanese", "Simplified Chinese", "第1段：細編み6目", "第1圈：6短针"),
        )
        for source_mode, output_mode, source, translation in cases:
            with self.subTest(route=(source_mode, output_mode)):
                result, caller, prompts = _translate(
                    [source],
                    [translation],
                    source_mode=source_mode,
                    output_mode=output_mode,
                )
                caller.assert_called_once()
                self.assertEqual("validated", result.loc[0, "Validation Status"])
                self.assertEqual(translation, result.loc[0, "Translation"])
                payload = json.loads(prompts[0].split("INPUT: ", 1)[1])
                self.assertEqual(
                    broad_translation._route_config(
                        source_mode,
                        output_mode,
                    ).source_language,
                    payload["source_language"],
                )
                self.assertEqual(
                    broad_translation._route_config(
                        source_mode,
                        output_mode,
                    ).target_language,
                    payload["target_language"],
                )


class PromptAndGlossaryContractTests(unittest.TestCase):
    def test_all_routes_receive_full_route_relevant_glossary_and_strict_schema(self):
        source_fields = {
            "English — US": {
                "english_us",
                "english_us_aliases",
                "english_us_abbreviations",
            },
            "English — UK": {
                "english_uk",
                "english_uk_aliases",
                "english_uk_abbreviations",
            },
            "Simplified Chinese": {
                "simplified_chinese_authoritative_term",
                "simplified_chinese_aliases",
                "simplified_chinese_abbreviation",
            },
            "Traditional Chinese": {
                "traditional_chinese",
                "traditional_chinese_aliases",
                "traditional_chinese_abbreviation",
            },
            "Japanese": {"japanese", "japanese_aliases"},
        }
        target_fields = {
            "Traditional Chinese": source_fields["Traditional Chinese"],
            "Simplified Chinese": source_fields["Simplified Chinese"],
            "English — US": source_fields["English — US"],
            "English — UK": source_fields["English — UK"],
            "Japanese": source_fields["Japanese"],
        }
        all_language_fields = set().union(
            *source_fields.values(),
            *target_fields.values(),
        )
        segments = [
            {"source_segment_id": "segment-0000", "text": "complete first segment"},
            {"source_segment_id": "segment-0001", "text": "complete second segment"},
        ]
        for source_mode, output_mode in ROUTES:
            with self.subTest(route=(source_mode, output_mode)):
                config = broad_translation._route_config(source_mode, output_mode)
                terms = broad_translation.build_glossary(source_mode, output_mode)
                prompt = broad_translation.build_prompt(segments, terms, config)
                payload = json.loads(prompt.split("INPUT: ", 1)[1])
                self.assertEqual(config.source_language, payload["source_language"])
                self.assertEqual(config.target_language, payload["target_language"])
                self.assertEqual(segments, payload["source_segments"])
                self.assertEqual(
                    terms,
                    payload["authoritative_crochet_glossary"],
                )
                self.assertIn("specialist crochet-pattern translation agent", prompt)
                self.assertIn("segment_assignments", prompt)
                self.assertIn("semantic_units", prompt)
                self.assertIn(
                    "Every input source_segment_id must appear exactly once",
                    prompt,
                )
                self.assertIn("Do not invent missing instructions", prompt)
                self.assertIn("silently repair genuinely ambiguous OCR", prompt)
                if output_mode == "English — US":
                    self.assertIn("Use US English crochet terminology", prompt)
                if output_mode == "English — UK":
                    self.assertIn("Use UK English crochet terminology", prompt)
                allowed = (
                    {"concept_id", "category"}
                    | source_fields[source_mode]
                    | target_fields[output_mode]
                )
                present_across_glossary = set().union(
                    *(set(entry) for entry in terms)
                )
                self.assertTrue(
                    source_fields[source_mode].issubset(
                        present_across_glossary
                    )
                )
                self.assertTrue(
                    target_fields[output_mode].issubset(
                        present_across_glossary
                    )
                )
                for entry in terms:
                    present_language_fields = set(entry) & all_language_fields
                    self.assertTrue(present_language_fields)
                    self.assertTrue(present_language_fields.issubset(allowed))

    def test_measured_full_glossaries_remain_bounded(self):
        expected = {
            ("English — US", "English — UK"): (82, 23986),
            ("English — US", "Traditional Chinese"): (83, 21855),
            ("Simplified Chinese", "English — US"): (83, 23209),
            ("Simplified Chinese", "English — UK"): (82, 22972),
            ("Simplified Chinese", "Traditional Chinese"): (83, 20882),
            ("Simplified Chinese", "Japanese"): (43, 9414),
            ("English — US", "Simplified Chinese"): (83, 23209),
            ("English — US", "Japanese"): (43, 9536),
            ("English — UK", "English — US"): (82, 23986),
            ("English — UK", "Traditional Chinese"): (82, 21634),
            ("English — UK", "Simplified Chinese"): (82, 22972),
            ("English — UK", "Japanese"): (42, 9326),
            ("Traditional Chinese", "English — US"): (83, 21855),
            ("Traditional Chinese", "English — UK"): (82, 21634),
            ("Traditional Chinese", "Simplified Chinese"): (83, 20882),
            ("Traditional Chinese", "Japanese"): (43, 8722),
            ("Japanese", "English — US"): (43, 9536),
            ("Japanese", "English — UK"): (42, 9326),
            ("Japanese", "Traditional Chinese"): (43, 8722),
            ("Japanese", "Simplified Chinese"): (43, 9414),
        }
        self.assertEqual(set(ROUTES), set(expected))
        for route, measured in expected.items():
            with self.subTest(route=route):
                terms = broad_translation.build_glossary(*route)
                self.assertEqual(
                    measured,
                    (len(terms), broad_translation._glossary_char_count(terms)),
                )


class StructuralSchemaTests(unittest.TestCase):
    IDS = ["segment-0000", "segment-0001", "segment-0002"]

    def _assert_schema_failure(self, response: object, reason: str) -> None:
        with self.assertRaises(
            broad_translation._BroadResponseParsingError
        ) as caught:
            broad_translation._parse_semantic_units(response, self.IDS)
        self.assertEqual(reason, caught.exception.reason)

    def test_malformed_json_and_duplicate_json_keys_fail(self):
        with self.assertRaises(
            broad_translation._BroadResponseParsingError
        ) as malformed:
            broad_translation._parse_model_json("{not json")
        self.assertEqual("model_output_not_valid_json", malformed.exception.reason)

        duplicate = (
            '{"segment_assignments":{"segment-0000":"unit-0",'
            '"segment-0000":"unit-1"},"semantic_units":{}}'
        )
        with self.assertRaises(
            broad_translation._BroadResponseParsingError
        ) as caught:
            broad_translation._parse_model_json(duplicate)
        self.assertEqual("duplicate_json_object_key", caught.exception.reason)

    def test_wrong_top_level_schema_and_field_types_fail(self):
        self._assert_schema_failure([], "decoded_json_not_object")
        self._assert_schema_failure(
            {"semantic_units": {}},
            "unexpected_top_level_keys",
        )
        self._assert_schema_failure(
            {"segment_assignments": [], "semantic_units": {}},
            "segment_assignments_not_object",
        )
        self._assert_schema_failure(
            {"segment_assignments": {}, "semantic_units": []},
            "semantic_units_not_object",
        )

    def test_missing_and_unknown_segments_fail_exact_coverage(self):
        missing = {
            "segment_assignments": {
                "segment-0000": "unit-0",
                "segment-0001": "unit-1",
            },
            "semantic_units": {
                "unit-0": {"translated_text": "a"},
                "unit-1": {"translated_text": "b"},
            },
        }
        self._assert_schema_failure(missing, "source_segment_coverage_invalid")
        unknown = {
            "segment_assignments": {
                "segment-0000": "unit-0",
                "segment-0001": "unit-1",
                "unknown": "unit-2",
            },
            "semantic_units": {
                "unit-0": {"translated_text": "a"},
                "unit-1": {"translated_text": "b"},
                "unit-2": {"translated_text": "c"},
            },
        }
        self._assert_schema_failure(unknown, "source_segment_coverage_invalid")

    def test_undefined_orphan_and_noncontiguous_units_fail(self):
        undefined = {
            "segment_assignments": {item: "missing" for item in self.IDS},
            "semantic_units": {},
        }
        self._assert_schema_failure(
            undefined,
            "assignment_references_unknown_semantic_unit",
        )
        orphan = {
            "segment_assignments": {item: "unit-0" for item in self.IDS},
            "semantic_units": {
                "unit-0": {"translated_text": "ok"},
                "orphan": {"translated_text": "unused"},
            },
        }
        self._assert_schema_failure(orphan, "orphan_semantic_unit")
        noncontiguous = {
            "segment_assignments": {
                "segment-0000": "unit-a",
                "segment-0001": "unit-b",
                "segment-0002": "unit-a",
            },
            "semantic_units": {
                "unit-a": {"translated_text": "a"},
                "unit-b": {"translated_text": "b"},
            },
        }
        self._assert_schema_failure(
            noncontiguous,
            "semantic_unit_assignments_not_contiguous",
        )

    def test_duplicate_ownership_in_normalized_units_fails(self):
        units = [
            {
                "source_segment_ids": ["segment-0000", "segment-0001"],
                "translation": "a",
            },
            {
                "source_segment_ids": ["segment-0001", "segment-0002"],
                "translation": "b",
            },
        ]
        segments = [
            {"source_segment_id": item, "text": item}
            for item in self.IDS
        ]
        with self.assertRaises(broad_translation._BroadResponseParsingError):
            broad_translation.validate_semantic_units(
                units,
                segments,
                broad_translation._route_config("English — US", "Japanese"),
            )


class UnitIntegrityTests(unittest.TestCase):
    def test_one_blank_unit_preserves_source_without_suppressing_sibling(self):
        result, caller, _ = _translate(
            ["第1圈：6短针", "缝合部件"],
            ["第1段：細編み6目", "   "],
        )
        caller.assert_called_once()
        self.assertEqual("第1段：細編み6目", result.loc[0, "Translation"])
        self.assertEqual("validated", result.loc[0, "Validation Status"])
        self.assertEqual("缝合部件", result.loc[1, "Translation"])
        self.assertEqual("unresolved", result.loc[1, "Validation Status"])
        self.assertEqual(
            "blank_translation",
            result.loc[1, "Validation Failure Reason"],
        )

    def test_protected_placeholder_corruption_preserves_only_affected_unit(self):
        rows = pd.DataFrame(
            [
                _ocr_row("第1圈：6短针"),
                _ocr_row(
                    "访问 example.com 获取图样",
                    y=30,
                    min_y=30,
                    max_y=50,
                ),
            ]
        )
        prompts: list[str] = []

        def caller(prompt: str, _api_key: str):
            prompts.append(prompt)
            payload = json.loads(prompt.split("INPUT: ", 1)[1])
            segments = payload["source_segments"]
            self.assertIn("__ciurl", segments[1]["text"])
            response = _keyed_response(
                segments,
                ["第1段：細編み6目", "パターンを見る"],
            )
            return _response_text(response), 0.01

        result = broad_translation.translate_merged_ocr_lines_broad(
            rows,
            "Simplified Chinese",
            "Japanese",
            environ={"OPENAI_API_KEY": "test-key"},
            luna_caller=caller,
        )
        self.assertEqual(1, len(prompts))
        self.assertEqual("validated", result.loc[0, "Validation Status"])
        self.assertEqual("访问 example.com 获取图样", result.loc[1, "Translation"])
        self.assertEqual(
            "protected_url_or_domain",
            result.loc[1, "Validation Failure Reason"],
        )

    def test_correct_protected_placeholder_round_trips(self):
        rows = pd.DataFrame([_ocr_row("访问 example.com 获取图样")])

        def caller(prompt: str, _api_key: str):
            payload = json.loads(prompt.split("INPUT: ", 1)[1])
            protected = payload["source_segments"][0]["text"]
            response = _keyed_response(
                payload["source_segments"],
                [f"{protected} を見る"],
            )
            return _response_text(response), 0.01

        result = broad_translation.translate_merged_ocr_lines_broad(
            rows,
            "Simplified Chinese",
            "Japanese",
            environ={"OPENAI_API_KEY": "test-key"},
            luna_caller=caller,
        )
        self.assertIn("example.com", result.loc[0, "Translation"])
        self.assertEqual("validated", result.loc[0, "Validation Status"])


class ProviderAndFallbackTests(unittest.TestCase):
    def setUp(self):
        self.rows = pd.DataFrame([_ocr_row("Rnd 1: 6 sc")])
        self.segments, _ = broad_translation.build_source_segments(self.rows)
        self.valid = _response_text(
            _keyed_response(self.segments, ["第1圈：短针六针"])
        )

    def _direct(self, caller):
        return broad_translation.translate_merged_ocr_lines_broad(
            self.rows,
            "English — US",
            "Traditional Chinese",
            environ={"OPENAI_API_KEY": "test-key"},
            luna_caller=caller,
        )

    def test_malformed_first_response_retries_once_then_succeeds(self):
        caller = mock.Mock(
            side_effect=[({"output": []}, 0.01), (self.valid, 0.01)]
        )
        result = self._direct(caller)
        self.assertEqual(2, caller.call_count)
        self.assertEqual("第1圈：短针六针", result.loc[0, "Translation"])

    def test_fully_blank_response_retries_once_then_falls_back(self):
        blank = _response_text(_keyed_response(self.segments, ["  "]))
        caller = mock.Mock(return_value=(blank, 0.01))
        with self.assertRaises(broad_translation.BroadRecoverableError) as caught:
            self._direct(caller)
        self.assertEqual(2, caller.call_count)
        self.assertEqual("all_translations_blank", caught.exception.reason)

    def test_new_route_malformed_response_keeps_existing_retry_contract(self):
        rows = pd.DataFrame([_ocr_row("第1段：細編み6目")])
        caller = mock.Mock(return_value=({"output": []}, 0.01))

        with self.assertRaises(broad_translation.BroadRecoverableError) as caught:
            broad_translation.translate_merged_ocr_lines_broad(
                rows,
                "Japanese",
                "English — UK",
                environ={"OPENAI_API_KEY": "test-key"},
                luna_caller=caller,
            )

        self.assertEqual(2, caller.call_count)
        self.assertEqual("output_text_not_found", caught.exception.reason)

    def test_nonretryable_provider_failure_is_single_call(self):
        caller = mock.Mock(side_effect=TimeoutError("timeout"))
        with self.assertRaises(broad_translation.BroadRecoverableError):
            self._direct(caller)
        caller.assert_called_once()

    def test_retryable_http_failure_keeps_two_call_ceiling(self):
        error = urllib.error.HTTPError(
            "https://api.openai.com/v1/responses",
            503,
            "transient",
            None,
            io.BytesIO(b""),
        )
        caller = mock.Mock(side_effect=[error, (self.valid, 0.01)])
        self._direct(caller)
        self.assertEqual(2, caller.call_count)

    @mock.patch.dict(
        os.environ,
        {"PATTERN_BROAD_TRANSLATION_ENABLED": "1", "OPENAI_API_KEY": "test-key"},
        clear=False,
    )
    def test_structurally_valid_linguistic_variation_skips_all_legacy_paths(self):
        supplied_legacy_provider = mock.Mock(
            side_effect=AssertionError("legacy LLM provider")
        )
        with mock.patch.object(
            broad_translation,
            "call_luna_once",
            return_value=(self.valid, 0.01),
        ) as provider, mock.patch.object(
            line_translation,
            "translate_ocr_line",
            side_effect=AssertionError("legacy deterministic path"),
        ) as deterministic:
            result = ocr_lines.build_ocr_line_translations(
                self.rows,
                {},
                pd.DataFrame(),
                "Traditional Chinese",
                "English — US",
                llm_provider=supplied_legacy_provider,
            )
        provider.assert_called_once()
        deterministic.assert_not_called()
        supplied_legacy_provider.assert_not_called()
        self.assertEqual("validated", result.loc[0, "Validation Status"])

    @mock.patch.dict(
        os.environ,
        {"PATTERN_BROAD_TRANSLATION_ENABLED": "1", "OPENAI_API_KEY": "test-key"},
        clear=False,
    )
    def test_malformed_response_uses_deterministic_fallback_after_two_calls(self):
        with mock.patch.object(
            broad_translation,
            "call_luna_once",
            return_value=({"output": []}, 0.01),
        ) as provider, mock.patch.object(
            line_translation,
            "translate_ocr_line",
            return_value="deterministic fallback",
        ) as deterministic:
            result = ocr_lines.build_ocr_line_translations(
                self.rows,
                {},
                pd.DataFrame(),
                "Traditional Chinese",
                "English — US",
            )
        self.assertEqual(2, provider.call_count)
        deterministic.assert_called()
        self.assertEqual(
            "deterministic fallback",
            result.loc[0, "Translation"],
        )
        self.assertEqual(
            "deterministic_legacy",
            result.attrs["broad_fallback_mode"],
        )

    @mock.patch.dict(
        os.environ,
        {"PATTERN_BROAD_TRANSLATION_ENABLED": "1", "OPENAI_API_KEY": "test-key"},
        clear=False,
    )
    def test_new_route_malformed_response_uses_deterministic_fallback(self):
        rows = pd.DataFrame([_ocr_row("第1段：細編み6目")])
        with mock.patch.object(
            broad_translation,
            "call_luna_once",
            return_value=({"output": []}, 0.01),
        ) as provider, mock.patch.object(
            line_translation,
            "translate_ocr_line",
            return_value="deterministic fallback",
        ) as deterministic:
            result = ocr_lines.build_ocr_line_translations(
                rows,
                {},
                pd.DataFrame(),
                "English — UK",
                "Japanese",
            )

        self.assertEqual(2, provider.call_count)
        deterministic.assert_called()
        self.assertEqual("deterministic fallback", result.loc[0, "Translation"])
        self.assertEqual(
            "deterministic_legacy",
            result.attrs["broad_fallback_mode"],
        )

    @mock.patch.dict(
        os.environ,
        {"PATTERN_BROAD_TRANSLATION_ENABLED": "1", "OPENAI_API_KEY": "test-key"},
        clear=False,
    )
    def test_provider_timeout_uses_deterministic_fallback_after_one_call(self):
        with mock.patch.object(
            broad_translation,
            "call_luna_once",
            side_effect=TimeoutError("timeout"),
        ) as provider, mock.patch.object(
            line_translation,
            "translate_ocr_line",
            return_value="deterministic fallback",
        ) as deterministic:
            result = ocr_lines.build_ocr_line_translations(
                self.rows,
                {},
                pd.DataFrame(),
                "Traditional Chinese",
                "English — US",
            )
        provider.assert_called_once()
        deterministic.assert_called()
        self.assertEqual(
            "deterministic_legacy",
            result.attrs["broad_fallback_mode"],
        )

    @mock.patch.dict(
        os.environ,
        {"PATTERN_BROAD_TRANSLATION_ENABLED": "1", "OPENAI_API_KEY": "test-key"},
        clear=False,
    )
    def test_emergency_legacy_reuses_original_rows_and_disables_all_providers(self):
        rows = pd.DataFrame(
            [
                _ocr_row(
                    "第1圈：",
                    min_x=0,
                    max_x=35,
                    min_y=0,
                    max_y=20,
                ),
                _ocr_row(
                    "6短针",
                    min_x=40,
                    max_x=80,
                    min_y=0,
                    max_y=20,
                ),
            ]
        )
        supplied_legacy_provider = mock.Mock(
            side_effect=AssertionError("legacy provider")
        )
        real_merge = ocr_lines.merge_ocr_boxes_into_visual_lines
        merge_calls = []

        def merge_wrapper(candidate_rows, **kwargs):
            merge_calls.append((candidate_rows is rows, dict(kwargs)))
            return real_merge(candidate_rows, **kwargs)

        with mock.patch.object(
            broad_translation,
            "call_luna_once",
            return_value=({"output": []}, 0.01),
        ) as broad_provider, mock.patch.object(
            ocr_lines,
            "merge_ocr_boxes_into_visual_lines",
            side_effect=merge_wrapper,
        ), mock.patch.object(
            shadow_title_classifier,
            "resolve_title_route_indices",
            side_effect=AssertionError("title provider path"),
        ) as title_route:
            result = ocr_lines.build_ocr_line_translations(
                rows,
                {},
                pd.DataFrame(),
                "English — US",
                "Simplified Chinese",
                llm_provider=supplied_legacy_provider,
            )

        self.assertEqual(2, broad_provider.call_count)
        supplied_legacy_provider.assert_not_called()
        title_route.assert_not_called()
        self.assertEqual(2, len(merge_calls))
        self.assertTrue(all(used_original for used_original, _ in merge_calls))
        self.assertFalse(
            merge_calls[0][1]["correct_chinese_legacy_layout"]
        )
        self.assertTrue(
            merge_calls[1][1]["correct_chinese_legacy_layout"]
        )
        self.assertEqual(
            "deterministic_legacy",
            result.attrs["broad_fallback_mode"],
        )


if __name__ == "__main__":
    unittest.main()
