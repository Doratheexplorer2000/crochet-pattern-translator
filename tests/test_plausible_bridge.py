import os
import unittest
from pathlib import Path
from unittest import mock

from crochet_intelligence import plausible_bridge


class PlausibleBridgeTests(unittest.TestCase):
    def test_stage_creates_one_unique_pending_event(self):
        state = {}

        plausible_bridge.stage_plausible_event(state, "pattern_png_downloaded")

        event = state["pending_plausible_v2_event"]
        self.assertEqual(event["name"], "pattern_png_downloaded")
        self.assertTrue(event["id"])

    def test_main_mount_passes_pending_event_to_v2_component(self):
        pending = {"name": "pattern_translation_completed", "id": "event-1"}
        with mock.patch.dict(
            os.environ,
            {"PUBLIC_PLAUSIBLE_SCRIPT_URL": "https://example.test/pa.js"},
            clear=True,
        ), mock.patch.object(plausible_bridge, "_plausible_bridge") as component:
            plausible_bridge.mount_plausible_bridge(pending)

        component.assert_called_once()
        kwargs = component.call_args.kwargs
        self.assertEqual(kwargs["key"], "crochet_intelligence_plausible_bridge")
        self.assertEqual(kwargs["data"]["event"], pending)
        self.assertIsNone(kwargs["data"]["link"])

    def test_direct_event_uses_same_v2_component(self):
        with mock.patch.dict(
            os.environ,
            {"PUBLIC_PLAUSIBLE_SCRIPT_URL": "https://example.test/pa.js"},
            clear=True,
        ), mock.patch.object(plausible_bridge, "_plausible_bridge") as component:
            plausible_bridge.emit_plausible_event(
                "pattern_image_uploaded",
                "upload-action-1",
                key="upload-transport",
            )

        kwargs = component.call_args.kwargs
        self.assertEqual(kwargs["key"], "upload-transport")
        self.assertEqual(
            kwargs["data"]["event"],
            {"name": "pattern_image_uploaded", "id": "upload-action-1"},
        )

    def test_tracked_link_uses_v2_and_preserves_native_fallback_on_failure(self):
        environment = {"PUBLIC_PLAUSIBLE_SCRIPT_URL": "https://example.test/pa.js"}
        with mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(
            plausible_bridge, "_plausible_bridge"
        ) as component:
            rendered = plausible_bridge.plausible_link_button(
                "Feedback",
                "https://example.test/form",
                "pattern_feedback_clicked",
                key="feedback-link",
            )

        self.assertTrue(rendered)
        kwargs = component.call_args.kwargs
        self.assertEqual(kwargs["data"]["link"]["event_name"], "pattern_feedback_clicked")

        with mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(
            plausible_bridge, "_plausible_bridge", side_effect=RuntimeError("unavailable")
        ):
            rendered = plausible_bridge.plausible_link_button(
                "Feedback",
                "https://example.test/form",
                "pattern_feedback_clicked",
                key="feedback-link",
            )
        self.assertFalse(rendered)

    def test_link_without_tracking_configuration_uses_native_fallback(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            plausible_bridge, "_plausible_bridge"
        ) as component:
            rendered = plausible_bridge.plausible_link_button(
                "Feedback",
                "https://example.test/form",
                "pattern_feedback_clicked",
                key="feedback-link",
            )

        self.assertFalse(rendered)
        component.assert_not_called()

    def test_analytics_component_failure_is_non_blocking(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            plausible_bridge, "_plausible_bridge", side_effect=RuntimeError("unavailable")
        ):
            plausible_bridge.mount_plausible_bridge(None)
            plausible_bridge.emit_plausible_event(
                "pattern_image_uploaded", "event-1", key="upload-transport"
            )

    def test_browser_contract_deduplicates_and_uses_no_iframe(self):
        source = plausible_bridge._BRIDGE_JS
        self.assertIn('document.getElementById("ci-plausible-script")', source)
        self.assertIn("window.__ciPlausibleLoadPromise", source)
        self.assertIn("window.__ciPlausibleSentEvents", source)
        self.assertIn("window.sessionStorage", source)
        self.assertIn("duplicate suppressed", source)
        self.assertNotIn("iframe", source.lower())

    def test_app_maps_all_five_events_to_v2_transport(self):
        app_source = Path("pattern_translator/app.py").read_text(encoding="utf-8")
        for event_name in (
            "pattern_image_uploaded",
            "pattern_translation_completed",
            "pattern_png_downloaded",
            "pattern_txt_downloaded",
            "pattern_feedback_clicked",
        ):
            self.assertIn(event_name, app_source)

        self.assertNotIn("pattern_translator.components.plausible_event", app_source)
        self.assertNotIn("pending_plausible_events", app_source)
        self.assertNotIn("queue_plausible_event", app_source)
        self.assertIn("stage_plausible_event(st.session_state, plausible_event_name)", app_source)
        self.assertIn(
            'stage_plausible_event(st.session_state, "pattern_translation_completed")',
            app_source,
        )
        self.assertIn(
            'emit_plausible_event(\n            "pattern_image_uploaded"',
            app_source,
        )
        self.assertIn('plausible_event_name="pattern_png_downloaded"', app_source)
        self.assertIn('plausible_event_name="pattern_txt_downloaded"', app_source)
        self.assertIn(
            '"pattern_feedback_clicked",\n            key="pattern_feedback_clicked_link"',
            app_source,
        )
        self.assertFalse(Path("pattern_translator/components/plausible_event").exists())


if __name__ == "__main__":
    unittest.main()
