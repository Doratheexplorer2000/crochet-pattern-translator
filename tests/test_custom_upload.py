import base64
import io
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from pattern_translator.components import custom_upload


class CustomUploadTests(unittest.TestCase):
    def setUp(self):
        self.strings = {
            "error_unreadable": "unreadable",
            "error_unsupported": "unsupported",
            "error_empty": "empty",
            "error_too_large": "too large",
            "error_invalid": "invalid",
        }

    @staticmethod
    def png_bytes(colour):
        output = io.BytesIO()
        Image.new("RGB", (2, 2), colour).save(output, format="PNG")
        return output.getvalue()

    def test_component_receives_fresh_empty_state(self):
        with mock.patch.object(
            custom_upload, "_custom_upload_component", return_value=None
        ) as component:
            result = custom_upload.custom_image_uploader(
                self.strings,
                key="upload",
            )
        self.assertEqual(result, (None, None, None))
        self.assertFalse(component.call_args.kwargs["active_image_present"])
        self.assertEqual(component.call_args.kwargs["active_image_name"], "")
        self.assertEqual(component.call_args.kwargs["accepted_generation"], 0)

    def test_component_receives_backend_loaded_state_on_repeated_renders(self):
        with mock.patch.object(
            custom_upload, "_custom_upload_component", return_value=None
        ) as component:
            for _ in range(3):
                custom_upload.custom_image_uploader(
                    self.strings,
                    key="upload",
                    active_image_present=True,
                    active_image_name="capybara.png",
                    accepted_generation=4,
                )
        self.assertEqual(component.call_count, 3)
        for call in component.call_args_list:
            self.assertTrue(call.kwargs["active_image_present"])
            self.assertEqual(call.kwargs["active_image_name"], "capybara.png")
            self.assertEqual(call.kwargs["accepted_generation"], 4)

    def test_upload_and_replace_payloads_decode_to_active_image_bytes(self):
        first = self.png_bytes("red")
        second = self.png_bytes("blue")
        payloads = (
            {
                "name": "capybara.png",
                "type": "image/png",
                "data_base64": base64.b64encode(first).decode("ascii"),
                "action_id": "upload-1",
                "generation": 1,
            },
            {
                "name": "potato.png",
                "type": "image/png",
                "data_base64": base64.b64encode(second).decode("ascii"),
                "action_id": "replace-2",
                "generation": 2,
            },
        )
        decoded = [
            custom_upload._decode_upload_payload(payload, self.strings)[0]
            for payload in payloads
        ]
        self.assertEqual([item.name for item in decoded], ["capybara.png", "potato.png"])
        self.assertEqual([item.action_id for item in decoded], ["upload-1", "replace-2"])
        self.assertEqual([item.generation for item in decoded], [1, 2])
        self.assertEqual([item.getvalue() for item in decoded], [first, second])

    def test_remove_payload_clears_active_image(self):
        image, error, removal = custom_upload._decode_upload_payload(
            {"removed": True, "action_id": "remove-3", "generation": 3},
            self.strings,
        )
        self.assertIsNone(image)
        self.assertIsNone(error)
        self.assertEqual(removal.action_id, "remove-3")
        self.assertEqual(removal.generation, 3)

    def test_accepted_payload_is_not_decoded_again_on_rerun(self):
        payload = {
            "name": "capybara.png",
            "type": "image/png",
            "data_base64": "large-payload-is-not-read",
            "action_id": "upload-accepted",
            "generation": 3,
        }
        with mock.patch.object(custom_upload.base64, "b64decode") as decode:
            result = custom_upload._decode_upload_payload(
                payload,
                self.strings,
                accepted_action_id="upload-accepted",
                accepted_generation=3,
            )
        self.assertEqual(result, (None, None, None))
        decode.assert_not_called()

    def test_lightweight_acknowledgement_is_not_treated_as_an_upload(self):
        self.assertEqual(
            custom_upload._decode_upload_payload(
                {"acknowledged_action_id": "upload-accepted"}, self.strings
            ),
            (None, None, None),
        )

    def test_backend_snapshot_restores_upload_after_component_remount(self):
        original = custom_upload.UploadedImageBytes(
            self.png_bytes("green"),
            "capybara.png",
            "image/png",
            action_id="upload-1",
            generation=1,
        )
        snapshot = custom_upload.snapshot_uploaded_image(original)
        restored = custom_upload.restore_uploaded_image(snapshot)

        self.assertIsNotNone(restored)
        self.assertEqual(restored.getvalue(), original.getvalue())
        self.assertEqual(restored.name, "capybara.png")
        self.assertEqual(restored.type, "image/png")
        self.assertEqual(restored.action_id, "upload-1")
        self.assertEqual(restored.generation, 1)

    def test_repeated_upload_snapshots_keep_only_the_latest_image(self):
        snapshot = None
        for number, colour in enumerate(("red", "green", "blue"), start=1):
            uploaded = custom_upload.UploadedImageBytes(
                self.png_bytes(colour),
                f"pattern-{number}.png",
                "image/png",
                action_id=f"upload-{number}",
                generation=number,
            )
            snapshot = custom_upload.snapshot_uploaded_image(uploaded)

        restored = custom_upload.restore_uploaded_image(snapshot)
        self.assertEqual(restored.name, "pattern-3.png")
        self.assertEqual(restored.action_id, "upload-3")
        self.assertEqual(restored.generation, 3)
        self.assertEqual(restored.getvalue(), self.png_bytes("blue"))

    def test_out_of_order_replace_cannot_overwrite_newer_snapshot(self):
        payload_b = {
            "name": "b.png",
            "type": "image/png",
            "data_base64": base64.b64encode(self.png_bytes("blue")).decode("ascii"),
            "action_id": "replace-b",
            "generation": 2,
        }
        payload_c = {
            "name": "c.png",
            "type": "image/png",
            "data_base64": base64.b64encode(self.png_bytes("green")).decode("ascii"),
            "action_id": "replace-c",
            "generation": 3,
        }

        newest, _, _ = custom_upload._decode_upload_payload(
            payload_c, self.strings, accepted_generation=1
        )
        snapshot = custom_upload.snapshot_uploaded_image(newest)
        delayed, _, _ = custom_upload._decode_upload_payload(
            payload_b, self.strings, accepted_generation=3
        )

        self.assertIsNone(delayed)
        restored = custom_upload.restore_uploaded_image(snapshot)
        self.assertEqual(restored.name, "c.png")
        self.assertEqual(restored.generation, 3)

    def test_stale_generation_is_rejected_before_base64_decode(self):
        stale_payload = {
            "name": "stale.png",
            "type": "image/png",
            "data_base64": "large-stale-payload-is-not-read",
            "action_id": "different-stale-action",
            "generation": 2,
        }
        with mock.patch.object(custom_upload.base64, "b64decode") as decode:
            result = custom_upload._decode_upload_payload(
                stale_payload,
                self.strings,
                accepted_generation=3,
            )
        self.assertEqual(result, (None, None, None))
        decode.assert_not_called()

    def test_multiple_consecutive_replacements_keep_latest_generation(self):
        accepted_generation = 0
        snapshot = None
        colours = ("red", "green", "blue", "yellow", "purple")
        for generation, colour in enumerate(colours, start=1):
            payload = {
                "name": f"pattern-{generation}.png",
                "type": "image/png",
                "data_base64": base64.b64encode(self.png_bytes(colour)).decode("ascii"),
                "action_id": f"replace-{generation}",
                "generation": generation,
            }
            image, error, removal = custom_upload._decode_upload_payload(
                payload,
                self.strings,
                accepted_generation=accepted_generation,
            )
            self.assertIsNone(error)
            self.assertIsNone(removal)
            snapshot = custom_upload.snapshot_uploaded_image(image)
            accepted_generation = image.generation

        restored = custom_upload.restore_uploaded_image(snapshot)
        self.assertEqual(restored.name, "pattern-5.png")
        self.assertEqual(restored.generation, 5)
        self.assertEqual(restored.getvalue(), self.png_bytes("purple"))

    def test_remove_blocks_replay_and_next_upload_remains_current(self):
        _, _, removal = custom_upload._decode_upload_payload(
            {"removed": True, "action_id": "remove", "generation": 4},
            self.strings,
            accepted_generation=3,
        )
        replayed, _, _ = custom_upload._decode_upload_payload(
            {
                "name": "c.png",
                "type": "image/png",
                "data_base64": "stale-payload-must-not-be-decoded",
                "action_id": "replace-c",
                "generation": 3,
            },
            self.strings,
            accepted_generation=removal.generation,
        )
        payload_d = {
            "name": "d.png",
            "type": "image/png",
            "data_base64": base64.b64encode(self.png_bytes("red")).decode("ascii"),
            "action_id": "upload-d",
            "generation": 5,
        }
        newest, _, _ = custom_upload._decode_upload_payload(
            payload_d, self.strings, accepted_generation=removal.generation
        )

        self.assertIsNone(replayed)
        self.assertEqual(newest.name, "d.png")
        self.assertEqual(newest.generation, 5)

    def test_frontend_render_uses_backend_state_after_component_remount(self):
        source = (
            Path(custom_upload.__file__).resolve().parent
            / "src"
            / "index.js"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "backendImagePresent = Boolean(args.active_image_present)", source
        )
        self.assertIn(
            'setState(reading ? "reading" : hasActiveImage() ? "selected" : "empty")',
            source,
        )
        self.assertIn("backendImagePresent = false", source)
        self.assertIn("generation !== selectedGeneration", source)
        self.assertIn("acceptedGeneration >= selectedPayload.generation", source)
        self.assertIn("generation: acceptedGeneration", source)
        self.assertIn("generation,", source)
        self.assertIn("selectedFile = null", source)
        self.assertIn("selectedPayload = null", source)
        self.assertIn("acknowledged_action_id: acceptedActionId", source)

    def test_app_rerenders_component_after_backend_removal(self):
        app_source = (
            Path(custom_upload.__file__).resolve().parents[2] / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'if upload_removed:\n'
            '    st.session_state["rc3_upload_generation"] = max(',
            app_source,
        )
        self.assertIn(
            'st.session_state["rc3_active_image_upload"] = snapshot_uploaded_image(image_file)',
            app_source,
        )
        self.assertIn("image_file = active_image_upload", app_source)
        self.assertIn(
            'st.session_state["rc3_active_image_upload"] = None', app_source
        )
        self.assertIn(
            'accepted_generation=st.session_state.get("rc3_upload_generation", 0)',
            app_source,
        )

    def test_app_preserves_duplicate_processing_guard(self):
        app_source = (
            Path(custom_upload.__file__).resolve().parents[2] / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'or ocr_request_lifecycle_engine.is_active(',
            app_source,
        )
        self.assertIn(
            'st.session_state["duplicate_ocr_run_ignored_count"]', app_source
        )
        self.assertIn("        return\n", app_source)

    def test_app_claims_pending_request_before_ocr_and_finishes_it(self):
        app_source = (
            Path(custom_upload.__file__).resolve().parents[2] / "app.py"
        ).read_text(encoding="utf-8")
        claim_position = app_source.index(
            "lifecycle, request_claimed = ocr_request_lifecycle_engine.claim_request("
        )
        pending_log_position = app_source.index('"pending_run_begin"', claim_position)
        ocr_position = app_source.index("candidate_result = run_primary_ocr(", claim_position)
        result_position = app_source.index(
            'st.session_state["rc3_ocr_result"] = {', ocr_position
        )
        finish_position = app_source.index(
            "ocr_request_lifecycle_engine.finish_request(", result_position
        )
        success_ui_position = app_source.index(
            'ocr_status_placeholder.success("🟢 OCR completed.")', finish_position
        )

        self.assertLess(claim_position, pending_log_position)
        self.assertLess(pending_log_position, ocr_position)
        self.assertLess(ocr_position, result_position)
        self.assertLess(result_position, finish_position)
        self.assertLess(finish_position, success_ui_position)
        self.assertEqual(app_source.count('"pending_run_begin"'), 1)
        self.assertIn(
            'st.session_state["pending_ocr_run"] = False\n'
            '            if not request_claimed:',
            app_source[claim_position:pending_log_position],
        )

    def test_production_retains_disconnected_sessions_for_mobile_resume(self):
        start_script = (
            Path(custom_upload.__file__).resolve().parents[3] / "railway_start.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'STREAMLIT_SERVER_DISCONNECTED_SESSION_TTL="${STREAMLIT_SERVER_DISCONNECTED_SESSION_TTL:-900}"',
            start_script,
        )


if __name__ == "__main__":
    unittest.main()
