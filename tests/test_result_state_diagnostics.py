import contextlib
import io
import unittest
from pathlib import Path

from pattern_translator.engine import result_delivery


class ResultStateDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.app_source = (
            Path(__file__).resolve().parents[1]
            / "pattern_translator"
            / "app.py"
        ).read_text(encoding="utf-8")

    def test_signature_diagnostics_return_field_names_only(self):
        stored = (
            "private-image-signature-a",
            "source-a",
            "target-a",
            "Whole Pattern",
            (1, 2, 3, 4),
            (False, "option-a", "resize-a"),
        )
        current = (
            "private-image-signature-b",
            "source-b",
            "target-b",
            "Select Area",
            (5, 6, 7, 8),
            (True, "option-b", "resize-b"),
        )

        differences = result_delivery.differing_signature_fields(stored, current)

        self.assertEqual(
            differences,
            (
                "image_signature",
                "source_language",
                "target_language",
                "area_mode",
                "crop_box",
                "downscale_flag",
                "downscale_option",
                "ocr_resize_option",
            ),
        )
        self.assertFalse(any("private" in field for field in differences))

    def test_matching_signature_has_no_mismatch_fields(self):
        signature = (
            "private-image-signature",
            "source",
            "target",
            "Whole Pattern",
            (1, 2, 3, 4),
            (False, "option", "resize"),
        )

        self.assertEqual(
            result_delivery.differing_signature_fields(signature, signature),
            (),
        )

    def test_logger_emits_structural_categories_without_values(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            result_delivery.log_result_state(
                "request-uuid",
                "translation_signature_guard",
                session_generation="session-generation",
                script_run_no=7,
                lifecycle="completed",
                result_present=True,
                active_image=True,
                accepted_upload_generation=4,
                action="png",
                area_mode="select_area",
                select_area_editing=False,
                crop_confirmed=True,
                stored_signature_present=True,
                current_signature_present=True,
                signature_match=False,
                mismatch_fields=("image_signature", "crop_box"),
            )

        line = output.getvalue()
        self.assertIn("action=png", line)
        self.assertIn("mismatch_fields=image_signature,crop_box", line)
        self.assertIn("result_present=true", line)
        self.assertNotIn("private-image-signature", line)
        self.assertNotIn("1,2,3,4", line)

    def test_logger_drops_unapproved_mismatch_fields(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            result_delivery.log_result_state(
                "request-uuid",
                "result_clear",
                session_generation="session-generation",
                script_run_no=2,
                lifecycle="completed",
                result_present=True,
                active_image=True,
                accepted_upload_generation=1,
                mismatch_fields=("source_language", "secret-value"),
            )

        line = output.getvalue()
        self.assertIn("mismatch_fields=source_language", line)
        self.assertNotIn("secret-value", line)

    def test_png_and_txt_receipts_report_result_present(self):
        for action in ("png", "txt"):
            with self.subTest(action=action):
                output = io.StringIO()
                with contextlib.redirect_stderr(output):
                    result_delivery.log_result_state(
                        "request-uuid",
                        "post_result_action_received",
                        session_generation="session-generation",
                        script_run_no=4,
                        lifecycle="completed",
                        result_present=True,
                        active_image=True,
                        accepted_upload_generation=2,
                        action=action,
                    )
                line = output.getvalue()
                self.assertIn(f"action={action}", line)
                self.assertIn("result_present=true", line)
                self.assertIn("lifecycle=completed", line)

    def test_logging_does_not_mutate_result_state(self):
        result = {"readable_translation": "private translation"}
        state = {
            "rc3_ocr_result": result,
            "ocr_request_lifecycle": {
                "request_id": "request-uuid",
                "state": "completed",
            },
        }
        before = dict(state)

        with contextlib.redirect_stderr(io.StringIO()):
            result_delivery.log_result_state(
                "request-uuid",
                "result_render_enter",
                session_generation="session-generation",
                script_run_no=3,
                lifecycle="completed",
                result_present=True,
                active_image=True,
                accepted_upload_generation=1,
            )

        self.assertEqual(state, before)
        self.assertIs(state["rc3_ocr_result"], result)

    def test_png_and_txt_callbacks_log_receipt_without_changing_download_flow(self):
        callback_start = self.app_source.index("    def mark_download_complete(")
        callback_end = self.app_source.index("\n\n    try:", callback_start)
        callback_source = self.app_source[callback_start:callback_end]

        self.assertIn('"post_result_action_received"', callback_source)
        self.assertIn("action=diagnostic_action", callback_source)
        self.assertIn(
            'st.session_state["last_successful_download_key"] = download_key',
            callback_source,
        )
        self.assertIn('diagnostic_action="png"', self.app_source)
        self.assertIn('diagnostic_action="txt"', self.app_source)

    def test_diagnostic_receipt_and_handler_entry_are_distinct(self):
        diagnostic_position = self.app_source.index(
            'key="prepare_debug_report_download"'
        )
        nearby_source = self.app_source[
            diagnostic_position - 500:diagnostic_position + 900
        ]

        self.assertIn("on_click=note_diagnostic_action_received", nearby_source)
        self.assertIn('"post_result_action_received"', nearby_source)
        self.assertIn('"post_result_action_handler_enter"', nearby_source)
        self.assertIn('action="diagnostic"', nearby_source)
        self.assertIn('"diagnostic_report_begin"', self.app_source)

    def test_all_result_clear_reasons_are_instrumented(self):
        for reason in (
            "image_removed",
            "new_image",
            "select_area_start_over",
            "translation_signature_mismatch",
            "new_translation_result",
        ):
            with self.subTest(reason=reason):
                self.assertIn(f'reason="{reason}"', self.app_source)

        direct_clears = self.app_source.count(
            'st.session_state["rc3_ocr_result"] = None'
        )
        self.assertEqual(direct_clears, 3)
        self.assertGreaterEqual(
            self.app_source.count('"result_clear"'), direct_clears
        )
        self.assertIn('uploader_event = "remove"', self.app_source)
        self.assertIn('uploader_event = "replace"', self.app_source)
        self.assertIn('else "new"', self.app_source)

    def test_render_entry_and_early_exit_reasons_are_instrumented(self):
        self.assertIn('"result_render_enter"', self.app_source)
        for reason in (
            "no_active_image",
            "select_area_editing",
            "pending_request_replay",
            "ocr_failure",
            "result_invalidated",
            "result_absent",
        ):
            with self.subTest(reason=reason):
                self.assertIn(f'reason="{reason}"', self.app_source)

    def test_whole_pattern_and_select_area_categories_are_both_supported(self):
        self.assertIn('"Whole Pattern": "whole_pattern"', self.app_source)
        self.assertIn('"Select Area": "select_area"', self.app_source)


if __name__ == "__main__":
    unittest.main()
