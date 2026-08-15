from __future__ import annotations

import base64
import binascii
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

import streamlit.components.v1 as components
from PIL import Image, UnidentifiedImageError


_FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
_custom_upload_component = components.declare_component(
    "crochet_custom_image_upload",
    path=str(_FRONTEND_DIR),
)

_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class UploadedImageBytes(BytesIO):
    """BytesIO upload adapter with public file metadata."""

    def __init__(self, data: bytes, name: str, mime_type: str, action_id: str = "") -> None:
        super().__init__(data)
        self.name = name
        self.type = mime_type
        self.size = len(data)
        self.action_id = action_id


def _decode_upload_payload(
    payload: Any,
    messages: Mapping[str, str],
    accepted_action_id: str = "",
) -> Tuple[Optional[UploadedImageBytes], Optional[str], bool]:
    def message(key: str) -> str:
        return str(messages.get(key) or "")

    if payload is None:
        return None, None, False
    if not isinstance(payload, dict):
        return None, message("error_unreadable"), False

    if payload.get("removed"):
        return None, None, True

    if payload.get("acknowledged_action_id"):
        return None, None, False

    action_id = str(payload.get("action_id") or "")
    if accepted_action_id and action_id == accepted_action_id:
        return None, None, False

    frontend_error_code = str(payload.get("error_code") or "")
    if frontend_error_code:
        # The component already renders frontend validation next to the control.
        return None, None, False

    name = Path(str(payload.get("name") or "uploaded-image")).name
    mime_type = str(payload.get("type") or "").lower()
    extension = Path(name).suffix.lower()
    if extension not in _ALLOWED_EXTENSIONS:
        return None, message("error_unsupported"), False
    if mime_type and mime_type not in _ALLOWED_MIME_TYPES:
        return None, message("error_unsupported"), False

    encoded_data = payload.get("data_base64")
    if not encoded_data:
        return None, message("error_empty"), False
    try:
        data = base64.b64decode(str(encoded_data), validate=True)
    except (binascii.Error, ValueError):
        return None, message("error_unreadable"), False

    if not data:
        return None, message("error_empty"), False
    if len(data) > _MAX_UPLOAD_BYTES:
        return None, message("error_too_large"), False

    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        return None, message("error_invalid"), False

    return UploadedImageBytes(
        data,
        name,
        mime_type,
        action_id=action_id,
    ), None, False


def snapshot_uploaded_image(uploaded_image: UploadedImageBytes) -> dict[str, Any]:
    """Keep one accepted upload in authoritative Streamlit session state."""
    return {
        "data": uploaded_image.getvalue(),
        "name": str(uploaded_image.name or "uploaded-image"),
        "type": str(uploaded_image.type or ""),
        "action_id": str(uploaded_image.action_id or ""),
    }


def restore_uploaded_image(snapshot: Any) -> Optional[UploadedImageBytes]:
    """Restore an already validated upload without decoding its base64 again."""
    if not isinstance(snapshot, Mapping):
        return None
    data = snapshot.get("data")
    if not isinstance(data, bytes) or not data:
        return None
    return UploadedImageBytes(
        data,
        Path(str(snapshot.get("name") or "uploaded-image")).name,
        str(snapshot.get("type") or ""),
        action_id=str(snapshot.get("action_id") or ""),
    )


def custom_image_uploader(
    strings: Mapping[str, str],
    *,
    key: str,
    active_image_present: bool = False,
    active_image_name: str = "",
    accepted_action_id: str = "",
) -> Tuple[Optional[UploadedImageBytes], Optional[str], bool]:
    payload = _custom_upload_component(
        strings=dict(strings),
        allowed_extensions=sorted(extension.lstrip(".") for extension in _ALLOWED_EXTENSIONS),
        allowed_mime_types=sorted(_ALLOWED_MIME_TYPES),
        max_upload_bytes=_MAX_UPLOAD_BYTES,
        active_image_present=bool(active_image_present),
        active_image_name=str(active_image_name or ""),
        accepted_action_id=str(accepted_action_id or ""),
        key=key,
        default=None,
    )
    return _decode_upload_payload(payload, strings, accepted_action_id)
