import base64
import copy
import io
import json
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
from fastapi.testclient import TestClient
from PIL import Image

from pattern_translator import api as pattern_api
from pattern_translator.api import app
from pattern_translator.engine import translation_area_state as translation_area_state_engine
from pattern_translator.translation_service import (
    TranslateImageRequest,
    prepare_translation_dataframe,
    translate_image,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class PatternApiImportTests(unittest.TestCase):
    def test_module_imports_without_streamlit(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                "import importlib; "
                "importlib.import_module('pattern_translator.api'); "
                "import pathlib; "
                "source = pathlib.Path('pattern_translator/api.py').read_text(encoding='utf-8'); "
                "assert 'import streamlit' not in source; "
                "assert 'from streamlit' not in source",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr or completed.stdout)


class PatternApiHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full_df = pd.read_csv(REPO_ROOT / "knowledge_base/data/master_stitches.csv").fillna("")
        cls.source_mode = "Traditional Chinese"
        cls.output_mode = "English — US"
        cls.df, cls.index = prepare_translation_dataframe(cls.full_df, cls.source_mode)
        cls.client = TestClient(app)

    @staticmethod
    def _png_bytes(width: int = 120, height: int = 80, colour: str = "white") -> bytes:
        output = io.BytesIO()
        Image.new("RGB", (width, height), colour).save(output, format="PNG")
        return output.getvalue()

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

    def _mock_primary_ocr(self):
        return {
            "selected_name": "PaddleOCR",
            "selected_text": "R1: 6X",
            "selected_rows": self._ocr_rows(),
            "paddle_inference_seconds": 0.05,
        }

    def _multipart(self, **fields):
        files = fields.pop("files", None)
        data = dict(fields)
        return self.client.post("/api/v1/translate", data=data, files=files)

    def _translated_payload(self, area_mode="Whole Pattern", crop_box=None):
        fields = {
            "files": {
                "image": (
                    "pattern.png",
                    self._png_bytes(200, 160),
                    "image/png",
                )
            },
            "source_mode": self.source_mode,
            "output_mode": self.output_mode,
            "area_mode": area_mode,
        }
        if crop_box:
            for name, value in zip(
                ("crop_left", "crop_top", "crop_right", "crop_bottom"),
                crop_box,
            ):
                fields[name] = str(value)
        with mock.patch(
            "pattern_translator.translation_service.run_primary_ocr",
            return_value=self._mock_primary_ocr(),
        ):
            response = self._multipart(**fields)
        self.assertEqual(200, response.status_code)
        return response.json()

    def test_whole_pattern_valid_request_returns_200(self):
        with mock.patch(
            "pattern_translator.translation_service.run_primary_ocr",
            return_value=self._mock_primary_ocr(),
        ):
            response = self._multipart(
                files={"image": ("pattern.png", self._png_bytes(), "image/png")},
                source_mode=self.source_mode,
                output_mode=self.output_mode,
                area_mode="Whole Pattern",
            )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(self.source_mode, payload["source_mode"])
        self.assertEqual(self.output_mode, payload["output_mode"])
        self.assertEqual("Whole Pattern", payload["area_mode"])
        self.assertIn("R1: 6 sc", payload["readable_translation"])
        self.assertIn("R1: 6 sc", payload["translation_txt"])
        self.assertIsNotNone(payload["overlay_png"])
        self.assertEqual("image/png", payload["overlay_png"]["media_type"])
        self.assertTrue(payload["overlay_png"]["base64"])

    def test_translate_image_invoked_once_with_real_request(self):
        with mock.patch(
            "pattern_translator.translation_service.run_primary_ocr",
            return_value=self._mock_primary_ocr(),
        ), mock.patch(
            "pattern_translator.api.translate_image",
            wraps=translate_image,
        ) as translate_spy:
            response = self._multipart(
                files={"image": ("pattern.png", self._png_bytes(), "image/png")},
                source_mode=self.source_mode,
                output_mode=self.output_mode,
                area_mode="Whole Pattern",
            )
        self.assertEqual(200, response.status_code)
        translate_spy.assert_called_once()
        request = translate_spy.call_args.args[0]
        self.assertIsInstance(request, TranslateImageRequest)
        self.assertEqual(self.source_mode, request.source_mode)
        self.assertEqual(self.output_mode, request.output_mode)
        self.assertEqual("Whole Pattern", request.area_mode)

    def test_translate_exposes_snapshot_without_building_report(self):
        with mock.patch(
            "pattern_translator.translation_service.run_primary_ocr",
            return_value=self._mock_primary_ocr(),
        ), mock.patch.object(
            pattern_api.result_delivery_engine,
            "build_deferred_diagnostic_report",
        ) as report_builder:
            response = self._multipart(
                files={"image": ("pattern.png", self._png_bytes(), "image/png")},
                source_mode=self.source_mode,
                output_mode=self.output_mode,
                area_mode="Whole Pattern",
            )

        self.assertEqual(200, response.status_code)
        diagnostic_context = response.json()["diagnostic_context"]
        self.assertEqual(1, diagnostic_context["schema_version"])
        self.assertEqual(
            "Whole Pattern",
            diagnostic_context["result"]["area_mode"],
        )
        self.assertLessEqual(
            len(json.dumps(diagnostic_context).encode("utf-8")),
            pattern_api.result_delivery_engine.MAX_DIAGNOSTIC_SNAPSHOT_BYTES,
        )
        report_builder.assert_not_called()

    def test_snapshot_failure_does_not_replace_successful_translation(self):
        with mock.patch(
            "pattern_translator.translation_service.run_primary_ocr",
            return_value=self._mock_primary_ocr(),
        ), mock.patch.object(
            pattern_api.result_delivery_engine,
            "create_diagnostic_snapshot",
            side_effect=ValueError("snapshot failed"),
        ):
            response = self._multipart(
                files={"image": ("pattern.png", self._png_bytes(), "image/png")},
                source_mode=self.source_mode,
                output_mode=self.output_mode,
                area_mode="Whole Pattern",
            )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertIsNone(payload["diagnostic_context"])
        self.assertIn("R1: 6 sc", payload["readable_translation"])
        self.assertTrue(payload["overlay_png"]["base64"])

    def test_diagnostic_endpoint_restores_whole_and_selected_area_context(self):
        cases = [
            ("Whole Pattern", None, [0, 0, 200, 160], "200 x 160 px"),
            ("Select Area", (40, 30, 140, 110), [40, 30, 140, 110], "100 x 80 px"),
        ]
        real_builder = (
            pattern_api.result_delivery_engine.build_deferred_diagnostic_report
        )
        for area_mode, crop_box, expected_crop, expected_resolution in cases:
            with self.subTest(area_mode=area_mode):
                translated = self._translated_payload(area_mode, crop_box)
                with mock.patch(
                    "pattern_translator.api.translate_image"
                ) as translate_spy, mock.patch(
                    "pattern_translator.translation_service.run_primary_ocr"
                ) as ocr_spy, mock.patch.object(
                    pattern_api.result_delivery_engine,
                    "build_deferred_diagnostic_report",
                    wraps=real_builder,
                ) as report_builder:
                    response = self.client.post(
                        "/api/v1/diagnostic-report",
                        json={
                            "diagnostic_context": translated[
                                "diagnostic_context"
                            ],
                            "ui_lang": "ja",
                        },
                        headers={"user-agent": "Phase3B1-Test-Agent"},
                    )

                self.assertEqual(200, response.status_code)
                self.assertTrue(
                    response.headers["content-type"].startswith(
                        "text/plain; charset=utf-8"
                    )
                )
                self.assertRegex(
                    response.headers["content-disposition"],
                    r'attachment; filename="PatternOCR_DiagnosticReport_RC26_\d{8}_\d{6}\.txt"',
                )
                self.assertIn(f"Area selected: {area_mode}", response.text)
                self.assertIn(f"Crop box: {tuple(expected_crop)}", response.text)
                self.assertIn(f"Resolution: {expected_resolution}", response.text)
                self.assertIn("R1: 6X", response.text)
                self.assertIn("R1: 6 sc", response.text)
                self.assertIn("Interface language: Japanese", response.text)
                self.assertIn("Platform: Phase3B1-Test-Agent", response.text)
                self.assertIn(
                    "Image quality status: Not assessed",
                    response.text,
                )
                restored_result = report_builder.call_args.args[0]
                self.assertEqual(area_mode, restored_result["area_mode"])
                self.assertEqual(tuple(expected_crop), restored_result["crop_box"])
                self.assertEqual(
                    "R1: 6X",
                    restored_result["raw_ocr_text"],
                )
                self.assertIn(
                    "R1: 6 sc",
                    restored_result["readable_translation"],
                )
                translate_spy.assert_not_called()
                ocr_spy.assert_not_called()

    def test_diagnostic_endpoint_rejects_malformed_and_oversized_requests(self):
        valid_snapshot = self._translated_payload()["diagnostic_context"]
        invalid_result_type = copy.deepcopy(valid_snapshot)
        invalid_result_type["result"]["quality_metrics"] = []
        duplicate_frame_columns = copy.deepcopy(valid_snapshot)
        duplicate_frame_columns["frames"]["line_df"]["columns"] = [
            "Original",
            "Original",
        ]
        cases = [
            (
                b"{",
                {"content-type": "application/json"},
            ),
            (
                json.dumps(
                    {
                        "diagnostic_context": {"schema_version": 1},
                        "ui_lang": "en",
                    }
                ).encode("utf-8"),
                {"content-type": "application/json"},
            ),
            (
                json.dumps(
                    {
                        "diagnostic_context": {"schema_version": True},
                        "ui_lang": "en",
                    }
                ).encode("utf-8"),
                {"content-type": "application/json"},
            ),
            (
                json.dumps(
                    {
                        "diagnostic_context": {},
                        "ui_lang": "invalid",
                    }
                ).encode("utf-8"),
                {"content-type": "application/json"},
            ),
            (
                b"x" * (pattern_api._MAX_DIAGNOSTIC_REQUEST_BYTES + 1),
                {"content-type": "application/json"},
            ),
            (
                json.dumps(
                    {
                        "diagnostic_context": invalid_result_type,
                        "ui_lang": "en",
                    }
                ).encode("utf-8"),
                {"content-type": "application/json"},
            ),
            (
                json.dumps(
                    {
                        "diagnostic_context": duplicate_frame_columns,
                        "ui_lang": "en",
                    }
                ).encode("utf-8"),
                {"content-type": "application/json"},
            ),
        ]
        for content, headers in cases:
            with self.subTest(size=len(content)):
                response = self.client.post(
                    "/api/v1/diagnostic-report",
                    content=content,
                    headers=headers,
                )
                self.assertEqual(400, response.status_code)
                self.assertEqual(
                    "Invalid diagnostic request",
                    response.json()["error"],
                )
                self.assertTrue(response.json()["request_id"])

    def test_diagnostic_builder_exception_is_generic_and_isolated(self):
        translated = self._translated_payload()
        snapshot = translated["diagnostic_context"]
        before = json.dumps(snapshot, sort_keys=True)
        with mock.patch.object(
            pattern_api.result_delivery_engine,
            "build_deferred_diagnostic_report",
            side_effect=RuntimeError("secret diagnostic failure"),
        ), mock.patch("pattern_translator.api.translate_image") as translate_spy:
            response = self.client.post(
                "/api/v1/diagnostic-report",
                json={"diagnostic_context": snapshot, "ui_lang": "en"},
            )

        self.assertEqual(500, response.status_code)
        self.assertEqual("Diagnostic report failed", response.json()["error"])
        self.assertTrue(response.json()["request_id"])
        self.assertNotIn("secret", response.text)
        self.assertEqual(before, json.dumps(snapshot, sort_keys=True))
        translate_spy.assert_not_called()

    def test_select_area_ocr_receives_cropped_dimensions(self):
        width, height = 200, 160
        crop_box = (40, 30, 140, 110)
        observed_sizes = []

        def capture_ocr(image, *_args, **_kwargs):
            observed_sizes.append(image.size)
            return self._mock_primary_ocr()

        with mock.patch(
            "pattern_translator.translation_service.run_primary_ocr",
            side_effect=capture_ocr,
        ):
            response = self._multipart(
                files={
                    "image": (
                        "pattern.png",
                        self._png_bytes(width, height),
                        "image/png",
                    )
                },
                source_mode=self.source_mode,
                output_mode=self.output_mode,
                area_mode="Select Area",
                crop_left=str(crop_box[0]),
                crop_top=str(crop_box[1]),
                crop_right=str(crop_box[2]),
                crop_bottom=str(crop_box[3]),
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual([(100, 80)], observed_sizes)
        payload = response.json()
        self.assertEqual(list(crop_box), payload["crop_box"])

    def test_unsupported_language_fails_before_service(self):
        with mock.patch(
            "pattern_translator.api.translate_image",
        ) as translate_spy:
            response = self._multipart(
                files={"image": ("pattern.png", self._png_bytes(), "image/png")},
                source_mode="Klingon",
                output_mode=self.output_mode,
                area_mode="Whole Pattern",
            )
        self.assertEqual(400, response.status_code)
        translate_spy.assert_not_called()

    def test_unsupported_area_mode_fails_before_service(self):
        with mock.patch(
            "pattern_translator.api.translate_image",
        ) as translate_spy:
            response = self._multipart(
                files={"image": ("pattern.png", self._png_bytes(), "image/png")},
                source_mode=self.source_mode,
                output_mode=self.output_mode,
                area_mode="Left Column",
            )
        self.assertEqual(400, response.status_code)
        translate_spy.assert_not_called()

    def test_partial_crop_fails_before_service(self):
        with mock.patch(
            "pattern_translator.api.translate_image",
        ) as translate_spy:
            response = self._multipart(
                files={"image": ("pattern.png", self._png_bytes(200, 160), "image/png")},
                source_mode=self.source_mode,
                output_mode=self.output_mode,
                area_mode="Select Area",
                crop_left="10",
                crop_top="10",
            )
        self.assertEqual(400, response.status_code)
        translate_spy.assert_not_called()

    def test_invalid_crop_bounds_fail_before_service(self):
        with mock.patch(
            "pattern_translator.api.translate_image",
        ) as translate_spy:
            response = self._multipart(
                files={"image": ("pattern.png", self._png_bytes(200, 160), "image/png")},
                source_mode=self.source_mode,
                output_mode=self.output_mode,
                area_mode="Select Area",
                crop_left="150",
                crop_top="10",
                crop_right="140",
                crop_bottom="120",
            )
        self.assertEqual(400, response.status_code)
        translate_spy.assert_not_called()

    def test_out_of_bounds_crop_fails_before_service(self):
        with mock.patch(
            "pattern_translator.api.translate_image",
        ) as translate_spy:
            response = self._multipart(
                files={"image": ("pattern.png", self._png_bytes(200, 160), "image/png")},
                source_mode=self.source_mode,
                output_mode=self.output_mode,
                area_mode="Select Area",
                crop_left="0",
                crop_top="0",
                crop_right="250",
                crop_bottom="160",
            )
        self.assertEqual(400, response.status_code)
        translate_spy.assert_not_called()

    def test_invalid_image_bytes_fail_before_service(self):
        with mock.patch(
            "pattern_translator.api.translate_image",
        ) as translate_spy:
            response = self._multipart(
                files={"image": ("pattern.png", b"not-an-image", "image/png")},
                source_mode=self.source_mode,
                output_mode=self.output_mode,
                area_mode="Whole Pattern",
            )
        self.assertEqual(400, response.status_code)
        translate_spy.assert_not_called()

    def test_unsupported_image_format_fails_before_service(self):
        gif_bytes = io.BytesIO()
        Image.new("RGB", (4, 4), "red").save(gif_bytes, format="GIF")
        with mock.patch(
            "pattern_translator.api.translate_image",
        ) as translate_spy:
            response = self._multipart(
                files={"image": ("pattern.gif", gif_bytes.getvalue(), "image/gif")},
                source_mode=self.source_mode,
                output_mode=self.output_mode,
                area_mode="Whole Pattern",
            )
        self.assertEqual(400, response.status_code)
        translate_spy.assert_not_called()

    def test_internal_service_failure_returns_generic_error_with_request_id(self):
        with mock.patch(
            "pattern_translator.api.translate_image",
            side_effect=RuntimeError("secret internal failure detail"),
        ):
            response = self._multipart(
                files={"image": ("pattern.png", self._png_bytes(), "image/png")},
                source_mode=self.source_mode,
                output_mode=self.output_mode,
                area_mode="Whole Pattern",
            )
        self.assertEqual(500, response.status_code)
        payload = response.json()
        self.assertEqual("Translation failed", payload["error"])
        self.assertTrue(payload["request_id"])
        self.assertNotIn("secret", response.text)

    def test_http_result_matches_direct_translate_image(self):
        image = Image.new("RGB", (120, 80), color=(255, 255, 255))
        crop_box = (0, 0, image.size[0], image.size[1])
        action_started = time.perf_counter() - 0.1
        ocr_execution_start = time.perf_counter() - 0.05

        direct_request = TranslateImageRequest(
            image=image,
            selected_image=image,
            working_image=image,
            source_mode=self.source_mode,
            output_mode=self.output_mode,
            area_mode="Whole Pattern",
            crop_box=crop_box,
            df=self.df,
            index=self.index,
            diagnostic_request_id="direct-equivalence",
            diagnostic_session_generation="direct-equivalence",
            action_started=action_started,
            image_load_seconds=0.01,
            crop_extraction_seconds=0.02,
            quality_metrics={"width_px": 120, "height_px": 80},
            quality_errors=[],
            quality_warnings=[],
            quality_label="Not assessed",
            experimental_downscale=False,
            downscale_max_height_option="Original / no resize",
            ocr_resize_test="1000 px",
            session_diagnostics={},
            diagnostic_events=[],
            diagnostic_platform="unit-test",
            interface_language="English",
            ocr_execution_start=ocr_execution_start,
        )

        with mock.patch(
            "pattern_translator.translation_service.run_primary_ocr",
            return_value=self._mock_primary_ocr(),
        ):
            direct_result = translate_image(direct_request)
            response = self._multipart(
                files={
                    "image": (
                        "pattern.png",
                        self._png_bytes(120, 80),
                        "image/png",
                    )
                },
                source_mode=self.source_mode,
                output_mode=self.output_mode,
                area_mode="Whole Pattern",
            )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        direct_primary = direct_result.primary_result
        self.assertEqual(
            direct_primary["readable_translation"],
            payload["readable_translation"],
        )
        self.assertEqual(
            direct_primary["translation_txt"],
            payload["translation_txt"],
        )
        self.assertEqual(
            direct_primary["overlay_png"],
            base64.b64decode(payload["overlay_png"]["base64"]),
        )


if __name__ == "__main__":
    unittest.main()
