"""Minimal FastAPI HTTP boundary for Pattern Translator image translation."""

from __future__ import annotations

import base64
import io
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps

from pattern_translator.engine import result_delivery as result_delivery_engine
from pattern_translator.engine import translation_area_state as translation_area_state_engine
from pattern_translator.engine import translation_language_state as translation_language_state_engine
from pattern_translator.translation_service import (
    CSV_TERM_CACHE_STATS,
    NORMALIZED_LOOKUP_INDEX_STATS,
    TranslateImageRequest,
    assess_image_quality,
    get_quality_status,
    load_database_dataframe,
    prepare_translation_dataframe,
    translate_image,
)

app = FastAPI(title="Pattern Translator API")
_WEB_DIRECTORY = Path(__file__).resolve().parent / "web"
app.mount("/static", StaticFiles(directory=_WEB_DIRECTORY), name="static")

_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_SUPPORTED_PIL_FORMATS = {"JPEG", "MPO", "PNG", "WEBP"}
_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/x-png",
    "image/webp",
}
_GENERIC_CONTENT_TYPES = {"application/octet-stream"}
_DEFAULT_OCR_RESIZE_TEST = "1000 px"
_DEFAULT_INTERFACE_LANGUAGE = "English"
_DEFAULT_DIAGNOSTIC_PLATFORM = "http-api"
_DEFAULT_DIAGNOSTIC_SESSION_GENERATION = "http-api"
_APP_VERSION = "Pattern OCR Translator (Beta RC26)"
_MAX_DIAGNOSTIC_REQUEST_BYTES = 4 * 1024 * 1024
_UI_LANGUAGE_LABELS = {
    "en": "English",
    "zh-Hant": "Traditional Chinese",
    "zh-Hans": "Simplified Chinese",
    "ja": "Japanese",
}


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
    generic_type_with_supported_extension = (
        content_type in _GENERIC_CONTENT_TYPES and extension in _ALLOWED_EXTENSIONS
    )
    if (
        content_type
        and content_type not in _ALLOWED_CONTENT_TYPES
        and not generic_type_with_supported_extension
    ):
        raise HTTPException(status_code=400, detail="Unsupported image format")
    try:
        with Image.open(io.BytesIO(raw_bytes)) as opened:
            if opened.format not in _SUPPORTED_PIL_FORMATS:
                raise HTTPException(status_code=400, detail="Unsupported image format")
            return ImageOps.exif_transpose(opened).convert("RGB")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image")


def _read_uploaded_bytes(upload: UploadFile) -> bytes:
    try:
        raw_bytes = upload.file.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image")
    if len(raw_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Image too large")
    return raw_bytes


def _parse_optional_coordinate(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid crop coordinates")


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


def _quality_details(image: Image.Image) -> Dict[str, Any]:
    errors, warnings, metrics = assess_image_quality(image)
    level, _status_label, _message = get_quality_status(errors, warnings)
    return {
        "level": level,
        "label": level.capitalize(),
        "requires_confirmation": level == "poor",
        "metrics": metrics,
        "errors": errors,
        "warnings": warnings,
    }


def _quality_response(
    *,
    request_id: str,
    area_mode: str,
    crop_box: Tuple[int, int, int, int],
    quality: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "request_id": request_id,
        "area_mode": area_mode,
        "crop_box": list(crop_box),
        "quality": quality,
    }


def _image_quality_error(status_code: int, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": "Image quality assessment failed",
            "request_id": request_id,
        },
    )


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
    quality: Dict[str, Any],
) -> TranslateImageRequest:
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
        quality_metrics=dict(quality["metrics"]),
        quality_errors=list(quality["errors"]),
        quality_warnings=list(quality["warnings"]),
        quality_label=str(quality["label"]),
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
    terminology_dataframe,
    quality: Dict[str, Any],
) -> Dict[str, Any]:
    primary = result.primary_result
    analytics = result.analytics
    timings = primary.get("timings", {})
    try:
        diagnostic_context = result_delivery_engine.create_diagnostic_snapshot(
            primary,
            terminology_row_count=len(terminology_dataframe),
            csv_term_cache_stats=dict(CSV_TERM_CACHE_STATS),
            normalized_lookup_index_stats=dict(NORMALIZED_LOOKUP_INDEX_STATS),
        )
    except Exception:
        diagnostic_context = None
    return {
        "request_id": request_id,
        "source_mode": source_mode,
        "output_mode": output_mode,
        "area_mode": area_mode,
        "crop_box": list(crop_box),
        "quality": quality,
        "raw_ocr_text": primary.get("raw_ocr_text", ""),
        "readable_translation": primary.get("readable_translation", ""),
        "translation_txt": primary.get("translation_txt", ""),
        "overlay_png": _overlay_png_payload(primary.get("overlay_png")),
        "diagnostic_context": diagnostic_context,
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


def _diagnostic_error(status_code: int, request_id: str) -> JSONResponse:
    message = (
        "Invalid diagnostic request"
        if status_code == 400
        else "Diagnostic report failed"
    )
    return JSONResponse(
        status_code=status_code,
        content={"error": message, "request_id": request_id},
    )


async def _read_bounded_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > _MAX_DIAGNOSTIC_REQUEST_BYTES:
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid diagnostic request")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > _MAX_DIAGNOSTIC_REQUEST_BYTES:
            raise HTTPException(status_code=400, detail="Invalid diagnostic request")
    return bytes(body)


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


@app.post("/api/v1/image-quality")
def image_quality(
    image: Optional[UploadFile] = File(None),
    area_mode: str = Form(translation_area_state_engine.WHOLE_PATTERN),
    crop_left: Optional[str] = Form(None),
    crop_top: Optional[str] = Form(None),
    crop_right: Optional[str] = Form(None),
    crop_bottom: Optional[str] = Form(None),
) -> Dict[str, Any]:
    request_id = uuid.uuid4().hex
    try:
        if image is None:
            raise HTTPException(status_code=400, detail="Invalid image")
        area_mode = _validate_area_mode(area_mode)
        raw_bytes = _read_uploaded_bytes(image)
        decoded_image = _decode_uploaded_image(image, raw_bytes)
        crop_box = _resolve_crop_box(
            area_mode,
            decoded_image,
            _parse_optional_coordinate(crop_left),
            _parse_optional_coordinate(crop_top),
            _parse_optional_coordinate(crop_right),
            _parse_optional_coordinate(crop_bottom),
        )
        working_image = (
            _crop_image(decoded_image, crop_box)
            if area_mode == translation_area_state_engine.SELECT_AREA
            else decoded_image
        )
        quality = _quality_details(working_image)
    except HTTPException as error:
        return _image_quality_error(error.status_code, request_id)
    except Exception:
        return _image_quality_error(500, request_id)

    return _quality_response(
        request_id=request_id,
        area_mode=area_mode,
        crop_box=crop_box,
        quality=quality,
    )


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
    force_run: bool = Form(False),
) -> Dict[str, Any]:
    request_id = uuid.uuid4().hex
    source_mode = _validate_language(source_mode, "source_mode")
    output_mode = _validate_language(output_mode, "output_mode")
    area_mode = _validate_area_mode(area_mode)

    image_load_start = time.perf_counter()
    raw_bytes = _read_uploaded_bytes(image)
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
        quality = _quality_details(working_image)
    except Exception:
        return _image_quality_error(500, request_id)
    if quality["requires_confirmation"] and not force_run:
        content = _quality_response(
            request_id=request_id,
            area_mode=area_mode,
            crop_box=crop_box,
            quality=quality,
        )
        content["error"] = "Image quality confirmation required"
        return JSONResponse(status_code=409, content=content)

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
        quality=quality,
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
        df,
        quality,
    )


@app.post("/api/v1/diagnostic-report")
async def diagnostic_report(request: Request):
    request_id = uuid.uuid4().hex
    try:
        raw_body = await _read_bounded_body(request)
        payload = json.loads(raw_body)
        if not isinstance(payload, dict):
            raise ValueError
        ui_lang = payload.get("ui_lang")
        if ui_lang not in _UI_LANGUAGE_LABELS:
            raise ValueError
        user_agent = str(request.headers.get("user-agent", "") or "Not captured")
        user_agent = user_agent.replace("\r", " ").replace("\n", " ")[:512]
        restored = result_delivery_engine.restore_diagnostic_snapshot(
            payload.get("diagnostic_context"),
            interface_language=_UI_LANGUAGE_LABELS[ui_lang],
            platform=user_agent,
        )
    except Exception:
        return _diagnostic_error(400, request_id)

    try:
        report_text = result_delivery_engine.build_deferred_diagnostic_report(
            restored.result,
            terminology_row_count=restored.terminology_row_count,
            csv_term_cache_stats=restored.csv_term_cache_stats,
            normalized_lookup_index_stats=restored.normalized_lookup_index_stats,
            app_version=_APP_VERSION,
        )
    except Exception:
        return _diagnostic_error(500, request_id)

    filename = result_delivery_engine.diagnostic_report_filename(_APP_VERSION)
    return PlainTextResponse(
        report_text,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
