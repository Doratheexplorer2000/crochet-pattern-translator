import io
import json
import os
import unittest
import urllib.error
from unittest import mock

import pandas as pd

from pattern_translator.engine import llm_fallback
from pattern_translator.engine import line_translation
from pattern_translator.engine import ocr_lines
from pattern_translator.engine import pattern_document
from pattern_translator.engine import terminology


class LlmFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv("knowledge_base/data/master_stitches.csv")
        cls.english_index = terminology.build_term_index(cls.df, "English — US")

    def apply(self, source, deterministic, target, provider, *, title_context=False):
        return llm_fallback.apply_llm_fallback(
            source,
            deterministic,
            "previous",
            "next",
            target,
            self.df,
            provider,
            title_context=title_context,
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

    def test_context_backed_single_unresolved_word_calls_provider(self):
        deterministic = line_translation.translate_ocr_line(
            "Capybara pattern",
            self.english_index,
            self.df,
            "Traditional Chinese",
        )
        self.assertEqual(deterministic, "Capybara 花樣")
        self.assertTrue(
            llm_fallback.should_use_llm(
                "Capybara pattern", deterministic, "Traditional Chinese"
            )
        )

        provider = mock.Mock(side_effect=lambda _p, current, _n, _t: current)
        result = self.apply(
            "Capybara pattern", deterministic, "Traditional Chinese", provider
        )
        self.assertEqual(result, deterministic)
        provider.assert_called_once()

    def test_context_backed_rule_is_general_for_short_labels(self):
        csv_text = " ".join(self.df.fillna("").astype(str).to_numpy().ravel()).lower()
        self.assertNotIn("otter", csv_text)
        self.assertNotIn("forest", csv_text)

        for source, expected in (
            ("Otter pattern", "Otter 花樣"),
            ("Forest stuffing", "Forest 塞入棉花"),
        ):
            with self.subTest(source=source):
                deterministic = line_translation.translate_ocr_line(
                    source,
                    self.english_index,
                    self.df,
                    "Traditional Chinese",
                )
                self.assertEqual(deterministic, expected)
                self.assertTrue(
                    llm_fallback.should_use_llm(
                        source, deterministic, "Traditional Chinese"
                    )
                )

    def test_title_prompt_translates_descriptions_but_preserves_genuine_names(self):
        captured = {}

        class FakeResponse(io.BytesIO):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        response = FakeResponse(json.dumps({
            "output": [{
                "content": [{"type": "output_text", "text": "translated __ciqa__"}]
            }]
        }).encode("utf-8"))

        def urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return response

        provider = llm_fallback.create_openai_provider("synthetic-test-key")
        with mock.patch.object(llm_fallback.urllib.request, "urlopen", side_effect=urlopen):
            result = provider(
                "previous context",
                "Capybara __ciqa__",
                "next context",
                "Traditional Chinese",
            )

        self.assertEqual(result, "translated __ciqa__")
        self.assertEqual(captured["timeout"], llm_fallback.DEFAULT_TIMEOUT_SECONDS)
        self.assertEqual(captured["payload"]["model"], "gpt-5-nano")
        self.assertEqual(captured["payload"]["reasoning"], {"effort": "minimal"})
        self.assertEqual(captured["payload"]["max_output_tokens"], 180)
        prompt = captured["payload"]["input"]
        instruction = prompt.split("\nPREVIOUS:", 1)[0]
        self.assertIn("descriptive nouns in pattern titles and headings", instruction)
        self.assertIn("Title Case alone does not make a word a proper name", instruction)
        for category in (
            "animals", "plants", "foods", "objects", "body parts", "colours", "materials"
        ):
            self.assertIn(category, instruction)
        for name_type in (
            "brand names", "designer names", "usernames", "product names",
            "contextually clear proper names",
        ):
            self.assertIn(name_type, instruction)
        self.assertIn("unknown crochet abbreviations or designer shorthand", instruction)
        self.assertIn("copy each exactly once and unchanged", instruction)
        self.assertIn("PREVIOUS and NEXT are context only", instruction)
        self.assertNotIn("Capybara", instruction)

    def test_title_provider_uses_strict_mode_b_contract(self):
        captured = {}

        class FakeResponse(io.BytesIO):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        model_result = json.dumps({
            "classification": "ordinary_descriptive_noun",
            "translated_or_preserved_text": "翻譯結果",
        })
        response = FakeResponse(json.dumps({
            "output": [{
                "content": [{"type": "output_text", "text": model_result}]
            }]
        }).encode("utf-8"))

        def urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return response

        provider = llm_fallback.create_openai_provider("synthetic-test-key")
        with mock.patch.object(llm_fallback.urllib.request, "urlopen", side_effect=urlopen):
            result = provider(
                "ignored previous",
                llm_fallback.TitleTranslationRequest("Otter"),
                "ignored following",
                "Traditional Chinese",
            )

        self.assertEqual(result, model_result)
        self.assertEqual(captured["timeout"], llm_fallback.DEFAULT_TIMEOUT_SECONDS)
        self.assertEqual(captured["payload"]["model"], "gpt-5-nano")
        self.assertEqual(captured["payload"]["reasoning"], {"effort": "minimal"})
        self.assertEqual(captured["payload"]["max_output_tokens"], 180)
        prompt = captured["payload"]["input"]
        self.assertIn("ordinary_descriptive_noun", prompt)
        self.assertIn("brand_or_proper_name", prompt)
        self.assertIn("translated_or_preserved_text", prompt)
        self.assertIn("SUBJECT: Otter", prompt)
        self.assertNotIn("PREVIOUS:", prompt)
        for forbidden in (
            "Capybara", "Penguin", "Rabbit", "Pumpkin", "Sunflower", "Jellycat"
        ):
            self.assertNotIn(forbidden, prompt)

    def test_general_title_examples_remain_provider_candidates(self):
        for source in (
            "Capybara pattern",
            "Penguin pattern",
            "Rabbit pattern",
            "Pumpkin pattern",
            "Sunflower pattern",
            "Little brown bear pattern",
            "Jellycat pattern",
            "Mabel designer pattern",
        ):
            with self.subTest(source=source):
                deterministic = line_translation.translate_ocr_line(
                    source,
                    self.english_index,
                    self.df,
                    "Traditional Chinese",
                )
                self.assertTrue(
                    llm_fallback.should_use_llm(
                        source, deterministic, "Traditional Chinese"
                    )
                )

    def test_title_route_accepts_arbitrary_single_and_multiword_subjects(self):
        csv_text = " ".join(self.df.fillna("").astype(str).to_numpy().ravel()).lower()
        self.assertNotIn("otter", csv_text)
        self.assertNotIn("badger", csv_text)

        for source, subject in (
            ("Otter pattern", "Otter"),
            ("Badger pattern", "Badger"),
            ("Little brown bear pattern", "Little brown bear"),
        ):
            with self.subTest(source=source):
                deterministic = line_translation.translate_ocr_line(
                    source, self.english_index, self.df, "Traditional Chinese"
                )

                def provider(_previous, current, _following, _target):
                    self.assertIsInstance(
                        current, llm_fallback.TitleTranslationRequest
                    )
                    self.assertEqual(current.subject, subject)
                    return json.dumps({
                        "classification": "ordinary_descriptive_noun",
                        "translated_or_preserved_text": "已翻譯標題",
                    })

                result = self.apply(
                    source,
                    deterministic,
                    "Traditional Chinese",
                    provider,
                    title_context=True,
                )
                self.assertEqual(result, "已翻譯標題 花樣")

    def test_title_route_preserves_brand_and_authoritative_pattern_term(self):
        source = "Jellycat pattern"
        deterministic = line_translation.translate_ocr_line(
            source, self.english_index, self.df, "Traditional Chinese"
        )

        def provider(_previous, current, _following, _target):
            self.assertIsInstance(current, llm_fallback.TitleTranslationRequest)
            return json.dumps({
                "classification": "brand_or_proper_name",
                "translated_or_preserved_text": current.subject,
            })

        result = self.apply(
            source,
            deterministic,
            "Traditional Chinese",
            provider,
            title_context=True,
        )
        self.assertEqual(result, "Jellycat 花樣")

    def test_title_route_rejects_changed_proper_name(self):
        deterministic = "Jellycat 花樣"
        result = self.apply(
            "Jellycat pattern",
            deterministic,
            "Traditional Chinese",
            lambda *_args: json.dumps({
                "classification": "brand_or_proper_name",
                "translated_or_preserved_text": "changed brand",
            }),
            title_context=True,
        )
        self.assertEqual(result, deterministic)

    def test_title_result_contract_rejects_malformed_or_extra_fields(self):
        cases = (
            "not json",
            json.dumps({"classification": "ordinary_descriptive_noun"}),
            json.dumps({
                "classification": "unknown",
                "translated_or_preserved_text": "result",
            }),
            json.dumps({
                "classification": "ordinary_descriptive_noun",
                "translated_or_preserved_text": "result",
                "extra": "not allowed",
            }),
        )
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertIsNone(
                    llm_fallback._parse_title_result(raw, "Ordinary subject")
                )

    def test_existing_block_title_signals_require_real_context(self):
        self.assertTrue(
            pattern_document.is_title_heading_context("Otter pattern", [])
        )
        self.assertTrue(
            pattern_document.is_title_heading_context(
                "Mushroom hat", ["R1: 6 sc"]
            )
        )
        self.assertFalse(
            pattern_document.is_title_heading_context(
                "Mushroom hat", ["ordinary prose"]
            )
        )
        for value in ("x", "A", "sc", "24x", "R16:x", "xyl0ph0ne"):
            with self.subTest(value=value):
                self.assertFalse(
                    pattern_document.is_title_heading_context(
                        value, ["R1: 6 sc"]
                    )
                )

    def test_general_fallback_still_receives_plain_text(self):
        provider = mock.Mock(side_effect=lambda _p, current, _n, _t: current)
        deterministic = "Dark brown yarn"
        self.apply(
            deterministic,
            deterministic,
            "Traditional Chinese",
            provider,
        )
        provider.assert_called_once()
        self.assertIsInstance(provider.call_args.args[1], str)

    def test_ocr_line_boundary_routes_confirmed_pattern_title(self):
        rows = pd.DataFrame([
            {
                "text": "Otter pattern",
                "confidence": 0.99,
                "min_x": 0,
                "max_x": 180,
                "min_y": 0,
                "max_y": 20,
            },
            {
                "text": "R1: 6 sc",
                "confidence": 0.99,
                "min_x": 0,
                "max_x": 180,
                "min_y": 30,
                "max_y": 50,
            },
        ])

        def provider(_previous, current, _following, _target):
            self.assertIsInstance(current, llm_fallback.TitleTranslationRequest)
            return json.dumps({
                "classification": "ordinary_descriptive_noun",
                "translated_or_preserved_text": "已翻譯標題",
            })

        result = ocr_lines.build_ocr_line_translations(
            rows,
            self.english_index,
            self.df,
            "Traditional Chinese",
            llm_provider=provider,
        )
        self.assertEqual(result.loc[0, "Translation"], "已翻譯標題 花樣")

    def test_short_notation_and_noise_do_not_call_provider(self):
        cases = (
            ("x", "x"),
            ("v", "v"),
            ("A", "A"),
            ("sc", "sc"),
            ("dc", "dc"),
            ("hdc", "hdc"),
            ("24x", "24x"),
            ("8A", "8A"),
            ("xv", "xv"),
            ("v2x", "v2x"),
            ("R16:x", "R16:x"),
            ("XYZ pattern", "XYZ 花樣"),
            ("R16: 24 sc", "R16: 24 sc"),
            ("xyl0ph0ne pattern", "xyl0ph0ne 花樣"),
        )
        for source, deterministic in cases:
            with self.subTest(source=source):
                provider = mock.Mock(return_value="wrong")
                result = self.apply(
                    source,
                    deterministic,
                    "Traditional Chinese",
                    provider,
                    title_context=True,
                )
                self.assertEqual(result, deterministic)
                provider.assert_not_called()

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
