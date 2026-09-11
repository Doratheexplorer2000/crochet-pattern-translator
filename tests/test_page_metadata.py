import json
import os
import unittest
from unittest import mock

import pandas as pd
from PIL import Image, ImageDraw

from pattern_translator.engine import broad_translation
from pattern_translator.engine import ocr_lines
from pattern_translator.engine import overlay
from pattern_translator.engine import pattern_document


def _row(text, x1, y1, x2, y2, confidence=0.98):
    return {
        "text": text,
        "confidence": confidence,
        "min_x": x1,
        "min_y": y1,
        "max_x": x2,
        "max_y": y2,
        "x": (x1 + x2) / 2,
        "y": (y1 + y2) / 2,
        "global_x": (x1 + x2) / 2,
    }


class PageMetadataCleanupTests(unittest.TestCase):
    def test_flower_short_cjk_continuation_is_kept_and_page_label_is_excluded(self):
        rows = pd.DataFrame(
            [
                _row("線頭留於外側，纏繞1圈後打", 521.3, 1323.0, 936.7, 1358.2),
                _row("結。", 516.7, 1375.1, 582.6, 1416.5),
                _row("-7-", 486.0, 1457.9, 522.8, 1483.9, 0.758),
            ]
        )

        kept, excluded = pattern_document.filter_noise_and_watermarks(
            rows,
            image_width=1018,
            image_height=1533,
        )

        self.assertEqual(
            ["線頭留於外側，纏繞1圈後打", "結。"],
            kept["text"].tolist(),
        )
        self.assertEqual(["-7-"], excluded["text"].tolist())
        self.assertEqual("page_label", excluded.iloc[0]["Content Category"])
        self.assertEqual(
            "detached_footer_page_label",
            excluded.iloc[0]["Content Exclusion Reason"],
        )
        self.assertEqual("preserved_in_source", excluded.iloc[0]["Preserved State"])

    def test_isolated_short_noise_remains_removable(self):
        rows = pd.DataFrame([_row("Q.", 20, 20, 30, 35)])

        kept, removed = pattern_document.filter_noise_and_watermarks(
            rows,
            image_width=400,
            image_height=600,
        )

        self.assertTrue(kept.empty)
        self.assertEqual(["Q"], removed["text"].tolist())
        self.assertIn("watermark/noise", removed.iloc[0]["removed_reason"])

    def test_supported_detached_page_label_forms_are_excluded(self):
        for label in ("-7-", "- 7 -", "—7—", "7"):
            with self.subTest(label=label):
                rows = pd.DataFrame(
                    [
                        _row("ordinary body text", 100, 1200, 500, 1235),
                        _row(label, 490, 1450, 530, 1480),
                    ]
                )
                kept, excluded = pattern_document.filter_noise_and_watermarks(
                    rows,
                    image_width=1020,
                    image_height=1530,
                )
                self.assertEqual(["ordinary body text"], kept["text"].tolist())
                self.assertEqual([label], excluded["text"].tolist())
                self.assertEqual(
                    "detached_footer_page_label",
                    excluded.iloc[0]["Content Exclusion Reason"],
                )

    def test_legitimate_numeric_crochet_content_is_not_page_metadata(self):
        cases = (
            "R7",
            "Row 7",
            "Rnd 7",
            "7 sc",
            "Total: 7 stitches",
            "repeat 7 times",
            "Work into stitch 7 before turning",
            "7 sc at the bottom of the page",
        )
        rows = pd.DataFrame(
            [
                _row(text, 30, 1050 + index * 35, 500, 1080 + index * 35)
                for index, text in enumerate(cases)
            ]
        )

        kept, excluded = pattern_document.filter_noise_and_watermarks(
            rows,
            image_width=1020,
            image_height=1530,
        )

        self.assertEqual(list(cases), kept["text"].tolist())
        self.assertTrue(excluded.empty)

    def test_plain_number_without_footer_geometry_is_preserved_as_content(self):
        rows = pd.DataFrame([_row("7", 50, 300, 65, 330)])

        kept, excluded = pattern_document.filter_noise_and_watermarks(
            rows,
            image_width=1020,
            image_height=1530,
        )

        self.assertEqual(["7"], kept["text"].tolist())
        self.assertTrue(excluded.empty)


class FlowerPageGroupingTests(unittest.TestCase):
    def test_page_label_never_enters_broad_and_remains_visible(self):
        source = Image.new("RGB", (1018, 1533), "white")
        source_draw = ImageDraw.Draw(source)
        source_draw.text((486, 1457), "-7-", fill="black")
        page_before = source.crop((486, 1458, 523, 1484)).tobytes()
        rows = pd.DataFrame(
            [
                _row("線頭留於外側，纏繞1圈後打", 521.3, 1323.0, 936.7, 1358.2),
                _row("結。", 516.7, 1375.1, 582.6, 1416.5),
                _row("-7-", 486.0, 1457.9, 522.8, 1483.9, 0.758),
            ]
        )
        kept, excluded = pattern_document.filter_noise_and_watermarks(
            rows,
            image_width=1018,
            image_height=1533,
        )
        prompts = []

        def fake_luna(prompt, api_key):
            self.assertEqual("test-key", api_key)
            prompts.append(prompt)
            payload = json.loads(prompt.split("INPUT: ", 1)[1])
            segments = payload["source_segments"]
            self.assertEqual(
                ["線頭留於外側,纏繞1圈後打", "結."],
                [segment["text"] for segment in segments],
            )
            self.assertNotIn("-7-", prompt)
            assignments = {
                segment["source_segment_id"]: "unit-0000"
                for segment in segments
            }
            response = {
                "segment_assignments": assignments,
                "semantic_units": {
                    "unit-0000": {
                        "translated_text": (
                            "Leave the yarn end on the outside, wrap it 1 time, then tie."
                        )
                    }
                },
            }
            return {
                "output": [
                    {
                        "content": [
                            {"type": "output_text", "text": json.dumps(response)}
                        ]
                    }
                ]
            }, 0.01

        environment = {
            "PATTERN_BROAD_TRANSLATION_ENABLED": "1",
            "OPENAI_API_KEY": "test-key",
            "PATTERN_SOURCE_REPLACEMENT_OVERLAY_ENABLED": "1",
        }
        with mock.patch.dict(os.environ, environment, clear=False), mock.patch.object(
            broad_translation,
            "call_luna_once",
            side_effect=fake_luna,
        ):
            line_df = ocr_lines.build_ocr_line_translations(
                kept,
                {},
                pd.DataFrame(),
                "English — US",
                "Traditional Chinese",
            )
            rendered, _legend, legend_df = overlay.make_line_translation_overlay(
                source,
                line_df,
                "English — US",
                protected_ocr_rows=excluded,
            )

        self.assertEqual(1, len(prompts))
        self.assertEqual(1, len(line_df))
        self.assertEqual(
            "線頭留於外側，纏繞1圈後打\n結。",
            line_df.loc[0, "Original"],
        )
        self.assertNotIn("-7-", line_df.loc[0, "Original"])
        self.assertNotIn("-7-", line_df.loc[0, "Translation"])
        self.assertEqual("", line_df.loc[0, "Overlay Marker"])
        self.assertTrue(legend_df.empty or not legend_df["Marker"].astype(str).any())
        self.assertIsNotNone(rendered)
        self.assertEqual(
            page_before,
            rendered.crop((486, 1458, 523, 1484)).tobytes(),
        )


if __name__ == "__main__":
    unittest.main()
