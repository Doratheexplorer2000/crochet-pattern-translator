"""Stable translation-area state across Streamlit widget cleanup reruns."""

from collections.abc import MutableMapping
from typing import Any


WHOLE_PATTERN = "Whole Pattern"
SELECT_AREA = "Select Area"
AREA_OPTIONS = (WHOLE_PATTERN, SELECT_AREA)
AREA_WIDGET_KEY = "translation_area_mode_radio"
AREA_STATE_KEY = "rc3_translation_area_mode"


def set_translation_area(
    session_state: MutableMapping[str, Any], area_mode: str
) -> str:
    """Set both canonical and not-yet-rendered widget area state."""
    selected = area_mode if area_mode in AREA_OPTIONS else WHOLE_PATTERN
    session_state[AREA_STATE_KEY] = selected
    session_state[AREA_WIDGET_KEY] = selected
    return selected


def reconcile_translation_area(session_state: MutableMapping[str, Any]) -> str:
    """Restore a cleaned-up area widget or accept a genuine widget change."""
    widget_value = session_state.get(AREA_WIDGET_KEY)
    stable_value = session_state.get(AREA_STATE_KEY)

    if widget_value in AREA_OPTIONS:
        selected = str(widget_value)
        session_state[AREA_STATE_KEY] = selected
        return selected
    if stable_value in AREA_OPTIONS:
        return set_translation_area(session_state, str(stable_value))
    return set_translation_area(session_state, WHOLE_PATTERN)
