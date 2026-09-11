import re
import csv
import importlib
import subprocess
import sys
import threading
import time
import types
import unittest
from contextvars import ContextVar
from pathlib import Path
from unittest import mock

import pandas as pd
from PIL import Image, ImageDraw

from pattern_translator.engine import line_translation as line_translation_engine
from pattern_translator.engine import overlay as overlay_engine
from pattern_translator.engine import result_delivery as result_delivery_engine
from pattern_translator.engine import terminology as terminology_engine
from pattern_translator.translation_service import (
    TranslateImageRequest,
    _TRANSLATION_PROFILE,
    _classify_image_quality,
    _main_text_height_metrics,
    assess_image_quality,
    get_quality_status,
    prepare_translation_dataframe,
    profile_count,
    translate_image,
)

_TEST_REQUEST_MARKER: ContextVar[str] = ContextVar("test_request_marker", default="")


class TranslationServiceImportTests(unittest.TestCase):
    def test_module_imports_without_streamlit(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                "import importlib; "
                "importlib.import_module('pattern_translator.translation_service'); "
                "import pathlib; "
                "source = pathlib.Path('pattern_translator/translation_service.py').read_text(encoding='utf-8'); "
                "assert 'import streamlit' not in source; "
                "assert 'from streamlit' not in source",
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr or completed.stdout)

    def test_translate_image_is_callable(self):
        from pattern_translator.translation_service import translate_image as imported

        self.assertTrue(callable(imported))

    def test_streamlit_delegates_to_shared_quality_assessment(self):
        app_source = (
            Path(__file__).resolve().parents[1] / "pattern_translator" / "app.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("def assess_image_quality(", app_source)
        self.assertNotIn("def get_quality_status(", app_source)
        self.assertIn("    assess_image_quality,", app_source)
        self.assertIn("    get_quality_status,", app_source)


class ImageQualityAssessmentTests(unittest.TestCase):
    @staticmethod
    def _component_image(
        width: int = 414,
        height: int = 394,
        component_height: int = 14,
        component_count: int = 30,
        tiny_count: int = 0,
    ) -> Image.Image:
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        columns = 5 if width < 300 else 10
        for index in range(component_count):
            box_height = 5 if index < tiny_count else component_height
            x = 15 + (index % columns) * 35
            y = 15 + (index // columns) * 35
            draw.rectangle(
                (x, y, x + 8, y + box_height - 1),
                outline="black",
                width=2,
            )
        return image

    def test_small_readable_crop_is_good_and_dimensions_do_not_control_status(self):
        errors, warnings, metrics = assess_image_quality(self._component_image())

        self.assertEqual("good", get_quality_status(errors, warnings)[0])
        self.assertEqual(414, metrics["assessment_width_px"])
        self.assertEqual(394, metrics["assessment_height_px"])
        self.assertGreaterEqual(metrics["main_text_height_px"], 10)
        self.assertTrue(metrics["main_text_height_reliable"])
        self.assertNotIn("pixel_count", metrics)

    def test_assessment_image_caps_longest_side_and_never_upscales(self):
        large = self._component_image(width=828, height=1104, component_count=60)
        small = self._component_image(width=414, height=394)

        large_metrics = assess_image_quality(large)[2]
        small_metrics = assess_image_quality(small)[2]

        self.assertEqual((750, 1000), (
            large_metrics["assessment_width_px"],
            large_metrics["assessment_height_px"],
        ))
        self.assertEqual((414, 394), (
            small_metrics["assessment_width_px"],
            small_metrics["assessment_height_px"],
        ))

    def test_tiny_main_text_is_poor(self):
        errors, warnings, reason = _classify_image_quality(120, 28, 6.9, True)
        self.assertEqual("poor", get_quality_status(errors, warnings)[0])
        self.assertEqual("main_text_too_small", reason)

    def test_severe_blur_is_poor_only_with_moderately_small_main_text(self):
        errors, warnings, reason = _classify_image_quality(4.9, 28, 17.9, True)
        self.assertEqual("poor", get_quality_status(errors, warnings)[0])
        self.assertEqual("severe_blur_with_small_main_text", reason)

        errors, warnings, reason = _classify_image_quality(4.9, 28, 18.0, True)
        self.assertEqual("fair", get_quality_status(errors, warnings)[0])
        self.assertEqual("low_sharpness", reason)

    def test_low_contrast_alone_is_fair(self):
        errors, warnings, reason = _classify_image_quality(120, 11.9, 14, True)
        self.assertEqual("fair", get_quality_status(errors, warnings)[0])
        self.assertEqual("low_contrast", reason)

    def test_unreliable_or_sparse_main_text_estimate_is_always_fair(self):
        sparse = _main_text_height_metrics([14.0] * 19)
        ambiguous = _main_text_height_metrics(
            ([5.0] * 5) + ([20.0] * 5) + ([50.0] * 5) + ([90.0] * 5)
        )
        self.assertFalse(sparse["main_text_height_reliable"])
        self.assertFalse(ambiguous["main_text_height_reliable"])

        for metrics in (sparse, ambiguous):
            errors, warnings, reason = _classify_image_quality(
                0,
                0,
                metrics["main_text_height_px"],
                bool(metrics["main_text_height_reliable"]),
            )
            self.assertEqual("fair", get_quality_status(errors, warnings)[0])
            self.assertEqual("unreliable_main_text_scale", reason)

    def test_isolated_tiny_components_do_not_override_dominant_text(self):
        metrics = _main_text_height_metrics(([5.0] * 5) + ([14.0] * 25))
        errors, warnings, reason = _classify_image_quality(
            120,
            28,
            metrics["main_text_height_px"],
            bool(metrics["main_text_height_reliable"]),
        )

        self.assertEqual(14.0, metrics["main_text_height_px"])
        self.assertTrue(metrics["main_text_height_reliable"])
        self.assertEqual("good", get_quality_status(errors, warnings)[0])
        self.assertEqual("main_text_readable", reason)

    def test_status_precedence_is_error_then_warning_then_good(self):
        self.assertEqual("poor", get_quality_status(["error"], ["warning"])[0])
        self.assertEqual("fair", get_quality_status([], ["warning"])[0])
        self.assertEqual("good", get_quality_status([], [])[0])

    def test_numpy_fallback_is_used_when_opencv_assessment_fails(self):
        image = Image.linear_gradient("L").resize((1500, 600)).convert("RGB")
        failing_cv2 = types.SimpleNamespace(
            COLOR_RGB2GRAY=1,
            cvtColor=mock.Mock(side_effect=RuntimeError("opencv failed")),
        )
        with mock.patch.dict(sys.modules, {"cv2": failing_cv2}):
            errors, warnings, metrics = assess_image_quality(image)

        failing_cv2.cvtColor.assert_called_once()
        self.assertEqual(1500, metrics["width_px"])
        self.assertEqual(600, metrics["height_px"])
        self.assertIsInstance(metrics["sharpness_score"], float)
        self.assertIsInstance(metrics["contrast_score"], float)
        self.assertFalse(metrics["main_text_height_reliable"])
        self.assertEqual("unreliable_main_text_scale", metrics["classification_reason"])
        self.assertEqual("fair", get_quality_status(errors, warnings)[0])


class OverlayScalingTests(unittest.TestCase):
    @staticmethod
    def _line_rows(height: float) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "Original": f"R{index}: 6X",
                    "Translation": f"R{index}: 6 sc",
                    "min_x": 10.0,
                    "max_x": 400.0,
                    "min_y": float(index * 100),
                    "max_y": float(index * 100) + height,
                }
                for index in range(1, 4)
            ]
        )

    def test_line_overlay_font_uses_source_geometry_only_for_select_area(self):
        normal_width = 1180
        camera_width = 4084
        camera_crop_width = 1038

        normal_size = overlay_engine.line_overlay_font_size(normal_width)
        camera_size = overlay_engine.line_overlay_font_size(camera_width)
        camera_crop_size = overlay_engine.line_overlay_font_size(
            camera_crop_width,
            self._line_rows(90),
            scale_to_source_text=True,
        )
        normal_photo_crop_size = overlay_engine.line_overlay_font_size(
            normal_width,
            self._line_rows(40),
            scale_to_source_text=True,
        )

        self.assertEqual(31, normal_size)
        self.assertEqual(107, camera_size)
        self.assertEqual(54, camera_crop_size)
        self.assertEqual(31, normal_photo_crop_size)
        self.assertAlmostEqual(
            normal_size / normal_width,
            camera_size / camera_width,
            delta=0.001,
        )

    @staticmethod
    def _marker_mapping_rows() -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "Original": "Long source one",
                    "Translation": "This translated instruction is deliberately longer than forty-two characters one.",
                    "min_x": 40.0,
                    "max_x": 180.0,
                    "min_y": 40.0,
                    "max_y": 70.0,
                },
                {
                    "Original": "Short source",
                    "Translation": "Short result",
                    "min_x": 40.0,
                    "max_x": 180.0,
                    "min_y": 180.0,
                    "max_y": 210.0,
                },
                {
                    "Original": "Unchanged",
                    "Translation": "Unchanged",
                    "min_x": 40.0,
                    "max_x": 180.0,
                    "min_y": 280.0,
                    "max_y": 310.0,
                },
                {
                    "Original": "Empty target",
                    "Translation": "",
                    "min_x": 40.0,
                    "max_x": 180.0,
                    "min_y": 330.0,
                    "max_y": 360.0,
                },
                {
                    "Original": "Long source two",
                    "Translation": "This second translated instruction is also deliberately longer than forty-two characters.",
                    "min_x": 40.0,
                    "max_x": 180.0,
                    "min_y": 400.0,
                    "max_y": 430.0,
                },
            ]
        )

    def test_renderer_markers_flow_to_readable_translation_and_txt(self):
        rows = self._marker_mapping_rows()
        originals_before = rows["Original"].tolist()
        translations_before = rows["Translation"].tolist()

        image, _legend, legend_df = overlay_engine.make_line_translation_overlay(
            Image.new("RGB", (1000, 520), "white"),
            rows,
            "English — US",
        )

        self.assertIsNotNone(image)
        self.assertEqual(["[1]", "", "", "", "[2]"], rows["Overlay Marker"].tolist())
        self.assertEqual(originals_before, rows["Original"].tolist())
        self.assertEqual(translations_before, rows["Translation"].tolist())
        self.assertEqual(
            [
                ("[1]", "Long source one", translations_before[0]),
                ("", "Short source", "Short result"),
                ("[2]", "Long source two", translations_before[4]),
            ],
            list(
                legend_df[["Marker", "Original", "Translation"]].itertuples(
                    index=False,
                    name=None,
                )
            ),
        )

        readable = line_translation_engine.build_readable_line_translation(rows)
        translation_txt = line_translation_engine.build_overlay_export_text(rows)
        self.assertIn(f"[1]\nLong source one\n→ {translations_before[0]}", readable)
        self.assertIn("Short source\n→ Short result", readable)
        self.assertNotIn("[2]\nShort source", readable)
        self.assertIn(f"[2]\nLong source two\n→ {translations_before[4]}", readable)
        self.assertEqual(readable + "\n", translation_txt)

    def test_overlay_marker_metadata_does_not_change_rendered_pixels(self):
        clean_rows = self._marker_mapping_rows()
        stale_rows = self._marker_mapping_rows()
        stale_rows["Overlay Marker"] = ["[99]"] * len(stale_rows)

        clean_image, clean_legend, clean_legend_df = overlay_engine.make_line_translation_overlay(
            Image.new("RGB", (1000, 520), "white"),
            clean_rows,
            "English — US",
        )
        stale_image, stale_legend, stale_legend_df = overlay_engine.make_line_translation_overlay(
            Image.new("RGB", (1000, 520), "white"),
            stale_rows,
            "English — US",
        )

        self.assertEqual(clean_image.tobytes(), stale_image.tobytes())
        self.assertEqual(clean_legend, stale_legend)
        pd.testing.assert_frame_equal(clean_legend_df, stale_legend_df)
        self.assertEqual(clean_rows["Overlay Marker"].tolist(), stale_rows["Overlay Marker"].tolist())


class TranslationProfileIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full_df = pd.read_csv("knowledge_base/data/master_stitches.csv").fillna("")
        cls.source_mode = "Traditional Chinese"
        cls.output_mode = "English — US"
        cls.df, cls.index = prepare_translation_dataframe(cls.full_df, cls.source_mode)

    def setUp(self):
        self.assertIsNone(_TRANSLATION_PROFILE.get())

    def tearDown(self):
        self.assertIsNone(_TRANSLATION_PROFILE.get())

    def _base_request(self, **overrides):
        image = Image.new("RGB", (1200, 800), color=(255, 255, 255))
        crop_box = (0, 0, image.size[0], image.size[1])
        values = {
            "image": image,
            "selected_image": image,
            "working_image": image,
            "source_mode": self.source_mode,
            "output_mode": self.output_mode,
            "area_mode": "Whole Pattern",
            "crop_box": crop_box,
            "df": self.df,
            "index": self.index,
            "diagnostic_request_id": "test-request",
            "diagnostic_session_generation": "test-session",
            "action_started": None,
            "image_load_seconds": 0.01,
            "crop_extraction_seconds": 0.02,
            "quality_metrics": {"width_px": 1200, "height_px": 800},
            "quality_errors": [],
            "quality_warnings": [],
            "quality_label": "Good",
            "experimental_downscale": False,
            "downscale_max_height_option": "Original / no resize",
            "ocr_resize_test": "1000 px",
            "session_diagnostics": {"ocr_started_at": "2026-01-01 00:00:00"},
            "diagnostic_events": [],
            "diagnostic_platform": "unit-test",
            "interface_language": "English",
        }
        values.update(overrides)
        return TranslateImageRequest(**values)

    def _ocr_rows(self):
        return pd.DataFrame(
            [
                {
                    "text": "R1: 6X",
                    "confidence": 0.99,
                    "x": 10.0,
                    "global_x": 10.0,
                    "y": 10.0,
                    "min_x": 0.0,
                    "max_x": 20.0,
                    "min_y": 0.0,
                    "max_y": 20.0,
                }
            ]
        )

    @mock.patch(
        "pattern_translator.translation_service.ocr_lines_engine.build_ocr_line_translations"
    )
    @mock.patch("pattern_translator.translation_service.run_primary_ocr")
    def test_concurrent_calls_do_not_share_profile_state(
        self, mock_run_primary_ocr, mock_build_lines
    ):
        overlap_barrier = threading.Barrier(2)
        observed_profiles = {}
        errors = []

        mock_run_primary_ocr.return_value = {
            "selected_name": "PaddleOCR",
            "selected_text": "R1: 6X",
            "selected_rows": self._ocr_rows(),
            "paddle_inference_seconds": 0.1,
        }

        def build_lines(*args, **kwargs):
            marker = _TEST_REQUEST_MARKER.get()
            profile_count(f"thread_marker::{marker}")
            overlap_barrier.wait(timeout=2)
            return pd.DataFrame(
                [
                    {
                        "Original": "R1: 6X",
                        "Translation": "R1: 6 sc",
                        "Confidence": 0.99,
                        "Changed": "✓",
                        "min_x": 0.0,
                        "max_x": 20.0,
                        "min_y": 0.0,
                        "max_y": 20.0,
                    }
                ]
            )

        mock_build_lines.side_effect = build_lines

        def run_request(thread_name: str, request_id: str):
            marker_token = _TEST_REQUEST_MARKER.set(thread_name)
            try:
                result = translate_image(
                    self._base_request(
                        diagnostic_request_id=request_id,
                        diagnostic_session_generation=thread_name,
                    )
                )
                observed_profiles[thread_name] = dict(
                    result.primary_result["translation_profile"]["counts"]
                )
            except Exception as error:
                errors.append(error)
            finally:
                _TEST_REQUEST_MARKER.reset(marker_token)

        first = threading.Thread(target=run_request, args=("thread-a", "request-a"))
        second = threading.Thread(target=run_request, args=("thread-b", "request-b"))
        first.start()
        second.start()
        first.join(timeout=5)
        second.join(timeout=5)

        self.assertEqual([], errors)
        self.assertEqual(1.0, observed_profiles["thread-a"]["thread_marker::thread-a"])
        self.assertEqual(1.0, observed_profiles["thread-b"]["thread_marker::thread-b"])
        self.assertNotIn("thread_marker::thread-b", observed_profiles["thread-a"])
        self.assertNotIn("thread_marker::thread-a", observed_profiles["thread-b"])
        self.assertIsNone(_TRANSLATION_PROFILE.get())

    @mock.patch("pattern_translator.translation_service.run_primary_ocr")
    def test_profile_context_cleared_after_success(self, mock_run_primary_ocr):
        mock_run_primary_ocr.return_value = {
            "selected_name": "PaddleOCR",
            "selected_text": "R1: 6X",
            "selected_rows": self._ocr_rows(),
            "paddle_inference_seconds": 0.1,
        }
        with mock.patch(
            "pattern_translator.translation_service.ocr_lines_engine.build_ocr_line_translations",
            return_value=pd.DataFrame(
                [
                    {
                        "Original": "R1: 6X",
                        "Translated": "R1: 6 sc",
                        "min_x": 0.0,
                        "max_x": 20.0,
                        "min_y": 0.0,
                        "max_y": 20.0,
                    }
                ]
            ),
        ):
            translate_image(self._base_request())
        self.assertIsNone(_TRANSLATION_PROFILE.get())

    @mock.patch("pattern_translator.translation_service.run_primary_ocr")
    def test_profile_context_cleared_after_exception(self, mock_run_primary_ocr):
        mock_run_primary_ocr.return_value = {
            "selected_name": "PaddleOCR",
            "selected_text": "R1: 6X",
            "selected_rows": self._ocr_rows(),
            "paddle_inference_seconds": 0.1,
        }
        with mock.patch(
            "pattern_translator.translation_service.ocr_lines_engine.build_ocr_line_translations",
            side_effect=RuntimeError("translation failed"),
        ):
            with self.assertRaises(RuntimeError):
                translate_image(self._base_request())
        self.assertIsNone(_TRANSLATION_PROFILE.get())


class PrimaryResultContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full_df = pd.read_csv("knowledge_base/data/master_stitches.csv").fillna("")
        cls.source_mode = "Traditional Chinese"
        cls.output_mode = "English — US"
        cls.df, cls.index = prepare_translation_dataframe(cls.full_df, cls.source_mode)

    def _base_request(self, **overrides):
        image = Image.new("RGB", (1200, 800), color=(255, 255, 255))
        crop_box = (0, 0, image.size[0], image.size[1])
        values = {
            "image": image,
            "selected_image": image,
            "working_image": image,
            "source_mode": self.source_mode,
            "output_mode": self.output_mode,
            "area_mode": "Whole Pattern",
            "crop_box": crop_box,
            "df": self.df,
            "index": self.index,
            "diagnostic_request_id": "contract-request",
            "diagnostic_session_generation": "contract-session",
            "action_started": time.perf_counter() - 0.5,
            "image_load_seconds": 0.01,
            "crop_extraction_seconds": 0.02,
            "quality_metrics": {"width_px": 1200, "height_px": 800},
            "quality_errors": [],
            "quality_warnings": [],
            "quality_label": "Good",
            "experimental_downscale": False,
            "downscale_max_height_option": "Original / no resize",
            "ocr_resize_test": "1000 px",
            "session_diagnostics": {"ocr_started_at": "2026-01-01 00:00:00"},
            "diagnostic_events": [{"event": "snapshot"}],
            "diagnostic_platform": "unit-test",
            "interface_language": "English",
            "ocr_execution_start": time.perf_counter() - 0.25,
        }
        values.update(overrides)
        return TranslateImageRequest(**values)

    @mock.patch("pattern_translator.translation_service.run_primary_ocr")
    def test_translate_image_primary_result_matches_streamlit_contract(
        self, mock_run_primary_ocr
    ):
        ocr_rows = pd.DataFrame(
            [
                {
                    "text": "R1: 6X",
                    "confidence": 0.99,
                    "x": 10.0,
                    "global_x": 10.0,
                    "y": 10.0,
                    "min_x": 0.0,
                    "max_x": 20.0,
                    "min_y": 0.0,
                    "max_y": 20.0,
                }
            ]
        )
        mock_run_primary_ocr.return_value = {
            "selected_name": "PaddleOCR",
            "selected_text": "R1: 6X",
            "selected_rows": ocr_rows,
            "paddle_inference_seconds": 0.2,
        }

        result = translate_image(self._base_request())
        primary = result.primary_result

        required_keys = {
            "overlay_image",
            "overlay_png",
            "overlay_legend",
            "overlay_legend_df",
            "raw_ocr_text",
            "clean_text",
            "line_df",
            "ocr_rows",
            "removed_noise_df",
            "matches_df",
            "unmatched",
            "readable_translation",
            "translation_txt",
            "quality_metrics",
            "quality_errors",
            "quality_warnings",
            "timings",
            "runtime_profile",
            "translation_profile",
            "source_mode",
            "output_mode",
            "area_mode",
            "crop_box",
            "diagnostic_request_id",
            "diagnostic_session_generation",
            "diagnostic_report_inputs",
        }
        self.assertTrue(required_keys.issubset(primary.keys()))
        self.assertIsInstance(primary["overlay_png"], (bytes, type(None)))
        self.assertIsInstance(primary["line_df"], pd.DataFrame)
        self.assertFalse(primary["line_df"].empty)
        self.assertEqual(primary["source_mode"], self.source_mode)
        self.assertEqual(primary["output_mode"], self.output_mode)
        self.assertEqual(primary["area_mode"], "Whole Pattern")
        self.assertEqual(primary["diagnostic_request_id"], "contract-request")
        self.assertEqual(
            primary["diagnostic_session_generation"], "contract-session"
        )
        self.assertIn("R1: 6 sc", primary["readable_translation"])
        self.assertIn("R1: 6 sc", primary["translation_txt"])
        self.assertEqual(
            primary["line_df"]["Translation"].iloc[0],
            "R1: 6 sc",
        )
        self.assertIsInstance(primary["translation_profile"]["counts"], dict)
        self.assertIsInstance(primary["translation_profile"]["timings"], dict)

        diagnostics = primary["diagnostic_report_inputs"]
        self.assertEqual(diagnostics["ocr_engine"], "PaddleOCR")
        self.assertEqual(diagnostics["image_quality_status"], "Good")
        self.assertEqual(diagnostics["interface_language"], "English")
        self.assertEqual(diagnostics["platform"], "unit-test")
        self.assertEqual(diagnostics["events"], [{"event": "snapshot"}])
        self.assertIn("session_diagnostics", diagnostics)
        self.assertIn("ocr_workload_diagnostics", diagnostics)
        self.assertIn("ocr_call_diagnostics", diagnostics)

        self.assertGreaterEqual(result.ocr_duration_seconds, 0.2)
        self.assertEqual(result.analytics["source_mode"], self.source_mode)
        self.assertEqual(result.analytics["output_mode"], self.output_mode)
        self.assertEqual(result.analytics["area_mode"], "Whole Pattern")
        self.assertGreater(result.analytics["translation_time_sec"], 0.0)


class TranslationServiceOrchestrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full_df = pd.read_csv("knowledge_base/data/master_stitches.csv").fillna("")
        cls.source_mode = "Traditional Chinese"
        cls.output_mode = "English — US"
        cls.df, cls.index = prepare_translation_dataframe(cls.full_df, cls.source_mode)

    def _base_request(self, **overrides):
        image = Image.new("RGB", (1200, 800), color=(255, 255, 255))
        crop_box = (0, 0, image.size[0], image.size[1])
        values = {
            "image": image,
            "selected_image": image,
            "working_image": image,
            "source_mode": self.source_mode,
            "output_mode": self.output_mode,
            "area_mode": "Whole Pattern",
            "crop_box": crop_box,
            "df": self.df,
            "index": self.index,
            "diagnostic_request_id": "test-request",
            "diagnostic_session_generation": "test-session",
            "action_started": None,
            "image_load_seconds": 0.01,
            "crop_extraction_seconds": 0.02,
            "quality_metrics": {"width_px": 1200, "height_px": 800},
            "quality_errors": [],
            "quality_warnings": [],
            "quality_label": "Good",
            "experimental_downscale": False,
            "downscale_max_height_option": "Original / no resize",
            "ocr_resize_test": "1000 px",
            "session_diagnostics": {"ocr_started_at": "2026-01-01 00:00:00"},
            "diagnostic_events": [],
            "diagnostic_platform": "unit-test",
            "interface_language": "English",
        }
        values.update(overrides)
        return TranslateImageRequest(**values)

    def _mock_pipeline(self):
        ocr_rows = pd.DataFrame(
            [
                {
                    "text": "R1: 6X",
                    "confidence": 0.99,
                    "x": 10.0,
                    "global_x": 10.0,
                    "y": 10.0,
                    "min_x": 0.0,
                    "max_x": 20.0,
                    "min_y": 0.0,
                    "max_y": 20.0,
                }
            ]
        )
        line_df = pd.DataFrame(
            [
                {
                    "Original": "R1: 6X",
                    "Translated": "R1: 6 sc",
                    "min_x": 0.0,
                    "max_x": 20.0,
                    "min_y": 0.0,
                    "max_y": 20.0,
                }
            ]
        )
        overlay_image = Image.new("RGB", (1200, 800), color=(255, 255, 255))
        return ocr_rows, line_df, overlay_image

    @mock.patch("pattern_translator.translation_service.overlay_engine.image_to_png_bytes")
    @mock.patch("pattern_translator.translation_service.overlay_engine.make_line_translation_overlay")
    @mock.patch("pattern_translator.translation_service.ocr_lines_engine.build_ocr_line_translations")
    @mock.patch("pattern_translator.translation_service.run_primary_ocr")
    def test_whole_pattern_path_returns_expected_structure(
        self,
        mock_run_primary_ocr,
        mock_build_lines,
        mock_make_overlay,
        mock_png_bytes,
    ):
        ocr_rows, line_df, overlay_image = self._mock_pipeline()
        mock_run_primary_ocr.return_value = {
            "selected_name": "PaddleOCR",
            "selected_text": "R1: 6X",
            "selected_rows": ocr_rows,
            "paddle_inference_seconds": 0.5,
        }
        mock_build_lines.return_value = line_df
        mock_make_overlay.return_value = (overlay_image, "[1] R1: 6 sc", line_df)
        mock_png_bytes.return_value = b"png-bytes"

        result = translate_image(self._base_request(area_mode="Whole Pattern"))

        self.assertIn("overlay_png", result.primary_result)
        self.assertIn("translation_txt", result.primary_result)
        self.assertIn("diagnostic_report_inputs", result.primary_result)
        self.assertEqual(result.analytics["area_mode"], "Whole Pattern")
        mock_run_primary_ocr.assert_called_once()
        overlay_args, overlay_kwargs = mock_make_overlay.call_args
        self.assertIs(line_df, overlay_args[1])
        self.assertEqual(self.output_mode, overlay_args[2])
        self.assertEqual({"scale_to_source_text": False}, overlay_kwargs)

    @mock.patch("pattern_translator.translation_service.overlay_engine.image_to_png_bytes")
    @mock.patch("pattern_translator.translation_service.overlay_engine.make_line_translation_overlay")
    @mock.patch("pattern_translator.translation_service.ocr_lines_engine.build_ocr_line_translations")
    @mock.patch("pattern_translator.translation_service.run_primary_ocr")
    def test_broad_debug_capture_flows_only_to_diagnostic_inputs(
        self,
        mock_run_primary_ocr,
        mock_build_lines,
        mock_make_overlay,
        mock_png_bytes,
    ):
        ocr_rows, line_df, overlay_image = self._mock_pipeline()
        capture = {
            "enabled": True,
            "route": "English US -> Traditional Chinese",
            "units": [
                {
                    "semantic_unit_id": "unit-0000",
                    "source_text": "R1: 6X",
                    "raw_candidate": "R1：6 短針",
                    "validation_status": "accepted",
                    "rejection_reason": "",
                    "route": "English US -> Traditional Chinese",
                    "protected_spans": [],
                }
            ],
        }
        line_df.attrs["broad_raw_candidate_debug"] = capture
        mock_run_primary_ocr.return_value = {
            "selected_name": "PaddleOCR",
            "selected_text": "R1: 6X",
            "selected_rows": ocr_rows,
            "paddle_inference_seconds": 0.5,
        }
        mock_build_lines.return_value = line_df
        mock_make_overlay.return_value = (overlay_image, "[1] R1: 6 sc", line_df)
        mock_png_bytes.return_value = b"png-bytes"

        result = translate_image(self._base_request(area_mode="Whole Pattern"))

        self.assertEqual(
            capture,
            result.primary_result["diagnostic_report_inputs"][
                "broad_raw_candidate_debug"
            ],
        )
        self.assertNotIn("broad_raw_candidate_debug", result.analytics)
        self.assertIs(line_df, result.primary_result["line_df"])

    @mock.patch("pattern_translator.translation_service.overlay_engine.image_to_png_bytes")
    @mock.patch("pattern_translator.translation_service.overlay_engine.make_line_translation_overlay")
    @mock.patch("pattern_translator.translation_service.ocr_lines_engine.build_ocr_line_translations")
    @mock.patch("pattern_translator.translation_service.run_primary_ocr")
    def test_select_area_path_uses_cropped_working_image(
        self,
        mock_run_primary_ocr,
        mock_build_lines,
        mock_make_overlay,
        mock_png_bytes,
    ):
        image = Image.new("RGB", (1000, 1000), color=(255, 255, 255))
        cropped = image.crop((100, 100, 500, 500))
        crop_box = (100, 100, 500, 500)
        ocr_rows, line_df, overlay_image = self._mock_pipeline()
        mock_run_primary_ocr.return_value = {
            "selected_name": "PaddleOCR",
            "selected_text": "R1: 6X",
            "selected_rows": ocr_rows,
            "paddle_inference_seconds": 0.4,
        }
        mock_build_lines.return_value = line_df
        mock_make_overlay.return_value = (overlay_image, "[1] R1: 6 sc", line_df)
        mock_png_bytes.return_value = b"png-bytes"

        result = translate_image(
            self._base_request(
                image=image,
                selected_image=cropped,
                working_image=cropped,
                area_mode="Select Area",
                crop_box=crop_box,
            )
        )

        diagnostics = result.primary_result["diagnostic_report_inputs"]
        ocr_call_diagnostics = diagnostics["ocr_call_diagnostics"]
        self.assertFalse(ocr_call_diagnostics["whole_pattern_sends_full_image"])
        self.assertTrue(ocr_call_diagnostics["select_area_sends_cropped_image"])
        self.assertEqual(result.analytics["area_mode"], "Select Area")
        overlay_args, overlay_kwargs = mock_make_overlay.call_args
        self.assertIs(cropped, overlay_args[0])
        self.assertIs(line_df, overlay_args[1])
        self.assertEqual(self.output_mode, overlay_args[2])
        self.assertEqual({"scale_to_source_text": True}, overlay_kwargs)
        passed_image = mock_run_primary_ocr.call_args.args[0]
        self.assertEqual(passed_image.size, cropped.size)

    @mock.patch("pattern_translator.translation_service.run_primary_ocr")
    def test_ocr_failure_propagates(self, mock_run_primary_ocr):
        mock_run_primary_ocr.side_effect = RuntimeError("ocr failed")
        with self.assertRaises(RuntimeError):
            translate_image(self._base_request())

    def test_no_streamlit_session_state_dependency(self):
        source = Path("pattern_translator/translation_service.py").read_text(encoding="utf-8")
        self.assertNotIn("session_state", source)
        self.assertIsNone(re.search(r"\bst\.", source))

    @mock.patch("pattern_translator.translation_service.overlay_engine.image_to_png_bytes")
    @mock.patch("pattern_translator.translation_service.overlay_engine.make_line_translation_overlay")
    @mock.patch("pattern_translator.translation_service.ocr_lines_engine.build_ocr_line_translations")
    @mock.patch("pattern_translator.translation_service.run_primary_ocr")
    def test_post_translation_ai_terminal_events_reach_downloadable_report(
        self,
        mock_run_primary_ocr,
        mock_build_lines,
        mock_make_overlay,
        mock_png_bytes,
    ):
        ocr_rows, line_df, overlay_image = self._mock_pipeline()
        mock_run_primary_ocr.return_value = {
            "selected_name": "PaddleOCR",
            "selected_text": "R1: 6X",
            "selected_rows": ocr_rows,
            "paddle_inference_seconds": 0.1,
        }

        def build_lines(*_args, **kwargs):
            logger = kwargs["diagnostic_logger"]
            common = {
                "model": "gpt-5.6-luna",
                "route": "general",
                "source_mode": "Traditional Chinese",
                "target_mode": "English — US",
                "elapsed_seconds": 0.25,
                "raw_response": "never-store-this-provider-content",
                "api_key": "sk-never-store-this-secret",
            }
            barrier = threading.Barrier(2)

            def emit(call_ordinal, outcome, reason, fallback):
                barrier.wait(timeout=1)
                logger(
                    "ai_request_end",
                    **common,
                    call_ordinal=call_ordinal,
                    outcome=outcome,
                    reason=reason,
                    deterministic_fallback_returned=fallback,
                )

            workers = (
                threading.Thread(
                    target=emit,
                    args=(
                        2,
                        "validation_rejected",
                        "validation_rejected_residual_cjk",
                        True,
                    ),
                ),
                threading.Thread(
                    target=emit,
                    args=(1, "success", "success", False),
                ),
            )
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=2)
                self.assertFalse(worker.is_alive())
            logger(
                "ai_request_end",
                **{
                    **common,
                    "route": "broad",
                    "call_ordinal": 99,
                    "outcome": "success",
                    "reason": "success",
                    "deterministic_fallback_returned": False,
                },
            )
            return line_df

        mock_build_lines.side_effect = build_lines
        mock_make_overlay.return_value = (overlay_image, "[1] R1: 6 sc", line_df)
        mock_png_bytes.return_value = b"png-bytes"

        result = translate_image(self._base_request())
        records = result.primary_result["diagnostic_report_inputs"][
            "ai_fallback_diagnostics"
        ]
        self.assertEqual([record["call_ordinal"] for record in records], [1, 2])
        self.assertEqual(
            [record["reason"] for record in records],
            ["success", "validation_rejected_residual_cjk"],
        )
        serialized = str(records)
        self.assertNotIn("never-store-this-provider-content", serialized)
        self.assertNotIn("sk-never-store-this-secret", serialized)

        report = result_delivery_engine.build_deferred_diagnostic_report(
            result.primary_result,
            terminology_dataframe=self.df,
        )
        self.assertIn("=== AI Fallback Diagnostics ===", report)
        self.assertIn("Call 1 | outcome=success | reason=success", report)
        self.assertIn(
            "Call 2 | outcome=validation_rejected | "
            "reason=validation_rejected_residual_cjk",
            report,
        )
        self.assertNotIn("never-store-this-provider-content", report)
        self.assertNotIn("sk-never-store-this-secret", report)


class DirectCorpusParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus_path = Path("rc49_evidence/Direct_Corpus_RC48_vs_RC49.csv")
        cls.full_df = pd.read_csv("knowledge_base/data/master_stitches.csv").fillna("")

    def test_direct_corpus_remains_identical(self):
        self.assertTrue(self.corpus_path.exists(), "Expected direct corpus reference file")
        mismatches = []
        with self.corpus_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                source_mode = row["source_mode"]
                output_mode = row["output_mode"]
                text = row["input"]
                expected = row["rc49_actual"]
                index = terminology_engine.build_term_index(
                    terminology_engine.get_active_search_df(self.full_df),
                    source_mode,
                )
                df = terminology_engine.get_active_search_df(self.full_df)
                actual = line_translation_engine.translate_ocr_line(
                    text, index, df, output_mode
                )
                if actual != expected:
                    mismatches.append((text, expected, actual))
        self.assertEqual([], mismatches[:5])
        self.assertEqual(220, self._corpus_count())
        self.assertEqual(0, len(mismatches))

    def _corpus_count(self) -> int:
        with self.corpus_path.open(encoding="utf-8", newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))


if __name__ == "__main__":
    unittest.main()
