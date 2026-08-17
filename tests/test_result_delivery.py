import threading
import unittest
from pathlib import Path

import pandas as pd

from pattern_translator.engine import diagnostic_report
from pattern_translator.engine import result_delivery


class ResultDeliveryTests(unittest.TestCase):
    def test_primary_result_is_stored_without_diagnostic_report(self):
        session_state = {}
        result = {"readable_translation": "translated", "overlay_png": b"png"}

        result_delivery.store_primary_result(session_state, result)

        self.assertIs(session_state["rc3_ocr_result"], result)
        self.assertNotIn("debug_report_txt", result)

    def test_diagnostic_exception_does_not_destroy_primary_result(self):
        session_state = {}
        result = {"readable_translation": "translated", "overlay_png": b"png"}
        result_delivery.store_primary_result(session_state, result)

        def fail():
            raise RuntimeError("synthetic report failure")

        generated, outcome = result_delivery.generate_optional_diagnostic_report(
            result, fail
        )

        self.assertFalse(generated)
        self.assertEqual(outcome, "generation_error")
        self.assertEqual(
            session_state["rc3_ocr_result"]["readable_translation"], "translated"
        )
        self.assertNotIn("debug_report_txt", result)

    def test_diagnostic_stall_cannot_delay_primary_result_commit(self):
        session_state = {}
        result = {"readable_translation": "translated", "overlay_png": b"png"}
        result_delivery.store_primary_result(session_state, result)
        builder_started = threading.Event()
        release_builder = threading.Event()

        def stall():
            builder_started.set()
            release_builder.wait(timeout=2)
            return "report"

        worker = threading.Thread(
            target=result_delivery.generate_optional_diagnostic_report,
            args=(result, stall),
        )
        worker.start()
        self.assertTrue(builder_started.wait(timeout=1))
        self.assertEqual(
            session_state["rc3_ocr_result"]["readable_translation"], "translated"
        )
        self.assertNotIn("debug_report_txt", result)
        release_builder.set()
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result["debug_report_txt"], "report")

    def test_successful_diagnostic_report_remains_downloadable(self):
        result = {"readable_translation": "translated"}

        generated, outcome = result_delivery.generate_optional_diagnostic_report(
            result, lambda: "diagnostic report"
        )

        self.assertTrue(generated)
        self.assertEqual(outcome, "success")
        self.assertEqual(result["debug_report_txt"], "diagnostic report")

    def test_existing_report_builder_still_generates_normal_report(self):
        line_df = pd.DataFrame(
            [{"original": "R1", "translated": "Round 1"}]
        )

        report = diagnostic_report.build_debug_report_text(line_df)

        self.assertIn("Diagnostic Report", report)
        self.assertIn("Translation Output", report)

    def test_app_stores_primary_result_before_optional_report_generation(self):
        app_source = (
            Path(__file__).resolve().parents[1] / "pattern_translator" / "app.py"
        ).read_text(encoding="utf-8")
        store_position = app_source.index(
            "result_delivery_engine.store_primary_result("
        )
        store_success_position = app_source.index(
            '"translation_result_store_success"', store_position
        )
        report_button_position = app_source.index(
            'key="generate_debug_report_txt"', store_success_position
        )
        report_begin_position = app_source.index(
            '"diagnostic_report_begin"', report_button_position
        )

        self.assertLess(store_position, store_success_position)
        self.assertLess(store_success_position, report_button_position)
        self.assertLess(report_button_position, report_begin_position)


if __name__ == "__main__":
    unittest.main()
