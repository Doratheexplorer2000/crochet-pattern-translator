import json
import unittest

import pandas as pd

from pattern_translator.engine import broad_translation
from pattern_translator.engine import diagnostic_report
from pattern_translator.engine import result_delivery


def _row(text: str, y: float) -> dict:
    return {
        "text": text,
        "semantic_text": text,
        "confidence": 0.95,
        "min_x": 0.0,
        "max_x": 200.0,
        "min_y": y,
        "max_y": y + 20.0,
    }


def _provider_payload(translations: list[str]) -> dict:
    assignments = {}
    units = {}
    for index, translation in enumerate(translations):
        unit_id = f"unit-{index:04d}"
        assignments[f"segment-{index:04d}"] = unit_id
        units[unit_id] = {"translated_text": translation}
    response = {
        "segment_assignments": assignments,
        "semantic_units": units,
    }
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


class BroadRawCandidateDebugCaptureTests(unittest.TestCase):
    def setUp(self):
        self.rows = pd.DataFrame(
            [
                _row("PATTERN", 0.0),
                _row("R1: 6 sc (6)", 30.0),
                _row("R2: 6 inc (12)", 60.0),
                _row("docs.example.com", 90.0),
            ]
        )
        self.payload = _provider_payload(
            [
                "花樣（パターン）",
                "R1：6 短針（6）",
                "R2：6 短針（12）",
                "__ciurla__",
            ]
        )
        self.secret = "sk-unit-test-secret-must-not-appear"

    def _translate(self, debug_value=None):
        calls = []

        def caller(prompt, api_key):
            calls.append((prompt, api_key))
            return self.payload, 0.01

        environ = {"OPENAI_API_KEY": self.secret}
        if debug_value is not None:
            environ[broad_translation.BROAD_DEBUG_CAPTURE_ENV] = debug_value
        result = broad_translation.translate_merged_ocr_lines_broad(
            self.rows,
            source_mode="English — US",
            output_mode="Traditional Chinese",
            environ=environ,
            luna_caller=caller,
        )
        return result, calls

    def test_flag_absent_does_not_retain_or_report_raw_candidates(self):
        result, calls = self._translate()

        self.assertEqual(1, len(calls))
        self.assertNotIn(broad_translation.BROAD_DEBUG_CAPTURE_ATTR, result.attrs)
        report = diagnostic_report.build_debug_report_text(result)
        self.assertNotIn("=== Broad Raw Candidate Debug ===", report)
        self.assertIn("Raw provider output retained: No", report)
        self.assertNotIn("R2：6 短針（12）", report)

    def test_flag_on_captures_exact_candidates_and_validation_outcomes(self):
        result, calls = self._translate("1")

        self.assertEqual(1, len(calls))
        capture = result.attrs[broad_translation.BROAD_DEBUG_CAPTURE_ATTR]
        self.assertTrue(capture["enabled"])
        self.assertEqual("English US -> Traditional Chinese", capture["route"])
        self.assertEqual(4, len(capture["units"]))
        accepted = capture["units"][0]
        rejected = capture["units"][2]
        protected = capture["units"][3]
        self.assertEqual("unit-0000", accepted["semantic_unit_id"])
        self.assertEqual("PATTERN", accepted["source_text"])
        self.assertEqual("花樣（パターン）", accepted["raw_candidate"])
        self.assertEqual("accepted", accepted["validation_status"])
        self.assertEqual("rejected", rejected["validation_status"])
        self.assertEqual("stitch_terminology", rejected["rejection_reason"])
        self.assertEqual("__ciurla__", protected["raw_candidate"])
        self.assertEqual("docs.example.com", protected["processed_candidate"])
        self.assertEqual(
            [
                {
                    "source_segment_id": "segment-0003",
                    "kind": "url_or_domain",
                    "text": "docs.example.com",
                }
            ],
            protected["protected_spans"],
        )

        report = diagnostic_report.build_debug_report_text(
            result,
            broad_raw_candidate_debug=capture,
        )
        self.assertIn("=== Broad Raw Candidate Debug ===", report)
        self.assertIn("Raw provider output retained: Yes", report)
        self.assertIn("Semantic Unit: unit-0002", report)
        self.assertIn("Validation: rejected", report)
        self.assertIn("Reason: stitch_terminology", report)
        self.assertIn("花樣（パターン）", report)
        self.assertIn("R2：6 短針（12）", report)
        self.assertIn("Processed Candidate:\ndocs.example.com", report)
        self.assertNotIn(self.secret, json.dumps(capture, ensure_ascii=False))
        self.assertNotIn(self.secret, report)

    def test_debug_flag_does_not_change_validation_or_provider_call_count(self):
        without_capture, off_calls = self._translate("0")
        with_capture, on_calls = self._translate("1")

        self.assertEqual(1, len(off_calls))
        self.assertEqual(1, len(on_calls))
        for column in (
            "Original",
            "Translation",
            "Validation Status",
            "Validation Failure Reason",
        ):
            self.assertEqual(
                without_capture[column].tolist(),
                with_capture[column].tolist(),
            )

    def test_capture_survives_diagnostic_snapshot_without_truncation_or_secrets(self):
        line_df, _calls = self._translate("1")
        capture = line_df.attrs[broad_translation.BROAD_DEBUG_CAPTURE_ATTR]
        capture_with_injected_secret = dict(capture)
        capture_with_injected_secret["api_key"] = self.secret
        result = {
            "source_mode": "English — US",
            "output_mode": "Traditional Chinese",
            "area_mode": "Whole Pattern",
            "crop_box": (0, 0, 200, 120),
            "quality_metrics": {},
            "timings": {},
            "runtime_profile": {},
            "translation_profile": {},
            "request_warning": "",
            "overlay_legend": "",
            "raw_ocr_text": "",
            "clean_text": "",
            "unmatched": [],
            "line_df": line_df,
            "matches_df": pd.DataFrame(),
            "ocr_rows": pd.DataFrame(),
            "overlay_legend_df": pd.DataFrame(),
            "diagnostic_report_inputs": {
                "broad_raw_candidate_debug": capture_with_injected_secret,
                "ocr_box_rows": pd.DataFrame(
                    columns=[
                        "text",
                        "confidence",
                        "min_x",
                        "max_x",
                        "min_y",
                        "max_y",
                    ]
                ),
            },
        }

        snapshot = result_delivery.create_diagnostic_snapshot(
            result,
            terminology_row_count=0,
        )
        serialized = json.dumps(snapshot, ensure_ascii=False)
        self.assertIn("花樣（パターン）", serialized)
        self.assertIn("R2：6 短針（12）", serialized)
        self.assertNotIn(self.secret, serialized)
        restored = result_delivery.restore_diagnostic_snapshot(
            json.loads(serialized),
            interface_language="English",
            platform="local-test",
        )
        report = result_delivery.build_deferred_diagnostic_report(
            restored.result,
            terminology_row_count=0,
        )
        self.assertIn("=== Broad Raw Candidate Debug ===", report)
        self.assertIn("花樣（パターン）", report)
        self.assertIn("R2：6 短針（12）", report)
        self.assertNotIn(self.secret, report)


if __name__ == "__main__":
    unittest.main()
