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


def accept_translation_area_change(
    session_state: MutableMapping[str, Any],
) -> str:
    """Commit an explicit area-widget callback value to canonical state."""
    widget_value = session_state.get(AREA_WIDGET_KEY)
    if widget_value not in AREA_OPTIONS:
        return str(session_state.get(AREA_STATE_KEY) or WHOLE_PATTERN)
    selected = str(widget_value)
    session_state[AREA_STATE_KEY] = selected
    return selected


def reconcile_translation_area(session_state: MutableMapping[str, Any]) -> str:
    """Hydrate the area widget from canonical semantic state."""
    stable_value = session_state.get(AREA_STATE_KEY)
    selected = str(stable_value) if stable_value in AREA_OPTIONS else WHOLE_PATTERN
    session_state[AREA_STATE_KEY] = selected
    if session_state.get(AREA_WIDGET_KEY) != selected:
        session_state[AREA_WIDGET_KEY] = selected
    return selected
