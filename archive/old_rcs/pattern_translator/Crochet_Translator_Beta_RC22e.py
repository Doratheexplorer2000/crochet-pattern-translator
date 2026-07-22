# ocr_prototype_v14.py
# Crochet Stitch Translator OCR Prototype v1.9m
# New in v2:
# - Reading layout: single column / two columns
# - Cleaner OCR text for crochet patterns
# - Round extraction and numeric sorting
# - Basic pattern interpretation for common amigurumi rows
# - Pattern normalization layer for common OCR round errors: bare 9:/10:/11:, Rs-R8, RI1, R1o
# Put this file in the same folder as stitches_1_8.csv, then run:
# python3 -m streamlit run ocr_prototype_v9.py

import os
import io
import re
import html
import hashlib
import math
import tempfile
import time
import sys
import unicodedata
from pathlib import Path
from typing import Callable, Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image

APP_VERSION = "Pattern OCR Translator (Beta RC22e)"
BASE_DIR = Path(__file__).resolve().parent
SOURCE_CSV = BASE_DIR / "stitches_1_8e.csv"
FALLBACK_CSV = BASE_DIR / "stitches_1_8a.csv"
DEBUG_MODE = os.getenv("CROCHET_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
FEEDBACK_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScoDrN0xsyOg800O8Pw7aXAa5GREQIU-RmxlmXIlBOE7y_Q_w/viewform"

TRANSLATION_PROFILE: Optional[Dict[str, Dict[str, float]]] = None


def make_translation_profile() -> Dict[str, Dict[str, float]]:
    return {"timings": {}, "counts": {}}


def profile_count(name: str, amount: float = 1.0):
    if TRANSLATION_PROFILE is None:
        return
    counts = TRANSLATION_PROFILE.setdefault("counts", {})
    counts[name] = counts.get(name, 0.0) + amount


def profile_add_time(name: str, seconds: float):
    if TRANSLATION_PROFILE is None:
        return
    timings = TRANSLATION_PROFILE.setdefault("timings", {})
    timings[name] = timings.get(name, 0.0) + seconds


def profile_function(time_name: str, count_name: str):
    def decorator(func):
        def wrapped(*args, **kwargs):
            profile_count(count_name)
            profile_start = time.perf_counter() if TRANSLATION_PROFILE is not None else None
            try:
                return func(*args, **kwargs)
            finally:
                if profile_start is not None:
                    profile_add_time(time_name, time.perf_counter() - profile_start)
        return wrapped
    return decorator

st.set_page_config(page_title="Crochet Translator", page_icon="🧶", layout="centered")

st.markdown(
    """
<style>
h1, h2, h3 { color: #5f73a8 !important; }
.block-container { padding-top: 1.5rem; }
h1 { margin-bottom: 0.15rem !important; line-height: 1.12 !important; }
h1 a[href^="#"], h1 .anchor-link { display: none !important; }
h1 + div[data-testid="stCaptionContainer"] { margin-top: -0.25rem; }
div[data-testid="stCaptionContainer"] { margin-bottom: 0.35rem; }
.small-note { font-size: 0.9rem; opacity: 0.82; margin: 0.15rem 0 0.35rem; line-height: 1.35; }
.warning-box {
    border: 1px solid rgba(180, 130, 60, 0.35);
    border-radius: 0.6rem;
    padding: 0.55rem 0.65rem;
    background: rgba(180, 130, 60, 0.08);
    font-size: 0.9rem;
    line-height: 1.35;
}
.good-box {
    border: 1px solid rgba(80, 150, 100, 0.35);
    border-radius: 0.6rem;
    padding: 0.75rem;
    background: rgba(80, 150, 100, 0.08);
}
div[data-testid="stExpander"] { margin-bottom: 0.45rem; }
div[data-testid="stExpander"] details { border-radius: 0.5rem; }
div[data-testid="stExpander"] summary { min-height: 2rem; }
div[data-testid="stExpander"] div[data-testid="stMarkdownContainer"] p { margin-bottom: 0.25rem; }
div[data-testid="stVerticalBlock"] > div { gap: 0.45rem; }
div[data-testid="stSelectbox"], div[data-testid="stRadio"], div[data-testid="stFileUploader"] { margin-bottom: 0.15rem; }
div[data-testid="stHorizontalBlock"] div[data-testid="stSelectbox"] { margin-bottom: 0; }
div[data-testid="stHorizontalBlock"] div[data-testid="stSelectbox"] label { min-height: 0; }
div[data-testid="stFileUploader"] section {
    border-color: rgba(95, 115, 168, 0.28);
    background: rgba(95, 115, 168, 0.045);
    border-radius: 0.55rem;
}
div[data-testid="stFileUploader"] section:hover {
    border-color: rgba(95, 115, 168, 0.48);
    background: rgba(95, 115, 168, 0.07);
}
.report-action {
    font-size: 1rem;
    font-weight: 650;
    margin: 0.85rem 0 0.15rem;
}
.report-helper {
    color: rgba(120, 120, 120, 0.95);
    font-size: 0.9rem;
    line-height: 1.35;
    margin: 0 0 0.45rem 1.35rem;
}
.feedback-link {
    display: inline-block;
    min-height: 2.4rem;
    line-height: 2.4rem;
    padding: 0 1rem;
    border: 1px solid rgba(120, 120, 120, 0.55);
    border-radius: 0.5rem;
    color: inherit !important;
    text-decoration: none !important;
    font-weight: 500;
    margin-top: 0.15rem;
}
.feedback-link:hover {
    border-color: rgba(120, 120, 120, 0.85);
    text-decoration: none !important;
}
@media (max-width: 640px) {
    .block-container { padding-top: 0.75rem; padding-left: 1rem; padding-right: 1rem; }
    h1 { font-size: 1.85rem !important; margin-top: 0 !important; }
    .small-note { font-size: 0.86rem; margin-bottom: 0.25rem; }
    div[data-testid="stExpander"] { margin-bottom: 0.25rem; }
    div[data-testid="stHorizontalBlock"] { gap: 0.25rem; }
    div[data-testid="stFileUploader"] section { padding: 0.75rem; }
}
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# Text normalisation
# -----------------------------
ZH_VARIANTS = str.maketrans({
    "钩": "鈎", "勾": "鈎", "针": "針", "锁": "鎖", "长": "長",
    "编": "編", "织": "織", "线": "線", "绕": "繞", "组": "組",
    "环": "環", "双": "雙", "单": "單", "减": "減", "裏": "裡",
    "里": "裡", "辫": "辮", "结": "結", "记": "記", "内": "內",
    "后": "後",
})

def norm_text(value: object) -> str:
    profile_count("norm_text calls")
    if TRANSLATION_PROFILE is not None:
        try:
            caller = sys._getframe(1).f_code.co_name
        except Exception:
            caller = "unknown"
        profile_count(f"norm_text caller: {caller}")
    profile_start = time.perf_counter() if TRANSLATION_PROFILE is not None else None
    if value is None or pd.isna(value):
        if profile_start is not None:
            profile_add_time("OCR text normalization", time.perf_counter() - profile_start)
        return ""
    text = str(value).strip()
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(ZH_VARIANTS)
    text = text.lower()
    text = re.sub(r"[\u200b\u200c\u200d]", "", text)
    text = re.sub(r"[“”‘’'\"`´]", "", text)
    text = re.sub(r"\s+", " ", text)
    out = text.strip()
    if profile_start is not None:
        profile_add_time("OCR text normalization", time.perf_counter() - profile_start)
    return out

def split_aliases(value: object) -> List[str]:
    if value is None or pd.isna(value):
        return []
    raw = str(value)
    parts = re.split(r"[|,;；，/]+", raw)
    return [p.strip() for p in parts if p.strip()]

# -----------------------------
# Load data and build index
# -----------------------------
@st.cache_data
def load_database() -> pd.DataFrame:
    csv_path = SOURCE_CSV if SOURCE_CSV.exists() else FALLBACK_CSV
    if not csv_path.exists():
        st.error(t("missing_csv").format(file=SOURCE_CSV.name))
        st.stop()
    df = pd.read_csv(csv_path).fillna("")
    return df

def get_active_search_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "search_status" not in df.columns:
        return df
    status = df["search_status"].fillna("").astype(str).str.strip().str.lower()
    return df[(status == "") | (status == "active")].copy()

def get_source_columns(source_mode: str) -> List[str]:
    if source_mode in ["English — UK", "English UK terms"]:
        return ["UK_term", "UK_term_alias", "UK_abb", "UK_abb1"]
    if source_mode in ["English — US", "English US terms"]:
        return ["US_term", "US_term_alias", "US_abb", "US_abb1"]
    if source_mode in ["Traditional Chinese", "Simplified Chinese", "Chinese"]:
        return ["Chinese_term", "Chinese_term_alias", "Chinese_abb"]
    if source_mode == "Japanese":
        return ["Japanese", "Japanese_alias"]
    return [
        "US_term", "US_term_alias", "US_abb", "US_abb1",
        "UK_term", "UK_term_alias", "UK_abb", "UK_abb1",
        "Chinese_term", "Chinese_term_alias", "Chinese_abb",
        "Japanese", "Japanese_alias",
    ]

@st.cache_data
def build_term_index(df: pd.DataFrame, source_mode: str) -> Dict[str, int]:
    df = get_active_search_df(df)
    cols = [c for c in get_source_columns(source_mode) if c in df.columns]
    index: Dict[str, int] = {}
    for i, row in df.iterrows():
        for col in cols:
            values = [row.get(col, "")] + split_aliases(row.get(col, ""))
            for v in values:
                key = norm_text(v)
                if key and key not in index:
                    index[key] = i
    return index


@st.cache_data
def build_all_term_index(df: pd.DataFrame) -> Dict[str, int]:
    df = get_active_search_df(df)
    fallback_cols = [
        "US_term", "US_term_alias", "US_abb", "US_abb1",
        "UK_term", "UK_term_alias", "UK_abb", "UK_abb1",
        "Chinese_term", "Chinese_term_alias", "Chinese_abb",
        "Japanese", "Japanese_alias",
    ]
    all_index: Dict[str, int] = {}
    for i, row in df.iterrows():
        for col in fallback_cols:
            if col not in df.columns:
                continue
            values = [row.get(col, "")] + split_aliases(row.get(col, ""))
            for value in values:
                key = norm_text(value)
                if key and key not in all_index:
                    all_index[key] = i
    return all_index


# -----------------------------
# Image quality check
# -----------------------------
def assess_image_quality(image: Image.Image) -> Tuple[List[str], List[str], Dict[str, object]]:
    """Return blocking errors, non-blocking warnings, and diagnostic metrics.

    This is intentionally conservative. File size alone is not reliable: a large
    decorative screenshot can still be unreadable, and a small crop can be sharp.
    We mainly check pixel size, sharpness, contrast, and text-area adequacy.
    """
    img_rgb = image.convert("RGB")
    w, h = img_rgb.size
    arr = np.array(img_rgb)

    try:
        import cv2
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        contrast = float(gray.std())
    except Exception:
        # If OpenCV fails, do a simple NumPy fallback.
        gray = np.dot(arr[..., :3], [0.299, 0.587, 0.114])
        gy, gx = np.gradient(gray.astype(float))
        sharpness = float((gx ** 2 + gy ** 2).mean())
        contrast = float(gray.std())

    shortest = min(w, h)
    longest = max(w, h)
    megapixels = round((w * h) / 1_000_000, 2)

    errors: List[str] = []
    warnings: List[str] = []

    if longest < 1000 or shortest < 600:
        errors.append(
            "Image is probably too small for reliable OCR. Recommended: crop the pattern area and use an image at least 1000px wide, preferably 1500px+."
        )
    elif longest < 1500:
        warnings.append(
            "Image size is acceptable but not ideal. For small crochet text, 1500px+ on the longer side usually works better."
        )

    # Thresholds are deliberately broad because decorative backgrounds vary a lot.
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

    metrics = {
        "width_px": w,
        "height_px": h,
        "megapixels": megapixels,
        "sharpness_score": round(sharpness, 1),
        "contrast_score": round(contrast, 1),
    }
    return errors, warnings, metrics

# -----------------------------
# OCR
# -----------------------------
@st.cache_resource
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
    """Split image into two OCR regions with centre overlap.

    Do NOT drop a centre gutter. Crochet patterns often place R9/R10/R11
    close to the centre, so a hard 50/50 split can cut off the leading R.
    Example with 20% overlap:
    - left region:  0%  to 60%
    - right region: 40% to 100%
    """
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
    # Light translucent overlap zone. It is a guide only, not a destructive crop.
    draw.rectangle((x1, 0, x2, h), fill=(255, 80, 80, 38))
    # Thin centre guide line.
    line_width = max(2, w // 500)
    draw.line((mid, 0, mid, h), fill=(255, 60, 60, 210), width=line_width)
    return Image.alpha_composite(img, overlay).convert("RGB")

MIN_CONF_FOR_CLEAN_TEXT = 0.45

def min_conf_for_mode(lang_mode: str) -> float:
    # Chinese/Japanese OCR often returns lower confidence for mixed symbols like R10:(7X,V).
    # Keep more text, then let the pattern parser reject junk later.
    if lang_mode in ["Traditional Chinese", "Simplified Chinese", "Chinese"]:
        return 0.20
    if lang_mode == "Japanese":
        return 0.30
    return MIN_CONF_FOR_CLEAN_TEXT

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

@st.cache_resource(show_spinner=False, max_entries=1)
def get_paddle_reader(lang: str):
    """Load PaddleOCR lazily. PaddleOCR 3.x and older APIs use different kwargs."""
    from paddleocr import PaddleOCR
    try:
        return PaddleOCR(
            lang=lang,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except TypeError:
        return PaddleOCR(lang=lang, use_angle_cls=False)


def _save_image_temp(image: Image.Image) -> str:
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    image.convert("RGB").save(path)
    return path


def _box_to_coords(box) -> Tuple[float, float, float, float]:
    """Return min_x, max_x, min_y, max_y from Paddle/Easy style boxes."""
    try:
        arr = np.array(box, dtype=float)
        if arr.ndim == 1 and arr.size >= 4:
            # Sometimes [x1, y1, x2, y2]
            xs = [arr[0], arr[2]]
            ys = [arr[1], arr[3]]
        else:
            xs = arr[:, 0]
            ys = arr[:, 1]
        return float(np.min(xs)), float(np.max(xs)), float(np.min(ys)), float(np.max(ys))
    except Exception:
        return 0.0, 80.0, 0.0, 20.0


def flatten_paddle_result_to_rows(result: object) -> List[Dict[str, object]]:
    """Extract text, confidence and box from PaddleOCR 3.x / older result formats."""
    rows: List[Dict[str, object]] = []

    def add_row(text: object, confidence: object = None, box: object = None):
        clean = str(text).strip() if text is not None else ""
        if not clean:
            return
        try:
            conf = float(confidence) if confidence is not None else 0.0
        except Exception:
            conf = 0.0
        min_x, max_x, min_y, max_y = _box_to_coords(box)
        rows.append({
            "source": "PaddleOCR",
            "text": clean,
            "confidence": round(conf, 3),
            "x": round((min_x + max_x) / 2, 1),
            "global_x": round((min_x + max_x) / 2, 1),
            "y": round((min_y + max_y) / 2, 1),
            "min_x": round(min_x, 1),
            "max_x": round(max_x, 1),
            "min_y": round(min_y, 1),
            "max_y": round(max_y, 1),
        })

    if isinstance(result, list):
        for page in result:
            if isinstance(page, dict):
                texts = page.get("rec_texts") or page.get("texts") or []
                scores = page.get("rec_scores") or page.get("scores") or []
                boxes = page.get("rec_polys") or page.get("dt_polys") or page.get("boxes") or []
                if texts:
                    for i, text in enumerate(texts):
                        add_row(text, scores[i] if i < len(scores) else None, boxes[i] if i < len(boxes) else None)
                    continue
            if isinstance(page, list):
                for item in page:
                    try:
                        box = item[0]
                        rec = item[1]
                        if isinstance(rec, (list, tuple)) and len(rec) >= 2:
                            add_row(rec[0], rec[1], box)
                        elif isinstance(rec, str):
                            add_row(rec, None, box)
                    except Exception:
                        if isinstance(item, str):
                            add_row(item)

    return sorted(rows, key=lambda r: (r["y"], r["global_x"]))


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


def run_paddle_ocr_single(
    image: Image.Image,
    lang_mode: str,
    trace: Optional[List[str]] = None,
    diagnostics: Optional[Dict[str, object]] = None,
) -> Tuple[str, pd.DataFrame, object, float]:
    if diagnostics is not None:
        diagnostics["run_paddle_ocr_single_calls"] = int(diagnostics.get("run_paddle_ocr_single_calls", 0)) + 1
        diagnostics["run_paddle_ocr_single_input"] = _image_size_dict(image)
    _ocr_trace_event(trace, "run_paddle_ocr_single start")
    lang = paddle_lang_from_mode(lang_mode)
    ocr = get_paddle_reader(lang)
    if diagnostics is not None:
        diagnostics["ocr_language_model"] = lang
        diagnostics["ocr_backend"] = "PaddleOCR"
        diagnostics["ocr_reader_class"] = type(ocr).__name__
        diagnostics["detector_model"] = _debug_cell(getattr(ocr, "det_model_dir", "")) or "Not exposed by current PaddleOCR object"
        diagnostics["recognizer_model"] = _debug_cell(getattr(ocr, "rec_model_dir", "")) or "Not exposed by current PaddleOCR object"
        diagnostics["paddle_actual_loaded_image_size"] = "Not exposed by current PaddleOCR API"
    _ocr_trace_event(trace, "save temp PNG")
    image_path = _save_image_temp(image)
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
    inference_seconds = 0.0
    try:
        try:
            _ocr_trace_event(trace, "PaddleOCR call start")
            inference_start = time.perf_counter()
            raw_result = ocr.predict(image_path)
            inference_seconds = time.perf_counter() - inference_start
            _ocr_trace_event(trace, "PaddleOCR call end")
        except AttributeError:
            _ocr_trace_event(trace, "PaddleOCR call start")
            inference_start = time.perf_counter()
            raw_result = ocr.ocr(image_path, cls=False)
            inference_seconds = time.perf_counter() - inference_start
            _ocr_trace_event(trace, "PaddleOCR call end")
    finally:
        try:
            os.remove(image_path)
        except Exception:
            pass
    rows = flatten_paddle_result_to_rows(raw_result)
    df = pd.DataFrame(rows)
    text = "\n".join(df["text"].astype(str).tolist()) if not df.empty else ""
    _ocr_trace_event(trace, "OCR results returned")
    return text, df, raw_result, inference_seconds


def run_primary_ocr(
    image: Image.Image,
    lang_mode: str,
    compare_easyocr: bool = False,
    trace: Optional[List[str]] = None,
    diagnostics: Optional[Dict[str, object]] = None,
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
    work["_norm"] = work["text"].map(lambda x: norm_text(x))
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
# OCR cleanup
# -----------------------------
def normalize_pattern_rounds(text: str) -> str:
    """Repair common OCR mistakes around amigurumi round labels.

    Examples:
    - 9; (2SC, 1DEC)x6 [18]  -> R9: (2SC, 1DEC)x6 [18]
    - 10: (1SC, 1DEC)x6 [12] -> R10: (1SC, 1DEC)x6 [12]
    - Rs-R8:                  -> R5-R8:
    - RI1 / Rl1 / R1o         -> R11 / R11 / R10
    """
    # Character-level / short-token repairs often caused by OCR.
    repairs = {
        "R1o": "R10", "R1O": "R10", "R10;": "R10:",
        "RI1": "R11", "Rl1": "R11", "Rll": "R11", "R11;": "R11:",
        "Rs-R8": "R5-R8", "RS-R8": "R5-R8", "R$-R8": "R5-R8",
        "Rs - R8": "R5-R8", "RS - R8": "R5-R8",
    }
    for bad, good in repairs.items():
        text = text.replace(bad, good)

    # Normalise R 1 / R1; / R1. to R1:
    text = re.sub(r"\bR\s*(\d+)", r"R\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\bR(\d+)\s*[;.]", r"R\1:", text, flags=re.IGNORECASE)

    # If OCR drops the R at the start of a line, restore it when the line looks like a round row.
    # Example: 9; (2SC, 1DEC)x6 [18] / 10: (1SC, 1DEC)x6 [12]
    fixed_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^\d{1,2}\s*[:;]\s*", stripped) and re.search(
            r"\b(SC|INC|DEC|HDC|DC|TR|SLST|MR)\b|\[[0-9]+\]",
            stripped,
            flags=re.IGNORECASE,
        ):
            stripped = re.sub(r"^(\d{1,2})\s*[:;]\s*", r"R\1: ", stripped)
            fixed_lines.append(stripped)
        else:
            fixed_lines.append(line)

    text = "\n".join(fixed_lines)

    # Sometimes OCR reads R5-R8 as R5 R8 or R5-RB. Handle the obvious safe cases only.
    text = re.sub(r"\bR5\s*[-–]\s*R?8\s*[:;]", "R5-R8:", text, flags=re.IGNORECASE)
    return text


def clean_ocr_text(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw)
    text = normalize_decimal_mm(text)
    # Common OCR repairs in amigurumi patterns.
    replacements = {
        "；": ":",
        "：": ":",
        "IINC": "1INC",
        "IInc": "1INC",
        "lINC": "1INC",
        "InC": "INC",
        "INc": "INC",
        "DEc": "DEC",
        "IDEC": "1DEC",
        "ISc": "1SC",
        "IS C": "1SC",
        "S LST": "SLST",
        "SL ST": "SLST",
        "S L ST": "SLST",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)

    text = normalize_pattern_rounds(text)

    # V27: English patterns often use Rnd 1 / Rnd 3-4 instead of R1 / R3-4.
    # Normalise only the crochet round abbreviation, not the ordinary word "round".
    text = re.sub(r"\bRnd\s*(\d+)", r"R\1", text, flags=re.IGNORECASE)

    # More Chinese-pattern OCR normalization. Many mainland screenshots mix R labels,
    # digits, Chinese characters, and X/V/A shorthand.
    text = re.sub(r"\br\s*(\d+)", r"R\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\bR(\d+)\s*[;.]", r"R\1:", text, flags=re.IGNORECASE)
    text = re.sub(r"\bR[gq]\s*[:：]", "R9:", text, flags=re.IGNORECASE)
    text = re.sub(r"\bR[lI]\s*[:：]", "R1:", text, flags=re.IGNORECASE)
    text = re.sub(r"\bR114\s*[:：]", "R14:", text, flags=re.IGNORECASE)
    text = re.sub(r"\bR[lI]0\s*[:：]", "R10:", text, flags=re.IGNORECASE)
    text = re.sub(r"\bR[lI]{2}\s*[:：]", "R11:", text, flags=re.IGNORECASE)
    text = text.replace("。", ".").replace("，", ",").replace("、", ",")
    text = normalize_decimal_mm(text)
    text = re.sub(r"([xvaftesl])\s*[.]\s*([xvaftesl])", r"\1,\2", text, flags=re.I)
    text = re.sub(r"([XVAFTESL])\s*[.]\s*([XVAFTESL])", r"\1,\2", text)

    text = re.sub(r"\b(\d+)\s*(SC|INC|DEC|HDC|DC|TR|SLST|SL\s*ST|MR|CH|BLO|FLO|FO|STS?|STITCHES?)\b", r"\1\2", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(SLST|SC|INC|DEC|HDC|DC|TR|MR)\b", lambda m: m.group(1).upper(), text, flags=re.IGNORECASE)

    # Mainland Chinese crochet shorthand often uses X/V/A/T/F/E.
    # Uppercase them when they appear as stitch symbols, without touching ordinary words.
    text = re.sub(r"(?<=\d)\s*([xvatfe])\b", lambda m: m.group(1).upper(), text, flags=re.I)
    text = re.sub(r"(?<=[(,，、.。\s])([xvatfe])(?=[),，、.。\s])", lambda m: m.group(1).upper(), text, flags=re.I)
    text = re.sub(r"(?<=[不加減交叉])([xvatfe])\b", lambda m: m.group(1).upper(), text, flags=re.I)
    text = normalize_decimal_mm(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

# -----------------------------
# Matching
# -----------------------------
def make_candidates(ocr_text: str) -> List[str]:
    text = norm_text(ocr_text)
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
        key = norm_text(cand)
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

# -----------------------------
# Pattern parser / interpreter
# -----------------------------
SIMP_MAP = str.maketrans({
    "針": "针", "鎖": "锁", "長": "长", "環": "环", "編": "编", "織": "织",
    "線": "线", "減": "减", "鈎": "钩", "鉤": "钩", "雙": "双", "單": "单",
    "組": "组", "記": "记", "裡": "里", "辮": "辫", "結": "结", "狀": "状",
    "內": "内", "後": "后",
})

def to_simplified(text: str) -> str:
    return str(text).translate(SIMP_MAP)

def term_from_row(row: pd.Series, output_mode: str, prefer_abbrev: bool = False) -> str:
    """Return the same crochet concept in the user's chosen output language."""
    if output_mode == "Traditional Chinese":
        return str(row.get("Chinese_term", "") or row.get("US_term", "")).strip()
    if output_mode == "Simplified Chinese":
        return to_simplified(str(row.get("Chinese_term", "") or row.get("US_term", "")).strip())
    if output_mode in ["English — US", "English US terms"]:
        return str((row.get("US_abb", "") if prefer_abbrev else row.get("US_term", "")) or row.get("US_term", "")).strip()
    if output_mode in ["English — UK", "English UK terms"]:
        return str((row.get("UK_abb", "") if prefer_abbrev else row.get("UK_term", "")) or row.get("UK_term", "") or row.get("US_term", "")).strip()
    if output_mode == "Japanese":
        return str(row.get("Japanese", "") or row.get("US_term", "")).strip()
    return str(row.get("Chinese_term", "") or row.get("US_term", "")).strip()

def format_counted_term(term_text: str, number: str, kind: str, output_mode: str) -> str:
    kind = kind.lower()
    n = str(number)
    if output_mode == "Traditional Chinese":
        if kind in ["increase", "decrease"]:
            return f"{term_text}{n}次"
        return f"{term_text}{n}針"
    if output_mode == "Simplified Chinese":
        if kind in ["increase", "decrease"]:
            return f"{term_text}{n}次"
        return f"{term_text}{n}针"
    if output_mode in ["English — US", "English — UK", "English US terms", "English UK terms"]:
        if kind in ["increase", "decrease"]:
            return f"{term_text} x{n}"
        return f"{n} {term_text}"
    if output_mode == "Japanese":
        if kind in ["increase", "decrease"]:
            return f"{term_text}{n}回"
        return f"{term_text}{n}目"
    return f"{term_text}{n}"

def format_stitch_count(number: str, output_mode: str) -> str:
    n = str(number).strip()
    if output_mode == "Simplified Chinese":
        return f"{n}针"
    if output_mode == "Traditional Chinese":
        return f"{n}針"
    if output_mode == "Japanese":
        return f"{n}目"
    return f"{n} sts"


CHAIN_START_INSTRUCTION_ID = "st_090_start_in_stitch"
CHAIN_START_INSTRUCTION_RE = re.compile(
    r"倒\s*(?:[數数]\s*第\s*)?(?P<number>\d+|[一二三四五六七八九十]+)\s*(?:[針针]|(?:回\s*)?[鉤钩鈎勾])"
)
BARE_CHAIN_START_RECOVERY_RE = re.compile(
    r"倒\s*(?![數数])(?P<number>\d+|[一二三四五六七八九十]+)\s*(?P<context_sep>[\.:：,，;；、。．])?"
)
CHAIN_START_BEFORE_CONTEXT_RE = re.compile(
    r"(?:ch|chain|鎖針|锁针|辮子針|辫子针)\s*[\.:：,，;；、。．]*\s*$",
    flags=re.I,
)
CHAIN_START_AFTER_CONTEXT_RE = re.compile(
    r"^\s*[\.:：,，;；、。．]*\s*(?:sl\s*st|slst|sc|dc|tr|hdc|inc|dec|mr|ch|[XVAWFTESLM])(?=$|[^A-Za-z])",
    flags=re.I,
)


def parse_small_chinese_number(value: str) -> Optional[int]:
    token = str(value or "").strip()
    if not token:
        return None
    if token.isdigit():
        return int(token)
    digits = {
        "零": 0,
        "一": 1,
        "二": 2,
        "兩": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if token in digits:
        return digits[token]
    if token == "十":
        return 10
    if "十" in token:
        left, _, right = token.partition("十")
        tens = digits.get(left, 1 if left == "" else None)
        ones = digits.get(right, 0 if right == "" else None)
        if tens is not None and ones is not None:
            return tens * 10 + ones
    return None


def english_ordinal(number: int) -> str:
    suffix = "th"
    if number % 100 not in {11, 12, 13}:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def get_chain_start_instruction_row(df: pd.DataFrame) -> Optional[pd.Series]:
    if df is None or df.empty or "stitch_id" not in df.columns:
        return None
    active_df = get_active_search_df(df)
    matches = active_df[active_df["stitch_id"].astype(str).str.strip() == CHAIN_START_INSTRUCTION_ID]
    if matches.empty:
        return None
    return matches.iloc[0]


def chain_start_template_from_row(row: pd.Series, output_mode: str) -> str:
    if row is None:
        return ""
    if output_mode in ["English — US", "English US terms"]:
        options = [row.get("US_term", "")] + split_aliases(row.get("US_term_alias", ""))
        return next((str(v).strip() for v in options if "the ..." in str(v)), str(row.get("US_term", "")).strip())
    if output_mode in ["English — UK", "English UK terms"]:
        options = [row.get("UK_term", "")] + split_aliases(row.get("UK_term_alias", ""))
        return next((str(v).strip() for v in options if "the ..." in str(v)), str(row.get("UK_term", "") or row.get("US_term", "")).strip())
    if output_mode == "Japanese" and not str(row.get("Japanese", "")).strip():
        options = [row.get("US_term", "")] + split_aliases(row.get("US_term_alias", ""))
        return next((str(v).strip() for v in options if "the ..." in str(v)), str(row.get("US_term", "")).strip())
    return term_from_row(row, output_mode)


def format_chain_start_instruction(number: int, df: pd.DataFrame, output_mode: str) -> str:
    row = get_chain_start_instruction_row(df)
    if row is None:
        if output_mode == "Simplified Chinese":
            return f"倒{number}针"
        if output_mode == "Traditional Chinese":
            return f"倒{number}針"
        return f"Start in the {english_ordinal(number)} chain from hook"
    template = chain_start_template_from_row(row, output_mode)
    if not template:
        template = str(row.get("US_term", "") or "start in ... chain from hook").strip()
    replacement = english_ordinal(number) if output_mode in ["English — US", "English — UK", "English US terms", "English UK terms", "Japanese"] else str(number)
    out = template.replace("...", replacement)
    if output_mode == "Simplified Chinese":
        out = to_simplified(out)
    if output_mode in ["English — US", "English — UK", "English US terms", "English UK terms", "Japanese"] and out:
        out = out[0].upper() + out[1:]
    return out


def has_bare_chain_start_context(source: str, start: int, end: int) -> bool:
    before = str(source or "")[:start]
    after = str(source or "")[end:]
    before_window = before[-40:]
    after_window = after[:40]
    return bool(
        CHAIN_START_BEFORE_CONTEXT_RE.search(before_window)
        or CHAIN_START_AFTER_CONTEXT_RE.search(after_window)
    )


def replace_chain_start_instructions(
    text: str,
    df: pd.DataFrame,
    output_mode: str,
    protect: Optional[Callable[[str], str]] = None,
) -> str:
    def repl(m: re.Match) -> str:
        number = parse_small_chinese_number(m.group("number"))
        if number is None:
            return m.group(0)
        translated = format_chain_start_instruction(number, df, output_mode)
        rendered = protect(translated) if protect is not None else translated
        source = m.string
        before = source[m.start() - 1] if m.start() > 0 else ""
        after = source[m.end()] if m.end() < len(source) else ""
        prefix = " " if before and not before.isspace() and before not in "([（{：:,，;；、" else ""
        suffix = " " if after and not after.isspace() and after not in ")]）}：:,，;；、." else ""
        return f"{prefix}{rendered}{suffix}"

    s = CHAIN_START_INSTRUCTION_RE.sub(repl, str(text or ""))

    def bare_repl(m: re.Match) -> str:
        if not has_bare_chain_start_context(m.string, m.start(), m.end()):
            return m.group(0)
        return repl(m)

    return BARE_CHAIN_START_RECOVERY_RE.sub(bare_repl, s)


def translate_chain_start_expression_if_full(text: str, df: pd.DataFrame, output_mode: str) -> Optional[str]:
    s = unicodedata.normalize("NFKC", str(text or "")).strip()
    m = re.fullmatch(CHAIN_START_INSTRUCTION_RE, s)
    if not m:
        return None
    number = parse_small_chinese_number(m.group("number"))
    if number is None:
        return None
    return format_chain_start_instruction(number, df, output_mode)


def contains_chinese_stitch_count(text: str) -> bool:
    return bool(re.search(r"(?<![A-Za-z0-9.])\d+\s*[針针](?![A-Za-z0-9])", str(text)))

def format_group_with_stitch_count(inner: str, count: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str) -> str:
    parts = [translate_group_part(part, index, df, output_mode) for part in split_expression_parts(inner)]
    return f"({', '.join(parts)})({format_stitch_count(count, output_mode)})"

def format_symbol_with_stitch_count(term: str, count: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str) -> str:
    term_clean = re.sub(r"\s+", "", term).upper()
    term_text = lookup_expression_symbol(term_clean, index, df, output_mode)
    return f"{term_text}({format_stitch_count(count, output_mode)})"

def lookup_expression_symbol(term: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str) -> str:
    term_clean = re.sub(r"\s+", "", str(term or "")).upper()
    if term_clean == "M":
        m_key = norm_text(term_clean)
        for _, row in get_active_search_df(df).iterrows():
            aliases = split_aliases(row.get("Chinese_abb", ""))
            values = [row.get("Chinese_abb", "")] + aliases
            if any(norm_text(value) == m_key for value in values):
                us_abb = norm_text(row.get("US_abb", ""))
                uk_abb = norm_text(row.get("UK_abb", ""))
                if us_abb == "sc3tog" or uk_abb == "dc3tog":
                    return term_from_row(row, output_mode, prefer_abbrev=(output_mode in ["English — US", "English — UK", "English US terms", "English UK terms"]))
    return lookup_term(term_clean, index, df, output_mode, prefer_abbrev=(output_mode in ["English — US", "English — UK", "English US terms", "English UK terms"]))

COUNTED_TOKEN_TERM_PATTERN = r"sl\s*st|slst|sts?|stitches?|sc|inc|dec|hdc|dc|tr|mr|ch|blo|flo|fo|[XVATFESLWM]{1,2}"


def translate_counted_token(
    number: str,
    term: str,
    index: Dict[str, int],
    df: pd.DataFrame,
    output_mode: str,
    protect: Optional[Callable[[str], str]] = None,
) -> str:
    """Translate compact number-before-term tokens consistently across paths."""
    n = str(number)
    term_clean = re.sub(r"\s+", "", str(term or ""))
    key = norm_text(term_clean)
    if key in {"st", "sts", "stitch", "stitches"}:
        if output_mode == "Simplified Chinese":
            return protect(f"{n}针") if protect is not None else f"{n}针"
        if output_mode == "Traditional Chinese":
            return protect(f"{n}針") if protect is not None else f"{n}針"
        if output_mode == "Japanese":
            return protect(f"{n}目") if protect is not None else f"{n}目"
        term_text = lookup_term(term_clean, index, df, output_mode, prefer_abbrev=True)
        term_text = protect(term_text) if protect is not None else term_text
        return f"{n} {term_text}"
    term_text = lookup_expression_symbol(term_clean, index, df, output_mode)
    term_text = protect(term_text) if protect is not None else term_text
    return format_counted_term(term_text, n, term_kind(term_clean, index, df), output_mode)

def normalize_decimal_mm(text: str) -> str:
    return re.sub(r"\b(\d+)\s*[\.,，]\s*(\d)\s*m\s*m\b", r"\1.\2mm", str(text), flags=re.I)

def translate_around_connector(text: str, output_mode: str) -> str:
    if output_mode == "Traditional Chinese":
        return re.sub(r"\b(?:work\s+|rnd\s+)?around\b", "一圈", text, flags=re.I)
    if output_mode == "Simplified Chinese":
        return re.sub(r"\b(?:work\s+|rnd\s+)?around\b", "一圈", text, flags=re.I)
    if output_mode == "Japanese":
        return re.sub(r"\b(?:work\s+|rnd\s+)?around\b", "1周", text, flags=re.I)
    return text

def join_parts(parts: List[str], output_mode: str) -> str:
    parts = [p for p in parts if p]
    if output_mode in ["Traditional Chinese", "Simplified Chinese", "Japanese"]:
        return "，".join(parts)
    return ", ".join(parts)

def repeat_phrase(inner: str, repeat: str, output_mode: str) -> str:
    if output_mode == "Traditional Chinese":
        return f"（{inner}）重複{repeat}次"
    if output_mode == "Simplified Chinese":
        return f"（{inner}）重复{repeat}次"
    if output_mode == "Japanese":
        return f"（{inner}）を{repeat}回繰り返す"
    return f"({inner}) x{repeat}"

def row_to_chinese(row: pd.Series) -> str:
    zh = str(row.get("Chinese_term", "")).strip()
    return zh or str(row.get("US_term", "")).strip()


NORMALIZED_LOOKUP_INDEX_STATS = {
    "enabled": "Yes",
    "last_key": "",
    "build_count": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "index_size": 0,
    "duplicate_keys": 0,
    "indexed_lookup_attempts": 0,
    "indexed_lookup_hits": 0,
    "indexed_lookup_misses": 0,
    "fallback_lookup_attempts": 0,
    "fallback_lookup_hits": 0,
    "fallback_lookup_misses": 0,
    "index_error": "",
}


def build_normalized_lookup_index(
    index: Dict[str, int],
    all_term_index: Dict[str, int],
    source_mode: str,
) -> Dict[str, int]:
    NORMALIZED_LOOKUP_INDEX_STATS["last_key"] = f"source_mode:{source_mode}"
    NORMALIZED_LOOKUP_INDEX_STATS["cache_misses"] += 1
    NORMALIZED_LOOKUP_INDEX_STATS["build_count"] += 1
    combined: Dict[str, int] = {}
    duplicate_count = 0
    for term_key, row_idx in index.items():
        if term_key and term_key not in combined:
            combined[term_key] = row_idx
        elif term_key:
            duplicate_count += 1
    for term_key, row_idx in all_term_index.items():
        if term_key and term_key not in combined:
            combined[term_key] = row_idx
        elif term_key:
            duplicate_count += 1
    NORMALIZED_LOOKUP_INDEX_STATS["index_size"] = len(combined)
    NORMALIZED_LOOKUP_INDEX_STATS["duplicate_keys"] = duplicate_count
    return combined


def lookup_row(term: str, index: Dict[str, int], df: pd.DataFrame) -> Optional[pd.Series]:
    profile_count("lookup_row calls")
    profile_start = time.perf_counter() if TRANSLATION_PROFILE is not None else None
    key = norm_text(term)
    try:
        NORMALIZED_LOOKUP_INDEX_STATS["indexed_lookup_attempts"] += 1
        normalized_index = df.attrs.get("normalized_lookup_index", {})
        if normalized_index and key in normalized_index:
            NORMALIZED_LOOKUP_INDEX_STATS["indexed_lookup_hits"] += 1
            profile_count("lookup_row normalized index hits")
            if profile_start is not None:
                profile_add_time("term lookup: lookup_row", time.perf_counter() - profile_start)
            return df.loc[normalized_index[key]]
        NORMALIZED_LOOKUP_INDEX_STATS["indexed_lookup_misses"] += 1
    except Exception as e:
        NORMALIZED_LOOKUP_INDEX_STATS["index_error"] = str(e)
        NORMALIZED_LOOKUP_INDEX_STATS["indexed_lookup_misses"] += 1

    NORMALIZED_LOOKUP_INDEX_STATS["fallback_lookup_attempts"] += 1
    if key in index:
        NORMALIZED_LOOKUP_INDEX_STATS["fallback_lookup_hits"] += 1
        profile_count("lookup_row fast hits")
        if profile_start is not None:
            profile_add_time("term lookup: lookup_row", time.perf_counter() - profile_start)
        return df.loc[index[key]]
    # Search across all key columns as fallback, useful when source mode is Chinese but OCR produced English-style terms.
    # RC9c preserves the old fallback search order, but uses a prebuilt dictionary instead of scanning the CSV per lookup.
    all_term_index = df.attrs.get("all_term_index", {})
    if not all_term_index:
        all_term_index = build_all_term_index(df)
        df.attrs["all_term_index"] = all_term_index
    profile_count("lookup_row fallback dictionary checks")
    if key in all_term_index:
        NORMALIZED_LOOKUP_INDEX_STATS["fallback_lookup_hits"] += 1
        profile_count("lookup_row fallback hits")
        if profile_start is not None:
            profile_add_time("term lookup: lookup_row", time.perf_counter() - profile_start)
        return df.loc[all_term_index[key]]
    NORMALIZED_LOOKUP_INDEX_STATS["fallback_lookup_misses"] += 1
    if profile_start is not None:
        profile_add_time("term lookup: lookup_row", time.perf_counter() - profile_start)
    return None

def lookup_term(term: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str = "Traditional Chinese", prefer_abbrev: bool = False) -> str:
    profile_count("lookup_term calls")
    profile_start = time.perf_counter() if TRANSLATION_PROFILE is not None else None
    try:
        row = lookup_row(term, index, df)
        if row is not None:
            return term_from_row(row, output_mode, prefer_abbrev=prefer_abbrev)
        fallback_zh = {
            "sc": "短針", "x": "短針", "inc": "加針", "v": "加針", "dec": "減針", "a": "減針", "mr": "環狀起針",
            "magic ring": "環狀起針", "magic circle": "環狀起針", "adjustable ring": "環狀起針",
            "slst": "引拔針", "sl st": "引拔針", "sl": "引拔針", "hdc": "中長針", "t": "中長針", "dc": "長針", "f": "長針", "tr": "長長針", "e": "長長針",
            "fo": "收線", "blo": "後半針", "flo": "前半針", "ch": "鎖針", "chain": "鎖針", "chains": "鎖針", "st": "針", "sts": "針", "stitch": "針", "stitches": "針",
        }
        fallback_us = {
            "x": "sc", "v": "inc", "a": "dec", "t": "hdc", "f": "dc", "e": "tr", "sl": "sl st",
            "sc": "sc", "inc": "inc", "dec": "dec", "mr": "MR", "magic ring": "MR", "magic circle": "MR", "adjustable ring": "MR", "slst": "sl st", "sl st": "sl st", "ch": "ch", "chain": "ch", "chains": "ch", "st": "st", "sts": "sts", "stitch": "stitch", "stitches": "stitches",
        }
        key = norm_text(term)
        if output_mode == "Simplified Chinese":
            return to_simplified(fallback_zh.get(key, term))
        if output_mode == "Traditional Chinese":
            return fallback_zh.get(key, term)
        if output_mode in ["English — US", "English — UK", "English US terms", "English UK terms"]:
            return fallback_us.get(key, term)
        if output_mode == "Japanese":
            zh = fallback_zh.get(key, term)
            jp = {"短針":"細編み", "加針":"増し目", "減針":"減らし目", "環狀起針":"輪の作り目", "引拔針":"引き抜き編み", "中長針":"中長編み", "長針":"長編み"}
            return jp.get(zh, term)
        return term
    finally:
        if profile_start is not None:
            profile_add_time("term lookup: lookup_term", time.perf_counter() - profile_start)


CSV_TERM_CACHE: Dict[Tuple[object, ...], Tuple[str, ...]] = {}
CSV_TERM_CACHE_STATS = {
    "hits": 0,
    "misses": 0,
    "generation_count": 0,
    "served_from_cache_count": 0,
    "last_key": "",
    "last_error": "",
    "last_terms_returned": 0,
}


def csv_term_cache_key(df: pd.DataFrame) -> Tuple[object, ...]:
    try:
        content_hash = hashlib.md5(
            pd.util.hash_pandas_object(df.astype(str), index=True).values.tobytes()
        ).hexdigest()
    except Exception:
        content_hash = "content-hash-unavailable"
    return (
        int(len(df)),
        tuple(str(col) for col in df.columns),
        tuple(int(v) for v in df.shape),
        content_hash,
    )


def generate_all_csv_terms_uncached(df: pd.DataFrame) -> List[str]:
    """Return all searchable terms/aliases from the crochet CSV.

    This powers V24's term-replacement engine: do not hard-code whole
    sentences; scan every OCR line for known crochet terms from the CSV.
    """
    cols = [
        "US_term", "US_term_alias", "US_abb", "US_abb1",
        "UK_term", "UK_term_alias", "UK_abb", "UK_abb1",
        "Chinese_term", "Chinese_term_alias", "Chinese_abb",
        "Japanese", "Japanese_alias",
    ]
    df = get_active_search_df(df)
    seen = set()
    terms: List[str] = []
    for _, row in df.iterrows():
        profile_count("get_all_csv_terms row scans")
        for col in cols:
            if col not in df.columns:
                continue
            vals = [row.get(col, "")] + split_aliases(row.get(col, ""))
            for v in vals:
                profile_count("alias values inspected")
                t = unicodedata.normalize("NFKC", str(v)).strip()
                if not t:
                    continue
                key = norm_text(t)
                # Keep single-letter stitch symbols only; avoid broad accidental words.
                if len(key) == 1 and key not in {"x", "v", "a", "t", "f", "e"}:
                    continue
                if key not in seen:
                    seen.add(key)
                    terms.append(t)
    # Longest first so "magic ring" is replaced before "ring", and "sl st" before "st".
    terms.sort(key=lambda x: len(norm_text(x)), reverse=True)
    profile_count("protected terms generated", len(terms))
    return terms


def get_all_csv_terms(df: pd.DataFrame) -> List[str]:
    profile_count("get_all_csv_terms calls")
    profile_start = time.perf_counter() if TRANSLATION_PROFILE is not None else None
    try:
        key = csv_term_cache_key(df)
        key_text = hashlib.md5(repr(key).encode("utf-8")).hexdigest()
        CSV_TERM_CACHE_STATS["last_key"] = key_text
        if key in CSV_TERM_CACHE:
            CSV_TERM_CACHE_STATS["hits"] += 1
            CSV_TERM_CACHE_STATS["served_from_cache_count"] += 1
            terms = list(CSV_TERM_CACHE[key])
            CSV_TERM_CACHE_STATS["last_terms_returned"] = len(terms)
            profile_count("get_all_csv_terms served from cache")
            profile_count("protected terms returned from cache", len(terms))
            return terms
        CSV_TERM_CACHE_STATS["misses"] += 1
        CSV_TERM_CACHE_STATS["generation_count"] += 1
        terms = generate_all_csv_terms_uncached(df)
        CSV_TERM_CACHE[key] = tuple(terms)
        CSV_TERM_CACHE_STATS["last_terms_returned"] = len(terms)
        return list(terms)
    except Exception as e:
        CSV_TERM_CACHE_STATS["last_error"] = str(e)
        terms = generate_all_csv_terms_uncached(df)
        CSV_TERM_CACHE_STATS["last_terms_returned"] = len(terms)
        return terms
    finally:
        if profile_start is not None:
            profile_add_time("alias lookup / CSV term list", time.perf_counter() - profile_start)


def _ascii_term_regex(term: str) -> str:
    """Regex for English/abbreviation terms with safe boundaries."""
    escaped = re.escape(term.strip())
    escaped = re.sub(r"\\\s+", r"\\s+", escaped)
    return rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"


def _looks_like_prose_line(text: str) -> bool:
    """Return True for ordinary instruction sentences mixed with crochet terms.

    Formulae like "ch, (sc, inc)x8, slst (24)" should still go through
    the expression parser. Sentences like "Start with 8sc in a Magic ring"
    should prefer CSV term replacement.
    """
    s = str(text or "").strip()
    if not s:
        return False
    crochet_words = {
        "sc", "inc", "dec", "hdc", "dc", "tr", "slst", "sl", "st", "sts",
        "ch", "mr", "blo", "flo", "fo", "magic", "ring", "circle",
        "stitch", "stitches", "chain", "chains",
    }
    words = re.findall(r"[A-Za-z]{3,}", s)
    non_crochet = [w for w in words if w.lower() not in crochet_words]
    return bool(non_crochet)


def replace_csv_terms_in_line(text: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str) -> str:
    """Replace known crochet terms inside a normal sentence.

    Example:
        turn and slst until the end
        -> 反轉 and 引拔 until the end

    This is intentionally *not* a general translation engine. Unknown ordinary
    language remains unchanged. The goal is to protect and translate crochet
    terminology wherever it appears in a sentence.
    """
    profile_count("replace_csv_terms_in_line calls")
    profile_start = time.perf_counter() if TRANSLATION_PROFILE is not None else None
    s = normalize_decimal_mm(unicodedata.normalize("NFKC", str(text or "")).strip())
    if not s:
        if profile_start is not None:
            profile_add_time("CSV replacement loops", time.perf_counter() - profile_start)
        return ""

    generated_terms: List[str] = []

    def protect_generated_term(value: str) -> str:
        marker = f"@@RC9D_TERM_{len(generated_terms)}@@"
        generated_terms.append(str(value))
        return marker

    def restore_generated_terms(value: str) -> str:
        out_value = str(value)
        for i, original_value in enumerate(generated_terms):
            out_value = out_value.replace(f"@@RC9D_TERM_{i}@@", original_value)
        return out_value

    s = replace_chain_start_instructions(s, df, output_mode, protect=protect_generated_term)

    def stitch_count_repl(m: re.Match) -> str:
        return protect_generated_term(format_stitch_count(m.group(1), output_mode))

    profile_count("regex passes estimated")
    s = re.sub(r"(?<![A-Za-z0-9.])(\d+)\s*[針针](?![A-Za-z0-9])", stitch_count_repl, s)

    # 1) Compact counted terms: 8sc, 4ch, 6sts, 2 dc.
    counted_pat = re.compile(
        rf"(?<![A-Za-z0-9])(\d+)\s*({COUNTED_TOKEN_TERM_PATTERN})\b",
        flags=re.I,
    )

    def counted_repl(m: re.Match) -> str:
        n, term = m.groups()
        return translate_counted_token(n, term, index, df, output_mode, protect=protect_generated_term)

    profile_count("regex passes estimated")
    out = counted_pat.sub(counted_repl, s)

    # V29: term-before-number shorthand, e.g. ch1 / ch 1 / sc 6.
    # Many English patterns write "ch1" at the end of a long round, or
    # "sc 6 into magic ring". V25/V28 only handled number-before-term
    # such as 8sc / 4ch, so ch1 was left untranslated.
    term_number_pat = re.compile(
        r"(?<![A-Za-z0-9])(sl\s*st|slst|sts?|stitches?|sc|inc|dec|hdc|dc|tr|mr|ch|blo|flo|fo)\s*(\d+)(?![A-Za-z0-9])",
        flags=re.I,
    )

    def term_number_repl(m: re.Match) -> str:
        term, n = m.groups()
        term_clean = re.sub(r"\s+", "", term)
        key = norm_text(term_clean)
        if key in {"st", "sts", "stitch", "stitches"}:
            if output_mode == "Simplified Chinese":
                return protect_generated_term(f"{n}针")
            if output_mode == "Traditional Chinese":
                return protect_generated_term(f"{n}針")
            if output_mode == "Japanese":
                return protect_generated_term(f"{n}目")
            return f"{n} {protect_generated_term(lookup_term(term_clean, index, df, output_mode, prefer_abbrev=True))}"
        term_text = lookup_term(term_clean, index, df, output_mode, prefer_abbrev=(output_mode in ["English — US", "English — UK", "English US terms", "English UK terms"]))
        return format_counted_term(protect_generated_term(term_text), n, term_kind(term_clean, index, df), output_mode)

    profile_count("regex passes estimated")
    out = term_number_pat.sub(term_number_repl, out)

    # V29: safe repair for common OCR confusion in crochet shorthand.
    # "linc" is usually OCR's lowercase L + inc, meaning "1inc".
    profile_count("regex passes estimated")
    out = re.sub(r"(?<![A-Za-z0-9])linc(?![A-Za-z0-9])", lambda m: term_number_repl(type('M', (), {'groups': lambda self: ('inc','1')})()), out, flags=re.I)

    # 2) Phrase and token replacement from CSV terms/aliases.
    protected_terms = get_all_csv_terms(df)
    # V25: include common OCR spellings that may not appear literally in CSV.
    protected_terms.extend([
        "slst", "sl st", "magic ring", "magic circle", "adjustable ring",
        "stitch", "stitches", "sts", "turn", "fasten off", "weave in ends",
    ])
    # De-duplicate while preserving longest-first order.
    seen_terms = set()
    protected_terms = sorted(
        [t for t in protected_terms if not (norm_text(t) in seen_terms or seen_terms.add(norm_text(t)))],
        key=lambda x: len(norm_text(x)),
        reverse=True,
    )
    for term in protected_terms:
        profile_count("protected terms looped")
        key = norm_text(term)
        if not key:
            continue
        # Never replace bare single-letter symbols inside ordinary sentences.
        # Example: the English article "a" must not become "減針".
        # Counted forms such as 2A / 6X are handled earlier by counted_pat.
        if re.fullmatch(r"[A-Za-z]", key):
            profile_count("regex passes estimated")
            continue
        replacement = lookup_term(term, index, df, output_mode, prefer_abbrev=(output_mode in ["English — US", "English — UK", "English US terms", "English UK terms"]))
        if not replacement:
            continue
        # Avoid replacing single-letter symbols in prose unless they are clearly separated.
        if re.fullmatch(r"[A-Za-z0-9 ]+", term):
            profile_count("regex passes estimated")
            if norm_text(replacement) == key:
                continue
            pat = re.compile(_ascii_term_regex(term), flags=re.I)
            profile_count("regex passes estimated")
            out = pat.sub(replacement, out)
        else:
            # Chinese/Japanese terms: direct safe replacement.
            out = out.replace(term, replacement)
            cjk_variants = {
                "針": "[針针]", "內": "[內内]", "後": "[後后]", "環": "[環环]",
                "鎖": "[鎖锁]", "長": "[長长]", "減": "[減减]", "線": "[線线]",
                "繞": "[繞绕]", "鈎": "[鈎钩勾]", "鉤": "[鉤钩勾]",
            }
            variant_pat = "".join(cjk_variants.get(ch, re.escape(ch)) for ch in term)
            profile_count("regex passes estimated")
            out = re.sub(variant_pat, replacement, out)

    # V28: small crochet-context connectors. Check the ORIGINAL sentence, not
    # only the already-replaced output. In v27, "6 inc around" became
    # "加針6次 around" first, so the old English-token check missed "around".
    profile_count("regex passes estimated")
    has_crochet_context = bool(re.search(
        r"\b(sc|inc|dec|hdc|dc|tr|sl\s*st|slst|ch|sts?|stitches?|blo|flo|fo|mr|magic\s+ring|x|v|a)\b",
        s,
        flags=re.I,
    )) or bool(re.search(r"\b(?:work\s+|rnd\s+)?around\b", s, flags=re.I))
    if has_crochet_context:
        profile_count("regex passes estimated")
        out = translate_around_connector(out, output_mode)

    if profile_start is not None:
        profile_add_time("CSV replacement loops", time.perf_counter() - profile_start)
    return restore_generated_terms(out)

def term_kind(term: str, index: Dict[str, int], df: pd.DataFrame) -> str:
    row = lookup_row(term, index, df)
    if row is not None:
        cat = norm_text(row.get("category", ""))
        if "increase" in cat:
            return "increase"
        if "decrease" in cat:
            return "decrease"
    key = norm_text(term)
    if key in ["inc", "v"]:
        return "increase"
    if key in ["dec", "a"]:
        return "decrease"
    return "stitch"

@profile_function("expression parsing: split_expression_parts", "split_expression_parts calls")
def split_expression_parts(text: str) -> List[str]:
    """Split crochet expressions on separators, but keep commas/dots inside brackets.

    Naive splitting breaks common rows such as:
    - ch, (sc, inc)x8, slst (24)
    - 6(X,V)
    - 2T.7X.3T.2Tv

    This helper only splits when we are not inside parentheses/brackets.
    """
    if text is None:
        return []
    s = unicodedata.normalize("NFKC", str(text)).strip()
    parts: List[str] = []
    buf: List[str] = []
    depth = 0
    for i, ch in enumerate(s):
        if ch in "([{（【":
            depth += 1
            buf.append(ch)
            continue
        if ch in ")]）】}":
            depth = max(0, depth - 1)
            buf.append(ch)
            continue
        # Dot is a separator in mainland symbol strings, but only outside brackets.
        if depth == 0 and ch == ".":
            prev_ch = s[i - 1] if i > 0 else ""
            next_ch = s[i + 1] if i + 1 < len(s) else ""
            if prev_ch.isdigit() and next_ch.isdigit():
                buf.append(ch)
                continue
        if depth == 0 and ch in [",", "，", "、", ";", "；", "。", "."]:
            item = "".join(buf).strip()
            if item:
                parts.append(item)
            buf = []
            continue
        buf.append(ch)
    item = "".join(buf).strip()
    if item:
        parts.append(item)
    return parts

def translate_group_part(part: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str = "Traditional Chinese") -> str:
    part_text = normalize_decimal_mm(unicodedata.normalize("NFKC", str(part or "")).strip())
    if not part_text:
        return ""
    translated = translate_expression(part_text, index, df, output_mode)
    return translated if translated else translate_piece(part_text, index, df, output_mode)

@profile_function("translate_piece()", "translate_piece calls")
def translate_piece(piece: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str = "Traditional Chinese") -> str:
    p = normalize_decimal_mm(unicodedata.normalize("NFKC", piece).strip())
    if not p:
        return ""

    chain_start = translate_chain_start_expression_if_full(p, df, output_mode)
    if chain_start is not None:
        return chain_start

    # Repeat group as one comma-split part, e.g. (sc, inc)x8 / (2sc, dec, 2sc)x8.
    m = re.fullmatch(r"\((.*?)\)\s*(?:[xX×]|\*)\s*(\d+)\s*[（(]\s*(\d+)\s*[)）]", p)
    if m:
        inside, repeat, total = m.groups()
        parts = [translate_group_part(part, index, df, output_mode) for part in split_expression_parts(inside)]
        return f"{repeat_phrase(join_parts(parts, output_mode), repeat, output_mode)} ({total})"

    m = re.fullmatch(r"\((.*?)\)\s*(?:[xX×]|\*)\s*(\d+)", p)
    if m:
        inside, repeat = m.groups()
        parts = [translate_group_part(part, index, df, output_mode) for part in split_expression_parts(inside)]
        return repeat_phrase(join_parts(parts, output_mode), repeat, output_mode)

    m = re.fullmatch(r"\((.*?)\)\s*[（(]\s*(\d+)\s*[針针]\s*[)）]", p)
    if m:
        inside, count = m.groups()
        return format_group_with_stitch_count(inside, count, index, df, output_mode)

    # Bare bracketed group without explicit repeat, e.g. (10X,V).
    m = re.fullmatch(r"\((.*?)\)", p)
    if m:
        parts = [translate_group_part(part, index, df, output_mode) for part in split_expression_parts(m.group(1))]
        return f"（{join_parts(parts, output_mode)}）" if output_mode in ["Traditional Chinese", "Simplified Chinese", "Japanese"] else f"({join_parts(parts, output_mode)})"

    # Term with total count note, e.g. slst (24) / turn (6). Keep the count.
    m = re.fullmatch(r"(SLST|SL\s*ST|CH|SC|INC|DEC|HDC|DC|TR|MR|BLO|FLO|FO)\s*[（(]\s*(\d+)\s*[)）]", p, flags=re.I)
    if m:
        term, total = m.groups()
        term_text = lookup_term(term.replace(" ", ""), index, df, output_mode, prefer_abbrev=(output_mode in ["English — US", "English — UK", "English US terms", "English UK terms"]))
        return f"{term_text} ({total})"

    m = re.fullmatch(r"([XVATFESLWM]{1,2}|SC|INC|DEC|HDC|DC|TR|SLST|MR)\s*[（(]\s*(\d+)\s*[針针]\s*[)）]", p, flags=re.I)
    if m:
        term, count = m.groups()
        return format_symbol_with_stitch_count(term, count, index, df, output_mode)

    m = re.fullmatch(r"(\d+)\s*[針针]", p)
    if m:
        return format_stitch_count(m.group(1), output_mode)

    # Bare English crochet terms.
    if re.fullmatch(r"SLST|SL\s*ST|CH|SC|INC|DEC|HDC|DC|TR|MR|BLO|FLO|FO|ST|STS|STITCH|STITCHES", p, flags=re.I):
        return lookup_term(p.replace(" ", ""), index, df, output_mode, prefer_abbrev=(output_mode in ["English — US", "English — UK", "English US terms", "English UK terms"]))

    # Chinese-mainland shorthand: 2X / 10x / 1V / 6A / 2SL
    m = re.fullmatch(r"(\d+)\s*([XVATFESLWM]{1,2})", p, flags=re.I)
    if m:
        n, term = m.groups()
        return translate_counted_token(n, term, index, df, output_mode)

    # English shorthand: 6SC / 1DEC / 2 SC
    m = re.fullmatch(r"(\d+)\s*(SC|INC|DEC|HDC|DC|TR|SLST|SL\s*ST|MR|CH|BLO|FLO|FO|STS?|STITCHES?)", p, flags=re.I)
    if m:
        n, term = m.groups()
        return translate_counted_token(n, term, index, df, output_mode)

    # Bare V / X / A or SC / INC / DEC
    if re.fullmatch(r"[XVATFESLWM]{1,2}|SC|INC|DEC|HDC|DC|TR|SLST|MR", p, flags=re.I):
        return lookup_expression_symbol(p.upper(), index, df, output_mode)

    # SC all around / 不加減 / 不加減交叉X
    if re.search(r"\bSC\s+all\s+around\b", p, flags=re.I) or "不加減" in p or "不加减" in p:
        cross = "交叉" in p
        # Safe rule: 不加減X / 不加减X means no increase/decrease, usually X all around.
        # For 交叉X, keep the wording conservative because the exact stitch is not confirmed in CSV yet.
        if output_mode == "Simplified Chinese":
            return "交叉X，不加不减一圈" if cross else "短针不加不减一圈"
        if output_mode == "Traditional Chinese":
            return "交叉X，不加不減一圈" if cross else "短針不加不減一圈"
        if output_mode == "Japanese":
            return "交差X、増減なしで1周" if cross else "細編みで増減なし1周"
        return "cross X all around (not yet confirmed)" if cross else "sc all around"

    # in MR / 環起 / 环起
    if re.search(r"\bin\s+MR\b", p, flags=re.I):
        before = re.sub(r"\bin\s+MR\b", "", p, flags=re.I).strip()
        before_out = translate_piece(before, index, df, output_mode) if before else ""
        if output_mode == "Simplified Chinese":
            return f"在环状起针中钩{before_out}" if before_out else "环状起针"
        if output_mode == "Traditional Chinese":
            return f"在環狀起針中鈎{before_out}" if before_out else "環狀起針"
        if output_mode == "Japanese":
            return f"輪の作り目に{before_out}" if before_out else "輪の作り目"
        return f"{before_out} in MR" if before_out else "MR"

    m = re.search(r"(?:環起|环起|環狀起針|环状起针|環形起針|环形起针|圈起|起圈|環|环)\s*(\d+)\s*([XVATFESLWM]|SC|INC|DEC)?", p, flags=re.I)
    if m:
        n, term = m.groups()
        term = term or "X"
        counted = translate_piece(f"{n}{term}", index, df, output_mode)
        if output_mode == "Simplified Chinese":
            return f"环状起针，{counted}"
        if output_mode == "Traditional Chinese":
            return f"環狀起針，{counted}"
        if output_mode == "Japanese":
            return f"輪の作り目、{counted}"
        return f"MR, {counted}"

    # V26 fallback: expression fragments can contain embedded terms rather than
    # being a single clean token, e.g. "40sc in BLO" or "6sts in between".
    # Run the CSV replacement engine before giving up.
    csv_replaced = replace_csv_terms_in_line(p, index, df, output_mode)
    if csv_replaced and (norm_text(csv_replaced) != norm_text(p) or (contains_chinese_stitch_count(p) and csv_replaced != p)):
        return csv_replaced

    return p

@profile_function("translate_expression()", "translate_expression calls")
def translate_expression(expr: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str = "Traditional Chinese") -> str:
    original = unicodedata.normalize("NFKC", expr).strip()
    if not original:
        return ""

    chain_start = translate_chain_start_expression_if_full(original, df, output_mode)
    if chain_start is not None:
        return chain_start

    generated_chain_terms: List[str] = []

    def protect_chain_start_term(value: str) -> str:
        marker = f"@@R21A_{len(generated_chain_terms)}@@"
        generated_chain_terms.append(str(value))
        return marker

    def restore_chain_start_terms(value: str) -> str:
        out_value = str(value)
        for i, original_value in enumerate(generated_chain_terms):
            out_value = out_value.replace(f"@@R21A_{i}@@", original_value)
        return out_value

    chain_start_recovered = replace_chain_start_instructions(original, df, output_mode, protect=protect_chain_start_term)
    if chain_start_recovered != original:
        original = chain_start_recovered

    total_counts = re.findall(r"\[\s*(\d+)\s*\]", original)
    total_suffix = " ".join(f"({format_stitch_count(count, output_mode)})" for count in total_counts)

    def with_total(value: str) -> str:
        value = restore_chain_start_terms(str(value or "").strip())
        if total_suffix:
            return f"{value} {total_suffix}".strip()
        return value

    expr_no_total = re.sub(r"\[[^\]]+\]", "", original).strip()
    expr_no_total = expr_no_total.replace("×", "x")

    # OCR can merge a formula row with nearby prose, e.g.
    # "(9X,A.9X)*3(57) 把它们粘在脸上". Translate the leading formula
    # through the normal parser, then keep/rewrite the trailing text normally.
    m = re.fullmatch(r"(\([^)]*\)\s*(?:[xX]|\*)\s*\d+\s*(?:[（(]\s*\d+\s*[)）])?)(\s+.+)", expr_no_total)
    if m:
        leading_expr, trailing_text = m.groups()
        trailing = replace_csv_terms_in_line(trailing_text.strip(), index, df, output_mode)
        return with_total(f"{translate_expression(leading_expr, index, df, output_mode)} {trailing}".strip())

    # Chinese shorthand with prefix repeat: 8(X,V) / 8 (2x.v)
    m = re.search(r"^(\d+)\s*\((.*?)\)$", expr_no_total, flags=re.I)
    if m:
        repeat, inside = m.groups()
        parts = [translate_group_part(p, index, df, output_mode) for p in split_expression_parts(inside)]
        return with_total(repeat_phrase(join_parts(parts, output_mode), repeat, output_mode))

    # English/general repeat: (2SC, 1DEC)x6 / (1INC, 1SC)x6 / (10X,V)
    m = re.fullmatch(r"\((.*?)\)\s*(?:[xX×]|\*)\s*(\d+)\s*[（(]\s*(\d+)\s*[)）]", expr_no_total)
    if m:
        inside, repeat, total = m.groups()
        parts = [translate_group_part(p, index, df, output_mode) for p in split_expression_parts(inside)]
        return with_total(f"{repeat_phrase(join_parts(parts, output_mode), repeat, output_mode)} ({total})")

    m = re.fullmatch(r"\((.*?)\)\s*(?:[xX×]|\*)\s*(\d+)", expr_no_total)
    if m:
        inside, repeat = m.groups()
        parts = [translate_group_part(p, index, df, output_mode) for p in split_expression_parts(inside)]
        return with_total(repeat_phrase(join_parts(parts, output_mode), repeat, output_mode))

    m = re.fullmatch(r"\((.*?)\)\s*[（(]\s*(\d+)\s*[針针]\s*[)）]", expr_no_total)
    if m:
        inside, count = m.groups()
        return with_total(format_group_with_stitch_count(inside, count, index, df, output_mode))

    # A bracketed group without explicit repeat, e.g. (10X,V)
    m = re.fullmatch(r"\((.*?)\)", expr_no_total)
    if m:
        parts = [translate_group_part(p, index, df, output_mode) for p in split_expression_parts(m.group(1))]
        return with_total(f"（{join_parts(parts, output_mode)}）" if output_mode in ["Traditional Chinese", "Simplified Chinese", "Japanese"] else f"({join_parts(parts, output_mode)})")

    if re.search(r"\bin\s+MR\b", expr_no_total, flags=re.I) or re.search(r"環起|环起|環狀起針|环状起针|環形起針|环形起针|圈起|起圈|環\s*\d|环\s*\d", expr_no_total):
        return with_total(translate_piece(expr_no_total, index, df, output_mode))

    if "," in expr_no_total or "，" in expr_no_total or "、" in expr_no_total or "." in expr_no_total:
        split_parts = split_expression_parts(expr_no_total)
        if len(split_parts) == 1 and split_parts[0] == expr_no_total:
            return with_total(translate_piece(expr_no_total, index, df, output_mode))
        parts = [translate_expression(p, index, df, output_mode) for p in split_parts]
        return with_total(join_parts(parts, output_mode))

    return with_total(translate_piece(expr_no_total, index, df, output_mode))


def repair_ocr_round_token(token: str) -> str:
    """Repair common OCR round labels such as Rl14, RI6, R2g."""
    t = unicodedata.normalize("NFKC", token).strip()
    t = t.replace("：", ":").replace("；", ":").replace(";", ":")
    t = re.sub(r"^r", "R", t, flags=re.I)
    t = re.sub(r"^R[gq](?=\s*:)", "R9", t, flags=re.I)
    t = re.sub(r"^R[lI](?=\s*:)", "R1", t, flags=re.I)
    t = re.sub(r"^R114(?=\s*:)", "R14", t, flags=re.I)
    t = re.sub(r"^R2[gq](?=\s*:)", "R29", t, flags=re.I)

    m = re.match(r"^R([lI])([0-9]+)(.*)$", t)
    if m:
        digits = m.group(2)
        rest = m.group(3)
        # Rl0 / RI0 usually means R10. Rl1 alone usually means R11.
        if digits == "0":
            return "R10" + rest
        if digits == "1":
            return "R11" + rest
        # Rl14 / RI6 means an extra l/I was inserted after R. Drop it.
        return "R" + digits + rest

    t = re.sub(r"^R114", "R14", t)
    t = re.sub(r"^Rl0", "R10", t)
    t = re.sub(r"^Rl1", "R11", t)
    t = re.sub(r"^RI1", "R11", t)
    return t


def normalize_chinese_pattern_text(text: str) -> str:
    """Mainland Chinese crochet pattern cleanup before round extraction.

    Handles raw OCR like:
    Rg: 8 (6X.V)\n(7xV)\nRl0:\nRl1: 不加减x
    by moving the orphan (7XV) into R10 and repairing Rl0/Rl1/R2g.
    """
    text = unicodedata.normalize("NFKC", text)
    text = normalize_decimal_mm(text)
    text = text.replace("：", ":").replace("；", ":").replace(";", ":")
    text = text.replace("，", ",").replace("、", ",").replace("。", ".")
    text = normalize_decimal_mm(text)
    text = re.sub(r"([xvaftesl])\s*[.]\s*([xvaftesl])", r"\1,\2", text, flags=re.I)
    text = normalize_decimal_mm(text)
    text = re.sub(r"\bIOX\b", "10X", text, flags=re.I)
    text = re.sub(r"\bI0X\b", "10X", text, flags=re.I)
    text = re.sub(r"\bGX\b", "6X", text, flags=re.I)
    text = re.sub(r"\bSXV\b", "5XV", text, flags=re.I)

    raw_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    fixed = []
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        line = repair_ocr_round_token(line)
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
            nxt = repair_ocr_round_token(raw_lines[i + 1].strip())
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
    text = normalize_pattern_rounds(text)
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
        translated = translate_expression(str(r["Original"]), index, df, output_mode)
        output_col = "解讀" if output_mode in ["Traditional Chinese", "Simplified Chinese"] else "Interpretation"
        rows.append({
            "Round": r["Round"],
            "Original": r["Original"],
            output_col: translated,
            "Total stitches": r["Total stitches"],
        })
    return pd.DataFrame(rows)


# -----------------------------
# Visual overlay + readable line output
# -----------------------------
def get_output_column_name(output_mode: str) -> str:
    return "解讀" if output_mode in ["Traditional Chinese", "Simplified Chinese"] else "Interpretation"

def build_line_by_line_text(interpretation_df: pd.DataFrame, output_mode: str) -> str:
    if interpretation_df.empty:
        return ""
    output_col = get_output_column_name(output_mode)
    lines = []
    for _, row in interpretation_df.iterrows():
        round_label = str(row.get("Round", "")).strip()
        interp = str(row.get(output_col, "")).strip()
        total = str(row.get("Total stitches", "")).strip()
        if not round_label and not interp:
            continue
        suffix = ""
        if total:
            if output_mode == "Simplified Chinese":
                suffix = f"（共{total}针）"
            elif output_mode == "Traditional Chinese":
                suffix = f"（共{total}針）"
            elif output_mode == "Japanese":
                suffix = f"（合計{total}目）"
            else:
                suffix = f" [{total} sts]"
        lines.append(f"{round_label}: {interp}{suffix}".strip())
    return "\n".join(lines)

def _load_overlay_font(size: int):
    from PIL import ImageFont
    font_paths = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for fp in font_paths:
        try:
            return ImageFont.truetype(fp, size=size)
        except Exception:
            continue
    return ImageFont.load_default()

def _wrap_label(text: str, max_chars: int = 24) -> List[str]:
    text = str(text).strip()
    if len(text) <= max_chars:
        return [text]
    # Prefer breaking at punctuation/spaces, but keep it simple and deterministic.
    chunks = []
    current = ""
    for part in re.split(r"(,|，|、|\s+)", text):
        if not part:
            continue
        if len(current) + len(part) > max_chars and current:
            chunks.append(current.strip())
            current = part.strip()
        else:
            current += part
    if current.strip():
        chunks.append(current.strip())
    # Very long formula with no separators.
    final = []
    for c in chunks:
        while len(c) > max_chars:
            final.append(c[:max_chars])
            c = c[max_chars:]
        if c:
            final.append(c)
    return final[:3]


def _wrap_label_to_width(text: str, draw, font, max_width: float, max_lines: int = 3) -> List[str]:
    """Wrap overlay label text by rendered pixel width instead of character count."""
    text = str(text).strip()
    if not text:
        return []
    max_width = max(80, float(max_width))

    def text_width(value: str) -> float:
        bb = draw.textbbox((0, 0), value, font=font)
        return float(bb[2] - bb[0])

    if text_width(text) <= max_width:
        return [text]

    tokens = [token for token in re.split(r"(,|，|、|\s+)", text) if token]
    lines: List[str] = []
    current = ""
    for token in tokens:
        candidate = f"{current}{token}" if current else token.strip()
        if current and text_width(candidate.strip()) > max_width:
            lines.append(current.strip())
            current = token.strip()
        else:
            current = candidate
    if current.strip():
        lines.append(current.strip())

    final: List[str] = []
    for line in lines:
        if text_width(line) <= max_width:
            final.append(line)
            continue
        chunk = ""
        for ch in line:
            candidate = chunk + ch
            if chunk and text_width(candidate) > max_width:
                final.append(chunk)
                chunk = ch
            else:
                chunk = candidate
        if chunk:
            final.append(chunk)
    return final[:max_lines]

def _find_anchor_for_round(ocr_rows: pd.DataFrame, round_label: str) -> Optional[Dict[str, float]]:
    if ocr_rows is None or ocr_rows.empty:
        return None
    if not round_label:
        return None
    m = re.match(r"R(\d+)", str(round_label), flags=re.I)
    if not m:
        return None
    n = m.group(1)
    patterns = [
        rf"\bR\s*{n}\s*[:：;]",
        rf"\br\s*{n}\s*[:：;]",
    ]
    rows = ocr_rows.copy()
    rows["confidence"] = pd.to_numeric(rows.get("confidence", 0), errors="coerce").fillna(0)
    # First pass: exact round marker.
    for pat in patterns:
        hit = rows[rows["text"].astype(str).str.contains(pat, regex=True, case=False, na=False)]
        if not hit.empty:
            hit = hit.sort_values(["confidence"], ascending=False).iloc[0]
            return hit.to_dict()
    # Second pass: common OCR errors for R1/R9/R10/R11.
    if n == "1":
        hit = rows[rows["text"].astype(str).str.contains(r"\bR[lI]?\s*[:：;]", regex=True, case=False, na=False)]
        if not hit.empty:
            return hit.sort_values(["confidence"], ascending=False).iloc[0].to_dict()
    return None

def make_translation_overlay(image: Image.Image, ocr_rows: pd.DataFrame, interpretation_df: pd.DataFrame, output_mode: str) -> Optional[Image.Image]:
    """Draw compact translation labels near detected round rows on the original image.

    This is deliberately not a full Google Translate style overwrite. It keeps the
    original visible and places small labels near likely round anchors for debugging
    and readability.
    """
    if interpretation_df.empty or ocr_rows is None or ocr_rows.empty:
        return None
    from PIL import ImageDraw
    img = image.convert("RGBA")
    w, h = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_size = max(14, min(28, int(w / 45)))
    font = _load_overlay_font(font_size)
    output_col = get_output_column_name(output_mode)

    used_slots = []
    for _, row in interpretation_df.head(40).iterrows():
        round_label = str(row.get("Round", "")).strip()
        interp = str(row.get(output_col, "")).strip()
        if not round_label or not interp:
            continue
        anchor = _find_anchor_for_round(ocr_rows, round_label)
        if not anchor:
            continue
        min_x = float(anchor.get("min_x", anchor.get("global_x", 0)))
        max_x = float(anchor.get("max_x", min_x + 80))
        min_y = float(anchor.get("min_y", anchor.get("y", 0)))
        max_y = float(anchor.get("max_y", min_y + 20))
        label = f"{round_label}: {interp}"
        lines = _wrap_label(label, max_chars=28)

        # Measure text.
        bboxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
        tw = max(bb[2] - bb[0] for bb in bboxes) + 16
        th = sum(bb[3] - bb[1] for bb in bboxes) + 10 + (len(lines) - 1) * 4

        # Prefer right side of the detected text; if no room, place below/left.
        x = max_x + 8
        y = min_y - 2
        if x + tw > w - 4:
            x = max(4, min_x - tw - 8)
        if x < 4:
            x = max(4, min_x)
            y = max_y + 4
        if y + th > h - 4:
            y = max(4, h - th - 4)

        # Avoid stacking labels exactly on top of each other.
        for _ in range(8):
            rect = (x, y, x + tw, y + th)
            overlap = any(not (rect[2] < r[0] or rect[0] > r[2] or rect[3] < r[1] or rect[1] > r[3]) for r in used_slots)
            if not overlap:
                break
            y = min(h - th - 4, y + th + 4)
        used_slots.append((x, y, x + tw, y + th))

        # Draw anchor outline and label.
        draw.rectangle((min_x, min_y, max_x, max_y), outline=(255, 80, 80, 210), width=max(2, w // 700))
        draw.rounded_rectangle((x, y, x + tw, y + th), radius=8, fill=(255, 255, 245, 230), outline=(80, 80, 80, 170), width=1)
        cursor_y = y + 5
        for line, bb in zip(lines, bboxes):
            draw.text((x + 8, cursor_y), line, fill=(20, 20, 20, 255), font=font)
            cursor_y += (bb[3] - bb[1]) + 4

    return Image.alpha_composite(img, overlay).convert("RGB")



# -----------------------------
# Line translation mode
# -----------------------------
@profile_function("OCR text normalization: clean_single_ocr_line", "clean_single_ocr_line calls")
def clean_single_ocr_line(text: str) -> str:
    """Clean one OCR box/line without trying to rebuild sections or columns."""
    s = unicodedata.normalize("NFKC", str(text)).strip()
    if not s:
        return ""
    s = normalize_decimal_mm(s)
    # Keep this conservative. Do not invent missing separators such as XV -> X,V.
    s = s.replace("：", ":").replace("；", ":").replace(";", ":")
    s = s.replace("，", ",").replace("、", ",").replace("。", ".")
    s = normalize_decimal_mm(s)
    s = repair_ocr_round_token(s)
    # Common OCR repairs only when very safe.
    repairs = {
        "Rl:": "R1:", "RI:": "R1:", "Rg:": "R9:", "R2g:": "R29:",
        "Rl0:": "R10:", "RI0:": "R10:", "Rl1:": "R11:", "RI1:": "R11:",
        "R114:": "R14:", "IOX": "10X", "I0X": "10X", "GX": "6X", "SXV": "5XV",
        "S LST": "SLST", "SL ST": "SLST", "S L ST": "SLST", "IDEC": "1DEC", "ISc": "1SC",
    }
    for bad, good in repairs.items():
        s = s.replace(bad, good)
    # Safe OCR fixes in English patterns. 6cc is almost always 6ch in crochet; avoid changing ordinary words.
    s = re.sub(r"(?<=\d)\s*cc\b", "ch", s, flags=re.I)
    s = re.sub(r"\bsl\s*st\b", "slst", s, flags=re.I)
    s = re.sub(r"\bsl\s*st(s)?\b", "slst", s, flags=re.I)
    s = re.sub(r"\bR\s*(\d+)", r"R\1", s, flags=re.I)
    s = re.sub(r"\bR(\d+)\s*[.]", r"R\1:", s, flags=re.I)
    # Normalize punctuation between stitch symbols only if OCR already saw a dot/comma.
    s = re.sub(r"([xvatfeXVATFE])\s*[.]\s*([xvatfeXVATFE])", r"\1,\2", s)
    s = normalize_decimal_mm(s)
    return s.strip()



def translate_common_instruction_line(s: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str) -> Optional[str]:
    """Conservative translation for common non-round crochet instruction lines.

    This is not a general translator. It only handles high-frequency pattern
    phrases safely, while preserving the original when uncertain.
    """
    raw = unicodedata.normalize("NFKC", str(s)).strip()
    if not raw:
        return None

    # Normalise compact stitch counts inside ordinary sentences: 6sts, 8sc, 4ch.
    def counted(n: str, term: str) -> str:
        return translate_piece(f"{n}{term}", index, df, output_mode)

    # Start with 8sc in a Magic ring, slst (8)
    m = re.search(
        r"^Start\s+with\s+(\d+)\s*(sc|sts?|stitches?|ch|dc|hdc|tr)\s+in\s+a\s+Magic\s+ring\s*,?\s*(sl\s*st|slst)?\s*(?:\((\d+)\))?\s*$",
        raw,
        flags=re.I,
    )
    if m:
        n, term, join_term, total = m.groups()
        main = counted(n, "sc" if term.lower().startswith("st") else term)
        mr = lookup_term("mr", index, df, output_mode)
        join = lookup_term("slst", index, df, output_mode) if join_term else ""
        if output_mode == "Simplified Chinese":
            out = f"以{mr}起针，钩{main}"
            if join:
                out += f"，{join}"
            if total:
                out += f"（共{total}针）"
            return out
        if output_mode == "Traditional Chinese":
            out = f"以{mr}起針，鈎{main}"
            if join:
                out += f"，{join}"
            if total:
                out += f"（共{total}針）"
            return out
        if output_mode == "Japanese":
            out = f"{mr}で始め、{main}"
            if join:
                out += f"、{join}"
            if total:
                out += f"（合計{total}目）"
            return out
        out = f"Start with {main} in {mr}"
        if join:
            out += f", {join}"
        if total:
            out += f" ({total})"
        return out

    # Start from 4ch / Start with 6ch / Start with 6cc (OCR-safe)
    m = re.search(r"^Start\s+(?:from|with)\s+(\d+)\s*(ch|cc)\s*$", raw, flags=re.I)
    if m:
        n, term = m.groups()
        main = counted(n, "ch")
        if output_mode == "Simplified Chinese":
            return f"从{main}开始"
        if output_mode == "Traditional Chinese":
            return f"從{main}開始"
        if output_mode == "Japanese":
            return f"{main}から始める"
        return f"Start from {main}"

    # Pure explanatory sentence with embedded stitch count, e.g. "6sts in between".
    # Keep it conservative to avoid Argos-style nonsense.
    m = re.search(r"^(?:Place\s+the\s+eyes\s+on\s+the\s+center\s+of\s+the\s+sleeve,\s*)?(\d+)\s*sts?\s+in\s+between\.?$", raw, flags=re.I)
    if m:
        n = m.group(1)
        stitch_word = counted(n, "st")
        if output_mode == "Simplified Chinese":
            return f"将眼睛放在袖子中央，中间相隔{stitch_word}。" if raw.lower().startswith("place") else f"中间相隔{stitch_word}。"
        if output_mode == "Traditional Chinese":
            return f"將眼睛放在袖子中央，中間相隔{stitch_word}。" if raw.lower().startswith("place") else f"中間相隔{stitch_word}。"
        if output_mode == "Japanese":
            return f"目を袖の中央に付け、間を{stitch_word}空ける。" if raw.lower().startswith("place") else f"間を{stitch_word}空ける。"
        return raw

    # Simple sewing line.
    if re.fullmatch(r"Sew\s+the\s+mouth\.?", raw, flags=re.I):
        if output_mode == "Simplified Chinese":
            return "缝上嘴巴。"
        if output_mode == "Traditional Chinese":
            return "縫上嘴巴。"
        if output_mode == "Japanese":
            return "口を縫い付ける。"
        return raw

    return None

@profile_function("line-by-line translation: translate_ocr_line", "translate_ocr_line calls")
def translate_ocr_line(original: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str) -> str:
    """Translate one OCR text box. If uncertain, return the cleaned original.

    This deliberately behaves like a conservative Google-Translate-ish reader:
    translate recognisable crochet shorthand; keep unrecognised text intact.
    """
    s = clean_single_ocr_line(original)
    if not s:
        return ""

    # V24: avoid hard-coded full-sentence translations.
    # First try CSV term replacement inside the whole line; this lets CSV terms
    # such as turn / slst / magic ring / ch / sts translate wherever they appear.
    csv_replaced = replace_csv_terms_in_line(s, index, df, output_mode)

    # Section headers / ordinary structural labels.
    section_map = {
        "上半部分": {"Traditional Chinese": "上半部分", "Simplified Chinese": "上半部分", "English — US": "Upper section", "English — UK": "Upper section", "Japanese": "上半分"},
        "上半部份": {"Traditional Chinese": "上半部分", "Simplified Chinese": "上半部分", "English — US": "Upper section", "English — UK": "Upper section", "Japanese": "上半分"},
        "下半部分": {"Traditional Chinese": "下半部分", "Simplified Chinese": "下半部分", "English — US": "Lower section", "English — UK": "Lower section", "Japanese": "下半分"},
        "下半部份": {"Traditional Chinese": "下半部分", "Simplified Chinese": "下半部分", "English — US": "Lower section", "English — UK": "Lower section", "Japanese": "下半分"},
        "腳丫": {"Traditional Chinese": "腳丫", "Simplified Chinese": "脚丫", "English — US": "Feet", "English — UK": "Feet", "Japanese": "足"},
        "脚丫": {"Traditional Chinese": "腳丫", "Simplified Chinese": "脚丫", "English — US": "Feet", "English — UK": "Feet", "Japanese": "足"},
    }
    for key, outputs in section_map.items():
        if key in s:
            return outputs.get(output_mode, outputs.get("Traditional Chinese", key))

    # Round label plus expression: R1: 环6x / R3: 6(X,V) / Rnd 1: sc 6
    m = re.match(r"^(?:Rnd\s*)?R?\s*([lI]?[0-9gq]+(?:\s*[-–—~～〜－]\s*R?\d+)?)\s*[:：]\s*(.*)$", s, flags=re.I)
    if m:
        label_core, expr = m.groups()
        label = "R" + repair_ocr_round_token(label_core).replace(" ", "")
        label = re.sub(r"^RR", "R", label, flags=re.I)
        label = re.sub(r"[-–—~～〜－]", "-", label)
        expr = expr.strip()
        if not expr:
            return label
        translated = translate_expression(expr, index, df, output_mode)
        # If no useful change, keep original expression.
        return f"{label}: {translated}"

    # A line can be a raw crochet formula without R label.
    translated = translate_expression(s, index, df, output_mode)

    # V25: for ordinary instruction sentences, prefer CSV term replacement.
    # This avoids partial expression-parser output such as leaving 8sc / Magic ring
    # untranslated in "Start with 8sc in a Magic ring, slst (8)".
    if _looks_like_prose_line(s):
        if csv_replaced and (norm_text(csv_replaced) != norm_text(s) or (contains_chinese_stitch_count(s) and csv_replaced != s)):
            return csv_replaced
        return translated if translated else s

    # Prefer full pattern-expression translation when it clearly changed the line.
    if translated and norm_text(translated) != norm_text(s):
        return translated

    # Otherwise return CSV term replacement. Unknown ordinary language remains as-is.
    if csv_replaced and (norm_text(csv_replaced) != norm_text(s) or (contains_chinese_stitch_count(s) and csv_replaced != s)):
        return csv_replaced

    return translated if translated else s



def merge_ocr_boxes_into_visual_lines(ocr_rows: pd.DataFrame) -> pd.DataFrame:
    """Merge PaddleOCR text boxes that sit on the same visual line.

    PaddleOCR often returns English pattern rows as separate boxes:
        "Rnd 2:"   "6 inc around"   "(12)"
    If we translate box-by-box, the order becomes messy and the round label is
    detached from the instruction. This function groups boxes by vertical
    position, then merges nearby boxes left-to-right while avoiding large column
    gaps.
    """
    if ocr_rows is None or ocr_rows.empty:
        return pd.DataFrame()

    rows = ocr_rows.copy()
    for col in ["min_x", "max_x", "min_y", "max_y", "x", "y", "global_x", "confidence"]:
        if col in rows.columns:
            rows[col] = pd.to_numeric(rows[col], errors="coerce")

    if "min_y" not in rows.columns or "max_y" not in rows.columns:
        rows = rows.sort_values(["y", "global_x" if "global_x" in rows.columns else "x"]).reset_index(drop=True)
        return rows

    rows["_cy"] = (rows["min_y"].fillna(rows.get("y", 0)) + rows["max_y"].fillna(rows.get("y", 0))) / 2
    rows["_h"] = (rows["max_y"].fillna(rows.get("y", 0) + 20) - rows["min_y"].fillna(rows.get("y", 0))).abs()
    median_h = float(rows["_h"].replace(0, pd.NA).dropna().median() or 20)
    y_threshold = max(10.0, median_h * 0.65)

    rows = rows.sort_values(["_cy", "min_x"]).reset_index(drop=True)
    line_groups = []
    cur = []
    cur_cy = None
    for idx, row in rows.iterrows():
        cy = float(row.get("_cy", 0) or 0)
        if cur_cy is None or abs(cy - cur_cy) <= y_threshold:
            cur.append(idx)
            cur_cy = cy if cur_cy is None else (cur_cy * (len(cur) - 1) + cy) / len(cur)
        else:
            line_groups.append(cur)
            cur = [idx]
            cur_cy = cy
    if cur:
        line_groups.append(cur)

    canvas_width = float(max(rows["max_x"].max() if "max_x" in rows.columns else 0, 1.0))
    gap_threshold = max(180.0, canvas_width * 0.20)
    merged_records = []

    for group in line_groups:
        line = rows.loc[group].copy().sort_values("min_x")
        cluster = []
        last_max_x = None
        for _, r in line.iterrows():
            min_x = float(r.get("min_x", r.get("x", 0)) or 0)
            if cluster and last_max_x is not None and min_x - last_max_x > gap_threshold:
                merged_records.append(_merge_ocr_cluster(cluster))
                cluster = []
            cluster.append(r)
            last_max_x = float(r.get("max_x", r.get("x", min_x) + 80) or (min_x + 80))
        if cluster:
            merged_records.append(_merge_ocr_cluster(cluster))

    out = pd.DataFrame(merged_records)
    if out.empty:
        return rows.drop(columns=[c for c in ["_cy", "_h"] if c in rows.columns], errors="ignore")
    return out.sort_values(["min_y", "min_x"]).reset_index(drop=True)


def _merge_ocr_cluster(cluster: list) -> Dict[str, object]:
    texts = [str(r.get("text", "")).strip() for r in cluster if str(r.get("text", "")).strip()]
    # Tighten punctuation spacing after joining left-to-right OCR boxes.
    text = " ".join(texts)
    text = re.sub(r"\s+([:：,，;；)])", r"\1", text)
    text = re.sub(r"([(（])\s+", r"\1", text)
    text = re.sub(r"\b(Rnd|R)\s+(\d)", r"\1 \2", text, flags=re.I)
    confs = [float(r.get("confidence", 0) or 0) for r in cluster]
    min_x = min(float(r.get("min_x", r.get("x", 0)) or 0) for r in cluster)
    max_x = max(float(r.get("max_x", r.get("x", 0) + 80) or 80) for r in cluster)
    min_y = min(float(r.get("min_y", r.get("y", 0)) or 0) for r in cluster)
    max_y = max(float(r.get("max_y", r.get("y", 0) + 20) or 20) for r in cluster)
    return {
        "text": text,
        "confidence": sum(confs) / len(confs) if confs else 0,
        "x": (min_x + max_x) / 2,
        "global_x": (min_x + max_x) / 2,
        "y": (min_y + max_y) / 2,
        "min_x": min_x,
        "max_x": max_x,
        "min_y": min_y,
        "max_y": max_y,
        "source": "visual line merge",
    }

@profile_function("line-by-line translation: build_ocr_line_translations", "build_ocr_line_translations calls")
def build_ocr_line_translations(ocr_rows: pd.DataFrame, index: Dict[str, int], df: pd.DataFrame, output_mode: str) -> pd.DataFrame:
    if ocr_rows is None or ocr_rows.empty:
        return pd.DataFrame()
    # V28: merge visually aligned OCR boxes before translation.
    # This keeps rows like "Rnd 2:   6 inc around   (12)" together.
    rows = merge_ocr_boxes_into_visual_lines(ocr_rows)
    rows["confidence"] = pd.to_numeric(rows.get("confidence", 0), errors="coerce").fillna(0)
    # For line-translation mode, do NOT discard aggressively. Keep low-confidence rows visible.
    rows = rows.sort_values(["min_y", "min_x"]).reset_index(drop=True)
    profile_count("merged OCR lines", len(rows))
    out = []
    for _, r in rows.iterrows():
        original = str(r.get("text", "")).strip()
        if not original:
            continue
        profile_count("OCR lines processed")
        cleaned = clean_single_ocr_line(original)
        translated = translate_ocr_line(cleaned, index, df, output_mode)
        changed = norm_text(cleaned) != norm_text(translated)
        out.append({
            "Original": cleaned,
            "Translation": translated,
            "Confidence": round(float(r.get("confidence", 0)), 3),
            "Changed": "✓" if changed else "",
            "min_x": float(r.get("min_x", r.get("x", 0))),
            "max_x": float(r.get("max_x", r.get("x", 0) + 80)),
            "min_y": float(r.get("min_y", r.get("y", 0))),
            "max_y": float(r.get("max_y", r.get("y", 0) + 20)),
        })
    return pd.DataFrame(out)


@profile_function("line-by-line translation: build_readable_line_translation", "build_readable_line_translation calls")
def build_readable_line_translation(line_df: pd.DataFrame) -> str:
    if line_df is None or line_df.empty:
        return ""
    lines = []
    for _, row in line_df.iterrows():
        original = str(row.get("Original", "")).strip()
        translated = str(row.get("Translation", "")).strip()
        if not original and not translated:
            continue
        if norm_text(original) == norm_text(translated):
            lines.append(original)
        else:
            lines.append(f"{original}\n→ {translated}")
    return "\n\n".join(lines)



# -----------------------------
# Watermark / noise filtering
# -----------------------------
WATERMARK_KEYWORDS = [
    "HANDMADE", "handmade", "小红书", "小紅書", "小红书号", "小紅書號",
    "禁商用", "禁盗图", "禁盜圖", "禁止商用", "禁止盗图", "禁止盜圖",
    "转载请", "請標明", "请标明", "轉載請", "转载请", "转载", "轉載",
    "cookie_", "cookie", "ID:", "id:", "號:", "号:", "书号", "書號",
]

WATERMARK_TRAILING_PATTERNS = [
    r"[\.。·、,，\s]*小[红紅]書(?:號|号)?\s*[:：]?\s*[A-Za-z0-9_\-]*.*$",
    r"[\.。·、,，\s]*布丁\s*HANDMADE.*$",
    r"[\.。·、,，\s]*HANDMADE.*$",
    r"[\.。·、,，\s]*(?:禁商用|禁盗图|禁盜圖|禁止商用|禁止盗图|禁止盜圖).*$",
    r"[\.。·、,，\s]*(?:转载请|轉載請|转载请|轉載|转载).*$",
]


def strip_watermark_substrings(text: str) -> str:
    s = str(text or "").strip()
    for pat in WATERMARK_TRAILING_PATTERNS:
        s = re.sub(pat, "", s, flags=re.I)
    return s.strip(" .。·、,，;；")


def looks_like_section_header_text(text: str) -> bool:
    return detect_section_header(str(text or ""), "English — US") is not None


def looks_like_pattern_text(text: str) -> bool:
    """Protect real crochet content from watermark removal.

    Do not remove repeated R1/R2/6V/X/V/A lines. Repeated watermarks are only
    removed when they do *not* look like crochet notation, section headers, or
    instructions.
    """
    s = unicodedata.normalize("NFKC", str(text or "")).strip()
    if not s:
        return False
    if looks_like_section_header_text(s):
        return True
    patterns = [
        r"\b[Rr]\s*\d+\b",                         # R1 / R20
        r"\b[Rr]\s*\d+\s*[-~～]\s*\d+\b",          # R5-6 / R5~6
        r"\d+\s*[xXvVaAtTfFeE]\b",                 # 6V / 18x / 2T
        r"[xXvVaAtTfFeE]\s*[\.．,，、]\s*[xXvVaAtTfFeE]",  # X.V / T.v
        r"\d+\s*ch\b|\bch\s*\d+",                 # 6ch / ch6
        r"\b(?:MR|mr|sc|SC|dc|DC|hdc|HDC|tr|TR|sl\s*st|SLST|inc|INC|dec|DEC|blo|BLO|flo|FLO)\b",
        r"環起|环起|環|环|起針|起针|針|针|半針|半针|外半針|内半针|內半針|加針|加针|減針|减针|不加減|不加减|交叉|倒\d+",
    ]
    return any(re.search(pat, s, flags=re.I) for pat in patterns)


def is_watermark_like_text(text: str, repeated_count: int = 1) -> bool:
    s = unicodedata.normalize("NFKC", str(text or "")).strip()
    if not s:
        return True
    # Strong blacklist, but only remove if it is not also a real pattern line.
    if any(k.lower() in s.lower() for k in WATERMARK_KEYWORDS) and not looks_like_pattern_text(s):
        return True
    # Repeated text filter: safe version. Never remove crochet-looking content.
    if repeated_count >= 5 and not looks_like_pattern_text(s):
        return True
    # Very short decorative leftovers with no crochet meaning.
    if len(s) <= 2 and not looks_like_pattern_text(s):
        return True
    return False


def filter_noise_and_watermarks(ocr_rows: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Remove common watermark/noise rows without deleting real pattern rows.

    Also strips trailing watermark fragments from otherwise useful rows, e.g.
    R9: ... 小紅書號:7110260553
    """
    if ocr_rows is None or ocr_rows.empty:
        return pd.DataFrame(), pd.DataFrame()

    rows = ocr_rows.copy().reset_index(drop=True)
    rows["original_text_before_filter"] = rows["text"].astype(str)
    rows["text"] = rows["text"].astype(str).map(strip_watermark_substrings)

    norm_counts = rows["text"].map(lambda x: norm_text(x)).value_counts().to_dict()
    keep = []
    removed = []
    for _, r in rows.iterrows():
        txt = str(r.get("text", "")).strip()
        original_txt = str(r.get("original_text_before_filter", "")).strip()
        nkey = norm_text(txt)
        repeated = int(norm_counts.get(nkey, 0)) if nkey else 0
        reason = ""
        if original_txt and txt != original_txt and not txt:
            reason = "watermark substring only"
        elif is_watermark_like_text(txt, repeated_count=repeated):
            reason = f"watermark/noise; repeated={repeated}"
        if reason:
            rr = r.to_dict()
            rr["removed_reason"] = reason
            removed.append(rr)
        else:
            keep.append(r.to_dict())

    keep_df = pd.DataFrame(keep)
    removed_df = pd.DataFrame(removed)
    if not keep_df.empty and "original_text_before_filter" in keep_df.columns:
        # Keep this hidden unless debugging removed rows.
        pass
    return keep_df, removed_df


# -----------------------------
# Section detection / section-aware output
# -----------------------------
SECTION_TRANSLATIONS = {
    "上半部分": {"Traditional Chinese": "上半部分", "Simplified Chinese": "上半部分", "English — US": "Upper section", "English — UK": "Upper section", "Japanese": "上半分"},
    "上半部份": {"Traditional Chinese": "上半部分", "Simplified Chinese": "上半部分", "English — US": "Upper section", "English — UK": "Upper section", "Japanese": "上半分"},
    "下半部分": {"Traditional Chinese": "下半部分", "Simplified Chinese": "下半部分", "English — US": "Lower section", "English — UK": "Lower section", "Japanese": "下半分"},
    "下半部份": {"Traditional Chinese": "下半部分", "Simplified Chinese": "下半部分", "English — US": "Lower section", "English — UK": "Lower section", "Japanese": "下半分"},
    "腳丫": {"Traditional Chinese": "腳丫", "Simplified Chinese": "脚丫", "English — US": "Feet", "English — UK": "Feet", "Japanese": "足"},
    "脚丫": {"Traditional Chinese": "腳丫", "Simplified Chinese": "脚丫", "English — US": "Feet", "English — UK": "Feet", "Japanese": "足"},
    "腳Y": {"Traditional Chinese": "腳丫", "Simplified Chinese": "脚丫", "English — US": "Feet", "English — UK": "Feet", "Japanese": "足"},
    "脚Y": {"Traditional Chinese": "腳丫", "Simplified Chinese": "脚丫", "English — US": "Feet", "English — UK": "Feet", "Japanese": "足"},
    "頭": {"Traditional Chinese": "頭", "Simplified Chinese": "头", "English — US": "Head", "English — UK": "Head", "Japanese": "頭"},
    "头": {"Traditional Chinese": "頭", "Simplified Chinese": "头", "English — US": "Head", "English — UK": "Head", "Japanese": "頭"},
    "身體": {"Traditional Chinese": "身體", "Simplified Chinese": "身体", "English — US": "Body", "English — UK": "Body", "Japanese": "体"},
    "身体": {"Traditional Chinese": "身體", "Simplified Chinese": "身体", "English — US": "Body", "English — UK": "Body", "Japanese": "体"},
    "耳朵": {"Traditional Chinese": "耳朵", "Simplified Chinese": "耳朵", "English — US": "Ears", "English — UK": "Ears", "Japanese": "耳"},
    "尾巴": {"Traditional Chinese": "尾巴", "Simplified Chinese": "尾巴", "English — US": "Tail", "English — UK": "Tail", "Japanese": "しっぽ"},
    "手臂": {"Traditional Chinese": "手臂", "Simplified Chinese": "手臂", "English — US": "Arms", "English — UK": "Arms", "Japanese": "腕"},
    "腿": {"Traditional Chinese": "腿", "Simplified Chinese": "腿", "English — US": "Legs", "English — UK": "Legs", "Japanese": "脚"},
}


def _clean_section_candidate(text: str) -> str:
    s = unicodedata.normalize("NFKC", str(text or "")).strip()
    s = s.replace("（", "(").replace("）", ")")
    s = re.sub(r"^[\s\-~:：;；,，、.。()]+|[\s\-~:：;；,，、.。()]+$", "", s)
    s = re.sub(r"\s+", "", s)
    return s


def detect_section_header(original: str, output_mode: str) -> Optional[str]:
    """Return translated section title if this OCR line looks like a section header.

    Be conservative. A line containing 手 in a note like 靠近自己手半针 should NOT
    become a section. Short standalone labels such as （上半部分） or 脚丫: should.
    """
    raw = str(original or "").strip()
    s = _clean_section_candidate(raw)
    if not s:
        return None

    # Direct known headers. Allow titles plus a colon, but avoid long instruction notes.
    for key, outputs in SECTION_TRANSLATIONS.items():
        if s == key or s.startswith(key + ":") or s.startswith(key + "："):
            return outputs.get(output_mode, outputs.get("Traditional Chinese", key))
        if key in ["上半部分", "上半部份", "下半部分", "下半部份"] and key in s and len(s) <= 12:
            return outputs.get(output_mode, outputs.get("Traditional Chinese", key))

    # Common OCR: 脚丫 can appear as 脚Y / 腳Y and may include colon.
    if re.fullmatch(r"[腳脚][丫Yy]", s):
        return SECTION_TRANSLATIONS["腳丫"].get(output_mode, "腳丫")

    # Very short part headers only. Do not classify longer notes.
    short_part_map = {
        "耳": "Ears", "耳朵": "Ears", "尾": "Tail", "尾巴": "Tail",
        "花瓣": "Petals", "葉子": "Leaves", "叶子": "Leaves", "翅膀": "Wings",
    }
    if len(s) <= 4 and s in short_part_map:
        if output_mode == "Traditional Chinese":
            return {"叶子":"葉子"}.get(s, s)
        if output_mode == "Simplified Chinese":
            return {"葉子":"叶子"}.get(s, s)
        return short_part_map[s]

    return None


def extract_round_label_from_line(original: str) -> Optional[str]:
    """Extract round labels including ranges such as R10~15 / R10-15 / Rnd 3-4."""
    s = unicodedata.normalize("NFKC", str(original or "")).strip()
    s = s.replace("：", ":").replace("；", ":").replace(";", ":")
    # Support common range separators used in Chinese / Japanese / English patterns.
    sep = r"[-–—~～〜－]"
    # Accept both compact R labels and English "Rnd" labels.
    m = re.match(rf"^(?:Rnd\s*)?R?\s*([lI]?[0-9gq]+(?:\s*{sep}\s*R?\s*[0-9gq]+)?)\s*:", s, flags=re.I)
    if not m:
        return None
    label = "R" + repair_ocr_round_token(m.group(1)).replace(" ", "")
    label = re.sub(r"^RR", "R", label, flags=re.I)
    # Normalise all range separators for display and downstream parsing.
    label = re.sub(sep, "-", label)
    return label


def _line_to_section_item(row: pd.Series, assigned_by: str = "") -> Dict[str, object]:
    original = str(row.get("Original", "")).strip()
    translated = str(row.get("Translation", "")).strip()
    round_label = extract_round_label_from_line(original) or ""
    return {
        "Original": original,
        "Translation": translated or original,
        "Round": round_label,
        "Confidence": row.get("Confidence", ""),
        "Changed": row.get("Changed", ""),
        "x": float(row.get("min_x", 0) or 0),
        "y": float(row.get("min_y", 0) or 0),
        "assigned_by": assigned_by,
    }


def _round_number(label: str) -> Optional[int]:
    m = re.match(r"^R(\d+)", str(label or ""), flags=re.I)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _row_has_pattern_tokens(original: str) -> bool:
    s = unicodedata.normalize("NFKC", str(original or ""))
    return bool(
        extract_round_label_from_line(s)
        or re.search(r"\d+\s*[xXvVaAtTfFeE]", s)
        or re.search(r"[xXvVaAtTfFeE]\s*[.．,，]", s)
        or re.search(r"\d+\s*(?:ch|sc|dc|hdc|tr|inc|dec|slst|sts?)\b", s, flags=re.I)
        or re.search(r"\b(ch|mr|magic\s*ring|sc|dc|hdc|tr|inc|dec|blo|flo|slst|sl\s*st|sts?|stitch(?:es)?)\b", s, flags=re.I)
        or re.search(r"[環环]\s*\d+\s*[xX]", s)
    )


def _looks_like_instruction_continuation(original: str) -> bool:
    """Detect non-R instruction lines that belong to the current pattern block.

    Example: 雪絨花內半針扭花短針48 is an instruction under R16, not a new section title.
    """
    s = unicodedata.normalize("NFKC", str(original or "")).strip()
    if not s or extract_round_label_from_line(s):
        return False
    # Chinese stitch / loop / crochet instruction with a count usually continues the previous row.
    if re.search(r"[針针半外內内短長长中扭翻圈繞绕鈎钩加減减]", s) and re.search(r"\d+", s):
        return True
    # English-style instruction with a count, but no round label. Handles compact terms: 8sc, 6ch, slst (8).
    if re.search(r"\d+\s*(?:ch|sc|dc|hdc|tr|inc|dec|slst|sts?)\b", s, flags=re.I):
        return True
    if re.search(r"\b(?:start\s+with|start\s+from|magic\s+ring|slst|sl\s*st|blo|flo|turn|join|sew|place)\b", s, flags=re.I) and re.search(r"\d+|\b(?:sc|dc|hdc|tr|ch|inc|dec|slst|mr)\b", s, flags=re.I):
        return True
    return False


def _looks_like_block_title(original: str) -> bool:
    """Heuristic title detector. No fixed title dictionary.

    A title is a short non-round line that is near pattern rows. We do not need
    to know what 蛋糕主體 / 櫻桃 / 蠟燭 means; we only need to avoid treating it as
    a crochet instruction row.
    """
    s = unicodedata.normalize("NFKC", str(original or "")).strip()
    if not s:
        return False
    if extract_round_label_from_line(s):
        return False
    if _row_has_pattern_tokens(s):
        # e.g. 起83CH... is an instruction, not a title.
        return False
    if _looks_like_instruction_continuation(s):
        return False
    if len(s) > 28:
        return False
    # Chinese part names or short English headings/material labels, without hard-coding every title.
    if re.search(r"[\u4e00-\u9fff]", s):
        return True
    # English part headings tend to be short Title Case words: Body, Cover, Legs, Strap, Sleeve.
    if re.fullmatch(r"[A-Z][A-Za-z ]{1,24}", s) and len(s.split()) <= 4:
        return True
    # Material headings such as <white yarn> should stay with the upcoming section.
    if re.fullmatch(r"<[^>]{2,40}>", s):
        return True
    return False


def _cluster_rows_by_x(rows: pd.DataFrame) -> Dict[int, List[int]]:
    """Cluster rows into rough visual columns using x-start of pattern rows.

    This is intentionally simple. It helps with layouts where left and right
    columns contain separate parts but OCR reading order interleaves them.
    """
    if rows.empty:
        return {0: []}

    rows = rows.copy()
    canvas_width = float(max(rows["max_x"].max(), 1.0))
    pattern_indices = []
    xs = []
    for idx, row in rows.iterrows():
        original = str(row.get("Original", ""))
        if _row_has_pattern_tokens(original) or _looks_like_block_title(original):
            pattern_indices.append(idx)
            xs.append(float(row.get("min_x", 0) or 0))

    if not xs:
        return {0: list(rows.index)}

    points = sorted(xs)
    # A gap of roughly a fifth of the page usually separates columns.
    gap_threshold = max(170.0, canvas_width * 0.18)
    centers = []
    cur = [points[0]]
    for x in points[1:]:
        if x - cur[-1] > gap_threshold:
            centers.append(sum(cur) / len(cur))
            cur = [x]
        else:
            cur.append(x)
    centers.append(sum(cur) / len(cur))

    if len(centers) > 4:
        # Too many means decorative text polluted clustering. Collapse a little.
        merged = []
        for c in centers:
            if not merged or abs(c - merged[-1]) > gap_threshold:
                merged.append(c)
            else:
                merged[-1] = (merged[-1] + c) / 2
        centers = merged[:4]

    groups: Dict[int, List[int]] = {i: [] for i in range(len(centers))}
    for idx, row in rows.iterrows():
        original = str(row.get("Original", ""))
        if not (_row_has_pattern_tokens(original) or _looks_like_block_title(original)):
            # General noise/instruction goes to nearest column only if close; otherwise leave for group 0.
            pass
        x = float(row.get("min_x", 0) or 0)
        nearest = min(range(len(centers)), key=lambda i: abs(x - centers[i]))
        # If far from every column and not pattern-like, keep in first group as detected text.
        if abs(x - centers[nearest]) > max(260.0, gap_threshold * 1.2) and not _row_has_pattern_tokens(original):
            nearest = 0
        groups[nearest].append(idx)
    return groups


def _make_section_title_from_pending(pending_titles: List[Tuple[float, str]], default_title: str) -> str:
    if not pending_titles:
        return default_title
    # Use the closest preceding title. If it has bracket notes, keep it; user can judge.
    title = pending_titles[-1][1].strip()
    # Remove common punctuation around it.
    title = re.sub(r"^[\s:：()（）]+|[\s:：()（）]+$", "", title)
    return title or default_title


def _build_layout_blocks_without_headers(rows: pd.DataFrame, output_mode: str) -> List[Dict[str, object]]:
    """Fallback layout parser v1.

    When no explicit known section headers are detected, infer blocks from visual
    columns + round sequence. This avoids merging left-column and right-column
    parts into one section when titles are arbitrary, such as 蛋糕主體 / 櫻桃.
    """
    groups = _cluster_rows_by_x(rows)
    all_sections: List[Dict[str, object]] = []
    unsectioned_lines: List[Dict[str, object]] = []
    section_counter = 1

    # Process columns visually left-to-right.
    for group_id, idxs in sorted(groups.items(), key=lambda kv: float(rows.loc[kv[1], "min_x"].median()) if kv[1] else 0):
        group = rows.loc[idxs].copy().sort_values(["min_y", "min_x"]).reset_index(drop=True)
        current: Optional[Dict[str, object]] = None
        last_round_num: Optional[int] = None
        pending_titles: List[Tuple[float, str]] = []
        current_has_rounds = False

        for _, row in group.iterrows():
            original = str(row.get("Original", "")).strip()
            if not original:
                continue
            round_label = extract_round_label_from_line(original)
            round_num = _round_number(round_label or "")
            y = float(row.get("min_y", 0) or 0)

            if round_label:
                # Start a new block when a new R1 appears, or when numbering goes
                # backwards / repeats after the current block already has rounds.
                restart = False
                if current is None:
                    restart = True
                elif round_num == 1 and current_has_rounds:
                    restart = True
                elif round_num is not None and last_round_num is not None:
                    # R3 followed by another R3/R2 in the same visual column usually
                    # means another nearby part was interleaved, so start a new block.
                    if round_num <= last_round_num and current_has_rounds:
                        restart = True

                if restart:
                    if current and current.get("lines"):
                        all_sections.append(current)
                        section_counter += 1
                    title = _make_section_title_from_pending(pending_titles, f"Section {section_counter}")
                    current = {"title": title, "lines": [], "explicit": False, "x": float(row.get("min_x", 0) or 0), "y": y}
                    pending_titles = []
                    last_round_num = None
                    current_has_rounds = False

                if current is None:
                    current = {"title": f"Section {section_counter}", "lines": [], "explicit": False, "x": float(row.get("min_x", 0) or 0), "y": y}
                current["lines"].append(_line_to_section_item(row, assigned_by=f"layout/col{group_id}"))
                current_has_rounds = True
                if round_num is not None:
                    last_round_num = round_num
                continue

            # Non-round rows.
            if _looks_like_instruction_continuation(original) and current is not None:
                current["lines"].append(_line_to_section_item(row, assigned_by=f"instruction-cont/col{group_id}"))
                continue

            if _looks_like_block_title(original):
                # A title after a block has begun usually starts a new nearby part.
                # Close current so the next R1/R2 can become a clean new block.
                if current and current_has_rounds and current.get("lines"):
                    all_sections.append(current)
                    section_counter += 1
                    current = None
                    last_round_num = None
                    current_has_rounds = False
                pending_titles.append((y, original))
                # Keep only the closest few title candidates.
                pending_titles = pending_titles[-3:]
                continue

            if _row_has_pattern_tokens(original) or _looks_like_instruction_continuation(original):
                # Continuation of previous pattern line, e.g. x.Tv.3Fv... after R6.
                if current is None:
                    title = _make_section_title_from_pending(pending_titles, f"Section {section_counter}")
                    current = {"title": title, "lines": [], "explicit": False, "x": float(row.get("min_x", 0) or 0), "y": y}
                    pending_titles = []
                current["lines"].append(_line_to_section_item(row, assigned_by=f"layout-cont/col{group_id}"))
            else:
                # General non-pattern text: keep only before any sections as Detected text.
                if current is None and not all_sections:
                    unsectioned_lines.append(_line_to_section_item(row, assigned_by="non-pattern"))

        if current and current.get("lines"):
            all_sections.append(current)
            section_counter += 1

    # Sort final sections visually: top-to-bottom, then left-to-right, but keep unsectioned first.
    all_sections = sorted(all_sections, key=lambda sec: (float(sec.get("y", 0) or 0), float(sec.get("x", 0) or 0)))
    if unsectioned_lines:
        return [{"title": "Detected text", "lines": unsectioned_lines, "explicit": False}] + all_sections
    return all_sections or [{"title": "Detected text", "lines": [_line_to_section_item(r, assigned_by="fallback") for _, r in rows.iterrows()], "explicit": False}]



def merge_section_continuation_lines(sections: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Merge OCR-wrapped continuation lines back into the previous round row.

    Long rows are often split by OCR, e.g.
        R1 In a magic ring: 1sc, 2hdc, ...
        1hdc, 1dc, 2hdc, 2sc, ch1 (12)
        slst and fo, leave a long tail for sewing.

    The second/third lines do not start with R1, but they clearly continue the
    previous round. We merge only conservative continuation-looking rows:
    - no own round label
    - previous row has a round label
    - contains crochet tokens or starts with a formula-like token
    This avoids swallowing ordinary notes such as "At the end you should...".
    """
    if not sections:
        return sections

    def continuation_like(text: str) -> bool:
        t = unicodedata.normalize("NFKC", str(text or "")).strip()
        if not t or extract_round_label_from_line(t):
            return False
        if re.match(r"^[,，.;；)）]", t):
            return True
        if re.match(r"^\d+\s*(?:ch|sc|hdc|dc|tr|inc|dec|slst|sl\s*st|sts?|[XVAFTES])\b", t, flags=re.I):
            return True
        if re.match(r"^(?:slst|sl\s*st|fo|fasten\s+off|turn|join|ch|sc|hdc|dc|tr|inc|dec)\b", t, flags=re.I):
            return True
        # Formula fragments without a round prefix.
        if re.search(r"\d+\s*(?:ch|sc|hdc|dc|tr|inc|dec|slst|sl\s*st|sts?)\b", t, flags=re.I):
            return True
        if re.search(r"[()]|[XVAFTES]\s*[,.]", t, flags=re.I) and re.search(r"\d", t):
            return True
        return False

    for sec in sections:
        merged = []
        for line in sec.get("lines", []):
            original = str(line.get("Original", "")).strip()
            if (
                merged
                and not str(line.get("Round", "")).strip()
                and str(merged[-1].get("Round", "")).strip()
                and continuation_like(original)
            ):
                prev = merged[-1]
                prev["Original"] = (str(prev.get("Original", "")).rstrip() + " " + original).strip()
                prev["Translation"] = (str(prev.get("Translation", "")).rstrip() + " " + str(line.get("Translation", "")).strip()).strip()
                # Keep the lower confidence as a conservative signal.
                try:
                    prev["Confidence"] = round(min(float(prev.get("Confidence", 1)), float(line.get("Confidence", 1))), 3)
                except Exception:
                    pass
                if line.get("Changed"):
                    prev["Changed"] = "✓"
            else:
                merged.append(line)
        sec["lines"] = merged
    return sections

def build_section_blocks(line_df: pd.DataFrame, output_mode: str) -> List[Dict[str, object]]:
    """Group OCR line translations into human-readable pattern sections.

    V19 adds Layout Parser v1 for pages with arbitrary titles. Instead of
    relying on a title dictionary, it groups by visual columns and round-number
    sequences, then uses the nearest short non-pattern line above as the block
    title. This handles titles like 蛋糕主體 / 櫻桃 without knowing the words.
    """
    if line_df is None or line_df.empty:
        return []

    rows = line_df.copy().reset_index(drop=True)
    for c in ["min_x", "max_x", "min_y", "max_y"]:
        if c not in rows.columns:
            rows[c] = 0.0
        rows[c] = pd.to_numeric(rows[c], errors="coerce").fillna(0.0)
    rows["cx"] = (rows["min_x"] + rows["max_x"]) / 2
    rows["cy"] = (rows["min_y"] + rows["max_y"]) / 2

    header_rows: List[Dict[str, object]] = []
    for idx, row in rows.iterrows():
        title = detect_section_header(str(row.get("Original", "")), output_mode)
        if title:
            header_rows.append({
                "idx": idx,
                "title": title,
                "x": float(row["min_x"]),
                "cx": float(row["cx"]),
                "y": float(row["min_y"]),
                "cy": float(row["cy"]),
                "lines": [],
                "explicit": True,
            })

    # Position-based path: explicit section headers were found.
    if header_rows:
        header_rows = sorted(header_rows, key=lambda h: (h["y"], h["x"]))
        unsectioned = {"title": "Unsectioned text", "lines": [], "explicit": False, "x": 0, "y": 0}

        for idx, row in rows.iterrows():
            original = str(row.get("Original", "")).strip()
            if not original:
                continue
            if any(h["idx"] == idx for h in header_rows):
                continue

            cy = float(row["cy"])
            cx = float(row["cx"])
            min_x = float(row["min_x"])
            max_x = float(row["max_x"])
            width = max(1.0, max_x - min_x)

            is_roundish = bool(extract_round_label_from_line(original)) or bool(re.match(r"^\s*[Rr][0-9lIgq]+", original))
            has_crochet_tokens = bool(re.search(r"[0-9]+\s*[xXvVaAtTfFeE]|[xXvVaAtTfFeE]\s*[.．,，]", original))
            if is_roundish or has_crochet_tokens or width > 260:
                anchor_x = min_x
                anchor_reason = "start-x"
            else:
                anchor_x = cx
                anchor_reason = "center-x"

            candidates = []
            for h in header_rows:
                if h["cy"] <= cy + 35:
                    vertical_gap = max(0.0, cy - h["cy"])
                    horizontal_gap = abs(anchor_x - h["x"])
                    score = vertical_gap + horizontal_gap * 1.25
                    candidates.append((score, vertical_gap, horizontal_gap, h, anchor_reason))

            if candidates:
                candidates.sort(key=lambda x: (x[0], x[1], x[2]))
                chosen = candidates[0][3]
                chosen["lines"].append(_line_to_section_item(row, assigned_by=f"position/{candidates[0][4]}"))
            else:
                unsectioned["lines"].append(_line_to_section_item(row, assigned_by="above first header"))

        sections: List[Dict[str, object]] = []
        if unsectioned["lines"]:
            sections.append(unsectioned)
        for h in header_rows:
            if h["lines"]:
                sections.append({
                    "title": h["title"],
                    "lines": h["lines"],
                    "explicit": True,
                    "x": h["x"],
                    "y": h["y"],
                })
        return merge_section_continuation_lines(sections)

    # V19 fallback: no explicit known headers. Infer layout blocks.
    return merge_section_continuation_lines(_build_layout_blocks_without_headers(rows, output_mode))

def section_blocks_to_debug_df(sections: List[Dict[str, object]]) -> pd.DataFrame:
    rows = []
    for i, sec in enumerate(sections, start=1):
        lines = sec.get("lines", [])
        rows.append({
            "#": i,
            "Section": sec.get("title", f"Section {i}"),
            "Lines": len(lines),
            "Header x": round(float(sec.get("x", 0) or 0), 1) if sec.get("explicit") else "",
            "Header y": round(float(sec.get("y", 0) or 0), 1) if sec.get("explicit") else "",
            "Round labels": ", ".join([l.get("Round", "") for l in lines if l.get("Round", "")])[:120],
        })
    return pd.DataFrame(rows)


def build_section_readable_text(sections: List[Dict[str, object]]) -> str:
    chunks = []
    for sec in sections:
        title = str(sec.get("title", "Section")).strip()
        lines = sec.get("lines", [])
        if not lines:
            continue
        chunks.append(f"## {title}")
        for line in lines:
            original = str(line.get("Original", "")).strip()
            translated = str(line.get("Translation", "")).strip()
            if norm_text(original) == norm_text(translated):
                chunks.append(original)
            else:
                chunks.append(f"{original}\n→ {translated}")
        chunks.append("")
    return "\n".join(chunks).strip()




def build_section_export_text(sections: List[Dict[str, object]], clean_text: str = "", raw_text: str = "") -> str:
    """Plain-text export for users to copy/edit after OCR.

    Keeps both original and translated lines when they differ.
    """
    parts = [
        "Crochet OCR Translation Export",
        "Generated by Crochet OCR Prototype",
        "",
        "Note: OCR and translation may contain mistakes. Please check against the original pattern image.",
        "",
    ]
    readable = build_section_readable_text(sections) if sections else ""
    if readable:
        parts.append("=== Section translation ===")
        parts.append(readable)
        parts.append("")
    if clean_text.strip():
        parts.append("=== Cleaned OCR text ===")
        parts.append(clean_text.strip())
        parts.append("")
    if raw_text.strip():
        parts.append("=== Raw OCR text ===")
        parts.append(raw_text.strip())
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def build_pattern_export_text(interpretation_df: pd.DataFrame, clean_text: str = "", raw_text: str = "", output_mode: str = "Traditional Chinese") -> str:
    parts = [
        "Crochet OCR Pattern Export",
        "Generated by Crochet OCR Prototype",
        "",
        "Note: OCR and pattern interpretation may contain mistakes. Please check against the original pattern image.",
        "",
    ]
    line_text = build_line_by_line_text(interpretation_df, output_mode) if interpretation_df is not None and not interpretation_df.empty else ""
    if line_text:
        parts.append("=== Pattern interpretation ===")
        parts.append(line_text)
        parts.append("")
    if clean_text.strip():
        parts.append("=== Cleaned OCR text ===")
        parts.append(clean_text.strip())
        parts.append("")
    if raw_text.strip():
        parts.append("=== Raw OCR text ===")
        parts.append(raw_text.strip())
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def _rects_overlap(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _pad_rect(rect: Tuple[float, float, float, float], pad: float) -> Tuple[float, float, float, float]:
    return (rect[0] - pad, rect[1] - pad, rect[2] + pad, rect[3] + pad)


def _left_reading_margin_protected_slot(
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> Tuple[float, float, float, float]:
    """Protect the left reading anchor of the current OCR row."""
    row_width = max(1.0, float(max_x) - float(min_x))
    protected_width = min(row_width, max(30.0, min(80.0, row_width * 0.22)))
    return _pad_rect((min_x, min_y, min_x + protected_width, max_y), 2)


def _find_free_label_position(
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    tw: float,
    th: float,
    image_w: int,
    image_h: int,
    used_slots: List[Tuple[float, float, float, float]],
    protected_slots: Optional[List[Tuple[float, float, float, float]]] = None,
) -> Optional[Tuple[float, float]]:
    """Find a reading-order-safe label position that avoids source text."""
    protected_slots = protected_slots or []

    def safe_at(x: float, y: float) -> Optional[Tuple[float, float]]:
        x = max(4, min(float(x), image_w - tw - 4))
        y = max(4, min(float(y), image_h - th - 4))
        if y + 1 < min_y:
            return None
        rect = (x, y, x + tw, y + th)
        if not any(_rects_overlap(rect, r) for r in used_slots + protected_slots):
            return x, y
        return None

    # Same-row/right placement can often be rescued by sliding a little farther
    # right while preserving reading order and protected OCR regions.
    start_x = max_x + 6
    max_search_x = min(image_w - tw - 4, max(start_x, image_w * 0.72))
    for y in [min_y, min_y + th * 0.35]:
        x = start_x
        while x <= max_search_x:
            pos = safe_at(x, y)
            if pos is not None:
                return pos
            x += 10

    candidates = [
        (min_x - tw - 6, min_y),         # same-row left
        (min_x, max_y + 4),              # below
        (max_x + 6, max_y + 4),          # lower-right
        (min_x - tw - 6, max_y + 4),     # lower-left
    ]
    for x, y in candidates:
        pos = safe_at(x, y)
        if pos is not None:
            return pos
    return None


def _find_free_marker_position(
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    mw: float,
    mh: float,
    image_w: int,
    image_h: int,
    used_slots: List[Tuple[float, float, float, float]],
    protected_slots: Optional[List[Tuple[float, float, float, float]]] = None,
    marker_column_x: Optional[float] = None,
) -> Tuple[float, float, Tuple[float, float, float, float]]:
    """Place a small marker near its source box without covering OCR text."""
    protected_slots = protected_slots or []
    candidates = [
        (max_x + 4, min_y),              # right of source text
        (max_x + 4, max_y - mh),         # right, aligned to lower edge
        (min_x, max_y + 3),              # just below
        (max_x + 4, max_y + 3),          # lower-right
        (min_x - mw - 4, min_y),         # left, last same-row option
        (min_x - mw - 4, max_y + 3),     # lower-left
    ]
    for x, y in candidates:
        x = max(4, min(float(x), image_w - mw - 4))
        y = max(4, min(float(y), image_h - mh - 4))
        rect = (x, y, x + mw, y + mh)
        if not any(_rects_overlap(rect, r) for r in used_slots + protected_slots):
            return x, y, rect

    # Final fallback: preserve row association. In narrow crops, distant vertical
    # searching can make marker numbers appear beside the wrong OCR rows, which
    # is worse than marker crowding. Use a controlled marker column near the row.
    column_x = marker_column_x if marker_column_x is not None else max_x + 4
    x = max(4, min(float(column_x), image_w - mw - 4))
    y = max(4, min(float(min_y + ((max_y - min_y) - mh) / 2), image_h - mh - 4))
    row_band_top = max(4, min_y - max(4.0, mh * 0.35))
    row_band_bottom = min(image_h - mh - 4, max_y + max(4.0, mh * 0.35))
    for offset in [0, -mh * 0.35, mh * 0.35, -mh * 0.7, mh * 0.7]:
        yy = max(row_band_top, min(y + offset, row_band_bottom))
        rect = (x, yy, x + mw, yy + mh)
        if not any(_rects_overlap(rect, r) for r in protected_slots):
            return x, yy, rect
    return x, y, (x, y, x + mw, y + mh)


@profile_function("overlay label preparation", "make_line_translation_overlay calls")
def make_line_translation_overlay(
    image: Image.Image,
    line_df: pd.DataFrame,
    output_mode: str,
    max_labels: int = 120,
    max_full_label_chars: int = 42,
) -> Tuple[Optional[Image.Image], str, pd.DataFrame]:
    """Draw smart overlay labels for translated OCR visual lines.

    Short translations are drawn near their OCR boxes. Long or colliding labels are
    replaced by numbered markers, with the full text returned as a legend. This is
    designed for beta stability rather than beautiful automatic typesetting.
    """
    if line_df is None or line_df.empty:
        return None, "", pd.DataFrame()
    from PIL import ImageDraw

    img = image.convert("RGBA")
    w, h = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_size = max(16, min(30, int(w / 45)))
    font = _load_overlay_font(font_size)
    marker_font = _load_overlay_font(max(font_size, 18))

    source_slots: List[Tuple[float, float, float, float]] = []
    for _, source_row in line_df.iterrows():
        source_text = str(source_row.get("Original", "")).strip()
        if not source_text:
            continue
        sx1 = float(source_row.get("min_x", 0)); sx2 = float(source_row.get("max_x", sx1 + 80))
        sy1 = float(source_row.get("min_y", 0)); sy2 = float(source_row.get("max_y", sy1 + 20))
        sx1 = max(0, min(sx1, w - 1)); sx2 = max(0, min(sx2, w - 1))
        sy1 = max(0, min(sy1, h - 1)); sy2 = max(0, min(sy2, h - 1))
        source_slots.append(_pad_rect((sx1, sy1, sx2, sy2), 3))

    used_slots: List[Tuple[float, float, float, float]] = []
    legend_rows: List[Dict[str, object]] = []
    drawn_count = 0
    marker_no = 1
    marker_column_x = max(4.0, min(w - 34.0, w * 0.82))

    for row_no, (_, row) in enumerate(line_df.iterrows()):
        if drawn_count >= max_labels:
            break
        original = str(row.get("Original", "")).strip()
        translated = str(row.get("Translation", "")).strip()
        if not translated or norm_text(original) == norm_text(translated):
            continue

        min_x = float(row.get("min_x", 0)); max_x = float(row.get("max_x", min_x + 80))
        min_y = float(row.get("min_y", 0)); max_y = float(row.get("max_y", min_y + 20))
        min_x = max(0, min(min_x, w - 1)); max_x = max(0, min(max_x, w - 1))
        min_y = max(0, min(min_y, h - 1)); max_y = max(0, min(max_y, h - 1))
        current_row_marker_slot = _left_reading_margin_protected_slot(min_x, min_y, max_x, max_y)

        label = translated
        force_marker = len(label) > max_full_label_chars
        placed_full = False

        if not force_marker:
            protected_slots = source_slots[:row_no] + source_slots[row_no + 1:]
            if current_row_marker_slot is not None:
                protected_slots = protected_slots + [current_row_marker_slot]
            right_space = w - max_x - 12
            max_label_width = min(w - 8, max(180, min(int(w * 0.58), int(max(right_space, w * 0.38)))))
            lines = _wrap_label_to_width(label, draw, font, max_label_width)
            bboxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
            tw = max(bb[2] - bb[0] for bb in bboxes) + 14
            th = sum(bb[3] - bb[1] for bb in bboxes) + 10 + (len(lines)-1)*3
            pos = _find_free_label_position(min_x, min_y, max_x, max_y, tw, th, w, h, used_slots, protected_slots)
            if pos is not None:
                x, y = pos
                used_slots.append((x, y, x + tw, y + th))
                draw.rectangle((min_x, min_y, max_x, max_y), outline=(255, 80, 80, 185), width=max(1, w//900))
                draw.rounded_rectangle((x, y, x+tw, y+th), radius=7, fill=(255,255,245,232), outline=(60,60,60,150), width=1)
                cy = y + 5
                for line, bb in zip(lines, bboxes):
                    draw.text((x+7, cy), line, fill=(15,15,15,255), font=font)
                    cy += (bb[3]-bb[1]) + 3
                placed_full = True
                legend_rows.append({
                    "Marker": "",
                    "Original": original,
                    "Translation": translated,
                    "Overlay": "full label",
                    "Confidence": row.get("Confidence", ""),
                })

        if not placed_full:
            marker = f"[{marker_no}]"
            marker_no += 1
            mbb = draw.textbbox((0, 0), marker, font=marker_font)
            mw = mbb[2] - mbb[0] + 12
            mh = mbb[3] - mbb[1] + 8
            protected_slots = source_slots[:row_no] + source_slots[row_no + 1:]
            current_source_slot = _pad_rect((min_x, min_y, max_x, max_y), 2)
            if current_row_marker_slot is not None:
                protected_slots = protected_slots + [current_row_marker_slot]
            x, y, rect = _find_free_marker_position(
                min_x,
                min_y,
                max_x,
                max_y,
                mw,
                mh,
                w,
                h,
                used_slots,
                protected_slots + [current_source_slot],
                marker_column_x=marker_column_x,
            )
            used_slots.append(rect)
            draw.rectangle((min_x, min_y, max_x, max_y), outline=(255, 80, 80, 170), width=max(1, w//1000))
            draw.rounded_rectangle(rect, radius=6, fill=(255,255,245,240), outline=(40,40,40,180), width=1)
            draw.text((x + 6, y + 4), marker, fill=(15,15,15,255), font=marker_font)
            legend_rows.append({
                "Marker": marker,
                "Original": original,
                "Translation": translated,
                "Overlay": "numbered marker",
                "Confidence": row.get("Confidence", ""),
            })

        drawn_count += 1

    if drawn_count == 0:
        return None, "", pd.DataFrame()

    legend_df = pd.DataFrame(legend_rows)
    legend_lines = []
    for _, r in legend_df.iterrows():
        marker = str(r.get("Marker", "")).strip()
        original = str(r.get("Original", "")).strip()
        translated = str(r.get("Translation", "")).strip()
        prefix = f"{marker} " if marker else ""
        legend_lines.append(f"{prefix}{original} → {translated}".strip())
    legend_text = "\n".join(legend_lines)
    return Image.alpha_composite(img, overlay).convert("RGB"), legend_text, legend_df


def image_to_png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


@profile_function("line-by-line translation: build_overlay_export_text", "build_overlay_export_text calls")
def build_overlay_export_text(line_df: pd.DataFrame, legend_text: str = "", clean_text: str = "", raw_text: str = "") -> str:
    """User-facing TXT export: line-by-line translation only."""
    readable = build_readable_line_translation(line_df) if line_df is not None and not line_df.empty else ""
    return readable.strip() + "\n" if readable.strip() else ""


def _debug_cell(value: object) -> str:
    text = "" if value is None else str(value).strip()
    return text.replace("\n", " ")


def _match_target_from_row(row: pd.Series, output_mode: str) -> str:
    if output_mode == "English — US":
        return _debug_cell(row.get("US abb", "")) or _debug_cell(row.get("US", ""))
    if output_mode == "English — UK":
        return _debug_cell(row.get("UK abb", "")) or _debug_cell(row.get("UK", ""))
    if output_mode == "Japanese":
        return _debug_cell(row.get("日本語", ""))
    zh = _debug_cell(row.get("中文", ""))
    if output_mode == "Simplified Chinese" and zh:
        return to_simplified(zh)
    return zh or _debug_cell(row.get("US abb", "")) or _debug_cell(row.get("US", ""))


def _format_matched_terms(matches_df: Optional[pd.DataFrame], output_mode: str) -> str:
    if matches_df is None or matches_df.empty:
        return "No matched dictionary terms found."
    lines = []
    for _, row in matches_df.iterrows():
        detected = _debug_cell(row.get("Original detected", ""))
        target = _match_target_from_row(row, output_mode)
        category = _debug_cell(row.get("Category", ""))
        if detected and target:
            suffix = f" [{category}]" if category else ""
            lines.append(f"{detected} -> {target}{suffix}")
    return "\n".join(lines) if lines else "No matched dictionary terms found."


def _format_unmatched_terms(unmatched: Optional[List[str]]) -> str:
    if not unmatched:
        return "No unmatched candidates captured."
    return "\n".join(_debug_cell(term) for term in unmatched if _debug_cell(term))


def _format_csv_match_details(matches_df: Optional[pd.DataFrame]) -> str:
    if matches_df is None or matches_df.empty:
        return "No CSV match detail rows available."
    columns = [str(c) for c in matches_df.columns]
    lines = [" | ".join(columns)]
    for _, row in matches_df.iterrows():
        lines.append(" | ".join(_debug_cell(row.get(col, "")) for col in columns))
    return "\n".join(lines)


def _format_debug_timings(timings: Optional[Dict[str, object]]) -> str:
    if not timings:
        return "No timing data captured."
    ordered = [
        "Image load",
        "Crop extraction",
        "PaddleOCR inference",
        "OCR cleanup",
        "Translation processing",
        "Overlay generation",
        "Total runtime",
    ]
    lines = []
    for key in ordered:
        if key in timings:
            try:
                value = f"{float(timings.get(key, 0.0)):.3f} sec"
            except Exception:
                value = _debug_cell(timings.get(key, ""))
            lines.append(f"{key}: {value}")
    for key, value in timings.items():
        if key in ordered:
            continue
        try:
            display_value = f"{float(value):.3f} sec"
        except Exception:
            display_value = _debug_cell(value)
        lines.append(f"{key}: {display_value}")
    return "\n".join(lines) if lines else "No timing data captured."


def format_runtime_profile(runtime_profile: Optional[Dict[str, object]]) -> str:
    if not runtime_profile:
        return "No runtime profile captured."
    resize_label = str(runtime_profile.get("ocr_resize_test") or "").strip()
    heading = f"Runtime Profile (Resize: {resize_label})" if resize_label else "Runtime Profile"
    ordered = [
        ("image_loading", "Image loading"),
        ("image_preprocessing", "Image preprocessing"),
        ("ocr", "OCR"),
        ("ocr_cleanup", "OCR cleanup / normalization"),
        ("translation", "Translation"),
        ("overlay_generation", "Overlay generation"),
        ("png_encoding", "PNG encoding"),
        ("translation_txt_generation", "Translation TXT generation"),
        ("diagnostic_report_generation", "Diagnostic Report generation"),
        ("ui_rendering", "UI rendering"),
        ("total", "TOTAL runtime"),
    ]
    label_width = max(len(label) for _, label in ordered)
    lines = [heading, ""]
    for key, label in ordered:
        value = runtime_profile.get(key)
        if value is None:
            display_value = "N/A"
        else:
            try:
                display_value = f"{float(value):.2f} s"
            except Exception:
                display_value = _debug_cell(value)
        lines.append(f"{label.ljust(label_width)}  {display_value}")
    return "\n".join(lines)


def _box_diag_row(row: pd.Series) -> str:
    text = _debug_cell(row.get("text", ""))
    confidence = _debug_cell(row.get("confidence", ""))
    try:
        min_x = float(row.get("min_x", 0))
        min_y = float(row.get("min_y", 0))
        max_x = float(row.get("max_x", 0))
        max_y = float(row.get("max_y", 0))
    except Exception:
        min_x = min_y = max_x = max_y = 0.0
    width = max(0.0, max_x - min_x)
    height = max(0.0, max_y - min_y)
    area = width * height
    return (
        f"{text} | {confidence} | "
        f"{min_x:.1f},{min_y:.1f},{max_x:.1f},{max_y:.1f} | "
        f"w={width:.1f}, h={height:.1f}, area={area:.1f}"
    )


def _format_ocr_box_list(rows: Optional[pd.DataFrame], mode: str, limit: int = 20) -> str:
    if rows is None or rows.empty:
        return "No OCR boxes captured."
    work = rows.copy()
    for col in ["confidence", "min_x", "max_x", "min_y", "max_y"]:
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0)
    if "box_area" not in work.columns:
        work["box_area"] = (work.get("max_x", 0) - work.get("min_x", 0)).clip(lower=0) * (work.get("max_y", 0) - work.get("min_y", 0)).clip(lower=0)
    if mode == "confidence":
        work = work.sort_values("confidence", ascending=False)
    elif mode == "largest":
        work = work.sort_values("box_area", ascending=False)
    elif mode == "smallest":
        work = work.sort_values("box_area", ascending=True)
    lines = ["text | confidence | x1,y1,x2,y2 | dimensions"]
    for _, row in work.head(limit).iterrows():
        lines.append(_box_diag_row(row))
    return "\n".join(lines)


def _format_ocr_workload_diagnostics(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    lines = [
        f"Image width: {diagnostics.get('image_width', 'Not captured')}",
        f"Image height: {diagnostics.get('image_height', 'Not captured')}",
        f"Pixel count: {diagnostics.get('pixel_count', 'Not captured')}",
        f"Megapixels: {diagnostics.get('megapixels', 'Not captured')}",
        f"OCR boxes detected: {diagnostics.get('ocr_box_count', 'Not captured')}",
        f"OCR text lines: {diagnostics.get('ocr_text_line_count', 'Not captured')}",
        f"Overlay items: {diagnostics.get('overlay_item_count', 'Not captured')}",
        f"Boxes per MP: {diagnostics.get('boxes_per_megapixel', 'Not captured')}",
        f"PaddleOCR detect timing: {diagnostics.get('paddle_detect_timing', 'Not captured')}",
        f"PaddleOCR recognize timing: {diagnostics.get('paddle_recognize_timing', 'Not captured')}",
    ]
    return "\n".join(lines)


def _rc11a_value(value: object) -> object:
    if value is None or value == "":
        return "N/A"
    return value


def _rc11a_seconds(timings: Optional[Dict[str, object]], key: str) -> str:
    timings = timings or {}
    value = timings.get(key)
    if value is None or value == "":
        return "N/A"
    try:
        return f"{float(value):.3f} sec"
    except Exception:
        return _debug_cell(value) or "N/A"


def _rc11a_sum_seconds(timings: Optional[Dict[str, object]], keys: List[str]) -> str:
    timings = timings or {}
    total = 0.0
    found = False
    for key in keys:
        value = timings.get(key)
        if value is None or value == "":
            continue
        try:
            total += float(value)
            found = True
        except Exception:
            pass
    return f"{total:.3f} sec" if found else "N/A"


def _format_rc11a_performance_diagnostics(
    ocr_workload: Optional[Dict[str, object]],
    ocr_call: Optional[Dict[str, object]],
    timings: Optional[Dict[str, object]],
    area_mode: str = "",
) -> str:
    ocr_workload = ocr_workload or {}
    ocr_call = ocr_call or {}
    run_primary_input = ocr_call.get("run_primary_ocr_input")
    if isinstance(run_primary_input, dict):
        input_width = run_primary_input.get("width")
        input_height = run_primary_input.get("height")
        input_pixels = run_primary_input.get("pixels")
    else:
        input_width = ocr_workload.get("image_width")
        input_height = ocr_workload.get("image_height")
        input_pixels = ocr_workload.get("pixel_count")
    try:
        input_megapixels = round(float(input_pixels) / 1_000_000, 3)
    except Exception:
        input_megapixels = ocr_workload.get("megapixels")
    lines = [
        f"OCR input image width: {_rc11a_value(input_width)}",
        f"OCR input image height: {_rc11a_value(input_height)}",
        f"OCR input megapixels: {_rc11a_value(input_megapixels)}",
        f"OCR mode: {_rc11a_value(area_mode)}",
        f"OCR box count: {_rc11a_value(ocr_workload.get('ocr_box_count'))}",
        f"Image preprocess / preparation time: {_rc11a_sum_seconds(timings, ['Image load', 'Crop extraction'])}",
        f"Image load time: {_rc11a_seconds(timings, 'Image load')}",
        f"Crop extraction time: {_rc11a_seconds(timings, 'Crop extraction')}",
        f"PaddleOCR inference time: {_rc11a_seconds(timings, 'PaddleOCR inference')}",
        f"OCR cleanup / postprocess time: {_rc11a_seconds(timings, 'OCR cleanup')}",
        f"Translation time: {_rc11a_seconds(timings, 'Translation processing')}",
        f"Overlay generation time: {_rc11a_seconds(timings, 'Overlay generation')}",
        f"Total time: {_rc11a_seconds(timings, 'Total runtime')}",
    ]
    return "\n".join(lines)


def _format_size_info(value: object) -> str:
    if isinstance(value, dict):
        return f"{value.get('width')} x {value.get('height')} ({value.get('pixels')} px)"
    return _debug_cell(value) or "Not captured"


def _format_bytes(value: object) -> str:
    try:
        byte_count = int(value)
        return f"{byte_count} bytes ({byte_count / (1024 * 1024):.2f} MB)"
    except Exception:
        return _debug_cell(value) or "Not captured"


def _format_ocr_image_pipeline(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    lines = [
        f"Original uploaded image: {_format_size_info(diagnostics.get('original_uploaded_image'))}",
        f"Selected image: {_format_size_info(diagnostics.get('selected_image'))}",
        f"Working image: {_format_size_info(diagnostics.get('working_image'))}",
        f"Working image before downscale: {_format_size_info(diagnostics.get('working_image_before_downscale'))}",
        f"Image actually passed to PaddleOCR: {_format_size_info(diagnostics.get('image_actually_passed_to_paddleocr'))}",
        f"Image passed into run_primary_ocr(): {_format_size_info(diagnostics.get('run_primary_ocr_input'))}",
        f"Image passed into run_paddle_ocr_single(): {_format_size_info(diagnostics.get('run_paddle_ocr_single_input'))}",
        f"Temp PNG image: {_format_size_info(diagnostics.get('temp_png_image'))}",
        f"Temp PNG size: {_format_bytes(diagnostics.get('temp_png_size_bytes'))}",
        f"App-level resize before PaddleOCR: {diagnostics.get('app_level_resize_before_paddleocr', 'Not captured')}",
        f"Size after downscale: {_format_size_info(diagnostics.get('size_after_downscale'))}",
        f"Boxes scaled back for overlay: {diagnostics.get('boxes_scaled_back_for_overlay', 'Not captured')}",
        f"Original size before app preprocessing: {_format_size_info(diagnostics.get('preprocessing_original_size'))}",
        f"Size after app preprocessing: {_format_size_info(diagnostics.get('preprocessing_output_size'))}",
        f"Whole Pattern sends full image: {diagnostics.get('whole_pattern_sends_full_image', 'Not captured')}",
        f"Select Area sends cropped image: {diagnostics.get('select_area_sends_cropped_image', 'Not captured')}",
        f"PaddleOCR actual loaded image size: {diagnostics.get('paddle_actual_loaded_image_size', 'Not captured')}",
    ]
    return "\n".join(lines)


def _format_rc11b_downscale_diagnostics(
    downscale_diagnostics: Optional[Dict[str, object]],
    timings: Optional[Dict[str, object]],
    ocr_workload: Optional[Dict[str, object]],
) -> str:
    downscale_diagnostics = downscale_diagnostics or {}
    ocr_workload = ocr_workload or {}
    lines = [
        f"Downscale enabled: {downscale_diagnostics.get('downscale_enabled', 'N/A')}",
        f"Downscale applied: {downscale_diagnostics.get('downscale_applied', 'N/A')}",
        f"Requested max height: {downscale_diagnostics.get('requested_max_height', 'N/A')}",
        f"Original OCR input width: {downscale_diagnostics.get('original_ocr_input_width', 'N/A')}",
        f"Original OCR input height: {downscale_diagnostics.get('original_ocr_input_height', 'N/A')}",
        f"Original OCR input megapixels: {downscale_diagnostics.get('original_ocr_input_megapixels', 'N/A')}",
        f"Actual PaddleOCR image width: {downscale_diagnostics.get('actual_paddleocr_image_width', 'N/A')}",
        f"Actual PaddleOCR image height: {downscale_diagnostics.get('actual_paddleocr_image_height', 'N/A')}",
        f"Actual PaddleOCR megapixels: {downscale_diagnostics.get('actual_paddleocr_megapixels', 'N/A')}",
        f"Downscale ratio: {downscale_diagnostics.get('downscale_ratio', 'N/A')}",
        f"Coordinate scale_x: {downscale_diagnostics.get('coordinate_scale_x', 'N/A')}",
        f"Coordinate scale_y: {downscale_diagnostics.get('coordinate_scale_y', 'N/A')}",
        f"Boxes scaled back for overlay: {downscale_diagnostics.get('boxes_scaled_back_for_overlay', 'N/A')}",
        f"PaddleOCR inference time: {_rc11a_seconds(timings, 'PaddleOCR inference')}",
        f"OCR box count: {_rc11a_value(ocr_workload.get('ocr_box_count'))}",
        f"Total time: {_rc11a_seconds(timings, 'Total runtime')}",
        f"Downscale error: {downscale_diagnostics.get('downscale_error') or 'N/A'}",
    ]
    return "\n".join(lines)


def _profile_timing(profile: Optional[Dict[str, Dict[str, float]]], key: str) -> Optional[float]:
    if not isinstance(profile, dict):
        return None
    timings = profile.get("timings", {})
    if not isinstance(timings, dict):
        return None
    value = timings.get(key)
    try:
        return float(value)
    except Exception:
        return None


def _profile_count_value(profile: Optional[Dict[str, Dict[str, float]]], key: str) -> Optional[float]:
    if not isinstance(profile, dict):
        return None
    counts = profile.get("counts", {})
    if not isinstance(counts, dict):
        return None
    value = counts.get(key)
    try:
        return float(value)
    except Exception:
        return None


def _format_diag_seconds(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.3f} sec"
    except Exception:
        return "N/A"


def _format_diag_count(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    try:
        numeric = float(value)
        return str(int(numeric)) if numeric.is_integer() else str(round(numeric, 3))
    except Exception:
        return "N/A"


def build_rc11c_translation_diagnostics(
    translation_profile: Optional[Dict[str, Dict[str, float]]],
    timings: Optional[Dict[str, object]],
    ocr_rows: Optional[pd.DataFrame],
    line_df: Optional[pd.DataFrame],
    overlay_legend_df: Optional[pd.DataFrame],
) -> Dict[str, object]:
    parser_keys = [
        "line-by-line translation: build_ocr_line_translations",
        "line-by-line translation: translate_ocr_line",
        "OCR text normalization: clean_single_ocr_line",
        "translate_expression()",
        "translate_piece()",
        "expression parsing: split_expression_parts",
    ]
    csv_keys = [
        "term lookup: lookup_row",
        "term lookup: lookup_term",
        "alias lookup / CSV term list",
        "term matching: find_matches",
    ]
    regex_keys = [
        "CSV replacement loops",
    ]
    replacement_keys = [
        "CSV replacement loops",
        "line-by-line translation: build_overlay_export_text",
    ]
    overlay_keys = [
        "overlay label preparation",
        "line-by-line translation: build_readable_line_translation",
    ]

    def sum_keys(keys: List[str]) -> Optional[float]:
        values = [_profile_timing(translation_profile, key) for key in keys]
        found = [value for value in values if value is not None]
        return sum(found) if found else None

    timings_dict = timings or {}
    try:
        total_translation = float(timings_dict.get("Translation processing"))
    except Exception:
        total_translation = None

    lookup_attempts = _profile_count_value(translation_profile, "lookup_term calls")
    lookup_matches = (
        (_profile_count_value(translation_profile, "lookup_row fast hits") or 0)
        + (_profile_count_value(translation_profile, "lookup_row fallback hits") or 0)
    )
    if lookup_matches == 0 and lookup_attempts is None:
        lookup_matches_value: Optional[float] = None
    else:
        lookup_matches_value = lookup_matches

    return {
        "pattern_parser_time": sum_keys(parser_keys),
        "csv_lookup_time": sum_keys(csv_keys),
        "regex_processing_time": sum_keys(regex_keys),
        "translation_replacement_time": sum_keys(replacement_keys),
        "overlay_text_preparation_time": sum_keys(overlay_keys),
        "total_translation_stage_time": total_translation,
        "ocr_text_line_count": float(len(ocr_rows)) if ocr_rows is not None else None,
        "pattern_rows_detected": _profile_count_value(translation_profile, "merged OCR lines"),
        "dictionary_lookup_attempts": lookup_attempts,
        "dictionary_matches": lookup_matches_value,
        "regex_replacements": _profile_count_value(translation_profile, "regex replacements"),
        "regex_passes_estimated": _profile_count_value(translation_profile, "regex passes estimated"),
        "translated_output_rows": float(len(line_df)) if line_df is not None else None,
        "overlay_legend_entries": float(len(overlay_legend_df)) if overlay_legend_df is not None else None,
    }


def _format_rc11c_translation_diagnostics(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    lines = [
        f"Pattern parser time: {_format_diag_seconds(diagnostics.get('pattern_parser_time'))}",
        f"CSV lookup time: {_format_diag_seconds(diagnostics.get('csv_lookup_time'))}",
        f"Regex processing time: {_format_diag_seconds(diagnostics.get('regex_processing_time'))}",
        f"Translation replacement time: {_format_diag_seconds(diagnostics.get('translation_replacement_time'))}",
        f"Overlay text preparation time: {_format_diag_seconds(diagnostics.get('overlay_text_preparation_time'))}",
        f"Total translation stage time: {_format_diag_seconds(diagnostics.get('total_translation_stage_time'))}",
        "",
        f"OCR text line count: {_format_diag_count(diagnostics.get('ocr_text_line_count'))}",
        f"Pattern rows detected: {_format_diag_count(diagnostics.get('pattern_rows_detected'))}",
        f"Dictionary lookup attempts: {_format_diag_count(diagnostics.get('dictionary_lookup_attempts'))}",
        f"Dictionary matches: {_format_diag_count(diagnostics.get('dictionary_matches'))}",
        f"Regex replacements: {_format_diag_count(diagnostics.get('regex_replacements'))}",
        f"Regex passes estimated: {_format_diag_count(diagnostics.get('regex_passes_estimated'))}",
        f"Translated output rows: {_format_diag_count(diagnostics.get('translated_output_rows'))}",
        f"Overlay legend entries: {_format_diag_count(diagnostics.get('overlay_legend_entries'))}",
    ]
    return "\n".join(lines)


def _format_rc11c_translation_cost_summary(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    items = [
        ("Pattern parser", diagnostics.get("pattern_parser_time")),
        ("CSV lookup", diagnostics.get("csv_lookup_time")),
        ("Regex processing", diagnostics.get("regex_processing_time")),
        ("Translation replacement", diagnostics.get("translation_replacement_time")),
        ("Overlay text preparation", diagnostics.get("overlay_text_preparation_time")),
    ]
    parsed = []
    for label, value in items:
        try:
            if value is not None:
                parsed.append((label, float(value)))
        except Exception:
            pass
    if not parsed:
        return "N/A"
    parsed.sort(key=lambda item: item[1], reverse=True)
    return "\n".join(f"{label}: {seconds:.3f} sec" for label, seconds in parsed)


def build_rc11d_validation_diagnostics(
    translation_profile: Optional[Dict[str, Dict[str, float]]],
    rc11c_translation_diagnostics: Optional[Dict[str, object]],
) -> Dict[str, object]:
    counts = translation_profile.get("counts", {}) if isinstance(translation_profile, dict) else {}
    timings = translation_profile.get("timings", {}) if isinstance(translation_profile, dict) else {}
    function_counts = {}
    if isinstance(counts, dict):
        for key, value in counts.items():
            if str(key).endswith(" calls"):
                function_counts[str(key)] = value
    return {
        "translation_profile_timings": timings if isinstance(timings, dict) else {},
        "translation_profile_counts": counts if isinstance(counts, dict) else {},
        "function_counts": function_counts,
        "rc11c_translation_diagnostics": rc11c_translation_diagnostics or {},
    }


def _format_rc11d_timing_validation(_: Optional[Dict[str, object]]) -> str:
    rows = [
        (
            "Pattern parser time",
            "Cumulative / overlapping aggregate",
            "Sum of nested decorated function wall times: build_ocr_line_translations, translate_ocr_line, clean_single_ocr_line, translate_expression(), translate_piece(), split_expression_parts. These functions call each other, so their timings overlap and can exceed total translation stage time.",
        ),
        (
            "CSV lookup time",
            "Cumulative / overlapping aggregate",
            "Sum of lookup_row, lookup_term, alias term-list generation, and find_matches timings. lookup_term calls lookup_row, and find_matches performs lookups, so this bucket overlaps internally.",
        ),
        (
            "Regex processing time",
            "Cumulative / inclusive function timing",
            "Uses CSV replacement loops timing from replace_csv_terms_in_line. That function includes regex checks plus lookup and replacement work, so it is not regex-only exclusive time.",
        ),
        (
            "Translation replacement time",
            "Cumulative / overlapping aggregate",
            "Sum of CSV replacement loops and build_overlay_export_text. CSV replacement loops already include regex and lookup work, so this overlaps with CSV lookup and regex processing.",
        ),
        (
            "Overlay text preparation time",
            "Cumulative / separate-stage aggregate",
            "Sum of make_line_translation_overlay profile timing and build_readable_line_translation. make_line_translation_overlay is accounted under overlay generation, not under the top-level Translation processing timer.",
        ),
        (
            "Total translation stage time",
            "Top-level wall-clock timing",
            "Measured in the OCR success block as Translation processing. It covers build_ocr_line_translations, find_matches/readable translation, and build_overlay_export_text, but not every nested/profiled bucket listed above and not overlay generation.",
        ),
    ]
    lines = []
    for name, timing_type, method in rows:
        lines.append(f"{name}:")
        lines.append(f"Type: {timing_type}")
        lines.append(f"Calculation method: {method}")
        lines.append("")
    return "\n".join(lines).strip()


def _format_rc11d_function_call_diagnostics(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    function_counts = diagnostics.get("function_counts", {})
    if not isinstance(function_counts, dict) or not function_counts:
        return "N/A"
    display_names = {
        "find_matches calls": "find_matches()",
        "split_expression_parts calls": "split_expression_parts()",
        "translate_piece calls": "translate_piece()",
        "translate_expression calls": "translate_expression()",
        "clean_single_ocr_line calls": "clean_single_ocr_line()",
        "translate_ocr_line calls": "translate_ocr_line()",
        "build_ocr_line_translations calls": "build_ocr_line_translations()",
        "build_readable_line_translation calls": "build_readable_line_translation()",
        "make_line_translation_overlay calls": "make_line_translation_overlay()",
        "build_overlay_export_text calls": "build_overlay_export_text()",
        "lookup_row calls": "lookup_row()",
        "lookup_term calls": "lookup_term()",
        "get_all_csv_terms calls": "get_all_csv_terms()",
        "replace_csv_terms_in_line calls": "replace_csv_terms_in_line()",
    }
    lines = []
    for key in sorted(function_counts):
        label = display_names.get(key, str(key).replace(" calls", "()"))
        lines.append(f"{label}: {_format_diag_count(function_counts.get(key))}")
    return "\n".join(lines)


def _format_rc11d_lookup_validation(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    counts = diagnostics.get("translation_profile_counts", {})
    if not isinstance(counts, dict):
        counts = {}
    lines = [
        f"Lookup count value: {_format_diag_count(counts.get('lookup_term calls'))}",
        "Lookup count source: profile_count('lookup_term calls') inside lookup_term()",
        "Actual or estimated: Actual runtime call count for lookup_term()",
        f"lookup_row() actual calls: {_format_diag_count(counts.get('lookup_row calls'))}",
        f"lookup_row() fast hits: {_format_diag_count(counts.get('lookup_row fast hits'))}",
        f"lookup_row() fallback dictionary checks: {_format_diag_count(counts.get('lookup_row fallback dictionary checks'))}",
        f"lookup_row() fallback hits: {_format_diag_count(counts.get('lookup_row fallback hits'))}",
        "Dictionary matches source: lookup_row fast hits + fallback hits",
        "Dictionary matches actual or estimated: Actual counted successful lookup_row paths",
    ]
    return "\n".join(lines)


def _format_rc11d_regex_validation(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    counts = diagnostics.get("translation_profile_counts", {})
    if not isinstance(counts, dict):
        counts = {}
    lines = [
        f"Regex count source: {_format_diag_count(counts.get('regex passes estimated'))}",
        "Actual or estimated: Estimated",
        "Calculation method: The code increments profile_count('regex passes estimated') before selected regex checks/substitution sites and loop branches in replace_csv_terms_in_line(). It is not an instrumented count of actual regex engine executions or replacements.",
        f"Regex replacements: {_format_diag_count(counts.get('regex replacements'))}",
        "Regex replacements source: No active replacement counter was found; value may be N/A unless a future build instruments actual substitutions.",
    ]
    return "\n".join(lines)


def _format_rc11d_top_function_calls(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    function_counts = diagnostics.get("function_counts", {})
    if not isinstance(function_counts, dict) or not function_counts:
        return "N/A"
    parsed = []
    for key, value in function_counts.items():
        try:
            parsed.append((str(key).replace(" calls", "()"), float(value)))
        except Exception:
            pass
    parsed.sort(key=lambda item: item[1], reverse=True)
    return "\n".join(f"{name}: {_format_diag_count(count)}" for name, count in parsed)


def build_rc11e_normalization_diagnostics(
    translation_profile: Optional[Dict[str, Dict[str, float]]],
    df: Optional[pd.DataFrame],
) -> Dict[str, object]:
    counts = translation_profile.get("counts", {}) if isinstance(translation_profile, dict) else {}
    if not isinstance(counts, dict):
        counts = {}
    norm_callers = {}
    for key, value in counts.items():
        key_text = str(key)
        if key_text.startswith("norm_text caller: "):
            caller = key_text.replace("norm_text caller: ", "", 1)
            norm_callers[caller] = value
    get_all_calls = counts.get("get_all_csv_terms calls")
    generated_terms = counts.get("protected terms generated")
    try:
        avg_terms = float(generated_terms) / float(get_all_calls) if get_all_calls else None
    except Exception:
        avg_terms = None
    return {
        "norm_text_total_calls": counts.get("norm_text calls"),
        "norm_text_callers": norm_callers,
        "lookup_term_calls": counts.get("lookup_term calls"),
        "lookup_row_calls": counts.get("lookup_row calls"),
        "lookup_row_norm_text_calls": norm_callers.get("lookup_row"),
        "lookup_term_norm_text_calls": norm_callers.get("lookup_term"),
        "csv_rows_loaded": float(len(df)) if df is not None else None,
        "total_searchable_terms_generated": generated_terms,
        "get_all_csv_terms_call_count": get_all_calls,
        "average_terms_per_call": avg_terms,
    }


def _format_rc11e_normalization_diagnostics(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    callers = diagnostics.get("norm_text_callers", {})
    lines = [
        f"Total norm_text() calls: {_format_diag_count(diagnostics.get('norm_text_total_calls'))}",
        "Caller breakdown:",
    ]
    if isinstance(callers, dict) and callers:
        for caller in sorted(callers):
            lines.append(f"{caller}() -> norm_text() calls: {_format_diag_count(callers.get(caller))}")
    else:
        lines.append("N/A")
    return "\n".join(lines)


def _format_rc11e_top_normalization_callers(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    callers = diagnostics.get("norm_text_callers", {})
    if not isinstance(callers, dict) or not callers:
        return "N/A"
    parsed = []
    for caller, value in callers.items():
        try:
            parsed.append((str(caller), float(value)))
        except Exception:
            pass
    parsed.sort(key=lambda item: item[1], reverse=True)
    return "\n".join(f"{caller}(): {_format_diag_count(count)}" for caller, count in parsed)


def _format_rc11e_lookup_chain_diagnostics(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    lines = [
        f"lookup_term() calls: {_format_diag_count(diagnostics.get('lookup_term_calls'))}",
        f"lookup_row() calls: {_format_diag_count(diagnostics.get('lookup_row_calls'))}",
        f"lookup_term() -> norm_text() calls: {_format_diag_count(diagnostics.get('lookup_term_norm_text_calls'))}",
        f"lookup_row() -> norm_text() calls: {_format_diag_count(diagnostics.get('lookup_row_norm_text_calls'))}",
        "lookup_term() -> lookup_row(): lookup_term calls lookup_row once per invocation in the current code path.",
        "Counts are actual runtime counters from profile_count during the translation run.",
    ]
    return "\n".join(lines)


def _format_rc11e_csv_term_diagnostics(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    lines = [
        f"CSV rows loaded: {_format_diag_count(diagnostics.get('csv_rows_loaded'))}",
        f"Total searchable terms generated: {_format_diag_count(diagnostics.get('total_searchable_terms_generated'))}",
        f"get_all_csv_terms() call count: {_format_diag_count(diagnostics.get('get_all_csv_terms_call_count'))}",
        f"Average terms per call: {_format_diag_count(diagnostics.get('average_terms_per_call'))}",
        "Generation source: profile_count('protected terms generated') inside get_all_csv_terms().",
        "Repeated generation check: if get_all_csv_terms() call count is greater than 1, searchable terms were regenerated multiple times during this OCR run.",
    ]
    return "\n".join(lines)


def build_rc11f_cache_diagnostics(
    translation_profile: Optional[Dict[str, Dict[str, float]]],
    timings: Optional[Dict[str, object]],
    translation_output: str,
) -> Dict[str, object]:
    counts = translation_profile.get("counts", {}) if isinstance(translation_profile, dict) else {}
    if not isinstance(counts, dict):
        counts = {}
    stats = dict(CSV_TERM_CACHE_STATS)
    return {
        "cache_enabled": "Yes",
        "cache_key": stats.get("last_key") or "N/A",
        "cache_hits": stats.get("hits"),
        "cache_misses": stats.get("misses"),
        "generation_count": stats.get("generation_count"),
        "served_from_cache_count": stats.get("served_from_cache_count"),
        "searchable_terms_returned": stats.get("last_terms_returned"),
        "norm_text_total_calls": counts.get("norm_text calls"),
        "lookup_term_calls": counts.get("lookup_term calls"),
        "lookup_row_calls": counts.get("lookup_row calls"),
        "translation_processing_time": (timings or {}).get("Translation processing"),
        "total_runtime": (timings or {}).get("Total runtime"),
        "translation_output_hash": hashlib.sha256(str(translation_output or "").encode("utf-8")).hexdigest(),
        "cache_error": stats.get("last_error") or "N/A",
    }


def _format_rc11f_cache_diagnostics(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    lines = [
        f"CSV term cache enabled: {diagnostics.get('cache_enabled', 'N/A')}",
        f"CSV term cache key: {diagnostics.get('cache_key', 'N/A')}",
        f"CSV term cache hits: {_format_diag_count(diagnostics.get('cache_hits'))}",
        f"CSV term cache misses: {_format_diag_count(diagnostics.get('cache_misses'))}",
        f"get_all_csv_terms() actual generation count: {_format_diag_count(diagnostics.get('generation_count'))}",
        f"get_all_csv_terms() served from cache count: {_format_diag_count(diagnostics.get('served_from_cache_count'))}",
        f"Searchable terms returned: {_format_diag_count(diagnostics.get('searchable_terms_returned'))}",
        f"norm_text() total calls: {_format_diag_count(diagnostics.get('norm_text_total_calls'))}",
        f"lookup_term() calls: {_format_diag_count(diagnostics.get('lookup_term_calls'))}",
        f"lookup_row() calls: {_format_diag_count(diagnostics.get('lookup_row_calls'))}",
        f"Translation processing time: {_format_diag_seconds(diagnostics.get('translation_processing_time'))}",
        f"Total runtime: {_format_diag_seconds(diagnostics.get('total_runtime'))}",
        f"Translation output hash: {diagnostics.get('translation_output_hash', 'N/A')}",
        f"Cache error: {diagnostics.get('cache_error', 'N/A')}",
    ]
    return "\n".join(lines)


def build_rc11g_lookup_index_diagnostics(
    translation_profile: Optional[Dict[str, Dict[str, float]]],
    timings: Optional[Dict[str, object]],
    translation_output: str,
) -> Dict[str, object]:
    counts = translation_profile.get("counts", {}) if isinstance(translation_profile, dict) else {}
    if not isinstance(counts, dict):
        counts = {}
    stats = dict(NORMALIZED_LOOKUP_INDEX_STATS)
    return {
        "lookup_index_enabled": stats.get("enabled", "Yes"),
        "lookup_index_key": stats.get("last_key") or "N/A",
        "lookup_index_build_count": stats.get("build_count"),
        "lookup_index_cache_hits": stats.get("cache_hits"),
        "lookup_index_cache_misses": stats.get("cache_misses"),
        "lookup_index_size": stats.get("index_size"),
        "duplicate_normalized_keys": stats.get("duplicate_keys"),
        "indexed_lookup_attempts": stats.get("indexed_lookup_attempts"),
        "indexed_lookup_hits": stats.get("indexed_lookup_hits"),
        "indexed_lookup_misses": stats.get("indexed_lookup_misses"),
        "fallback_lookup_attempts": stats.get("fallback_lookup_attempts"),
        "fallback_lookup_hits": stats.get("fallback_lookup_hits"),
        "fallback_lookup_misses": stats.get("fallback_lookup_misses"),
        "lookup_term_calls": counts.get("lookup_term calls"),
        "lookup_row_calls": counts.get("lookup_row calls"),
        "norm_text_total_calls": counts.get("norm_text calls"),
        "translation_processing_time": (timings or {}).get("Translation processing"),
        "total_runtime": (timings or {}).get("Total runtime"),
        "translation_output_hash": hashlib.sha256(str(translation_output or "").encode("utf-8")).hexdigest(),
        "index_error": stats.get("index_error") or "N/A",
    }


def _format_rc11g_lookup_index_diagnostics(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    lines = [
        f"Lookup index enabled: {diagnostics.get('lookup_index_enabled', 'N/A')}",
        f"Lookup index key: {diagnostics.get('lookup_index_key', 'N/A')}",
        f"Lookup index build count: {_format_diag_count(diagnostics.get('lookup_index_build_count'))}",
        f"Lookup index cache hits: {_format_diag_count(diagnostics.get('lookup_index_cache_hits'))}",
        f"Lookup index cache misses: {_format_diag_count(diagnostics.get('lookup_index_cache_misses'))}",
        f"Lookup index size: {_format_diag_count(diagnostics.get('lookup_index_size'))}",
        f"Duplicate normalized keys: {_format_diag_count(diagnostics.get('duplicate_normalized_keys'))}",
        f"Indexed lookup attempts: {_format_diag_count(diagnostics.get('indexed_lookup_attempts'))}",
        f"Indexed lookup hits: {_format_diag_count(diagnostics.get('indexed_lookup_hits'))}",
        f"Indexed lookup misses: {_format_diag_count(diagnostics.get('indexed_lookup_misses'))}",
        f"Fallback lookup attempts: {_format_diag_count(diagnostics.get('fallback_lookup_attempts'))}",
        f"Fallback lookup hits: {_format_diag_count(diagnostics.get('fallback_lookup_hits'))}",
        f"Fallback lookup misses: {_format_diag_count(diagnostics.get('fallback_lookup_misses'))}",
        f"lookup_term() calls: {_format_diag_count(diagnostics.get('lookup_term_calls'))}",
        f"lookup_row() calls: {_format_diag_count(diagnostics.get('lookup_row_calls'))}",
        f"norm_text() total calls: {_format_diag_count(diagnostics.get('norm_text_total_calls'))}",
        f"Translation processing time: {_format_diag_seconds(diagnostics.get('translation_processing_time'))}",
        f"Total runtime: {_format_diag_seconds(diagnostics.get('total_runtime'))}",
        f"Translation output hash: {diagnostics.get('translation_output_hash', 'N/A')}",
        f"Index error: {diagnostics.get('index_error', 'N/A')}",
    ]
    return "\n".join(lines)


def _format_ocr_model_diagnostics(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    lines = [
        f"OCR backend: {diagnostics.get('ocr_backend', 'Not captured')}",
        f"Language model: {diagnostics.get('ocr_language_model', 'Not captured')}",
        f"OCR reader class: {diagnostics.get('ocr_reader_class', 'Not captured')}",
        f"Detector model: {diagnostics.get('detector_model', 'Not captured')}",
        f"Recognizer model: {diagnostics.get('recognizer_model', 'Not captured')}",
    ]
    return "\n".join(lines)


def _format_ocr_invocation_counts(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    lines = [
        f"run_primary_ocr calls: {diagnostics.get('run_primary_ocr_calls', 'Not captured')}",
        f"run_paddle_ocr_single calls: {diagnostics.get('run_paddle_ocr_single_calls', 'Not captured')}",
    ]
    return "\n".join(lines)


def _format_ocr_call_trace(trace: Optional[List[str]]) -> str:
    if not trace:
        return "No OCR call trace captured."
    return "\n".join(_debug_cell(item) for item in trace)


def _format_event_log(events: Optional[List[Dict[str, object]]]) -> str:
    if not events:
        return "No diagnostic events captured."
    interesting_events = []
    for event in events:
        event_name = str(event.get("event", ""))
        if any(token in event_name for token in ["image", "cropper", "Run OCR", "Pending OCR"]):
            interesting_events.append(event)
    if not interesting_events:
        interesting_events = events
    lines = []
    for event in interesting_events[-100:]:
        details = [
            f"{key}={_debug_cell(value)}"
            for key, value in event.items()
            if key not in {"time", "event"}
        ]
        suffix = f" | {'; '.join(details)}" if details else ""
        lines.append(f"{event.get('time', '')} | {event.get('event', '')}{suffix}")
    return "\n".join(lines)


def _format_session_diagnostics(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    lines = [
        f"Total session_state keys: {diagnostics.get('total_session_state_keys', 'Not captured')}",
        f"Cropper-related key count: {diagnostics.get('cropper_related_keys', 'Not captured')}",
        f"Slider-related key count: {diagnostics.get('slider_related_keys', 'Not captured')}",
        f"Image signature history length: {diagnostics.get('image_signature_history_length', 'Not captured')}",
    ]
    return "\n".join(lines)


def _format_button_ocr_diagnostics(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    lines = [
        f"Run button click count: {diagnostics.get('run_button_click_count', 'Not captured')}",
        f"Reruns between click and OCR block: {diagnostics.get('reruns_between_click_and_ocr_block', 'Not captured')}",
        f"pending_ocr_run status: {diagnostics.get('pending_ocr_run', 'Not captured')}",
        f"latest_crop_box status: {diagnostics.get('latest_crop_box', 'Not captured')}",
    ]
    return "\n".join(lines)


def _format_ocr_execution_diagnostics(diagnostics: Optional[Dict[str, object]]) -> str:
    diagnostics = diagnostics or {}
    lines = [
        f"OCR started at: {diagnostics.get('ocr_started_at', 'Not captured')}",
        f"OCR finished at: {diagnostics.get('ocr_finished_at', 'Not captured')}",
        f"OCR duration: {diagnostics.get('ocr_duration_seconds', 'Not captured')}",
        f"OCR running state: {diagnostics.get('ocr_running', 'Not captured')}",
        f"OCR run request ignored because OCR already running: {diagnostics.get('duplicate_ocr_run_ignored_count', 'Not captured')}",
    ]
    return "\n".join(lines)


def build_debug_report_text(
    line_df: pd.DataFrame,
    legend_text: str = "",
    clean_text: str = "",
    raw_text: str = "",
    source_mode: str = "",
    output_mode: str = "",
    area_mode: str = "",
    crop_box: Optional[Tuple[int, int, int, int]] = None,
    matches_df: Optional[pd.DataFrame] = None,
    unmatched: Optional[List[str]] = None,
    ocr_engine: str = "",
    image_quality_status: str = "",
    quality_metrics: Optional[Dict[str, object]] = None,
    session_diagnostics: Optional[Dict[str, object]] = None,
    events: Optional[List[Dict[str, object]]] = None,
    timings: Optional[Dict[str, object]] = None,
    ocr_workload_diagnostics: Optional[Dict[str, object]] = None,
    ocr_box_rows: Optional[pd.DataFrame] = None,
    ocr_call_diagnostics: Optional[Dict[str, object]] = None,
    ocr_call_trace: Optional[List[str]] = None,
    downscale_diagnostics: Optional[Dict[str, object]] = None,
    ocr_resize_test: str = "Auto",
    interface_language: str = "",
    platform: str = "",
    rc11c_translation_diagnostics: Optional[Dict[str, object]] = None,
    rc11d_validation_diagnostics: Optional[Dict[str, object]] = None,
    rc11e_normalization_diagnostics: Optional[Dict[str, object]] = None,
    rc11f_cache_diagnostics: Optional[Dict[str, object]] = None,
    rc11g_lookup_index_diagnostics: Optional[Dict[str, object]] = None,
) -> str:
    """Developer-facing diagnostic export for beta testing."""
    quality_metrics = quality_metrics or {}
    readable = build_readable_line_translation(line_df) if line_df is not None and not line_df.empty else ""
    report_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    if not platform:
        try:
            platform = str(st.context.headers.get("user-agent", "") or "Not captured")
        except Exception:
            platform = "Not captured"
    parts = [
        "================================================",
        "Diagnostic Report",
        "================================================",
        "",
        "Note: This report is for diagnosing OCR / dictionary / overlay issues.",
        "",
        "=== Application Information ===",
        f"App version: {APP_VERSION}",
        f"Timestamp: {report_timestamp}",
        f"Interface language: {interface_language or 'Not captured'}",
        f"Pattern language / terminology: {source_mode}",
        f"Translate result to: {output_mode}",
        f"Platform: {platform or 'Not captured'}",
        "",
        "=== Image Information ===",
        f"Area selected: {area_mode}",
        f"Crop box: {crop_box}",
        f"OCR Resize Test: {ocr_resize_test}",
        f"Image quality status: {image_quality_status or 'Not captured'}",
        f"Resolution: {quality_metrics.get('width_px', '')} x {quality_metrics.get('height_px', '')} px",
        f"Sharpness: {quality_metrics.get('sharpness_score', '')}",
        f"Contrast: {quality_metrics.get('contrast_score', '')}",
        "",
        "=== OCR Image Pipeline ===",
        _format_ocr_image_pipeline(ocr_call_diagnostics),
        "",
        "=== OCR Resize / Downscale Details ===",
        _format_rc11b_downscale_diagnostics(
            downscale_diagnostics,
            timings,
            ocr_workload_diagnostics,
        ),
        "",
        "=== OCR Information ===",
        f"OCR engine: {ocr_engine or 'Not captured'}",
        "",
        "=== OCR Configuration / Model ===",
        _format_ocr_model_diagnostics(ocr_call_diagnostics),
        "",
        "=== OCR Invocation Counts ===",
        _format_ocr_invocation_counts(ocr_call_diagnostics),
        "",
        "=== OCR EXECUTION ===",
        _format_ocr_execution_diagnostics(session_diagnostics),
        "",
        "=== OCR WORKLOAD ===",
        _format_ocr_workload_diagnostics(ocr_workload_diagnostics),
        "",
        "=== Whole Pattern Performance Diagnostics ===",
        _format_rc11a_performance_diagnostics(
            ocr_workload_diagnostics,
            ocr_call_diagnostics,
            timings,
            area_mode=area_mode,
        ),
        "",
        "=== Top 20 OCR Boxes By Confidence ===",
        _format_ocr_box_list(ocr_box_rows, "confidence", limit=20),
        "",
        "=== Largest 20 OCR Boxes ===",
        _format_ocr_box_list(ocr_box_rows, "largest", limit=20),
        "",
        "=== Smallest 20 OCR Boxes ===",
        _format_ocr_box_list(ocr_box_rows, "smallest", limit=20),
        "",
        "=== Cleaned OCR ===",
        clean_text.strip() or "Not captured",
        "",
        "=== Raw OCR ===",
        raw_text.strip() or "Not captured",
        "",
        "=== Translation Information ===",
        "",
        "=== Translation Statistics ===",
        _format_rc11c_translation_diagnostics(rc11c_translation_diagnostics),
        "",
        "=== Translation Cost Summary ===",
        _format_rc11c_translation_cost_summary(rc11c_translation_diagnostics),
        "",
        "=== MATCHED TERMS ===",
        _format_matched_terms(matches_df, output_mode),
        "",
        "=== UNMATCHED TERMS ===",
        _format_unmatched_terms(unmatched),
        "",
        "=== CSV MATCH DETAILS ===",
        _format_csv_match_details(matches_df),
        "",
        "=== Translation Output ===",
        readable.strip() or "Not captured",
        "",
        "=== Overlay Legend ===",
        legend_text.strip() or "Not captured",
        "",
        "=== Performance ===",
        "",
        "=== DEBUG TIMINGS ===",
        _format_debug_timings(timings),
        "",
        "=== Developer Information ===",
        "",
        "=== Session Diagnostics ===",
        _format_session_diagnostics(session_diagnostics),
        "",
        "=== Button / OCR Diagnostics ===",
        _format_button_ocr_diagnostics(session_diagnostics),
        "",
        "=== OCR Call Trace ===",
        _format_ocr_call_trace(ocr_call_trace),
        "",
        "=== Event Log ===",
        _format_event_log(events),
        "",
        "=== Timing Validation ===",
        _format_rc11d_timing_validation(rc11d_validation_diagnostics),
        "",
        "=== Function Call Diagnostics ===",
        _format_rc11d_function_call_diagnostics(rc11d_validation_diagnostics),
        "",
        "=== Lookup Validation ===",
        _format_rc11d_lookup_validation(rc11d_validation_diagnostics),
        "",
        "=== Regex Validation ===",
        _format_rc11d_regex_validation(rc11d_validation_diagnostics),
        "",
        "=== Top Function Calls ===",
        _format_rc11d_top_function_calls(rc11d_validation_diagnostics),
        "",
        "=== Normalization Diagnostics ===",
        _format_rc11e_normalization_diagnostics(rc11e_normalization_diagnostics),
        "",
        "=== Top Normalization Callers ===",
        _format_rc11e_top_normalization_callers(rc11e_normalization_diagnostics),
        "",
        "=== Lookup Chain Diagnostics ===",
        _format_rc11e_lookup_chain_diagnostics(rc11e_normalization_diagnostics),
        "",
        "=== CSV Term Diagnostics ===",
        _format_rc11e_csv_term_diagnostics(rc11e_normalization_diagnostics),
        "",
        "=== CSV Term Cache Diagnostics ===",
        _format_rc11f_cache_diagnostics(rc11f_cache_diagnostics),
        "",
        "=== Normalized Lookup Index Diagnostics ===",
        _format_rc11g_lookup_index_diagnostics(rc11g_lookup_index_diagnostics),
        "",
    ]
    return "\n".join(parts).strip() + "\n"





# -----------------------------
# Area selection helpers
# -----------------------------
def get_preset_crop_box(image: Image.Image, area_mode: str) -> Tuple[int, int, int, int]:
    """Return a crop box (left, top, right, bottom) for simple user-friendly presets."""
    w, h = image.size
    if area_mode == "Left side":
        return (0, 0, max(1, w // 2), h)
    if area_mode == "Right side":
        return (min(w - 1, w // 2), 0, w, h)
    if area_mode == "Top half":
        return (0, 0, w, max(1, h // 2))
    if area_mode == "Bottom half":
        return (0, min(h - 1, h // 2), w, h)
    return (0, 0, w, h)


def get_default_select_area_crop_box(image: Image.Image) -> Tuple[int, int, int, int]:
    """Initial Select Area crop: centered 50% rectangle for clear edit intent."""
    w, h = image.size
    crop_w = max(50, int(round(w * 0.5)))
    crop_h = max(50, int(round(h * 0.5)))
    left = max(0, (w - crop_w) // 2)
    top = max(0, (h - crop_h) // 2)
    return clamp_crop_box((left, top, left + crop_w, top + crop_h), image)


def prepare_cropper_display_image(
    image: Image.Image,
    max_width: int = 380,
    max_height: int = 720,
) -> Tuple[Image.Image, float, float, Dict[str, object]]:
    """Create a mobile-friendly cropper image and return original/display scales.

    Crop coordinates are still stored in original-image coordinates. The display
    image only makes the interactive cropper fit better on narrow mobile screens.
    """
    start = time.perf_counter()
    original_w, original_h = image.size
    ratio = min(1.0, max_width / float(original_w), max_height / float(original_h))
    display_w = max(1, int(round(original_w * ratio)))
    display_h = max(1, int(round(original_h * ratio)))
    if display_w == original_w and display_h == original_h:
        display_image = image
    else:
        display_image = image.resize((display_w, display_h), Image.Resampling.LANCZOS)
    scale_x = original_w / float(display_w)
    scale_y = original_h / float(display_h)
    diagnostics = {
        "display_proxy_applied": bool(display_image is not image),
        "original_width": original_w,
        "original_height": original_h,
        "display_width": display_w,
        "display_height": display_h,
        "scale_x": round(scale_x, 6),
        "scale_y": round(scale_y, 6),
        "creation_seconds": round(time.perf_counter() - start, 6),
    }
    return display_image, scale_x, scale_y, diagnostics


def crop_box_original_to_display(
    box: Tuple[int, int, int, int],
    scale_x: float,
    scale_y: float,
    display_image: Image.Image,
) -> Tuple[int, int, int, int]:
    left, top, right, bottom = box
    display_box = (
        int(round(left / scale_x)),
        int(round(top / scale_y)),
        int(round(right / scale_x)),
        int(round(bottom / scale_y)),
    )
    return clamp_crop_box(display_box, display_image)


def crop_box_display_to_original(
    box: Tuple[int, int, int, int],
    scale_x: float,
    scale_y: float,
    original_image: Image.Image,
) -> Tuple[int, int, int, int]:
    left, top, right, bottom = box
    original_box = (
        int(math.floor(left * scale_x)),
        int(math.floor(top * scale_y)),
        int(math.ceil(right * scale_x)),
        int(math.ceil(bottom * scale_y)),
    )
    return clamp_crop_box(original_box, original_image)


def clamp_crop_box(box: Tuple[int, int, int, int], image: Image.Image, min_size: int = 50) -> Tuple[int, int, int, int]:
    w, h = image.size
    left, top, right, bottom = [int(v) for v in box]
    left = max(0, min(left, w - min_size))
    right = max(left + min_size, min(right, w))
    top = max(0, min(top, h - min_size))
    bottom = max(top + min_size, min(bottom, h))
    return left, top, right, bottom


def crop_image_by_box(image: Image.Image, box: Tuple[int, int, int, int]) -> Image.Image:
    return image.convert("RGB").crop(clamp_crop_box(box, image))




def streamlit_cropper_available() -> bool:
    try:
        import streamlit_cropper  # noqa: F401
        return True
    except Exception:
        return False


def crop_box_from_cropper_result(result: object, image: Image.Image) -> Optional[Tuple[int, int, int, int]]:
    """Convert streamlit-cropper return_type='box' result to PIL crop box.

    Expected result shape from streamlit-cropper:
    {'left': x, 'top': y, 'width': w, 'height': h}
    The helper is defensive because Streamlit components can return None on first render.
    """
    if not isinstance(result, dict):
        return None
    try:
        left = int(round(float(result.get("left", 0))))
        top = int(round(float(result.get("top", 0))))
        width = int(round(float(result.get("width", 0))))
        height = int(round(float(result.get("height", 0))))
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    return clamp_crop_box((left, top, left + width, top + height), image)


def make_area_preview(image: Image.Image, box: Tuple[int, int, int, int]) -> Image.Image:
    """Show selected area with a light mask and simple boundary lines."""
    from PIL import ImageDraw
    img = image.convert("RGBA")
    w, h = img.size
    left, top, right, bottom = clamp_crop_box(box, image)
    shade = Image.new("RGBA", img.size, (0, 0, 0, 72))
    clear = Image.new("RGBA", (right-left, bottom-top), (0, 0, 0, 0))
    shade.paste(clear, (left, top))
    out = Image.alpha_composite(img, shade)
    draw = ImageDraw.Draw(out)
    line_w = max(3, min(w, h)//350)
    draw.rectangle((left, top, right, bottom), outline=(255, 80, 80, 235), width=line_w)
    # Four boundary guides, kept deliberately simple for mobile users.
    draw.line((left, 0, left, h), fill=(255, 80, 80, 155), width=max(1, line_w//2))
    draw.line((right, 0, right, h), fill=(255, 80, 80, 155), width=max(1, line_w//2))
    draw.line((0, top, w, top), fill=(255, 80, 80, 155), width=max(1, line_w//2))
    draw.line((0, bottom, w, bottom), fill=(255, 80, 80, 155), width=max(1, line_w//2))
    return out.convert("RGB")


# -----------------------------
# RC3 UI helpers
# -----------------------------
INTERFACE_LANGUAGES = {
    "English": {
        "app_title": "🧶 Crochet Translator",
        "app_subtitle": "Pattern OCR Translator (Beta)",
        "privacy_expander": "Privacy / storage note",
        "privacy": "Please only upload images you have permission to use, or images used for personal study/reference. This beta does not intentionally store uploaded images or OCR results; files are processed only for the current session.",
        "intro": "Translate crochet pattern images with OCR overlay and line-by-line translation.",
        "source_label": "Pattern language / terminology",
        "source_help": "If your English pattern does not say US or UK, choose English — US first. Most online amigurumi patterns use US terms.",
        "source_hint": "Not sure whether an English pattern uses US or UK terms? Choose **English — US** first. Switch to UK only if stitch names look wrong.",
        "source_hint_us": "💡 Most crochet patterns use US terminology.\nIf the stitch names don’t look right, try switching to English (UK).",
        "source_hint_uk": "💡 UK terminology is less common.\nIf the stitch names don’t look right, try switching to English (US), as most crochet patterns use US terminology.",
        "output_label": "Translate result to",
        "output_hint_us": "💡 US terminology is the standard used by most crochet patterns.",
        "output_hint_uk": "💡 Choose UK terminology only if you specifically need UK stitch names.",
        "default_mode_info": "Default mode is **Overlay Translation**. Select a smaller area for faster and more accurate results.",
        "upload_prompt": "Upload pattern image",
        "original_image": "Original image",
        "translation_area": "Translation area",
        "translation_area_tip": "💡 Whole Pattern is available, but Select Area is usually faster and more accurate, especially for patterns with multiple sections or columns.",
        "area_label": "Area to Translate",
        "area_select": "Select Area",
        "area_left": "Left Column",
        "area_right": "Right Column",
        "area_whole": "Whole Pattern",
        "cropper_missing": "Direct drag selection needs the optional package `streamlit-cropper`. Until installed, this version falls back to presets or sliders.",
        "cropper_drag": "Drag the rectangle around the text you want translated.",
        "cropper_failed": "Drag cropper could not load. Falling back to boundary sliders.",
        "boundary_instruction": "Move the boundary lines. No percentages needed — just keep the red box around the text you want translated.",
        "left_boundary": "Left boundary",
        "top_boundary": "Top boundary",
        "right_boundary": "Right boundary",
        "bottom_boundary": "Bottom boundary",
        "selected_area": "Selected translation area",
        "preview_selected_area": "Preview selected area only",
        "selected_area_sent_to_ocr": "This cropped area will be sent to OCR",
        "select_area_start": "Select Area",
        "select_area_edit": "Edit Selection",
        "select_area_use": "Use This Area",
        "select_area_cancel": "Cancel",
        "select_area_scroll_hint": "Preview is scrollable. Tap Select Area when you are ready to adjust the crop.",
        "select_area_confirmed_hint": "This selected area will be used for OCR. Tap Edit Selection to change it.",
        "select_area_required": "Please select an area before running OCR, or switch back to Whole Pattern.",
        "quality_good": "🟢 Good",
        "quality_fair": "🟡 Fair",
        "quality_poor": "🔴 Poor",
        "quality_good_msg": "Image quality looks suitable for OCR.",
        "quality_fair_msg": "OCR may contain some errors.",
        "quality_poor_msg": "Image quality may affect OCR accuracy.",
        "show_details": "Show Details",
        "resolution": "Resolution",
        "sharpness": "Sharpness",
        "contrast": "Contrast",
        "recommendation": "Recommendation",
        "table_item": "Item",
        "table_value": "Value",
        "quality_recommendation_good": "No major quality issue detected.",
        "quality_recommendation_check": "For better results, crop closer to the text and use a sharper, higher-contrast image.",
        "quality_block_warning": "OCR is likely to be unreliable with this image. A clearer crop is strongly recommended. You can still force a test run below for checking.",
        "force_ocr": "Run OCR anyway",
        "run_ocr": "Run OCR overlay translation",
        "running_ocr": "Running OCR and building overlay translation.",
        "ocr_failed": "OCR failed. This may be an OCR installation/model issue or an unsupported image format.",
        "settings_changed_rerun": "Settings changed. Please run OCR overlay translation again.",
        "overlay_translation": "Overlay translation",
        "overlay_caption": "Smart overlay: short translations are shown directly; long/colliding translations use numbered markers.",
        "download_overlay": "Download Overlay Image PNG",
        "no_overlay": "No translated overlay labels were generated. The OCR may have found text, but no CSV-backed crochet translation changed the lines.",
        "line_translation": "Line-by-line Translation",
        "translated_lines": "Translated OCR lines",
        "download_translation": "Download Translation TXT",
        "no_ocr_lines": "No OCR lines available for translation.",
        "report_problem": "🐞 Report a Problem",
        "report_problem_help": "If something doesn’t look right:\n\n• 📄 Download Diagnostic Report (recommended)\n\nIt helps us diagnose problems much faster.\n\n• 💬 Open Feedback Form\n\nDescribe the problem and optionally attach your Diagnostic Report or screenshots.",
        "report_intro": "If something doesn’t look right:",
        "report_download_action": "📄 Download Diagnostic Report (recommended)",
        "report_download_helper": "Helps us diagnose problems much faster.",
        "report_feedback_action": "💬 Open Feedback Form",
        "report_feedback_helper": "Describe the problem. You may optionally attach your Diagnostic Report or screenshots.",
        "generate_debug_report": "Generate Diagnostic Report",
        "debug_report_generated": "✅ Diagnostic Report generated successfully.",
        "download_debug_report": "Download Diagnostic Report",
        "send_feedback": "Open Feedback Form",
        "download_success": "✅ File downloaded successfully.\n\n📁 On most phones and tablets, downloaded files are usually saved in your Downloads folder.",
        "diagnostic_download_success": "✅ Diagnostic Report downloaded successfully.\n\n📁 On most phones and tablets, downloaded files are usually saved in your Downloads folder.",
        "start_info": "Upload an image or take a photo to begin.",
        "missing_csv": "Cannot find {file}. Put it in the same folder as this app.",
        "language_english_us": "English — US",
        "language_english_uk": "English — UK",
        "language_traditional_chinese": "Traditional Chinese",
        "language_simplified_chinese": "Simplified Chinese",
        "language_japanese": "Japanese",
    },
    "繁體中文": {
        "privacy": "請只上載你有權使用的圖片，或只作個人學習／參考用途的圖片。本測試版不會刻意儲存上載圖片或文字辨識結果；檔案只在本次使用期間中處理。",
        "privacy_expander": "私隱／儲存說明",
        "intro": "上載鈎織圖樣圖片，取得圖片標示翻譯及逐行翻譯。",
        "app_title": "🧶 鈎織翻譯器",
        "app_subtitle": "圖樣文字辨識翻譯器（測試版）",
        "source_label": "圖樣語言／術語",
        "source_help": "如果英文圖樣沒有標明美式或英式，請先選「英文－美式」。大部分網上 amigurumi 圖樣使用美式術語。",
        "source_hint": "不確定英文圖樣使用美式還是英式術語？請先選「英文－美式」。如果針法名稱看起來不對，再切換到「英文－英式」。",
        "source_hint_us": "💡 大部分鈎織圖樣使用美式術語。\n如果針法名稱看起來不對，可以試試切換到英文（英式）。",
        "source_hint_uk": "💡 英式術語較少見。\n如果針法名稱看起來不對，可以試試切換到英文（美式），因為大部分鈎織圖樣使用美式術語。",
        "output_label": "翻譯結果語言",
        "output_hint_us": "💡 美式術語是大部分鈎織圖樣使用的標準。",
        "output_hint_uk": "💡 只有在你特別需要英式針法名稱時，才建議選擇英式術語。",
        "default_mode_info": "預設會在圖片上顯示翻譯。選取較小範圍通常更快、更準確。",
        "upload_prompt": "上載圖樣圖片",
        "original_image": "原始圖片",
        "translation_area": "翻譯範圍",
        "translation_area_tip": "💡 你仍可使用整個圖樣，但選取範圍通常更快、更準確，特別適合有多個段落或多欄的圖樣。",
        "area_label": "要翻譯的範圍",
        "area_select": "選取範圍",
        "area_left": "左欄",
        "area_right": "右欄",
        "area_whole": "整個圖樣",
        "cropper_missing": "拖拉選取範圍需要額外套件 `streamlit-cropper`。未安裝時，會改用預設範圍或滑桿。",
        "cropper_drag": "請拖拉方框，框住要翻譯的文字。",
        "cropper_failed": "拖拉裁剪工具未能載入，將改用邊界滑桿。",
        "boundary_instruction": "移動邊界線即可。不需要輸入百分比，只要讓紅框包住要翻譯的文字。",
        "left_boundary": "左邊界",
        "top_boundary": "上邊界",
        "right_boundary": "右邊界",
        "bottom_boundary": "下邊界",
        "selected_area": "已選翻譯範圍",
        "preview_selected_area": "只預覽已選範圍",
        "selected_area_sent_to_ocr": "這個裁剪範圍會送去文字辨識",
        "select_area_start": "選取範圍",
        "select_area_edit": "編輯範圍",
        "select_area_use": "使用此範圍",
        "select_area_cancel": "取消",
        "select_area_scroll_hint": "預覽可以正常捲動。準備調整裁剪範圍時，請點選「選取範圍」。",
        "select_area_confirmed_hint": "文字辨識會使用這個已選範圍。如需修改，請點選「編輯範圍」。",
        "select_area_required": "請先選取要翻譯的範圍，或切換回整個圖樣。",
        "quality_good": "🟢 良好",
        "quality_fair": "🟡 尚可",
        "quality_poor": "🔴 不理想",
        "quality_good_msg": "圖片品質適合文字辨識。",
        "quality_fair_msg": "辨識結果可能有一些錯誤。",
        "quality_poor_msg": "圖片品質可能影響辨識準確度。",
        "show_details": "顯示詳情",
        "resolution": "解像度",
        "sharpness": "清晰度",
        "contrast": "對比",
        "recommendation": "建議",
        "table_item": "項目",
        "table_value": "數值",
        "quality_recommendation_good": "未發現明顯圖片品質問題。",
        "quality_recommendation_check": "建議裁剪得更貼近文字，並使用更清晰、對比較高的圖片。",
        "quality_block_warning": "這張圖片的辨識結果可能不可靠。建議先使用更清晰的裁剪範圍；你仍可強制測試。",
        "force_ocr": "仍然開始文字辨識",
        "run_ocr": "開始圖片翻譯",
        "running_ocr": "正在辨識圖片文字並產生翻譯……",
        "ocr_failed": "文字辨識失敗。可能是文字辨識模型問題，或圖片格式不支援。",
        "settings_changed_rerun": "設定已變更，請重新開始圖片翻譯。",
        "overlay_translation": "圖片翻譯結果",
        "overlay_caption": "短翻譯會直接顯示在圖片上；較長或重疊的翻譯會用編號標記。",
        "download_overlay": "下載翻譯圖片 PNG",
        "no_overlay": "未產生圖片標示翻譯。文字辨識可能找到文字，但沒有產生可用字典翻譯。",
        "line_translation": "逐行翻譯",
        "translated_lines": "已翻譯的文字辨識行",
        "download_translation": "下載文字翻譯 TXT",
        "no_ocr_lines": "沒有可翻譯的文字辨識行。",
        "report_problem": "🐞 回報問題",
        "report_problem_help": "如果翻譯看起來不太對：\n\n• 📄 下載診斷報告（建議）\n\n這能幫助我們更快找出問題。\n\n• 💬 開啟意見表單\n\n請描述問題，也可以附上診斷報告或截圖。",
        "report_intro": "如果翻譯看起來不太對：",
        "report_download_action": "📄 下載診斷報告（建議）",
        "report_download_helper": "這能幫助我們更快找出問題。",
        "report_feedback_action": "💬 開啟意見表單",
        "report_feedback_helper": "請描述問題，也可以附上診斷報告或截圖。",
        "generate_debug_report": "產生診斷報告",
        "debug_report_generated": "✅ 診斷報告已成功產生。",
        "download_debug_report": "下載診斷報告",
        "send_feedback": "開啟意見表單",
        "download_success": "✅ 檔案已成功下載。\n\n📁 在大部分手機和平板電腦上，下載的檔案通常會儲存在「下載」資料夾。",
        "diagnostic_download_success": "✅ 診斷報告已成功下載。\n\n📁 在大部分手機和平板電腦上，下載的檔案通常會儲存在「下載」資料夾。",
        "start_info": "請上載圖片或拍照開始。",
        "missing_csv": "找不到 {file}。請把它放在 app 同一個資料夾。",
        "language_english_us": "英文 — 美式",
        "language_english_uk": "英文 — 英式",
        "language_traditional_chinese": "繁體中文",
        "language_simplified_chinese": "簡體中文",
        "language_japanese": "日文",
    },
    "简体中文": {
        "privacy": "请只上传你有权使用的图片，或只作个人学习／参考用途的图片。本测试版不会刻意储存上传图片或文字识别结果；文件只在本次使用期间中处理。",
        "privacy_expander": "隐私／存储说明",
        "intro": "上传钩织图样图片，获得图片标示翻译和逐行翻译。",
        "app_title": "🧶 钩织翻译器",
        "app_subtitle": "图样文字识别翻译器（测试版）",
        "source_label": "图样语言／术语",
        "source_help": "如果英文图样没有标明美式或英式，请先选“英文－美式”。大部分网上 amigurumi 图样使用美式术语。",
        "source_hint": "不确定英文图样使用美式还是英式术语？请先选“英文－美式”。如果针法名称看起来不对，再切换到“英文－英式”。",
        "source_hint_us": "💡 大部分钩织图样使用美式术语。\n如果针法名称看起来不对，可以试试切换到英文（英式）。",
        "source_hint_uk": "💡 英式术语较少见。\n如果针法名称看起来不对，可以试试切换到英文（美式），因为大部分钩织图样使用美式术语。",
        "output_label": "翻译结果语言",
        "output_hint_us": "💡 美式术语是大部分钩织图样使用的标准。",
        "output_hint_uk": "💡 只有在你特别需要英式针法名称时，才建议选择英式术语。",
        "default_mode_info": "默认会在图片上显示翻译。选取较小范围通常更快、更准确。",
        "upload_prompt": "上传图样图片",
        "original_image": "原始图片",
        "translation_area": "翻译范围",
        "translation_area_tip": "💡 你仍可使用整个图样，但选取范围通常更快、更准确，特别适合有多个段落或多栏的图样。",
        "area_label": "要翻译的范围",
        "area_select": "选取范围",
        "area_left": "左栏",
        "area_right": "右栏",
        "area_whole": "整个图样",
        "cropper_missing": "拖拉选取范围需要额外套件 `streamlit-cropper`。未安装时，会改用默认范围或滑杆。",
        "cropper_drag": "请拖拉方框，框住要翻译的文字。",
        "cropper_failed": "拖拉裁剪工具未能加载，将改用边界滑杆。",
        "boundary_instruction": "移动边界线即可。不需要输入百分比，只要让红框包住要翻译的文字。",
        "left_boundary": "左边界",
        "top_boundary": "上边界",
        "right_boundary": "右边界",
        "bottom_boundary": "下边界",
        "selected_area": "已选翻译范围",
        "preview_selected_area": "只预览已选范围",
        "selected_area_sent_to_ocr": "这个裁剪范围会送去文字识别",
        "select_area_start": "选取范围",
        "select_area_edit": "编辑范围",
        "select_area_use": "使用此范围",
        "select_area_cancel": "取消",
        "select_area_scroll_hint": "预览可以正常滚动。准备调整裁剪范围时，请点选“选取范围”。",
        "select_area_confirmed_hint": "文字识别会使用这个已选范围。如需修改，请点选“编辑范围”。",
        "select_area_required": "请先选取要翻译的范围，或切换回整个图样。",
        "quality_good": "🟢 良好",
        "quality_fair": "🟡 尚可",
        "quality_poor": "🔴 不理想",
        "quality_good_msg": "图片质量适合文字识别。",
        "quality_fair_msg": "识别结果可能有一些错误。",
        "quality_poor_msg": "图片质量可能影响识别准确度。",
        "show_details": "显示详情",
        "resolution": "分辨率",
        "sharpness": "清晰度",
        "contrast": "对比度",
        "recommendation": "建议",
        "table_item": "项目",
        "table_value": "数值",
        "quality_recommendation_good": "未发现明显图片质量问题。",
        "quality_recommendation_check": "建议裁剪得更贴近文字，并使用更清晰、对比度更高的图片。",
        "quality_block_warning": "这张图片的识别结果可能不可靠。建议先使用更清晰的裁剪范围；你仍可强制测试。",
        "force_ocr": "仍然开始文字识别",
        "run_ocr": "开始图片翻译",
        "running_ocr": "正在识别图片文字并生成翻译……",
        "ocr_failed": "文字识别失败。可能是文字识别模型问题，或图片格式不支持。",
        "settings_changed_rerun": "设置已更改，请重新开始图片翻译。",
        "overlay_translation": "图片翻译结果",
        "overlay_caption": "短翻译会直接显示在图片上；较长或重叠的翻译会用编号标记。",
        "download_overlay": "下载翻译图片 PNG",
        "no_overlay": "未生成图片标示翻译。文字识别可能找到文字，但没有生成可用字典翻译。",
        "line_translation": "逐行翻译",
        "translated_lines": "已翻译的文字识别行",
        "download_translation": "下载文字翻译 TXT",
        "no_ocr_lines": "没有可翻译的文字识别行。",
        "report_problem": "🐞 回报问题",
        "report_problem_help": "如果翻译看起来不太对：\n\n• 📄 下载诊断报告（建议）\n\n这能帮助我们更快找出问题。\n\n• 💬 打开反馈表单\n\n请描述问题，也可以附上诊断报告或截图。",
        "report_intro": "如果翻译看起来不太对：",
        "report_download_action": "📄 下载诊断报告（建议）",
        "report_download_helper": "这能帮助我们更快找出问题。",
        "report_feedback_action": "💬 打开反馈表单",
        "report_feedback_helper": "请描述问题，也可以附上诊断报告或截图。",
        "generate_debug_report": "生成诊断报告",
        "debug_report_generated": "✅ 诊断报告已成功生成。",
        "download_debug_report": "下载诊断报告",
        "send_feedback": "打开反馈表单",
        "download_success": "✅ 文件已成功下载。\n\n📁 在大部分手机和平板电脑上，下载的文件通常会保存在“下载”文件夹。",
        "diagnostic_download_success": "✅ 诊断报告已成功下载。\n\n📁 在大部分手机和平板电脑上，下载的文件通常会保存在“下载”文件夹。",
        "start_info": "请上传图片或拍照开始。",
        "missing_csv": "找不到 {file}。请把它放在 app 同一个文件夹。",
        "language_english_us": "英文 — 美式",
        "language_english_uk": "英文 — 英式",
        "language_traditional_chinese": "繁体中文",
        "language_simplified_chinese": "简体中文",
        "language_japanese": "日文",
    },
    "日本語": {
        "privacy": "使用許可のある画像、または個人学習・参考用の画像のみアップロードしてください。このベータ版はアップロード画像やOCR結果を意図的に保存しません。ファイルは現在の利用中のみ処理されます。",
        "privacy_expander": "プライバシー／保存について",
        "intro": "かぎ針編みパターン画像をアップロードして、画像上の翻訳と行ごとの翻訳を確認できます。",
        "app_title": "🧶 かぎ針編み翻訳",
        "app_subtitle": "パターンOCR翻訳（ベータ版）",
        "source_label": "パターンの言語／用語",
        "source_help": "英語パターンに米式／英式の記載がない場合は、まず「英語 — 米国式」を選んでください。オンラインの amigurumi パターンは米式が多いです。",
        "source_hint": "英語パターンが米式か英式かわからない場合は、まず「英語 — 米国式」を選んでください。針目名が合わない場合だけ「英語 — 英国式」に切り替えてください。",
        "source_hint_us": "💡 ほとんどのかぎ針編みパターンは米式用語を使っています。\n針目名が合わない場合は、英語（英国式）に切り替えてみてください。",
        "source_hint_uk": "💡 英国式用語は比較的少数派です。\n針目名が合わない場合は、ほとんどのパターンで使われる英語（米国式）に切り替えてみてください。",
        "output_label": "翻訳先",
        "output_hint_us": "💡 米式用語は、ほとんどのかぎ針編みパターンで使われる標準的な用語です。",
        "output_hint_uk": "💡 英国式の針目名が特に必要な場合だけ、英国式用語を選んでください。",
        "default_mode_info": "初期設定では画像上に翻訳を表示します。範囲を小さくすると、より速く正確になりやすいです。",
        "upload_prompt": "パターン画像をアップロード",
        "original_image": "元の画像",
        "translation_area": "翻訳する範囲",
        "translation_area_tip": "💡 パターン全体も使用できますが、範囲を選択するほうが通常は速く、より正確です。複数のセクションや列があるパターンに特に適しています。",
        "area_label": "翻訳する範囲",
        "area_select": "範囲を選択",
        "area_left": "左の列",
        "area_right": "右の列",
        "area_whole": "パターン全体",
        "cropper_missing": "ドラッグ選択には追加パッケージ `streamlit-cropper` が必要です。未導入の場合は、プリセットまたはスライダーを使用します。",
        "cropper_drag": "翻訳したい文字を囲むように四角をドラッグしてください。",
        "cropper_failed": "ドラッグ選択を読み込めませんでした。境界スライダーに切り替えます。",
        "boundary_instruction": "境界線を動かしてください。パーセント指定は不要です。赤い枠で翻訳したい文字を囲んでください。",
        "left_boundary": "左の境界",
        "top_boundary": "上の境界",
        "right_boundary": "右の境界",
        "bottom_boundary": "下の境界",
        "selected_area": "選択した翻訳範囲",
        "preview_selected_area": "選択範囲だけをプレビュー",
        "selected_area_sent_to_ocr": "この切り抜き範囲が文字認識に送られます",
        "select_area_start": "範囲を選択",
        "select_area_edit": "選択範囲を編集",
        "select_area_use": "この範囲を使う",
        "select_area_cancel": "キャンセル",
        "select_area_scroll_hint": "プレビューは通常どおりスクロールできます。範囲を調整する場合は「範囲を選択」をタップしてください。",
        "select_area_confirmed_hint": "この選択範囲が文字認識に使われます。変更する場合は「選択範囲を編集」をタップしてください。",
        "select_area_required": "OCRを実行する前に範囲を選択するか、パターン全体に戻してください。",
        "quality_good": "🟢 良好",
        "quality_fair": "🟡 やや注意",
        "quality_poor": "🔴 不十分",
        "quality_good_msg": "OCRに適した画像です。",
        "quality_fair_msg": "OCR結果に一部誤りが出る可能性があります。",
        "quality_poor_msg": "画像品質がOCR精度に影響する可能性があります。",
        "show_details": "詳細を表示",
        "resolution": "解像度",
        "sharpness": "鮮明度",
        "contrast": "コントラスト",
        "recommendation": "推奨",
        "table_item": "項目",
        "table_value": "値",
        "quality_recommendation_good": "大きな画像品質の問題は見つかりませんでした。",
        "quality_recommendation_check": "文字部分に近く切り抜き、より鮮明でコントラストの高い画像を使うことをおすすめします。",
        "quality_block_warning": "この画像ではOCRが不安定になる可能性があります。より鮮明な切り抜きをおすすめしますが、テストとして強制実行できます。",
        "force_ocr": "それでもOCRを実行",
        "run_ocr": "画像翻訳を開始",
        "running_ocr": "画像の文字を認識して翻訳を作成しています……",
        "ocr_failed": "文字認識に失敗しました。OCRのインストール／モデルの問題、または未対応の画像形式の可能性があります。",
        "settings_changed_rerun": "設定が変更されました。もう一度画像翻訳を開始してください。",
        "overlay_translation": "画像上の翻訳",
        "overlay_caption": "短い翻訳は画像上に直接表示されます。長い翻訳や重なる翻訳は番号で表示されます。",
        "download_overlay": "翻訳画像PNGをダウンロード",
        "no_overlay": "画像上の翻訳ラベルは生成されませんでした。OCRで文字は検出されましたが、辞書に基づく翻訳が生成されなかった可能性があります。",
        "line_translation": "行ごとの翻訳",
        "translated_lines": "翻訳されたOCR行",
        "download_translation": "翻訳テキストをダウンロード",
        "no_ocr_lines": "翻訳できるOCR行がありません。",
        "report_problem": "🐞 問題を報告",
        "report_problem_help": "翻訳が正しくないように見える場合：\n\n• 📄 診断レポートをダウンロード（推奨）\n\n問題の確認がずっと速くなります。\n\n• 💬 フィードバックフォームを開く\n\n問題の内容を入力し、必要に応じて診断レポートやスクリーンショットを添付してください。",
        "report_intro": "翻訳が正しくないように見える場合：",
        "report_download_action": "📄 診断レポートをダウンロード（推奨）",
        "report_download_helper": "問題の確認がずっと速くなります。",
        "report_feedback_action": "💬 フィードバックフォームを開く",
        "report_feedback_helper": "問題の内容を入力し、必要に応じて診断レポートやスクリーンショットを添付してください。",
        "generate_debug_report": "診断レポートを生成",
        "debug_report_generated": "✅ 診断レポートを生成しました。",
        "download_debug_report": "診断レポートをダウンロード",
        "send_feedback": "フィードバックフォームを開く",
        "download_success": "✅ ファイルをダウンロードしました。\n\n📁 ほとんどのスマートフォンやタブレットでは、ダウンロードしたファイルは通常「ダウンロード」フォルダに保存されます。",
        "diagnostic_download_success": "✅ 診断レポートをダウンロードしました。\n\n📁 ほとんどのスマートフォンやタブレットでは、ダウンロードしたファイルは通常「ダウンロード」フォルダに保存されます。",
        "start_info": "画像をアップロードするか、写真を撮って開始してください。",
        "missing_csv": "{file} が見つかりません。このアプリと同じフォルダに置いてください。",
        "language_english_us": "英語 — 米国式",
        "language_english_uk": "英語 — 英国式",
        "language_traditional_chinese": "繁体字中国語",
        "language_simplified_chinese": "簡体字中国語",
        "language_japanese": "日本語",
    },
}


def get_quality_status(errors: List[str], warnings: List[str]) -> Tuple[str, str, str]:
    if errors:
        return "poor", "🔴 Poor", "Image quality may affect OCR accuracy."
    if warnings:
        return "fair", "🟡 Fair", "OCR may contain some errors."
    return "good", "🟢 Good", "Image quality looks suitable for OCR."


def build_quality_recommendation(errors: List[str], warnings: List[str]) -> str:
    messages = errors + warnings
    if messages:
        return " ".join(messages)
    return "No major quality issue detected."


def image_upload_signature(uploaded_file: object) -> str:
    try:
        pos = uploaded_file.tell()
        uploaded_file.seek(0)
        data = uploaded_file.getvalue()
        uploaded_file.seek(pos)
    except Exception:
        data = repr(uploaded_file).encode("utf-8")
    return hashlib.md5(data).hexdigest()


def build_ocr_input_signature(
    image_signature: str,
    source_mode: str,
    output_mode: str,
    area_mode: str,
    crop_box: Tuple[int, int, int, int],
    extra_settings: Optional[Tuple[object, ...]] = None,
) -> Tuple[object, ...]:
    stable_crop_box = tuple(int(round(v)) for v in crop_box)
    return (image_signature, source_mode, output_mode, area_mode, stable_crop_box, extra_settings or ())


def diagnostic_report_filename() -> str:
    version = APP_VERSION.split("Beta ", 1)[-1].rstrip(")") if "Beta " in APP_VERSION else APP_VERSION
    safe_version = re.sub(r"[^A-Za-z0-9]+", "", version) or "RC"
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return f"PatternOCR_DiagnosticReport_{safe_version}_{timestamp}.txt"


def download_button_rc3(label: str, data: object, file_name: str, mime: str, key: str, success_message: Optional[str] = None):
    """Render a download button and show a shared public confirmation after click."""
    def mark_download_complete(download_key: str = key) -> None:
        st.session_state["last_successful_download_key"] = download_key

    try:
        clicked = st.download_button(
            label,
            data=data,
            file_name=file_name,
            mime=mime,
            key=key,
            on_click=mark_download_complete,
        )
    except TypeError:
        # Older Streamlit fallback. Results are still preserved by session_state.
        clicked = st.download_button(
            label,
            data=data,
            file_name=file_name,
            mime=mime,
            key=key,
            on_click=mark_download_complete,
        )
    if st.session_state.get("last_successful_download_key") == key:
        try:
            default_success = t("download_success")
        except Exception:
            default_success = INTERFACE_LANGUAGES["English"]["download_success"]
        st.success(success_message or default_success)
    return clicked


def init_rc3_state():
    st.session_state.setdefault("rc3_ocr_result", None)
    st.session_state.setdefault("rc3_image_signature", None)
    st.session_state.setdefault("rc3_ocr_result_signature", None)
    st.session_state.setdefault("pending_ocr_run", False)
    st.session_state.setdefault("latest_crop_box", None)
    st.session_state.setdefault("select_area_confirmed_crop_box", None)
    st.session_state.setdefault("select_area_editing", False)
    st.session_state.setdefault("select_area_draft_crop_box", None)
    st.session_state.setdefault("select_area_display_proxy_diagnostics", {})
    st.session_state.setdefault("ocr_running", False)
    st.session_state.setdefault("ocr_started_at", None)
    st.session_state.setdefault("ocr_finished_at", None)
    st.session_state.setdefault("ocr_duration_seconds", None)
    st.session_state.setdefault("duplicate_ocr_run_ignored_count", 0)
    st.session_state.setdefault("debug_report_ready", False)
    st.session_state.setdefault("last_successful_download_key", None)
    st.session_state.setdefault("rc10b_diagnostic_events", [])
    st.session_state.setdefault("rc10b_image_signature_history", [])
    st.session_state.setdefault("rc10b_last_image_present", False)
    st.session_state.setdefault("rc10b_last_image_signature", None)
    st.session_state.setdefault("rc10b_rerun_count", 0)
    st.session_state.setdefault("rc10b_run_button_click_count", 0)
    st.session_state.setdefault("rc10b_last_button_click_rerun", None)
    st.session_state.setdefault("rc10b_last_ocr_block_rerun_delta", None)
    st.session_state.setdefault("rc10b_last_cropper_box", None)


def request_ocr_run():
    if st.session_state.get("ocr_running"):
        st.session_state["duplicate_ocr_run_ignored_count"] = st.session_state.get("duplicate_ocr_run_ignored_count", 0) + 1
        rc10b_log_event(
            "Run OCR request ignored because OCR already running",
            duplicate_ocr_run_ignored_count=st.session_state.get("duplicate_ocr_run_ignored_count"),
        )
        return
    st.session_state["rc10b_run_button_click_count"] = st.session_state.get("rc10b_run_button_click_count", 0) + 1
    st.session_state["rc10b_last_button_click_rerun"] = st.session_state.get("rc10b_rerun_count")
    st.session_state["pending_ocr_run"] = True
    rc10b_log_event(
        "Run OCR button clicked",
        run_button_click_count=st.session_state.get("rc10b_run_button_click_count"),
        click_rerun=st.session_state.get("rc10b_last_button_click_rerun"),
    )


def rc10b_session_state_counts() -> Dict[str, int]:
    keys = [str(key) for key in st.session_state.keys()]
    cropper_keys = [
        key for key in keys
        if "cropper" in key.lower() or key.startswith("crop_")
    ]
    slider_keys = [
        key for key in keys
        if key.startswith("crop_left_")
        or key.startswith("crop_top_")
        or key.startswith("crop_right_")
        or key.startswith("crop_bottom_")
    ]
    return {
        "total_session_state_keys": len(keys),
        "cropper_related_keys": len(cropper_keys),
        "slider_related_keys": len(slider_keys),
    }


def rc10b_log_event(event: str, **details):
    events = st.session_state.setdefault("rc10b_diagnostic_events", [])
    counts = rc10b_session_state_counts()
    record = {
        "time": time.strftime("%H:%M:%S"),
        "event": event,
        **counts,
        **details,
    }
    events.append(record)
    st.session_state["rc10b_diagnostic_events"] = events[-200:]


def rc10b_note_image_absent():
    if st.session_state.get("rc10b_last_image_present"):
        rc10b_log_event(
            "image deleted or cleared",
            previous_signature=st.session_state.get("rc10b_last_image_signature"),
        )
    st.session_state["rc10b_last_image_present"] = False
    st.session_state["rc10b_last_image_signature"] = None


def rc10b_note_image_present(image_signature: str):
    history = st.session_state.setdefault("rc10b_image_signature_history", [])
    previous_signature = st.session_state.get("rc10b_last_image_signature")
    if previous_signature != image_signature:
        if image_signature not in history:
            history.append(image_signature)
            st.session_state["rc10b_image_signature_history"] = history
        rc10b_log_event(
            "image uploaded or changed",
            image_signature=image_signature,
            previous_signature=previous_signature,
            image_signature_history_length=len(history),
        )
    st.session_state["rc10b_last_image_present"] = True
    st.session_state["rc10b_last_image_signature"] = image_signature


def render_rc10b_diagnostics():
    counts = rc10b_session_state_counts()
    history = st.session_state.get("rc10b_image_signature_history", [])
    events = st.session_state.get("rc10b_diagnostic_events", [])
    with st.expander("RC10b upload/session diagnostics", expanded=False):
        summary_df = pd.DataFrame(
            [
                {"Metric": "Total session_state keys", "Value": counts["total_session_state_keys"]},
                {"Metric": "Cropper-related session_state keys", "Value": counts["cropper_related_keys"]},
                {"Metric": "Slider-related session_state keys", "Value": counts["slider_related_keys"]},
                {"Metric": "Image signature history length", "Value": len(history)},
                {"Metric": "Current rc3 image signature", "Value": st.session_state.get("rc3_image_signature")},
                {"Metric": "Last observed image present", "Value": st.session_state.get("rc10b_last_image_present")},
                {"Metric": "Last observed image signature", "Value": st.session_state.get("rc10b_last_image_signature")},
                {"Metric": "Run button click count", "Value": st.session_state.get("rc10b_run_button_click_count")},
                {"Metric": "Reruns between click and OCR block", "Value": st.session_state.get("rc10b_last_ocr_block_rerun_delta")},
                {"Metric": "pending_ocr_run", "Value": st.session_state.get("pending_ocr_run")},
                {"Metric": "latest_crop_box", "Value": st.session_state.get("latest_crop_box")},
                {"Metric": "ocr_running", "Value": st.session_state.get("ocr_running")},
                {"Metric": "OCR started at", "Value": st.session_state.get("ocr_started_at")},
                {"Metric": "OCR finished at", "Value": st.session_state.get("ocr_finished_at")},
                {"Metric": "OCR duration seconds", "Value": st.session_state.get("ocr_duration_seconds")},
                {"Metric": "Duplicate OCR run requests ignored", "Value": st.session_state.get("duplicate_ocr_run_ignored_count")},
            ]
        )
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
        if events:
            st.markdown("**Recent events**")
            st.dataframe(pd.DataFrame(events[-100:]), use_container_width=True, hide_index=True)


def rc10b_diagnostic_snapshot() -> Dict[str, object]:
    counts = rc10b_session_state_counts()
    history = st.session_state.get("rc10b_image_signature_history", [])
    return {
        **counts,
        "image_signature_history_length": len(history),
        "run_button_click_count": st.session_state.get("rc10b_run_button_click_count"),
        "reruns_between_click_and_ocr_block": st.session_state.get("rc10b_last_ocr_block_rerun_delta"),
        "pending_ocr_run": st.session_state.get("pending_ocr_run"),
        "latest_crop_box": st.session_state.get("latest_crop_box"),
        "ocr_running": st.session_state.get("ocr_running"),
        "ocr_started_at": st.session_state.get("ocr_started_at"),
        "ocr_finished_at": st.session_state.get("ocr_finished_at"),
        "ocr_duration_seconds": st.session_state.get("ocr_duration_seconds"),
        "duplicate_ocr_run_ignored_count": st.session_state.get("duplicate_ocr_run_ignored_count"),
    }


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


# -----------------------------
# UI
# -----------------------------
init_rc3_state()
st.session_state["rc10b_rerun_count"] = st.session_state.get("rc10b_rerun_count", 0) + 1

INTERFACE_LANGUAGE_DISPLAY_LABELS = {
    "English": "EN",
    "繁體中文": "繁中",
    "简体中文": "简中",
    "日本語": "日本語",
}

INTERFACE_LANGUAGE_OPTIONS = ["English", "繁體中文", "简体中文", "日本語"]

def detect_initial_interface_language() -> str:
    raw_locale = ""
    try:
        raw_locale = str(getattr(st.context, "locale", "") or "")
    except Exception:
        raw_locale = ""

    if not raw_locale:
        try:
            raw_locale = str(st.context.headers.get("accept-language", "") or "")
        except Exception:
            raw_locale = ""

    locale_tags = [
        part.split(";")[0].strip().lower().replace("_", "-")
        for part in raw_locale.split(",")
        if part.split(";")[0].strip()
    ]

    for tag in locale_tags:
        if tag.startswith("zh") or "hant" in tag or "hans" in tag:
            if "hans" in tag or "-cn" in tag or "-sg" in tag:
                return "简体中文"
            return "繁體中文"

    for tag in locale_tags:
        if tag.startswith("ja"):
            return "日本語"

    return "English"

initial_interface_language = detect_initial_interface_language()
initial_interface_language_index = INTERFACE_LANGUAGE_OPTIONS.index(initial_interface_language)

interface_language = st.selectbox(
    "Language",
    INTERFACE_LANGUAGE_OPTIONS,
    index=initial_interface_language_index,
    key="interface_language_selector",
    format_func=lambda value: INTERFACE_LANGUAGE_DISPLAY_LABELS.get(value, value),
    width="stretch",
)
ui_text = INTERFACE_LANGUAGES.get(interface_language, INTERFACE_LANGUAGES["English"])

def t(key: str) -> str:
    return ui_text.get(key, INTERFACE_LANGUAGES["English"].get(key, key))


LANGUAGE_OPTION_LABEL_KEYS = {
    "English — US": "language_english_us",
    "English — UK": "language_english_uk",
    "Traditional Chinese": "language_traditional_chinese",
    "Simplified Chinese": "language_simplified_chinese",
    "Japanese": "language_japanese",
}

AREA_LABEL_KEYS = {
    "Select Area": "area_select",
    "Left Column": "area_left",
    "Right Column": "area_right",
    "Whole Pattern": "area_whole",
}


st.title(t("app_title"))
st.caption(t("app_subtitle"))

LANGUAGE_OPTIONS = ["English — US", "English — UK", "Traditional Chinese", "Simplified Chinese", "Japanese"]

image_file = st.file_uploader(
    t("upload_prompt"),
    type=["png", "jpg", "jpeg", "webp"],
    label_visibility="collapsed",
)

if image_file is None:
    rc10b_note_image_absent()
    with st.expander(t("privacy_expander"), expanded=False):
        st.markdown(
            f"<div class='warning-box'>{ui_text['privacy']}</div>",
            unsafe_allow_html=True,
        )

if image_file is not None:
    current_signature = image_upload_signature(image_file)
    rc10b_note_image_present(current_signature)
    if st.session_state.get("rc3_image_signature") != current_signature:
        st.session_state["rc3_ocr_result"] = None
        st.session_state["rc3_ocr_result_signature"] = None
        st.session_state["pending_ocr_run"] = False
        st.session_state["latest_crop_box"] = None
        st.session_state["select_area_confirmed_crop_box"] = None
        st.session_state["select_area_editing"] = False
        st.session_state["select_area_draft_crop_box"] = None
        st.session_state["select_area_display_proxy_diagnostics"] = {}
        st.session_state["rc10b_last_cropper_box"] = None
        st.session_state["debug_report_ready"] = False
        st.session_state["last_successful_download_key"] = None
        st.session_state["rc3_image_signature"] = current_signature

    image_load_start = time.perf_counter()
    image = Image.open(image_file).convert("RGB")
    image_load_seconds = time.perf_counter() - image_load_start
    st.image(image, caption=t("original_image"), use_container_width=True)

    source_mode = st.selectbox(
        t("source_label"),
        LANGUAGE_OPTIONS,
        index=2,
        key="source_language_selector",
        help=t("source_help"),
        format_func=lambda value: t(LANGUAGE_OPTION_LABEL_KEYS.get(value, value)),
    )
    if source_mode == "English — US":
        st.caption(t("source_hint_us"))
    elif source_mode == "English — UK":
        st.caption(t("source_hint_uk"))

    output_mode = st.selectbox(
        t("output_label"),
        LANGUAGE_OPTIONS,
        index=2,
        key="target_language_selector",
        format_func=lambda value: t(LANGUAGE_OPTION_LABEL_KEYS.get(value, value)),
    )
    if output_mode == "English — US":
        st.caption(t("output_hint_us"))
    elif output_mode == "English — UK":
        st.caption(t("output_hint_uk"))

    st.subheader(t("translation_area"))

    area_options = ["Select Area", "Whole Pattern"]
    if st.session_state.get("translation_area_mode_radio") not in area_options:
        st.session_state["translation_area_mode_radio"] = "Select Area"
    area_mode = st.radio(
        t("area_label"),
        area_options,
        key="translation_area_mode_radio",
        horizontal=True,
        index=area_options.index(st.session_state["translation_area_mode_radio"]),
        format_func=lambda value: t(AREA_LABEL_KEYS.get(value, value)),
    )
    if area_mode == "Whole Pattern":
        st.caption(t("translation_area_tip"))

    area_map = {
        "Select Area": "Whole image",
        "Left Column": "Left side",
        "Right Column": "Right side",
        "Whole Pattern": "Whole image",
    }

    area_mode_for_box = area_map.get(area_mode, "Whole image")
    preset_box = get_preset_crop_box(image, area_mode_for_box)

    if area_mode == "Whole Pattern":
        crop_box = preset_box
        st.session_state["latest_crop_box"] = crop_box
        st.session_state["select_area_editing"] = False
        st.session_state["select_area_draft_crop_box"] = None
        st.session_state["select_area_display_proxy_diagnostics"] = {}
    else:
        cropper_ok = streamlit_cropper_available()
        confirmed_crop_box = st.session_state.get("select_area_confirmed_crop_box")
        is_editing_area = bool(st.session_state.get("select_area_editing"))
        crop_box = clamp_crop_box(confirmed_crop_box, image) if confirmed_crop_box is not None else (0, 0, image.size[0], image.size[1])

        if is_editing_area:
            draft_crop_box = st.session_state.get("select_area_draft_crop_box") or confirmed_crop_box or get_default_select_area_crop_box(image)
            draft_crop_box = clamp_crop_box(draft_crop_box, image)
            adjust_mode = "Drag rectangle on image" if cropper_ok else "Use boundary sliders"

            if not cropper_ok:
                st.caption(t("cropper_missing"))

            if cropper_ok:
                st.caption(t("cropper_drag"))
                try:
                    from streamlit_cropper import st_cropper
                    safe_area_mode = re.sub(r"\W+", "_", area_mode_for_box.lower())
                    image_key_fragment = current_signature[:12]
                    cropper_key = f"cropper_{image_key_fragment}_{safe_area_mode}_{image.size[0]}x{image.size[1]}"
                    display_image, display_scale_x, display_scale_y, display_diag = prepare_cropper_display_image(image)
                    st.session_state["select_area_display_proxy_diagnostics"] = display_diag
                    display_crop_box = crop_box_original_to_display(
                        draft_crop_box,
                        display_scale_x,
                        display_scale_y,
                        display_image,
                    )
                    left0, top0, right0, bottom0 = display_crop_box
                    rc10b_log_event(
                        "cropper widget created",
                        cropper_key=cropper_key,
                        image_signature=current_signature,
                        area_mode=area_mode,
                        display_proxy=display_diag,
                    )

                    cropper_result = st_cropper(
                        display_image,
                        realtime_update=True,
                        default_coords=(left0, right0, top0, bottom0),
                        box_color="#ff4b4b",
                        aspect_ratio=None,
                        return_type="box",
                        should_resize_image=False,
                        key=cropper_key,
                    )
                    display_cropper_box = crop_box_from_cropper_result(cropper_result, display_image)
                    if display_cropper_box is not None:
                        cropper_box = crop_box_display_to_original(
                            display_cropper_box,
                            display_scale_x,
                            display_scale_y,
                            image,
                        )
                        previous_cropper_box = st.session_state.get("rc10b_last_cropper_box")
                        if previous_cropper_box != cropper_box:
                            rc10b_log_event(
                                "cropper box updated",
                                previous_cropper_box=previous_cropper_box,
                                cropper_box=cropper_box,
                                display_cropper_box=display_cropper_box,
                                image_signature=current_signature,
                                area_mode=area_mode,
                            )
                            st.session_state["rc10b_last_cropper_box"] = cropper_box
                        draft_crop_box = cropper_box
                        st.session_state["select_area_draft_crop_box"] = cropper_box
                except Exception as e:
                    st.warning(t("cropper_failed"))
                    st.caption(str(e))
                    adjust_mode = "Use boundary sliders"

            if adjust_mode != "Drag rectangle on image":
                w, h = image.size
                left0, top0, right0, bottom0 = draft_crop_box
                st.caption(t("boundary_instruction"))
                col_a, col_b = st.columns(2)
                safe_area_mode = re.sub(r"\W+", "_", area_mode_for_box.lower())
                key_suffix = f"{current_signature[:12]}_{safe_area_mode}_draft"
                with col_a:
                    left = st.slider(t("left_boundary"), 0, max(0, w - 50), int(left0), key=f"crop_left_{key_suffix}")
                    top = st.slider(t("top_boundary"), 0, max(0, h - 50), int(top0), key=f"crop_top_{key_suffix}")
                with col_b:
                    right = st.slider(t("right_boundary"), 50, w, int(right0), key=f"crop_right_{key_suffix}")
                    bottom = st.slider(t("bottom_boundary"), 50, h, int(bottom0), key=f"crop_bottom_{key_suffix}")
                draft_crop_box = clamp_crop_box((left, top, right, bottom), image)
                st.session_state["select_area_draft_crop_box"] = draft_crop_box

            preview_image = make_area_preview(image, draft_crop_box)
            st.image(preview_image, caption=t("selected_area"), use_container_width=True)
            col_cancel, col_use = st.columns(2)
            with col_cancel:
                if st.button(t("select_area_cancel"), key="select_area_cancel_button"):
                    st.session_state["select_area_editing"] = False
                    st.session_state["select_area_draft_crop_box"] = None
                    try:
                        st.rerun()
                    except Exception:
                        pass
            with col_use:
                if st.button(t("select_area_use"), key="select_area_use_button", type="primary"):
                    confirmed = clamp_crop_box(st.session_state.get("select_area_draft_crop_box") or draft_crop_box, image)
                    st.session_state["select_area_confirmed_crop_box"] = confirmed
                    st.session_state["latest_crop_box"] = confirmed
                    st.session_state["rc10b_last_cropper_box"] = confirmed
                    st.session_state["select_area_editing"] = False
                    st.session_state["select_area_draft_crop_box"] = None
                    crop_box = confirmed
                    rc10b_log_event(
                        "cropper box confirmed",
                        cropper_box=confirmed,
                        image_signature=current_signature,
                        area_mode=area_mode,
                    )
                    try:
                        st.rerun()
                    except Exception:
                        pass
        else:
            if confirmed_crop_box is not None:
                crop_box = clamp_crop_box(confirmed_crop_box, image)
                st.session_state["latest_crop_box"] = crop_box
                preview_image = make_area_preview(image, crop_box)
                st.image(preview_image, caption=t("selected_area"), use_container_width=True)
                st.caption(t("select_area_confirmed_hint"))
                if st.button(t("select_area_edit"), key="select_area_edit_button"):
                    st.session_state["select_area_editing"] = True
                    st.session_state["select_area_draft_crop_box"] = crop_box
                    try:
                        st.rerun()
                    except Exception:
                        pass
            else:
                st.image(image, caption=t("original_image"), use_container_width=True)
                st.caption(t("select_area_scroll_hint"))
                if st.button(t("select_area_start"), key="select_area_start_button", type="primary"):
                    st.session_state["select_area_editing"] = True
                    st.session_state["select_area_draft_crop_box"] = get_default_select_area_crop_box(image)
                    try:
                        st.rerun()
                    except Exception:
                        pass

        if st.session_state.get("select_area_editing"):
            st.stop()

    crop_extract_start = time.perf_counter()
    selected_image = crop_image_by_box(image, crop_box)
    crop_extraction_seconds = time.perf_counter() - crop_extract_start
    select_area_confirmed = area_mode == "Select Area" and st.session_state.get("select_area_confirmed_crop_box") is not None
    if select_area_confirmed:
        if crop_box != (0, 0, image.size[0], image.size[1]):
            with st.expander(t("preview_selected_area"), expanded=True):
                st.image(selected_image, caption=t("selected_area_sent_to_ocr"), use_container_width=True)
    working_image = selected_image

    ocr_resize_test = "1000 px"

    quality_errors, quality_warnings, quality_metrics = assess_image_quality(working_image)
    quality_level, quality_label, quality_message = get_quality_status(quality_errors, quality_warnings)
    localized_quality = {
        "good": (t("quality_good"), t("quality_good_msg")),
        "fair": (t("quality_fair"), t("quality_fair_msg")),
        "poor": (t("quality_poor"), t("quality_poor_msg")),
    }
    display_quality_label, display_quality_message = localized_quality.get(quality_level, (quality_label, quality_message))
    if quality_level == "good":
        st.success(f"{display_quality_label}\n\n{display_quality_message}")
    elif quality_level == "fair":
        st.warning(f"{display_quality_label}\n\n{display_quality_message}")
    else:
        st.error(f"{display_quality_label}\n\n{display_quality_message}")

    if DEBUG_MODE:
        with st.expander(t("show_details"), expanded=False):
            recommendation_text = t("quality_recommendation_check") if quality_errors or quality_warnings else t("quality_recommendation_good")
            detail_df = pd.DataFrame([
                {t("table_item"): t("resolution"), t("table_value"): f"{quality_metrics.get('width_px')} × {quality_metrics.get('height_px')} px"},
                {t("table_item"): t("sharpness"), t("table_value"): quality_metrics.get("sharpness_score")},
                {t("table_item"): t("contrast"), t("table_value"): quality_metrics.get("contrast_score")},
                {t("table_item"): t("recommendation"), t("table_value"): recommendation_text},
            ])
            st.dataframe(detail_df, use_container_width=True, hide_index=True)

    force_run = False
    if quality_errors:
        st.markdown(
            f"<div class='warning-box'>{t('quality_block_warning')}</div>",
            unsafe_allow_html=True,
        )
        force_run = st.checkbox(t("force_ocr"), value=False, key="force_ocr_checkbox")

    select_area_needs_confirmation = area_mode == "Select Area" and st.session_state.get("select_area_confirmed_crop_box") is None
    if select_area_needs_confirmation:
        st.info(t("select_area_required"))

    resize_max_side = 1400
    if ocr_resize_test != "Auto":
        resize_match = re.search(r"(\d+)", ocr_resize_test)
        resize_max_side = int(resize_match.group(1)) if resize_match else 1400
    experimental_downscale = max(working_image.size) > resize_max_side
    downscale_max_height_option = f"Max height {resize_max_side} px" if experimental_downscale else "Original / no resize"

    current_ocr_signature = build_ocr_input_signature(
        current_signature,
        source_mode,
        output_mode,
        area_mode,
        crop_box,
        extra_settings=(experimental_downscale, downscale_max_height_option, ocr_resize_test),
    )
    stored_ocr_signature = st.session_state.get("rc3_ocr_result_signature")
    if st.session_state.get("rc3_ocr_result") is not None and stored_ocr_signature != current_ocr_signature:
        st.session_state["rc3_ocr_result"] = None
        st.warning(t("settings_changed_rerun"))

    full_df = load_database()
    df = get_active_search_df(full_df)
    index = build_term_index(df, source_mode)
    all_term_index = build_all_term_index(df)
    df.attrs["all_term_index"] = all_term_index
    try:
        df.attrs["normalized_lookup_index"] = build_normalized_lookup_index(index, all_term_index, source_mode)
    except Exception as e:
        NORMALIZED_LOOKUP_INDEX_STATS["index_error"] = str(e)
        df.attrs["normalized_lookup_index"] = {}

    ocr_running = bool(st.session_state.get("ocr_running"))
    run_button_label = "⏳ OCR Running..." if ocr_running else t("run_ocr")
    st.button(
        run_button_label,
        key="run_ocr_overlay_translation_button",
        type="primary",
        disabled=ocr_running or select_area_needs_confirmation or (bool(quality_errors) and not force_run),
        on_click=request_ocr_run,
    )
    ocr_status_placeholder = st.empty()

    if st.session_state.get("pending_ocr_run"):
        last_click_rerun = st.session_state.get("rc10b_last_button_click_rerun")
        current_rerun = st.session_state.get("rc10b_rerun_count")
        rerun_delta = None
        if isinstance(last_click_rerun, int) and isinstance(current_rerun, int):
            rerun_delta = current_rerun - last_click_rerun
        st.session_state["rc10b_last_ocr_block_rerun_delta"] = rerun_delta
        rc10b_log_event(
            "Pending OCR block reached",
            current_rerun=current_rerun,
            last_click_rerun=last_click_rerun,
            reruns_between_click_and_ocr_block=rerun_delta,
        )
        ocr_status_placeholder.info("🔵 OCR started...")
        with st.spinner(t("running_ocr")):
            try:
                st.session_state["ocr_running"] = True
                st.session_state["ocr_started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                st.session_state["ocr_finished_at"] = None
                st.session_state["ocr_duration_seconds"] = None
                ocr_execution_start = time.perf_counter()
                rc10b_log_event(
                    "OCR started",
                    ocr_started_at=st.session_state.get("ocr_started_at"),
                )
                ocr_status_placeholder.warning("🟡 OCR running...")
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
                ocr_stage_start = time.perf_counter()
                candidate_result = run_primary_ocr(
                    ocr_input_image,
                    source_mode,
                    compare_easyocr=False,
                    trace=ocr_call_trace,
                    diagnostics=ocr_call_diagnostics,
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
                ocr_rows, removed_noise_df = filter_noise_and_watermarks(ocr_rows)
                raw_ocr_text = "\n".join(ocr_rows["text"].astype(str).tolist()) if ocr_rows is not None and not ocr_rows.empty else ""
                clean_text = clean_ocr_text(raw_ocr_text)
                cleanup_seconds = time.perf_counter() - cleanup_start
                runtime_profile["ocr_cleanup"] = cleanup_seconds
                timings["OCR cleanup"] = cleanup_seconds

                translation_profile = make_translation_profile()
                previous_translation_profile = TRANSLATION_PROFILE
                TRANSLATION_PROFILE = translation_profile
                try:
                    translation_start = time.perf_counter()
                    line_df = build_ocr_line_translations(ocr_rows, index, df, output_mode)
                    translation_seconds = time.perf_counter() - translation_start

                    overlay_start = time.perf_counter()
                    overlay_image, overlay_legend, overlay_legend_df = make_line_translation_overlay(working_image, line_df, output_mode)
                    overlay_seconds = time.perf_counter() - overlay_start

                    translation_start = time.perf_counter()
                    matches_df, unmatched = find_matches(clean_text, df, index)
                    readable_translation = build_readable_line_translation(line_df) if line_df is not None and not line_df.empty else ""
                    translation_seconds += time.perf_counter() - translation_start

                    png_start = time.perf_counter()
                    overlay_png = image_to_png_bytes(overlay_image) if overlay_image is not None else None
                    png_seconds = time.perf_counter() - png_start

                    txt_start = time.perf_counter()
                    translation_txt = build_overlay_export_text(line_df)
                    txt_seconds = time.perf_counter() - txt_start
                finally:
                    TRANSLATION_PROFILE = previous_translation_profile
                runtime_profile["translation"] = translation_seconds
                runtime_profile["overlay_generation"] = overlay_seconds
                runtime_profile["png_encoding"] = png_seconds
                runtime_profile["translation_txt_generation"] = txt_seconds
                timings["Translation processing"] = translation_seconds
                timings["Overlay generation"] = overlay_seconds
                timings["PNG encoding"] = png_seconds
                timings["Translation TXT generation"] = txt_seconds
                timings["Total runtime"] = image_load_seconds + crop_extraction_seconds + (time.perf_counter() - total_start)
                rc11c_translation_diagnostics = build_rc11c_translation_diagnostics(
                    translation_profile,
                    timings,
                    ocr_rows,
                    line_df,
                    overlay_legend_df,
                )
                rc11d_validation_diagnostics = build_rc11d_validation_diagnostics(
                    translation_profile,
                    rc11c_translation_diagnostics,
                )
                rc11e_normalization_diagnostics = build_rc11e_normalization_diagnostics(
                    translation_profile,
                    df,
                )
                rc11f_cache_diagnostics = build_rc11f_cache_diagnostics(
                    translation_profile,
                    timings,
                    readable_translation,
                )
                rc11g_lookup_index_diagnostics = build_rc11g_lookup_index_diagnostics(
                    translation_profile,
                    timings,
                    readable_translation,
                )
                ocr_workload_diagnostics = build_ocr_workload_diagnostics(
                    working_image,
                    detected_ocr_rows,
                    ocr_rows,
                    overlay_legend_df,
                )
                processing_total_before_status = image_load_seconds + crop_extraction_seconds + (time.perf_counter() - total_start)
                st.session_state["ocr_finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                st.session_state["ocr_duration_seconds"] = round(time.perf_counter() - ocr_execution_start, 3)
                st.session_state["ocr_running"] = False
                rc10b_log_event(
                    "OCR completed",
                    ocr_started_at=st.session_state.get("ocr_started_at"),
                    ocr_finished_at=st.session_state.get("ocr_finished_at"),
                    ocr_duration_seconds=st.session_state.get("ocr_duration_seconds"),
                )
                ocr_status_placeholder.success("🟢 OCR completed.")
                time.sleep(3)
                ocr_status_placeholder.empty()

                diagnostic_report_start = time.perf_counter()
                debug_report_txt = build_debug_report_text(
                    line_df,
                    overlay_legend,
                    clean_text=clean_text,
                    raw_text=raw_ocr_text,
                    source_mode=source_mode,
                    output_mode=output_mode,
                    area_mode=area_mode,
                    crop_box=crop_box,
                    matches_df=matches_df,
                    unmatched=unmatched,
                    ocr_engine=str(candidate_result.get("selected_name", "")),
                    image_quality_status=quality_label,
                    quality_metrics=quality_metrics,
                    session_diagnostics=rc10b_diagnostic_snapshot(),
                    events=st.session_state.get("rc10b_diagnostic_events", []),
                    timings=timings,
                    ocr_workload_diagnostics=ocr_workload_diagnostics,
                    ocr_box_rows=detected_ocr_rows,
                    ocr_call_diagnostics=ocr_call_diagnostics,
                    ocr_call_trace=ocr_call_trace,
                    downscale_diagnostics=downscale_diagnostics,
                    ocr_resize_test=ocr_resize_test,
                    interface_language=interface_language,
                    rc11c_translation_diagnostics=rc11c_translation_diagnostics,
                    rc11d_validation_diagnostics=rc11d_validation_diagnostics,
                    rc11e_normalization_diagnostics=rc11e_normalization_diagnostics,
                    rc11f_cache_diagnostics=rc11f_cache_diagnostics,
                    rc11g_lookup_index_diagnostics=rc11g_lookup_index_diagnostics,
                )
                diagnostic_report_seconds = time.perf_counter() - diagnostic_report_start
                runtime_profile["diagnostic_report_generation"] = diagnostic_report_seconds
                runtime_profile["total"] = processing_total_before_status + diagnostic_report_seconds
                timings["Diagnostic Report generation"] = diagnostic_report_seconds
                timings["Total runtime"] = float(runtime_profile["total"])
                debug_report_txt = "\n".join([
                    debug_report_txt.rstrip(),
                    "",
                    "=== Performance: Runtime Profile ===",
                    format_runtime_profile(runtime_profile),
                    "",
                ])
                st.session_state["rc3_ocr_result"] = {
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
                    "debug_report_txt": debug_report_txt,
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
                }
                st.session_state["rc3_ocr_result_signature"] = current_ocr_signature
                st.session_state["pending_ocr_run"] = False
                st.session_state["debug_report_ready"] = False
                st.session_state["last_successful_download_key"] = None
            except Exception as e:
                st.session_state["ocr_finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                st.session_state["ocr_duration_seconds"] = round(time.perf_counter() - ocr_execution_start, 3) if "ocr_execution_start" in locals() else None
                st.session_state["ocr_running"] = False
                rc10b_log_event(
                    "OCR failed",
                    ocr_started_at=st.session_state.get("ocr_started_at"),
                    ocr_finished_at=st.session_state.get("ocr_finished_at"),
                    ocr_duration_seconds=st.session_state.get("ocr_duration_seconds"),
                    error=str(e),
                )
                st.session_state["pending_ocr_run"] = False
                st.error(t("ocr_failed"))
                st.exception(e)
                st.stop()

    result = st.session_state.get("rc3_ocr_result")
    if result:
        overlay_image = result.get("overlay_image")
        overlay_png = result.get("overlay_png")
        line_df = result.get("line_df")
        readable_translation = result.get("readable_translation", "")
        overlay_legend = result.get("overlay_legend", "")
        overlay_legend_df = result.get("overlay_legend_df")
        raw_ocr_text = result.get("raw_ocr_text", "")
        clean_text = result.get("clean_text", "")
        ocr_rows = result.get("ocr_rows")
        removed_noise_df = result.get("removed_noise_df")
        matches_df = result.get("matches_df")
        unmatched = result.get("unmatched", [])
        saved_quality_metrics = result.get("quality_metrics", {})
        saved_quality_errors = result.get("quality_errors", [])
        saved_quality_warnings = result.get("quality_warnings", [])
        timings = result.get("timings", {})
        runtime_profile = result.get("runtime_profile", {})
        translation_profile = result.get("translation_profile", {})

        st.subheader(t("overlay_translation"))
        if overlay_image is not None:
            st.image(
                overlay_image,
                caption=t("overlay_caption"),
                use_container_width=True,
            )
            download_button_rc3(
                t("download_overlay"),
                data=overlay_png,
                file_name="crochet_ocr_overlay_translation.png",
                mime="image/png",
                key="download_overlay_png",
            )
        else:
            st.info(t("no_overlay"))

        st.subheader(t("line_translation"))
        if line_df is not None and not line_df.empty:
            st.text_area(t("translated_lines"), readable_translation, height=320)
            download_button_rc3(
                t("download_translation"),
                data=result.get("translation_txt", ""),
                file_name="crochet_translation.txt",
                mime="text/plain",
                key="download_overlay_translation_txt",
            )
        else:
            st.warning(t("no_ocr_lines"))

        st.subheader(t("report_problem"))
        st.markdown(t("report_intro"))
        st.markdown(f"<div class='report-action'>{html.escape(t('report_download_action'))}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='report-helper'>{html.escape(t('report_download_helper'))}</div>", unsafe_allow_html=True)
        download_button_rc3(
            t("download_debug_report"),
            data=result.get("debug_report_txt", ""),
            file_name=diagnostic_report_filename(),
            mime="text/plain",
            key="download_debug_report_txt",
            success_message=t("diagnostic_download_success"),
        )
        st.markdown(f"<div class='report-action'>{html.escape(t('report_feedback_action'))}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='report-helper'>{html.escape(t('report_feedback_helper'))}</div>", unsafe_allow_html=True)
        st.markdown(
            f"<a class='feedback-link' href='{html.escape(FEEDBACK_FORM_URL, quote=True)}' target='_blank' rel='noopener noreferrer'>{html.escape(t('send_feedback'))}</a>",
            unsafe_allow_html=True,
        )

        if DEBUG_MODE and timings:
            with st.expander("Debug timings", expanded=False):
                timing_df = pd.DataFrame(
                    [
                        {"Stage": stage, "Seconds": round(float(seconds), 3)}
                        for stage, seconds in timings.items()
                    ]
                )
                st.dataframe(timing_df, use_container_width=True, hide_index=True)
                profile_timings = translation_profile.get("timings", {}) if isinstance(translation_profile, dict) else {}
                profile_counts = translation_profile.get("counts", {}) if isinstance(translation_profile, dict) else {}
                if profile_timings:
                    st.markdown("**Translation sub-timings**")
                    profile_timing_df = pd.DataFrame(
                        [
                            {"Function / section": name, "Seconds": round(float(seconds), 3)}
                            for name, seconds in sorted(profile_timings.items(), key=lambda item: item[1], reverse=True)
                        ]
                    )
                    st.dataframe(profile_timing_df, use_container_width=True, hide_index=True)
                if profile_counts:
                    st.markdown("**Translation counters**")
                    profile_count_df = pd.DataFrame(
                        [
                            {"Counter": name, "Count": int(value) if float(value).is_integer() else round(float(value), 3)}
                            for name, value in sorted(profile_counts.items())
                        ]
                    )
                    st.dataframe(profile_count_df, use_container_width=True, hide_index=True)
else:
    pass

if DEBUG_MODE:
    render_rc10b_diagnostics()
