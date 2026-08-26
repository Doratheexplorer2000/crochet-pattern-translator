import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from pattern_translator.engine import result_delivery
from pattern_translator.engine import translation_area_state
from pattern_translator.engine import translation_language_state


def signature(area_mode, crop_box):
    selected_width = crop_box[2] - crop_box[0]
    selected_height = crop_box[3] - crop_box[1]
    downscale = max(selected_width, selected_height) > 1000
    downscale_option = "Max height 1000 px" if downscale else "Original / no resize"
    return (
        "image-signature",
        "Traditional Chinese",
        "English — UK",
        area_mode,
        crop_box,
        (downscale, downscale_option, "1000 px"),
    )


class TranslationAreaStateTests(unittest.TestCase):
    def test_genuine_area_change_updates_canonical_state(self):
        app = AppTest.from_string(
            """
import streamlit as st
from pattern_translator.engine import translation_area_state

def area_changed():
    translation_area_state.accept_translation_area_change(st.session_state)

translation_area_state.reconcile_translation_area(st.session_state)
st.radio(
    "Area",
    translation_area_state.AREA_OPTIONS,
    index=None,
    key=translation_area_state.AREA_WIDGET_KEY,
    on_change=area_changed,
)
"""
        ).run()

        app.radio[0].set_value(translation_area_state.SELECT_AREA).run()

        self.assertEqual(
            app.session_state[translation_area_state.AREA_STATE_KEY],
            translation_area_state.SELECT_AREA,
        )

    def test_canonical_select_area_survives_widget_omission_and_default(self):
        state = {
            translation_area_state.AREA_STATE_KEY: translation_area_state.SELECT_AREA,
            translation_area_state.AREA_WIDGET_KEY: translation_area_state.WHOLE_PATTERN,
        }

        selected = translation_area_state.reconcile_translation_area(state)

        self.assertEqual(selected, translation_area_state.SELECT_AREA)
        self.assertEqual(
            state[translation_area_state.AREA_WIDGET_KEY],
            translation_area_state.SELECT_AREA,
        )
        state.pop(translation_area_state.AREA_WIDGET_KEY)
        self.assertEqual(
            translation_area_state.reconcile_translation_area(state),
            translation_area_state.SELECT_AREA,
        )

    def test_canonical_whole_pattern_survives_widget_omission(self):
        state = {
            translation_area_state.AREA_STATE_KEY: translation_area_state.WHOLE_PATTERN
        }

        selected = translation_area_state.reconcile_translation_area(state)

        self.assertEqual(selected, translation_area_state.WHOLE_PATTERN)
        self.assertEqual(
            state[translation_area_state.AREA_WIDGET_KEY],
            translation_area_state.WHOLE_PATTERN,
        )

    def test_genuine_area_and_crop_changes_still_invalidate(self):
        stored_crop = (100, 120, 700, 820)
        stored = signature(translation_area_state.SELECT_AREA, stored_crop)
        state = {
            translation_area_state.AREA_STATE_KEY: translation_area_state.SELECT_AREA,
            translation_area_state.AREA_WIDGET_KEY: translation_area_state.WHOLE_PATTERN,
        }

        translation_area_state.accept_translation_area_change(state)
        changed_area = signature(
            translation_area_state.reconcile_translation_area(state),
            (0, 0, 2000, 2000),
        )
        changed_crop = signature(
            translation_area_state.SELECT_AREA, (110, 120, 700, 820)
        )

        self.assertEqual(
            result_delivery.differing_signature_fields(stored, changed_area),
            ("area_mode", "crop_box", "downscale_flag", "downscale_option"),
        )
        self.assertEqual(
            result_delivery.differing_signature_fields(stored, changed_crop),
            ("crop_box",),
        )

    def test_genuine_resize_setting_change_still_invalidates(self):
        stored = list(
            signature(translation_area_state.SELECT_AREA, (100, 120, 700, 820))
        )
        changed = list(stored)
        changed[5] = (True, "Max height 1400 px", "1400 px")

        self.assertEqual(
            result_delivery.differing_signature_fields(tuple(stored), tuple(changed)),
            ("downscale_flag", "downscale_option", "ocr_resize_option"),
        )

    def test_completed_select_area_result_survives_post_result_early_rerun(self):
        crop_box = (100, 120, 700, 820)
        stored_signature = signature(translation_area_state.SELECT_AREA, crop_box)
        for action in ("png", "txt", "diagnostic"):
            with self.subTest(action=action):
                state = {
                    translation_language_state.SOURCE_STATE_KEY: "Traditional Chinese",
                    translation_language_state.TARGET_STATE_KEY: "English — UK",
                    translation_area_state.AREA_STATE_KEY: translation_area_state.SELECT_AREA,
                    "select_area_confirmed_crop_box": crop_box,
                    "rc3_ocr_result": {"action": action},
                    "rc3_ocr_result_signature": stored_signature,
                    "completed_result_analytics_pending": {"action": action},
                }

                # The post-result action run exits before rendering these widgets.
                translation_language_state.reconcile_translation_languages(state)
                translation_area_state.reconcile_translation_area(state)
                state.pop(translation_language_state.SOURCE_WIDGET_KEY)
                state.pop(translation_language_state.TARGET_WIDGET_KEY)
                state.pop(translation_area_state.AREA_WIDGET_KEY)

                # Model Streamlit's remount defaults on the queued analytics rerun.
                state[translation_language_state.TARGET_WIDGET_KEY] = None
                state[translation_area_state.AREA_WIDGET_KEY] = (
                    translation_area_state.WHOLE_PATTERN
                )
                languages = translation_language_state.reconcile_translation_languages(
                    state
                )
                area_mode = translation_area_state.reconcile_translation_area(state)
                current_signature = signature(
                    area_mode, state["select_area_confirmed_crop_box"]
                )

                self.assertEqual(languages["target"], "English — UK")
                self.assertEqual(area_mode, translation_area_state.SELECT_AREA)
                self.assertEqual(
                    state["select_area_confirmed_crop_box"], crop_box
                )
                self.assertEqual(
                    result_delivery.differing_signature_fields(
                        state["rc3_ocr_result_signature"], current_signature
                    ),
                    (),
                )
                self.assertIsNotNone(state["rc3_ocr_result"])

    def test_streamlit_production_sequence_preserves_result_for_each_action(self):
        for action in ("png", "txt", "diagnostic"):
            with self.subTest(action=action):
                app = AppTest.from_string(
                    f'''\
import streamlit as st
from pattern_translator.engine import translation_area_state
from pattern_translator.engine import translation_language_state

CROP = (100, 120, 700, 820)

def source_changed():
    translation_language_state.accept_source_language_change(st.session_state)

def target_changed():
    translation_language_state.accept_target_language_change(st.session_state)

def area_changed():
    translation_area_state.accept_translation_area_change(st.session_state)

def complete_result():
    st.session_state["select_area_confirmed_crop_box"] = CROP
    st.session_state["stored_signature"] = (
        "image-signature",
        st.session_state[translation_language_state.SOURCE_STATE_KEY],
        st.session_state[translation_language_state.TARGET_STATE_KEY],
        st.session_state[translation_area_state.AREA_STATE_KEY],
        CROP,
    )
    st.session_state["result"] = {{"complete": True}}

def post_result_action():
    st.session_state["completed_result_analytics_pending"] = "{action}"

languages = translation_language_state.reconcile_translation_languages(st.session_state)
area_mode = translation_area_state.reconcile_translation_area(st.session_state)
if st.session_state.pop("completed_result_analytics_pending", None):
    st.rerun()
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
st.radio(
    "Area",
    translation_area_state.AREA_OPTIONS,
    key=translation_area_state.AREA_WIDGET_KEY,
    on_change=area_changed,
)
st.button("complete", on_click=complete_result)
st.button("{action}", on_click=post_result_action)
current_signature = (
    "image-signature",
    languages["source"],
    languages["target"],
    area_mode,
    st.session_state.get("select_area_confirmed_crop_box"),
)
if st.session_state.get("result") and st.session_state.get("stored_signature") != current_signature:
    st.session_state["result"] = None
'''
                ).run()
                app.selectbox[0].select("Traditional Chinese").run()
                app.selectbox[1].select("English — UK").run()
                app.radio[0].set_value(translation_area_state.SELECT_AREA).run()
                app.button[0].click().run()

                app.button[1].click().run()

                self.assertEqual(
                    app.session_state[translation_language_state.TARGET_STATE_KEY],
                    "English — UK",
                )
                self.assertEqual(
                    app.session_state[translation_area_state.AREA_STATE_KEY],
                    translation_area_state.SELECT_AREA,
                )
                self.assertEqual(
                    app.session_state["select_area_confirmed_crop_box"],
                    (100, 120, 700, 820),
                )
                self.assertEqual(app.session_state["result"], {"complete": True})

    def test_select_area_cropper_path_survives_component_reruns(self):
        app = AppTest.from_string(
            """
import streamlit as st
from pattern_translator.engine import translation_area_state

def area_changed():
    translation_area_state.accept_translation_area_change(st.session_state)

translation_area_state.reconcile_translation_area(st.session_state)
st.radio(
    "Area",
    translation_area_state.AREA_OPTIONS,
    key=translation_area_state.AREA_WIDGET_KEY,
    on_change=area_changed,
)
area_mode = st.session_state[translation_area_state.AREA_STATE_KEY]
if area_mode == translation_area_state.SELECT_AREA:
    st.session_state["cropper_path_runs"] = st.session_state.get("cropper_path_runs", 0) + 1
    st.button("component rerun")
"""
        ).run()
        app.radio[0].set_value(translation_area_state.SELECT_AREA).run()
        first_count = app.session_state["cropper_path_runs"]

        app.button[0].click().run()

        self.assertGreater(app.session_state["cropper_path_runs"], first_count)
        self.assertEqual(
            app.session_state[translation_area_state.AREA_STATE_KEY],
            translation_area_state.SELECT_AREA,
        )

    def test_app_uses_area_callback_and_canonical_semantic_value(self):
        source = (
            Path(__file__).resolve().parents[1] / "pattern_translator" / "app.py"
        ).read_text(encoding="utf-8")

        self.assertIn("on_change=accept_translation_area_change", source)
        self.assertNotIn("area_mode = st.radio(", source)
        self.assertIn(
            "st.session_state.get(translation_area_state_engine.AREA_STATE_KEY)",
            source,
        )

    def test_area_reconciliation_precedes_analytics_short_circuit(self):
        source = (
            Path(__file__).resolve().parents[1] / "pattern_translator" / "app.py"
        ).read_text(encoding="utf-8")

        reconciliation = source.index(
            "translation_area_state_engine.reconcile_translation_area"
        )
        analytics_rerun = source.index(
            'completed_result_analytics = st.session_state.pop('
        )
        area_widget = source.index('key="translation_area_mode_radio"')

        self.assertLess(reconciliation, analytics_rerun)
        self.assertLess(analytics_rerun, area_widget)


if __name__ == "__main__":
    unittest.main()
