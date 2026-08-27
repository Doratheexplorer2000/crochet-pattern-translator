import re
import csv
import importlib
import subprocess
import sys
import threading
import time
import unittest
from contextvars import ContextVar
from pathlib import Path
from unittest import mock

import pandas as pd
from PIL import Image

from pattern_translator.engine import line_translation as line_translation_engine
from pattern_translator.engine import terminology as terminology_engine
from pattern_translator.translation_service import (
    TranslateImageRequest,
    _TRANSLATION_PROFILE,
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
