import unittest
from pathlib import Path

from pattern_translator.engine import result_delivery
from pattern_translator.engine import translation_language_state
from streamlit.testing.v1 import AppTest


def signature(target: str, *, source: str = "Traditional Chinese", area: str = "Whole Pattern"):
    return (
        "image-signature",
        source,
        target,
        area,
        (0, 0, 100, 100),
        (False, "Original / no resize", "Auto"),
    )


class TranslationLanguageStateTests(unittest.TestCase):
    def test_streamlit_151_short_circuit_rerun_restores_target_widget(self):
        app = AppTest.from_string(
            """
import streamlit as st
from pattern_translator.engine import translation_language_state

translation_language_state.reconcile_translation_languages(st.session_state)
if st.button("post-result action"):
    st.rerun()
st.selectbox(
    "Target",
    translation_language_state.LANGUAGE_OPTIONS,
    index=2,
    key=translation_language_state.TARGET_WIDGET_KEY,
)
"""
        ).run()
        app.selectbox[0].select("English — UK").run()

        self.assertEqual(
            app.session_state[translation_language_state.TARGET_WIDGET_KEY],
            "English — UK",
        )
        self.assertEqual(
            app.session_state[translation_language_state.TARGET_STATE_KEY],
            "English — UK",
        )

        app.button[0].click().run()

        self.assertEqual(
            app.session_state[translation_language_state.TARGET_WIDGET_KEY],
            "English — UK",
        )
        self.assertEqual(
            app.session_state[translation_language_state.TARGET_STATE_KEY],
            "English — UK",
        )

    def test_all_target_languages_survive_widget_cleanup_rerun(self):
        for target in translation_language_state.LANGUAGE_OPTIONS:
            with self.subTest(target=target):
                state = {
                    translation_language_state.TARGET_WIDGET_KEY: target,
                    translation_language_state.SOURCE_WIDGET_KEY: "Japanese",
                }
                translation_language_state.reconcile_translation_languages(state)
                stored_signature = signature(target, source="Japanese")

                # Streamlit removes widget keys after a run exits before rendering them.
                state.pop(translation_language_state.TARGET_WIDGET_KEY)
                state.pop(translation_language_state.SOURCE_WIDGET_KEY)
                restored = translation_language_state.reconcile_translation_languages(state)
                current_signature = signature(
                    restored["target"], source=restored["source"]
                )

                self.assertEqual(stored_signature, current_signature)
                self.assertEqual(
                    state[translation_language_state.TARGET_WIDGET_KEY], target
                )
                self.assertEqual(
                    state[translation_language_state.SOURCE_WIDGET_KEY], "Japanese"
                )

    def test_post_result_actions_preserve_target_signature(self):
        for action in ("png", "txt", "diagnostic", "harmless_rerun"):
            for area in ("Whole Pattern", "Select Area"):
                with self.subTest(action=action, area=area):
                    state = {
                        translation_language_state.TARGET_WIDGET_KEY: "English — UK",
                        translation_language_state.SOURCE_WIDGET_KEY: "Japanese",
                    }
                    translation_language_state.reconcile_translation_languages(state)
                    stored_signature = signature(
                        "English — UK", source="Japanese", area=area
                    )

                    # Each action causes a rerun; analytics can short-circuit before widgets.
                    state.pop(translation_language_state.TARGET_WIDGET_KEY)
                    state.pop(translation_language_state.SOURCE_WIDGET_KEY)
                    current = translation_language_state.reconcile_translation_languages(
                        state
                    )

                    self.assertEqual(
                        result_delivery.differing_signature_fields(
                            stored_signature,
                            signature(
                                current["target"],
                                source=current["source"],
                                area=area,
                            ),
                        ),
                        (),
                    )

    def test_genuine_target_change_still_mismatches(self):
        state = {
            translation_language_state.TARGET_WIDGET_KEY: "English — US",
            translation_language_state.SOURCE_WIDGET_KEY: "Japanese",
        }
        translation_language_state.reconcile_translation_languages(state)
        stored_signature = signature("English — US", source="Japanese")

        state[translation_language_state.TARGET_WIDGET_KEY] = "Simplified Chinese"
        current = translation_language_state.reconcile_translation_languages(state)

        self.assertEqual(current["target"], "Simplified Chinese")
        self.assertEqual(
            result_delivery.differing_signature_fields(
                stored_signature,
                signature(current["target"], source=current["source"]),
            ),
            ("target_language",),
        )

    def test_interface_language_does_not_change_translation_target(self):
        for interface_language in ("en", "zh-Hant", "zh-Hans", "ja"):
            with self.subTest(interface_language=interface_language):
                state = {
                    "ui_lang": interface_language,
                    translation_language_state.TARGET_WIDGET_KEY: "Japanese",
                    translation_language_state.SOURCE_WIDGET_KEY: "English — US",
                }
                translation_language_state.reconcile_translation_languages(state)
                state.pop(translation_language_state.TARGET_WIDGET_KEY)
                state["ui_lang"] = "zh-Hant"

                current = translation_language_state.reconcile_translation_languages(
                    state
                )

                self.assertEqual(current["target"], "Japanese")

    def test_source_and_structural_signature_invalidation_remain_unchanged(self):
        stored = signature("English — UK", source="Japanese")
        changed_source = signature("English — UK", source="Traditional Chinese")
        changed_area = signature(
            "English — UK", source="Japanese", area="Select Area"
        )
        changed_image = list(stored)
        changed_image[0] = "different-image"
        changed_crop = list(stored)
        changed_crop[4] = (1, 2, 80, 90)

        self.assertEqual(
            result_delivery.differing_signature_fields(stored, changed_source),
            ("source_language",),
        )
        self.assertEqual(
            result_delivery.differing_signature_fields(stored, changed_area),
            ("area_mode",),
        )
        self.assertEqual(
            result_delivery.differing_signature_fields(stored, tuple(changed_image)),
            ("image_signature",),
        )
        self.assertEqual(
            result_delivery.differing_signature_fields(stored, tuple(changed_crop)),
            ("crop_box",),
        )

    def test_reconciliation_runs_before_analytics_short_circuit_and_widgets(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "pattern_translator"
            / "app.py"
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
