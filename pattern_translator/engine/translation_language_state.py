"""Stable translation-language state across Streamlit widget cleanup reruns."""

from collections.abc import MutableMapping
from typing import Any, Dict, Optional


LANGUAGE_OPTIONS = (
    "English — US",
    "English — UK",
    "Traditional Chinese",
    "Simplified Chinese",
    "Japanese",
)
SOURCE_WIDGET_KEY = "source_language_selector"
TARGET_WIDGET_KEY = "target_language_selector"
SOURCE_STATE_KEY = "rc3_source_language"
TARGET_STATE_KEY = "rc3_target_language"


def _reconcile_language(
    session_state: MutableMapping[str, Any],
    *,
    widget_key: str,
    state_key: str,
) -> Optional[str]:
    """Hydrate presentation state from the canonical language selection."""
    stable_value = session_state.get(state_key)
    selected = str(stable_value) if stable_value in LANGUAGE_OPTIONS else None
    session_state[state_key] = selected
    if session_state.get(widget_key) != selected:
        session_state[widget_key] = selected
    return selected


def _accept_widget_change(
    session_state: MutableMapping[str, Any],
    *,
    widget_key: str,
    state_key: str,
) -> Optional[str]:
    """Commit an explicit widget callback value to canonical state."""
    widget_value = session_state.get(widget_key)
    selected = str(widget_value) if widget_value in LANGUAGE_OPTIONS else None
    session_state[state_key] = selected
    return selected


def accept_source_language_change(
    session_state: MutableMapping[str, Any],
) -> Optional[str]:
    return _accept_widget_change(
        session_state,
        widget_key=SOURCE_WIDGET_KEY,
        state_key=SOURCE_STATE_KEY,
    )


def accept_target_language_change(
    session_state: MutableMapping[str, Any],
) -> Optional[str]:
    return _accept_widget_change(
        session_state,
        widget_key=TARGET_WIDGET_KEY,
        state_key=TARGET_STATE_KEY,
    )


def reconcile_translation_languages(
    session_state: MutableMapping[str, Any],
) -> Dict[str, Optional[str]]:
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
