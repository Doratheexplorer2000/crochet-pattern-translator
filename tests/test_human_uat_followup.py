import contextlib
import io
import os
import unittest
from unittest import mock

import pandas as pd

from pattern_translator.engine import line_translation
from pattern_translator.engine import llm_fallback
from pattern_translator.engine import ocr_lines
from pattern_translator.engine import terminology


class HumanUatDeterministicFollowupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv("knowledge_base/data/master_stitches.csv").fillna("")
        cls.chinese_index = terminology.build_term_index(cls.df, "Simplified Chinese")
        cls.english_index = terminology.build_term_index(cls.df, "English — US")

    def test_second_round_in_one_visual_line_is_translated(self):
        source = "R9:x,A,3x结束留长线 R16:x,A,55x"
        self.assertEqual(
            line_translation.translate_ocr_line(
                source, self.chinese_index, self.df, "English — US"
            ),
            "R9: sc, dec, 3 sc 结束留长线 R16: sc, dec, 55 sc",
        )

    def test_unknown_designer_name_remains_conservative(self):
        self.assertEqual(
            line_translation.translate_ocr_line(
                "UnknownDesigner pattern", self.english_index, self.df, "Traditional Chinese"
            ),
            "UnknownDesigner 花樣",
        )


class HumanUatLlmDiagnosisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv("knowledge_base/data/master_stitches.csv").fillna("")
        cls.english_index = terminology.build_term_index(cls.df, "English — US")

    def run_with_debug(self, source, deterministic, provider):
        output = io.StringIO()
        environment = {
            "PATTERN_LLM_FALLBACK_ENABLED": "1",
            "PATTERN_LLM_DEBUG": "1",
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            with contextlib.redirect_stderr(output):
                result = llm_fallback.apply_llm_fallback(
                    source,
                    deterministic,
                    "",
                    "",
                    "Traditional Chinese",
                    self.df,
                    provider,
                )
        return result, output.getvalue().strip()

    def test_both_unresolved_lines_are_eligible_and_call_provider(self):
        cases = (
            ("(Dark brown yarn)", "(Dark brown yarn)"),
            (
                "1 of 4 leaves 25-30cm long yarns, others leave short yarns",
                "1 of 4 leaves 25-30cm long yarns，others leave short yarns",
            ),
        )
        for source, deterministic in cases:
            with self.subTest(source=source):
                self.assertTrue(
                    llm_fallback.should_use_llm(source, deterministic, "Traditional Chinese")
                )
                provider = mock.Mock(side_effect=lambda _p, current, _n, _t: current)
                result, debug = self.run_with_debug(source, deterministic, provider)
                provider.assert_called_once()
                self.assertEqual(result, deterministic)
                self.assertEqual(debug, "[pattern_llm] outcome=called_no_improvement")

    def test_outer_parenthesized_prose_is_unwrapped_then_rewrapped(self):
        cases = (
            ("(Dark brown yarn)", "（Dark brown yarn）", "深棕色毛線", "（深棕色毛線）"),
            ("Dark brown yarn", "Dark brown yarn", "深棕色毛線", "深棕色毛線"),
            ("(brown yarn)", "（brown yarn）", "棕色毛線", "（棕色毛線）"),
            ("brown yarn", "brown yarn", "棕色毛線", "棕色毛線"),
        )
        for source, deterministic, provider_result, expected in cases:
            with self.subTest(source=source):
                provider = mock.Mock(return_value=provider_result)
                result, debug = self.run_with_debug(source, deterministic, provider)
                provider.assert_called_once()
                current = provider.call_args.args[1]
                self.assertFalse(llm_fallback._PLACEHOLDER_RE.search(current))
                self.assertEqual(current, deterministic.strip("（）"))
                self.assertEqual(result, expected)
                self.assertEqual(debug, "[pattern_llm] outcome=called_accepted")

    def test_inner_parentheses_are_not_removed(self):
        value = "prefix (ordinary prose) suffix"
        self.assertEqual(llm_fallback._unwrap_outer_parentheses(value), (value, None))

    def test_four_variants_reach_the_normal_ocr_line_output(self):
        cases = (
            ("(Dark brown yarn)", "深棕色毛線", "（深棕色毛線）"),
            ("Dark brown yarn", "深棕色毛線", "深棕色毛線"),
            ("(brown yarn)", "棕色毛線", "（棕色毛線）"),
            ("brown yarn", "棕色毛線", "棕色毛線"),
        )
        for source, provider_result, expected in cases:
            with self.subTest(source=source):
                rows = pd.DataFrame([{
                    "text": source,
                    "confidence": 0.99,
                    "min_x": 0,
                    "max_x": 180,
                    "min_y": 0,
                    "max_y": 20,
                }])
                provider = mock.Mock(return_value=provider_result)
                result = ocr_lines.build_ocr_line_translations(
                    rows,
                    self.english_index,
                    self.df,
                    "Traditional Chinese",
                    llm_provider=provider,
                )
                self.assertEqual(result.loc[0, "Translation"], expected)
                self.assertEqual(result.loc[0, "Changed"], "✓")
                provider.assert_called_once()

    def test_long_yarn_line_accepts_preserved_order_but_rejects_natural_reordering(self):
        source = "1 of 4 leaves 25-30cm long yarns, others leave short yarns"
        deterministic = "1 of 4 leaves 25-30cm long yarns，others leave short yarns"

        def preserved_order(_previous, current, _following, _target):
            placeholders = llm_fallback._PLACEHOLDER_RE.findall(current)
            return f"{placeholders[0]} / {placeholders[1]} 留 {placeholders[2]} 厘米長線，其餘留短線"

        accepted, accepted_debug = self.run_with_debug(source, deterministic, preserved_order)
        self.assertEqual(accepted, "1 / 4 留 25-30 厘米長線，其餘留短線")
        self.assertEqual(accepted_debug, "[pattern_llm] outcome=called_accepted")

        def natural_reordering(_previous, current, _following, _target):
            placeholders = llm_fallback._PLACEHOLDER_RE.findall(current)
            return f"{placeholders[1]} 片中有 {placeholders[0]} 片留 {placeholders[2]} 厘米長線，其餘留短線"

        rejected, rejected_debug = self.run_with_debug(source, deterministic, natural_reordering)
        self.assertEqual(rejected, deterministic)
        self.assertEqual(rejected_debug, "[pattern_llm] outcome=validation_rejected")

    def test_validation_has_no_target_language_completeness_rule(self):
        deterministic = "(Dark brown yarn)"
        protected, replacements = llm_fallback.protect_authoritative_content(
            deterministic, self.df, "Traditional Chinese"
        )
        self.assertEqual(
            llm_fallback._restore_if_valid(protected, protected, deterministic, replacements),
            deterministic,
        )


if __name__ == "__main__":
    unittest.main()
