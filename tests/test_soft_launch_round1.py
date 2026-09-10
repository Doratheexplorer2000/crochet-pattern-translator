import unittest
from pathlib import Path

import pandas as pd

from pattern_translator.engine import line_translation, ocr_cleanup, terminology


REPO_ROOT = Path(__file__).resolve().parents[1]


class BobbleAbbreviationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv(
            REPO_ROOT / "knowledge_base/data/master_stitches.csv"
        ).fillna("")

    def test_bob_resolves_to_existing_bobble_row_in_us_and_uk(self):
        for source_mode in ("English — US", "English — UK"):
            with self.subTest(source_mode=source_mode):
                index = terminology.build_term_index(self.df, source_mode)
                row = terminology.lookup_row("BOB", index, self.df)
                self.assertIsNotNone(row)
                self.assertEqual("st_052_bobble", row["stitch_id"])

    def test_existing_bo_mapping_and_preferred_output_are_unchanged(self):
        row = self.df[self.df["stitch_id"] == "st_052_bobble"].iloc[0]
        for source_mode in ("English — US", "English — UK"):
            with self.subTest(source_mode=source_mode):
                index = terminology.build_term_index(self.df, source_mode)
                self.assertEqual(
                    "st_052_bobble",
                    terminology.lookup_row("bo", index, self.df)["stitch_id"],
                )
                self.assertEqual(
                    "bo",
                    terminology.term_from_row(row, source_mode, prefer_abbrev=True),
                )

    def test_bobble_has_one_active_canonical_row(self):
        active = terminology.get_active_search_df(self.df)
        rows = active[
            active["US_term"].astype(str).str.casefold().eq("bobble")
        ]
        self.assertEqual(["st_052_bobble"], rows["stitch_id"].tolist())


class AttachedRowSeparatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv(
            REPO_ROOT / "knowledge_base/data/master_stitches.csv"
        ).fillna("")
        cls.index = terminology.build_term_index(cls.df, "English — US")

    def test_attached_and_spaced_row_separators_translate_identically(self):
        for source in ("5.24 sc (24)", "5. 24 sc (24)"):
            with self.subTest(source=source):
                self.assertEqual(
                    "R5: 24 sc (24)",
                    line_translation.translate_ocr_line(
                        source, self.index, self.df, "English — US"
                    ),
                )

    def test_existing_row_syntax_remains_unchanged(self):
        self.assertEqual(
            "R5: 24 sc (24)",
            line_translation.clean_single_ocr_line("R5: 24 sc (24)"),
        )

    def test_unrelated_decimal_measurement_remains_unchanged(self):
        value = "5.24mm hook"
        self.assertEqual(value, line_translation.clean_single_ocr_line(value))
        self.assertEqual(value, ocr_cleanup.clean_ocr_text(value))


class OverlayGuideTests(unittest.TestCase):
    def test_browser_guide_precedes_image_and_old_caption_is_removed(self):
        html = (REPO_ROOT / "pattern_translator/web/index.html").read_text(
            encoding="utf-8"
        )
        self.assertLess(html.index('class="overlay-guide"'), html.index('id="overlay-image"'))
        self.assertNotIn('data-i18n="overlayCaption"', html)

    def test_all_supported_languages_explain_markers_and_line_translation(self):
        source = (REPO_ROOT / "pattern_translator/web/translations.js").read_text(
            encoding="utf-8"
        )
        for title, section_name in (
            ("How to read the translated image", "Line-by-line Translation"),
            ("如何閱讀翻譯圖片", "逐行翻譯"),
            ("如何阅读翻译图片", "逐行翻译"),
            ("翻訳画像の見方", "行ごとの翻訳"),
        ):
            with self.subTest(title=title):
                self.assertIn(title, source)
                self.assertIn(section_name, source)
        self.assertEqual(4, source.count("overlayGuideTitle:"))
        self.assertEqual(4, source.count("overlayGuideBody:"))
        self.assertEqual(4, source.count("overlayGuideBodyReplacement:"))
        self.assertEqual(8, source.count("[1] [2] [3]"))


if __name__ == "__main__":
    unittest.main()
