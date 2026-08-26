import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from pattern_translator.engine import result_delivery
from pattern_translator.engine import translation_language_state


def signature(target, *, source=None, area="Whole Pattern"):
    return (
        "image-signature",
        source,
        target,
        area,
        (0, 0, 100, 100),
        (False, "Original / no resize", "Auto"),
    )


class TranslationLanguageStateTests(unittest.TestCase):
    def test_initial_no_selection_is_canonical_and_rendered(self):
        app = AppTest.from_string(
            """
import streamlit as st
from pattern_translator.engine import translation_language_state

def source_changed():
    translation_language_state.accept_source_language_change(st.session_state)

def target_changed():
    translation_language_state.accept_target_language_change(st.session_state)

canonical = translation_language_state.reconcile_translation_languages(st.session_state)
st.write(canonical)
st.selectbox(
    "Source",
    translation_language_state.LANGUAGE_OPTIONS,
    index=None,
    key=translation_language_state.SOURCE_WIDGET_KEY,
    on_change=source_changed,
)
st.selectbox(
    "Target",
    translation_language_state.LANGUAGE_OPTIONS,
    index=None,
    key=translation_language_state.TARGET_WIDGET_KEY,
    on_change=target_changed,
)
"""
        ).run()

        self.assertIsNone(
            app.session_state[translation_language_state.SOURCE_STATE_KEY]
        )
        self.assertIsNone(
            app.session_state[translation_language_state.TARGET_STATE_KEY]
        )
        self.assertIsNone(app.selectbox[0].value)
        self.assertIsNone(app.selectbox[1].value)
        self.assertEqual(list(app.warning), [])

    def test_genuine_widget_changes_update_canonical_state(self):
        app = AppTest.from_string(
            """
import streamlit as st
from pattern_translator.engine import translation_language_state

def source_changed():
    translation_language_state.accept_source_language_change(st.session_state)

def target_changed():
    translation_language_state.accept_target_language_change(st.session_state)

translation_language_state.reconcile_translation_languages(st.session_state)
st.selectbox(
    "Source",
    translation_language_state.LANGUAGE_OPTIONS,
    index=None,
    key=translation_language_state.SOURCE_WIDGET_KEY,
    on_change=source_changed,
)
st.selectbox(
    "Target",
    translation_language_state.LANGUAGE_OPTIONS,
    index=None,
    key=translation_language_state.TARGET_WIDGET_KEY,
    on_change=target_changed,
)
"""
        ).run()

        app.selectbox[0].select("Japanese").run()
        app.selectbox[1].select("English — UK").run()

        self.assertEqual(
            app.session_state[translation_language_state.SOURCE_STATE_KEY],
            "Japanese",
        )
        self.assertEqual(
            app.session_state[translation_language_state.TARGET_STATE_KEY],
            "English — UK",
        )

    def test_canonical_languages_survive_widget_omission(self):
        state = {
            translation_language_state.SOURCE_STATE_KEY: "Japanese",
            translation_language_state.TARGET_STATE_KEY: "English — UK",
        }

        restored = translation_language_state.reconcile_translation_languages(state)

        self.assertEqual(restored, {"source": "Japanese", "target": "English — UK"})
        self.assertEqual(
            state[translation_language_state.SOURCE_WIDGET_KEY], "Japanese"
        )
        self.assertEqual(
            state[translation_language_state.TARGET_WIDGET_KEY], "English — UK"
        )

    def test_remounted_widget_defaults_cannot_overwrite_canonical(self):
        state = {
            translation_language_state.SOURCE_STATE_KEY: "Japanese",
            translation_language_state.TARGET_STATE_KEY: "English — UK",
            translation_language_state.SOURCE_WIDGET_KEY: "Traditional Chinese",
            translation_language_state.TARGET_WIDGET_KEY: None,
        }

        current = translation_language_state.reconcile_translation_languages(state)

        self.assertEqual(current, {"source": "Japanese", "target": "English — UK"})
        self.assertEqual(
            state[translation_language_state.SOURCE_WIDGET_KEY], "Japanese"
        )
        self.assertEqual(
            state[translation_language_state.TARGET_WIDGET_KEY], "English — UK"
        )

    def test_explicit_source_change_still_changes_signature(self):
        state = {
            translation_language_state.SOURCE_STATE_KEY: "Japanese",
            translation_language_state.TARGET_STATE_KEY: "English — UK",
        }
        translation_language_state.reconcile_translation_languages(state)
        stored = signature("English — UK", source="Japanese")

        state[translation_language_state.SOURCE_WIDGET_KEY] = "Traditional Chinese"
        translation_language_state.accept_source_language_change(state)
        current = translation_language_state.reconcile_translation_languages(state)

        self.assertEqual(
            result_delivery.differing_signature_fields(
                stored,
                signature(current["target"], source=current["source"]),
            ),
            ("source_language",),
        )

    def test_explicit_target_change_still_changes_signature(self):
        state = {
            translation_language_state.SOURCE_STATE_KEY: "Japanese",
            translation_language_state.TARGET_STATE_KEY: "English — UK",
        }
        translation_language_state.reconcile_translation_languages(state)
        stored = signature("English — UK", source="Japanese")

        state[translation_language_state.TARGET_WIDGET_KEY] = "Simplified Chinese"
        translation_language_state.accept_target_language_change(state)
        current = translation_language_state.reconcile_translation_languages(state)

        self.assertEqual(
            result_delivery.differing_signature_fields(
                stored,
                signature(current["target"], source=current["source"]),
            ),
            ("target_language",),
        )

    def test_harmless_rerun_keeps_language_signature(self):
        state = {
            translation_language_state.SOURCE_STATE_KEY: "Japanese",
            translation_language_state.TARGET_STATE_KEY: "English — UK",
        }
        stored = signature("English — UK", source="Japanese")

        current = translation_language_state.reconcile_translation_languages(state)

        self.assertEqual(
            result_delivery.differing_signature_fields(
                stored,
                signature(current["target"], source=current["source"]),
            ),
            (),
        )

    def test_interface_language_does_not_change_translation_languages(self):
        state = {
            "ui_lang": "en",
            translation_language_state.SOURCE_STATE_KEY: "English — US",
            translation_language_state.TARGET_STATE_KEY: "Japanese",
        }
        translation_language_state.reconcile_translation_languages(state)
        state.pop(translation_language_state.SOURCE_WIDGET_KEY)
        state.pop(translation_language_state.TARGET_WIDGET_KEY)
        state["ui_lang"] = "zh-Hant"

        current = translation_language_state.reconcile_translation_languages(state)

        self.assertEqual(current, {"source": "English — US", "target": "Japanese"})

    def test_app_uses_callbacks_and_canonical_semantic_values(self):
        source = (
            Path(__file__).resolve().parents[1] / "pattern_translator" / "app.py"
        ).read_text(encoding="utf-8")

        self.assertIn("on_change=accept_source_language_change", source)
        self.assertIn("on_change=accept_target_language_change", source)
        self.assertIn('source_mode = canonical_translation_languages["source"]', source)
        self.assertIn('output_mode = canonical_translation_languages["target"]', source)
        self.assertNotIn("source_mode = st.selectbox(", source)
        self.assertNotIn("output_mode = st.selectbox(", source)

    def test_reconciliation_precedes_analytics_short_circuit_and_widgets(self):
        source = (
            Path(__file__).resolve().parents[1] / "pattern_translator" / "app.py"
        ).read_text(encoding="utf-8")

        reconciliation = source.index(
            "translation_language_state_engine.reconcile_translation_languages"
        )
        analytics_rerun = source.index(
            'completed_result_analytics = st.session_state.pop('
        )
        target_widget = source.index('key="target_language_selector"')

        self.assertLess(reconciliation, analytics_rerun)
        self.assertLess(analytics_rerun, target_widget)


if __name__ == "__main__":
    unittest.main()
