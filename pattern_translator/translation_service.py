"""Framework-neutral Pattern Translator image translation service."""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import math
import os
import platform
import re
import sys
import tempfile
import threading
import time
import unicodedata
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from PIL import Image

from pattern_translator.engine import diagnostic_report as diagnostic_report_engine
from pattern_translator.engine import line_translation as line_translation_engine
from pattern_translator.engine import llm_fallback as llm_fallback_engine
from pattern_translator.engine import ocr_cleanup as ocr_cleanup_engine
from pattern_translator.engine import ocr_lines as ocr_lines_engine
from pattern_translator.engine import ocr_runtime as ocr_runtime_engine
from pattern_translator.engine import overlay as overlay_engine
from pattern_translator.engine import pattern_document as pattern_document_engine
from pattern_translator.engine import terminology as terminology_engine

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
KNOWLEDGE_BASE_DIR = REPO_ROOT / "knowledge_base"
SOURCE_CSV = KNOWLEDGE_BASE_DIR / "data" / "master_stitches.csv"
FALLBACK_CSV = KNOWLEDGE_BASE_DIR / "releases" / "database" / "stitches_1_8e.csv"

_TRANSLATION_PROFILE: ContextVar[Optional[Dict[str, Dict[str, float]]]] = ContextVar(
    "translation_profile",
    default=None,
)

_MIN_CONF_FOR_CLEAN_TEXT = 0.45


def _classify_image_quality(
    width: int,
    height: int,
    sharpness: float,
    contrast: float,
) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    shortest = min(width, height)
    longest = max(width, height)

    if longest < 1000 or shortest < 600:
        errors.append(
            "Image is probably too small for reliable OCR. Recommended: crop the pattern area and use an image at least 1000px wide, preferably 1500px+."
        )
    elif longest < 1500:
        warnings.append(
            "Image size is acceptable but not ideal. For small crochet text, 1500px+ on the longer side usually works better."
        )

    if sharpness < 60:
        errors.append(
            "Image appears blurry. Retake the photo or upload a sharper screenshot before running OCR."
        )
    elif sharpness < 120:
        warnings.append(
            "Image is slightly soft. OCR may confuse punctuation such as X.V, commas, colons, or R10/R11."
        )

    if contrast < 28:
        warnings.append(
            "Text contrast seems low. Fancy backgrounds, watermarks, or pale text may reduce OCR accuracy. Try cropping closer to the text area."
        )

    return errors, warnings


def assess_image_quality(
    image: Image.Image,
) -> Tuple[List[str], List[str], Dict[str, object]]:
    """Return the existing blocking issues, warnings, and quality metrics."""
    img_rgb = image.convert("RGB")
    width, height = img_rgb.size
    pixels = np.array(img_rgb)

    try:
        import cv2

        gray = cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        contrast = float(gray.std())
    except Exception:
        gray = np.dot(pixels[..., :3], [0.299, 0.587, 0.114])
        gradient_y, gradient_x = np.gradient(gray.astype(float))
        sharpness = float((gradient_x ** 2 + gradient_y ** 2).mean())
        contrast = float(gray.std())

    errors, warnings = _classify_image_quality(
        width,
        height,
        sharpness,
        contrast,
    )
    metrics = {
        "width_px": width,
        "height_px": height,
        "megapixels": round((width * height) / 1_000_000, 2),
        "sharpness_score": round(sharpness, 1),
        "contrast_score": round(contrast, 1),
    }
    return errors, warnings, metrics


def get_quality_status(
    errors: List[str],
    warnings: List[str],
) -> Tuple[str, str, str]:
    if errors:
        return "poor", "🔴 Poor", "Image quality may affect OCR accuracy."
    if warnings:
        return "fair", "🟡 Fair", "OCR may contain some errors."
    return "good", "🟢 Good", "Image quality looks suitable for OCR."


def load_database_dataframe() -> pd.DataFrame:
    csv_path = SOURCE_CSV if SOURCE_CSV.exists() else FALLBACK_CSV
    if not csv_path.exists():
        raise FileNotFoundError(f"Cannot find stitch database at {SOURCE_CSV}")
    return pd.read_csv(csv_path).fillna("")


def build_term_index(df: pd.DataFrame, source_mode: str) -> Dict[str, int]:
    return terminology_engine.build_term_index(df, source_mode)


def build_all_term_index(df: pd.DataFrame) -> Dict[str, int]:
    return terminology_engine.build_all_term_index(df)


def prepare_translation_dataframe(
    full_df: pd.DataFrame,
    source_mode: str,
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    df = terminology_engine.get_active_search_df(full_df)
    index = build_term_index(df, source_mode)
    all_term_index = build_all_term_index(df)
    df.attrs["all_term_index"] = all_term_index
    try:
        df.attrs["normalized_lookup_index"] = terminology_engine.build_normalized_lookup_index(
            index, all_term_index, source_mode
        )
    except Exception as error:
        NORMALIZED_LOOKUP_INDEX_STATS["index_error"] = str(error)
        df.attrs["normalized_lookup_index"] = {}
    return df, index


def log_app_ocr_timing(
    request_id: str,
    phase: str,
    *,
    elapsed_seconds: Optional[float] = None,
    outcome: str = "",
    session_generation: str = "",
    request_lifecycle: str = "",
    active_image: Optional[bool] = None,
    script_run_no: Optional[int] = None,
    visual_line_count: Optional[int] = None,
    eligible_line_count: Optional[int] = None,
    call_ordinal: Optional[int] = None,
    model: str = "",
    route: str = "",
    **diagnostic_fields: object,
) -> None:
    ocr_runtime_engine.log_ocr_timing(
        request_id,
        phase,
        elapsed_seconds=elapsed_seconds,
        outcome=outcome,
        session_generation=session_generation,
        request_lifecycle=request_lifecycle,
        active_image=active_image,
        script_run_no=script_run_no,
        visual_line_count=visual_line_count,
        eligible_line_count=eligible_line_count,
        call_ordinal=call_ordinal,
        model=model,
        route=route,
        **diagnostic_fields,
    )


def make_translation_profile() -> Dict[str, Dict[str, float]]:
    return {"timings": {}, "counts": {}}


def profile_count(name: str, amount: float = 1.0):
    profile = _TRANSLATION_PROFILE.get()
    if profile is None:
        return
    counts = profile.setdefault("counts", {})
    counts[name] = counts.get(name, 0.0) + amount


def profile_add_time(name: str, seconds: float):
    profile = _TRANSLATION_PROFILE.get()
    if profile is None:
        return
    timings = profile.setdefault("timings", {})
    timings[name] = timings.get(name, 0.0) + seconds


def profile_function(time_name: str, count_name: str):
    def decorator(func):
        def wrapped(*args, **kwargs):
            profile_count(count_name)
            profile_start = (
                time.perf_counter() if _TRANSLATION_PROFILE.get() is not None else None
            )
            try:
                return func(*args, **kwargs)
            finally:
                if profile_start is not None:
                    profile_add_time(time_name, time.perf_counter() - profile_start)
        return wrapped
    return decorator


terminology_engine.configure_profile_context(
    _TRANSLATION_PROFILE.get,
    profile_count,
    profile_add_time,
)
line_translation_engine.configure_profile_context(
    _TRANSLATION_PROFILE.get,
    profile_count,
    profile_add_time,
)
overlay_engine.configure_profile_context(
    _TRANSLATION_PROFILE.get,
    profile_count,
    profile_add_time,
)
ocr_lines_engine.configure_profile_context(
    _TRANSLATION_PROFILE.get,
    profile_count,
    profile_add_time,
)

def get_reader(lang_mode: str):
    import easyocr
    if lang_mode in ["Traditional Chinese", "Simplified Chinese", "Chinese"]:
        langs = ["ch_sim", "en"]
    elif lang_mode == "Japanese":
        langs = ["ja", "en"]
    else:
        langs = ["en"]
    return easyocr.Reader(langs, gpu=False)


def split_image_two_columns(image: Image.Image, overlap_percent: int = 20) -> Tuple[Image.Image, Image.Image]:
    """Split image into two OCR regions with centre overlap."""
    img = image.convert("RGB")
    w, h = img.size
    mid = w // 2
    overlap = int(w * overlap_percent / 100)
    left_end = min(w, mid + overlap // 2)
    right_start = max(0, mid - overlap // 2)
    left = img.crop((0, 0, left_end, h))
    right = img.crop((right_start, 0, w, h))
    return left, right


def make_column_guide_preview(image: Image.Image, overlap_percent: int = 20) -> Image.Image:
    """Return full image with a centre split guide and overlap zone for testing preview."""
    from PIL import ImageDraw
    img = image.convert("RGBA")
    w, h = img.size
    mid = w // 2
    overlap = int(w * overlap_percent / 100)
    x1 = max(0, mid - overlap // 2)
    x2 = min(w, mid + overlap // 2)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((x1, 0, x2, h), fill=(255, 80, 80, 38))
    line_width = max(2, w // 500)
    draw.line((mid, 0, mid, h), fill=(255, 60, 60, 210), width=line_width)
    return Image.alpha_composite(img, overlay).convert("RGB")


def min_conf_for_mode(lang_mode: str) -> float:
    # Chinese/Japanese OCR often returns lower confidence for mixed symbols like R10:(7X,V).
    # Keep more text, then let the pattern parser reject junk later.
    if lang_mode in ["Traditional Chinese", "Simplified Chinese", "Chinese"]:
        return 0.20
    if lang_mode == "Japanese":
        return 0.30
    return _MIN_CONF_FOR_CLEAN_TEXT

def run_ocr_single(image: Image.Image, lang_mode: str, source_label: str = "image", x_offset: int = 0) -> Tuple[List[str], pd.DataFrame]:
    reader = get_reader(lang_mode)
    arr = np.array(image.convert("RGB"))
    result = reader.readtext(arr, detail=1, paragraph=False)

    rows = []
    for item in result:
        box, text, conf = item
        clean = str(text).strip()
        if not clean:
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        local_x = float(sum(xs) / len(xs))
        min_x = float(min(xs))
        max_x = float(max(xs))
        min_y = float(min(ys))
        max_y = float(max(ys))
        rows.append({
            "source": source_label,
            "text": clean,
            "confidence": round(float(conf), 3),
            "x": round(local_x, 1),
            "global_x": round(local_x + x_offset, 1),
            "y": round(float(sum(ys) / len(ys)), 1),
            "min_x": round(min_x + x_offset, 1),
            "max_x": round(max_x + x_offset, 1),
            "min_y": round(min_y, 1),
            "max_y": round(max_y, 1),
        })

    rows = sorted(rows, key=lambda r: (r["y"], r["global_x"]))
    lines = [r["text"] for r in rows]
    return lines, pd.DataFrame(rows)


# -----------------------------
# PaddleOCR primary engine
# -----------------------------
def paddle_lang_from_mode(lang_mode: str) -> str:
    if lang_mode == "Japanese":
        return "japan"
    if lang_mode in ["Traditional Chinese", "Simplified Chinese", "Chinese"]:
        return "ch"
    return "en"

def _save_image_temp(image: Image.Image) -> str:
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    image.convert("RGB").save(path)
    return path


def _ocr_trace_event(trace: Optional[List[str]], message: str):
    if trace is not None:
        trace.append(f"{time.strftime('%H:%M:%S')} {message}")


def _image_size_dict(image: Image.Image) -> Dict[str, int]:
    width, height = image.size
    return {
        "width": int(width),
        "height": int(height),
        "pixels": int(width * height),
    }


def _debug_cell(value: object) -> str:
    """Normalize app-collected diagnostic metadata without depending on report rendering."""
    text = "" if value is None else str(value).strip()
    return text.replace("\n", " ")


def _safe_diagnostic_token(value: object) -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    return token[:80] or "unknown"


def _installed_package_version(distribution: str) -> str:
    try:
        return _safe_diagnostic_token(importlib_metadata.version(distribution))
    except importlib_metadata.PackageNotFoundError:
        return "not_installed"
    except Exception:
        return "unavailable"


def _log_paddle_failure(
    stage: str,
    error: Exception,
    image: Image.Image,
    image_path: Optional[str] = None,
    reader: object = None,
) -> None:
    """Log content-free runtime facts for otherwise opaque native Paddle failures."""
    width, height = image.size
    temp_exists = bool(image_path and os.path.isfile(image_path))
    temp_size = 0
    temp_valid = "not_checked"
    if temp_exists and image_path:
        try:
            temp_size = int(os.path.getsize(image_path))
            with Image.open(image_path) as temp_image:
                temp_image.verify()
            temp_valid = "yes"
        except Exception:
            temp_valid = "no"

    fields = {
        "outcome": "runtime_error",
        "stage": _safe_diagnostic_token(stage),
        "exception_type": _safe_diagnostic_token(type(error).__name__),
        "image_width": int(width),
        "image_height": int(height),
        "image_mode": _safe_diagnostic_token(image.mode),
        "temp_exists": str(temp_exists).lower(),
        "temp_size_bytes": temp_size,
        "temp_valid_png": temp_valid,
        "reader_class": _safe_diagnostic_token(type(reader).__name__) if reader is not None else "unavailable",
        "python": _safe_diagnostic_token(platform.python_version()),
        "machine": _safe_diagnostic_token(platform.machine()),
        "paddleocr": _installed_package_version("paddleocr"),
        "paddlex": _installed_package_version("paddlex"),
        "paddlepaddle": _installed_package_version("paddlepaddle"),
        "numpy": _installed_package_version("numpy"),
        "opencv": _installed_package_version("opencv-python-headless"),
    }
    details = " ".join(f"{key}={value}" for key, value in fields.items())
    print(f"[pattern_ocr] {details}", file=sys.stderr, flush=True)


def run_paddle_ocr_single(
    image: Image.Image,
    lang_mode: str,
    trace: Optional[List[str]] = None,
    diagnostics: Optional[Dict[str, object]] = None,
    diagnostic_request_id: Optional[str] = None,
) -> Tuple[str, pd.DataFrame, object, float]:
    if diagnostics is not None:
        diagnostics["run_paddle_ocr_single_calls"] = int(diagnostics.get("run_paddle_ocr_single_calls", 0)) + 1
        diagnostics["run_paddle_ocr_single_input"] = _image_size_dict(image)
    _ocr_trace_event(trace, "run_paddle_ocr_single start")
    lang = paddle_lang_from_mode(lang_mode)
    if diagnostics is not None:
        diagnostics["ocr_language_model"] = lang
        diagnostics["ocr_backend"] = "PaddleOCR"
        diagnostics["paddle_actual_loaded_image_size"] = "Not exposed by current PaddleOCR API"
    _ocr_trace_event(trace, "save temp PNG")
    temp_preparation_start = time.perf_counter()
    if diagnostic_request_id:
        log_app_ocr_timing(
            diagnostic_request_id,
            "temp_image_preparation_begin",
        )
    try:
        image_path = _save_image_temp(image)
    except Exception as error:
        _log_paddle_failure("temp_png_save", error, image)
        raise
    if diagnostic_request_id:
        log_app_ocr_timing(
            diagnostic_request_id,
            "temp_image_preparation_end",
            elapsed_seconds=time.perf_counter() - temp_preparation_start,
        )
    _ocr_trace_event(trace, "temp PNG saved")
    if diagnostics is not None:
        try:
            diagnostics["temp_png_size_bytes"] = os.path.getsize(image_path)
        except Exception:
            diagnostics["temp_png_size_bytes"] = "Not captured"
        try:
            with Image.open(image_path) as temp_img:
                diagnostics["temp_png_image"] = _image_size_dict(temp_img)
        except Exception:
            diagnostics["temp_png_image"] = "Not captured"
    try:
        _ocr_trace_event(trace, "PaddleOCR call start")
        worker_result = ocr_runtime_engine.get_process_ocr_manager().run_ocr(
            image_path,
            lang,
            diagnostic_request_id=diagnostic_request_id,
        )
        _ocr_trace_event(trace, "PaddleOCR call end")
    except Exception as error:
        failure_stage = getattr(error, "stage", "worker")
        _log_paddle_failure(failure_stage, error, image, image_path=image_path)
        raise
    finally:
        try:
            os.remove(image_path)
        except Exception:
            pass
    reader_metadata = worker_result["reader_metadata"]
    inference_seconds = float(worker_result["inference_seconds"])
    rows = worker_result["rows"]
    if diagnostics is not None:
        diagnostics["ocr_reader_class"] = _debug_cell(reader_metadata.get("class")) or "Not exposed by current PaddleOCR object"
        diagnostics["detector_model"] = _debug_cell(reader_metadata.get("detector_model")) or "Not exposed by current PaddleOCR object"
        diagnostics["recognizer_model"] = _debug_cell(reader_metadata.get("recognizer_model")) or "Not exposed by current PaddleOCR object"
        diagnostics["paddle_worker_recovered"] = "Yes" if worker_result.get("worker_recovered") else "No"
        diagnostics["paddle_worker_recycled"] = "Yes" if worker_result.get("worker_recycled") else "No"
    df = pd.DataFrame(rows)
    text = "\n".join(df["text"].astype(str).tolist()) if not df.empty else ""
    _ocr_trace_event(trace, "OCR results returned")
    return text, df, None, inference_seconds


def run_primary_ocr(
    image: Image.Image,
    lang_mode: str,
    compare_easyocr: bool = False,
    trace: Optional[List[str]] = None,
    diagnostics: Optional[Dict[str, object]] = None,
    diagnostic_request_id: Optional[str] = None,
) -> Dict[str, object]:
    """Use PaddleOCR as primary. Optionally run EasyOCR for debug comparison."""
    if diagnostics is not None:
        diagnostics["run_primary_ocr_calls"] = int(diagnostics.get("run_primary_ocr_calls", 0)) + 1
        diagnostics["run_primary_ocr_input"] = _image_size_dict(image)
    _ocr_trace_event(trace, "run_primary_ocr start")
    paddle_text, paddle_rows, paddle_raw, paddle_inference_seconds = run_paddle_ocr_single(
        image,
        lang_mode,
        trace=trace,
        diagnostics=diagnostics,
        diagnostic_request_id=diagnostic_request_id,
    )
    paddle_metrics = _ocr_candidate_metrics(paddle_rows)
    comparison_rows = [{"Engine": "PaddleOCR", **paddle_metrics}]
    easy_text = ""
    easy_rows = pd.DataFrame()

    if compare_easyocr:
        easy_lines, easy_rows = run_ocr_single(image, lang_mode, "EasyOCR")
        easy_text = "\n".join(easy_lines)
        easy_metrics = _ocr_candidate_metrics(easy_rows)
        comparison_rows.append({"Engine": "EasyOCR", **easy_metrics})

    comparison_df = pd.DataFrame(comparison_rows)
    return {
        "selected_name": "PaddleOCR",
        "selected_text": paddle_text,
        "selected_rows": paddle_rows,
        "comparison_df": comparison_df,
        "paddle_text": paddle_text,
        "easy_text": easy_text,
        "paddle_rows": paddle_rows,
        "easy_rows": easy_rows,
        "paddle_raw": paddle_raw,
        "paddle_inference_seconds": paddle_inference_seconds,
    }


# -----------------------------
# OCR candidate comparison
# -----------------------------
def preprocess_enhanced_for_ocr(image: Image.Image, scale: int = 2) -> Image.Image:
    """Make a second OCR candidate: upscale + grayscale + contrast + sharpen.

    This is intentionally a candidate, not a permanent replacement. Fancy pattern
    images vary a lot; sometimes original OCR is better, sometimes enhanced OCR is.
    """
    img = image.convert("RGB")
    w, h = img.size
    img = img.resize((w * scale, h * scale), Image.Resampling.LANCZOS)
    arr = np.array(img)
    try:
        import cv2
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        # Local contrast boost. Useful for screenshots with coloured/fancy backgrounds.
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        # Gentle sharpen; too much thresholding destroys punctuation like x.v.
        blur = cv2.GaussianBlur(gray, (0, 0), 1.0)
        sharp = cv2.addWeighted(gray, 1.45, blur, -0.45, 0)
        rgb = cv2.cvtColor(sharp, cv2.COLOR_GRAY2RGB)
        return Image.fromarray(rgb)
    except Exception:
        from PIL import ImageEnhance, ImageFilter
        img = img.convert("L")
        img = ImageEnhance.Contrast(img).enhance(1.6)
        img = img.filter(ImageFilter.SHARPEN)
        return img.convert("RGB")


def _scale_rows_back(rows: pd.DataFrame, scale: float) -> pd.DataFrame:
    if rows is None or rows.empty or scale == 1:
        return rows
    out = rows.copy()
    for col in ["x", "global_x", "y", "min_x", "max_x", "min_y", "max_y"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce") / scale
            out[col] = out[col].round(1)
    return out


def scale_ocr_rows_to_original(
    rows: Optional[pd.DataFrame],
    scale_x: float,
    scale_y: float,
) -> Optional[pd.DataFrame]:
    if rows is None or rows.empty or (scale_x == 1 and scale_y == 1):
        return rows
    out = rows.copy()
    for col in ["x", "global_x", "min_x", "max_x"]:
        if col in out.columns:
            out[col] = (pd.to_numeric(out[col], errors="coerce") * scale_x).round(1)
    for col in ["y", "min_y", "max_y"]:
        if col in out.columns:
            out[col] = (pd.to_numeric(out[col], errors="coerce") * scale_y).round(1)
    return out


def prepare_experimental_ocr_image(
    image: Image.Image,
    downscale_enabled: bool,
    max_height_option: str,
) -> Tuple[Image.Image, Dict[str, object]]:
    original_w, original_h = image.size
    diagnostics: Dict[str, object] = {
        "downscale_enabled": "Yes" if downscale_enabled else "No",
        "downscale_applied": "No",
        "requested_max_height": max_height_option,
        "original_ocr_input_width": original_w,
        "original_ocr_input_height": original_h,
        "original_ocr_input_megapixels": round((original_w * original_h) / 1_000_000, 3),
        "actual_paddleocr_image_width": original_w,
        "actual_paddleocr_image_height": original_h,
        "actual_paddleocr_megapixels": round((original_w * original_h) / 1_000_000, 3),
        "downscale_ratio": 1.0,
        "coordinate_scale_x": 1.0,
        "coordinate_scale_y": 1.0,
        "boxes_scaled_back_for_overlay": "No",
        "downscale_error": "",
    }
    if not downscale_enabled or max_height_option == "Original / no resize":
        return image, diagnostics
    max_height_match = re.search(r"(\d+)", max_height_option)
    if not max_height_match:
        return image, diagnostics
    max_side = int(max_height_match.group(1))
    original_longest_side = max(original_w, original_h)
    if original_longest_side <= max_side:
        return image, diagnostics
    try:
        ratio = max_side / float(original_longest_side)
        resized_w = max(1, int(round(original_w * ratio)))
        resized_h = max(1, int(round(original_h * ratio)))
        resized = image.resize((resized_w, resized_h), Image.Resampling.LANCZOS)
        diagnostics.update({
            "downscale_applied": "Yes",
            "actual_paddleocr_image_width": resized_w,
            "actual_paddleocr_image_height": resized_h,
            "actual_paddleocr_megapixels": round((resized_w * resized_h) / 1_000_000, 3),
            "downscale_ratio": round(ratio, 4),
            "coordinate_scale_x": round(original_w / float(resized_w), 6),
            "coordinate_scale_y": round(original_h / float(resized_h), 6),
            "boxes_scaled_back_for_overlay": "Yes",
        })
        return resized, diagnostics
    except Exception as e:
        diagnostics["downscale_error"] = str(e)
        return image, diagnostics


def _ocr_candidate_metrics(rows: pd.DataFrame) -> Dict[str, object]:
    if rows is None or rows.empty:
        return {
            "avg_confidence": 0.0,
            "lines": 0,
            "rounds_detected": 0,
            "crochet_tokens": 0,
            "score": 0.0,
        }
    texts = rows["text"].astype(str).tolist()
    joined = "\n".join(texts)
    conf = pd.to_numeric(rows.get("confidence", 0), errors="coerce").fillna(0)
    avg_conf = float(conf.mean()) if len(conf) else 0.0

    # Round markers including common OCR variants: R1, r1, Rl, Rg, R2g.
    rounds = re.findall(r"\b(?:R|r)\s*(?:\d+|[lIgq]|2[gq])\b", joined)

    # Crochet-like tokens for English, Chinese shorthand, and common symbol formulas.
    token_patterns = [
        r"\b\d+\s*[xXvVaAtTfFeE]\b",
        r"\b[xX]\s*[.,，、]\s*[vVaA]\b",
        r"\b\d+\s*[xX]\s*[.,，、]?\s*[vVaA]\b",
        r"\b(?:MR|mr|sc|SC|dc|DC|hdc|HDC|tr|TR|ch|CH|sl\s*st|SLST|inc|INC|dec|DEC|blo|BLO|flo|FLO)\b",
        r"環起|环起|環|环|不加減|不加减|交叉",
    ]
    token_count = 0
    for pat in token_patterns:
        token_count += len(re.findall(pat, joined))

    # Useful-line count: ignore decorative one-character fragments where possible.
    useful_lines = sum(1 for t in texts if len(t.strip()) >= 2)

    # Score: confidence matters, but crochet tokens and round labels matter more
    # for pattern screenshots. This avoids choosing a confident but irrelevant OCR.
    score = (avg_conf * 35) + (len(rounds) * 7) + (token_count * 3) + (useful_lines * 0.8)
    return {
        "avg_confidence": round(avg_conf, 3),
        "lines": int(useful_lines),
        "rounds_detected": int(len(rounds)),
        "crochet_tokens": int(token_count),
        "score": round(float(score), 1),
    }


def run_ocr_candidate_comparison(image: Image.Image, lang_mode: str) -> Dict[str, object]:
    """Run original OCR and enhanced OCR, score both, and return the selected output."""
    original_lines, original_rows = run_ocr_single(image, lang_mode, "original image")

    scale = 2
    enhanced_image = preprocess_enhanced_for_ocr(image, scale=scale)
    enhanced_lines, enhanced_rows_scaled = run_ocr_single(enhanced_image, lang_mode, "enhanced x2 grayscale contrast")
    enhanced_rows = _scale_rows_back(enhanced_rows_scaled, scale=scale)
    if enhanced_rows is not None and not enhanced_rows.empty:
        enhanced_rows["source"] = "enhanced x2 grayscale contrast"

    candidates = []
    for name, rows in [("Original", original_rows), ("Enhanced", enhanced_rows)]:
        metrics = _ocr_candidate_metrics(rows)
        candidates.append({"Candidate": name, **metrics})
    comparison_df = pd.DataFrame(candidates)

    # Pick highest score. If scores are close, prefer Original to avoid overprocessing.
    orig_score = float(comparison_df.loc[comparison_df["Candidate"] == "Original", "score"].iloc[0])
    enh_score = float(comparison_df.loc[comparison_df["Candidate"] == "Enhanced", "score"].iloc[0])
    if enh_score > orig_score * 1.08:
        selected_name = "Enhanced"
        selected_rows = enhanced_rows
    else:
        selected_name = "Original"
        selected_rows = original_rows

    selected_text = "\n".join(selected_rows["text"].astype(str).tolist()) if selected_rows is not None and not selected_rows.empty else ""
    return {
        "selected_name": selected_name,
        "selected_text": selected_text,
        "selected_rows": selected_rows,
        "comparison_df": comparison_df,
        "original_text": "\n".join(original_rows["text"].astype(str).tolist()) if not original_rows.empty else "",
        "enhanced_text": "\n".join(enhanced_rows["text"].astype(str).tolist()) if enhanced_rows is not None and not enhanced_rows.empty else "",
        "original_rows": original_rows,
        "enhanced_rows": enhanced_rows,
        "enhanced_preview": enhanced_image,
    }

def prepare_two_column_rows(rows: pd.DataFrame, image_width: int, lang_mode: str) -> pd.DataFrame:
    """Assign overlapped OCR boxes to their real column using global x.

    v4 read the overlap twice and then simply appended left OCR + right OCR.
    That could attach right-column instructions like '~start' to R2.
    v5 keeps the overlap for recognition, but assigns each detected text box
    to left/right by its centre x-coordinate, removes low-confidence noise,
    and de-duplicates near-identical overlap hits.
    """
    if rows.empty:
        return rows

    work = rows.copy()
    work["confidence"] = pd.to_numeric(work["confidence"], errors="coerce").fillna(0)
    work = work[work["confidence"] >= min_conf_for_mode(lang_mode)].copy()
    if work.empty:
        return rows.copy()

    mid = image_width / 2
    work["assigned_column"] = np.where(work["global_x"] < mid, "left", "right")
    work["column_order"] = np.where(work["assigned_column"] == "left", 0, 1)

    # De-duplicate repeated overlap recognitions by normalized text.
    # Keep the higher-confidence reading, then sort left column top-down, then right column top-down.
    work["_norm"] = work["text"].map(lambda x: terminology_engine.norm_text(x))
    work = work.sort_values(["_norm", "confidence"], ascending=[True, False])
    work = work.drop_duplicates(subset=["_norm"], keep="first")
    work = work.sort_values(["column_order", "y", "global_x"]).drop(columns=["_norm"])
    return work.reset_index(drop=True)

def run_ocr(image: Image.Image, lang_mode: str, layout_mode: str) -> Tuple[str, pd.DataFrame, Optional[Image.Image]]:
    if layout_mode == "Two columns — OCR left then right":
        overlap_percent = 20
        left, right = split_image_two_columns(image, overlap_percent=overlap_percent)
        w, _ = image.size
        mid = w // 2
        overlap = int(w * overlap_percent / 100)
        right_start = max(0, mid - overlap // 2)

        _, left_rows = run_ocr_single(left, lang_mode, "left column with overlap", x_offset=0)
        _, right_rows = run_ocr_single(right, lang_mode, "right column with overlap", x_offset=right_start)

        all_rows = pd.concat([left_rows, right_rows], ignore_index=True)
        rows_for_text = prepare_two_column_rows(all_rows, image_width=w, lang_mode=lang_mode)
        text = "\n".join(rows_for_text["text"].astype(str).tolist())

        preview = make_column_guide_preview(image, overlap_percent=overlap_percent)
        return text, all_rows, preview

    lines, rows = run_ocr_single(image, lang_mode, "single image")
    return "\n".join(lines), rows, None

# -----------------------------
# Matching
# -----------------------------
def make_candidates(ocr_text: str) -> List[str]:
    text = terminology_engine.norm_text(ocr_text)
    candidates = set()

    for line in text.splitlines():
        line = line.strip()
        if line:
            candidates.add(line)

    # Prioritise crochet abbreviations in compact pattern expressions: 6SC, 1DEC, etc.
    crochet_abbrevs = re.findall(r"\b(?:sl\s?st|mr|sc|hdc|dc|tr|dtr|inc|dec|blo|flo|fo|rs|ws|ch|x|v|a|t|f|e)\b", text, flags=re.I)
    for token in crochet_abbrevs:
        candidates.add(token.replace(" ", ""))
        if token.lower() == "slst":
            candidates.add("sl st")

    # General words / Japanese-Chinese chunks.
    tokens = re.findall(r"[a-zA-Z]+(?:\s+[a-zA-Z]+)?|[\u3040-\u30ff\u3400-\u9fff]+", text)
    for token in tokens:
        token = token.strip()
        if token:
            candidates.add(token)

    return sorted(candidates, key=lambda x: (-len(x), x))

@profile_function("term matching: find_matches", "find_matches calls")
def find_matches(ocr_text: str, df: pd.DataFrame, index: Dict[str, int]) -> Tuple[pd.DataFrame, List[str]]:
    candidates = make_candidates(ocr_text)
    matched_rows = []
    used_row_ids = set()
    unmatched = []

    for cand in candidates:
        key = terminology_engine.norm_text(cand)
        if not key or len(key) <= 1:
            continue
        if key in index:
            row_id = index[key]
            if row_id in used_row_ids:
                continue
            used_row_ids.add(row_id)
            row = df.loc[row_id]
            matched_rows.append({
                "Original detected": cand,
                "Category": row.get("category", ""),
                "US": row.get("US_term", ""),
                "US abb": row.get("US_abb", ""),
                "UK": row.get("UK_term", ""),
                "UK abb": row.get("UK_abb", ""),
                "中文": row.get("Chinese_term", ""),
                "日本語": row.get("Japanese", ""),
            })
        else:
            if len(key) >= 2 and not key.isnumeric():
                unmatched.append(cand)

    return pd.DataFrame(matched_rows), unmatched[:40]

NORMALIZED_LOOKUP_INDEX_STATS = terminology_engine.NORMALIZED_LOOKUP_INDEX_STATS

CSV_TERM_CACHE_STATS = terminology_engine.CSV_TERM_CACHE_STATS


def normalize_chinese_pattern_text(text: str) -> str:
    """Mainland Chinese crochet pattern cleanup before round extraction.

    Handles raw OCR like:
    Rg: 8 (6X.V)\n(7xV)\nRl0:\nRl1: 不加减x
    by moving the orphan (7XV) into R10 and repairing Rl0/Rl1/R2g.
    """
    text = unicodedata.normalize("NFKC", text)
    text = line_translation_engine.normalize_decimal_mm(text)
    text = text.replace("：", ":").replace("；", ":").replace(";", ":")
    text = text.replace("，", ",").replace("、", ",").replace("。", ".")
    text = line_translation_engine.normalize_decimal_mm(text)
    text = re.sub(r"([xvaftesl])\s*[.]\s*([xvaftesl])", r"\1,\2", text, flags=re.I)
    text = line_translation_engine.normalize_decimal_mm(text)
    text = re.sub(r"\bIOX\b", "10X", text, flags=re.I)
    text = re.sub(r"\bI0X\b", "10X", text, flags=re.I)
    text = re.sub(r"\bGX\b", "6X", text, flags=re.I)
    text = re.sub(r"\bSXV\b", "5XV", text, flags=re.I)

    raw_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    fixed = []
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        line = line_translation_engine.repair_ocr_round_token(line)
        line = re.sub(r"\br\s*(\d+)", r"R\1", line, flags=re.I)
        line = re.sub(r"\bR(\d+)\s*[.;]", r"R\1:", line, flags=re.I)
        line = re.sub(r"\bR[gq]\s*:", "R9:", line, flags=re.I)
        line = re.sub(r"\bR[lI]\s*:", "R1:", line, flags=re.I)
        line = re.sub(r"\bR114\s*:", "R14:", line, flags=re.I)
        line = re.sub(r"\bR2[gq]\s*:", "R29:", line, flags=re.I)

        orphan_bracket = re.fullmatch(r"[（(]\s*[0-9IOGS]*\s*[XxVvAaTtFfEeSsLl,.，、 ]+\s*[)）]", line)

        # If an orphan bracket line is followed by a round marker, it often belongs
        # to that next round, not to the previous round.
        # Example: (XV) / R3:8 -> R3: 8 (XV)
        # Example: (7XV) / Rl0: -> R10: (7XV)
        if orphan_bracket and i + 1 < len(raw_lines):
            nxt = line_translation_engine.repair_ocr_round_token(raw_lines[i + 1].strip())
            if re.fullmatch(r"R\d+\s*:\s*\d*\s*", nxt, flags=re.I):
                fixed.append(f"{nxt} {line}".strip())
                i += 2
                continue

        # If a round marker/body is followed by an expression, attach it when the
        # marker body is empty or just a repeat number.
        # Example: R6: / (4X,V) / 8 -> R6: 8 (4X,V)
        # Example: R24:6 / (13XV) -> R24: 6 (13XV)
        m_round_short = re.fullmatch(r"(R\d+\s*:)\s*(\d*)\s*", line, flags=re.I)
        if m_round_short and i + 1 < len(raw_lines):
            nxt = raw_lines[i + 1].strip()
            if re.fullmatch(r"[（(].*[)）]", nxt):
                prefix, num = m_round_short.groups()
                # If marker is empty and the line after the bracket is a number, use that as prefix repeat.
                if not num and i + 2 < len(raw_lines) and re.fullmatch(r"\d+", raw_lines[i + 2].strip()):
                    fixed.append(f"{prefix} {raw_lines[i + 2].strip()} {nxt}")
                    i += 3
                    continue
                fixed.append(f"{prefix} {num} {nxt}".strip())
                i += 2
                continue
            if not m_round_short.group(2) and re.fullmatch(r"\d+\s*[XxVvAaTtFfEe]", nxt):
                fixed.append(f"{line} {nxt}")
                i += 2
                continue

        fixed.append(line)
        i += 1

    text = "\n".join(fixed)
    # Uppercase crochet shorthand in pattern positions.
    text = re.sub(r"([0-9])\s*([xvaftes])\b", lambda m: m.group(1) + m.group(2).upper(), text, flags=re.I)
    text = re.sub(r"(?<=[(,，、.。\s])([xvaftes])(?=[),，、.。\s])", lambda m: m.group(1).upper(), text, flags=re.I)
    text = re.sub(r"(?<=[不加減减交叉])([xvaftes])\b", lambda m: m.group(1).upper(), text, flags=re.I)
    return text


def extract_rounds(clean_text: str) -> List[Dict[str, object]]:
    """Extract R1/R2/R5-R8 rows from both line-based and run-on OCR text."""
    text = unicodedata.normalize("NFKC", clean_text)
    text = normalize_chinese_pattern_text(text)
    text = ocr_cleanup_engine.normalize_pattern_rounds(text)
    text = re.sub(r"\br\s*(\d+)", r"R\1", text, flags=re.I)
    text = re.sub(r"\bR(\d+)\s*[;.]", r"R\1:", text, flags=re.I)
    text = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()

    marker = re.compile(r"\bR\s*(\d+)(?:\s*[-–—~～〜－]\s*R?\s*(\d+))?\s*[:：]", flags=re.I)
    matches = list(marker.finditer(text))
    rounds = []

    for idx, m in enumerate(matches):
        start_num = int(m.group(1))
        end_num = int(m.group(2)) if m.group(2) else start_num
        body_start = m.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip(" -~，,;；")
        if not body:
            continue

        # Total stitch count in [12], if present.
        total_match = re.search(r"\[(\d+)\]", body)
        total = total_match.group(1) if total_match else ""
        if total_match:
            body = body[:total_match.end()].strip()

        # Trim obvious neighbouring note text after a Chinese row.
        body = re.sub(r"\s+(?=R\d+:)", " ", body)
        body = body.strip()

        looks_like_pattern = bool(re.search(
            r"\d+\s*(?:\(|[XVAFTESL]|SC|INC|DEC|HDC|DC|TR)|不加[減减]|環起|环起|環形起|环形起|圈起|起圈|環\s*\d|环\s*\d|[（(].*[XVAFTESL].*[)）]",
            body,
            flags=re.I,
        ))
        if not total and not looks_like_pattern:
            continue

        rounds.append({
            "sort": start_num,
            "Round": f"R{start_num}" if start_num == end_num else f"R{start_num}-R{end_num}",
            "Original": body,
            "Total stitches": total,
        })

    best = {}
    for r in rounds:
        key = r["Round"]
        body = str(r["Original"])
        # Prefer rows with total stitches and compact row-like content; avoid long contaminated rows.
        pattern_score = 0
        if re.search(r"[XVAFTESL]|SC|INC|DEC|不加", body, flags=re.I):
            pattern_score += 2
        if r["Total stitches"]:
            pattern_score += 1
        if len(body) > 40:
            pattern_score -= 1
        score = (pattern_score, -len(body) if len(body) > 60 else len(body))
        old = best.get(key)
        old_body = str(old.get("Original", "")) if old else ""
        old_pattern_score = 0
        if old and re.search(r"[XVAFTESL]|SC|INC|DEC|不加", old_body, flags=re.I):
            old_pattern_score += 2
        if old and old.get("Total stitches"):
            old_pattern_score += 1
        if len(old_body) > 40:
            old_pattern_score -= 1
        old_score = (old_pattern_score, -len(old_body) if len(old_body) > 60 else len(old_body))
        if old is None or score > old_score:
            best[key] = r

    return sorted(best.values(), key=lambda x: int(x["sort"]))

def build_interpretation(clean_text: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str) -> pd.DataFrame:
    rounds = extract_rounds(clean_text)
    rows = []
    for r in rounds:
        translated = line_translation_engine.translate_expression(str(r["Original"]), index, df, output_mode)
        output_col = "解讀" if output_mode in ["Traditional Chinese", "Simplified Chinese"] else "Interpretation"
        rows.append({
            "Round": r["Round"],
            "Original": r["Original"],
            output_col: translated,
            "Total stitches": r["Total stitches"],
        })
    return pd.DataFrame(rows)

def build_ocr_workload_diagnostics(
    image: Image.Image,
    detected_ocr_rows: Optional[pd.DataFrame],
    text_rows: Optional[pd.DataFrame],
    line_df: Optional[pd.DataFrame],
) -> Dict[str, object]:
    width, height = image.size
    pixel_count = int(width * height)
    megapixels = round(pixel_count / 1_000_000, 3)
    ocr_box_count = int(len(detected_ocr_rows)) if detected_ocr_rows is not None else 0
    ocr_text_line_count = int(len(text_rows)) if text_rows is not None and not text_rows.empty else 0
    overlay_item_count = int(len(line_df)) if line_df is not None and not line_df.empty else 0
    boxes_per_mp = round(ocr_box_count / megapixels, 1) if megapixels else 0
    return {
        "image_width": width,
        "image_height": height,
        "pixel_count": pixel_count,
        "megapixels": megapixels,
        "ocr_box_count": ocr_box_count,
        "ocr_text_line_count": ocr_text_line_count,
        "overlay_item_count": overlay_item_count,
        "boxes_per_megapixel": boxes_per_mp,
        "paddle_detect_timing": "Not exposed by current PaddleOCR predict()/ocr() call",
        "paddle_recognize_timing": "Not exposed by current PaddleOCR predict()/ocr() call",
    }


def build_ocr_image_pipeline_diagnostics(
    original_image: Image.Image,
    selected_image: Image.Image,
    working_image: Image.Image,
    ocr_input_image: Image.Image,
    area_mode: str,
    crop_box: Tuple[int, int, int, int],
    downscale_diagnostics: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    downscale_diagnostics = downscale_diagnostics or {}
    original_size = _image_size_dict(original_image)
    selected_size = _image_size_dict(selected_image)
    working_size = _image_size_dict(working_image)
    ocr_input_size = _image_size_dict(ocr_input_image)
    full_box = (0, 0, original_image.size[0], original_image.size[1])
    return {
        "original_uploaded_image": original_size,
        "selected_image": selected_size,
        "working_image": working_size,
        "working_image_before_downscale": working_size,
        "image_actually_passed_to_paddleocr": ocr_input_size,
        "preprocessing_original_size": working_size,
        "preprocessing_output_size": ocr_input_size,
        "app_level_resize_before_paddleocr": downscale_diagnostics.get("downscale_applied", "No"),
        "size_after_downscale": ocr_input_size,
        "boxes_scaled_back_for_overlay": downscale_diagnostics.get("boxes_scaled_back_for_overlay", "No"),
        "whole_pattern_sends_full_image": bool(area_mode == "Whole Pattern" and tuple(crop_box) == full_box),
        "select_area_sends_cropped_image": bool(area_mode == "Select Area" and tuple(crop_box) != full_box),
    }

@dataclass(frozen=True)
class TranslateImageRequest:
    image: Image.Image
    selected_image: Image.Image
    working_image: Image.Image
    source_mode: str
    output_mode: str
    area_mode: str
    crop_box: Tuple[int, int, int, int]
    df: pd.DataFrame
    index: Dict[str, int]
    diagnostic_request_id: str
    diagnostic_session_generation: str
    action_started: Optional[float]
    image_load_seconds: float
    crop_extraction_seconds: float
    quality_metrics: Dict[str, object]
    quality_errors: List[str]
    quality_warnings: List[str]
    quality_label: str
    experimental_downscale: bool
    downscale_max_height_option: str
    ocr_resize_test: str
    session_diagnostics: Dict[str, object]
    diagnostic_events: List[Dict[str, object]]
    diagnostic_platform: str
    interface_language: str
    ocr_execution_start: Optional[float] = None


@dataclass(frozen=True)
class TranslateImageResult:
    primary_result: Dict[str, object]
    analytics: Dict[str, object]
    ocr_finished_at: str
    ocr_duration_seconds: float
    downstream_elapsed_seconds: float
    translation_run_elapsed_seconds: float


def translate_image(request: TranslateImageRequest) -> TranslateImageResult:
    """Run the full image translation pipeline without Streamlit dependencies."""
    ocr_execution_start = (
        request.ocr_execution_start
        if isinstance(request.ocr_execution_start, (int, float))
        else time.perf_counter()
    )
    diagnostic_request_id = request.diagnostic_request_id
    diagnostic_session_generation = request.diagnostic_session_generation
    action_started = request.action_started
    image_load_seconds = request.image_load_seconds
    crop_extraction_seconds = request.crop_extraction_seconds
    image = request.image
    selected_image = request.selected_image
    working_image = request.working_image
    source_mode = request.source_mode
    output_mode = request.output_mode
    area_mode = request.area_mode
    crop_box = request.crop_box
    df = request.df
    index = request.index
    quality_metrics = request.quality_metrics
    quality_errors = request.quality_errors
    quality_warnings = request.quality_warnings
    quality_label = request.quality_label
    experimental_downscale = request.experimental_downscale
    downscale_max_height_option = request.downscale_max_height_option
    ocr_resize_test = request.ocr_resize_test

    delivery_session_diagnostics = dict(request.session_diagnostics)
    delivery_diagnostic_events = list(request.diagnostic_events)
    ai_fallback_diagnostics: List[Dict[str, object]] = []
    ai_fallback_diagnostics_lock = threading.Lock()
    delivery_diagnostic_platform = request.diagnostic_platform
    total_start = time.perf_counter()
    timings = {
        "Image load": image_load_seconds,
        "Crop extraction": crop_extraction_seconds,
    }
    runtime_profile: Dict[str, object] = {
        "image_loading": image_load_seconds,
        "image_preprocessing": crop_extraction_seconds,
        "ocr": None,
        "ocr_cleanup": None,
        "translation": None,
        "overlay_generation": None,
        "png_encoding": None,
        "translation_txt_generation": None,
        "diagnostic_report_generation": None,
        "ui_rendering": None,
        "total": None,
        "ocr_resize_test": ocr_resize_test,
    }
    preparation_start = time.perf_counter()
    log_app_ocr_timing(
        diagnostic_request_id,
        "pre_ocr_preparation_begin",
        elapsed_seconds=(
            preparation_start - action_started
            if isinstance(action_started, (int, float))
            else None
        ),
    )
    preprocessing_start = time.perf_counter()
    ocr_input_image, downscale_diagnostics = prepare_experimental_ocr_image(
        working_image,
        experimental_downscale,
        downscale_max_height_option,
    )
    preprocessing_seconds = crop_extraction_seconds + (time.perf_counter() - preprocessing_start)
    runtime_profile["image_preprocessing"] = preprocessing_seconds
    timings["Image preprocessing"] = preprocessing_seconds
    ocr_call_trace: List[str] = []
    ocr_call_diagnostics = build_ocr_image_pipeline_diagnostics(
        image,
        selected_image,
        working_image,
        ocr_input_image,
        area_mode,
        crop_box,
        downscale_diagnostics=downscale_diagnostics,
    )
    log_app_ocr_timing(
        diagnostic_request_id,
        "pre_ocr_preparation_end",
        elapsed_seconds=time.perf_counter() - preparation_start,
    )
    ocr_stage_start = time.perf_counter()
    candidate_result = run_primary_ocr(
        ocr_input_image,
        source_mode,
        compare_easyocr=False,
        trace=ocr_call_trace,
        diagnostics=ocr_call_diagnostics,
        diagnostic_request_id=diagnostic_request_id,
    )
    ocr_seconds = time.perf_counter() - ocr_stage_start
    runtime_profile["ocr"] = ocr_seconds
    timings["OCR"] = ocr_seconds
    timings["PaddleOCR inference"] = float(candidate_result.get("paddle_inference_seconds", 0.0) or 0.0)
    if downscale_diagnostics.get("downscale_applied") == "Yes":
        scale_x = float(downscale_diagnostics.get("coordinate_scale_x", 1.0) or 1.0)
        scale_y = float(downscale_diagnostics.get("coordinate_scale_y", 1.0) or 1.0)
        scaled_rows = scale_ocr_rows_to_original(candidate_result.get("selected_rows"), scale_x, scale_y)
        candidate_result["selected_rows"] = scaled_rows
        candidate_result["paddle_rows"] = scaled_rows

    cleanup_start = time.perf_counter()
    raw_ocr_text = candidate_result["selected_text"]
    ocr_rows = candidate_result["selected_rows"]
    detected_ocr_rows = ocr_rows.copy() if ocr_rows is not None else pd.DataFrame()
    ocr_rows, removed_noise_df = pattern_document_engine.filter_noise_and_watermarks(ocr_rows)
    raw_ocr_text = "\n".join(ocr_rows["text"].astype(str).tolist()) if ocr_rows is not None and not ocr_rows.empty else ""
    clean_text = ocr_cleanup_engine.clean_ocr_text(raw_ocr_text)
    cleanup_seconds = time.perf_counter() - cleanup_start
    runtime_profile["ocr_cleanup"] = cleanup_seconds
    timings["OCR cleanup"] = cleanup_seconds

    translation_profile = make_translation_profile()
    profile_token = _TRANSLATION_PROFILE.set(translation_profile)

    def log_downstream_timing(phase: str, **fields: object) -> None:
        if phase == "ai_request_end" and fields.get("route") in {"general", "title"}:
            reason = str(fields.get("reason", ""))
            outcome = str(fields.get("outcome", ""))
            call_ordinal = fields.get("call_ordinal")
            elapsed_seconds = fields.get("elapsed_seconds")
            if (
                reason in llm_fallback_engine.AI_TERMINAL_REASON_CODES
                and isinstance(call_ordinal, int)
                and not isinstance(call_ordinal, bool)
                and isinstance(elapsed_seconds, (int, float))
                and not isinstance(elapsed_seconds, bool)
            ):
                record = {
                    "call_ordinal": call_ordinal,
                    "outcome": outcome[:64],
                    "reason": reason,
                    "elapsed_seconds": round(float(elapsed_seconds), 4),
                    "route": str(fields.get("route", ""))[:32],
                    "model": str(fields.get("model", ""))[:64],
                    "source_mode": str(fields.get("source_mode", ""))[:64],
                    "target_mode": str(fields.get("target_mode", ""))[:64],
                    "deterministic_fallback_returned": bool(
                        fields.get("deterministic_fallback_returned", False)
                    ),
                }
                with ai_fallback_diagnostics_lock:
                    ai_fallback_diagnostics.append(record)
        try:
            log_app_ocr_timing(
                diagnostic_request_id,
                phase,
                session_generation=diagnostic_session_generation,
                **fields,
            )
        except Exception:
            pass

    try:
        downstream_start = time.perf_counter()
        log_downstream_timing(
            "downstream_translation_begin",
            elapsed_seconds=time.perf_counter() - ocr_execution_start,
        )
        translation_start = time.perf_counter()
        line_df = ocr_lines_engine.build_ocr_line_translations(
            ocr_rows,
            index,
            df,
            output_mode,
            source_mode,
            llm_provider=llm_fallback_engine.get_openai_provider_from_env(),
            diagnostic_logger=log_downstream_timing,
        )
        translation_seconds = time.perf_counter() - translation_start

        overlay_start = time.perf_counter()
        log_downstream_timing("overlay_begin")
        overlay_image, overlay_legend, overlay_legend_df = overlay_engine.make_line_translation_overlay(
            working_image,
            line_df,
            output_mode,
            scale_to_source_text=area_mode == "Select Area",
        )
        overlay_seconds = time.perf_counter() - overlay_start
        log_downstream_timing(
            "overlay_end",
            elapsed_seconds=overlay_seconds,
            outcome="success",
        )

        export_start = time.perf_counter()
        log_downstream_timing("export_begin")
        translation_start = time.perf_counter()
        matches_df, unmatched = find_matches(clean_text, df, index)
        readable_translation = (
            line_translation_engine.build_readable_line_translation(line_df)
            if line_df is not None and not line_df.empty
            else ""
        )
        translation_seconds += time.perf_counter() - translation_start

        png_start = time.perf_counter()
        overlay_png = overlay_engine.image_to_png_bytes(overlay_image) if overlay_image is not None else None
        png_seconds = time.perf_counter() - png_start

        txt_start = time.perf_counter()
        translation_txt = line_translation_engine.build_overlay_export_text(line_df)
        txt_seconds = time.perf_counter() - txt_start
        log_downstream_timing(
            "export_end",
            elapsed_seconds=time.perf_counter() - export_start,
            outcome="success",
        )
    finally:
        _TRANSLATION_PROFILE.reset(profile_token)

    runtime_profile["translation"] = translation_seconds
    runtime_profile["overlay_generation"] = overlay_seconds
    runtime_profile["png_encoding"] = png_seconds
    runtime_profile["translation_txt_generation"] = txt_seconds
    timings["Translation processing"] = translation_seconds
    timings["Overlay generation"] = overlay_seconds
    timings["PNG encoding"] = png_seconds
    timings["Translation TXT generation"] = txt_seconds
    ocr_workload_diagnostics = build_ocr_workload_diagnostics(
        working_image,
        detected_ocr_rows,
        ocr_rows,
        overlay_legend_df,
    )
    processing_total_before_status = image_load_seconds + crop_extraction_seconds + (time.perf_counter() - total_start)
    runtime_profile["total"] = processing_total_before_status
    timings["Total runtime"] = processing_total_before_status
    ocr_finished_at_text = time.strftime("%Y-%m-%d %H:%M:%S")
    ocr_duration_seconds = round(time.perf_counter() - ocr_execution_start, 3)
    delivery_session_diagnostics.update(
        {
            "pending_ocr_run": False,
            "ocr_running": False,
            "ocr_finished_at": ocr_finished_at_text,
            "ocr_duration_seconds": ocr_duration_seconds,
        }
    )
    if request.session_diagnostics.get("ocr_started_at"):
        delivery_session_diagnostics["ocr_started_at"] = request.session_diagnostics.get(
            "ocr_started_at"
        )
    primary_result = {
        "overlay_image": overlay_image,
        "overlay_png": overlay_png,
        "overlay_legend": overlay_legend,
        "overlay_legend_df": overlay_legend_df,
        "raw_ocr_text": raw_ocr_text,
        "clean_text": clean_text,
        "line_df": line_df,
        "ocr_rows": ocr_rows,
        "removed_noise_df": removed_noise_df,
        "matches_df": matches_df,
        "unmatched": unmatched,
        "readable_translation": readable_translation,
        "translation_txt": translation_txt,
        "quality_metrics": quality_metrics,
        "quality_errors": quality_errors,
        "quality_warnings": quality_warnings,
        "timings": timings,
        "runtime_profile": runtime_profile,
        "translation_profile": translation_profile,
        "source_mode": source_mode,
        "output_mode": output_mode,
        "area_mode": area_mode,
        "crop_box": crop_box,
        "diagnostic_request_id": diagnostic_request_id,
        "diagnostic_session_generation": diagnostic_session_generation,
        "diagnostic_report_inputs": {
            "ocr_engine": str(candidate_result.get("selected_name", "")),
            "image_quality_status": quality_label,
            "session_diagnostics": delivery_session_diagnostics,
            "events": delivery_diagnostic_events,
            "ai_fallback_diagnostics": sorted(
                ai_fallback_diagnostics,
                key=lambda record: int(record["call_ordinal"]),
            ),
            "ocr_workload_diagnostics": ocr_workload_diagnostics,
            "ocr_box_rows": detected_ocr_rows,
            "ocr_call_diagnostics": ocr_call_diagnostics,
            "ocr_call_trace": list(ocr_call_trace),
            "downscale_diagnostics": downscale_diagnostics,
            "ocr_resize_test": ocr_resize_test,
            "interface_language": request.interface_language,
            "platform": delivery_diagnostic_platform,
        },
    }
    analytics = {
        "area_mode": area_mode,
        "source_mode": source_mode,
        "output_mode": output_mode,
        "ocr_box_count": (
            int(len(detected_ocr_rows))
            if detected_ocr_rows is not None
            else ""
        ),
        "ocr_time_sec": round(float(ocr_seconds), 3),
        "translation_time_sec": round(float(translation_seconds), 3),
    }
    return TranslateImageResult(
        primary_result=primary_result,
        analytics=analytics,
        ocr_finished_at=ocr_finished_at_text,
        ocr_duration_seconds=ocr_duration_seconds,
        downstream_elapsed_seconds=time.perf_counter() - downstream_start,
        translation_run_elapsed_seconds=(
            time.perf_counter() - action_started
            if isinstance(action_started, (int, float))
            else time.perf_counter() - ocr_execution_start
        ),
    )
