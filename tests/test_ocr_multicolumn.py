import json
import os
import unittest
from unittest import mock

import pandas as pd
from PIL import Image

from pattern_translator.engine import broad_translation
from pattern_translator.engine import ocr_lines
from pattern_translator.engine import overlay


def _ocr_row(text, x1, y1, x2, y2):
    return {
        "text": text,
        "confidence": 0.99,
        "min_x": float(x1),
        "max_x": float(x2),
        "min_y": float(y1),
        "max_y": float(y2),
    }


def _response_text(response):
    return {
        "output": [
            {
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(response, ensure_ascii=False),
                    }
                ]
            }
        ]
    }


class CoffeeToGoLaneInferenceTests(unittest.TestCase):
    @staticmethod
    def production_rows():
        return pd.DataFrame(
            [
                _ocr_row("Body", 119.0, 361.4, 235.8, 422.1),
                _ocr_row("Legs", 835.6, 363.7, 943.4, 424.3),
                _ocr_row("<light brown yarn>", 125.8, 424.3, 449.2, 469.2),
                _ocr_row("<Dark brown yarn>", 837.8, 419.8, 1199.4, 473.7),
                _ocr_row(
                    "Start with 8sc in a Magic ring, slst (8)",
                    123.5,
                    473.7,
                    734.5,
                    518.6,
                ),
                _ocr_row("Start from 4ch", 837.8, 480.4, 1107.3, 525.3),
                _ocr_row("R1-left", 125.8, 527.6, 449.2, 565.7),
                _ocr_row("R1-right", 840.0, 536.6, 1513.9, 581.5),
                _ocr_row("R2-left", 123.5, 572.5, 552.5, 617.4),
                _ocr_row("R2-right", 840.0, 590.4, 1185.9, 635.3),
                _ocr_row("R3-left", 125.8, 626.4, 570.5, 664.5),
                _ocr_row("R3-right", 840.0, 646.6, 1347.7, 684.7),
                _ocr_row("R4-left", 125.8, 675.7, 572.8, 716.2),
                _ocr_row("R4-right", 840.0, 700.4, 1394.8, 747.6),
                _ocr_row("R5-8-left", 125.8, 727.4, 494.1, 765.5),
                _ocr_row("R5-7-right", 840.0, 754.3, 1194.9, 801.5),
                _ocr_row("R9-left", 125.8, 776.8, 570.5, 814.9),
                _ocr_row("R10-13-left", 125.8, 823.9, 523.3, 862.1),
                _ocr_row("Strap", 831.1, 859.8, 961.3, 924.9),
                _ocr_row("R14-left", 125.8, 875.6, 579.5, 913.7),
                _ocr_row("R15-22-left", 121.3, 920.4, 527.8, 967.6),
                _ocr_row("<Light brown yarn>", 842.3, 924.9, 1199.4, 972.1),
                _ocr_row("Chains as long as you like", 842.3, 978.8, 1302.7, 1026.0),
                _ocr_row("Cover", 119.0, 1021.5, 251.6, 1075.4),
                _ocr_row("Turn and slst until the end", 840.0, 1037.2, 1325.2, 1075.4),
            ]
        )

    def test_production_cross_column_pairs_become_independent_visual_lines(self):
        merged = ocr_lines.merge_ocr_boxes_into_visual_lines(self.production_rows())
        texts = merged["text"].tolist()

        self.assertEqual(25, len(merged))
        for left, right in (
            ("Start with 8sc in a Magic ring, slst (8)", "Start from 4ch"),
            ("R2-left", "R2-right"),
            ("R3-left", "R3-right"),
            ("R9-left", "R5-7-right"),
            ("R14-left", "Strap"),
        ):
            with self.subTest(left=left, right=right):
                self.assertIn(left, texts)
                self.assertIn(right, texts)
                self.assertNotIn(f"{left} {right}", texts)

        left_order = [
            text
            for text in texts
            if text.endswith("-left")
        ]
        right_order = [
            text
            for text in texts
            if text.endswith("-right")
        ]
        self.assertEqual(
            [
                "R1-left",
                "R2-left",
                "R3-left",
                "R4-left",
                "R5-8-left",
                "R9-left",
                "R10-13-left",
                "R14-left",
                "R15-22-left",
            ],
            left_order,
        )
        self.assertEqual(
            ["R1-right", "R2-right", "R3-right", "R4-right", "R5-7-right"],
            right_order,
        )

        segments, _segment_rows = broad_translation.build_source_segments(
            merged.assign(semantic_text=merged["text"])
        )
        segment_texts = [segment["text"] for segment in segments]
        self.assertEqual(texts, segment_texts)
        self.assertTrue(all(len(members) == 1 for members in merged["Member Boxes"]))

    def test_same_lane_fragmented_round_still_merges(self):
        rows = self.production_rows()
        rows = rows[rows["text"] != "R2-left"].copy()
        rows = pd.concat(
            [
                rows,
                pd.DataFrame(
                    [
                        _ocr_row("R2:", 123.5, 572.5, 190.0, 617.4),
                        _ocr_row("ch, (sc, inc)x8, slst", 200.0, 573.0, 500.0, 617.0),
                        _ocr_row("(24)", 510.0, 573.2, 552.5, 616.8),
                    ]
                ),
            ],
            ignore_index=True,
        )

        merged = ocr_lines.merge_ocr_boxes_into_visual_lines(rows)
        texts = merged["text"].tolist()

        self.assertIn("R2: ch, (sc, inc)x8, slst (24)", texts)
        self.assertIn("R2-right", texts)
        row = merged.loc[merged["text"] == "R2: ch, (sc, inc)x8, slst (24)"].iloc[0]
        self.assertEqual(3, len(row["Member Boxes"]))

    def test_single_column_indents_and_dense_rows_retain_existing_grouping(self):
        rows = []
        for index in range(8):
            y = 40.0 + index * 55.0
            start = 210.0 if index == 4 else 100.0
            rows.append(_ocr_row(f"R{index + 1}:", start, y, start + 70.0, y + 30.0))
            rows.append(
                _ocr_row(
                    f"instruction-{index + 1}",
                    start + 82.0,
                    y + 1.0,
                    start + 430.0,
                    y + 31.0,
                )
            )

        merged = ocr_lines.merge_ocr_boxes_into_visual_lines(pd.DataFrame(rows))

        self.assertEqual(8, len(merged))
        self.assertEqual(
            [f"R{index}: instruction-{index}" for index in range(1, 9)],
            merged["text"].tolist(),
        )
        self.assertTrue(all(len(members) == 2 for members in merged["Member Boxes"]))

    def test_full_width_spanner_and_isolated_pair_do_not_create_lanes(self):
        production = pd.concat(
            [
                self.production_rows(),
                pd.DataFrame(
                    [_ocr_row("Coffee-to-go Pattern", 208.9, 134.7, 1406.1, 276.1)]
                ),
            ],
            ignore_index=True,
        )
        probe = production.copy()
        probe["_cy"] = (probe["min_y"] + probe["max_y"]) / 2.0
        probe["_h"] = probe["max_y"] - probe["min_y"]
        lane_assignments = ocr_lines._infer_confident_reading_lanes(
            probe,
            median_height=float(probe["_h"].median()),
        )
        title_index = int(probe.index[probe["text"] == "Coffee-to-go Pattern"][0])
        self.assertNotIn(title_index, lane_assignments)

        merged = ocr_lines.merge_ocr_boxes_into_visual_lines(production)
        title = merged.loc[merged["text"] == "Coffee-to-go Pattern"].iloc[0]
        self.assertEqual(1, len(title["Member Boxes"]))

        isolated = pd.DataFrame(
            [
                _ocr_row("left", 100.0, 20.0, 300.0, 55.0),
                _ocr_row("paired annotation", 480.0, 21.0, 650.0, 56.0),
                *[
                    _ocr_row(
                        f"single-{index}",
                        100.0,
                        100.0 + index * 50.0,
                        500.0,
                        135.0 + index * 50.0,
                    )
                    for index in range(6)
                ],
            ]
        )
        isolated_merged = ocr_lines.merge_ocr_boxes_into_visual_lines(isolated)
        self.assertIn("left paired annotation", isolated_merged["text"].tolist())

    def test_fake_broad_receives_separate_segments_and_overlay_has_no_false_footer(self):
        merged = ocr_lines.merge_ocr_boxes_into_visual_lines(self.production_rows())
        semantic_rows = merged.assign(semantic_text=merged["text"])
        segments, _segment_rows = broad_translation.build_source_segments(semantic_rows)
        translations = {
            segment["source_segment_id"]: f"翻译{index}"
            for index, segment in enumerate(segments)
        }
        source_by_id = {
            segment["source_segment_id"]: segment["text"] for segment in segments
        }
        for source_id, source in source_by_id.items():
            if source == "R3-left":
                translations[source_id] = (
                    "第3圈：锁针，（2个短针，加针）×8，引拔针（32）"
                )
            elif source == "R3-right":
                translations[source_id] = (
                    "第3圈：锁针，3个短针，2次减针，4个短针，引拔针（9）"
                )

        captured_segments = []

        def caller(prompt, api_key):
            self.assertEqual("test-key", api_key)
            payload = json.loads(prompt.split("INPUT: ", 1)[1])
            captured_segments.extend(payload["source_segments"])
            assignments = {}
            units = {}
            for index, segment in enumerate(payload["source_segments"]):
                unit_id = f"unit-{index:04d}"
                source_id = segment["source_segment_id"]
                assignments[source_id] = unit_id
                units[unit_id] = {"translated_text": translations[source_id]}
            return _response_text(
                {"segment_assignments": assignments, "semantic_units": units}
            ), 0.01

        line_df = broad_translation.translate_merged_ocr_lines_broad(
            semantic_rows,
            "English — US",
            "Simplified Chinese",
            environ={"OPENAI_API_KEY": "test-key"},
            luna_caller=mock.Mock(side_effect=caller),
        )

        captured_texts = [segment["text"] for segment in captured_segments]
        self.assertIn("R3-left", captured_texts)
        self.assertIn("R3-right", captured_texts)
        self.assertNotIn("R3-left R3-right", captured_texts)
        self.assertEqual(len(segments), len(line_df))

        with mock.patch.dict(
            os.environ,
            {overlay.SOURCE_REPLACEMENT_FLAG_ENV: "1"},
            clear=False,
        ):
            image, _legend, _legend_df = overlay.make_line_translation_overlay(
                Image.new("RGB", (1588, 1120), "white"),
                line_df,
                "Simplified Chinese",
            )

        self.assertIsNotNone(image)
        r3_rows = line_df[line_df["Original"].isin(("R3-left", "R3-right"))]
        self.assertEqual(["", ""], r3_rows["Overlay Marker"].tolist())
        self.assertEqual(0, line_df.attrs["overlay_renderer_diagnostics"]["footer_height"])


if __name__ == "__main__":
    unittest.main()
