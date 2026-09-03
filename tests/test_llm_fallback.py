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

    def test_general_provider_uses_contextual_luna_contract(self):
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
        self.assertEqual(captured["payload"]["model"], llm_fallback.GENERAL_MODEL)
        self.assertEqual(captured["payload"]["reasoning"], {"effort": "low"})
        self.assertEqual(captured["payload"]["max_output_tokens"], 400)
        prompt = captured["payload"]["input"]
        self.assertIn("DOMAIN: crochet pattern", prompt)
        self.assertIn("PATTERN CONTEXT: previous context", prompt)
        self.assertIn("CURRENT LINE: Capybara __ciqa__", prompt)
        self.assertIn("Translate only CURRENT LINE into Traditional Chinese", prompt)
        self.assertIn("semantic clues only", prompt)
        self.assertIn("placeholder exactly once and unchanged", prompt)
        self.assertNotIn("PREVIOUS:", prompt)
        self.assertNotIn("NEXT:", prompt)

    def test_downstream_timing_is_content_free_and_does_not_add_provider_calls(self):
        source_text = "we will not fill the body"
        translated_text = "我們不會填充身體"
        rows = pd.DataFrame([
            {
                "text": source_text,
                "confidence": 0.99,
                "min_x": 0,
                "max_x": 240,
                "min_y": 0,
                "max_y": 20,
            }
        ])
        events = []
        provider_calls = 0

        def diagnostic_logger(phase, **fields):
            events.append((phase, fields))

        def provider(_context, _current, _following, _target):
            nonlocal provider_calls
            provider_calls += 1
            return translated_text

        result = ocr_lines.build_ocr_line_translations(
            rows,
            self.english_index,
            self.df,
            "Traditional Chinese",
            "English — US",
            llm_provider=provider,
            diagnostic_logger=diagnostic_logger,
        )

        self.assertEqual(result.loc[0, "Translation"], translated_text)
        self.assertEqual(provider_calls, 1)
        phases = [phase for phase, _fields in events]
        for phase in (
            "deterministic_translation_begin",
            "deterministic_translation_end",
            "semantic_context_begin",
            "semantic_context_end",
            "ai_eligibility_summary",
            "ai_request_begin",
            "ai_request_end",
            "line_translation_end",
            "line_reconstruction_end",
        ):
            self.assertIn(phase, phases)
        summary = next(fields for phase, fields in events if phase == "ai_eligibility_summary")
        self.assertEqual(summary["visual_line_count"], 1)
        self.assertEqual(summary["eligible_line_count"], 1)
        serialized_events = json.dumps(events, ensure_ascii=False)
        self.assertNotIn(source_text, serialized_events)
        self.assertNotIn(translated_text, serialized_events)

    def test_provider_timing_covers_http_boundary_without_extra_request(self):
        events = []
        urlopen_calls = 0

        class FakeResponse(io.BytesIO):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        response = FakeResponse(json.dumps({
            "output": [{
                "content": [{"type": "output_text", "text": "我們不會填充身體"}]
            }]
        }).encode("utf-8"))

        def urlopen(_request, timeout):
            nonlocal urlopen_calls
            urlopen_calls += 1
            self.assertEqual(timeout, llm_fallback.DEFAULT_TIMEOUT_SECONDS)
            return response

        provider = llm_fallback.create_openai_provider("synthetic-test-key")
        with mock.patch.object(llm_fallback.urllib.request, "urlopen", side_effect=urlopen):
            result = llm_fallback.apply_llm_fallback(
                "we will not fill the body",
                "we will not fill the body",
                "",
                "",
                "Traditional Chinese",
                self.df,
                provider,
                diagnostic_logger=lambda phase, **fields: events.append((phase, fields)),
                call_ordinal=1,
            )

        self.assertEqual(result, "我們不會填充身體")
        self.assertEqual(urlopen_calls, 1)
        phases = [phase for phase, _fields in events]
        self.assertEqual(phases.count("ai_request_begin"), 1)
        self.assertEqual(phases.count("http_open_begin"), 1)
        self.assertEqual(phases.count("http_headers_received"), 1)
        self.assertEqual(phases.count("response_parse_end"), 1)
        self.assertEqual(phases.count("ai_request_end"), 1)
        request_end = next(fields for phase, fields in events if phase == "ai_request_end")
        self.assertEqual(request_end["outcome"], "success")
        self.assertEqual(request_end["model"], llm_fallback.GENERAL_MODEL)
        self.assertEqual(request_end["route"], "general")

    def test_provider_timeout_timing_preserves_deterministic_fallback(self):
        events = []
        provider_calls = 0

        def provider(*_args):
            nonlocal provider_calls
            provider_calls += 1
            raise TimeoutError()

        deterministic = "剪出兩隻眼睛"
        result = llm_fallback.apply_llm_fallback(
            deterministic,
            deterministic,
            "",
            "",
            "English — US",
            self.df,
            provider,
            diagnostic_logger=lambda phase, **fields: events.append((phase, fields)),
            call_ordinal=1,
        )

        self.assertEqual(result, deterministic)
        self.assertEqual(provider_calls, 1)
        self.assertEqual(
            [fields["outcome"] for phase, fields in events if phase == "ai_request_end"],
            ["timeout"],
        )
        self.assertNotIn(deterministic, json.dumps(events, ensure_ascii=False))

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
        self.assertEqual(captured["payload"]["model"], llm_fallback.TITLE_MODEL)
        self.assertEqual(captured["payload"]["reasoning"], {"effort": "low"})
        self.assertEqual(captured["payload"]["max_output_tokens"], 180)
        prompt = captured["payload"]["input"]
        self.assertEqual(
            prompt,
            "You are translating the subject of a crochet pattern title into Traditional Chinese. "
            "Classify the supplied subject as either an ordinary descriptive noun or a genuine brand/proper name. "
            "Translate an ordinary descriptive noun; preserve a genuine brand/proper name unchanged. "
            "Title Case alone does not make a word a proper name. "
            "Return JSON only with exactly these keys: classification, translated_or_preserved_text. "
            "Use classification ordinary_descriptive_noun or brand_or_proper_name.\n"
            "SUBJECT: Otter",
        )
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

    def test_structural_view_excludes_historical_pattern_instruction_prose(self):
        structural_index, structural_df = llm_fallback.structural_terminology_view(
            self.english_index, self.df
        )
        self.assertFalse(
            structural_df["category"].fillna("").eq("pattern_instruction").any()
        )
        source = "Stuff firmly before closing the opening"
        self.assertEqual(
            line_translation.translate_ocr_line(
                source, self.english_index, self.df, "Traditional Chinese"
            ),
            "塞滿棉花 before closing the opening",
        )
        self.assertEqual(
            line_translation.translate_ocr_line(
                source, structural_index, structural_df, "Traditional Chinese"
            ),
            source,
        )
        self.assertEqual(
            line_translation.translate_ocr_line(
                "R4: (sc, inc) x6",
                structural_index,
                structural_df,
                "Traditional Chinese",
            ),
            "R4: （短針，加針）重複6次",
        )

    def test_translation_scope_context_is_compact_deduplicated_and_notation_free(self):
        structural_index, structural_df = llm_fallback.structural_terminology_view(
            self.english_index, self.df
        )
        sources = (
            "Body (brown yarn)",
            "Body (brown yarn)",
            "R3: 6 sc",
            "R4: (sc, inc) x6",
            "Stuff firmly before closing the opening",
            "Sew the legs to both sides of the body",
        )
        lines = [
            line_translation.translate_ocr_line(
                source, structural_index, structural_df, "Traditional Chinese"
            )
            for source in sources
        ]
        context = llm_fallback.build_translation_scope_context(
            lines, structural_df, "Traditional Chinese"
        )
        self.assertEqual(
            context,
            "Body brown yarn | Stuff firmly before closing the opening | "
            "Sew the legs to both sides of the body",
        )
        for forbidden in ("R3", "R4", "6", "sc", "inc", "短針", "加針", "__ciq"):
            self.assertNotIn(forbidden, context)

    def test_scope_context_is_generated_once_and_reused(self):
        rows = pd.DataFrame([
            {"text": "Body (brown yarn)", "confidence": 0.99, "min_x": 0, "max_x": 180, "min_y": 0, "max_y": 20},
            {"text": "Stuff firmly before closing the opening", "confidence": 0.99, "min_x": 0, "max_x": 280, "min_y": 30, "max_y": 50},
            {"text": "R3: 6 sc", "confidence": 0.99, "min_x": 0, "max_x": 180, "min_y": 60, "max_y": 80},
        ])
        calls = []

        def provider(context, current, following, _target):
            calls.append((context, current, following))
            placeholders = llm_fallback._PLACEHOLDER_RE.findall(current)
            if current.startswith("Body"):
                return f"身體 {placeholders[0]}棕色毛線{placeholders[1]}"
            return "在縫合開口前填實填充物"

        with mock.patch.object(
            llm_fallback,
            "build_translation_scope_context",
            wraps=llm_fallback.build_translation_scope_context,
        ) as context_builder:
            result = ocr_lines.build_ocr_line_translations(
                rows,
                self.english_index,
                self.df,
                "Traditional Chinese",
                "English — US",
                llm_provider=provider,
            )

        context_builder.assert_called_once()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], calls[1][0])
        self.assertEqual(calls[0][2], "")
        self.assertEqual(calls[1][2], "")
        self.assertIn("Body brown yarn", calls[0][0])
        self.assertIn("Stuff firmly before closing the opening", calls[0][0])
        self.assertNotIn("R3", calls[0][0])
        self.assertEqual(result.loc[0, "Translation"], "身體 (棕色毛線)")
        self.assertEqual(result.loc[1, "Translation"], "在縫合開口前填實填充物")
        self.assertEqual(result.loc[2, "Translation"], "R3: 短針6針")

    def test_selected_scope_context_cannot_include_rows_not_supplied(self):
        selected_rows = pd.DataFrame([
            {"text": "Body (brown yarn)", "confidence": 0.99, "min_x": 0, "max_x": 180, "min_y": 0, "max_y": 20},
        ])
        contexts = []

        def provider(context, current, _following, _target):
            contexts.append(context)
            placeholders = llm_fallback._PLACEHOLDER_RE.findall(current)
            return f"身體 {placeholders[0]}棕色毛線{placeholders[1]}"

        ocr_lines.build_ocr_line_translations(
            selected_rows,
            self.english_index,
            self.df,
            "Traditional Chinese",
            "English — US",
            llm_provider=provider,
        )
        self.assertEqual(contexts, ["Body brown yarn"])
        self.assertNotIn("OUTSIDE_SELECTED_AREA", contexts[0])

    def test_twelve_general_prose_cases_route_through_contextual_luna_boundary(self):
        sources = (
            "Body (brown yarn)",
            "Head (white yarn)",
            "Petal (pink yarn)",
            "Stem (green yarn)",
            "Pot (brown yarn)",
            "Roof (red yarn)",
            "Leave a long yarn tail",
            "Embroider the eyes with black yarn",
            "Stuff firmly before closing the opening",
            "Sew the legs to both sides of the body",
            "Make another piece in the same way",
            "Change to white yarn and continue crocheting",
        )
        rows = pd.DataFrame([
            {"text": source, "confidence": 0.99, "min_x": 0, "max_x": 320, "min_y": position * 30, "max_y": position * 30 + 20}
            for position, source in enumerate(sources)
        ])
        translated = (
            "身體 {0}棕色毛線{1}",
            "頭部 {0}白色毛線{1}",
            "花瓣 {0}粉紅色毛線{1}",
            "莖 {0}綠色毛線{1}",
            "花盆 {0}棕色毛線{1}",
            "屋頂 {0}紅色毛線{1}",
            "留一段長毛線尾",
            "用黑色毛線繡上眼睛",
            "在縫合開口前填實填充物",
            "將腿縫到身體兩側",
            "以相同方式製作另一個部件",
            "改用白色毛線並繼續鈎織",
        )
        call_index = 0
        contexts = []

        def provider(context, current, _following, _target):
            nonlocal call_index
            contexts.append(context)
            placeholders = llm_fallback._PLACEHOLDER_RE.findall(current)
            value = translated[call_index]
            call_index += 1
            return value.format(*placeholders) if placeholders else value

        result = ocr_lines.build_ocr_line_translations(
            rows,
            self.english_index,
            self.df,
            "Traditional Chinese",
            "English — US",
            llm_provider=provider,
        )
        self.assertEqual(call_index, len(sources))
        self.assertEqual(len(set(contexts)), 1)
        self.assertEqual(
            result["Translation"].tolist(),
            [value.format("(", ")") if "{0}" in value else value for value in translated],
        )

    def test_pattern_instruction_fallback_remains_deterministic_without_provider(self):
        rows = pd.DataFrame([
            {"text": "Stuff firmly before closing the opening", "confidence": 0.99, "min_x": 0, "max_x": 300, "min_y": 0, "max_y": 20},
        ])
        result = ocr_lines.build_ocr_line_translations(
            rows, self.english_index, self.df, "Traditional Chinese", "English — US"
        )
        self.assertEqual(
            result.loc[0, "Translation"], "塞滿棉花 before closing the opening"
        )

    def test_structural_lines_remain_deterministic_and_do_not_call_luna(self):
        sources = ("R3: 6 sc", "R4: (sc, inc) x6", "R5-7: 24 sc", "24x", "R16:x")
        rows = pd.DataFrame([
            {"text": source, "confidence": 0.99, "min_x": 0, "max_x": 220, "min_y": position * 30, "max_y": position * 30 + 20}
            for position, source in enumerate(sources)
        ])
        provider = mock.Mock(return_value="wrong")
        result = ocr_lines.build_ocr_line_translations(
            rows,
            self.english_index,
            self.df,
            "Traditional Chinese",
            "English — US",
            llm_provider=provider,
        )
        provider.assert_not_called()
        self.assertEqual(
            result["Translation"].tolist(),
            ["R3: 短針6針", "R4: （短針，加針）重複6次", "R5-7: 短針24針", "短針24針", "R16: 短針"],
        )

    def test_contextual_results_preserve_line_order_and_txt_export_contract(self):
        rows = pd.DataFrame([
            {"text": "Body (brown yarn)", "confidence": 0.99, "min_x": 0, "max_x": 220, "min_y": 0, "max_y": 20},
            {"text": "R3: 6 sc", "confidence": 0.98, "min_x": 0, "max_x": 180, "min_y": 30, "max_y": 50},
        ])

        def provider(_context, current, _following, _target):
            placeholders = llm_fallback._PLACEHOLDER_RE.findall(current)
            return f"身體 {placeholders[0]}棕色毛線{placeholders[1]}"

        result = ocr_lines.build_ocr_line_translations(
            rows,
            self.english_index,
            self.df,
            "Traditional Chinese",
            "English — US",
            llm_provider=provider,
        )
        self.assertEqual(result["Original"].tolist(), ["Body (brown yarn)", "R3: 6 sc"])
        self.assertEqual(result["Translation"].tolist(), ["身體 (棕色毛線)", "R3: 短針6針"])

        readable = line_translation.build_readable_line_translation(result)
        self.assertLess(readable.index("Body (brown yarn)"), readable.index("R3: 6 sc"))
        self.assertEqual(
            line_translation.build_overlay_export_text(result),
            readable + "\n",
        )

    def test_mixed_notation_sends_only_embedded_chinese_prose_to_provider(self):
        source = "R9:x,A,3x结束留长线 R16:x,A,55x"
        rows = pd.DataFrame([
            {"text": source, "confidence": 0.99, "min_x": 0, "max_x": 500, "min_y": 0, "max_y": 20},
        ])
        calls = []

        def provider(context, current, following, target):
            calls.append((context, current, following, target))
            return "finish and leave a long yarn tail"

        result = ocr_lines.build_ocr_line_translations(
            rows,
            terminology.build_term_index(self.df, "Traditional Chinese"),
            self.df,
            "English — US",
            "Traditional Chinese",
            llm_provider=provider,
        )
        self.assertEqual(
            calls,
            [("结束留长线", "结束留长线", "", "English — US")],
        )
        self.assertEqual(
            result.loc[0, "Translation"],
            "R9: sc, dec, 3 sc finish and leave a long yarn tail R16: sc, dec, 55 sc",
        )

    def test_mixed_notation_prose_isolated_for_both_translation_directions(self):
        cases = (
            (
                "R8:12x换白色线 R9:12x",
                "Traditional Chinese",
                "English — US",
                "换白色线",
                "change to white yarn",
                "R8: 12 sc change to white yarn R9: 12 sc",
            ),
            (
                "R5:6x填充棉花 R6:6A",
                "Traditional Chinese",
                "English — US",
                "填充棉花",
                "stuff with filling",
                "R5: 6 sc stuff with filling R6: dec x6",
            ),
            (
                "R8: 12 sc finish the piece R9: 12 sc",
                "English — US",
                "Traditional Chinese",
                "finish the piece",
                "完成這個部件",
                "R8: 短針12針 完成這個部件 R9: 短針12針",
            ),
        )
        for source, source_mode, output_mode, expected_input, response, expected in cases:
            with self.subTest(source=source):
                rows = pd.DataFrame([
                    {"text": source, "confidence": 0.99, "min_x": 0, "max_x": 500, "min_y": 0, "max_y": 20},
                ])
                calls = []

                def provider(_context, current, _following, _target):
                    calls.append(current)
                    return response

                result = ocr_lines.build_ocr_line_translations(
                    rows,
                    terminology.build_term_index(self.df, source_mode),
                    self.df,
                    output_mode,
                    source_mode,
                    llm_provider=provider,
                )
                self.assertEqual(calls, [expected_input])
                self.assertEqual(result.loc[0, "Translation"], expected)

    def test_mixed_notation_rejects_attempted_structural_invention(self):
        source = "R9:x,A,3x结束留长线 R16:x,A,55x"
        deterministic = "R9: sc, dec, 3 sc 结束留长线 R16: sc, dec, 55 sc"
        structural_index, structural_df = llm_fallback.structural_terminology_view(
            terminology.build_term_index(self.df, "Traditional Chinese"), self.df
        )
        llm_input = line_translation.translate_ocr_line(
            source, structural_index, structural_df, "English — US"
        )
        for corrupt_response in (
            "finish and leave a long yarn tail R10",
            "finish and leave 4 sc",
            "finish and leave 54 sc",
            "finish and inc",
        ):
            with self.subTest(corrupt_response=corrupt_response):
                result = llm_fallback.apply_llm_fallback(
                    source=source,
                    deterministic=deterministic,
                    previous="",
                    following="",
                    output_mode="English — US",
                    df=self.df,
                    provider=lambda *_args, value=corrupt_response: value,
                    semantic_context="结束留长线",
                    llm_input_text=llm_input,
                    llm_df=structural_df,
                )
                self.assertEqual(result, deterministic)

    def test_non_latin_target_rejects_invented_latin_word_and_shorthand(self):
        source = "Ear / hand (x4)"
        deterministic = "Ear / hand (x4)"
        for invented in ("inventedword", "ZZ", "ZZ2", "Q7X"):
            with self.subTest(invented=invented):
                result = llm_fallback.apply_llm_fallback(
                    source=source,
                    deterministic=deterministic,
                    previous="",
                    following="",
                    output_mode="Traditional Chinese",
                    df=self.df,
                    provider=lambda *_args, token=invented: f"耳朵 / 手 {token}",
                    semantic_context="Body | Ear | hand",
                )
                self.assertEqual(result, deterministic)

    def test_source_derived_latin_name_remains_authorised(self):
        source = "Mabel body"
        deterministic = "Mabel 身體"
        result = llm_fallback.apply_llm_fallback(
            source=source,
            deterministic=deterministic,
            previous="",
            following="",
            output_mode="Traditional Chinese",
            df=self.df,
            provider=lambda *_args: "Mabel 的身體",
            semantic_context="Mabel body",
        )
        self.assertEqual(result, "Mabel 的身體")

    def test_context_term_does_not_authorise_latin_output_leak(self):
        source = "Ear / hand (x4)"
        deterministic = "Ear / hand (x4)"
        result = llm_fallback.apply_llm_fallback(
            source=source,
            deterministic=deterministic,
            previous="",
            following="",
            output_mode="Traditional Chinese",
            df=self.df,
            provider=lambda *_args: "耳朵 / 手 Roof",
            semantic_context="Roof red yarn | Ear hand",
        )
        self.assertEqual(result, deterministic)

    def test_english_target_allows_generated_target_language_words(self):
        source = "结束留长线"
        deterministic = "结束留长线"
        result = llm_fallback.apply_llm_fallback(
            source=source,
            deterministic=deterministic,
            previous="",
            following="",
            output_mode="English — US",
            df=self.df,
            provider=lambda *_args: "Finish off, leaving a long tail.",
            semantic_context="结束留长线",
        )
        self.assertEqual(result, "Finish off, leaving a long tail.")

    def test_latin_provenance_guard_is_target_aware_and_allows_crochet_abbreviations(self):
        for output_mode in ("Traditional Chinese", "Simplified Chinese", "Japanese"):
            with self.subTest(output_mode=output_mode):
                self.assertTrue(
                    llm_fallback._has_unsupported_latin_output(
                        "翻譯 inventedword", "原文", "原文", output_mode
                    )
                )
                self.assertFalse(
                    llm_fallback._has_unsupported_latin_output(
                        "sc dc hdc slst inc dec", "原文", "原文", output_mode
                    )
                )
        self.assertFalse(
            llm_fallback._has_unsupported_latin_output(
                "Finish off, leaving a long tail.",
                "结束留长线",
                "结束留长线",
                "English — US",
            )
        )

    def test_deterministic_start_with_mapping_remains_authorised(self):
        source = "Start with"
        deterministic = "從……開始"
        provider = mock.Mock(return_value="wrong")
        result = self.apply(
            source,
            deterministic,
            "Traditional Chinese",
            provider,
        )
        self.assertEqual(result, deterministic)
        provider.assert_not_called()

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
            "English — US",
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
        result = ocr_lines.build_ocr_line_translations(
            rows, index, self.df, "English — US", "Simplified Chinese"
        )
        self.assertEqual(
            result["Translation"].tolist(),
            [
                "Chain 21, Start in the 2nd chain from hook, 19 sc, 3 sc in same stitch",
                "眼睛在11-12行之间",
            ],
        )


if __name__ == "__main__":
    unittest.main()
