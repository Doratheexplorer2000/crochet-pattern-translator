import os
import unittest
import urllib.error
from unittest import mock

import pandas as pd

from pattern_translator.engine import llm_fallback
from pattern_translator.engine import ocr_lines
from pattern_translator.engine import terminology


class LlmFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv("knowledge_base/data/master_stitches.csv")

    def apply(self, source, deterministic, target, provider):
        return llm_fallback.apply_llm_fallback(
            source, deterministic, "previous", "next", target, self.df, provider
        )

    def test_unresolved_chinese_prose_to_english(self):
        def provider(_previous, current, _following, _target):
            return "Eyes between rows " + " ".join(llm_fallback._PLACEHOLDER_RE.findall(current))

        result = self.apply("眼睛在11-12行之间", "眼睛在11-12行之间", "English — US", provider)
        self.assertIn("11-12", result)
        self.assertNotEqual(result, "眼睛在11-12行之间")

    def test_unresolved_english_prose_to_chinese(self):
        result = self.apply(
            "we will not fill the body",
            "we will not fill the body",
            "Simplified Chinese",
            lambda *_args: "我们不会填充身体",
        )
        self.assertEqual(result, "我们不会填充身体")

    def test_mixed_prose_preserves_terms_and_counts(self):
        deterministic = "中长针2针 with the one paw (24)"

        def provider(_previous, current, _following, _target):
            return current.replace("中长针", "长针").replace("with the one paw", "与一只爪子一起钩")

        result = self.apply("2hdc with the one paw (24)", deterministic, "Simplified Chinese", provider)
        self.assertEqual(result, "中长针2针 与一只爪子一起钩 (24)")

    def test_correct_deterministic_line_does_not_call_provider(self):
        provider = mock.Mock(return_value="wrong")
        deterministic = "Chain 21, Start in the 2nd chain from hook, 19 sc, 3 sc in same stitch"
        result = self.apply("起21个辫子针倒2回钩19X,W", deterministic, "English — US", provider)
        self.assertEqual(result, deterministic)
        provider.assert_not_called()

    def test_us_uk_line_does_not_call_provider(self):
        provider = mock.Mock(return_value="wrong")
        self.assertEqual(self.apply("2SC", "2 dc", "English — UK", provider), "2 dc")
        provider.assert_not_called()

    def test_designer_shorthand_does_not_call_provider(self):
        provider = mock.Mock(return_value="invented")
        deterministic = "R14: cross X all around (not yet confirmed)"
        self.assertEqual(self.apply("R14:不加减交叉x", deterministic, "English — US", provider), deterministic)
        provider.assert_not_called()

    def test_ocr_noisy_number_is_preserved(self):
        deterministic = "中长针720针 with the one paw (48)"

        def provider(_previous, current, _following, _target):
            return current.replace("with the one paw", "与一只爪子一起钩")

        result = self.apply("720hdc with the one paw (48)", deterministic, "Simplified Chinese", provider)
        self.assertIn("720", result)
        self.assertIn("48", result)

    def test_timeout_falls_back(self):
        def provider(*_args):
            raise TimeoutError()

        self.assertEqual(self.apply("剪出两只眼睛", "剪出两只眼睛", "English — US", provider), "剪出两只眼睛")

    def test_api_error_falls_back(self):
        def provider(*_args):
            raise urllib.error.URLError("offline")

        self.assertEqual(self.apply("剪出两只眼睛", "剪出两只眼睛", "English — US", provider), "剪出两只眼睛")

    def test_missing_placeholder_falls_back(self):
        deterministic = "眼睛在11-12行之间"
        self.assertEqual(self.apply(deterministic, deterministic, "English — US", lambda *_args: "Eyes between rows"), deterministic)

    def test_missing_key_disables_provider(self):
        with mock.patch.dict(os.environ, {"PATTERN_LLM_FALLBACK_ENABLED": "1"}, clear=True):
            self.assertIsNone(llm_fallback.get_openai_provider_from_env())

    def test_false_feature_flag_values_disable_provider(self):
        for value in ("", "0", "false", "off"):
            with self.subTest(value=value):
                environment = {"PATTERN_LLM_FALLBACK_ENABLED": value, "OPENAI_API_KEY": "unused"}
                self.assertIsNone(llm_fallback.get_openai_provider_from_env(environment))

    def test_ocr_lines_default_remains_deterministic(self):
        rows = pd.DataFrame([
            {"text": "起21个辫子针倒2回钩19X,W", "confidence": 0.95, "min_x": 0, "max_x": 200, "min_y": 0, "max_y": 20},
            {"text": "眼睛在11-12行之间", "confidence": 0.94, "min_x": 0, "max_x": 200, "min_y": 40, "max_y": 60},
        ])
        index = terminology.build_term_index(self.df, "Simplified Chinese")
        result = ocr_lines.build_ocr_line_translations(rows, index, self.df, "English — US")
        self.assertEqual(
            result["Translation"].tolist(),
            [
                "Chain 21, Start in the 2nd chain from hook, 19 sc, 3 sc in same stitch",
                "眼睛在11-12行之间",
            ],
        )


if __name__ == "__main__":
    unittest.main()
