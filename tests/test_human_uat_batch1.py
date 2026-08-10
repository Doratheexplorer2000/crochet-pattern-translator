import contextlib
import io
import os
import unittest
import urllib.error
from unittest import mock

import pandas as pd

from pattern_translator.engine import line_translation
from pattern_translator.engine import llm_fallback
from pattern_translator.engine import terminology


class DeterministicBatchOneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv("knowledge_base/data/master_stitches.csv").fillna("")
        cls.chinese_index = terminology.build_term_index(cls.df, "Traditional Chinese")
        cls.english_index = terminology.build_term_index(cls.df, "English — US")

    def translate_chinese(self, text: str) -> str:
        return line_translation.translate_ocr_line(
            text, self.chinese_index, self.df, "English — US"
        )

    def test_plain_times_are_not_rounds(self):
        for value in ("14:27", "09:30", "7:45"):
            with self.subTest(value=value):
                self.assertEqual(self.translate_chinese(value), value)

    def test_explicit_round_labels_remain_supported(self):
        expected = "R14: 27 sc"
        for value in ("R14: 27 sc", "Rnd 14: 27 sc", "Round 14: 27 sc"):
            with self.subTest(value=value):
                self.assertEqual(self.translate_chinese(value), expected)

    def test_cjk_adjacent_counted_tokens(self):
        self.assertEqual(self.translate_chinese("24x留線"), "24 sc leave a yarn tail")
        self.assertEqual(self.translate_chinese("8A收口"), "dec x8 close opening")

    def test_counted_tokens_do_not_match_inside_latin_words(self):
        self.assertEqual(self.translate_chinese("24xylophone"), "24xylophone")
        self.assertEqual(self.translate_chinese("text24x"), "text24x")

    def test_generated_terms_have_safe_boundaries(self):
        self.assertEqual(self.translate_chinese("R3:內半針18x"), "R3: bl 18 sc")
        self.assertEqual(self.translate_chinese("內半針縫合"), "bl sew")

    def test_compact_group_shorthand(self):
        self.assertEqual(self.translate_chinese("R2:3(xv)"), "R2: (sc, inc) x3")
        self.assertEqual(self.translate_chinese("R6:3(v2x)"), "R6: (inc, 2 sc) x3")
        for value in ("R2:3(x,v)", "R2:3(x.v)", "R2:3(x v)"):
            with self.subTest(value=value):
                self.assertEqual(self.translate_chinese(value), "R2: (sc, inc) x3")
        self.assertEqual(self.translate_chinese("R2:3(xy)"), "R2: (xy) x3")

    def test_approved_terms_and_heading(self):
        expected = {
            "身体": "Body",
            "附圖解": "with diagram",
            "留線": "leave a yarn tail",
            "繡白點兒": "embroider white dots",
            "收口": "close opening",
        }
        for source, translated in expected.items():
            with self.subTest(source=source):
                self.assertEqual(self.translate_chinese(source), translated)
        self.assertEqual(
            line_translation.translate_ocr_line(
                "Stuffing", self.english_index, self.df, "Traditional Chinese"
            ),
            "塞入棉花",
        )


class LlmDebugOutcomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv("knowledge_base/data/master_stitches.csv").fillna("")

    def capture(self, source, deterministic, target, provider, *, enabled=True):
        environment = {"PATTERN_LLM_DEBUG": "1"}
        if enabled:
            environment["PATTERN_LLM_FALLBACK_ENABLED"] = "1"
        output = io.StringIO()
        with mock.patch.dict(os.environ, environment, clear=True):
            with contextlib.redirect_stderr(output):
                result = llm_fallback.apply_llm_fallback(
                    source, deterministic, "previous", "next", target, self.df, provider
                )
        return result, output.getvalue().strip()

    def test_debug_outcome_categories_are_compact_and_content_free(self):
        def timeout(*_args):
            raise TimeoutError()

        def api_error(*_args):
            raise urllib.error.URLError("private response detail")

        cases = [
            ("not_eligible", "text", "text", "Japanese", mock.Mock()),
            ("skipped_resolved", "6X", "6 sc", "English — US", mock.Mock()),
            (
                "skipped_designer_shorthand",
                "R14:不加减交叉x",
                "R14: cross X all around (not yet confirmed)",
                "English — US",
                mock.Mock(),
            ),
            ("no_api_key", "剪出两只眼睛", "剪出两只眼睛", "English — US", None),
            (
                "called_accepted",
                "剪出两只眼睛",
                "剪出两只眼睛",
                "English — US",
                lambda _p, current, _n, _t: "Cut out two eyes " + " ".join(llm_fallback._PLACEHOLDER_RE.findall(current)),
            ),
            ("called_no_improvement", "剪出两只眼睛", "剪出两只眼睛", "English — US", lambda _p, current, _n, _t: current),
            ("validation_rejected", "眼睛在11-12行之间", "眼睛在11-12行之间", "English — US", lambda *_args: "Eyes between rows"),
            ("timeout", "剪出两只眼睛", "剪出两只眼睛", "English — US", timeout),
            ("api_error", "剪出两只眼睛", "剪出两只眼睛", "English — US", api_error),
            ("malformed_response", "剪出两只眼睛", "剪出两只眼睛", "English — US", lambda *_args: ""),
        ]
        for outcome, source, deterministic, target, provider in cases:
            with self.subTest(outcome=outcome):
                _result, debug = self.capture(source, deterministic, target, provider)
                self.assertEqual(debug, f"[pattern_llm] outcome={outcome}")
                self.assertNotIn(source, debug)
                self.assertNotIn("private response detail", debug)

    def test_debug_flag_off_produces_no_output(self):
        with mock.patch.dict(os.environ, {"PATTERN_LLM_FALLBACK_ENABLED": "1"}, clear=True):
            output = io.StringIO()
            with contextlib.redirect_stderr(output):
                llm_fallback.apply_llm_fallback(
                    "剪出两只眼睛", "剪出两只眼睛", "", "", "English — US", self.df, None
                )
        self.assertEqual(output.getvalue(), "")

    def test_incomplete_response_logs_structure_without_content(self):
        response = {
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [
                {
                    "type": "reasoning",
                    "content": [{"type": "summary_text", "text": "private model content"}],
                }
            ],
        }
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"PATTERN_LLM_DEBUG": "1"}, clear=True):
            with contextlib.redirect_stderr(output):
                self.assertEqual(llm_fallback._extract_output_text(response), "")
        debug = output.getvalue()
        self.assertIn("response_status=incomplete", debug)
        self.assertIn("incomplete_reason=max_output_tokens", debug)
        self.assertIn("output_item_types=reasoning", debug)
        self.assertIn("content_types=summary_text", debug)
        self.assertIn("output_text_present=false", debug)
        self.assertNotIn("private model content", debug)

    def test_empty_output_text_is_distinguished_from_missing_output_text(self):
        response = {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": ""}],
                }
            ],
        }
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"PATTERN_LLM_DEBUG": "1"}, clear=True):
            with contextlib.redirect_stderr(output):
                self.assertEqual(llm_fallback._extract_output_text(response), "")
        debug = output.getvalue()
        self.assertIn("output_text_present=true", debug)
        self.assertIn("output_text_nonempty=false", debug)

    def test_response_structure_debug_is_silent_by_default(self):
        response = {
            "status": "incomplete",
            "incomplete_details": {"reason": "private reason"},
            "output": [],
        }
        output = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True):
            with contextlib.redirect_stderr(output):
                self.assertEqual(llm_fallback._extract_output_text(response), "")
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
