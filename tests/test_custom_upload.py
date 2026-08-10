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
        self.assertEqual(result, (None, None, False))
        self.assertFalse(component.call_args.kwargs["active_image_present"])
        self.assertEqual(component.call_args.kwargs["active_image_name"], "")

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
                )
        self.assertEqual(component.call_count, 3)
        for call in component.call_args_list:
            self.assertTrue(call.kwargs["active_image_present"])
            self.assertEqual(call.kwargs["active_image_name"], "capybara.png")

    def test_upload_and_replace_payloads_decode_to_active_image_bytes(self):
        first = self.png_bytes("red")
        second = self.png_bytes("blue")
        payloads = (
            {
                "name": "capybara.png",
                "type": "image/png",
                "data_base64": base64.b64encode(first).decode("ascii"),
                "action_id": "upload-1",
            },
            {
                "name": "potato.png",
                "type": "image/png",
                "data_base64": base64.b64encode(second).decode("ascii"),
                "action_id": "replace-2",
            },
        )
        decoded = [
            custom_upload._decode_upload_payload(payload, self.strings)[0]
            for payload in payloads
        ]
        self.assertEqual([item.name for item in decoded], ["capybara.png", "potato.png"])
        self.assertEqual([item.action_id for item in decoded], ["upload-1", "replace-2"])
        self.assertEqual([item.getvalue() for item in decoded], [first, second])

    def test_remove_payload_clears_active_image(self):
        self.assertEqual(
            custom_upload._decode_upload_payload(
                {"removed": True, "action_id": "remove-3"}, self.strings
            ),
            (None, None, True),
        )

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

    def test_app_rerenders_component_after_backend_removal(self):
        app_source = (
            Path(custom_upload.__file__).resolve().parents[2] / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'if upload_removed and st.session_state.get("rc3_image_signature") is not None:\n'
            "    reset_uploaded_image_derived_state(None)\n"
            "    st.rerun()",
            app_source,
        )


if __name__ == "__main__":
    unittest.main()
