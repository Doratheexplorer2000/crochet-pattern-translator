from __future__ import annotations

import base64
import io
import math
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import streamlit.components.v1 as components
from PIL import Image


_FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
_custom_cropper_component = components.declare_component(
    "crochet_custom_select_area",
    path=str(_FRONTEND_DIR),
)


def _image_data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _validated_component_result(
    payload: Any,
    image_signature: str,
) -> Optional[Dict[str, object]]:
    if not isinstance(payload, dict):
        return None
    if str(payload.get("image_signature") or "") != image_signature:
        return None

    action = str(payload.get("action") or "")
    action_id = str(payload.get("action_id") or "")
    if action == "cancel":
        return {"action": action, "action_id": action_id}
    if action != "confirm":
        return None

    box = payload.get("box")
    if not isinstance(box, dict):
        return None
    try:
        values = {
            name: float(box[name])
            for name in ("left", "top", "width", "height")
        }
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in values.values()):
        return None
    if values["width"] <= 0 or values["height"] <= 0:
        return None

    return {
        "action": action,
        "action_id": action_id,
        "box": values,
    }


def custom_select_area(
    image: Image.Image,
    initial_box: Tuple[int, int, int, int],
    strings: Mapping[str, str],
    *,
    image_signature: str,
    key: str,
) -> Optional[Dict[str, object]]:
    left, top, right, bottom = initial_box
    payload = _custom_cropper_component(
        image_data=_image_data_url(image),
        image_width=image.width,
        image_height=image.height,
        image_signature=image_signature,
        initial_box={
            "left": left,
            "top": top,
            "width": right - left,
            "height": bottom - top,
        },
        min_crop_size=50,
        strings=dict(strings),
        key=key,
        default=None,
    )
    return _validated_component_result(payload, image_signature)
