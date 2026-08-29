# ocr_prototype_v14.py
# Crochet Stitch Translator OCR Prototype v1.9m
# New in v2:
# - Reading layout: single column / two columns
# - Cleaner OCR text for crochet patterns
# - Round extraction and numeric sorting
# - Basic pattern interpretation for common amigurumi rows
# - Pattern normalization layer for common OCR round errors: bare 9:/10:/11:, Rs-R8, RI1, R1o
# Run from the repository root with:
# python3 -m streamlit run pattern_translator/app.py

import os
import io
import re
import html
import hashlib
import importlib.metadata as importlib_metadata
import math
import platform
import sys
import tempfile
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd
import streamlit as st
from PIL import Image
from crochet_intelligence.analytics import (
    WORKSHEET_PATTERN_TRANSLATION,
    ensure_analytics_session,
    get_session_translation_no,
    increment_session_translation_no,
    track_event as analytics_track_event,
)
from crochet_intelligence.plausible_bridge import (
    emit_plausible_event,
    mount_plausible_bridge,
    plausible_link_button,
    stage_plausible_event,
)
from pattern_translator.components.custom_upload import (
    custom_image_uploader,
    restore_uploaded_image,
    snapshot_uploaded_image,
)
from pattern_translator.components.custom_cropper import custom_select_area
from pattern_translator.engine import terminology as terminology_engine
from pattern_translator.engine import line_translation as line_translation_engine
from pattern_translator.engine import overlay as overlay_engine
from pattern_translator.engine import pattern_document as pattern_document_engine
from pattern_translator.engine import ocr_lines as ocr_lines_engine
from pattern_translator.engine import ocr_cleanup as ocr_cleanup_engine
from pattern_translator.engine import ocr_runtime as ocr_runtime_engine
from pattern_translator.engine import result_delivery as result_delivery_engine
from pattern_translator.engine import (
    translation_language_state as translation_language_state_engine,
)
from pattern_translator.engine import (
    translation_area_state as translation_area_state_engine,
)
from pattern_translator.engine import (
    ocr_request_lifecycle as ocr_request_lifecycle_engine,
)
from pattern_translator.engine import llm_fallback as llm_fallback_engine
from pattern_translator.translation_service import (
    CSV_TERM_CACHE_STATS,
    NORMALIZED_LOOKUP_INDEX_STATS,
    TranslateImageRequest,
    assess_image_quality,
    get_quality_status,
    log_app_ocr_timing,
    prepare_translation_dataframe,
    translate_image,
)

APP_VERSION = "Pattern OCR Translator (Beta RC26)"
APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
KNOWLEDGE_BASE_DIR = REPO_ROOT / "knowledge_base"
SOURCE_CSV = KNOWLEDGE_BASE_DIR / "data" / "master_stitches.csv"
FALLBACK_CSV = KNOWLEDGE_BASE_DIR / "releases" / "database" / "stitches_1_8e.csv"
DEBUG_MODE = os.getenv("CROCHET_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
FEEDBACK_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScoDrN0xsyOg800O8Pw7aXAa5GREQIU-RmxlmXIlBOE7y_Q_w/viewform"
DEFAULT_PORTAL_URL = "https://crochetintelligence.com"
PORTAL_URL = os.getenv("CROCHET_INTELLIGENCE_PORTAL_URL", DEFAULT_PORTAL_URL).strip() or DEFAULT_PORTAL_URL
SELECT_AREA_PREVIEW_WIDTH = 360

st.set_page_config(page_title="Crochet Pattern Translator", page_icon="🧶", layout="centered")

st.markdown(
    """
<style>
:root {
    --ci-teal-700: #0F766E;
    --ci-teal-600: #13867D;
    --ci-teal-100: #DDEDEA;
    --ci-teal-050: #EAF4F2;
    --ci-terracotta-700: #C2613F;
    --ci-terracotta-500: #D97A5A;
    --ci-terracotta-100: #F6E8E3;
    --ci-bg: #FAF9F7;
    --ci-surface: #FFFFFF;
    --ci-surface-subtle: #F2EEE9;
    --ci-border: #E7E3DE;
    --ci-text-primary: #1E1E20;
    --ci-text-secondary: #55565A;
    --ci-text-muted: #8A8D91;
    --ci-text-on-primary: #FFFFFF;
    --ci-primary: #0F766E;
    --ci-primary-hover: #13867D;
    --ci-primary-soft: #DDEDEA;
    --ci-success: #2E7D5B;
    --ci-warning: #D99A24;
    --ci-error: #D64545;
    --ci-info: #3A7BD5;
    --ci-focus-ring: rgba(15, 118, 110, 0.28);
    --ci-font: "Noto Sans TC", "Noto Sans SC", "Noto Sans JP", "Noto Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    --ci-radius-sm: 8px;
    --ci-radius-md: 12px;
    --ci-radius-lg: 16px;
    --ci-shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
}

html, body, .stApp {
    font-family: var(--ci-font);
    letter-spacing: 0;
}

body, .stApp, [data-testid="stAppViewContainer"] {
    background: var(--ci-bg);
    color: var(--ci-text-primary);
}

.block-container {
    width: 100%;
    max-width: 720px;
    margin: 0 auto;
    padding: 24px 20px 32px;
}

h1, h2, h3 { color: var(--ci-text-primary) !important; }
h1 {
    color: var(--ci-teal-700) !important;
    font-size: 30px !important;
    line-height: 36px !important;
    font-weight: 700 !important;
    margin: 0 !important;
    padding: 20px 0 4px !important;
}
h2 {
    font-size: 22px !important;
    line-height: 28px !important;
    font-weight: 600 !important;
}
h3 {
    font-size: 18px !important;
    line-height: 26px !important;
    font-weight: 600 !important;
}
h1 a[href^="#"], h1 .anchor-link { display: none !important; }
h1 + div[data-testid="stCaptionContainer"] { margin-top: 0; }
div[data-testid="stCaptionContainer"] {
    color: var(--ci-text-muted);
    font-size: 14px;
    line-height: 20px;
    margin-bottom: 8px;
    opacity: 1;
}
p, label, li { line-height: 24px; }
.product-kicker {
    margin: 16px 0 0;
    color: var(--ci-primary);
    font-size: 14px;
    line-height: 20px;
    font-weight: 600;
}
.small-note {
    color: var(--ci-text-secondary);
    font-size: 14px;
    line-height: 20px;
    margin: 4px 0 8px;
}
.warning-box {
    border: 1px solid rgba(217, 154, 36, 0.42);
    border-radius: var(--ci-radius-md);
    padding: 12px 16px;
    background: rgba(217, 154, 36, 0.09);
    color: var(--ci-text-primary);
    font-size: 14px;
    line-height: 21px;
}
.good-box {
    border: 1px solid rgba(46, 125, 91, 0.34);
    border-radius: var(--ci-radius-md);
    padding: 12px 16px;
    background: rgba(46, 125, 91, 0.08);
}
div[data-testid="stExpander"] { margin-bottom: 8px; }
div[data-testid="stExpander"] details {
    border: 1px solid var(--ci-border);
    border-radius: var(--ci-radius-md);
    background: var(--ci-surface);
    box-shadow: var(--ci-shadow-sm);
    overflow: hidden;
}
div[data-testid="stExpander"] summary {
    min-height: 56px;
    padding: 0 16px;
    color: var(--ci-text-primary);
    font-size: 16px;
    font-weight: 500;
}
div[data-testid="stExpander"] div[data-testid="stMarkdownContainer"] p { margin-bottom: 8px; }
div[data-testid="stExpander"] div[data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
div[data-testid="stVerticalBlock"] > div { gap: 8px; }
div[data-testid="stSelectbox"], div[data-testid="stRadio"] { margin-bottom: 4px; }
div[data-testid="stHorizontalBlock"] div[data-testid="stSelectbox"] { margin-bottom: 0; }
div[data-testid="stHorizontalBlock"] div[data-testid="stSelectbox"] label { min-height: 0; }

div[data-baseweb="select"] > div,
div[role="radiogroup"] label,
div[data-testid="stTextArea"] textarea,
div[data-testid="stTextInput"] input {
    border-color: var(--ci-border);
    border-radius: var(--ci-radius-md);
    background: var(--ci-surface);
    color: var(--ci-text-primary);
}

label[data-testid="stWidgetLabel"],
label[data-testid="stWidgetLabel"] p,
div[role="radiogroup"] label,
div[role="radiogroup"] label p,
div[data-testid="stCheckbox"] label,
div[data-testid="stCheckbox"] label p,
div[data-baseweb="select"] [value] {
    color: var(--ci-text-primary) !important;
}

[role="listbox"] {
    border-color: var(--ci-border) !important;
    background: var(--ci-surface) !important;
}

[role="listbox"] [role="option"] {
    color: var(--ci-text-primary) !important;
}

[role="listbox"] [role="option"][aria-selected="true"] {
    background: var(--ci-surface-subtle) !important;
}

button:focus-visible,
a:focus-visible,
textarea:focus-visible,
summary:focus-visible,
[role="radio"]:focus-visible,
div[data-testid="stTextInput"] input:focus-visible {
    outline: 3px solid var(--ci-focus-ring) !important;
    outline-offset: 2px !important;
}

div[data-baseweb="select"]:focus-within > div {
    outline: 3px solid var(--ci-focus-ring) !important;
    outline-offset: 2px !important;
}

div[data-testid="stButton"] > button,
div[data-testid="stDownloadButton"] > button,
div[data-testid="stLinkButton"] > a {
    min-height: 52px;
    padding: 0 20px;
    border: 1px solid var(--ci-primary);
    border-radius: var(--ci-radius-md);
    background: transparent;
    color: var(--ci-primary);
    font-size: 16px;
    line-height: 24px;
    font-weight: 600;
    box-shadow: none;
}

div[data-testid="stButton"] > button[kind="primary"] {
    min-height: 56px;
    padding: 0 24px;
    border-color: var(--ci-primary);
    background: var(--ci-primary);
    color: var(--ci-text-on-primary);
    font-size: 17px;
}

@media (hover: hover) and (pointer: fine) {
    div[data-testid="stButton"] > button:hover,
    div[data-testid="stDownloadButton"] > button:hover,
    div[data-testid="stLinkButton"] > a:hover {
        border-color: var(--ci-primary-hover);
        background: var(--ci-primary-soft);
        color: var(--ci-primary-hover);
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover {
        border-color: var(--ci-primary-hover);
        background: var(--ci-primary-hover);
        color: var(--ci-text-on-primary);
    }
}

div[data-testid="stButton"] > button:active,
div[data-testid="stDownloadButton"] > button:active,
div[data-testid="stLinkButton"] > a:active {
    transform: translateY(1px);
}

div[data-testid="stAlert"] {
    border-radius: var(--ci-radius-md);
}

div[data-testid="stImage"] img {
    border-radius: var(--ci-radius-sm);
}
.report-action {
    color: var(--ci-text-primary);
    font-size: 16px;
    line-height: 24px;
    font-weight: 600;
    margin: 16px 0 4px;
}
.report-helper {
    color: var(--ci-text-muted);
    font-size: 14px;
    line-height: 20px;
    margin: 0 0 8px 20px;
}
.feedback-link {
    display: inline-block;
    min-height: 52px;
    line-height: 50px;
    padding: 0 20px;
    border: 1px solid var(--ci-primary);
    border-radius: var(--ci-radius-md);
    color: var(--ci-primary) !important;
    text-decoration: none !important;
    font-weight: 600;
    margin-top: 4px;
}
.feedback-link:hover {
    border-color: var(--ci-primary-hover);
    background: var(--ci-primary-soft);
    color: var(--ci-primary-hover) !important;
    text-decoration: none !important;
}

@media (max-width: 640px) {
    .block-container { padding: 24px 20px 32px; }
    div[data-testid="stHorizontalBlock"] { gap: 8px; }
}

@media (max-width: 359px) {
    .block-container { padding-left: 16px; padding-right: 16px; }
}

@media (min-width: 768px) {
    .block-container { padding-left: 32px; padding-right: 32px; }
}

@media (prefers-color-scheme: dark) {
    :root {
        --ci-bg: #17191A;
        --ci-surface: #202426;
        --ci-surface-subtle: #292D2F;
        --ci-border: #434A4D;
        --ci-text-primary: #F4F3F1;
        --ci-text-secondary: #C9C7C3;
        --ci-text-muted: #999C9D;
        --ci-text-on-primary: #FFFFFF;
        --ci-primary: #2F928A;
        --ci-primary-hover: #3AA49B;
        --ci-primary-soft: #213B39;
        --ci-focus-ring: rgba(47, 146, 138, 0.34);
        --ci-shadow-sm: none;
    }
    h1 { color: var(--ci-primary) !important; }
    .warning-box { background: rgba(217, 154, 36, 0.12); }
}

@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        scroll-behavior: auto !important;
        transition-duration: 0.01ms !important;
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
    }
}
</style>
""",
    unsafe_allow_html=True,
)

active_theme_type = getattr(st.context.theme, "type", "light")
configured_theme_base = st.get_option("theme.base")
if active_theme_type == "dark" or configured_theme_base == "dark":
    st.markdown(
        """
<style>
:root {
    --ci-bg: #17191A;
    --ci-surface: #202426;
    --ci-surface-subtle: #292D2F;
    --ci-border: #434A4D;
    --ci-text-primary: #F4F3F1;
    --ci-text-secondary: #C9C7C3;
    --ci-text-muted: #999C9D;
    --ci-text-on-primary: #FFFFFF;
    --ci-primary: #2F928A;
    --ci-primary-hover: #3AA49B;
    --ci-primary-soft: #213B39;
    --ci-focus-ring: rgba(47, 146, 138, 0.34);
    --ci-shadow-sm: none;
}
h1 { color: var(--ci-primary) !important; }
.warning-box { background: rgba(217, 154, 36, 0.12); }
</style>
""",
        unsafe_allow_html=True,
    )

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

@st.cache_data
def build_term_index(df: pd.DataFrame, source_mode: str) -> Dict[str, int]:
    return terminology_engine.build_term_index(df, source_mode)


@st.cache_data
def build_all_term_index(df: pd.DataFrame) -> Dict[str, int]:
    return terminology_engine.build_all_term_index(df)


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
        "app_title": "Crochet Pattern Translator",
        "app_subtitle": "Pattern OCR Translator (Beta)",
        "back_to_portal": "Back to Crochet Intelligence",
        "ai_translation_note": "AI may assist with unresolved instruction text. Crochet terminology and pattern structure are handled conservatively. Designer shorthand varies; check results against the original pattern and the designer's stitch key.",
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
        "upload_instruction": "Choose a pattern image",
        "upload_choose": "Choose image",
        "upload_drop_hint": "Or drag and drop an image here",
        "upload_drop_active": "Drop the image here",
        "upload_reading": "Reading image…",
        "upload_selected": "Selected image",
        "upload_replace": "Replace",
        "upload_remove": "Remove",
        "upload_error_unsupported": "This file cannot be used. Please choose a JPG, JPEG, PNG or WebP image from your Camera, Photos or Files.",
        "upload_error_empty": "This file is empty. Please choose another image.",
        "upload_error_too_large": "This image is too large. Please choose an image smaller than 25 MB.",
        "upload_error_unreadable": "This file could not be read. Please choose another image.",
        "upload_error_invalid": "This file is not a valid image. Please choose a JPG, JPEG, PNG or WebP image.",
        "original_image": "Original image",
        "translation_area": "Translation area",
        "translation_area_tip": "💡 Select Area is optional and experimental. Use it when you need to translate only part of an image.",
        "area_label": "Area to Translate",
        "area_select": "Select Area",
        "area_left": "Left Column",
        "area_right": "Right Column",
        "area_whole": "Whole Pattern",
        "cropper_missing": "Direct drag selection needs the optional package `streamlit-cropper`. Until installed, this version falls back to presets or sliders.",
        "cropper_drag": "Drag the rectangle around the text you want translated.\n\nUse the Precision Pad to fine-tune the highlighted border.",
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
        "select_area_cancel": "Start Over",
        "select_area_reset": "Reset",
        "select_area_image_alt": "Crochet pattern image for area selection",
        "select_area_selection_label": "Selected translation area",
        "select_area_move_controller": "Move precision controls",
        "select_area_move_up": "Adjust top edge upward",
        "select_area_move_down": "Adjust bottom edge downward",
        "select_area_move_left": "Adjust left edge outward",
        "select_area_move_right": "Adjust right edge outward",
        "select_area_adjust_top_up": "Move top edge upward",
        "select_area_adjust_top_down": "Move top edge downward",
        "select_area_adjust_bottom_up": "Move bottom edge upward",
        "select_area_adjust_bottom_down": "Move bottom edge downward",
        "select_area_adjust_left_left": "Move left edge left",
        "select_area_adjust_left_right": "Move left edge right",
        "select_area_adjust_right_left": "Move right edge left",
        "select_area_adjust_right_right": "Move right edge right",
        "select_area_resize_top": "Resize top edge",
        "select_area_resize_bottom": "Resize bottom edge",
        "select_area_resize_left": "Resize left edge",
        "select_area_resize_right": "Resize right edge",
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
        "no_crochet_pattern_title": "No crochet pattern was detected.",
        "no_crochet_pattern_body": "The text in this image was recognised successfully, but no crochet terms were found. Please upload a crochet pattern instead of a general photo or document.",
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
        "debug_report_failed": "The Diagnostic Report could not be generated. Your translation is still available.",
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
        "back_to_portal": "返回 Crochet Intelligence",
        "ai_translation_note": "AI 可能協助翻譯尚未解決的指示文字。鈎織術語及圖樣結構會以保守方式處理。不同設計師的簡寫可能不同，請對照原圖樣及設計師的針法說明。",
        "intro": "上載鈎織圖樣圖片，取得圖片標示翻譯及逐行翻譯。",
        "app_title": "鈎織翻譯器",
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
        "upload_instruction": "選擇要翻譯的圖樣圖片",
        "upload_choose": "選擇圖片",
        "upload_drop_hint": "或將圖片拖放到這裡",
        "upload_drop_active": "將圖片放到這裡",
        "upload_reading": "正在讀取圖片……",
        "upload_selected": "已選圖片",
        "upload_replace": "更換",
        "upload_remove": "移除",
        "upload_error_unsupported": "這個檔案無法使用。請從相機、相片或檔案選擇 JPG、JPEG、PNG 或 WebP 圖片。",
        "upload_error_empty": "這個檔案沒有內容。請選擇另一張圖片。",
        "upload_error_too_large": "圖片太大。請選擇小於 25 MB 的圖片。",
        "upload_error_unreadable": "無法讀取這個檔案。請選擇另一張圖片。",
        "upload_error_invalid": "這個檔案不是有效的圖片。請選擇 JPG、JPEG、PNG 或 WebP 圖片。",
        "original_image": "原始圖片",
        "translation_area": "翻譯範圍",
        "translation_area_tip": "💡 選取範圍是選用的實驗功能。需要只翻譯圖片的一部分時可以使用。",
        "area_label": "要翻譯的範圍",
        "area_select": "選取範圍",
        "area_left": "左欄",
        "area_right": "右欄",
        "area_whole": "整個圖樣",
        "cropper_missing": "拖拉選取範圍需要額外套件 `streamlit-cropper`。未安裝時，會改用預設範圍或滑桿。",
        "cropper_drag": "請拖拉方框，框住要翻譯的文字。\n\n使用精細調整控制器微調反白顯示的邊界。",
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
        "select_area_cancel": "重新選取",
        "select_area_reset": "重設",
        "select_area_image_alt": "用於選取範圍的鈎織圖樣圖片",
        "select_area_selection_label": "已選翻譯範圍",
        "select_area_move_controller": "移動精細調整控制器",
        "select_area_move_up": "向上微調上邊界",
        "select_area_move_down": "向下微調下邊界",
        "select_area_move_left": "向外微調左邊界",
        "select_area_move_right": "向外微調右邊界",
        "select_area_adjust_top_up": "向上移動上邊界",
        "select_area_adjust_top_down": "向下移動上邊界",
        "select_area_adjust_bottom_up": "向上移動下邊界",
        "select_area_adjust_bottom_down": "向下移動下邊界",
        "select_area_adjust_left_left": "向左移動左邊界",
        "select_area_adjust_left_right": "向右移動左邊界",
        "select_area_adjust_right_left": "向左移動右邊界",
        "select_area_adjust_right_right": "向右移動右邊界",
        "select_area_resize_top": "調整上邊界",
        "select_area_resize_bottom": "調整下邊界",
        "select_area_resize_left": "調整左邊界",
        "select_area_resize_right": "調整右邊界",
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
        "no_crochet_pattern_title": "未找到可翻譯的鈎織術語。",
        "no_crochet_pattern_body": "圖片中的文字已成功辨識，但沒有找到可翻譯的鈎織圖樣內容。請確認你上傳的是鈎織圖樣，而不是一般圖片或其他文件。",
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
        "debug_report_failed": "無法產生診斷報告。你的翻譯結果仍然可用。",
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
        "back_to_portal": "返回 Crochet Intelligence",
        "ai_translation_note": "AI 可能协助翻译尚未解决的指示文字。钩织术语及图样结构会以保守方式处理。不同设计师的简写可能不同，请对照原图样及设计师的针法说明。",
        "intro": "上传钩织图样图片，获得图片标示翻译和逐行翻译。",
        "app_title": "钩织翻译器",
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
        "upload_instruction": "选择要翻译的图样图片",
        "upload_choose": "选择图片",
        "upload_drop_hint": "或将图片拖放到这里",
        "upload_drop_active": "将图片放到这里",
        "upload_reading": "正在读取图片……",
        "upload_selected": "已选图片",
        "upload_replace": "更换",
        "upload_remove": "移除",
        "upload_error_unsupported": "这个文件无法使用。请从相机、照片或文件选择 JPG、JPEG、PNG 或 WebP 图片。",
        "upload_error_empty": "这个文件没有内容。请选择另一张图片。",
        "upload_error_too_large": "图片太大。请选择小于 25 MB 的图片。",
        "upload_error_unreadable": "无法读取这个文件。请选择另一张图片。",
        "upload_error_invalid": "这个文件不是有效的图片。请选择 JPG、JPEG、PNG 或 WebP 图片。",
        "original_image": "原始图片",
        "translation_area": "翻译范围",
        "translation_area_tip": "💡 选取范围是选用的实验功能。需要只翻译图片的一部分时可以使用。",
        "area_label": "要翻译的范围",
        "area_select": "选取范围",
        "area_left": "左栏",
        "area_right": "右栏",
        "area_whole": "整个图样",
        "cropper_missing": "拖拉选取范围需要额外套件 `streamlit-cropper`。未安装时，会改用默认范围或滑杆。",
        "cropper_drag": "请拖拉方框，框住要翻译的文字。\n\n使用精细调整控制器微调高亮显示的边界。",
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
        "select_area_cancel": "重新选择",
        "select_area_reset": "重置",
        "select_area_image_alt": "用于选取范围的钩织图样图片",
        "select_area_selection_label": "已选翻译范围",
        "select_area_move_controller": "移动精细调整控制器",
        "select_area_move_up": "向上微调上边界",
        "select_area_move_down": "向下微调下边界",
        "select_area_move_left": "向外微调左边界",
        "select_area_move_right": "向外微调右边界",
        "select_area_adjust_top_up": "向上移动上边界",
        "select_area_adjust_top_down": "向下移动上边界",
        "select_area_adjust_bottom_up": "向上移动下边界",
        "select_area_adjust_bottom_down": "向下移动下边界",
        "select_area_adjust_left_left": "向左移动左边界",
        "select_area_adjust_left_right": "向右移动左边界",
        "select_area_adjust_right_left": "向左移动右边界",
        "select_area_adjust_right_right": "向右移动右边界",
        "select_area_resize_top": "调整上边界",
        "select_area_resize_bottom": "调整下边界",
        "select_area_resize_left": "调整左边界",
        "select_area_resize_right": "调整右边界",
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
        "no_crochet_pattern_title": "未找到可翻译的钩织术语。",
        "no_crochet_pattern_body": "图片中的文字已成功识别，但没有找到可翻译的钩织图样内容。请确认你上传的是钩织图样，而不是一般图片或其他文件。",
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
        "debug_report_failed": "无法生成诊断报告。你的翻译结果仍然可用。",
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
        "back_to_portal": "Crochet Intelligence に戻る",
        "ai_translation_note": "AIが未解決の指示文の翻訳を補助する場合があります。かぎ針編み用語とパターン構造は慎重に保持されます。デザイナー独自の略語は異なるため、元のパターンとデザイナーのステッチキーをご確認ください。",
        "intro": "かぎ針編みパターン画像をアップロードして、画像上の翻訳と行ごとの翻訳を確認できます。",
        "app_title": "かぎ針編み翻訳",
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
        "upload_instruction": "翻訳するパターン画像を選んでください",
        "upload_choose": "画像を選択",
        "upload_drop_hint": "または画像をここにドラッグ＆ドロップ",
        "upload_drop_active": "画像をここにドロップ",
        "upload_reading": "画像を読み込んでいます……",
        "upload_selected": "選択した画像",
        "upload_replace": "変更",
        "upload_remove": "削除",
        "upload_error_unsupported": "このファイルは使用できません。カメラ、写真、またはファイルから JPG、JPEG、PNG、WebP の画像を選んでください。",
        "upload_error_empty": "このファイルは空です。別の画像を選んでください。",
        "upload_error_too_large": "画像が大きすぎます。25 MB 未満の画像を選んでください。",
        "upload_error_unreadable": "このファイルを読み込めませんでした。別の画像を選んでください。",
        "upload_error_invalid": "このファイルは有効な画像ではありません。JPG、JPEG、PNG、WebP の画像を選んでください。",
        "original_image": "元の画像",
        "translation_area": "翻訳する範囲",
        "translation_area_tip": "💡 範囲選択は任意の実験的な機能です。画像の一部だけを翻訳したい場合に使用してください。",
        "area_label": "翻訳する範囲",
        "area_select": "範囲を選択",
        "area_left": "左の列",
        "area_right": "右の列",
        "area_whole": "パターン全体",
        "cropper_missing": "ドラッグ選択には追加パッケージ `streamlit-cropper` が必要です。未導入の場合は、プリセットまたはスライダーを使用します。",
        "cropper_drag": "翻訳したい文字を囲むように四角をドラッグしてください。\n\n微調整コントローラーを使って、強調表示された境界線を細かく調整してください。",
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
        "select_area_cancel": "選び直す",
        "select_area_reset": "リセット",
        "select_area_image_alt": "範囲選択用のかぎ針編みパターン画像",
        "select_area_selection_label": "選択した翻訳範囲",
        "select_area_move_controller": "微調整コントローラーを移動",
        "select_area_move_up": "上端を上へ微調整",
        "select_area_move_down": "下端を下へ微調整",
        "select_area_move_left": "左端を外側へ微調整",
        "select_area_move_right": "右端を外側へ微調整",
        "select_area_adjust_top_up": "上端を上へ移動",
        "select_area_adjust_top_down": "上端を下へ移動",
        "select_area_adjust_bottom_up": "下端を上へ移動",
        "select_area_adjust_bottom_down": "下端を下へ移動",
        "select_area_adjust_left_left": "左端を左へ移動",
        "select_area_adjust_left_right": "左端を右へ移動",
        "select_area_adjust_right_left": "右端を左へ移動",
        "select_area_adjust_right_right": "右端を右へ移動",
        "select_area_resize_top": "上端を調整",
        "select_area_resize_bottom": "下端を調整",
        "select_area_resize_left": "左端を調整",
        "select_area_resize_right": "右端を調整",
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
        "no_crochet_pattern_title": "翻訳できるかぎ針編み用語が見つかりませんでした。",
        "no_crochet_pattern_body": "画像内の文字は認識されましたが、翻訳可能なかぎ針編みパターンの内容は見つかりませんでした。一般的な写真やその他の文書ではなく、かぎ針編みパターンをアップロードしていることをご確認ください。",
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
        "debug_report_failed": "診断レポートを生成できませんでした。翻訳結果は引き続き利用できます。",
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


def _result_request_id() -> str:
    lifecycle = st.session_state.get("ocr_request_lifecycle")
    if isinstance(lifecycle, dict) and lifecycle.get("request_id"):
        return str(lifecycle["request_id"])
    result = st.session_state.get("rc3_ocr_result")
    if isinstance(result, dict) and result.get("diagnostic_request_id"):
        return str(result["diagnostic_request_id"])
    return "none"


def _result_lifecycle_state() -> str:
    lifecycle = st.session_state.get("ocr_request_lifecycle")
    if isinstance(lifecycle, dict):
        return str(lifecycle.get("state") or "none")
    return "none"


def _safe_area_mode(value: object = None) -> str:
    area_mode = value or st.session_state.get("translation_area_mode_radio")
    return {
        "Whole Pattern": "whole_pattern",
        "Select Area": "select_area",
    }.get(str(area_mode or ""), "unavailable")


def log_result_state_event(
    phase: str,
    *,
    action: str = "",
    reason: str = "",
    uploader_event: str = "",
    area_mode: object = None,
    select_area_editing: Optional[bool] = None,
    crop_confirmed: Optional[bool] = None,
    stored_signature_present: Optional[bool] = None,
    current_signature_present: Optional[bool] = None,
    signature_match: Optional[bool] = None,
    mismatch_fields: Tuple[str, ...] = (),
    callback_receipt: bool = False,
) -> None:
    """Record content-free result state without mutating application state."""
    try:
        script_run_no = int(st.session_state.get("rc10b_rerun_count", 0) or 0)
        if callback_receipt:
            # Callbacks run before the corresponding top-to-bottom script run.
            script_run_no += 1
        accepted_generation = int(
            st.session_state.get("rc3_upload_generation", 0) or 0
        )
        result_delivery_engine.log_result_state(
            _result_request_id(),
            phase,
            session_generation=str(
                st.session_state.get("diagnostic_session_generation")
                or "unavailable"
            ),
            script_run_no=script_run_no,
            lifecycle=_result_lifecycle_state(),
            result_present=st.session_state.get("rc3_ocr_result") is not None,
            active_image=st.session_state.get("rc3_active_image_upload") is not None,
            accepted_upload_generation=accepted_generation,
            action=action,
            reason=reason,
            uploader_event=uploader_event,
            area_mode=_safe_area_mode(area_mode),
            select_area_editing=select_area_editing,
            crop_confirmed=crop_confirmed,
            stored_signature_present=stored_signature_present,
            current_signature_present=current_signature_present,
            signature_match=signature_match,
            mismatch_fields=mismatch_fields,
        )
    except Exception:
        # Diagnostics must never change product behavior.
        return


def download_button_rc3(
    label: str,
    data: object,
    file_name: str,
    mime: str,
    key: str,
    success_message: Optional[str] = None,
    analytics_event_type: Optional[str] = None,
    plausible_event_name: Optional[str] = None,
    prevent_rerun: bool = False,
    diagnostic_action: str = "",
):
    """Render a download button and show a shared public confirmation after click."""
    def mark_download_complete(download_key: str = key) -> None:
        if diagnostic_action:
            log_result_state_event(
                "post_result_action_received",
                action=diagnostic_action,
                callback_receipt=True,
            )
        st.session_state["last_successful_download_key"] = download_key
        if analytics_event_type:
            try:
                track_analytics_event(analytics_event_type)
            except Exception as exc:
                print(f"[analytics] download event failed: {exc}")
        if plausible_event_name:
            stage_plausible_event(st.session_state, plausible_event_name)

    try:
        clicked = st.download_button(
            label,
            data=data,
            file_name=file_name,
            mime=mime,
            key=key,
            on_click="ignore" if prevent_rerun else mark_download_complete,
        )
    except TypeError:
        # Older Streamlit fallback. Results are still preserved by session_state.
        clicked = st.download_button(
            label,
            data=data,
            file_name=file_name,
            mime=mime,
            key=key,
            on_click="ignore" if prevent_rerun else mark_download_complete,
        )
    if not prevent_rerun and st.session_state.get("last_successful_download_key") == key:
        try:
            default_success = t("download_success")
        except Exception:
            default_success = INTERFACE_LANGUAGES["English"]["download_success"]
        st.success(success_message or default_success)
    return clicked


def init_rc3_state():
    st.session_state.setdefault("rc3_ocr_result", None)
    st.session_state.setdefault("rc3_image_signature", None)
    st.session_state.setdefault("rc3_uploaded_image_name", "")
    st.session_state.setdefault("rc3_active_image_upload", None)
    st.session_state.setdefault("rc3_upload_generation", 0)
    st.session_state.setdefault("rc3_ocr_result_signature", None)
    st.session_state.setdefault("pending_ocr_run", False)
    st.session_state.setdefault("latest_crop_box", None)
    st.session_state.setdefault("select_area_confirmed_crop_box", None)
    st.session_state.setdefault("select_area_editing", False)
    st.session_state.setdefault("select_area_draft_crop_box", None)
    st.session_state.setdefault("select_area_display_proxy_diagnostics", {})
    st.session_state.setdefault("select_area_last_component_action_id", None)
    st.session_state.setdefault("select_area_edit_session_no", 0)
    st.session_state.setdefault("select_area_last_area_mode", None)
    st.session_state.setdefault("select_area_start_over_pending", False)
    st.session_state.setdefault("ocr_running", False)
    st.session_state.setdefault("ocr_started_at", None)
    st.session_state.setdefault("ocr_finished_at", None)
    st.session_state.setdefault("ocr_duration_seconds", None)
    st.session_state.setdefault("duplicate_ocr_run_ignored_count", 0)
    st.session_state.setdefault("debug_report_ready", False)
    st.session_state.setdefault("last_successful_download_key", None)
    st.session_state.setdefault("pending_plausible_v2_event", None)
    st.session_state.setdefault("rc10b_diagnostic_events", [])
    st.session_state.setdefault("rc10b_image_signature_history", [])
    st.session_state.setdefault("rc10b_last_image_present", False)
    st.session_state.setdefault("rc10b_last_image_signature", None)
    st.session_state.setdefault("rc10b_rerun_count", 0)
    st.session_state.setdefault("rc10b_run_button_click_count", 0)
    st.session_state.setdefault("rc10b_last_button_click_rerun", None)
    st.session_state.setdefault("rc10b_last_ocr_block_rerun_delta", None)
    st.session_state.setdefault("rc10b_last_cropper_box", None)
    st.session_state.setdefault("ocr_timing_request_id", None)
    st.session_state.setdefault("ocr_timing_action_started", None)
    st.session_state.setdefault("ocr_request_lifecycle", None)
    st.session_state.setdefault("diagnostic_session_generation", uuid.uuid4().hex)


def request_ocr_run():
    if (
        st.session_state.get("pending_ocr_run")
        or st.session_state.get("ocr_running")
        or ocr_request_lifecycle_engine.is_active(
            st.session_state.get("ocr_request_lifecycle")
        )
    ):
        st.session_state["duplicate_ocr_run_ignored_count"] = st.session_state.get("duplicate_ocr_run_ignored_count", 0) + 1
        rc10b_log_event(
            "Run OCR request ignored because OCR already running",
            duplicate_ocr_run_ignored_count=st.session_state.get("duplicate_ocr_run_ignored_count"),
        )
        return
    diagnostic_request_id = uuid.uuid4().hex
    action_started = time.perf_counter()
    st.session_state["ocr_timing_request_id"] = diagnostic_request_id
    st.session_state["ocr_timing_action_started"] = action_started
    st.session_state["ocr_request_lifecycle"] = (
        ocr_request_lifecycle_engine.new_request(diagnostic_request_id)
    )
    st.session_state["rc10b_run_button_click_count"] = st.session_state.get("rc10b_run_button_click_count", 0) + 1
    st.session_state["rc10b_last_button_click_rerun"] = st.session_state.get("rc10b_rerun_count")
    st.session_state["pending_ocr_run"] = True
    log_app_ocr_timing(
        diagnostic_request_id,
        "translation_action_accepted",
        session_generation=str(
            st.session_state.get("diagnostic_session_generation") or "unavailable"
        ),
        request_lifecycle="pending",
        active_image=st.session_state.get("rc3_active_image_upload") is not None,
    )
    rc10b_log_event(
        "Run OCR button clicked",
        run_button_click_count=st.session_state.get("rc10b_run_button_click_count"),
        click_rerun=st.session_state.get("rc10b_last_button_click_rerun"),
    )


def accept_source_language_change() -> None:
    translation_language_state_engine.accept_source_language_change(st.session_state)


def accept_target_language_change() -> None:
    translation_language_state_engine.accept_target_language_change(st.session_state)


def accept_translation_area_change() -> None:
    translation_area_state_engine.accept_translation_area_change(st.session_state)


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


# -----------------------------
# UI
# -----------------------------
def claim_and_commit_completed_result(
    session_generation: str,
    request_id: str,
) -> Optional[Dict[str, object]]:
    """Commit one completed result, leaving interrupted claims recoverable."""
    log_app_ocr_timing(
        request_id,
        "result_handoff_claim_attempt",
        session_generation=session_generation,
        request_lifecycle="running",
    )

    def commit_completed_delivery(delivery: Dict[str, object]) -> None:
        primary_result = delivery["primary_result"]
        if not isinstance(primary_result, dict):
            raise TypeError("Completed result payload is malformed")
        log_app_ocr_timing(
            request_id,
            "translation_result_store_attempt",
            session_generation=session_generation,
            request_lifecycle="running",
        )
        if st.session_state.get("rc3_ocr_result") is not None:
            log_result_state_event(
                "result_clear",
                reason="new_translation_result",
            )
        result_delivery_engine.store_primary_result(st.session_state, primary_result)
        st.session_state["rc3_ocr_result_signature"] = delivery["result_signature"]
        st.session_state["pending_ocr_run"] = False
        st.session_state["ocr_running"] = False
        st.session_state["ocr_finished_at"] = delivery["ocr_finished_at"]
        st.session_state["ocr_duration_seconds"] = delivery["ocr_duration_seconds"]
        st.session_state["ocr_timing_request_id"] = None
        st.session_state["ocr_timing_action_started"] = None
        st.session_state["debug_report_ready"] = False
        st.session_state["last_successful_download_key"] = None
        st.session_state["completed_result_analytics_pending"] = delivery.get(
            "analytics"
        )
        # Keep the lifecycle running until every other result mutation succeeds.
        st.session_state["ocr_request_lifecycle"] = (
            ocr_request_lifecycle_engine.finish_request(
                st.session_state.get("ocr_request_lifecycle"),
                request_id,
                succeeded=True,
            )
        )

    claimed_delivery, expired_handoff_count = (
        result_delivery_engine.claim_completed_result(
            session_generation,
            request_id,
            commit_completed_delivery,
        )
    )
    if expired_handoff_count:
        log_app_ocr_timing(
            request_id,
            "result_handoff_expired",
            session_generation=session_generation,
        )
    if claimed_delivery is not None:
        log_app_ocr_timing(
            request_id,
            "result_handoff_claim_success",
            session_generation=session_generation,
            request_lifecycle="completed",
        )
        log_app_ocr_timing(
            request_id,
            "translation_result_store_success",
            session_generation=session_generation,
            request_lifecycle="completed",
            outcome="success",
        )
        log_app_ocr_timing(
            request_id,
            "downstream_translation_end",
            elapsed_seconds=claimed_delivery.get("downstream_elapsed_seconds"),
            session_generation=session_generation,
            outcome="success",
        )
        log_app_ocr_timing(
            request_id,
            "translation_run_end",
            elapsed_seconds=claimed_delivery.get(
                "translation_run_elapsed_seconds"
            ),
            session_generation=session_generation,
            request_lifecycle="completed",
            outcome="success",
        )
    return claimed_delivery


init_rc3_state()
canonical_translation_languages = (
    translation_language_state_engine.reconcile_translation_languages(
        st.session_state
    )
)
canonical_area_mode = translation_area_state_engine.reconcile_translation_area(
    st.session_state
)
diagnostic_session_generation = str(
    st.session_state.get("diagnostic_session_generation") or "unavailable"
)
handoff_lifecycle = st.session_state.get("ocr_request_lifecycle")
handoff_request_id = str(
    handoff_lifecycle.get("request_id")
    if isinstance(handoff_lifecycle, dict) and handoff_lifecycle.get("request_id")
    else ""
)
claimed_completed_delivery = None
if handoff_request_id and (
    isinstance(handoff_lifecycle, dict)
    and handoff_lifecycle.get("state") == ocr_request_lifecycle_engine.RUNNING
):
    claimed_completed_delivery = claim_and_commit_completed_result(
        diagnostic_session_generation,
        handoff_request_id,
    )
mount_plausible_bridge(st.session_state.pop("pending_plausible_v2_event", None))
st.session_state["rc10b_rerun_count"] = st.session_state.get("rc10b_rerun_count", 0) + 1
if (
    st.session_state.get("rc3_ocr_result") is not None
    or _result_lifecycle_state() == ocr_request_lifecycle_engine.COMPLETED
):
    log_result_state_event("result_state_run_begin")
script_run_started = time.perf_counter()
script_run_lifecycle = st.session_state.get("ocr_request_lifecycle")
script_run_request_id = str(
    script_run_lifecycle.get("request_id")
    if isinstance(script_run_lifecycle, dict) and script_run_lifecycle.get("request_id")
    else st.session_state.get("ocr_timing_request_id") or "none"
)
log_app_ocr_timing(
    script_run_request_id,
    "script_run_begin",
    session_generation=diagnostic_session_generation,
    request_lifecycle=(
        str(script_run_lifecycle.get("state") or "none")
        if isinstance(script_run_lifecycle, dict)
        else "none"
    ),
    active_image=st.session_state.get("rc3_active_image_upload") is not None,
    script_run_no=st.session_state.get("rc10b_rerun_count"),
)

CANONICAL_INTERFACE_LANGUAGES = {
    "en": "English",
    "zh-Hant": "繁體中文",
    "zh-Hans": "简体中文",
    "ja": "日本語",
}
INTERFACE_LANGUAGE_CANONICAL_KEYS = {
    value: key for key, value in CANONICAL_INTERFACE_LANGUAGES.items()
}

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


def resolve_interface_language(query_value: object, fallback: str) -> str:
    if isinstance(query_value, list):
        query_value = query_value[0] if query_value else ""
    return CANONICAL_INTERFACE_LANGUAGES.get(str(query_value or ""), fallback)


def portal_url_for_language(language: str) -> str:
    canonical_language = INTERFACE_LANGUAGE_CANONICAL_KEYS.get(language, "en")
    parts = urlsplit(PORTAL_URL)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["ui_lang"] = canonical_language
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


initial_interface_language = detect_initial_interface_language()
interface_language = resolve_interface_language(
    st.query_params.get("ui_lang", ""), initial_interface_language
)
st.session_state["interface_language_selector"] = interface_language
st.session_state["ui_lang"] = INTERFACE_LANGUAGE_CANONICAL_KEYS.get(interface_language, "en")
ui_text = INTERFACE_LANGUAGES.get(interface_language, INTERFACE_LANGUAGES["English"])

def t(key: str) -> str:
    return ui_text.get(key, INTERFACE_LANGUAGES["English"].get(key, key))


def get_request_headers() -> Dict[str, object]:
    try:
        return dict(st.context.headers)
    except Exception:
        return {}


request_headers = get_request_headers()
ensure_analytics_session(st.session_state, headers=request_headers)
st.session_state.setdefault(
    "diagnostic_platform",
    str(request_headers.get("user-agent", "") or "Not captured"),
)


def track_analytics_event(event_type: str, **fields) -> None:
    analytics_track_event(
        session_state=st.session_state,
        secrets=st.secrets,
        worksheet_name=WORKSHEET_PATTERN_TRANSLATION,
        event_type=event_type,
        app_version=APP_VERSION,
        interface_language=interface_language,
        country=st.session_state.get("analytics_country", "Unknown"),
        **fields,
    )


if not st.session_state.get("analytics_app_open_logged"):
    track_analytics_event("app_open")
    st.session_state["analytics_app_open_logged"] = True

completed_result_analytics = st.session_state.pop(
    "completed_result_analytics_pending", None
)
if isinstance(completed_result_analytics, dict):
    try:
        translation_no = get_session_translation_no(st.session_state)
        track_analytics_event(
            "translation_completed",
            workflow_mode=completed_result_analytics["area_mode"],
            success=True,
            translate_from=completed_result_analytics["source_mode"],
            translate_to=completed_result_analytics["output_mode"],
            ocr_box_count=completed_result_analytics["ocr_box_count"],
            ocr_time_sec=completed_result_analytics["ocr_time_sec"],
            translation_time_sec=completed_result_analytics[
                "translation_time_sec"
            ],
            session_translation_no=translation_no,
        )
        stage_plausible_event(st.session_state, "pattern_translation_completed")
        increment_session_translation_no(st.session_state)
    except Exception as exc:
        print(f"[analytics] completed translation event failed: {exc}")
    st.rerun()

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


st.markdown(
    f'<a href="{html.escape(portal_url_for_language(interface_language), quote=True)}" '
    f'target="_self">← {html.escape(t("back_to_portal"))}</a>',
    unsafe_allow_html=True,
)
st.markdown('<div class="product-kicker">Crochet Intelligence</div>', unsafe_allow_html=True)
st.title(t("app_title"))
st.caption(t("app_subtitle"))

LANGUAGE_OPTIONS = translation_language_state_engine.LANGUAGE_OPTIONS

upload_strings = {
    "html_lang": {
        "English": "en",
        "Traditional Chinese": "zh-Hant",
        "Simplified Chinese": "zh-Hans",
        "Japanese": "ja",
    }.get(interface_language, "en"),
    "instruction": t("upload_instruction"),
    "choose": t("upload_choose"),
    "drop_hint": t("upload_drop_hint"),
    "drop_active": t("upload_drop_active"),
    "reading": t("upload_reading"),
    "selected": t("upload_selected"),
    "replace": t("upload_replace"),
    "remove": t("upload_remove"),
    "error_unsupported": t("upload_error_unsupported"),
    "error_empty": t("upload_error_empty"),
    "error_too_large": t("upload_error_too_large"),
    "error_unreadable": t("upload_error_unreadable"),
    "error_invalid": t("upload_error_invalid"),
}

active_image_upload = restore_uploaded_image(
    st.session_state.get("rc3_active_image_upload")
)
had_active_image_before_uploader = active_image_upload is not None
image_file, upload_error, upload_removed = custom_image_uploader(
    upload_strings,
    key="pattern_image_uploader",
    active_image_present=active_image_upload is not None,
    active_image_name=(active_image_upload.name if active_image_upload else ""),
    accepted_action_id=(active_image_upload.action_id if active_image_upload else ""),
    accepted_generation=st.session_state.get("rc3_upload_generation", 0),
)
if upload_error:
    st.error(upload_error)

uploader_event = "none"
if upload_removed is not None:
    uploader_event = "remove"
elif image_file is not None:
    uploader_event = "replace" if had_active_image_before_uploader else "new"
if (
    st.session_state.get("rc3_ocr_result") is not None
    or _result_lifecycle_state() == ocr_request_lifecycle_engine.COMPLETED
):
    log_result_state_event(
        "uploader_state",
        uploader_event=uploader_event,
    )

def reset_uploaded_image_derived_state(
    image_signature: Optional[str], image_name: str = "", *, reason: str
) -> None:
    log_result_state_event("result_clear", reason=reason)
    st.session_state["rc3_ocr_result"] = None
    st.session_state["rc3_ocr_result_signature"] = None
    st.session_state["pending_ocr_run"] = False
    st.session_state["ocr_running"] = False
    st.session_state["ocr_started_at"] = None
    st.session_state["ocr_finished_at"] = None
    st.session_state["ocr_duration_seconds"] = None
    st.session_state["latest_crop_box"] = None
    st.session_state["select_area_confirmed_crop_box"] = None
    st.session_state["select_area_editing"] = False
    st.session_state["select_area_draft_crop_box"] = None
    st.session_state["select_area_display_proxy_diagnostics"] = {}
    st.session_state["select_area_last_component_action_id"] = None
    st.session_state["select_area_edit_session_no"] = 0
    st.session_state["select_area_last_area_mode"] = None
    st.session_state["select_area_start_over_pending"] = False
    st.session_state["rc10b_last_cropper_box"] = None
    st.session_state["debug_report_ready"] = False
    st.session_state["last_successful_download_key"] = None
    st.session_state["rc3_image_signature"] = image_signature
    st.session_state["rc3_uploaded_image_name"] = (
        str(image_name or "") if image_signature is not None else ""
    )
    if image_signature is None:
        st.session_state["rc3_active_image_upload"] = None


if upload_removed:
    st.session_state["rc3_upload_generation"] = max(
        st.session_state.get("rc3_upload_generation", 0),
        upload_removed.generation,
    )
    if (
        st.session_state.get("rc3_image_signature") is not None
        or st.session_state.get("rc3_active_image_upload") is not None
    ):
        reset_uploaded_image_derived_state(None, reason="image_removed")
        st.rerun()

if image_file is not None:
    st.session_state["rc3_upload_generation"] = max(
        st.session_state.get("rc3_upload_generation", 0),
        image_file.generation,
    )
    st.session_state["rc3_active_image_upload"] = snapshot_uploaded_image(image_file)
    active_image_upload = restore_uploaded_image(
        st.session_state.get("rc3_active_image_upload")
    )

image_file = active_image_upload

if image_file is None:
    rc10b_note_image_absent()
    if (
        st.session_state.get("rc3_ocr_result") is not None
        or _result_lifecycle_state() == ocr_request_lifecycle_engine.COMPLETED
    ):
        log_result_state_event(
            "result_render_skipped",
            reason="no_active_image",
        )

if image_file is not None:
    current_signature = image_upload_signature(image_file)
    rc10b_note_image_present(current_signature)
    if st.session_state.get("rc3_image_signature") != current_signature:
        reset_uploaded_image_derived_state(
            current_signature,
            str(getattr(image_file, "name", "")),
            reason="new_image",
        )
        track_analytics_event("image_uploaded")
        emit_plausible_event(
            "pattern_image_uploaded",
            str(getattr(image_file, "action_id", "")),
            key="pattern_image_uploaded_transport",
        )

    image_load_start = time.perf_counter()
    image = Image.open(image_file).convert("RGB")
    image_load_seconds = time.perf_counter() - image_load_start
    st.image(image, caption=t("original_image"), use_container_width=True)

    st.selectbox(
        t("source_label"),
        LANGUAGE_OPTIONS,
        index=None,
        key="source_language_selector",
        help=t("source_help"),
        format_func=lambda value: t(LANGUAGE_OPTION_LABEL_KEYS.get(value, value)),
        on_change=accept_source_language_change,
    )
    source_mode = canonical_translation_languages["source"]
    if source_mode == "English — US":
        st.caption(t("source_hint_us"))
    elif source_mode == "English — UK":
        st.caption(t("source_hint_uk"))

    st.selectbox(
        t("output_label"),
        LANGUAGE_OPTIONS,
        index=None,
        key="target_language_selector",
        format_func=lambda value: t(LANGUAGE_OPTION_LABEL_KEYS.get(value, value)),
        on_change=accept_target_language_change,
    )
    output_mode = canonical_translation_languages["target"]
    if output_mode == "English — US":
        st.caption(t("output_hint_us"))
    elif output_mode == "English — UK":
        st.caption(t("output_hint_uk"))
    if llm_fallback_engine.is_fallback_enabled():
        st.caption(t("ai_translation_note"))

    st.subheader(t("translation_area"))

    area_options = translation_area_state_engine.AREA_OPTIONS
    if st.session_state.pop("select_area_start_over_pending", False):
        translation_area_state_engine.set_translation_area(
            st.session_state, "Whole Pattern"
        )
        st.session_state["select_area_last_area_mode"] = "Whole Pattern"
    st.radio(
        t("area_label"),
        area_options,
        key="translation_area_mode_radio",
        horizontal=True,
        index=None,
        format_func=lambda value: t(AREA_LABEL_KEYS.get(value, value)),
        on_change=accept_translation_area_change,
    )
    area_mode = str(
        st.session_state.get(translation_area_state_engine.AREA_STATE_KEY)
        or canonical_area_mode
    )
    previous_area_mode = st.session_state.get("select_area_last_area_mode")
    entered_select_area = area_mode == "Select Area" and previous_area_mode != "Select Area"
    st.session_state["select_area_last_area_mode"] = area_mode
    if area_mode == "Select Area":
        st.caption(t("translation_area_tip"))

    area_map = {
        "Select Area": "Whole image",
        "Left Column": "Left side",
        "Right Column": "Right side",
        "Whole Pattern": "Whole image",
    }

    area_mode_for_box = area_map.get(area_mode, "Whole image")
    preset_box = get_preset_crop_box(image, area_mode_for_box)

    def start_over_select_area() -> None:
        log_result_state_event(
            "result_clear",
            reason="select_area_start_over",
            area_mode=area_mode,
            select_area_editing=bool(
                st.session_state.get("select_area_editing")
            ),
            crop_confirmed=(
                st.session_state.get("select_area_confirmed_crop_box") is not None
            ),
        )
        st.session_state["select_area_start_over_pending"] = True
        st.session_state["select_area_confirmed_crop_box"] = None
        st.session_state["select_area_editing"] = False
        st.session_state["select_area_draft_crop_box"] = None
        st.session_state["select_area_display_proxy_diagnostics"] = {}
        st.session_state["select_area_last_component_action_id"] = None
        st.session_state["latest_crop_box"] = get_preset_crop_box(image, "Whole image")
        st.session_state["rc3_ocr_result"] = None
        st.session_state["rc3_ocr_result_signature"] = None
        st.session_state["pending_ocr_run"] = False
        st.session_state["ocr_running"] = False
        st.session_state["ocr_started_at"] = None
        st.session_state["ocr_finished_at"] = None
        st.session_state["ocr_duration_seconds"] = None

    if area_mode == "Whole Pattern":
        crop_box = preset_box
        st.session_state["latest_crop_box"] = crop_box
        st.session_state["select_area_editing"] = False
        st.session_state["select_area_draft_crop_box"] = None
        st.session_state["select_area_display_proxy_diagnostics"] = {}
    else:
        confirmed_crop_box = st.session_state.get("select_area_confirmed_crop_box")
        is_editing_area = bool(st.session_state.get("select_area_editing"))
        if confirmed_crop_box is None and not is_editing_area and entered_select_area:
            track_analytics_event("select_area_started", workflow_mode=area_mode)
            st.session_state["select_area_editing"] = True
            st.session_state["select_area_draft_crop_box"] = get_default_select_area_crop_box(image)
            st.session_state["select_area_edit_session_no"] = int(
                st.session_state.get("select_area_edit_session_no", 0)
            ) + 1
            is_editing_area = True
        crop_box = clamp_crop_box(confirmed_crop_box, image) if confirmed_crop_box is not None else (0, 0, image.size[0], image.size[1])

        if is_editing_area:
            draft_crop_box = st.session_state.get("select_area_draft_crop_box") or confirmed_crop_box or get_default_select_area_crop_box(image)
            draft_crop_box = clamp_crop_box(draft_crop_box, image)
            adjust_mode = "Custom crop workspace"

            def confirm_select_area_crop(button_key: str) -> None:
                if st.button(t("select_area_use"), key=button_key, type="primary"):
                    confirmed = clamp_crop_box(st.session_state.get("select_area_draft_crop_box") or draft_crop_box, image)
                    st.session_state["select_area_confirmed_crop_box"] = confirmed
                    st.session_state["latest_crop_box"] = confirmed
                    st.session_state["rc10b_last_cropper_box"] = confirmed
                    st.session_state["select_area_editing"] = False
                    st.session_state["select_area_draft_crop_box"] = None
                    rc10b_log_event(
                        "cropper box confirmed",
                        crop_box=confirmed,
                        image_signature=current_signature,
                        area_mode=area_mode,
                    )
                    track_analytics_event("select_area_confirmed", workflow_mode=area_mode)
                    try:
                        st.rerun()
                    except Exception:
                        pass

            def cancel_select_area_crop(button_key: str) -> None:
                if st.button(t("select_area_cancel"), key=button_key):
                    start_over_select_area()
                    try:
                        st.rerun()
                    except Exception:
                        pass

            st.caption(t("cropper_drag"))
            rerun_after_component_action = False
            try:
                safe_area_mode = re.sub(r"\W+", "_", area_mode_for_box.lower())
                image_key_fragment = current_signature[:12]
                edit_session_no = int(st.session_state.get("select_area_edit_session_no", 0))
                cropper_key = (
                    f"custom_cropper_{image_key_fragment}_{safe_area_mode}_"
                    f"{image.size[0]}x{image.size[1]}_{edit_session_no}"
                )
                display_image, display_scale_x, display_scale_y, display_diag = prepare_cropper_display_image(image)
                st.session_state["select_area_display_proxy_diagnostics"] = display_diag
                display_crop_box = crop_box_original_to_display(
                    draft_crop_box,
                    display_scale_x,
                    display_scale_y,
                    display_image,
                )
                cropper_strings = {
                    "html_lang": {
                        "Traditional Chinese": "zh-Hant",
                        "Simplified Chinese": "zh-Hans",
                        "Japanese": "ja",
                    }.get(interface_language, "en"),
                    "image_alt": t("select_area_image_alt"),
                    "selection_label": t("select_area_selection_label"),
                    "confirm": t("select_area_use"),
                    "reset": t("select_area_reset"),
                    "cancel": t("select_area_cancel"),
                    "move_controller": t("select_area_move_controller"),
                    "move_up": t("select_area_move_up"),
                    "move_down": t("select_area_move_down"),
                    "move_left": t("select_area_move_left"),
                    "move_right": t("select_area_move_right"),
                    "adjust_top_up": t("select_area_adjust_top_up"),
                    "adjust_top_down": t("select_area_adjust_top_down"),
                    "adjust_bottom_up": t("select_area_adjust_bottom_up"),
                    "adjust_bottom_down": t("select_area_adjust_bottom_down"),
                    "adjust_left_left": t("select_area_adjust_left_left"),
                    "adjust_left_right": t("select_area_adjust_left_right"),
                    "adjust_right_left": t("select_area_adjust_right_left"),
                    "adjust_right_right": t("select_area_adjust_right_right"),
                    "resize_top": t("select_area_resize_top"),
                    "resize_bottom": t("select_area_resize_bottom"),
                    "resize_left": t("select_area_resize_left"),
                    "resize_right": t("select_area_resize_right"),
                }
                rc10b_log_event(
                    "custom cropper workspace created",
                    cropper_key=cropper_key,
                    image_signature=current_signature,
                    area_mode=area_mode,
                    display_proxy=display_diag,
                )
                cropper_result = custom_select_area(
                    display_image,
                    display_crop_box,
                    cropper_strings,
                    image_signature=current_signature,
                    key=cropper_key,
                )
                action_id = str((cropper_result or {}).get("action_id") or "")
                is_new_action = bool(
                    action_id
                    and action_id != st.session_state.get("select_area_last_component_action_id")
                )
                if is_new_action:
                    st.session_state["select_area_last_component_action_id"] = action_id
                    if cropper_result.get("action") == "confirm":
                        display_cropper_box = crop_box_from_cropper_result(
                            cropper_result.get("box"),
                            display_image,
                        )
                        if display_cropper_box is None:
                            raise ValueError("Custom cropper returned an invalid crop box")
                        cropper_box = crop_box_display_to_original(
                            display_cropper_box,
                            display_scale_x,
                            display_scale_y,
                            image,
                        )
                        st.session_state["select_area_confirmed_crop_box"] = cropper_box
                        st.session_state["latest_crop_box"] = cropper_box
                        st.session_state["rc10b_last_cropper_box"] = cropper_box
                        st.session_state["select_area_editing"] = False
                        st.session_state["select_area_draft_crop_box"] = None
                        rc10b_log_event(
                            "custom cropper box confirmed",
                            crop_box=cropper_box,
                            display_cropper_box=display_cropper_box,
                            image_signature=current_signature,
                            area_mode=area_mode,
                        )
                        track_analytics_event("select_area_confirmed", workflow_mode=area_mode)
                    elif cropper_result.get("action") == "cancel":
                        start_over_select_area()
                    rerun_after_component_action = True
            except Exception as e:
                st.warning(t("cropper_failed"))
                st.caption(str(e))
                adjust_mode = "Use boundary sliders"
            if rerun_after_component_action:
                st.rerun()

            if adjust_mode == "Use boundary sliders":
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

            if adjust_mode == "Use boundary sliders":
                col_cancel, col_use = st.columns(2)
                with col_cancel:
                    cancel_select_area_crop("select_area_cancel_fallback_button")
                with col_use:
                    confirm_select_area_crop("select_area_use_fallback_button")
        else:
            if confirmed_crop_box is not None:
                crop_box = clamp_crop_box(confirmed_crop_box, image)
                st.session_state["latest_crop_box"] = crop_box
                st.caption(t("select_area_confirmed_hint"))
                if st.button(t("select_area_edit"), key="select_area_edit_button"):
                    track_analytics_event("select_area_started", workflow_mode=area_mode)
                    st.session_state["select_area_editing"] = True
                    st.session_state["select_area_draft_crop_box"] = crop_box
                    st.session_state["select_area_edit_session_no"] = int(
                        st.session_state.get("select_area_edit_session_no", 0)
                    ) + 1
                    try:
                        st.rerun()
                    except Exception:
                        pass
            else:
                crop_box = (0, 0, image.size[0], image.size[1])

        if st.session_state.get("select_area_editing"):
            log_result_state_event(
                "result_render_skipped",
                reason="select_area_editing",
                area_mode=area_mode,
                select_area_editing=True,
                crop_confirmed=(
                    st.session_state.get("select_area_confirmed_crop_box") is not None
                ),
            )
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
    result_present_at_signature_guard = (
        st.session_state.get("rc3_ocr_result") is not None
    )
    signature_match = stored_ocr_signature == current_ocr_signature
    mismatch_fields = (
        result_delivery_engine.differing_signature_fields(
            stored_ocr_signature,
            current_ocr_signature,
        )
        if result_present_at_signature_guard and not signature_match
        else ()
    )
    if (
        result_present_at_signature_guard
        or _result_lifecycle_state() == ocr_request_lifecycle_engine.COMPLETED
    ):
        log_result_state_event(
            "translation_signature_guard",
            area_mode=area_mode,
            select_area_editing=bool(
                st.session_state.get("select_area_editing")
            ),
            crop_confirmed=(
                st.session_state.get("select_area_confirmed_crop_box") is not None
            ),
            stored_signature_present=stored_ocr_signature is not None,
            current_signature_present=current_ocr_signature is not None,
            signature_match=signature_match,
            mismatch_fields=mismatch_fields,
        )
    if st.session_state.get("rc3_ocr_result") is not None and stored_ocr_signature != current_ocr_signature:
        log_result_state_event(
            "result_clear",
            reason="translation_signature_mismatch",
            area_mode=area_mode,
            select_area_editing=bool(
                st.session_state.get("select_area_editing")
            ),
            crop_confirmed=(
                st.session_state.get("select_area_confirmed_crop_box") is not None
            ),
            stored_signature_present=True,
            current_signature_present=True,
            signature_match=False,
            mismatch_fields=mismatch_fields,
        )
        st.session_state["rc3_ocr_result"] = None
        log_result_state_event(
            "result_render_skipped",
            reason="result_invalidated",
            area_mode=area_mode,
        )
        st.warning(t("settings_changed_rerun"))

    full_df = load_database()
    df, index = prepare_translation_dataframe(full_df, source_mode)

    ocr_running = bool(st.session_state.get("ocr_running"))
    ocr_busy = bool(st.session_state.get("pending_ocr_run")) or ocr_running
    run_button_label = "⏳ OCR Running..." if ocr_busy else t("run_ocr")
    ocr_status_placeholder = st.empty()
    translation_languages_missing = source_mode is None or output_mode is None
    st.button(
        run_button_label,
        key="run_ocr_overlay_translation_button",
        type="primary",
        disabled=(
            ocr_busy
            or translation_languages_missing
            or select_area_needs_confirmation
            or (bool(quality_errors) and not force_run)
        ),
        on_click=request_ocr_run,
    )

    if st.session_state.get("pending_ocr_run"):
        diagnostic_request_id = str(
            st.session_state.get("ocr_timing_request_id") or uuid.uuid4().hex
        )
        st.session_state["ocr_timing_request_id"] = diagnostic_request_id
        action_started = st.session_state.get("ocr_timing_action_started")
        click_to_pending_seconds = (
            time.perf_counter() - action_started
            if isinstance(action_started, (int, float))
            else None
        )
        ocr_status_placeholder.info("🔵 OCR started...")
        with st.spinner(t("running_ocr")):
            ocr_status_placeholder.warning("🟡 OCR running...")
            lifecycle, request_claimed = ocr_request_lifecycle_engine.claim_request(
                st.session_state.get("ocr_request_lifecycle"),
                diagnostic_request_id,
            )
            st.session_state["ocr_request_lifecycle"] = lifecycle
            st.session_state["pending_ocr_run"] = False
            if not request_claimed:
                st.session_state["duplicate_ocr_run_ignored_count"] = (
                    st.session_state.get("duplicate_ocr_run_ignored_count", 0) + 1
                )
                log_app_ocr_timing(
                    diagnostic_request_id,
                    "pending_run_replay_ignored",
                    outcome="already_consumed",
                )
                log_result_state_event(
                    "result_render_skipped",
                    reason="pending_request_replay",
                    area_mode=area_mode,
                )
                st.stop()

            # No Streamlit UI calls occur after this transition until the request
            # result is stored and its lifecycle is terminal.
            st.session_state["ocr_running"] = True
            log_app_ocr_timing(
                diagnostic_request_id,
                "pending_run_begin",
                elapsed_seconds=click_to_pending_seconds,
                session_generation=diagnostic_session_generation,
                request_lifecycle="running",
                active_image=st.session_state.get("rc3_active_image_upload") is not None,
            )
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
            try:
                ocr_started_at_text = time.strftime("%Y-%m-%d %H:%M:%S")
                st.session_state["ocr_started_at"] = ocr_started_at_text
                st.session_state["ocr_finished_at"] = None
                st.session_state["ocr_duration_seconds"] = None
                ocr_execution_start = time.perf_counter()
                rc10b_log_event(
                    "OCR started",
                    ocr_started_at=st.session_state.get("ocr_started_at"),
                )
                delivery_session_diagnostics = rc10b_diagnostic_snapshot()
                delivery_diagnostic_events = list(
                    st.session_state.get("rc10b_diagnostic_events", [])
                )
                delivery_diagnostic_platform = st.session_state.get(
                    "diagnostic_platform", "Not captured"
                )
                delivery_session_diagnostics["ocr_started_at"] = ocr_started_at_text
                translation_result = translate_image(
                    TranslateImageRequest(
                        image=image,
                        selected_image=selected_image,
                        working_image=working_image,
                        source_mode=source_mode,
                        output_mode=output_mode,
                        area_mode=area_mode,
                        crop_box=crop_box,
                        df=df,
                        index=index,
                        diagnostic_request_id=diagnostic_request_id,
                        diagnostic_session_generation=diagnostic_session_generation,
                        action_started=(
                            action_started
                            if isinstance(action_started, (int, float))
                            else None
                        ),
                        image_load_seconds=image_load_seconds,
                        crop_extraction_seconds=crop_extraction_seconds,
                        quality_metrics=quality_metrics,
                        quality_errors=quality_errors,
                        quality_warnings=quality_warnings,
                        quality_label=quality_label,
                        experimental_downscale=experimental_downscale,
                        downscale_max_height_option=downscale_max_height_option,
                        ocr_resize_test=ocr_resize_test,
                        session_diagnostics=delivery_session_diagnostics,
                        diagnostic_events=delivery_diagnostic_events,
                        diagnostic_platform=delivery_diagnostic_platform,
                        interface_language=interface_language,
                        ocr_execution_start=ocr_execution_start,
                    )
                )
                primary_result = translation_result.primary_result
                diagnostic_inputs = primary_result.get("diagnostic_report_inputs", {})
                if isinstance(diagnostic_inputs, dict):
                    session_diag = diagnostic_inputs.get("session_diagnostics", {})
                    if isinstance(session_diag, dict):
                        session_diag["ocr_started_at"] = ocr_started_at_text
                completed_delivery = {
                    "primary_result": primary_result,
                    "result_signature": current_ocr_signature,
                    "ocr_finished_at": translation_result.ocr_finished_at,
                    "ocr_duration_seconds": translation_result.ocr_duration_seconds,
                    "downstream_elapsed_seconds": translation_result.downstream_elapsed_seconds,
                    "translation_run_elapsed_seconds": translation_result.translation_run_elapsed_seconds,
                    "analytics": translation_result.analytics,
                }
                handoff_published, expired_handoff_count = (
                    result_delivery_engine.publish_completed_result(
                        diagnostic_session_generation,
                        diagnostic_request_id,
                        completed_delivery,
                    )
                )
                if expired_handoff_count:
                    log_app_ocr_timing(
                        diagnostic_request_id,
                        "result_handoff_expired",
                        session_generation=diagnostic_session_generation,
                    )
                log_app_ocr_timing(
                    diagnostic_request_id,
                    "result_handoff_publish",
                    session_generation=diagnostic_session_generation,
                    request_lifecycle="running",
                    outcome="published" if handoff_published else "already_published",
                )
                claimed_completed_delivery = claim_and_commit_completed_result(
                    diagnostic_session_generation,
                    diagnostic_request_id,
                )
            except Exception as e:
                st.session_state["ocr_finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                st.session_state["ocr_duration_seconds"] = round(time.perf_counter() - ocr_execution_start, 3) if "ocr_execution_start" in locals() else None
                st.session_state["ocr_running"] = False
                st.session_state["pending_ocr_run"] = False
                st.session_state["ocr_request_lifecycle"] = (
                    ocr_request_lifecycle_engine.finish_request(
                        st.session_state.get("ocr_request_lifecycle"),
                        diagnostic_request_id,
                        succeeded=False,
                    )
                )
                rc10b_log_event(
                    "OCR failed",
                    ocr_started_at=st.session_state.get("ocr_started_at"),
                    ocr_finished_at=st.session_state.get("ocr_finished_at"),
                    ocr_duration_seconds=st.session_state.get("ocr_duration_seconds"),
                    error=str(e),
                )
                track_analytics_event(
                    "translation_failed",
                    workflow_mode=area_mode if "area_mode" in locals() else "",
                    success=False,
                    translate_from=source_mode if "source_mode" in locals() else "",
                    translate_to=output_mode if "output_mode" in locals() else "",
                )
                log_app_ocr_timing(
                    diagnostic_request_id,
                    "translation_run_end",
                    elapsed_seconds=(
                        time.perf_counter() - action_started
                        if isinstance(action_started, (int, float))
                        else time.perf_counter() - ocr_execution_start
                        if "ocr_execution_start" in locals()
                        else None
                    ),
                    outcome="failed",
                    session_generation=diagnostic_session_generation,
                    request_lifecycle="failed",
                )
                st.session_state["ocr_timing_request_id"] = None
                st.session_state["ocr_timing_action_started"] = None
                st.error(t("ocr_failed"))
                log_result_state_event(
                    "result_render_skipped",
                    reason="ocr_failure",
                    area_mode=area_mode,
                )
                log_app_ocr_timing(
                    diagnostic_request_id,
                    "script_run_end",
                    elapsed_seconds=time.perf_counter() - script_run_started,
                    outcome="stopped_after_failure",
                    session_generation=diagnostic_session_generation,
                    request_lifecycle="failed",
                    active_image=st.session_state.get("rc3_active_image_upload") is not None,
                    script_run_no=st.session_state.get("rc10b_rerun_count"),
                )
                st.stop()

    result = st.session_state.get("rc3_ocr_result")
    if result:
        log_result_state_event(
            "result_render_enter",
            area_mode=area_mode,
            select_area_editing=bool(
                st.session_state.get("select_area_editing")
            ),
            crop_confirmed=(
                st.session_state.get("select_area_confirmed_crop_box") is not None
            ),
        )
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
                analytics_event_type="download_png",
                plausible_event_name="pattern_png_downloaded",
                diagnostic_action="png",
            )
        elif raw_ocr_text.strip():
            st.info(f"**{t('no_crochet_pattern_title')}**\n\n{t('no_crochet_pattern_body')}")

        st.subheader(t("line_translation"))
        if line_df is not None and not line_df.empty:
            st.text_area(t("translated_lines"), readable_translation, height=320)
            download_button_rc3(
                t("download_translation"),
                data=result.get("translation_txt", ""),
                file_name="crochet_translation.txt",
                mime="text/plain",
                key="download_overlay_translation_txt",
                analytics_event_type="download_txt",
                plausible_event_name="pattern_txt_downloaded",
                diagnostic_action="txt",
            )
        else:
            st.warning(t("no_ocr_lines"))

        st.subheader(t("report_problem"))
        st.markdown(t("report_intro"))
        st.markdown(f"<div class='report-action'>{html.escape(t('report_download_action'))}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='report-helper'>{html.escape(t('report_download_helper'))}</div>", unsafe_allow_html=True)
        debug_report_txt = str(result.get("debug_report_txt", "") or "")

        def note_diagnostic_action_received() -> None:
            log_result_state_event(
                "post_result_action_received",
                action="diagnostic",
                callback_receipt=True,
            )

        diagnostic_download_slot = st.empty()
        diagnostic_requested = False
        if not debug_report_txt:
            diagnostic_requested = diagnostic_download_slot.button(
                t("download_debug_report"),
                key="prepare_debug_report_download",
                on_click=note_diagnostic_action_received,
            )
        if diagnostic_requested:
            log_result_state_event(
                "post_result_action_handler_enter",
                action="diagnostic",
            )
            report_request_id = str(
                result.get("diagnostic_request_id") or uuid.uuid4().hex
            )
            report_generation_start = time.perf_counter()
            log_app_ocr_timing(
                report_request_id,
                "diagnostic_report_begin",
                session_generation=str(
                    result.get("diagnostic_session_generation") or "unavailable"
                ),
                request_lifecycle="completed",
            )
            generated, report_outcome = (
                result_delivery_engine.generate_optional_diagnostic_report(
                    result,
                    lambda: result_delivery_engine.build_deferred_diagnostic_report(
                        result,
                        terminology_dataframe=df,
                        csv_term_cache_stats=CSV_TERM_CACHE_STATS,
                        normalized_lookup_index_stats=NORMALIZED_LOOKUP_INDEX_STATS,
                        app_version=APP_VERSION,
                    ),
                )
            )
            report_seconds = time.perf_counter() - report_generation_start
            log_app_ocr_timing(
                report_request_id,
                "diagnostic_report_end",
                elapsed_seconds=report_seconds,
                outcome=report_outcome,
                session_generation=str(
                    result.get("diagnostic_session_generation") or "unavailable"
                ),
                request_lifecycle="completed",
            )
            if generated:
                st.session_state["debug_report_ready"] = True
                st.success(t("debug_report_generated"))
                debug_report_txt = str(result.get("debug_report_txt", "") or "")
            else:
                st.warning(t("debug_report_failed"))
        if debug_report_txt:
            diagnostic_download_slot.download_button(
                t("download_debug_report"),
                data=debug_report_txt,
                file_name=result_delivery_engine.diagnostic_report_filename(
                    APP_VERSION
                ),
                mime="text/plain",
                key="download_debug_report_txt",
                on_click="ignore",
            )
        st.markdown(f"<div class='report-action'>{html.escape(t('report_feedback_action'))}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='report-helper'>{html.escape(t('report_feedback_helper'))}</div>", unsafe_allow_html=True)
        feedback_link_rendered = plausible_link_button(
            t("send_feedback"),
            FEEDBACK_FORM_URL,
            "pattern_feedback_clicked",
            key="pattern_feedback_clicked_link",
        )
        if not feedback_link_rendered:
            st.link_button(t("send_feedback"), FEEDBACK_FORM_URL)

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
    elif _result_lifecycle_state() == ocr_request_lifecycle_engine.COMPLETED:
        log_result_state_event(
            "result_render_skipped",
            reason="result_absent",
            area_mode=area_mode,
            select_area_editing=bool(
                st.session_state.get("select_area_editing")
            ),
            crop_confirmed=(
                st.session_state.get("select_area_confirmed_crop_box") is not None
            ),
        )
else:
    pass

if DEBUG_MODE:
    render_rc10b_diagnostics()

try:
    final_lifecycle = st.session_state.get("ocr_request_lifecycle")
    final_request_id = str(
        final_lifecycle.get("request_id")
        if isinstance(final_lifecycle, dict) and final_lifecycle.get("request_id")
        else script_run_request_id
    )
    log_app_ocr_timing(
        final_request_id,
        "script_run_end",
        elapsed_seconds=time.perf_counter() - script_run_started,
        outcome="completed",
        session_generation=diagnostic_session_generation,
        request_lifecycle=(
            str(final_lifecycle.get("state") or "none")
            if isinstance(final_lifecycle, dict)
            else "none"
        ),
        active_image=st.session_state.get("rc3_active_image_upload") is not None,
        script_run_no=st.session_state.get("rc10b_rerun_count"),
    )
except Exception:
    pass
