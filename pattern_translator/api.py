"""Minimal FastAPI HTTP boundary for Pattern Translator image translation."""

from __future__ import annotations

import base64
import io
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from pattern_translator.engine import translation_area_state as translation_area_state_engine
from pattern_translator.engine import translation_language_state as translation_language_state_engine
from pattern_translator.translation_service import (
    TranslateImageRequest,
    load_database_dataframe,
    prepare_translation_dataframe,
    translate_image,
)

app = FastAPI(title="Pattern Translator API")
_WEB_DIRECTORY = Path(__file__).resolve().parent / "web"
app.mount("/static", StaticFiles(directory=_WEB_DIRECTORY), name="static")

_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_SUPPORTED_PIL_FORMATS = {"JPEG", "PNG", "WEBP"}
_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}
_DEFAULT_OCR_RESIZE_TEST = "1000 px"
_DEFAULT_INTERFACE_LANGUAGE = "English"
_DEFAULT_DIAGNOSTIC_PLATFORM = "http-api"
_DEFAULT_DIAGNOSTIC_SESSION_GENERATION = "http-api"
_DEFAULT_QUALITY_LABEL = "Not assessed"


def _validate_language(value: str, field_name: str) -> str:
    if value not in translation_language_state_engine.LANGUAGE_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported {field_name}",
        )
    return value


def _validate_area_mode(value: str) -> str:
    if value not in translation_area_state_engine.AREA_OPTIONS:
        raise HTTPException(status_code=400, detail="Unsupported area mode")
    return value


def _extension_for_upload(upload: UploadFile) -> str:
    filename = str(upload.filename or "").strip().lower()
    if "." in filename:
        return filename[filename.rfind(".") :]
    return ""


def _decode_uploaded_image(upload: UploadFile, raw_bytes: bytes) -> Image.Image:
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Invalid image")
    extension = _extension_for_upload(upload)
    content_type = str(upload.content_type or "").strip().lower()
    if extension and extension not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported image format")
    if content_type and content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image format")
    try:
        with Image.open(io.BytesIO(raw_bytes)) as opened:
            if opened.format not in _SUPPORTED_PIL_FORMATS:
                raise HTTPException(status_code=400, detail="Unsupported image format")
            return opened.convert("RGB")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image")


def _resolve_crop_box(
    area_mode: str,
    image: Image.Image,
    crop_left: Optional[int],
    crop_top: Optional[int],
    crop_right: Optional[int],
    crop_bottom: Optional[int],
) -> Tuple[int, int, int, int]:
    width, height = image.size
    if area_mode == translation_area_state_engine.WHOLE_PATTERN:
        return (0, 0, width, height)

    crop_values = (crop_left, crop_top, crop_right, crop_bottom)
    if any(value is None for value in crop_values):
        raise HTTPException(status_code=400, detail="Incomplete crop coordinates")

    left, top, right, bottom = (int(crop_left), int(crop_top), int(crop_right), int(crop_bottom))
    if not (0 <= left < right <= width):
        raise HTTPException(status_code=400, detail="Invalid crop coordinates")
    if not (0 <= top < bottom <= height):
        raise HTTPException(status_code=400, detail="Invalid crop coordinates")
    return (left, top, right, bottom)


def _crop_image(image: Image.Image, crop_box: Tuple[int, int, int, int]) -> Image.Image:
    left, top, right, bottom = crop_box
    return image.crop((left, top, right, bottom))


def _downscale_settings(working_image: Image.Image, ocr_resize_test: str) -> Tuple[bool, str]:
    resize_max_side = 1400
    if ocr_resize_test != "Auto":
        resize_match = re.search(r"(\d+)", ocr_resize_test)
        resize_max_side = int(resize_match.group(1)) if resize_match else 1400
    experimental_downscale = max(working_image.size) > resize_max_side
    downscale_max_height_option = (
        f"Max height {resize_max_side} px"
        if experimental_downscale
        else "Original / no resize"
    )
    return experimental_downscale, downscale_max_height_option


def _build_translate_request(
    *,
    image: Image.Image,
    selected_image: Image.Image,
    working_image: Image.Image,
    source_mode: str,
    output_mode: str,
    area_mode: str,
    crop_box: Tuple[int, int, int, int],
    df,
    index,
    request_id: str,
    image_load_seconds: float,
    crop_extraction_seconds: float,
    action_started: float,
    ocr_execution_start: float,
) -> TranslateImageRequest:
    width, height = image.size
    experimental_downscale, downscale_max_height_option = _downscale_settings(
        working_image,
        _DEFAULT_OCR_RESIZE_TEST,
    )
    return TranslateImageRequest(
        image=image,
        selected_image=selected_image,
        working_image=working_image,
        source_mode=source_mode,
        output_mode=output_mode,
        area_mode=area_mode,
        crop_box=crop_box,
        df=df,
        index=index,
        diagnostic_request_id=request_id,
        diagnostic_session_generation=_DEFAULT_DIAGNOSTIC_SESSION_GENERATION,
        action_started=action_started,
        image_load_seconds=image_load_seconds,
        crop_extraction_seconds=crop_extraction_seconds,
        quality_metrics={"width_px": width, "height_px": height},
        quality_errors=[],
        quality_warnings=[],
        quality_label=_DEFAULT_QUALITY_LABEL,
        experimental_downscale=experimental_downscale,
        downscale_max_height_option=downscale_max_height_option,
        ocr_resize_test=_DEFAULT_OCR_RESIZE_TEST,
        session_diagnostics={},
        diagnostic_events=[],
        diagnostic_platform=_DEFAULT_DIAGNOSTIC_PLATFORM,
        interface_language=_DEFAULT_INTERFACE_LANGUAGE,
        ocr_execution_start=ocr_execution_start,
    )


def _overlay_png_payload(overlay_png: Optional[bytes]) -> Optional[Dict[str, str]]:
    if overlay_png is None:
        return None
    return {
        "media_type": "image/png",
        "base64": base64.b64encode(overlay_png).decode("ascii"),
    }


def _serialize_success(
    request_id: str,
    source_mode: str,
    output_mode: str,
    area_mode: str,
    crop_box: Tuple[int, int, int, int],
    result,
) -> Dict[str, Any]:
    primary = result.primary_result
    analytics = result.analytics
    timings = primary.get("timings", {})
    return {
        "request_id": request_id,
        "source_mode": source_mode,
        "output_mode": output_mode,
        "area_mode": area_mode,
        "crop_box": list(crop_box),
        "raw_ocr_text": primary.get("raw_ocr_text", ""),
        "readable_translation": primary.get("readable_translation", ""),
        "translation_txt": primary.get("translation_txt", ""),
        "overlay_png": _overlay_png_payload(primary.get("overlay_png")),
        "ocr_finished_at": result.ocr_finished_at,
        "ocr_duration_seconds": result.ocr_duration_seconds,
        "ocr_time_sec": analytics.get("ocr_time_sec"),
        "translation_time_sec": analytics.get("translation_time_sec"),
        "ocr_box_count": analytics.get("ocr_box_count"),
        "timings": {
            "image_load": timings.get("Image load"),
            "crop_extraction": timings.get("Crop extraction"),
            "ocr": timings.get("OCR"),
            "translation_processing": timings.get("Translation processing"),
            "overlay_generation": timings.get("Overlay generation"),
            "total_runtime": timings.get("Total runtime"),
        },
    }


@app.get("/", include_in_schema=False)
def browser_ui() -> FileResponse:
    """Serve the local, framework-free Pattern Translator browser UI."""
    return FileResponse(_WEB_DIRECTORY / "index.html")


@app.get("/health", include_in_schema=False)
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/browser-config", include_in_schema=False)
def browser_config() -> Dict[str, str]:
    """Expose only explicitly public browser configuration."""
    return {
        "plausible_script_url": os.getenv(
            "PUBLIC_PLAUSIBLE_SCRIPT_URL",
            "",
        ).strip()
    }


@app.post("/api/v1/translate")
def translate_pattern(
    image: UploadFile = File(...),
    source_mode: str = Form(...),
    output_mode: str = Form(...),
    area_mode: str = Form(translation_area_state_engine.WHOLE_PATTERN),
    crop_left: Optional[int] = Form(None),
    crop_top: Optional[int] = Form(None),
    crop_right: Optional[int] = Form(None),
    crop_bottom: Optional[int] = Form(None),
) -> Dict[str, Any]:
    request_id = uuid.uuid4().hex
    source_mode = _validate_language(source_mode, "source_mode")
    output_mode = _validate_language(output_mode, "output_mode")
    area_mode = _validate_area_mode(area_mode)

    image_load_start = time.perf_counter()
    try:
        raw_bytes = image.file.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image")
    if len(raw_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Image too large")
    decoded_image = _decode_uploaded_image(image, raw_bytes)
    image_load_seconds = time.perf_counter() - image_load_start

    crop_box = _resolve_crop_box(
        area_mode,
        decoded_image,
        crop_left,
        crop_top,
        crop_right,
        crop_bottom,
    )

    crop_extract_start = time.perf_counter()
    if area_mode == translation_area_state_engine.SELECT_AREA:
        selected_image = _crop_image(decoded_image, crop_box)
    else:
        selected_image = decoded_image
    working_image = selected_image
    crop_extraction_seconds = time.perf_counter() - crop_extract_start

    try:
        full_df = load_database_dataframe()
        df, index = prepare_translation_dataframe(full_df, source_mode)
    except Exception:
        return JSONResponse(
            status_code=500,
            content={"error": "Translation failed", "request_id": request_id},
        )

    action_started = time.perf_counter()
    ocr_execution_start = time.perf_counter()
    request = _build_translate_request(
        image=decoded_image,
        selected_image=selected_image,
        working_image=working_image,
        source_mode=source_mode,
        output_mode=output_mode,
        area_mode=area_mode,
        crop_box=crop_box,
        df=df,
        index=index,
        request_id=request_id,
        image_load_seconds=image_load_seconds,
        crop_extraction_seconds=crop_extraction_seconds,
        action_started=action_started,
        ocr_execution_start=ocr_execution_start,
    )

    try:
        result = translate_image(request)
    except Exception:
        return JSONResponse(
            status_code=500,
            content={"error": "Translation failed", "request_id": request_id},
        )

    return _serialize_success(
        request_id,
        source_mode,
        output_mode,
        area_mode,
        crop_box,
        result,
    )
