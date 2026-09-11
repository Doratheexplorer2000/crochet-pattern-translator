import json
import os
import re
import unittest
from unittest import mock

import pandas as pd

from pattern_translator.engine import broad_translation
from pattern_translator.engine import line_translation
from pattern_translator.engine import llm_fallback
from pattern_translator.engine import ocr_lines
from pattern_translator.engine import pattern_document
from pattern_translator.engine import terminology


def _ocr_row(text: str, y: float = 0.0) -> dict:
    return {
        "text": text,
        "semantic_text": text,
        "confidence": 0.98,
        "x": 10.0,
        "y": y,
        "min_x": 10.0,
        "max_x": 410.0,
        "min_y": y,
        "max_y": y + 24.0,
    }


def _response(segments: list[dict[str, str]], translations: list[str]) -> dict:
    assignments = {}
    units = {}
    for index, (segment, translation) in enumerate(zip(segments, translations)):
        unit_id = f"unit-{index:04d}"
        assignments[segment["source_segment_id"]] = unit_id
        units[unit_id] = {"translated_text": translation}
    payload = {"segment_assignments": assignments, "semantic_units": units}
    return {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": json.dumps(payload)}
                ]
            }
        ]
    }


class CrossLanguageBroadRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv("knowledge_base/data/master_stitches.csv").fillna("")
        cls.english_index = terminology.build_term_index(cls.df, "English — US")
        cls.traditional_index = terminology.build_term_index(
            cls.df,
            "Traditional Chinese",
        )

    def _translate_once(
        self,
        source_mode: str,
        output_mode: str,
        sources: list[str],
        translations: list[str],
    ) -> tuple[pd.DataFrame, mock.Mock, list[str]]:
        rows = pd.DataFrame(
            [_ocr_row(source, index * 30.0) for index, source in enumerate(sources)]
        )
        segments, _rows = broad_translation.build_source_segments(rows)
        prompts: list[str] = []

        def call(prompt: str, api_key: str):
            self.assertEqual("test-key", api_key)
            prompts.append(prompt)
            return _response(segments, translations), 0.01

        caller = mock.Mock(side_effect=call)
        result = broad_translation.translate_merged_ocr_lines_broad(
            rows,
            source_mode,
            output_mode,
            environ={"OPENAI_API_KEY": "test-key"},
            luna_caller=caller,
        )
        return result, caller, prompts

    def test_english_us_to_japanese_is_one_broad_semantic_request(self):
        sources = [
            "FLOWER PATTERN",
            "R1: 6 sc in magic ring (6)",
            "R6: CC to white, BOB, CC to dark gray (2)",
            "Insert the safety eyes, then optionally sew on the nose.",
        ]
        translations = [
            "花のパターン",
            "R1: 輪の作り目に細編み6目 (6)",
            "R6: 色を替える 白、BOB、色を替える 濃い灰色 (2)",
            "差し目を取り付け、必要に応じて鼻を縫い付ける。",
        ]
        result, caller, prompts = self._translate_once(
            "English — US",
            "Japanese",
            sources,
            translations,
        )
        self.assertEqual(translations, result["Translation"].tolist())
        caller.assert_called_once()
        self.assertIn("into natural Japanese crochet instructions", prompts[0])
        self.assertIn('"japanese":"輪の作り目"', prompts[0])

    def test_japanese_glossary_contains_minimum_route_integrity_terms(self):
        terms = broad_translation.build_glossary("English — US", "Japanese")
        by_id = {term["concept_id"]: term for term in terms}
        expected = {
            "st_028_magic_ring": "輪の作り目",
            "st_036_round": "段",
            "st_093_rounds": "段",
            "st_078_pattern": "パターン",
            "st_086_stitch": "目",
            "st_098_change_ color": "色を替える",
            "st_100_join_with_sl_st": "引き抜き編みでつなぐ",
            "st_102_attach": "取り付ける",
            "st_103_sew": "縫い付ける",
        }
        self.assertEqual(
            expected,
            {concept_id: by_id[concept_id]["japanese"] for concept_id in expected},
        )

    def test_japanese_residual_english_prose_is_rejected(self):
        config = broad_translation._route_config("English — US", "Japanese")
        for source, translation in (
            ("Attach to the white section", "取り付ける to white"),
            (
                "Insert the safety eyes, then optionally sew on the nose.",
                "Insert the safety eyes, then optionally sew on the nose.",
            ),
        ):
            with self.subTest(translation=translation):
                with self.assertRaises(
                    broad_translation._ObjectiveValidationError
                ) as caught:
                    broad_translation.validate_semantic_units(
                        [
                            {
                                "source_segment_ids": ["segment-0000"],
                                "translation": translation,
                            }
                        ],
                        [
                            {
                                "source_segment_id": "segment-0000",
                                "text": source,
                            }
                        ],
                        config,
                    )
                self.assertEqual("residual_source_language", caught.exception.failed_rule)

    def test_japanese_residual_check_allows_handle_url_and_technical_tokens(self):
        source = "Designer @crochet_fosi https://example.com R1: 6 sc (6)"
        translation = "作者 @crochet_fosi https://example.com R1: 6 sc (6)"
        broad_translation.validate_semantic_units(
            [
                {
                    "source_segment_ids": ["segment-0000"],
                    "translation": translation,
                }
            ],
            [{"source_segment_id": "segment-0000", "text": source}],
            broad_translation._route_config("English — US", "Japanese"),
        )

    def test_traditional_chinese_to_us_and_uk_keep_distinct_stitch_terms(self):
        cases = (
            ("English — US", "R1: 6 sc (6)"),
            ("English — UK", "R1: 6 dc (6)"),
        )
        for output_mode, translation in cases:
            with self.subTest(output_mode=output_mode):
                result, caller, prompts = self._translate_once(
                    "Traditional Chinese",
                    output_mode,
                    ["R1：6短針 (6)"],
                    [translation],
                )
                self.assertEqual(translation, result.loc[0, "Translation"])
                caller.assert_called_once()
                expected_field = "english_us" if output_mode.endswith("US") else "english_uk"
                rejected_field = "english_uk" if output_mode.endswith("US") else "english_us"
                self.assertIn(f'"{expected_field}"', prompts[0])
                self.assertNotIn(f'"{rejected_field}"', prompts[0])

    def test_us_uk_stitch_leakage_is_rejected(self):
        for output_mode, wrong in (
            ("English — US", "R1: 6 dc (6)"),
            ("English — UK", "R1: 6 sc (6)"),
        ):
            with self.subTest(output_mode=output_mode):
                with self.assertRaises(broad_translation.BroadTranslationError):
                    broad_translation.validate_semantic_units(
                        [
                            {
                                "source_segment_ids": ["segment-0000"],
                                "translation": wrong,
                            }
                        ],
                        [
                            {
                                "source_segment_id": "segment-0000",
                                "text": "R1：6短針 (6)",
                            }
                        ],
                        broad_translation._route_config(
                            "Traditional Chinese",
                            output_mode,
                        ),
                    )

    @mock.patch.dict(
        os.environ,
        {"PATTERN_BROAD_TRANSLATION_ENABLED": "1", "OPENAI_API_KEY": "test-key"},
        clear=False,
    )
    def test_traditional_chinese_broad_success_avoids_legacy_row_fanout(self):
        rows = pd.DataFrame([_ocr_row("第1圈：6短針"), _ocr_row("第2圈：6加針", 30)])
        broad_result = pd.DataFrame(
            {
                "Original": ["第1圈：6短針", "第2圈：6加針"],
                "Translation": ["R1: 6 sc", "R2: 6 inc"],
            }
        )
        with mock.patch.object(
            broad_translation,
            "translate_merged_ocr_lines_broad",
            return_value=broad_result,
        ) as broad_call, mock.patch.object(
            line_translation,
            "translate_ocr_line",
            side_effect=AssertionError("Legacy row fan-out executed"),
        ) as legacy_call:
            result = ocr_lines.build_ocr_line_translations(
                rows,
                self.traditional_index,
                self.df,
                "English — US",
                "Traditional Chinese",
            )
        broad_call.assert_called_once()
        legacy_call.assert_not_called()
        self.assertEqual(["R1: 6 sc", "R2: 6 inc"], result["Translation"].tolist())

    def test_simplified_chinese_to_english_us_route_is_unchanged(self):
        self.assertTrue(
            broad_translation.is_broad_translation_route(
                "Simplified Chinese",
                "English — US",
            )
        )


class UrlDomainProtectionTests(unittest.TestCase):
    def test_bare_domain_and_full_url_are_atomic_during_expression_split(self):
        for identity in (
            "underthefloweringtree.blogspot.com",
            "https://underthefloweringtree.blogspot.com/pattern?id=1",
        ):
            with self.subTest(identity=identity):
                self.assertEqual([identity], line_translation.split_expression_parts(identity))

    def test_full_url_is_exact_through_ocr_line_cleanup(self):
        source = "https://example.com/pattern?a=1;b=2"
        self.assertEqual(source, line_translation.clean_single_ocr_line(source))

    def test_deterministic_mixed_line_preserves_domain_exactly(self):
        df = pd.read_csv("knowledge_base/data/master_stitches.csv").fillna("")
        index = terminology.build_term_index(df, "Traditional Chinese")
        source = "花树下手作:underthefloweringtree.blogspot.com"
        translated = line_translation.translate_ocr_line(
            source,
            index,
            df,
            "English — US",
        )
        self.assertIn("underthefloweringtree.blogspot.com", translated)
        self.assertNotIn("blogspot, com", translated)

    def test_broad_mixed_line_translates_text_and_restores_domain(self):
        for identity in (
            "underthefloweringtree.blogspot.com",
            "https://underthefloweringtree.blogspot.com/pattern?id=1",
        ):
            with self.subTest(identity=identity):
                source = f"花树下手作:{identity}"
                rows = pd.DataFrame([_ocr_row(source)])
                prompts: list[str] = []

                def call(prompt: str, api_key: str):
                    self.assertEqual("test-key", api_key)
                    prompts.append(prompt)
                    placeholder = re.search(r"__ciurl[a-z]+__", prompt).group(0)
                    segments, _ = broad_translation.build_source_segments(rows)
                    translated = f"Handmade Under the Flowering Tree:{placeholder}"
                    return _response(segments, [translated]), 0.01

                result = broad_translation.translate_merged_ocr_lines_broad(
                    rows,
                    "Traditional Chinese",
                    "English — US",
                    environ={"OPENAI_API_KEY": "test-key"},
                    luna_caller=call,
                )
                self.assertEqual(
                    f"Handmade Under the Flowering Tree:{identity}",
                    result.loc[0, "Translation"],
                )
                self.assertNotIn(identity, prompts[0])

    def test_bare_domain_is_a_protected_document_identity(self):
        spans = pattern_document.protected_identity_spans(
            "花树下手作:underthefloweringtree.blogspot.com"
        )
        self.assertEqual("url_or_domain", spans[0]["kind"])
        self.assertEqual("underthefloweringtree.blogspot.com", spans[0]["text"])

    def test_legacy_url_guard_precedes_residual_cjk_branch(self):
        source = "花树下手作:underthefloweringtree.blogspot.com"
        self.assertFalse(
            llm_fallback.should_use_llm(
                source,
                source,
                "English — US",
                "Traditional Chinese",
            )
        )

    def test_legacy_authoritative_protection_round_trips_full_url(self):
        df = pd.read_csv("knowledge_base/data/master_stitches.csv").fillna("")
        source = "See https://example.com/pattern?a=1;b=2"
        protected, replacements = llm_fallback.protect_authoritative_content(
            source,
            df,
            "Traditional Chinese",
        )
        self.assertNotIn("https://example.com", protected)
        self.assertEqual(
            source,
            llm_fallback._restore_if_valid(
                protected,
                protected,
                source,
                replacements,
            ),
        )


class CompactIncreaseGlyphNormalizationTests(unittest.TestCase):
    def test_sqrt_and_logical_or_glyphs_normalize_only_in_compact_rows(self):
        cases = (
            ("R9: 10X,(X,√,X)*4,10X", "R9: 10X,(X,V,X)*4,10X"),
            ("R11: 10X,(2X,∨,2X)*4,10X", "R11: 10X,(2X,V,2X)*4,10X"),
            ("R9: 10X,(X,V,X)*4,10X", "R9: 10X,(X,V,X)*4,10X"),
            ("√16 = 4", "√16 = 4"),
            ("A ∨ B", "A ∨ B"),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(expected, line_translation.clean_single_ocr_line(source))

    def test_supplied_compact_rows_translate_normalized_v_as_increase(self):
        df = pd.read_csv("knowledge_base/data/master_stitches.csv").fillna("")
        index = terminology.build_term_index(df, "Simplified Chinese")
        for source in (
            "R9: 10X,(X,√,X)*4,10X",
            "R11: 10X,(2X,∨,2X)*4,10X",
        ):
            translated = line_translation.translate_ocr_line(
                line_translation.clean_single_ocr_line(source),
                index,
                df,
                "English — US",
            )
            with self.subTest(source=source):
                self.assertIn("inc", translated)


class BroadValidatorCorrectionTests(unittest.TestCase):
    def _failure_reason(
        self,
        source_mode: str,
        output_mode: str,
        source: str,
        translation: str,
    ) -> str:
        segments = [{"source_segment_id": "segment-0000", "text": source}]
        with self.assertRaises(broad_translation.BroadTranslationError) as caught:
            broad_translation.validate_semantic_units(
                [
                    {
                        "source_segment_ids": ["segment-0000"],
                        "translation": translation,
                    }
                ],
                segments,
                broad_translation._route_config(source_mode, output_mode),
            )
        return caught.exception.failed_rule

    def _validate(
        self,
        source_mode: str,
        output_mode: str,
        source: str,
        translation: str,
    ) -> None:
        broad_translation.validate_semantic_units(
            [
                {
                    "source_segment_ids": ["segment-0000"],
                    "translation": translation,
                }
            ],
            [{"source_segment_id": "segment-0000", "text": source}],
            broad_translation._route_config(source_mode, output_mode),
        )

    def _translate_mocked(
        self,
        source_mode: str,
        output_mode: str,
        sources: list[str],
        translations: list[str],
    ) -> pd.DataFrame:
        rows = pd.DataFrame(
            [_ocr_row(source, index * 30.0) for index, source in enumerate(sources)]
        )
        segments, _ = broad_translation.build_source_segments(rows)
        caller = mock.Mock(
            return_value=(_response(segments, translations), 0.01)
        )
        result = broad_translation.translate_merged_ocr_lines_broad(
            rows,
            source_mode,
            output_mode,
            environ={"OPENAI_API_KEY": "test-key"},
            luna_caller=caller,
        )
        caller.assert_called_once()
        return result

    def test_japanese_penguin_color_operations_pass_through_mocked_provider(self):
        sources = [
            "R6: 11sc, *CC to white* BOB, *CC to dark gray* 3sc, "
            "*CC to white* BOB, *CC to dark gray* 8sc (24)",
            "9. *CC to blue* 24sc (24)",
            "10. *CC to purple* 24sc (24)",
        ]
        translations = [
            "R6: 細編み11目、*白に色替え* 玉編み、*濃いグレーに色替え* "
            "細編み3目、*白色に替える* 玉編み、*濃い灰色に替える* 細編み8目 (24)",
            "9. *青に替える* 細編み24目 (24)",
            "10. *紫に替える* 細編み24目 (24)",
        ]
        result = self._translate_mocked(
            "English — US", "Japanese", sources, translations
        )
        self.assertEqual(translations, result["Translation"].tolist())
        self.assertEqual(["validated"] * 3, result["Validation Status"].tolist())

    def test_exact_real_japanese_color_candidates_pass(self):
        cases = (
            (
                "R6: 11 sc, *CC to white* BOB, *CC to dark gray* 3sc,\n"
                "*CC to white* BOB, *CC to dark gray* 8 sc (24)",
                "R6：細編み11目、＊白に配色変更＊ 玉編み、\n"
                "＊濃いグレーに配色変更＊細編み3目、\n"
                "＊白に配色変更＊玉編み、\n"
                "＊濃いグレーに配色変更＊細編み8目（24）",
                ["white", "dark_gray", "white", "dark_gray"],
            ),
            (
                "9. *CC to blue* 24 sc (24)",
                "9. ＊青に配色変更＊細編み24目（24）",
                ["blue"],
            ),
            (
                "10. *CC to purple* 24 sc (24)",
                "10. ＊紫に配色変更＊細編み24目（24）",
                ["purple"],
            ),
        )
        for source, translation, operations in cases:
            with self.subTest(source=source):
                self.assertEqual(
                    operations,
                    broad_translation._japanese_color_change_operations(translation),
                )
                self._validate("English — US", "Japanese", source, translation)

    def test_japanese_color_operations_reject_drop_wrong_extra_and_reorder(self):
        source = "R6: CC to white, CC to dark gray, CC to white, CC to dark gray"
        invalid = (
            "R6: 白に色替え、濃いグレーに色替え、白に色替え",
            "R6: 白に色替え、青に替える、白に色替え、濃いグレーに色替え",
            "R6: 白に色替え、濃いグレーに色替え、白に色替え、"
            "濃いグレーに色替え、紫に替える",
            "R6: 濃いグレーに色替え、白に色替え、白に色替え、濃いグレーに色替え",
        )
        for translation in invalid:
            with self.subTest(translation=translation):
                self.assertEqual(
                    "color_change_count",
                    self._failure_reason(
                        "English — US", "Japanese", source, translation
                    ),
                )

    def test_real_japanese_color_grammar_still_rejects_semantic_changes(self):
        source = "R6: CC to white, CC to dark gray, CC to white, CC to dark gray"
        invalid = (
            "R6: 白に配色変更、濃いグレーに配色変更、白に配色変更",
            "R6: 白に配色変更、青に配色変更、白に配色変更、濃いグレーに配色変更",
            "R6: 濃いグレーに配色変更、白に配色変更、白に配色変更、濃いグレーに配色変更",
            "R6: CC to white, CC to dark gray, CC to white, CC to dark gray",
        )
        for translation in invalid:
            with self.subTest(translation=translation):
                self.assertEqual(
                    "color_change_count",
                    self._failure_reason(
                        "English — US", "Japanese", source, translation
                    ),
                )

    def test_japanese_one_to_ten_count_words_accept_matching_crochet_digits(self):
        units = ("段", "目", "回", "個")
        for word, digit in broad_translation.ENGLISH_CARDINAL_WORD_TO_DIGIT.items():
            for unit in units:
                with self.subTest(word=word, digit=digit, unit=unit):
                    self._validate(
                        "English — US",
                        "Japanese",
                        f"Move {word} row down",
                        f"{digit}{unit}下に移動する",
                    )
        self._validate(
            "English — US",
            "Japanese",
            "Move one row down",
            "一段下に移動する",
        )

    def test_japanese_count_equivalence_rejects_wrong_invented_or_lost_digits(self):
        cases = (
            ("Move one row down", "2段下に移動する"),
            ("Move one row down", "1段下、2目横に移動する"),
            ("Move 1 row down", "一段下に移動する"),
        )
        for source, translation in cases:
            with self.subTest(source=source, translation=translation):
                self.assertEqual(
                    "arabic_digit_multiset",
                    self._failure_reason(
                        "English — US", "Japanese", source, translation
                    ),
                )

    def test_japanese_protected_handle_requires_surrounding_prose_translation(self):
        source = "@crochetby_fosi all rights reserved"
        for translation in (
            "@crochetby_fosi 無断転載禁止",
            "@crochetby_fosi すべての権利を保有",
        ):
            with self.subTest(translation=translation):
                self._validate("English — US", "Japanese", source, translation)
        self.assertEqual(
            "residual_source_language",
            self._failure_reason("English — US", "Japanese", source, source),
        )

    def test_japanese_protected_domain_requires_surrounding_prose_translation(self):
        source = "crochetby-fosi.example all rights reserved"
        self._validate(
            "English — US",
            "Japanese",
            source,
            "crochetby-fosi.example すべての権利を保有",
        )
        self.assertEqual(
            "residual_source_language",
            self._failure_reason("English — US", "Japanese", source, source),
        )

    def test_prompt_requires_translation_around_protected_identities(self):
        config = broad_translation._route_config("English — US", "Japanese")
        prompt = broad_translation.build_prompt(
            [
                {
                    "source_segment_id": "segment-0000",
                    "text": "@crochetby_fosi __ciurl0000__ all rights reserved",
                }
            ],
            broad_translation.build_glossary("English — US", "Japanese"),
            config,
        )
        self.assertIn(
            "a protected identity does not exempt surrounding prose from translation",
            prompt,
        )

    def test_exact_real_flower_title_has_no_stitch_requirement(self):
        config = broad_translation._route_config(
            "Traditional Chinese", "English — US"
        )
        terms = broad_translation.build_glossary(
            config.source_mode, config.output_mode
        )
        required, present = broad_translation._strict_glossary_semantic_counts(
            "A.花", "A. Flower", config, terms
        )
        self.assertEqual({}, required)
        self.assertEqual({}, present)
        self._validate(
            "Traditional Chinese", "English — US", "A.花", "A. Flower"
        )

    def test_exact_real_flower_structured_candidates_pass(self):
        cases = (
            (
                "環狀起針,立3鎖針,14長針,引拔\n"
                "(鉤織長針時,開頭立起之3鎖針也算1針,因 共15針\n"
                "此需引拔於第三個鎖針上.以下同理.)",
                "Make a magic ring, chain 3, work 14 double crochet, and slip stitch. "
                "(When crocheting double crochet, the 3 turning chains at the beginning "
                "also count as 1 stitch, for a total of 15 stitches. "
                "Therefore, slip stitch into the third chain. The same applies below.)",
            ),
            (
                "立3鎖針,長針,14長針加針,引拔 共30針",
                "Chain 3, double crochet, 14 double crochet increases, "
                "and slip stitch. Total: 30 stitches.",
            ),
            (
                "立3鎖針,長針,29長針加針,引拔 共60針",
                "Chain 3, double crochet, 29 double crochet increases, "
                "and slip stitch. Total: 60 stitches.",
            ),
            (
                "立3鎖針,長針,59長針加針,引拔 共120針",
                "Chain 3, double crochet, 59 double crochet increases, "
                "and slip stitch. Total: 120 stitches.",
            ),
        )
        for source, translation in cases:
            with self.subTest(source=source):
                self._validate(
                    "Traditional Chinese", "English — US", source, translation
                )

    def test_real_flower_semantic_and_digit_corruptions_still_fail(self):
        invalid = (
            ("長針", "single crochet", "stitch_terminology"),
            ("長針加針", "double crochet decrease", "stitch_terminology"),
            (
                "立3鎖針,長針,14長針加針,引拔 共30針",
                "Chain 3, double crochet, 14 double crochet increases. "
                "Total: 30 stitches.",
                "stitch_terminology",
            ),
            ("長針", "double crochet, single crochet", "stitch_terminology"),
            (
                "立3鎖針,長針,14長針加針,引拔 共30針",
                "Chain 3, double crochet, 13 double crochet increases, "
                "and slip stitch. Total: 30 stitches.",
                "arabic_digit_multiset",
            ),
        )
        for source, translation, reason in invalid:
            with self.subTest(source=source, translation=translation):
                self.assertEqual(
                    reason,
                    self._failure_reason(
                        "Traditional Chinese", "English — US", source, translation
                    ),
                )

    def test_flower_structured_rows_pass_us_and_uk_mocked_providers(self):
        sources = [
            "環狀起針,立3鎖針,14長針,引拔",
            "立3鎖針,長針,14長針加針,引拔",
            "立3鎖針,長針,29長針加針,引拔",
            "立3鎖針,長針,59長針加針,引拔",
            "立1針,120(短針,3鎖針),引拔",
        ]
        outputs = {
            "English — US": [
                "magic ring, ch 3, 14 dc, sl st",
                "ch 3, dc, 14 dc inc, sl st",
                "ch 3, double crochet, 29 double crochet increase, slip stitch",
                "chain 3, dc, 59 dc inc, slip stitch",
                "ch 1, 120 (sc, ch 3), sl st",
            ],
            "English — UK": [
                "magic ring, ch 3, 14 tr, sl st",
                "ch 3, tr, 14 tr inc, sl st",
                "ch 3, treble crochet, 29 treble crochet increase, slip stitch",
                "chain 3, tr, 59 tr inc, slip stitch",
                "ch 1, 120 (dc, ch 3), sl st",
            ],
        }
        for output_mode, translations in outputs.items():
            with self.subTest(output_mode=output_mode):
                result = self._translate_mocked(
                    "Traditional Chinese", output_mode, sources, translations
                )
                self.assertEqual(translations, result["Translation"].tolist())
                self.assertEqual(
                    ["validated"] * len(sources),
                    result["Validation Status"].tolist(),
                )

    def test_compound_stitches_are_atomic_and_invalid_semantics_still_fail(self):
        config = broad_translation._route_config(
            "Traditional Chinese", "English — US"
        )
        terms = broad_translation.build_glossary(
            config.source_mode, config.output_mode
        )
        required, present = broad_translation._strict_glossary_semantic_counts(
            "長針,長針加針",
            "dc, dc inc",
            config,
            terms,
        )
        self.assertEqual(
            {"st_005_double_crochet": 1, "st_012_double_crochet_increase": 1},
            required,
        )
        self.assertEqual(required, present)

        invalid = (
            ("長針", "sc"),
            ("長針加針", "dc decrease"),
            ("長針,短針", "dc"),
            ("長針", "dc, sc"),
        )
        for source, translation in invalid:
            with self.subTest(source=source, translation=translation):
                self.assertEqual(
                    "stitch_terminology",
                    self._failure_reason(
                        "Traditional Chinese", "English — US", source, translation
                    ),
                )
        self.assertEqual(
            "arabic_digit_multiset",
            self._failure_reason(
                "Traditional Chinese", "English — US", "14長針", "13 dc"
            ),
        )

    def test_exact_real_round_ordinal_candidate_and_equivalents_pass(self):
        source = "在第2圈上方以缩口缝方式\n一入一出縫合一圈後收緊"
        for translation in (
            "Using a drawstring stitch method above the 2nd round, "
            "sew in and out around one round, then tighten.",
            "Using a drawstring stitch method above round 2, "
            "sew in and out around one round, then tighten.",
            "Using a drawstring stitch method above the second round, "
            "sew in and out around one round, then tighten.",
        ):
            with self.subTest(translation=translation):
                self._validate(
                    "Traditional Chinese", "English — US", source, translation
                )
        for translation in (
            "Using a drawstring stitch method above the third round, "
            "sew in and out around one round, then tighten.",
            "Using a drawstring stitch method above round 3, "
            "sew in and out around one round, then tighten.",
        ):
            with self.subTest(translation=translation):
                self.assertIn(
                    self._failure_reason(
                        "Traditional Chinese", "English — US", source, translation
                    ),
                    {"arabic_digit_multiset", "round_identity"},
                )

    def test_english_round_and_row_ordinals_one_through_ten_are_bounded(self):
        for word, digit in broad_translation.ENGLISH_ORDINAL_WORD_TO_DIGIT.items():
            with self.subTest(word=word, identity="round"):
                self._validate(
                    "Traditional Chinese",
                    "English — US",
                    f"第{digit}圈",
                    f"the {word} round",
                )
            with self.subTest(word=word, identity="row"):
                self._validate(
                    "Traditional Chinese",
                    "English — US",
                    f"第{digit}行",
                    f"the {word} row",
                )
        for ordinal, digit in broad_translation.ENGLISH_ORDINAL_ID_TO_DIGIT.items():
            if not ordinal[0].isdigit():
                continue
            with self.subTest(ordinal=ordinal):
                self._validate(
                    "Traditional Chinese",
                    "English — US",
                    f"第{digit}圈",
                    f"the {ordinal} round",
                )
        self.assertEqual(
            "arabic_digit_multiset",
            self._failure_reason(
                "Traditional Chinese", "English — US", "14長針", "fourteen dc"
            ),
        )

    def test_uk_dialect_isolation_and_explicit_digit_contract_remain_strict(self):
        self._validate(
            "Traditional Chinese",
            "English — UK",
            "在第2圈上方以缩口缝方式",
            "Use a drawstring stitch above round 2",
        )
        self._validate(
            "Traditional Chinese",
            "English — UK",
            "在第2圈上方以缩口缝方式",
            "Use a drawstring stitch above the second round",
        )
        for source, leaked in (
            ("長針", "dc"),
            ("短針", "sc"),
            ("長針加針", "dc inc"),
        ):
            with self.subTest(source=source, leaked=leaked):
                self.assertEqual(
                    "stitch_terminology",
                    self._failure_reason(
                        "Traditional Chinese", "English — UK", source, leaked
                    ),
                )


if __name__ == "__main__":
    unittest.main()
