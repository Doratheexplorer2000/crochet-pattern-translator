from __future__ import annotations

import os
from pathlib import Path

import streamlit.components.v1 as components


_FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
_plausible_event_component = components.declare_component(
    "crochet_plausible_event",
    path=str(_FRONTEND_DIR),
)


def emit_plausible_event(event_name: str, event_id: str, *, key: str) -> None:
    """Queue one browser-only Plausible event when tracking is configured."""
    script_url = os.getenv("PUBLIC_PLAUSIBLE_SCRIPT_URL", "").strip()
    if not script_url or not event_name or not event_id:
        return
    try:
        _plausible_event_component(
            event_name=event_name,
            event_id=event_id,
            script_url=script_url,
            key=key,
            default=None,
        )
    except Exception:
        # Analytics must never affect application behavior.
        return
