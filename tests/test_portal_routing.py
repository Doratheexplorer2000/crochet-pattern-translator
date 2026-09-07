import unittest
from pathlib import Path


class PortalRoutingTests(unittest.TestCase):
    def test_production_tool_destinations_remain_configured(self):
        dockerfile = Path("portal/Dockerfile").read_text(encoding="utf-8")

        self.assertIn(
            "ARG PUBLIC_PATTERN_TRANSLATOR_URL="
            "https://pattern.crochetintelligence.com",
            dockerfile,
        )
        self.assertIn(
            "ARG PUBLIC_STITCH_TRANSLATOR_URL="
            "https://stitch.crochetintelligence.com",
            dockerfile,
        )
        self.assertNotIn("up.railway.app", dockerfile)

    def test_portal_propagates_all_supported_locales_to_tool_links(self):
        layout = Path("portal/src/layouts/PortalLayout.astro").read_text(encoding="utf-8")
        tool_grid = Path("portal/src/components/ToolGrid.astro").read_text(encoding="utf-8")

        self.assertIn('const supportedLocales = ["en", "zh-Hant", "zh-Hans", "ja"]', layout)
        self.assertIn('toolUrl.searchParams.set("ui_lang", locale)', layout)
        self.assertIn('data-tool-href={tool.href}', tool_grid)
        self.assertIn("plausible-event-name=${tool.analyticsEvent}", tool_grid)

    def test_portal_privacy_contains_current_provider_neutral_ai_boundary(self):
        translations = Path("portal/src/i18n/translations.ts").read_text(encoding="utf-8")

        for expected_text in (
            "Uploaded images are never sent to an AI model provider",
            "上載圖片絕不會傳送至 AI 模型服務提供者",
            "上传图片绝不会发送至 AI 模型服务提供商",
            "アップロード画像がAIモデルサービス提供者へ送信されることはありません",
        ):
            self.assertIn(expected_text, translations)
        self.assertNotIn("OpenAI", translations)
        self.assertEqual(translations.count('"privacy.body"'), 4)

    def test_portal_approved_tool_demos_and_privacy_affordance_are_present(self):
        translations = Path("portal/src/i18n/translations.ts").read_text(encoding="utf-8")
        tool_grid = Path("portal/src/components/ToolGrid.astro").read_text(encoding="utf-8")
        footer = Path("portal/src/components/Footer.astro").read_text(encoding="utf-8")
        styles = Path("portal/src/styles/global.css").read_text(encoding="utf-8")

        for key in (
            "tools.pattern.demoLabel",
            "tools.pattern.demoInput",
            "tools.pattern.demoOutput",
            "tools.stitch.demoLabel",
            "tools.stitch.demoInput",
            "tools.stitch.demoOutput",
        ):
            self.assertEqual(translations.count(f'"{key}"'), 4)
        self.assertIn('class="tool-card__content"', tool_grid)
        self.assertIn('class="tool-demo"', tool_grid)
        self.assertIn('data-i18n-aria-label={`tools.${tool.translationKey}.demoLabel`}', tool_grid)
        self.assertIn("UK: R1: MR 6 dc", tool_grid)
        self.assertIn("UK: double crochet 繁中: 短針", tool_grid)
        self.assertIn('<details class="privacy-disclosure">', footer)
        self.assertIn('<summary data-i18n="privacy.title">', footer)
        self.assertIn('.privacy-disclosure summary::-webkit-details-marker', styles)
        self.assertIn('.privacy-disclosure summary::after', styles)
        self.assertIn('.privacy-disclosure[open] summary::after', styles)
        self.assertIn('content: "▾";', styles)
        self.assertIn('content: "▴";', styles)

    def test_pattern_uses_portal_locale_without_removing_translation_controls(self):
        source = Path("pattern_translator/app.py").read_text(encoding="utf-8")

        for canonical in (
            '"en": "English"',
            '"zh-Hant": "繁體中文"',
            '"zh-Hans": "简体中文"',
            '"ja": "日本語"',
        ):
            self.assertIn(canonical, source)
        self.assertIn('st.query_params.get("ui_lang", "")', source)
        self.assertNotIn('key="interface_language_selector",', source)
        self.assertIn('key="source_language_selector"', source)
        self.assertIn('key="target_language_selector"', source)
        self.assertNotIn('t("privacy_expander")', source)
        self.assertIn("portal_url_for_language(interface_language)", source)
        self.assertIn('target="_self"', source)
        self.assertIn('DEFAULT_PORTAL_URL = "https://crochetintelligence.com"', source)
        self.assertNotIn("up.railway.app", source)

    def test_pattern_translation_routing_is_independent_from_interface_language(self):
        app_source = Path("pattern_translator/app.py").read_text(encoding="utf-8")
        service_source = Path(
            "pattern_translator/translation_service.py"
        ).read_text(encoding="utf-8")

        self.assertIn("df, index = prepare_translation_dataframe(full_df, source_mode)", app_source)
        self.assertIn("output_mode=output_mode,", app_source)
        self.assertIn(
            "ocr_lines_engine.build_ocr_line_translations(\n"
            "            ocr_rows,\n"
            "            index,\n"
            "            df,\n"
            "            output_mode,",
            service_source,
        )
        self.assertNotIn("output_mode=interface_language", app_source)
        self.assertNotIn("source_mode=interface_language", app_source)
        self.assertNotIn("output_mode=interface_language", service_source)
        self.assertNotIn("source_mode=interface_language", service_source)

    def test_pattern_branding_uses_current_product_identity(self):
        source = Path("pattern_translator/app.py").read_text(encoding="utf-8")

        self.assertIn('page_title="Crochet Pattern Translator"', source)
        self.assertIn('"app_title": "Crochet Pattern Translator"', source)
        self.assertIn('<div class="product-kicker">Crochet Intelligence</div>', source)

    def test_analytics_event_names_remain_unchanged(self):
        portal_tools = Path("portal/src/data/tools.ts").read_text(encoding="utf-8")
        pattern = Path("pattern_translator/app.py").read_text(encoding="utf-8")
        stitch = Path("stitch_translator/app.py").read_text(encoding="utf-8")

        for event_name in ("portal_pattern_selected", "portal_stitch_selected"):
            self.assertIn(event_name, portal_tools)
        for event_name in (
            "pattern_image_uploaded",
            "pattern_translation_completed",
            "pattern_png_downloaded",
            "pattern_txt_downloaded",
            "pattern_feedback_clicked",
        ):
            self.assertIn(event_name, pattern)
        for event_name in ("stitch_searched", "tutorial_opened", "feedback_clicked"):
            self.assertIn(event_name, stitch)


if __name__ == "__main__":
    unittest.main()
