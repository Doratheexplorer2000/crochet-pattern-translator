import unittest
from unittest import mock

import pandas as pd

from pattern_translator.engine import line_translation
from pattern_translator.engine import llm_fallback
from pattern_translator.engine import ocr_lines
from pattern_translator.engine import terminology


class TerminologyDerivedCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = pd.read_csv("knowledge_base/data/master_stitches.csv").fillna("")

    def prepared(self, source_mode="Traditional Chinese"):
        df = terminology.get_active_search_df(self.database)
        index = terminology.build_term_index(df, source_mode)
        all_index = terminology.build_all_term_index(df)
        df.attrs["all_term_index"] = all_index
        df.attrs["normalized_lookup_index"] = terminology.build_normalized_lookup_index(
            index, all_index, source_mode
        )
        terminology.prepare_derived_terminology_cache(df)
        return df, index

    def test_hot_translation_does_not_rehash_dataframe(self):
        df, index = self.prepared()
        with mock.patch.object(
            terminology,
            "csv_term_cache_key",
            side_effect=AssertionError("hot path recomputed DataFrame hash"),
        ):
            first = line_translation.translate_ocr_line(
                "R4: (x, v) x6", index, df, "English — US"
            )
            second = line_translation.translate_ocr_line(
                "R4: (x, v) x6", index, df, "English — US"
            )
        self.assertEqual(first, second)
        self.assertEqual(first, "R4: (sc, inc) x6")

    def test_target_terms_are_built_once_per_output_language(self):
        df, _index = self.prepared()
        with mock.patch.object(
            terminology,
            "get_source_columns",
            wraps=terminology.get_source_columns,
        ) as source_columns:
            first = llm_fallback._target_terms(df, "English — US")
            second = llm_fallback._target_terms(df, "English — US")
            chinese = llm_fallback._target_terms(df, "Traditional Chinese")
        self.assertEqual(first, second)
        self.assertIn("sc", first)
        self.assertIn("短針", chinese)
        self.assertEqual(source_columns.call_count, 2)

    def test_full_llm_boundary_hashes_each_terminology_view_once(self):
        df = terminology.get_active_search_df(self.database)
        index = terminology.build_term_index(df, "Traditional Chinese")
        rows = pd.DataFrame(
            [
                {
                    "text": "Body (brown yarn)",
                    "confidence": 0.99,
                    "min_x": 0,
                    "max_x": 180,
                    "min_y": 0,
                    "max_y": 20,
                },
                {
                    "text": "R3: 6x",
                    "confidence": 0.99,
                    "min_x": 0,
                    "max_x": 180,
                    "min_y": 30,
                    "max_y": 50,
                },
            ]
        )
        with mock.patch.object(
            terminology,
            "csv_term_cache_key",
            wraps=terminology.csv_term_cache_key,
        ) as content_key:
            result = ocr_lines.build_ocr_line_translations(
                rows,
                index,
                df,
                "English — US",
                llm_provider=lambda _context, current, _following, _target: current,
            )
        self.assertEqual(len(result), 2)
        self.assertEqual(content_key.call_count, 2)

    def test_prepare_invalidates_cache_after_content_change(self):
        df = pd.DataFrame(
            [
                {
                    "search_status": "active",
                    "US_term": "alpha stitch",
                    "US_term_alias": "alpha alias",
                    "Chinese_term": "甲針",
                }
            ]
        ).fillna("")
        first = terminology.prepare_derived_terminology_cache(df)
        first_key = first["content_key"]
        self.assertIn("alpha alias", terminology.get_all_csv_terms(df))

        df.loc[0, "US_term_alias"] = "beta alias"
        second = terminology.prepare_derived_terminology_cache(df)
        self.assertNotEqual(first_key, second["content_key"])
        self.assertIn("beta alias", terminology.get_all_csv_terms(df))
        self.assertNotIn("alpha alias", terminology.get_all_csv_terms(df))

    def test_aliases_and_inactive_rows_preserve_existing_filtering(self):
        df = pd.DataFrame(
            [
                {
                    "search_status": "active",
                    "US_term": "active stitch",
                    "US_term_alias": "live alias|second alias",
                },
                {
                    "search_status": "inactive",
                    "US_term": "inactive stitch",
                    "US_term_alias": "hidden alias",
                },
            ]
        ).fillna("")
        terminology.prepare_derived_terminology_cache(df)
        terms = terminology.get_all_csv_terms(df)
        self.assertIn("active stitch", terms)
        self.assertIn("live alias", terms)
        self.assertIn("second alias", terms)
        self.assertNotIn("inactive stitch", terms)
        self.assertNotIn("hidden alias", terms)

    def test_us_uk_and_multilingual_output_remains_isolated(self):
        df = self.database.copy()
        index = terminology.build_term_index(df, "English — US")
        terminology.prepare_derived_terminology_cache(df)
        self.assertEqual(terminology.lookup_term("sc", index, df, "English — US", True), "sc")
        self.assertEqual(terminology.lookup_term("sc", index, df, "English — UK", True), "dc")
        self.assertEqual(terminology.lookup_term("sc", index, df, "Traditional Chinese"), "短針")
        self.assertEqual(terminology.lookup_term("sc", index, df, "Simplified Chinese"), "短针")
        self.assertTrue(terminology.lookup_term("sc", index, df, "Japanese"))


if __name__ == "__main__":
    unittest.main()
