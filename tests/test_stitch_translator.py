import unittest
from pathlib import Path

import streamlit

from stitch_translator import app


class StitchTranslatorRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        load_data = getattr(app.load_data, "__wrapped__", app.load_data)
        build_index = getattr(app.build_index, "__wrapped__", app.build_index)
        cls.database = load_data()
        cls.index = build_index(cls.database)

    def test_streamlit_runtime_matches_production_baseline(self):
        self.assertEqual(streamlit.__version__, "1.51.0")

    def test_known_stitch_returns_expected_multilingual_result(self):
        results = app.search("single crochet", self.database, self.index)

        self.assertEqual(len(results), 1)
        row = results.iloc[0]
        self.assertEqual(row["stitch_id"], "st_003_single_crochet")
        self.assertEqual(row["US_term"], "single crochet")
        self.assertEqual(row["UK_term"], "double crochet")
        self.assertEqual(row["Chinese_term"], "短針")
        self.assertEqual(row["Japanese"], "細編み")

    def test_unknown_non_stitch_remains_empty(self):
        results = app.search("not-a-crochet-stitch-xyz", self.database, self.index)
        self.assertTrue(results.empty)

    def test_us_uk_ambiguity_and_filtering_are_preserved(self):
        results = app.search("dc", self.database, self.index)

        self.assertTrue(app.needs_us_uk_choice("dc", results))
        us_results = app.filter_by_terminology(results, "us")
        uk_results = app.filter_by_terminology(results, "uk")
        self.assertTrue(us_results["_matched_col"].str.startswith("US_").all())
        self.assertTrue(uk_results["_matched_col"].str.startswith("UK_").all())

    def test_tutorial_search_remains_data_driven_and_localized(self):
        result = app.search("single crochet", self.database, self.index).iloc[0]

        self.assertEqual(str(result["tutorial_search"]).lower(), "yes")
        self.assertEqual(
            app.build_tutorial_search_query(result, "zh-Hant"),
            "crochet single crochet 短針",
        )
        self.assertIn("youtube.com/results?search_query=", app.build_tutorial_search_url(result, "en"))

    def test_search_analytics_dispatches_once_per_changed_submission(self):
        state = {}

        first = app.search_analytics_event(state, "single crochet", "en", found=True)
        rerun = app.search_analytics_event(state, "single crochet", "en", found=True)
        second = app.search_analytics_event(state, "double crochet", "zh-Hant", found=False)

        self.assertEqual(first["name"], "stitch_searched")
        self.assertEqual(
            first["properties"],
            {
                "search_keyword": "single crochet",
                "translate_to": "en",
                "search_result_status": "found",
            },
        )
        self.assertIsNone(rerun)
        self.assertEqual(second["properties"]["search_result_status"], "not_found")
        self.assertNotEqual(first["id"], second["id"])

    def test_clearing_search_allows_same_query_to_be_submitted_again(self):
        state = {}
        first = app.search_analytics_event(state, "dc", "en", found=True)
        app.search_analytics_event(state, "", "en", found=False)
        second = app.search_analytics_event(state, "dc", "en", found=True)

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertNotEqual(first["id"], second["id"])

    def test_stitch_app_uses_shared_v2_bridge_for_approved_events(self):
        source = Path("stitch_translator/app.py").read_text(encoding="utf-8")

        self.assertIn("mount_plausible_bridge(None)", source)
        self.assertIn('"stitch_searched"', source)
        self.assertIn('"tutorial_opened"', source)
        self.assertIn('"feedback_clicked"', source)
        self.assertNotIn("components.v2.component", source)

    def test_all_interface_languages_have_complete_visible_copy(self):
        required = {
            "title",
            "subtitle",
            "search_label",
            "results",
            "feedback_title",
            "feedback_button",
            "privacy_note",
            "tutorial_button",
            "terminology_us",
            "terminology_uk",
            "terminology_both",
        }
        self.assertEqual(set(app.SUPPORTED_LANGS), set(app.UI_TEXT))
        for language, text in app.UI_TEXT.items():
            self.assertTrue(required.issubset(text), language)
            self.assertTrue(all(str(text[key]).strip() for key in required), language)

    def test_ui_uses_shared_brand_tokens_and_system_theme(self):
        source = Path("stitch_translator/app.py").read_text(encoding="utf-8")
        self.assertIn("--ci-primary: #0F766E", source)
        self.assertIn("--ci-bg: #FAF9F7", source)
        self.assertIn("@media (prefers-color-scheme: dark)", source)
        self.assertIn("Crochet Intelligence", source)
        self.assertNotIn("#5f73a8", source.lower())
        self.assertNotIn("#6b46c1", source.lower())

    def test_railway_runtime_is_stitch_specific(self):
        dockerfile = Path("stitch_translator/Dockerfile").read_text(encoding="utf-8")
        start_script = Path("stitch_translator/railway_start.sh").read_text(encoding="utf-8")
        requirements = Path("stitch_translator/requirements.txt").read_text(encoding="utf-8")

        self.assertIn("streamlit==1.51.0", requirements)
        self.assertIn("pandas==2.3.3", requirements)
        self.assertIn("COPY crochet_intelligence ./crochet_intelligence", dockerfile)
        self.assertIn("COPY stitch_translator ./stitch_translator", dockerfile)
        self.assertIn("streamlit run stitch_translator/app.py", start_script)
        self.assertNotIn("pattern_translator/app.py", start_script)


if __name__ == "__main__":
    unittest.main()
