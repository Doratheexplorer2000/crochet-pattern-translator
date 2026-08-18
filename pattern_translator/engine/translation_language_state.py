"""Stable translation-language state across Streamlit widget cleanup reruns."""

from collections.abc import MutableMapping
from typing import Any, Dict


LANGUAGE_OPTIONS = (
    "English — US",
    "English — UK",
    "Traditional Chinese",
    "Simplified Chinese",
    "Japanese",
)
DEFAULT_LANGUAGE = "Traditional Chinese"

SOURCE_WIDGET_KEY = "source_language_selector"
TARGET_WIDGET_KEY = "target_language_selector"
SOURCE_STATE_KEY = "rc3_source_language"
TARGET_STATE_KEY = "rc3_target_language"


def _reconcile_language(
    session_state: MutableMapping[str, Any],
    *,
    widget_key: str,
    state_key: str,
) -> str:
    """Restore a cleaned-up widget key or accept a genuine widget change."""
    widget_value = session_state.get(widget_key)
    stable_value = session_state.get(state_key)

    if widget_value in LANGUAGE_OPTIONS:
        selected = str(widget_value)
    elif stable_value in LANGUAGE_OPTIONS:
        selected = str(stable_value)
        session_state[widget_key] = selected
    else:
        selected = DEFAULT_LANGUAGE
        session_state[widget_key] = selected

    session_state[state_key] = selected
    return selected


def reconcile_translation_languages(
    session_state: MutableMapping[str, Any],
) -> Dict[str, str]:
    """Return canonical source/target values while hydrating their widget keys."""
    return {
        "source": _reconcile_language(
            session_state,
            widget_key=SOURCE_WIDGET_KEY,
            state_key=SOURCE_STATE_KEY,
        ),
        "target": _reconcile_language(
            session_state,
            widget_key=TARGET_WIDGET_KEY,
            state_key=TARGET_STATE_KEY,
        ),
    }
