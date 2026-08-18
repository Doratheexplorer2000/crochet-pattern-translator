import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from pattern_translator.engine import result_delivery
from pattern_translator.engine import translation_area_state


def signature(area_mode, crop_box, *, image_size=(2000, 2000)):
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
    def test_streamlit_151_short_circuit_preserves_select_area_and_crop(self):
        app = AppTest.from_string(
            """
import streamlit as st
from pattern_translator.engine import translation_area_state

translation_area_state.reconcile_translation_area(st.session_state)
if st.button("post-result action"):
    st.rerun()
area_mode = st.radio(
    "Area",
    translation_area_state.AREA_OPTIONS,
    index=None,
    key=translation_area_state.AREA_WIDGET_KEY,
)
if area_mode == translation_area_state.SELECT_AREA:
    st.session_state.setdefault("select_area_confirmed_crop_box", (100, 120, 700, 820))
"""
        ).run()
        app.radio[0].set_value(translation_area_state.SELECT_AREA).run()
        crop_box = app.session_state["select_area_confirmed_crop_box"]

        app.button[0].click().run()

        self.assertEqual(
            app.session_state[translation_area_state.AREA_WIDGET_KEY],
            translation_area_state.SELECT_AREA,
        )
        self.assertEqual(
            app.session_state[translation_area_state.AREA_STATE_KEY],
            translation_area_state.SELECT_AREA,
        )
        self.assertEqual(
            app.session_state["select_area_confirmed_crop_box"], crop_box
        )
        self.assertEqual(list(app.warning), [])

    def test_post_result_actions_preserve_select_area_signature(self):
        crop_box = (100, 120, 700, 820)
        stored_signature = signature(translation_area_state.SELECT_AREA, crop_box)
        for action in ("png", "txt", "diagnostic", "analytics", "harmless_rerun"):
            with self.subTest(action=action):
                state = {
                    translation_area_state.AREA_WIDGET_KEY: (
                        translation_area_state.SELECT_AREA
                    ),
                    "select_area_confirmed_crop_box": crop_box,
                }
                translation_area_state.reconcile_translation_area(state)

                # A short-circuit run omits the radio, but not canonical crop state.
                state.pop(translation_area_state.AREA_WIDGET_KEY)
                current_area = translation_area_state.reconcile_translation_area(
                    state
                )
                current_signature = signature(
                    current_area, state["select_area_confirmed_crop_box"]
                )

                self.assertEqual(
                    result_delivery.differing_signature_fields(
                        stored_signature, current_signature
                    ),
                    (),
                )

    def test_whole_pattern_survives_post_result_actions(self):
        full_box = (0, 0, 2000, 2000)
        stored_signature = signature(translation_area_state.WHOLE_PATTERN, full_box)
        state = {
            translation_area_state.AREA_WIDGET_KEY: (
                translation_area_state.WHOLE_PATTERN
            )
        }
        translation_area_state.reconcile_translation_area(state)

        state.pop(translation_area_state.AREA_WIDGET_KEY)
        current_area = translation_area_state.reconcile_translation_area(state)

        self.assertEqual(
            result_delivery.differing_signature_fields(
                stored_signature, signature(current_area, full_box)
            ),
            (),
        )

    def test_genuine_area_change_still_invalidates_result(self):
        crop_box = (100, 120, 700, 820)
        stored_signature = signature(translation_area_state.SELECT_AREA, crop_box)
        state = {
            translation_area_state.AREA_WIDGET_KEY: translation_area_state.SELECT_AREA
        }
        translation_area_state.reconcile_translation_area(state)

        state[translation_area_state.AREA_WIDGET_KEY] = (
            translation_area_state.WHOLE_PATTERN
        )
        current_area = translation_area_state.reconcile_translation_area(state)
        current_signature = signature(current_area, (0, 0, 2000, 2000))

        self.assertEqual(
            result_delivery.differing_signature_fields(
                stored_signature, current_signature
            ),
            ("area_mode", "crop_box", "downscale_flag", "downscale_option"),
        )

    def test_genuine_crop_change_still_invalidates_result(self):
        stored = signature(
            translation_area_state.SELECT_AREA, (100, 120, 700, 820)
        )
        current = signature(
            translation_area_state.SELECT_AREA, (110, 120, 700, 820)
        )

        self.assertEqual(
            result_delivery.differing_signature_fields(stored, current),
            ("crop_box",),
        )

    def test_area_reconciliation_precedes_analytics_short_circuit(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "pattern_translator"
            / "app.py"
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
        self.assertIn("index=None", source[area_widget - 180:area_widget + 180])


if __name__ == "__main__":
    unittest.main()
