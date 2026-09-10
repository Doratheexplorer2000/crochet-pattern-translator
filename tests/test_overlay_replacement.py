import os
import unittest
from unittest import mock

import pandas as pd
from PIL import Image, ImageDraw

from pattern_translator.engine import broad_translation
from pattern_translator.engine import diagnostic_report
from pattern_translator.engine import line_translation
from pattern_translator.engine import ocr_lines
from pattern_translator.engine import overlay
from pattern_translator.engine import pattern_document


class GeometryMetadataTests(unittest.TestCase):
    def test_visual_line_retains_ordered_member_boxes(self):
        rows = pd.DataFrame(
            [
                {"text": "R1:", "confidence": 0.98, "min_x": 10, "max_x": 45, "min_y": 20, "max_y": 40},
                {"text": "6 sc", "confidence": 0.97, "min_x": 50, "max_x": 105, "min_y": 21, "max_y": 41},
            ]
        )
        merged = ocr_lines.merge_ocr_boxes_into_visual_lines(rows)

        self.assertEqual(1, len(merged))
        self.assertEqual("visual-0000", merged.loc[0, "Visual Line ID"])
        self.assertEqual(0, merged.loc[0, "Reading Order"])
        members = merged.loc[0, "Member Boxes"]
        self.assertEqual(["R1:", "6 sc"], [member["text"] for member in members])
        self.assertEqual((10.0, 105.0, 20.0, 41.0), (
            merged.loc[0, "min_x"], merged.loc[0, "max_x"],
            merged.loc[0, "min_y"], merged.loc[0, "max_y"],
        ))

    def test_broad_semantic_unit_retains_ordered_source_regions(self):
        rows = ocr_lines.merge_ocr_boxes_into_visual_lines(
            pd.DataFrame(
                [
                    {"text": "R6: 11 sc BOB", "confidence": 0.98, "min_x": 10, "max_x": 190, "min_y": 20, "max_y": 42},
                    {"text": "BOB 8 sc (24)", "confidence": 0.97, "min_x": 10, "max_x": 175, "min_y": 48, "max_y": 70},
                ]
            )
        )
        segments, segment_rows = broad_translation.build_source_segments(rows)
        result = broad_translation.adapt_semantic_units_to_line_df(
            [
                {
                    "semantic_unit_id": "unit-0000",
                    "source_segment_ids": ["segment-0000", "segment-0001"],
                    "translation": "第6圈：泡芙針，共24針",
                    "validation_status": "validated",
                    "validation_failure_reason": "",
                }
            ],
            segments,
            segment_rows,
        )

        regions = result.loc[0, "Source Regions"]
        self.assertEqual(2, len(regions))
        self.assertEqual(("segment-0000", "segment-0001"), result.loc[0, "Source Segment IDs"])
        self.assertEqual(("visual-0000", "visual-0001"), result.loc[0, "Visual Line IDs"])
        self.assertEqual([0, 1], [region["reading_order"] for region in regions])


class ContentClassificationTests(unittest.TestCase):
    def test_translatable_text_and_protected_identity_are_distinguished(self):
        self.assertEqual("translated_content", pattern_document.classify_overlay_content("R1: 6 sc"))
        self.assertEqual("translated_content", pattern_document.classify_overlay_content("#crochet #cute"))
        self.assertEqual("translated_content", pattern_document.classify_overlay_content("Sunny Day"))
        self.assertEqual("translated_content", pattern_document.classify_overlay_content("all rights reserved"))
        self.assertEqual("protected_identity", pattern_document.classify_overlay_content("@crochetby_fosi"))
        self.assertEqual(
            "mixed_protected_translation",
            pattern_document.classify_overlay_content("@crochetby_fosi all rights reserved"),
        )
        self.assertEqual("unchanged_numeric", pattern_document.classify_overlay_content("6262"))
        self.assertEqual(
            "translated_content",
            pattern_document.classify_overlay_content(
                "Insert the safety eyes and glue them on.",
                near_pattern_content=True,
            ),
        )

    def test_copyright_owner_and_year_are_protected_spans(self):
        spans = pattern_document.protected_identity_spans("© Jane Smith 2026")
        self.assertEqual(
            ["©", "Jane Smith", "2026"],
            [span["text"] for span in spans],
        )
        self.assertEqual(
            "protected_identity",
            pattern_document.classify_overlay_content("© Jane Smith 2026"),
        )

    def test_penguin_prose_does_not_create_false_account_identity_spans(self):
        cases = (
            (
                "Insert the safety eyes into the middle of the white BOBs (I like to\n"
                "glue them on so that they aren't indented into the plushie)",
                "將安全眼插入白色棗形針的中央（我喜歡把它們黏上去，這樣它們就不會凹進玩偶裡）",
            ),
            (
                "*Optional: sew on the nose between the middle of the eyes, one row\n"
                "down (or do it at the end)",
                "*可選：將鼻子縫在兩眼中央之間、往下 1 行的位置（或在最後再做）",
            ),
        )
        for original, translated in cases:
            with self.subTest(original=original):
                self.assertEqual((), pattern_document.protected_identity_spans(original))
                rows = pd.DataFrame(
                    [{"Original": original, "Translation": translated}]
                )
                annotated = pattern_document.annotate_overlay_content(rows)
                self.assertEqual("translated_content", annotated.loc[0, "Content Category"])
                self.assertEqual("trusted", annotated.loc[0, "Translation Trust"])
                self.assertEqual(0, annotated.loc[0, "Protected Identity Span Count"])
                self.assertEqual((), annotated.loc[0, "Protected Identity Spans"])

    def test_account_prefix_requires_a_real_word_boundary(self):
        for ordinary in (
            "middle",
            "the middle of the white BOBs",
            "Bobble stitch",
            "Optional Crochet Pattern",
        ):
            with self.subTest(ordinary=ordinary):
                self.assertEqual(
                    (), pattern_document.protected_identity_spans(ordinary)
                )

        account_span = pattern_document.protected_identity_spans(
            "Account: alice_123"
        )
        self.assertEqual(
            [("alice_123", "account_id")],
            [(span["text"], span["kind"]) for span in account_span],
        )


class OverlayFontResolverTests(unittest.TestCase):
    def setUp(self):
        overlay._resolve_overlay_font.cache_clear()

    def tearDown(self):
        overlay._resolve_overlay_font.cache_clear()

    @staticmethod
    def _fake_font(family, weight):
        font = mock.Mock()
        font.getname.return_value = (family, weight)
        return font

    def test_linux_noto_ttc_faces_are_language_aware(self):
        cases = (
            ("Traditional Chinese", 3, "Noto Sans CJK TC"),
            ("Simplified Chinese", 2, "Noto Sans CJK SC"),
            ("Japanese", 0, "Noto Sans CJK JP"),
            ("English", 0, "Noto Sans CJK JP"),
        )
        noto = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
        for language, expected_index, expected_family in cases:
            with self.subTest(language=language):
                font = self._fake_font(expected_family, "Regular")
                with mock.patch.object(
                    overlay.ImageFont,
                    "truetype",
                    return_value=font,
                ) as truetype:
                    resolution = overlay._resolve_overlay_font(24, language)
                truetype.assert_called_once_with(
                    noto,
                    size=24,
                    index=expected_index,
                )
                self.assertEqual(expected_index, resolution.face_index)
                self.assertEqual(expected_family, resolution.family)
                self.assertEqual("Regular", resolution.weight)

    def test_macos_fallback_mapping(self):
        cases = (
            ("Traditional Chinese", "STHeiti Medium.ttc", 0, "Heiti TC", "Medium"),
            ("Simplified Chinese", "Hiragino Sans GB.ttc", 0, "Hiragino Sans GB", "W3"),
            ("Japanese", "ヒラギノ角ゴシック W3.ttc", 0, "Hiragino Sans", "W3"),
            ("English", "Arial.ttf", 0, "Arial", "Regular"),
        )
        for language, filename, expected_index, family, weight in cases:
            with self.subTest(language=language):
                def load(path, *, size, index):
                    if path.endswith(filename):
                        return self._fake_font(family, weight)
                    raise OSError(path)

                with mock.patch.object(
                    overlay.ImageFont,
                    "truetype",
                    side_effect=load,
                ):
                    resolution = overlay._resolve_overlay_font(24, language)
                self.assertTrue(resolution.path.endswith(filename))
                self.assertEqual(expected_index, resolution.face_index)
                self.assertEqual(family, resolution.family)
                self.assertEqual(weight, resolution.weight)

    def test_traditional_chinese_candidate_does_not_use_japanese_noto_face(self):
        noto_candidates = [
            candidate
            for candidate in overlay._overlay_font_candidates("Traditional Chinese")
            if candidate[0].endswith("NotoSansCJK-Regular.ttc")
        ]
        self.assertEqual(1, len(noto_candidates))
        self.assertEqual(3, noto_candidates[0][1])

    def test_six_pixels_renders_for_each_local_scalable_mapping(self):
        samples = {
            "Traditional Chinese": "繁體中文",
            "Simplified Chinese": "简体中文",
            "Japanese": "日本語",
            "English": "English",
        }
        draw = ImageDraw.Draw(Image.new("RGB", (100, 30), "white"))
        for language, text in samples.items():
            with self.subTest(language=language):
                resolution = overlay._resolve_overlay_font(6, language)
                bbox = draw.textbbox((0, 0), text, font=resolution.font)
                self.assertGreater(bbox[2] - bbox[0], 0)
                self.assertGreater(bbox[3] - bbox[1], 0)

    def test_source_height_calibrates_actual_glyph_metrics(self):
        draw = ImageDraw.Draw(Image.new("RGB", (400, 120), "white"))
        size_30, resolution_30, height_30 = overlay._source_calibrated_font_size(
            draw,
            "繁體中文翻譯",
            30,
            "Traditional Chinese",
        )
        size_50, _resolution_50, height_50 = overlay._source_calibrated_font_size(
            draw,
            "繁體中文翻譯",
            50,
            "Traditional Chinese",
        )
        self.assertLessEqual(height_30, 31)
        self.assertNotEqual(36, size_30)
        self.assertGreater(size_50, size_30)
        self.assertLessEqual(height_50, 51)
        self.assertEqual("Traditional Chinese", resolution_30.target_language)

    def test_member_height_median_ignores_multiline_union(self):
        regions = [
            {
                "min_y": 10,
                "max_y": 110,
                "member_boxes": (
                    {"min_y": 10, "max_y": 20},
                    {"min_y": 90, "max_y": 102},
                ),
            }
        ]
        self.assertEqual(11, overlay._representative_source_text_height(regions))

    def test_progressive_candidates_include_every_integer_through_six(self):
        self.assertEqual(
            tuple(range(14, 5, -1)),
            overlay._replacement_font_candidates(14, 6),
        )


class SourceReplacementRendererTests(unittest.TestCase):
    def setUp(self):
        overlay._resolve_overlay_font.cache_clear()
        self.flag = mock.patch.dict(
            os.environ,
            {overlay.SOURCE_REPLACEMENT_FLAG_ENV: "1"},
            clear=False,
        )
        self.flag.start()

    def tearDown(self):
        self.flag.stop()
        overlay._resolve_overlay_font.cache_clear()

    @staticmethod
    def _row(original, translated, *, x1=20, x2=300, y1=20, y2=60, **extra):
        return {
            "Original": original,
            "Translation": translated,
            "Confidence": 0.99,
            "min_x": float(x1),
            "max_x": float(x2),
            "min_y": float(y1),
            "max_y": float(y2),
            **extra,
        }

    def test_default_flag_is_off(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(overlay.is_source_replacement_overlay_enabled())

    def test_direct_replacement_has_no_footer_and_preserves_dimensions(self):
        rows = pd.DataFrame([self._row("R1: 6X", "R1: 6 sc")])
        image, legend, legend_df = overlay.make_line_translation_overlay(
            Image.new("RGB", (600, 240), "white"), rows, "English — US"
        )

        self.assertEqual((600, 240), image.size)
        self.assertIn(rows.loc[0, "Overlay State"], {"replacement", "expanded_replacement"})
        self.assertEqual("", rows.loc[0, "Overlay Marker"])
        self.assertEqual(
            rows.attrs["overlay_renderer_diagnostics"]["units"][0][
                "baseline_font_size"
            ],
            rows.loc[0, "Overlay Font Size"],
        )
        self.assertEqual(0, rows.attrs["overlay_renderer_diagnostics"]["footer_height"])
        self.assertEqual("", legend_df.loc[0, "Marker"])
        self.assertIn("R1: 6 sc", legend)
        self.assertNotIn((255, 80, 80), set(image.getdata()))

    def test_expanded_replacement_stays_source_anchored(self):
        rows = pd.DataFrame(
            [
                self._row(
                    "R3: (X,V)*6",
                    "R3: repeat sc inc six times",
                    x1=20,
                    x2=180,
                    y1=20,
                    y2=60,
                )
            ]
        )

        image, _legend, _legend_df = overlay.make_line_translation_overlay(
            Image.new("RGB", (600, 200), "white"), rows, "English — US"
        )

        self.assertEqual("expanded_replacement", rows.loc[0, "Overlay State"])
        self.assertGreater(rows.loc[0, "Overlay Expansion X"], 4.0)
        self.assertEqual((600, 200), image.size)
        self.assertEqual("", rows.loc[0, "Overlay Marker"])

    def test_progressive_fit_uses_first_readable_font_that_fits(self):
        rows = pd.DataFrame(
            [
                self._row(
                    "3. [sc, inc] x 6 (18)",
                    "3. [短針，加針] x 6（18）",
                    x1=100,
                    x2=320,
                    y1=80,
                    y2=112,
                ),
                self._row(
                    "@same_row_neighbor",
                    "@same_row_neighbor",
                    x1=486,
                    x2=720,
                    y1=75,
                    y2=120,
                ),
            ]
        )

        image, _legend, _legend_df = overlay.make_line_translation_overlay(
            Image.new("RGB", (1080, 260), "white"),
            rows,
            "Traditional Chinese",
        )

        self.assertIsNotNone(image)
        self.assertEqual("expanded_replacement", rows.loc[0, "Overlay State"])
        self.assertEqual(33, rows.loc[0, "Overlay Font Size"])
        self.assertEqual(6, rows.loc[0, "Overlay Minimum Font Size"])

    def test_fit_below_old_relative_minimum_uses_safe_smaller_size(self):
        rows = pd.DataFrame(
            [
                self._row(
                    "R2: 6 inc (12)",
                    "R2：6 加針（12）",
                    x1=100,
                    x2=200,
                    y1=80,
                    y2=112,
                ),
                self._row(
                    "@same_row_neighbor",
                    "@same_row_neighbor",
                    x1=340,
                    x2=600,
                    y1=75,
                    y2=120,
                ),
            ]
        )

        image, _legend, _legend_df = overlay.make_line_translation_overlay(
            Image.new("RGB", (1080, 260), "white"),
            rows,
            "Traditional Chinese",
        )

        self.assertIsNotNone(image)
        self.assertEqual("expanded_replacement", rows.loc[0, "Overlay State"])
        self.assertEqual(6, rows.loc[0, "Overlay Minimum Font Size"])
        self.assertLess(rows.loc[0, "Overlay Font Size"], 30)
        self.assertEqual("", rows.loc[0, "Overlay Marker"])

    def test_vertical_padding_reduces_for_tall_font_metrics_only(self):
        penguin_cases = {
            "R1": (35.1, 33, 1),
            "R3": (35.0, 33, 1),
            "R5": (36.0, 33, 1),
            "R6": (73.4, 68, 2),
            "R7-R8": (35.0, 33, 1),
            "safety-eyes": (73.4, 68, 2),
        }

        for row, (
            corridor_height,
            text_height,
            expected_padding,
        ) in penguin_cases.items():
            with self.subTest(row=row):
                self.assertEqual(
                    expected_padding,
                    overlay._bounded_vertical_padding(
                        corridor_height,
                        text_height,
                        preferred_padding=4 if text_height == 68 else 2,
                    ),
                )

        self.assertEqual(
            2,
            overlay._bounded_vertical_padding(35.1, 29, preferred_padding=2),
        )
        self.assertIsNone(
            overlay._bounded_vertical_padding(34.9, 33, preferred_padding=2)
        )
        self.assertEqual(1, overlay._MIN_VERTICAL_PLATE_PADDING)

    def test_tall_font_single_line_uses_padding_floor_without_overflow(self):
        rows = pd.DataFrame(
            [
                self._row("@above", "@above", x1=100, x2=500, y1=60, y2=99),
                self._row(
                    "R1: 6 sc in mr (6)",
                    "R1：環狀起針中織 6 短針（6）",
                    x1=102.6,
                    x2=299.2,
                    y1=100,
                    y2=130,
                ),
                self._row("@below", "@below", x1=100, x2=500, y1=135, y2=175),
            ]
        )

        image, _legend, _legend_df = overlay.make_line_translation_overlay(
            Image.new("RGB", (1080, 220), "white"),
            rows,
            "Traditional Chinese",
        )

        decision = rows.attrs["overlay_renderer_diagnostics"]["units"][1]
        self.assertIsNotNone(image)
        self.assertEqual("expanded_replacement", rows.loc[1, "Overlay State"])
        self.assertLessEqual(
            rows.loc[1, "Overlay Font Size"],
            rows.loc[1, "Overlay Calibrated Start Font Size"],
        )
        self.assertEqual(6, rows.loc[1, "Overlay Minimum Font Size"])
        self.assertGreaterEqual(decision["vertical_padding"], 1)
        self.assertLessEqual(
            decision["required_rendered_height"],
            decision["available_corridor_height"],
        )
        self.assertEqual("", rows.loc[1, "Overlay Marker"])

    def test_text_requiring_less_than_six_pixels_uses_real_overflow(self):
        rows = pd.DataFrame(
            [
                self._row(
                    "R1: 6 sc in mr (6)",
                    "R1：這是無法在六像素完整容納的翻譯",
                    x1=20,
                    x2=26,
                    y1=40,
                    y2=50,
                ),
                self._row("@neighbor", "@neighbor", x1=35, x2=500, y1=35, y2=60),
            ]
        )

        image, legend, legend_df = overlay.make_line_translation_overlay(
            Image.new("RGB", (600, 120), "white"),
            rows,
            "Traditional Chinese",
        )

        decision = rows.attrs["overlay_renderer_diagnostics"]["units"][1]
        self.assertGreater(image.height, 120)
        self.assertEqual("overflow", rows.loc[0, "Overlay State"])
        self.assertEqual(6, decision["final_font_size"])
        self.assertEqual("[1]", rows.loc[0, "Overlay Marker"])
        self.assertEqual("[1]", legend_df.loc[0, "Marker"])
        self.assertIn("R1：這是無法在六像素完整容納的翻譯", legend)

    def test_tall_font_compound_row_reduces_padding_without_overflow(self):
        regions = (
            {
                "source_segment_id": "segment-0000",
                "visual_line_id": "visual-0000",
                "reading_order": 0,
                "member_boxes": (),
                "min_x": 104.0,
                "max_x": 900.0,
                "min_y": 100.0,
                "max_y": 130.0,
            },
            {
                "source_segment_id": "segment-0001",
                "visual_line_id": "visual-0001",
                "reading_order": 1,
                "member_boxes": (),
                "min_x": 104.0,
                "max_x": 520.0,
                "min_y": 136.0,
                "max_y": 166.0,
            },
        )
        rows = pd.DataFrame(
            [
                self._row(
                    "R6 source line one\nR6 source line two",
                    "R6 translated line one and translated line two",
                    x1=104,
                    x2=900,
                    y1=100,
                    y2=166,
                    Source_Regions=regions,
                ),
                self._row(
                    "@below",
                    "@below",
                    x1=100,
                    x2=950,
                    y1=169.9,
                    y2=210,
                ),
            ]
        ).rename(columns={"Source_Regions": "Source Regions"})

        with mock.patch.object(
            overlay,
            "_wrap_text_unlimited",
            return_value=["R6 translated line one", "and translated line two"],
        ):
            image, _legend, _legend_df = overlay.make_line_translation_overlay(
                Image.new("RGB", (1080, 240), "white"),
                rows,
                "Traditional Chinese",
            )

        decision = rows.attrs["overlay_renderer_diagnostics"]["units"][0]
        self.assertIsNotNone(image)
        self.assertEqual("expanded_replacement", rows.loc[0, "Overlay State"])
        self.assertGreaterEqual(decision["vertical_padding"], 1)
        self.assertLessEqual(
            decision["required_rendered_height"],
            decision["available_corridor_height"],
        )
        self.assertEqual(73.4, decision["available_corridor_height"])
        self.assertEqual("", rows.loc[0, "Overlay Marker"])

    def test_single_line_fit_stops_before_neighboring_ocr_content(self):
        source = Image.new("RGB", (1080, 260), (245, 245, 245))
        ImageDraw.Draw(source).rectangle(
            (520, 70, 720, 125), fill=(20, 80, 130)
        )
        protected_before = source.crop((520, 70, 721, 126)).tobytes()
        rows = pd.DataFrame(
            [
                self._row(
                    "Starting with dark gray",
                    "從深灰色開始",
                    x1=100,
                    x2=405,
                    y1=80,
                    y2=114,
                ),
                self._row(
                    "@neighbor",
                    "@neighbor",
                    x1=520,
                    x2=720,
                    y1=70,
                    y2=125,
                ),
            ]
        )

        image, _legend, _legend_df = overlay.make_line_translation_overlay(
            source, rows, "Traditional Chinese"
        )

        self.assertEqual("replacement", rows.loc[0, "Overlay State"])
        self.assertEqual(
            rows.loc[0, "Overlay Calibrated Start Font Size"],
            rows.loc[0, "Overlay Font Size"],
        )
        self.assertEqual(34, rows.loc[0, "Overlay Source Text Height"])
        self.assertEqual(
            protected_before,
            image.crop((520, 70, 721, 126)).tobytes(),
        )

    def test_penguin_rows_use_safe_same_row_fitting_before_overflow(self):
        def region(segment, x1, x2, y1, y2, order):
            return {
                "source_segment_id": segment,
                "visual_line_id": segment.replace("segment", "visual"),
                "reading_order": order,
                "member_boxes": (),
                "min_x": x1,
                "max_x": x2,
                "min_y": y1,
                "max_y": y2,
            }

        safety_original = (
            "Insert the safety eyes into the middle of the white BOBs (I like to\n"
            "glue them on so that they aren't indented into the plushie)"
        )
        optional_original = (
            "*Optional: sew on the nose between the middle of the eyes, one row\n"
            "down (or do it at the end)"
        )
        rows = pd.DataFrame(
            [
                self._row("PATTERN", "花樣", x1=108.3, x2=282.1, y1=57.0, y2=92.6),
                self._row("HEAD AND BODY (with 5mm hook):", "頭部和身體（使用 5mm 鈎針）：", x1=105.4, x2=568.5, y1=156.8, y2=185.2),
                self._row("Starting with dark gray", "從深灰色開始", x1=104.0, x2=407.5, y1=226.6, y2=260.8),
                self._row("1. 6 sc in mr (6)", "R1：環狀起針中鉤 6 短針（6）", x1=102.6, x2=299.2, y1=262.2, y2=293.6),
                self._row("2.6 inc (12)", "R2：6 加針（12）", x1=104.0, x2=253.6, y1=297.8, y2=327.8),
                self._row("3. [sc, inc] x 6 (18)", "3. [短針，加針] x 6（18）", x1=105.4, x2=336.3, y1=334.9, y2=364.8),
                self._row("4. [2 sc, inc] x 6 (24)", "4. [2 短針，加針] x 6（24）", x1=104.0, x2=364.7, y1=369.1, y2=399.0),
                self._row("5.24 sc (24)", "R5：24 短針（24）", x1=104.0, x2=263.6, y1=404.7, y2=433.2),
                self._row(
                    "6. 11 sc, *CC to white* BOB, *CC to dark gray* 3sc, *CC to white*\nBOB, *CC to dark gray* 8 sc (24)",
                    "R6：11 短針，*配色換成白色* 棗形針，*配色換成深灰色* 3 短針，*配色換成白色* 棗形針，*配色換成深灰色* 8 短針（24）",
                    x1=105.4,
                    x2=933.2,
                    y1=440.3,
                    y2=504.4,
                    **{
                        "Source Regions": (
                            region("segment-0008", 105.4, 933.2, 440.3, 470.2, 8),
                            region("segment-0009", 105.4, 522.9, 476.0, 504.4, 9),
                        )
                    },
                ),
                self._row("7-8. (2 rounds) 24 sc (24)", "7-8.（2 圈）24 短針（24）", x1=105.4, x2=430.3, y1=510.2, y2=538.6),
                self._row("9. *CC to blue* 24 sc (24)", "9. *配色換成藍色* 24 短針（24）", x1=102.6, x2=433.1, y1=544.4, y2=575.7),
                self._row("10. *CC to purple* 24 sc (24)", "10. *配色換成紫色* 24 短針（24）", x1=105.4, x2=473.0, y1=582.8, y2=611.3),
                self._row(
                    safety_original,
                    "將安全眼插入白色棗形針的中央（我喜歡把它們黏上去，這樣它們就不會凹進玩偶裡）",
                    x1=104.0,
                    x2=941.8,
                    y1=651.2,
                    y2=718.2,
                    **{
                        "Source Regions": (
                            region("segment-0013", 104.0, 941.8, 651.2, 682.6, 13),
                            region("segment-0014", 104.0, 879.1, 686.8, 718.2, 14),
                        )
                    },
                ),
                self._row(
                    optional_original,
                    "*可選：將鼻子縫在兩眼中央之間、往下 1 行的位置（或在最後再做）",
                    x1=104.0,
                    x2=997.4,
                    y1=721.1,
                    y2=786.6,
                    **{
                        "Source Regions": (
                            region("segment-0015", 104.0, 997.4, 721.1, 755.2, 15),
                            region("segment-0016", 105.4, 448.8, 758.1, 786.6, 16),
                        )
                    },
                ),
                self._row("@crochetby_fosi all rights reserved", "@crochetby_fosi 保留所有權利", x1=233.7, x2=853.5, y1=1359.4, y2=1395.1),
            ]
        )

        image, _legend, _legend_df = overlay.make_line_translation_overlay(
            Image.new("RGB", (1080, 1425), "white"),
            rows,
            "Traditional Chinese",
        )

        self.assertIsNotNone(image)
        for position in (2, 3, 4, 5, 7, 9, 11):
            with self.subTest(original=rows.loc[position, "Original"]):
                self.assertNotEqual(
                    "overflow",
                    rows.loc[position, "Overlay State"],
                    rows.attrs["overlay_renderer_diagnostics"]["units"][position],
                )
                self.assertEqual("", rows.loc[position, "Overlay Marker"])
                self.assertGreaterEqual(rows.loc[position, "Overlay Font Size"], 6)
                self.assertLessEqual(
                    rows.loc[position, "Overlay Font Size"],
                    rows.loc[position, "Overlay Calibrated Start Font Size"],
                )
        self.assertEqual(
            "expanded_replacement",
            rows.loc[8, "Overlay State"],
            rows.attrs["overlay_renderer_diagnostics"]["units"][8],
        )
        for position in (12, 13):
            self.assertEqual("trusted", rows.loc[position, "Translation Trust"])
            self.assertNotEqual("warning_untrusted", rows.loc[position, "Overlay State"])
        self.assertEqual("trusted", rows.loc[14, "Translation Trust"])
        self.assertEqual("preserved", rows.loc[14, "Protected Identity Status"])

    def test_overflow_appends_new_canvas_and_keeps_original_bottom_pixel(self):
        source = Image.new("RGB", (320, 160), "white")
        ImageDraw.Draw(source).point((319, 159), fill=(11, 22, 33))
        translation = "R2: " + "very long complete translated instruction " * 8
        rows = pd.DataFrame([self._row("R2: 6V", translation, x2=105, y2=48)])

        with mock.patch.object(
            overlay,
            "_render_translation_footer",
            wraps=overlay._render_translation_footer,
        ) as render_footer:
            image, legend, legend_df = overlay.make_line_translation_overlay(
                source, rows, "English — US"
            )

        self.assertEqual(320, image.width)
        self.assertGreater(image.height, 160)
        self.assertEqual((11, 22, 33), image.getpixel((319, 159)))
        self.assertEqual("overflow", rows.loc[0, "Overlay State"])
        self.assertEqual("[1]", rows.loc[0, "Overlay Marker"])
        self.assertEqual("[1]", legend_df.loc[0, "Marker"])
        self.assertIn(translation.strip(), legend)
        self.assertEqual(
            160 + rows.attrs["overlay_renderer_diagnostics"]["footer_height"],
            image.height,
        )
        self.assertEqual(translation.strip(), render_footer.call_args.args[1][0]["text"])
        footer_font = render_footer.call_args.args[3]
        marker_font = render_footer.call_args.args[4]
        expected_family = rows.attrs["overlay_renderer_diagnostics"][
            "font_resolver"
        ]["font_family"]
        self.assertEqual(expected_family, footer_font.getname()[0])
        self.assertEqual(expected_family, marker_font.getname()[0])

    def test_pure_handle_is_unchanged_and_does_not_create_footer(self):
        source = Image.new("RGB", (600, 240), (30, 40, 50))
        rows = pd.DataFrame(
            [self._row("@crochetby_fosi", "@crochetby_fosi")]
        )
        image, legend, legend_df = overlay.make_line_translation_overlay(
            source, rows, "Traditional Chinese"
        )

        self.assertIsNone(image)
        self.assertEqual("", legend)
        self.assertTrue(legend_df.empty)
        self.assertEqual("preserved", rows.loc[0, "Overlay State"])
        self.assertEqual("protected_identity", rows.loc[0, "Content Category"])

    def test_title_hashtags_social_ui_and_rights_phrase_enter_replacement(self):
        cases = (
            ("快和我去救爷爷", "Hurry and come with me to rescue Grandpa."),
            ("#钩针 #手工钩织", "#crochet #handmade-crochet"),
            ("追蹤", "Follow"),
            ("all rights reserved", "保留所有權利"),
        )
        for original, translated in cases:
            with self.subTest(original=original):
                rows = pd.DataFrame([self._row(original, translated, x2=420)])
                image, _legend, _legend_df = overlay.make_line_translation_overlay(
                    Image.new("RGB", (700, 240), "white"),
                    rows,
                    "Traditional Chinese",
                )

                self.assertIsNotNone(image)
                self.assertEqual("translated_content", rows.loc[0, "Content Category"])
                self.assertIn(
                    rows.loc[0, "Overlay State"],
                    {"replacement", "expanded_replacement", "overflow"},
                )
                self.assertNotIn((255, 80, 80), set(image.getdata()))

    def test_numeric_engagement_count_remains_unchanged(self):
        source = Image.new("RGB", (500, 200), (41, 42, 43))
        rows = pd.DataFrame([self._row("6262", "6262")])

        image, legend, legend_df = overlay.make_line_translation_overlay(
            source, rows, "English — US"
        )

        self.assertIsNone(image)
        self.assertEqual("", legend)
        self.assertTrue(legend_df.empty)
        self.assertEqual("unchanged_numeric", rows.loc[0, "Content Category"])
        self.assertEqual("preserved", rows.loc[0, "Overlay State"])

    def test_mixed_handle_and_rights_phrase_translates_without_changing_handle(self):
        rows = pd.DataFrame(
            [
                self._row(
                    "@crochetby_fosi all rights reserved",
                    "@crochetby_fosi 保留所有權利",
                    x2=480,
                )
            ]
        )

        image, legend, _legend_df = overlay.make_line_translation_overlay(
            Image.new("RGB", (760, 240), "white"), rows, "Traditional Chinese"
        )

        self.assertIsNotNone(image)
        self.assertEqual("mixed_protected_translation", rows.loc[0, "Content Category"])
        self.assertEqual("preserved", rows.loc[0, "Protected Identity Status"])
        self.assertEqual("trusted", rows.loc[0, "Translation Trust"])
        self.assertIn("@crochetby_fosi 保留所有權利", legend)
        self.assertIn(
            rows.loc[0, "Overlay State"],
            {"replacement", "expanded_replacement", "overflow"},
        )

    def test_changed_or_missing_handle_is_untrusted_and_source_preserving(self):
        rows = pd.DataFrame(
            [
                self._row(
                    "@crochetby_fosi all rights reserved",
                    "@different_handle 保留所有權利",
                    x2=480,
                )
            ]
        )
        source = Image.new("RGB", (760, 280), (244, 244, 244))
        before = source.crop((20, 20, 480, 60)).tobytes()

        image, _legend, _legend_df = overlay.make_line_translation_overlay(
            source, rows, "Traditional Chinese"
        )

        self.assertEqual("untrusted", rows.loc[0, "Translation Trust"])
        self.assertEqual("missing_or_changed", rows.loc[0, "Protected Identity Status"])
        self.assertEqual("warning_untrusted", rows.loc[0, "Overlay State"])
        self.assertEqual(before, image.crop((20, 20, 480, 60)).tobytes())

    def test_untrusted_instruction_remains_visible_and_uses_one_marker_identity(self):
        source = Image.new("RGB", (600, 260), (245, 245, 245))
        rows = pd.DataFrame(
            [
                self._row(
                    "R99: ambiguous stitch",
                    "⚠ Could not translate reliably: R99: ambiguous stitch",
                    x2=220,
                    Validation_Status="unresolved",
                )
            ]
        ).rename(columns={"Validation_Status": "Validation Status"})
        before = source.crop((20, 20, 220, 60)).tobytes()

        image, _legend, legend_df = overlay.make_line_translation_overlay(
            source, rows, "English — US"
        )

        self.assertEqual(before, image.crop((20, 20, 220, 60)).tobytes())
        self.assertEqual("warning_untrusted", rows.loc[0, "Overlay State"])
        self.assertEqual("[1]", rows.loc[0, "Overlay Marker"])
        self.assertEqual("[1]", legend_df.loc[0, "Marker"])
        readable = line_translation.build_readable_line_translation(rows)
        self.assertTrue(readable.startswith("[1]\n"))
        self.assertGreater(image.height, 260)

    def test_long_row_blocked_by_neighbor_uses_overflow_not_floating_label(self):
        rows = pd.DataFrame(
            [
                self._row(
                    "R8: 3X",
                    "R8: " + "long structured translation " * 5,
                    x1=20,
                    x2=150,
                    y1=20,
                    y2=55,
                ),
                self._row(
                    "R9: 6X",
                    "R9: 6 sc",
                    x1=165,
                    x2=300,
                    y1=20,
                    y2=55,
                ),
            ]
        )
        image, _legend, _legend_df = overlay.make_line_translation_overlay(
            Image.new("RGB", (600, 220), "white"), rows, "English — US"
        )

        self.assertIsNotNone(image)
        self.assertEqual("overflow", rows.loc[0, "Overlay State"])
        self.assertEqual("[1]", rows.loc[0, "Overlay Marker"])
        self.assertNotEqual("full label", rows.loc[0, "Overlay State"])

    def test_filtered_branding_geometry_blocks_expansion_and_stays_unchanged(self):
        source = Image.new("RGB", (600, 220), "white")
        ImageDraw.Draw(source).rectangle((185, 15, 400, 65), fill=(31, 42, 53))
        protected_before = source.crop((185, 15, 401, 66)).tobytes()
        rows = pd.DataFrame(
            [
                self._row(
                    "R3: (X,V)*6",
                    "R3: " + "repeat sc inc six times " * 2,
                    x1=20,
                    x2=180,
                    y1=20,
                    y2=60,
                )
            ]
        )
        filtered_branding = pd.DataFrame(
            [
                {
                    "text": "@designer",
                    "min_x": 185.0,
                    "max_x": 400.0,
                    "min_y": 15.0,
                    "max_y": 65.0,
                }
            ]
        )

        image, _legend, _legend_df = overlay.make_line_translation_overlay(
            source,
            rows,
            "English — US",
            protected_ocr_rows=filtered_branding,
        )

        self.assertIn(
            rows.loc[0, "Overlay State"],
            {"replacement", "expanded_replacement", "overflow"},
        )
        self.assertEqual(
            protected_before,
            image.crop((185, 15, 401, 66)).tobytes(),
        )

    def test_marker_assignment_is_stable_reading_order_and_shared_by_outputs(self):
        rows = pd.DataFrame(
            [
                self._row(
                    "R9: 10X",
                    "R9: " + "complete long translation " * 5,
                    x1=20,
                    x2=120,
                    y1=80,
                    y2=110,
                ),
                self._row(
                    "R8: 3X",
                    "R8: " + "complete long translation " * 5,
                    x1=20,
                    x2=120,
                    y1=20,
                    y2=50,
                ),
            ]
        )

        _image, _legend, legend_df = overlay.make_line_translation_overlay(
            Image.new("RGB", (500, 180), "white"), rows, "English — US"
        )

        self.assertEqual("[2]", rows.loc[0, "Overlay Marker"])
        self.assertEqual("[1]", rows.loc[1, "Overlay Marker"])
        self.assertEqual(["[1]", "[2]"], legend_df["Marker"].tolist())
        readable = line_translation.build_readable_line_translation(rows)
        self.assertIn("[1]\nR8: 3X", readable)
        self.assertIn("[2]\nR9: 10X", readable)

    def test_multiline_semantic_unit_uses_retained_regions(self):
        regions = (
            {"source_segment_id": "segment-0000", "visual_line_id": "visual-0000", "reading_order": 0, "member_boxes": (), "min_x": 20, "max_x": 280, "min_y": 20, "max_y": 55},
            {"source_segment_id": "segment-0001", "visual_line_id": "visual-0001", "reading_order": 1, "member_boxes": (), "min_x": 20, "max_x": 280, "min_y": 65, "max_y": 100},
        )
        rows = pd.DataFrame(
            [
                self._row(
                    "R6: 11 sc BOB\nBOB 8 sc (24)",
                    "R6: work 11 sc, change colour, BOB, then 8 sc (24)",
                    x2=280,
                    y2=100,
                    Source_Regions=regions,
                    **{"Source Segment IDs": ("segment-0000", "segment-0001")},
                )
            ]
        ).rename(columns={"Source_Regions": "Source Regions"})

        image, _legend, _legend_df = overlay.make_line_translation_overlay(
            Image.new("RGB", (700, 260), "white"), rows, "English — US"
        )

        self.assertIsNotNone(image)
        decision = rows.attrs["overlay_renderer_diagnostics"]["units"][0]
        self.assertEqual(2, decision["source_region_count"])
        self.assertIn(rows.loc[0, "Overlay State"], {"replacement", "expanded_replacement", "overflow"})

    def test_kerry_hashtags_use_safe_compound_corridor_without_overflow(self):
        original = (
            "#钩针#钩针图解#手工钩织#钩针编织#钩针小物#钩针\n"
            "挂件#小鸭子#可爱#钩针教程#手工编织#钩针玩偶#手\n"
            "工#动物#手工伙伴"
        )
        translated = (
            "#crochet #crochetpattern #handcrochet #crocheting "
            "#crocheteditem #crochet #keychain #duckling #cute "
            "#crochettutorial #handmade #crochetdoll #handicraft "
            "#animal #handmadebuddy"
        )
        regions = (
            {"source_segment_id": "segment-0002", "visual_line_id": "visual-0002", "reading_order": 2, "member_boxes": (), "min_x": 36.0, "max_x": 1034.4, "min_y": 302.4, "max_y": 343.2},
            {"source_segment_id": "segment-0003", "visual_line_id": "visual-0003", "reading_order": 3, "member_boxes": (), "min_x": 38.4, "max_x": 1032.0, "min_y": 369.6, "max_y": 410.4},
            {"source_segment_id": "segment-0004", "visual_line_id": "visual-0004", "reading_order": 4, "member_boxes": (), "min_x": 33.6, "max_x": 391.2, "min_y": 436.8, "max_y": 487.2},
        )
        rows = pd.DataFrame(
            [
                self._row(
                    original,
                    translated,
                    x1=33.6,
                    x2=1034.4,
                    y1=302.4,
                    y2=487.2,
                    Source_Regions=regions,
                    **{
                        "Source Segment IDs": (
                            "segment-0002",
                            "segment-0003",
                            "segment-0004",
                        )
                    },
                ),
                self._row(
                    "@protected_next_row",
                    "@protected_next_row",
                    x1=33.6,
                    x2=175.2,
                    y1=578.4,
                    y2=621.6,
                ),
            ]
        ).rename(columns={"Source_Regions": "Source Regions"})
        source = Image.new("RGB", (1080, 700), (24, 25, 28))
        ImageDraw.Draw(source).rectangle(
            (33, 578, 176, 622), fill=(17, 88, 143)
        )
        protected_before = source.crop((33, 578, 177, 623)).tobytes()

        image, _legend, legend_df = overlay.make_line_translation_overlay(
            source, rows, "English — US"
        )

        decision = rows.attrs["overlay_renderer_diagnostics"]["units"][0]
        self.assertEqual("expanded_replacement", rows.loc[0, "Overlay State"])
        self.assertEqual("", rows.loc[0, "Overlay Marker"])
        self.assertGreater(
            rows.loc[0, "Overlay Calibrated Start Font Size"],
            36,
        )
        self.assertLess(
            rows.loc[0, "Overlay Font Size"],
            rows.loc[0, "Overlay Calibrated Start Font Size"],
        )
        self.assertGreaterEqual(rows.loc[0, "Overlay Wrapped Lines"], 3)
        self.assertEqual("accepted", decision["collision_decision"])
        self.assertEqual(0, rows.attrs["overlay_renderer_diagnostics"]["footer_height"])
        self.assertEqual("", legend_df.loc[0, "Marker"])
        self.assertEqual((1080, 700), image.size)
        self.assertEqual(
            protected_before,
            image.crop((33, 578, 177, 623)).tobytes(),
        )

    def test_compound_corridor_blocked_below_overflows_without_truncating(self):
        translated = " ".join(f"translated-word-{index}" for index in range(18))
        regions = (
            {"source_segment_id": "segment-0000", "visual_line_id": "visual-0000", "reading_order": 0, "member_boxes": (), "min_x": 20, "max_x": 280, "min_y": 20, "max_y": 55},
            {"source_segment_id": "segment-0001", "visual_line_id": "visual-0001", "reading_order": 1, "member_boxes": (), "min_x": 20, "max_x": 280, "min_y": 65, "max_y": 100},
        )
        rows = pd.DataFrame(
            [
                self._row(
                    "meaningful source line one\nmeaningful source line two",
                    translated,
                    x1=20,
                    x2=280,
                    y1=20,
                    y2=100,
                    Source_Regions=regions,
                ),
                self._row(
                    "@protected_neighbor",
                    "@protected_neighbor",
                    x1=20,
                    x2=300,
                    y1=112,
                    y2=152,
                ),
            ]
        ).rename(columns={"Source_Regions": "Source Regions"})
        source = Image.new("RGB", (700, 240), (230, 231, 232))
        ImageDraw.Draw(source).rectangle((20, 112, 300, 152), fill=(12, 70, 120))
        protected_before = source.crop((20, 112, 301, 153)).tobytes()

        with mock.patch.object(
            overlay,
            "_wrap_text_unlimited",
            return_value=["complete translated text"] * 100,
        ), mock.patch.object(
            overlay,
            "_render_translation_footer",
            wraps=overlay._render_translation_footer,
        ) as render_footer:
            image, _legend, _legend_df = overlay.make_line_translation_overlay(
                source, rows, "English — US"
            )

        decision = rows.attrs["overlay_renderer_diagnostics"]["units"][0]
        self.assertEqual("overflow", rows.loc[0, "Overlay State"])
        self.assertEqual("compound_corridor_height", rows.loc[0, "Overflow Reason"])
        self.assertEqual("[1]", rows.loc[0, "Overlay Marker"])
        self.assertGreater(decision["actual_wrapped_line_count"], decision["allowed_line_count"])
        self.assertEqual((20.0, 112.0, 300.0, 152.0), decision["blocking_protected_region"])
        self.assertEqual(translated, render_footer.call_args.args[1][0]["text"])
        self.assertEqual(
            protected_before,
            image.crop((20, 112, 301, 153)).tobytes(),
        )

    def test_kerry_rounds_title_mouth_and_social_text_remain_complete(self):
        fixture = (
            ("快和我去救爷爷", "Hurry and come with me to save Grandpa.", 230.4, 508.8, 182.4, 230.4),
            ("R1:6X", "R1: 6 sc", 33.6, 175.2, 578.4, 621.6),
            ("R2:6V", "R2: 6 inc", 28.8, 175.2, 640.8, 691.2),
            ("R3:(X，V)*6", "R3: (sc, inc) * 6", 31.2, 321.6, 708.0, 765.6),
            ("R4:18X", "R4: 18 sc", 33.6, 199.2, 789.6, 832.8),
            ("R5:(X，V,X)*6", "R5: (sc, inc, sc) * 6", 31.2, 384.0, 849.6, 904.8),
            ("R6~R7:24X", "R6–R7: 24 sc", 33.6, 285.6, 928.8, 969.6),
            ("R8：(3X,V)*2,(X，V)*4,(3X,V)*2", "R8: (3 sc, inc) * 2, (sc, inc) * 4, (3 sc, inc) * 2", 33.6, 825.6, 993.6, 1041.6),
            ("R9：10X,(X，V，X)*4,10X", "R9: 10 sc, (sc, inc, sc) * 4, 10 sc", 31.2, 600.0, 1063.2, 1113.6),
            ("R10:10X,(3X,V)*4,10X", "R10: 10 sc, (3 sc, inc) * 4, 10 sc", 31.2, 583.2, 1132.8, 1183.2),
            ("R11：10X，(2X，V,2X)*4,10X", "R11: 10 sc, (2 sc, inc, 2 sc) * 4, 10 sc", 33.6, 664.8, 1204.8, 1250.4),
            ("R12~R13: 44X", "R12–R13: 44 sc", 33.6, 331.2, 1272.0, 1320.0),
            ("R14：16X，A,8X，A,16X", "R14: 16 sc, dec, 8 sc, dec, 16 sc", 36.0, 542.4, 1348.8, 1392.0),
            ("R15~R16:42X", "R15–R16: 42 sc", 28.8, 333.6, 1411.2, 1464.0),
            ("R17:(5X,A)*6", "R17: (5 sc, dec) * 6", 33.6, 372.0, 1483.2, 1531.2),
            ("R18:(2X,A,2X)*6", "R18: (2 sc, dec, 2 sc) * 6", 33.6, 458.4, 1552.8, 1600.8),
            ("R19：(3X,A)*6", "R19: (3 sc, dec) * 6", 33.6, 369.6, 1622.4, 1672.8),
            ("R20:(X，A,X)*6", "R20: (sc, dec, sc) * 6", 33.6, 408.0, 1694.4, 1742.4),
            ("R21:(X，A)*6", "R21: (sc, dec) * 6", 33.6, 343.2, 1761.6, 1809.6),
            ("R22:6A", "R22: 6 dec", 33.6, 199.2, 1838.4, 1881.6),
            ("嘴巴：环起3X", "Mouth: magic ring 3 sc", 33.6, 288.0, 1972.8, 2020.8),
            ("說點什麼", "Say something.", 60.0, 271.2, 2169.6, 2229.6),
        )
        rows = pd.DataFrame(
            [
                self._row(
                    original,
                    translated,
                    x1=x1,
                    x2=x2,
                    y1=y1,
                    y2=y2,
                )
                for original, translated, x1, x2, y1, y2 in fixture
            ]
        )

        image, legend, _legend_df = overlay.make_line_translation_overlay(
            Image.new("RGB", (1080, 2400), (24, 25, 28)),
            rows,
            "English — US",
        )

        self.assertIsNotNone(image)
        self.assertNotIn("warning_untrusted", set(rows["Overlay State"]))
        self.assertNotIn("preserved_unsupported", set(rows["Overlay State"]))
        for translated in ("R1: 6 sc", "R22: 6 dec", "Mouth: magic ring 3 sc", "Say something."):
            self.assertIn(translated, legend)
        diagnostics = rows.attrs["overlay_renderer_diagnostics"]
        self.assertGreater(diagnostics["final_font_size_summary"]["maximum"], 30)
        self.assertGreaterEqual(diagnostics["final_font_size_summary"]["minimum"], 6)

    def test_complete_wrapper_reports_overflow_without_truncating(self):
        image = Image.new("RGB", (300, 100), "white")
        draw = ImageDraw.Draw(image)
        font = overlay._load_overlay_font(18)
        text = "one two three four five six seven eight nine ten"

        lines, complete = overlay._wrap_text_to_widths(text, draw, font, [70])
        unlimited = overlay._wrap_text_unlimited(text, draw, font, 70)

        self.assertFalse(complete)
        self.assertGreater(len(unlimited), len(lines))
        self.assertEqual(
            "".join(text.split()),
            "".join(" ".join(unlimited).split()),
        )

    def test_absolute_minimum_is_not_image_width_driven(self):
        self.assertEqual(6, overlay._ABSOLUTE_MIN_FONT_PX)
        self.assertEqual((8, 7, 6), overlay._replacement_font_candidates(8, 6))

    def test_whole_pattern_coordinates_are_used_without_offset(self):
        source = Image.new("RGB", (640, 300), (231, 232, 233))
        rows = pd.DataFrame(
            [self._row("R1: 6X", "R1: 6 sc", x1=300, x2=500, y1=120, y2=170)]
        )

        image, _legend, _legend_df = overlay.make_line_translation_overlay(
            source, rows, "English — US"
        )

        self.assertEqual((231, 232, 233), image.getpixel((20, 20)))
        self.assertNotEqual((231, 232, 233), image.getpixel((300, 120)))
        self.assertEqual((640, 300), image.size)

    def test_select_area_coordinates_remain_crop_local(self):
        crop = Image.new("RGB", (240, 180), (221, 222, 223))
        rows = pd.DataFrame(
            [self._row("R1: 6X", "R1: 6 sc", x1=20, x2=170, y1=30, y2=75)]
        )

        image, _legend, _legend_df = overlay.make_line_translation_overlay(
            crop, rows, "English — US", scale_to_source_text=True
        )

        self.assertEqual((221, 222, 223), image.getpixel((220, 150)))
        self.assertNotEqual((221, 222, 223), image.getpixel((20, 30)))
        self.assertEqual((240, 180), image.size)

    def test_renderer_diagnostics_are_in_downloadable_report(self):
        rows = pd.DataFrame([self._row("R1: 6X", "R1: 6 sc")])
        overlay.make_line_translation_overlay(
            Image.new("RGB", (600, 240), "white"), rows, "English — US"
        )

        report = diagnostic_report.build_debug_report_text(
            rows,
            overlay_renderer_diagnostics=rows.attrs["overlay_renderer_diagnostics"],
        )

        self.assertIn("=== Overlay Renderer Diagnostics ===", report)
        self.assertIn("Renderer: source_replacement", report)
        self.assertIn("Per-unit decisions:", report)
        self.assertIn("corridor=", report)
        self.assertIn("required=", report)
        self.assertIn("allowed_lines=", report)
        self.assertIn("actual_lines=", report)
        self.assertIn("blocker=", report)
        self.assertIn("absolute_minimum_font=", report)
        self.assertIn("source_height=", report)
        self.assertIn("calibrated_start=", report)
        self.assertIn("Font face index:", report)

    def test_diagnostics_distinguish_translation_identity_mixed_and_numeric(self):
        rows = pd.DataFrame(
            [
                self._row("快和我去救爷爷", "Rescue Grandpa", y1=20, y2=55),
                self._row("@designer_name", "@designer_name", y1=80, y2=115),
                self._row(
                    "@crochetby_fosi all rights reserved",
                    "@crochetby_fosi 保留所有權利",
                    y1=140,
                    y2=175,
                ),
                self._row("6262", "6262", y1=200, y2=235),
            ]
        )

        overlay.make_line_translation_overlay(
            Image.new("RGB", (700, 300), "white"), rows, "Traditional Chinese"
        )
        diagnostics = rows.attrs["overlay_renderer_diagnostics"]
        categories = [unit["content_category"] for unit in diagnostics["units"]]

        self.assertEqual(
            [
                "translated_content",
                "protected_identity",
                "mixed_protected_translation",
                "unchanged_numeric",
            ],
            categories,
        )
        mixed = diagnostics["units"][2]
        self.assertEqual(1, mixed["protected_identity_span_count"])
        self.assertEqual("preserved", mixed["protected_identity_status"])
        report = diagnostic_report.build_debug_report_text(
            rows,
            overlay_renderer_diagnostics=diagnostics,
        )
        self.assertIn("content=mixed_protected_translation", report)
        self.assertIn("protected_spans=1", report)
        self.assertIn("('@crochetby_fosi', 'handle')", report)
        self.assertIn("protected_status=preserved", report)


if __name__ == "__main__":
    unittest.main()
