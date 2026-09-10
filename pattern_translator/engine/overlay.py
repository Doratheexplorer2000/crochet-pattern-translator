"""Overlay rendering engine for the Pattern Translator.

This module owns pure image overlay generation: font loading, label wrapping,
collision checks, marker placement, legend generation, and PNG byte encoding.
It intentionally does not depend on Streamlit, session state, downloads,
analytics, UI localization, or deployment configuration.
"""

import io
import math
import os
import re
import statistics
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from pattern_translator.engine import line_translation as line_translation_engine
from pattern_translator.engine import pattern_document as pattern_document_engine
from pattern_translator.engine import terminology as terminology_engine


ProfileGetter = Callable[[], object]
ProfileCount = Callable[[str, float], None]
ProfileAddTime = Callable[[str, float], None]

_profile_getter: ProfileGetter = lambda: None
_profile_count_func: ProfileCount = lambda name, amount=1.0: None
_profile_add_time_func: ProfileAddTime = lambda name, seconds: None
SOURCE_REPLACEMENT_FLAG_ENV = "PATTERN_SOURCE_REPLACEMENT_OVERLAY_ENABLED"
_TRUE_VALUES = {"1", "true", "yes", "on"}
_PLATE_FILL = (255, 255, 245)
_PLATE_TEXT = (15, 15, 15)
_TEAL = (15, 118, 110)
_WARNING = (183, 121, 31)
_MIN_VERTICAL_PLATE_PADDING = 1
_ABSOLUTE_MIN_FONT_PX = 6
_SOURCE_GLYPH_HEIGHT_TOLERANCE_PX = 1.0


@dataclass(frozen=True)
class OverlayFontResolution:
    """A loaded overlay font plus stable provenance for diagnostics."""

    font: object
    family: str
    path: str
    face_index: Optional[int]
    weight: str
    target_language: str


def is_source_replacement_overlay_enabled(environ: Optional[Dict[str, str]] = None) -> bool:
    values = os.environ if environ is None else environ
    return str(values.get(SOURCE_REPLACEMENT_FLAG_ENV, "")).strip().lower() in _TRUE_VALUES


def configure_profile_context(
    profile_getter: ProfileGetter,
    profile_count_func: ProfileCount,
    profile_add_time_func: ProfileAddTime,
) -> None:
    """Attach app-level profiling without making this module depend on Streamlit."""
    global _profile_getter, _profile_count_func, _profile_add_time_func
    _profile_getter = profile_getter
    _profile_count_func = profile_count_func
    _profile_add_time_func = profile_add_time_func


def _profile_active() -> bool:
    try:
        return _profile_getter() is not None
    except Exception:
        return False


def _profile_count(name: str, amount: float = 1.0) -> None:
    try:
        _profile_count_func(name, amount)
    except Exception:
        pass


def _profile_add_time(name: str, seconds: float) -> None:
    try:
        _profile_add_time_func(name, seconds)
    except Exception:
        pass


def profile_function(time_name: str, count_name: str):
    def decorator(func):
        def wrapped(*args, **kwargs):
            _profile_count(count_name)
            profile_start = time.perf_counter() if _profile_active() else None
            try:
                return func(*args, **kwargs)
            finally:
                if profile_start is not None:
                    _profile_add_time(time_name, time.perf_counter() - profile_start)
        return wrapped
    return decorator


def _overlay_font_candidates(output_mode: str) -> Tuple[Tuple[str, int, str, str], ...]:
    noto_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    language_candidates = {
        "Traditional Chinese": (
            (noto_path, 3, "Noto Sans CJK TC", "Regular"),
            ("/System/Library/Fonts/STHeiti Medium.ttc", 0, "Heiti TC", "Medium"),
        ),
        "Simplified Chinese": (
            (noto_path, 2, "Noto Sans CJK SC", "Regular"),
            ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0, "Hiragino Sans GB", "W3"),
            ("/System/Library/Fonts/STHeiti Medium.ttc", 1, "Heiti SC", "Medium"),
        ),
        "Japanese": (
            (noto_path, 0, "Noto Sans CJK JP", "Regular"),
            ("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc", 0, "Hiragino Sans", "W3"),
        ),
        "English": (
            (noto_path, 0, "Noto Sans CJK JP", "Regular"),
            ("/System/Library/Fonts/Supplemental/Arial.ttf", 0, "Arial", "Regular"),
        ),
    }
    common_fallbacks = (
        ("/Library/Fonts/Arial Unicode.ttf", 0, "Arial Unicode MS", "Regular"),
        ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 0, "Arial Unicode MS", "Regular"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0, "DejaVu Sans", "Book"),
    )
    return language_candidates.get(output_mode, language_candidates["English"]) + common_fallbacks


@lru_cache(maxsize=128)
def _resolve_overlay_font(size: int, output_mode: str) -> OverlayFontResolution:
    requested_size = max(_ABSOLUTE_MIN_FONT_PX, int(size))
    for path, face_index, expected_family, expected_weight in _overlay_font_candidates(output_mode):
        try:
            font = ImageFont.truetype(path, size=requested_size, index=face_index)
            try:
                actual_family, actual_weight = font.getname()
            except Exception:
                actual_family, actual_weight = expected_family, expected_weight
            return OverlayFontResolution(
                font=font,
                family=str(actual_family or expected_family),
                path=path,
                face_index=face_index,
                weight=str(actual_weight or expected_weight),
                target_language=output_mode,
            )
        except Exception:
            continue
    return OverlayFontResolution(
        font=ImageFont.load_default(),
        family="Pillow default",
        path="Pillow default",
        face_index=None,
        weight="default",
        target_language=output_mode,
    )


def _load_overlay_font(size: int, output_mode: str = "English"):
    """Compatibility wrapper for legacy rendering paths."""
    return _resolve_overlay_font(size, output_mode).font


def line_overlay_font_size(
    image_width: int,
    line_df: Optional[pd.DataFrame] = None,
    scale_to_source_text: bool = False,
) -> int:
    """Size labels from the canvas, plus source-row geometry for unscaled crops."""
    canvas_size = max(18, int(image_width / 38))
    if not scale_to_source_text or line_df is None or line_df.empty:
        return canvas_size
    row_heights = []
    for _, row in line_df.iterrows():
        try:
            height = float(row.get("max_y", 0)) - float(row.get("min_y", 0))
        except (TypeError, ValueError):
            continue
        if height > 0:
            row_heights.append(height)
    if not row_heights:
        return canvas_size
    row_heights.sort()
    middle = len(row_heights) // 2
    median_height = (
        row_heights[middle]
        if len(row_heights) % 2
        else (row_heights[middle - 1] + row_heights[middle]) / 2
    )
    return max(canvas_size, int(median_height * 0.6))


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


def make_translation_overlay(
    image: Image.Image,
    ocr_rows: pd.DataFrame,
    interpretation_df: pd.DataFrame,
    output_mode: str,
) -> Optional[Image.Image]:
    """Draw compact translation labels near detected round rows on the original image.

    This is deliberately not a full Google Translate style overwrite. It keeps the
    original visible and places small labels near likely round anchors for debugging
    and readability.
    """
    if interpretation_df.empty or ocr_rows is None or ocr_rows.empty:
        return None
    img = image.convert("RGBA")
    w, h = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_size = max(14, min(28, int(w / 45)))
    font = _load_overlay_font(font_size, output_mode)
    output_col = line_translation_engine.get_output_column_name(output_mode)

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


def _make_legacy_line_translation_overlay(
    image: Image.Image,
    line_df: pd.DataFrame,
    output_mode: str,
    max_labels: int = 120,
    max_full_label_chars: int = 42,
    scale_to_source_text: bool = False,
) -> Tuple[Optional[Image.Image], str, pd.DataFrame]:
    """Draw smart overlay labels for translated OCR visual lines.

    Short translations are drawn near their OCR boxes. Long or colliding labels are
    replaced by numbered markers, with the full text returned as a legend. This is
    designed for beta stability rather than beautiful automatic typesetting.
    """
    if line_df is None or line_df.empty:
        return None, "", pd.DataFrame()
    request_warning = str(line_df.attrs.get("request_warning", "") or "").strip()
    line_df["Overlay Marker"] = ""
    overlay_marker_column = line_df.columns.get_loc("Overlay Marker")

    img = image.convert("RGBA")
    w, h = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_size = line_overlay_font_size(w, line_df, scale_to_source_text)
    font = _load_overlay_font(font_size, output_mode)
    marker_font = _load_overlay_font(max(font_size, 20), output_mode)

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
        if not translated or terminology_engine.norm_text(original) == terminology_engine.norm_text(translated):
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
            line_df.iloc[row_no, overlay_marker_column] = marker
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
        return None, request_warning, pd.DataFrame()

    legend_df = pd.DataFrame(legend_rows)
    legend_lines = []
    for _, r in legend_df.iterrows():
        marker = str(r.get("Marker", "")).strip()
        original = str(r.get("Original", "")).strip()
        translated = str(r.get("Translation", "")).strip()
        prefix = f"{marker} " if marker else ""
        legend_lines.append(f"{prefix}{original} → {translated}".strip())
    if request_warning:
        legend_lines.insert(0, request_warning)
    legend_text = "\n".join(legend_lines)
    return Image.alpha_composite(img, overlay).convert("RGB"), legend_text, legend_df


def _replacement_font_candidates(baseline: int, minimum: int) -> Tuple[int, ...]:
    """Return every integer font size through the absolute technical floor."""
    floor = min(int(baseline), int(minimum))
    return tuple(range(int(baseline), floor - 1, -1))


def _text_width(draw: ImageDraw.ImageDraw, font: object, text: str) -> float:
    bbox = draw.textbbox((0, 0), str(text), font=font)
    return float(bbox[2] - bbox[0])


def _next_wrapped_line(
    text: str,
    draw: ImageDraw.ImageDraw,
    font: object,
    max_width: float,
) -> Tuple[str, str]:
    remaining = str(text or "").lstrip()
    if not remaining:
        return "", ""
    newline = remaining.find("\n")
    paragraph = remaining if newline < 0 else remaining[:newline]
    after_paragraph = "" if newline < 0 else remaining[newline + 1 :]
    if _text_width(draw, font, paragraph) <= max_width:
        return paragraph.rstrip(), after_paragraph.lstrip()

    cut = 0
    last_break = 0
    break_chars = set(" ,，、;；:：.)）]】/–—-")
    for index, character in enumerate(paragraph, start=1):
        if _text_width(draw, font, paragraph[:index]) > max_width:
            break
        cut = index
        if character in break_chars:
            last_break = index
    if cut <= 0:
        return "", remaining
    if last_break >= max(1, int(cut * 0.45)):
        cut = last_break
    line = paragraph[:cut].strip()
    tail = paragraph[cut:].lstrip()
    if after_paragraph:
        tail = f"{tail}\n{after_paragraph}" if tail else after_paragraph
    return line, tail


def _wrap_text_to_widths(
    text: str,
    draw: ImageDraw.ImageDraw,
    font: object,
    widths: List[float],
) -> Tuple[List[str], bool]:
    remaining = re.sub(r"[\t\r ]+", " ", str(text or "").strip())
    lines: List[str] = []
    for width in widths:
        if not remaining:
            break
        line, next_remaining = _next_wrapped_line(
            remaining,
            draw,
            font,
            max(1.0, float(width)),
        )
        if not line:
            return lines, False
        lines.append(line)
        remaining = next_remaining
    return lines, not remaining.strip()


def _wrap_text_unlimited(
    text: str,
    draw: ImageDraw.ImageDraw,
    font: object,
    width: float,
) -> List[str]:
    remaining = str(text or "").strip()
    lines: List[str] = []
    while remaining:
        line, next_remaining = _next_wrapped_line(remaining, draw, font, width)
        if not line:
            # A single glyph wider than the available footer width is still retained.
            line, next_remaining = remaining[0], remaining[1:]
        lines.append(line)
        if next_remaining == remaining:
            break
        remaining = next_remaining
    return lines


def _text_height(draw: ImageDraw.ImageDraw, font: object, text: str) -> int:
    measured_text = re.sub(r"\s+", " ", str(text or "").strip()) or "Ag中"
    bbox = draw.textbbox((0, 0), measured_text, font=font)
    return max(1, int(bbox[3] - bbox[1]))


def _line_height(draw: ImageDraw.ImageDraw, font: object) -> int:
    return _text_height(draw, font, "Ag中")


def _text_line_heights(
    draw: ImageDraw.ImageDraw,
    font: object,
    lines: List[str],
) -> List[int]:
    return [_text_height(draw, font, line) for line in lines]


def _text_block_height(line_heights: List[int], line_gap: int) -> int:
    if not line_heights:
        return 0
    return sum(line_heights) + max(0, len(line_heights) - 1) * line_gap


def _bounded_vertical_padding(
    available_height: float,
    content_height: float,
    preferred_padding: int,
) -> Optional[int]:
    """Return the largest fitting padding without dropping below one pixel per side."""
    preferred = max(_MIN_VERTICAL_PLATE_PADDING, int(preferred_padding))
    for candidate in range(preferred, _MIN_VERTICAL_PLATE_PADDING - 1, -1):
        if float(content_height) + candidate * 2 <= float(available_height) + 0.01:
            return candidate
    return None


def _clamped_rect(
    min_x: object,
    min_y: object,
    max_x: object,
    max_y: object,
    image_w: int,
    image_h: int,
) -> Tuple[float, float, float, float]:
    x1 = max(0.0, min(float(min_x or 0), float(image_w)))
    y1 = max(0.0, min(float(min_y or 0), float(image_h)))
    x2 = max(x1 + 1.0, min(float(max_x or (x1 + 80)), float(image_w)))
    y2 = max(y1 + 1.0, min(float(max_y or (y1 + 20)), float(image_h)))
    return x1, y1, x2, y2


def _source_regions_from_row(
    row: object,
    image_w: int,
    image_h: int,
) -> List[Dict[str, object]]:
    raw_regions = row.get("Source Regions", ())
    regions: List[Dict[str, object]] = []
    if isinstance(raw_regions, (list, tuple)):
        for position, raw in enumerate(raw_regions):
            if not isinstance(raw, dict):
                continue
            rect = _clamped_rect(
                raw.get("min_x", 0),
                raw.get("min_y", 0),
                raw.get("max_x", 80),
                raw.get("max_y", 20),
                image_w,
                image_h,
            )
            region = dict(raw)
            region.update(
                {
                    "min_x": rect[0],
                    "min_y": rect[1],
                    "max_x": rect[2],
                    "max_y": rect[3],
                    "reading_order": int(raw.get("reading_order", position) or position),
                }
            )
            regions.append(region)
    if not regions:
        rect = _clamped_rect(
            row.get("min_x", 0),
            row.get("min_y", 0),
            row.get("max_x", 80),
            row.get("max_y", 20),
            image_w,
            image_h,
        )
        regions.append(
            {
                "source_segment_id": "",
                "visual_line_id": str(row.get("Visual Line ID", "")),
                "reading_order": int(row.get("Reading Order", 0) or 0),
                "member_boxes": (),
                "min_x": rect[0],
                "min_y": rect[1],
                "max_x": rect[2],
                "max_y": rect[3],
            }
        )
    return sorted(
        regions,
        key=lambda region: (
            int(region.get("reading_order", 0) or 0),
            float(region["min_y"]),
            float(region["min_x"]),
        ),
    )


def _representative_source_text_height(regions: List[Dict[str, object]]) -> float:
    """Use individual OCR member heights, never a multi-line union height."""
    heights: List[float] = []
    for region in regions:
        member_heights: List[float] = []
        raw_members = region.get("member_boxes", ()) or ()
        if isinstance(raw_members, (list, tuple)):
            for member in raw_members:
                if not isinstance(member, dict):
                    continue
                try:
                    height = float(member.get("max_y", 0)) - float(
                        member.get("min_y", 0)
                    )
                except (TypeError, ValueError):
                    continue
                if height > 0:
                    member_heights.append(height)
        if member_heights:
            heights.extend(member_heights)
            continue
        try:
            region_height = float(region["max_y"]) - float(region["min_y"])
        except (KeyError, TypeError, ValueError):
            continue
        if region_height > 0:
            heights.append(region_height)
    return float(statistics.median(heights)) if heights else 20.0


def _source_calibrated_font_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    source_height: float,
    output_mode: str,
) -> Tuple[int, OverlayFontResolution, int]:
    """Find the largest nominal size whose actual glyphs match source height."""
    limit = max(1.0, float(source_height)) + _SOURCE_GLYPH_HEIGHT_TOLERANCE_PX
    low = _ABSOLUTE_MIN_FONT_PX
    high = max(low, int(math.ceil(max(1.0, float(source_height)) * 2.0)))
    best = low
    best_resolution = _resolve_overlay_font(best, output_mode)
    best_height = _text_height(draw, best_resolution.font, text)
    while low <= high:
        candidate = (low + high) // 2
        resolution = _resolve_overlay_font(candidate, output_mode)
        measured_height = _text_height(draw, resolution.font, text)
        if measured_height <= limit:
            best = candidate
            best_resolution = resolution
            best_height = measured_height
            low = candidate + 1
        else:
            high = candidate - 1
    return best, best_resolution, best_height


def _rect_for_region(region: Dict[str, object]) -> Tuple[float, float, float, float]:
    return (
        float(region["min_x"]),
        float(region["min_y"]),
        float(region["max_x"]),
        float(region["max_y"]),
    )


def _horizontal_overlap(first: Tuple[float, float, float, float], second: Tuple[float, float, float, float]) -> bool:
    return max(first[0], second[0]) < min(first[2], second[2])


def _vertical_overlap(first: Tuple[float, float, float, float], second: Tuple[float, float, float, float]) -> bool:
    return max(first[1], second[1]) < min(first[3], second[3])


def _expanded_source_rect(
    rect: Tuple[float, float, float, float],
    image_w: int,
    padding: int,
    protected: List[Tuple[float, float, float, float]],
    *,
    use_full_row_cap: bool = False,
) -> Tuple[float, float, float, float]:
    source_width = max(1.0, rect[2] - rect[0])
    expansion_cap = (
        image_w * 0.20
        if use_full_row_cap
        else min(image_w * 0.20, source_width * 0.75)
    )
    right = min(float(image_w - padding), rect[2] + expansion_cap)
    for other in protected:
        if _vertical_overlap(rect, other) and other[0] >= rect[2]:
            right = min(right, other[0] - padding)
    return (
        max(0.0, rect[0] - padding),
        max(0.0, rect[1] - padding),
        min(float(image_w), max(rect[2] + padding, right)),
        rect[3] + padding,
    )


def _single_line_row_corridor(
    source: Tuple[float, float, float, float],
    horizontal: Tuple[float, float, float, float],
    image_h: int,
    protected: List[Tuple[float, float, float, float]],
    used: List[Tuple[float, float, float, float]],
) -> Tuple[
    Optional[Tuple[float, float, float, float]],
    Optional[Tuple[float, float, float, float]],
]:
    """Return collision-free vertical space for one source-anchored row."""
    top = 0.0
    bottom = float(image_h)
    nearest: Optional[Tuple[float, float, float, float]] = None
    horizontal_band = (horizontal[0], 0.0, horizontal[2], float(image_h))
    for other in protected + used:
        if not _horizontal_overlap(horizontal_band, other):
            continue
        if _rects_overlap(source, other):
            return None, other
        if other[3] <= source[1] and other[3] > top:
            top = other[3] + 0.5
            nearest = other
        elif other[1] >= source[3] and other[1] < bottom:
            bottom = other[1] - 0.5
            nearest = other
    if bottom <= top:
        return None, nearest
    return (horizontal[0], top, horizontal[2], bottom), nearest


def _single_line_plate(
    source: Tuple[float, float, float, float],
    horizontal: Tuple[float, float, float, float],
    corridor: Tuple[float, float, float, float],
    required_width: float,
    required_height: float,
    padding: int,
) -> Optional[Tuple[float, float, float, float]]:
    """Fit a one-line plate while covering its source and no neighboring row."""
    left = horizontal[0]
    minimum_right = source[2] + padding
    right = max(minimum_right, left + required_width)
    if right > horizontal[2] + 0.01:
        return None

    plate_height = max(source[3] - source[1], required_height)
    lowest_top = max(corridor[1], source[3] - plate_height)
    highest_top = min(source[1], corridor[3] - plate_height)
    if lowest_top > highest_top + 0.01:
        return None
    centered_top = ((source[1] + source[3]) - plate_height) / 2.0
    top = min(highest_top, max(lowest_top, centered_top))
    return (left, top, right, top + plate_height)


def _compound_source_corridor(
    source_rects: List[Tuple[float, float, float, float]],
    image_w: int,
    image_h: int,
    padding: int,
    protected: List[Tuple[float, float, float, float]],
    used: List[Tuple[float, float, float, float]],
) -> Tuple[
    Optional[Tuple[float, float, float, float]],
    Optional[Tuple[float, float, float, float]],
]:
    """Return safe shared geometry for one multi-line semantic unit.

    Horizontal reach reuses the existing per-line expansion limits. Vertical reach
    stops before the nearest protected region below the compound source. The final
    collision check keeps side-by-side or interleaved OCR content out of the plate.
    """
    if len(source_rects) < 2:
        return None, None

    expanded = [
        _expanded_source_rect(rect, image_w, padding, protected)
        for rect in source_rects
    ]
    left = min(rect[0] for rect in expanded)
    source_top = min(rect[1] for rect in source_rects)
    top = max(0.0, source_top - padding)
    right = max(rect[2] for rect in expanded)
    source_bottom = max(rect[3] for rect in source_rects)
    bottom = float(image_h - padding)
    blocking_region: Optional[Tuple[float, float, float, float]] = None

    for other in protected + used:
        if not _horizontal_overlap((left, top, right, bottom), other):
            continue
        if _rects_overlap(
            (left, source_top, right, source_bottom), other
        ):
            return None, other
        if other[3] <= source_top and other[3] + 0.5 > top:
            top = other[3] + 0.5
            blocking_region = other
        elif other[1] >= source_bottom and other[1] - 0.5 < bottom:
            bottom = other[1] - 0.5
            blocking_region = other

    bottom = max(source_bottom, bottom)
    corridor = (left, top, right, min(float(image_h), bottom))
    return corridor, blocking_region


def _corridor_line_capacity(
    corridor_height: float,
    line_height: int,
    vertical_padding: int,
    line_gap: int,
) -> int:
    usable = max(0.0, float(corridor_height) - vertical_padding * 2)
    return max(0, int((usable + line_gap) // (line_height + line_gap)))


def _candidate_collides(
    rects: List[Tuple[float, float, float, float]],
    protected: List[Tuple[float, float, float, float]],
    used: List[Tuple[float, float, float, float]],
) -> bool:
    return any(
        _rects_overlap(rect, other)
        for rect in rects
        for other in protected + used
    )


def _localized_footer_heading(output_mode: str) -> str:
    return {
        "Traditional Chinese": "完整翻譯",
        "Simplified Chinese": "完整翻译",
        "Japanese": "完全な翻訳",
    }.get(output_mode, "Complete translations")


def _localized_untrusted_footer(output_mode: str, original: str) -> str:
    template = {
        "Traditional Chinese": "未能驗證此翻譯；已保留原文：{source}",
        "Simplified Chinese": "无法验证此翻译；已保留原文：{source}",
        "Japanese": "翻訳を確認できなかったため、原文を保持しました：{source}",
    }.get(output_mode, "Translation could not be verified; original preserved: {source}")
    return template.format(source=original)


def _draw_plate(
    draw: ImageDraw.ImageDraw,
    rect: Tuple[float, float, float, float],
    radius: int,
    *,
    outline: Optional[Tuple[int, int, int]] = None,
) -> None:
    draw.rounded_rectangle(
        rect,
        radius=radius,
        fill=_PLATE_FILL,
        outline=outline,
        width=1 if outline else 0,
    )


def _draw_text_lines(
    draw: ImageDraw.ImageDraw,
    rect: Tuple[float, float, float, float],
    lines: List[str],
    font: object,
    line_heights: List[int],
    horizontal_padding: int,
    *,
    vertical_padding: Optional[int] = None,
    line_gap: Optional[int] = None,
) -> None:
    vertical_padding = (
        horizontal_padding if vertical_padding is None else vertical_padding
    )
    line_gap = (
        max(2, horizontal_padding // 2) if line_gap is None else line_gap
    )
    y = rect[1] + vertical_padding
    for line, line_height in zip(lines, line_heights):
        bbox = draw.textbbox((0, 0), line, font=font)
        draw.text(
            (rect[0] + horizontal_padding, y - bbox[1]),
            line,
            fill=_PLATE_TEXT,
            font=font,
        )
        y += line_height + line_gap


def _warning_badge_position(
    source: Tuple[float, float, float, float],
    width: float,
    height: float,
    image_w: int,
    image_h: int,
    protected: List[Tuple[float, float, float, float]],
    used: List[Tuple[float, float, float, float]],
) -> Optional[Tuple[float, float, float, float]]:
    candidates = [
        (source[2] + 4, source[1]),
        (source[0], source[1] - height - 4),
        (source[0], source[3] + 4),
        (source[0] - width - 4, source[1]),
    ]
    for x, y in candidates:
        if x < 2 or y < 2 or x + width > image_w - 2 or y + height > image_h - 2:
            continue
        rect = (x, y, x + width, y + height)
        if not any(_rects_overlap(rect, other) for other in protected + used + [source]):
            return rect
    return None


def _render_translation_footer(
    image: Image.Image,
    entries: List[Dict[str, str]],
    output_mode: str,
    font: object,
    marker_font: object,
    padding: int,
) -> Tuple[Image.Image, int]:
    if not entries:
        return image, 0
    width, height = image.size
    sizing = Image.new("RGB", (width, 1), _PLATE_FILL)
    sizing_draw = ImageDraw.Draw(sizing)
    heading = _localized_footer_heading(output_mode)
    heading_height = _text_height(sizing_draw, font, heading)
    marker_width = max(
        _text_width(sizing_draw, marker_font, entry["marker"])
        for entry in entries
    ) + padding * 2
    outer_padding = max(16, min(40, int(round(width * 0.03))))
    text_width = max(40.0, width - outer_padding * 2 - marker_width - padding)
    wrapped_entries = []
    content_height = outer_padding + heading_height + padding
    for entry in entries:
        lines = _wrap_text_unlimited(entry["text"], sizing_draw, font, text_width)
        line_heights = _text_line_heights(sizing_draw, font, lines)
        entry_height = max(
            _text_height(sizing_draw, marker_font, entry["marker"]),
            _text_block_height(line_heights, max(2, padding // 2)),
        )
        wrapped_entries.append((entry, lines, line_heights, entry_height))
        content_height += entry_height + padding * 2
    footer_height = int(math.ceil(content_height + outer_padding))

    output = Image.new("RGB", (width, height + footer_height), _PLATE_FILL)
    output.paste(image, (0, 0))
    draw = ImageDraw.Draw(output)
    separator_width = max(2, width // 360)
    draw.rectangle((0, height, width, height + separator_width), fill=_TEAL)
    y = height + outer_padding
    draw.text(
        (
            outer_padding,
            y - sizing_draw.textbbox((0, 0), heading, font=font)[1],
        ),
        heading,
        fill=_PLATE_TEXT,
        font=font,
    )
    y += heading_height + padding
    for entry, lines, line_heights, entry_height in wrapped_entries:
        marker_bbox = draw.textbbox((0, 0), entry["marker"], font=marker_font)
        draw.text(
            (outer_padding, y - marker_bbox[1]),
            entry["marker"],
            fill=_TEAL,
            font=marker_font,
        )
        text_y = y
        for line, line_height in zip(lines, line_heights):
            bbox = draw.textbbox((0, 0), line, font=font)
            draw.text(
                (
                    outer_padding + marker_width + padding,
                    text_y - bbox[1],
                ),
                line,
                fill=_PLATE_TEXT,
                font=font,
            )
            text_y += line_height + max(2, padding // 2)
        y += entry_height + padding * 2
    return output, footer_height


def _make_source_replacement_overlay(
    image: Image.Image,
    line_df: pd.DataFrame,
    output_mode: str,
    max_labels: int = 120,
    protected_ocr_rows: Optional[pd.DataFrame] = None,
) -> Tuple[Optional[Image.Image], str, pd.DataFrame]:
    if line_df is None or line_df.empty:
        return None, "", pd.DataFrame()
    started = time.perf_counter()
    request_warning = str(line_df.attrs.get("request_warning", "") or "").strip()
    annotated = pattern_document_engine.annotate_overlay_content(line_df)
    for column in ("Content Category", "Translation Trust"):
        line_df[column] = annotated[column].tolist()
    defaults = {
        "Overlay Marker": "",
        "Overlay State": "preserved",
        "Overflow Reason": "",
        "Footer Entry Type": "",
        "Overlay Font Size": 0,
        "Overlay Minimum Font Size": 0,
        "Overlay Wrapped Lines": 0,
        "Overlay Expansion X": 0.0,
        "Overlay Expansion Y": 0.0,
        "Overlay Collision": "",
        "Overlay Available Corridor Width": 0.0,
        "Overlay Available Corridor Height": 0.0,
        "Overlay Required Width": 0.0,
        "Overlay Required Height": 0.0,
        "Overlay Allowed Lines": 0,
        "Overlay Blocking Region": "",
        "Overlay Source Text Height": 0.0,
        "Overlay Calibrated Start Font Size": 0,
        "Overlay Font Family": "",
        "Overlay Font Path": "",
        "Overlay Font Face Index": "",
        "Overlay Font Weight": "",
    }
    for column, default in defaults.items():
        line_df[column] = default

    canvas = image.convert("RGB")
    width, height = canvas.size
    draw = ImageDraw.Draw(canvas)
    line_df["Overlay Minimum Font Size"] = _ABSOLUTE_MIN_FONT_PX
    image_font_resolution = _resolve_overlay_font(
        _ABSOLUTE_MIN_FONT_PX,
        output_mode,
    )
    padding = max(4, min(10, int(round(width * 0.004))))
    radius = max(4, padding + 1)

    source_regions = {
        position: _source_regions_from_row(line_df.iloc[position], width, height)
        for position in range(len(line_df))
    }
    all_source_rects = [
        (position, _rect_for_region(region))
        for position, regions in source_regions.items()
        for region in regions
    ]
    externally_protected_rects: List[Tuple[float, float, float, float]] = []
    if protected_ocr_rows is not None and not protected_ocr_rows.empty:
        for _, protected_row in protected_ocr_rows.iterrows():
            externally_protected_rects.append(
                _clamped_rect(
                    protected_row.get("min_x", 0),
                    protected_row.get("min_y", 0),
                    protected_row.get("max_x", 80),
                    protected_row.get("max_y", 20),
                    width,
                    height,
                )
            )
    ordered_positions = sorted(
        range(len(line_df)),
        key=lambda position: (
            float(line_df.iloc[position].get("min_y", 0) or 0),
            float(line_df.iloc[position].get("min_x", 0) or 0),
            str(line_df.iloc[position].get("Semantic Unit ID", "")),
        ),
    )
    used_slots: List[Tuple[float, float, float, float]] = []
    footer_entries: List[Dict[str, str]] = []
    legend_rows: List[Dict[str, object]] = []
    unit_diagnostics: List[Dict[str, object]] = []
    counts = {
        "replacement": 0,
        "expanded_replacement": 0,
        "overflow": 0,
        "warning_untrusted": 0,
        "preserved_excluded": 0,
    }
    collision_rejections = 0
    max_expansion_x = 0.0
    max_expansion_y = 0.0
    marker_number = 1
    processed = 0
    source_start_sizes: List[int] = []
    final_font_sizes: List[int] = []

    for position in ordered_positions:
        row = line_df.iloc[position]
        original = str(row.get("Original", "")).strip()
        translated = str(row.get("Translation", "")).strip()
        category = str(row.get("Content Category", "unchanged_non_language"))
        trust = str(row.get("Translation Trust", "source_preserved"))
        regions = source_regions[position]
        original_rects = [_rect_for_region(region) for region in regions]
        representative_source_height = _representative_source_text_height(regions)
        source_start_size, source_font_resolution, calibrated_glyph_height = (
            _source_calibrated_font_size(
                draw,
                translated or original,
                representative_source_height,
                output_mode,
            )
        )
        marker_font = source_font_resolution.font
        line_df.iloc[
            position,
            line_df.columns.get_loc("Overlay Source Text Height"),
        ] = round(representative_source_height, 2)
        line_df.iloc[
            position,
            line_df.columns.get_loc("Overlay Calibrated Start Font Size"),
        ] = source_start_size
        line_df.iloc[
            position,
            line_df.columns.get_loc("Overlay Font Family"),
        ] = source_font_resolution.family
        line_df.iloc[
            position,
            line_df.columns.get_loc("Overlay Font Path"),
        ] = source_font_resolution.path
        line_df.iloc[
            position,
            line_df.columns.get_loc("Overlay Font Face Index"),
        ] = (
            ""
            if source_font_resolution.face_index is None
            else source_font_resolution.face_index
        )
        line_df.iloc[
            position,
            line_df.columns.get_loc("Overlay Font Weight"),
        ] = source_font_resolution.weight
        protected = [
            rect for owner, rect in all_source_rects if owner != position
        ] + externally_protected_rects
        raw_segment_ids = row.get("Source Segment IDs", ())
        source_segment_ids = (
            tuple(raw_segment_ids)
            if isinstance(raw_segment_ids, (list, tuple))
            else ()
        )
        diagnostic = {
            "semantic_unit_id": str(row.get("Semantic Unit ID", "")),
            "source_segment_ids": source_segment_ids,
            "source_region_count": len(regions),
            "member_box_count": sum(
                len(region.get("member_boxes", ()) or ()) for region in regions
            ),
            "content_category": category,
            "trust_status": trust,
            "protected_identity_span_count": int(
                row.get("Protected Identity Span Count", 0) or 0
            ),
            "protected_identity_spans": tuple(
                row.get("Protected Identity Spans", ()) or ()
            ),
            "protected_identity_status": str(
                row.get("Protected Identity Status", "not_applicable")
            ),
            "overlay_state": "preserved",
            "baseline_font_size": source_start_size,
            "representative_source_text_height": round(
                representative_source_height,
                2,
            ),
            "calibrated_start_font_size": source_start_size,
            "calibrated_glyph_height": calibrated_glyph_height,
            "absolute_minimum_font_size": _ABSOLUTE_MIN_FONT_PX,
            "minimum_font_size": _ABSOLUTE_MIN_FONT_PX,
            "font_family": source_font_resolution.family,
            "font_path": source_font_resolution.path,
            "font_face_index": source_font_resolution.face_index,
            "font_weight": source_font_resolution.weight,
            "target_language": source_font_resolution.target_language,
            "final_font_size": 0,
            "wrapped_line_count": 0,
            "expansion_x": 0.0,
            "expansion_y": 0.0,
            "collision_decision": "not_applicable",
            "overflow_reason": "",
            "marker": "",
            "available_corridor_width": 0.0,
            "available_corridor_height": 0.0,
            "required_rendered_width": 0.0,
            "required_rendered_height": 0.0,
            "allowed_line_count": 0,
            "actual_wrapped_line_count": 0,
            "blocking_protected_region": "",
        }

        if category not in {"translated_content", "mixed_protected_translation"}:
            counts["preserved_excluded"] += 1
            unit_diagnostics.append(diagnostic)
            continue
        source_start_sizes.append(source_start_size)
        if processed >= max_labels:
            trust = "trusted"
            translated = translated or original
            overflow_reason = "maximum_unit_limit"
        else:
            overflow_reason = ""
        processed += 1

        if trust != "trusted":
            marker = f"[{marker_number}]"
            marker_number += 1
            marker_bbox = draw.textbbox((0, 0), marker, font=marker_font)
            marker_width = marker_bbox[2] - marker_bbox[0] + padding * 2
            marker_height = marker_bbox[3] - marker_bbox[1] + padding * 2
            badge = _warning_badge_position(
                original_rects[0],
                marker_width,
                marker_height,
                width,
                height,
                protected,
                used_slots,
            )
            if badge is None:
                line_df.iloc[position, line_df.columns.get_loc("Overlay State")] = "preserved_unsupported"
                line_df.iloc[position, line_df.columns.get_loc("Overflow Reason")] = "warning_badge_collision"
                line_df.iloc[position, line_df.columns.get_loc("Overlay Collision")] = "rejected"
                counts["preserved_excluded"] += 1
                collision_rejections += 1
                diagnostic.update(
                    {
                        "overlay_state": "preserved_unsupported",
                        "collision_decision": "rejected",
                        "overflow_reason": "warning_badge_collision",
                    }
                )
                unit_diagnostics.append(diagnostic)
                continue
            _draw_plate(draw, badge, radius, outline=_WARNING)
            draw.text(
                (
                    badge[0] + padding,
                    badge[1] + padding - marker_bbox[1],
                ),
                marker,
                fill=_WARNING,
                font=marker_font,
            )
            used_slots.append(badge)
            footer_text = _localized_untrusted_footer(output_mode, original)
            footer_entries.append({"marker": marker, "text": footer_text, "type": "warning"})
            line_df.iloc[position, line_df.columns.get_loc("Overlay Marker")] = marker
            line_df.iloc[position, line_df.columns.get_loc("Overlay State")] = "warning_untrusted"
            line_df.iloc[position, line_df.columns.get_loc("Overflow Reason")] = "translation_untrusted"
            line_df.iloc[position, line_df.columns.get_loc("Footer Entry Type")] = "warning"
            line_df.iloc[position, line_df.columns.get_loc("Overlay Font Size")] = source_start_size
            counts["warning_untrusted"] += 1
            final_font_sizes.append(source_start_size)
            diagnostic.update(
                {
                    "overlay_state": "warning_untrusted",
                    "final_font_size": source_start_size,
                    "collision_decision": "accepted",
                    "overflow_reason": "translation_untrusted",
                    "marker": marker,
                }
            )
            legend_rows.append(
                {
                    "Marker": marker,
                    "Original": original,
                    "Translation": footer_text,
                    "Overlay": "warning_untrusted",
                    "Confidence": row.get("Confidence", ""),
                }
            )
            unit_diagnostics.append(diagnostic)
            continue

        horizontal_geometry = all(
            (rect[2] - rect[0]) >= (rect[3] - rect[1]) * 1.2
            for rect in original_rects
        )
        selected_layout = None
        fit_reason = overflow_reason or ("unsupported_geometry" if not horizontal_geometry else "text_did_not_fit")
        if horizontal_geometry and not overflow_reason:
            candidate_modes = []
            for font_size in _replacement_font_candidates(
                source_start_size, _ABSOLUTE_MIN_FONT_PX
            ):
                candidate_modes.extend(
                    ((font_size, False), (font_size, True))
                )
            for font_size, allow_expansion in candidate_modes:
                font_resolution = _resolve_overlay_font(font_size, output_mode)
                font = font_resolution.font
                short_single_source_row = (
                    len(regions) == 1
                    and "\n" not in original
                )
                expanded_rects = (
                    [
                        _expanded_source_rect(
                            rect,
                            width,
                            padding,
                            protected,
                            use_full_row_cap=short_single_source_row,
                        )
                        for rect in original_rects
                    ]
                    if allow_expansion
                    else [
                        (
                            max(0.0, rect[0] - padding),
                            max(0.0, rect[1] - padding),
                            min(float(width), rect[2] + padding),
                            min(float(height), rect[3] + padding),
                        )
                        for rect in original_rects
                    ]
                )
                prose = pattern_document_engine.overlay_content_layout(original) == "prose"
                text_padding = (
                    max(1, padding // 2)
                    if short_single_source_row
                    else padding
                )
                if short_single_source_row and allow_expansion:
                    current = expanded_rects[0]
                    expanded_rects[0] = (
                        current[0],
                        current[1],
                        min(float(width), current[2] + padding),
                        current[3],
                    )
                max_lines = (
                    1
                    if short_single_source_row
                    else (min(4, len(regions) + 1) if prose else 2)
                )
                if len(regions) == 1:
                    widths = [
                        expanded_rects[0][2]
                        - expanded_rects[0][0]
                        - text_padding * 2
                    ] * max_lines
                else:
                    widths = [rect[2] - rect[0] - padding * 2 for rect in expanded_rects]
                    if max_lines > len(widths):
                        widths.append(widths[-1])
                lines, complete = _wrap_text_to_widths(translated, draw, font, widths[:max_lines])
                if not complete or not lines:
                    continue
                line_heights = _text_line_heights(draw, font, lines)

                plate_rects = list(expanded_rects)
                fit_metrics = {}
                if len(regions) == 1:
                    if len(lines) == 1:
                        required_width = (
                            _text_width(draw, font, lines[0])
                            + text_padding * 2
                        )
                        corridor, blocking_region = _single_line_row_corridor(
                            original_rects[0],
                            plate_rects[0],
                            height,
                            protected,
                            used_slots,
                        )
                        available_width = (
                            plate_rects[0][2] - plate_rects[0][0]
                        )
                        available_height = (
                            corridor[3] - corridor[1]
                            if corridor is not None
                            else 0.0
                        )
                        vertical_padding = _bounded_vertical_padding(
                            available_height,
                            line_heights[0],
                            text_padding,
                        )
                        required_height = line_heights[0] + (
                            vertical_padding
                            if vertical_padding is not None
                            else _MIN_VERTICAL_PLATE_PADDING
                        ) * 2
                        fit_metrics = {
                            "available_corridor_width": round(
                                available_width, 1
                            ),
                            "available_corridor_height": round(
                                available_height, 1
                            ),
                            "required_rendered_width": round(
                                required_width, 1
                            ),
                            "required_rendered_height": round(
                                required_height, 1
                            ),
                            "allowed_line_count": 1,
                            "actual_wrapped_line_count": 1,
                            "blocking_protected_region": (
                                tuple(
                                    round(value, 1)
                                    for value in blocking_region
                                )
                                if blocking_region is not None
                                else ""
                            ),
                            "text_padding": text_padding,
                            "vertical_padding": vertical_padding,
                        }
                        diagnostic.update(fit_metrics)
                        if corridor is None:
                            fit_reason = "protected_region_collision"
                            collision_rejections += 1
                            continue
                        if vertical_padding is None:
                            fit_reason = "single_line_corridor_fit"
                            continue
                        plate = _single_line_plate(
                            original_rects[0],
                            plate_rects[0],
                            corridor,
                            required_width,
                            required_height,
                            padding,
                        )
                        if plate is None:
                            fit_reason = "single_line_corridor_fit"
                            continue
                        plate_rects[0] = plate
                    else:
                        required_height = (
                            _text_block_height(
                                line_heights,
                                max(2, padding // 2),
                            )
                            + padding * 2
                        )
                        current = plate_rects[0]
                        needed_bottom = max(
                            current[3], current[1] + required_height
                        )
                        if (
                            needed_bottom
                            - (original_rects[0][3] + padding)
                            > source_start_size
                        ):
                            continue
                        plate_rects[0] = (
                            current[0],
                            current[1],
                            current[2],
                            min(float(height), needed_bottom),
                        )
                else:
                    for rect_index, current in enumerate(list(plate_rects)):
                        corresponding_height = line_heights[
                            min(rect_index, len(line_heights) - 1)
                        ]
                        needed_bottom = max(
                            current[3],
                            current[1] + corresponding_height + padding * 2,
                        )
                        if needed_bottom - (original_rects[rect_index][3] + padding) > source_start_size:
                            plate_rects = []
                            break
                        plate_rects[rect_index] = (
                            current[0], current[1], current[2], min(float(height), needed_bottom)
                        )
                    if not plate_rects:
                        continue
                    if len(lines) > len(plate_rects):
                        last = plate_rects[-1]
                        extra = (
                            last[0],
                            last[3],
                            last[2],
                            min(
                                float(height),
                                last[3]
                                + line_heights[-1]
                                + padding * 2,
                            ),
                        )
                        if extra[3] - last[3] > source_start_size + padding * 2:
                            continue
                        plate_rects.append(extra)

                if _candidate_collides(plate_rects, protected, used_slots):
                    collision_rejections += 1
                    fit_reason = "protected_region_collision"
                    continue
                selected_layout = (
                    font_size,
                    font_resolution,
                    line_heights,
                    lines,
                    plate_rects,
                    "per_region",
                    fit_metrics,
                )
                break

            if selected_layout is None and len(regions) > 1:
                for font_size in _replacement_font_candidates(
                    source_start_size, _ABSOLUTE_MIN_FONT_PX
                ):
                    font_resolution = _resolve_overlay_font(font_size, output_mode)
                    font = font_resolution.font
                    corridor, blocking_region = _compound_source_corridor(
                        original_rects,
                        width,
                        height,
                        padding,
                        protected,
                        used_slots,
                    )
                    if corridor is None:
                        fit_reason = "compound_corridor_collision"
                        if blocking_region is not None:
                            diagnostic["blocking_protected_region"] = tuple(
                                round(value, 1) for value in blocking_region
                            )
                        continue
                    corridor_width = corridor[2] - corridor[0]
                    corridor_height = corridor[3] - corridor[1]
                    inner_width = max(1.0, corridor_width - padding * 2)
                    wrapped = _wrap_text_unlimited(
                        translated,
                        draw,
                        font,
                        inner_width,
                    )
                    line_gap = max(2, padding // 2)
                    line_heights = _text_line_heights(draw, font, wrapped)
                    text_height = _text_block_height(line_heights, line_gap)
                    vertical_padding = _bounded_vertical_padding(
                        corridor_height,
                        text_height,
                        padding,
                    )
                    capacity_padding = (
                        vertical_padding
                        if vertical_padding is not None
                        else _MIN_VERTICAL_PLATE_PADDING
                    )
                    allowed_lines = _corridor_line_capacity(
                        corridor_height,
                        max(line_heights, default=1),
                        capacity_padding,
                        line_gap,
                    )
                    required_width = (
                        max(
                            (_text_width(draw, font, line) for line in wrapped),
                            default=0.0,
                        )
                        + padding * 2
                    )
                    required_height = text_height + capacity_padding * 2
                    metrics = {
                        "available_corridor_width": round(corridor_width, 1),
                        "available_corridor_height": round(corridor_height, 1),
                        "required_rendered_width": round(required_width, 1),
                        "required_rendered_height": round(required_height, 1),
                        "allowed_line_count": allowed_lines,
                        "actual_wrapped_line_count": len(wrapped),
                        "text_padding": padding,
                        "vertical_padding": vertical_padding,
                        "line_gap": line_gap,
                        "blocking_protected_region": (
                            tuple(round(value, 1) for value in blocking_region)
                            if blocking_region is not None
                            else ""
                        ),
                    }
                    diagnostic.update(metrics)
                    if (
                        not wrapped
                        or vertical_padding is None
                        or len(wrapped) > allowed_lines
                    ):
                        fit_reason = "compound_corridor_height"
                        continue
                    needed_bottom = max(
                        max(rect[3] for rect in original_rects) + padding,
                        corridor[1] + required_height,
                    )
                    plate = (
                        corridor[0],
                        corridor[1],
                        corridor[2],
                        min(corridor[3], needed_bottom),
                    )
                    if _candidate_collides([plate], protected, used_slots):
                        collision_rejections += 1
                        fit_reason = "compound_corridor_collision"
                        continue
                    selected_layout = (
                        font_size,
                        font_resolution,
                        line_heights,
                        wrapped,
                        [plate],
                        "compound",
                        metrics,
                    )
                    break

        if selected_layout is not None:
            (
                font_size,
                font_resolution,
                line_heights,
                lines,
                plate_rects,
                layout_kind,
                fit_metrics,
            ) = selected_layout
            font = font_resolution.font
            for rect in plate_rects:
                _draw_plate(draw, rect, radius)
            if len(regions) == 1 or layout_kind == "compound":
                _draw_text_lines(
                    draw,
                    plate_rects[0],
                    lines,
                    font,
                    line_heights,
                    int(fit_metrics.get("text_padding", padding)),
                    vertical_padding=int(
                        fit_metrics.get("vertical_padding", padding)
                    ),
                    line_gap=int(
                        fit_metrics.get("line_gap", max(2, padding // 2))
                    ),
                )
            else:
                for line_index, line in enumerate(lines):
                    _draw_text_lines(
                        draw,
                        plate_rects[min(line_index, len(plate_rects) - 1)],
                        [line],
                        font,
                        [line_heights[min(line_index, len(line_heights) - 1)]],
                        padding,
                    )
            used_slots.extend(plate_rects)
            if layout_kind == "compound":
                expansion_x = max(
                    0.0,
                    plate_rects[0][2] - max(source[2] for source in original_rects),
                )
                expansion_y = max(
                    0.0,
                    plate_rects[0][3] - max(source[3] for source in original_rects),
                )
            else:
                expansion_x = max(
                    max(0.0, plate[2] - source[2])
                    for plate, source in zip(plate_rects, original_rects)
                )
                expansion_y = max(
                    max(0.0, plate[3] - source[3])
                    for plate, source in zip(plate_rects, original_rects)
                )
            expanded = expansion_x > padding + 0.1 or expansion_y > padding + 0.1
            state = "expanded_replacement" if expanded else "replacement"
            counts[state] += 1
            final_font_sizes.append(font_size)
            max_expansion_x = max(max_expansion_x, expansion_x)
            max_expansion_y = max(max_expansion_y, expansion_y)
            line_df.iloc[position, line_df.columns.get_loc("Overlay State")] = state
            line_df.iloc[position, line_df.columns.get_loc("Overlay Font Size")] = font_size
            line_df.iloc[position, line_df.columns.get_loc("Overlay Wrapped Lines")] = len(lines)
            line_df.iloc[position, line_df.columns.get_loc("Overlay Expansion X")] = round(expansion_x, 1)
            line_df.iloc[position, line_df.columns.get_loc("Overlay Expansion Y")] = round(expansion_y, 1)
            line_df.iloc[position, line_df.columns.get_loc("Overlay Collision")] = "accepted"
            if fit_metrics:
                line_df.iloc[position, line_df.columns.get_loc("Overlay Available Corridor Width")] = fit_metrics["available_corridor_width"]
                line_df.iloc[position, line_df.columns.get_loc("Overlay Available Corridor Height")] = fit_metrics["available_corridor_height"]
                line_df.iloc[position, line_df.columns.get_loc("Overlay Required Width")] = fit_metrics["required_rendered_width"]
                line_df.iloc[position, line_df.columns.get_loc("Overlay Required Height")] = fit_metrics["required_rendered_height"]
                line_df.iloc[position, line_df.columns.get_loc("Overlay Allowed Lines")] = fit_metrics["allowed_line_count"]
                line_df.iloc[position, line_df.columns.get_loc("Overlay Blocking Region")] = str(fit_metrics["blocking_protected_region"])
            diagnostic.update(
                {
                    "overlay_state": state,
                    "final_font_size": font_size,
                    "wrapped_line_count": len(lines),
                    "expansion_x": round(expansion_x, 1),
                    "expansion_y": round(expansion_y, 1),
                    "collision_decision": "accepted",
                    "font_family": font_resolution.family,
                    "font_path": font_resolution.path,
                    "font_face_index": font_resolution.face_index,
                    "font_weight": font_resolution.weight,
                    **fit_metrics,
                }
            )
            legend_rows.append(
                {
                    "Marker": "",
                    "Original": original,
                    "Translation": translated,
                    "Overlay": state,
                    "Confidence": row.get("Confidence", ""),
                }
            )
            unit_diagnostics.append(diagnostic)
            continue

        marker = f"[{marker_number}]"
        marker_number += 1
        overflow_rects = []
        for source in original_rects:
            padded = _pad_rect(source, padding)
            padded = (
                max(0.0, padded[0]),
                max(0.0, padded[1]),
                min(float(width), padded[2]),
                min(float(height), padded[3]),
            )
            if any(_rects_overlap(padded, other) for other in protected + used_slots):
                padded = source
            overflow_rects.append(padded)
        if _candidate_collides(overflow_rects, protected, used_slots):
            line_df.iloc[position, line_df.columns.get_loc("Overlay State")] = "preserved_unsupported"
            line_df.iloc[position, line_df.columns.get_loc("Overflow Reason")] = "source_region_collision"
            line_df.iloc[position, line_df.columns.get_loc("Overlay Collision")] = "rejected"
            counts["preserved_excluded"] += 1
            collision_rejections += 1
            diagnostic.update(
                {
                    "overlay_state": "preserved_unsupported",
                    "collision_decision": "rejected",
                    "overflow_reason": "source_region_collision",
                }
            )
            unit_diagnostics.append(diagnostic)
            continue
        for rect in overflow_rects:
            _draw_plate(draw, rect, radius)
        marker_bbox = draw.textbbox((0, 0), marker, font=marker_font)
        first_rect = overflow_rects[0]
        marker_x = first_rect[0] + padding
        marker_ink_y = first_rect[1] + max(
            padding,
            ((first_rect[3] - first_rect[1]) - (marker_bbox[3] - marker_bbox[1])) / 2.0,
        )
        draw.text(
            (marker_x, marker_ink_y - marker_bbox[1]),
            marker,
            fill=_TEAL,
            font=marker_font,
        )
        used_slots.extend(overflow_rects)
        footer_entries.append({"marker": marker, "text": translated, "type": "overflow"})
        line_df.iloc[position, line_df.columns.get_loc("Overlay Marker")] = marker
        line_df.iloc[position, line_df.columns.get_loc("Overlay State")] = "overflow"
        line_df.iloc[position, line_df.columns.get_loc("Overflow Reason")] = fit_reason
        line_df.iloc[position, line_df.columns.get_loc("Footer Entry Type")] = "overflow"
        line_df.iloc[position, line_df.columns.get_loc("Overlay Font Size")] = _ABSOLUTE_MIN_FONT_PX
        line_df.iloc[position, line_df.columns.get_loc("Overlay Wrapped Lines")] = 1
        line_df.iloc[position, line_df.columns.get_loc("Overlay Collision")] = "accepted"
        line_df.iloc[position, line_df.columns.get_loc("Overlay Available Corridor Width")] = diagnostic["available_corridor_width"]
        line_df.iloc[position, line_df.columns.get_loc("Overlay Available Corridor Height")] = diagnostic["available_corridor_height"]
        line_df.iloc[position, line_df.columns.get_loc("Overlay Required Width")] = diagnostic["required_rendered_width"]
        line_df.iloc[position, line_df.columns.get_loc("Overlay Required Height")] = diagnostic["required_rendered_height"]
        line_df.iloc[position, line_df.columns.get_loc("Overlay Allowed Lines")] = diagnostic["allowed_line_count"]
        line_df.iloc[position, line_df.columns.get_loc("Overlay Blocking Region")] = str(diagnostic["blocking_protected_region"])
        counts["overflow"] += 1
        final_font_sizes.append(_ABSOLUTE_MIN_FONT_PX)
        diagnostic.update(
            {
                "overlay_state": "overflow",
                "final_font_size": _ABSOLUTE_MIN_FONT_PX,
                "wrapped_line_count": 1,
                "collision_decision": "accepted",
                "overflow_reason": fit_reason,
                "marker": marker,
            }
        )
        legend_rows.append(
            {
                "Marker": marker,
                "Original": original,
                "Translation": translated,
                "Overlay": "overflow",
                "Confidence": row.get("Confidence", ""),
            }
        )
        unit_diagnostics.append(diagnostic)

    drawn_count = counts["replacement"] + counts["expanded_replacement"] + counts["overflow"] + counts["warning_untrusted"]
    resolver_summary = {
        "target_language": image_font_resolution.target_language,
        "font_family": image_font_resolution.family,
        "font_path": image_font_resolution.path,
        "font_face_index": image_font_resolution.face_index,
        "font_weight": image_font_resolution.weight,
    }
    final_size_summary = {
        "minimum": min(final_font_sizes) if final_font_sizes else 0,
        "maximum": max(final_font_sizes) if final_font_sizes else 0,
        "median": (
            float(statistics.median(final_font_sizes))
            if final_font_sizes
            else 0.0
        ),
    }
    if drawn_count == 0:
        line_df.attrs["overlay_renderer_diagnostics"] = {
            "renderer": "source_replacement",
            "original_dimensions": (width, height),
            "final_dimensions": (width, height),
            "footer_entry_count": 0,
            "footer_height": 0,
            **counts,
            "max_expansion_x": 0.0,
            "max_expansion_y": 0.0,
            "protected_region_collision_rejections": collision_rejections,
            "font_resolver": resolver_summary,
            "absolute_minimum_font_size": _ABSOLUTE_MIN_FONT_PX,
            "final_font_size_summary": final_size_summary,
            "overlay_generation_time": round(time.perf_counter() - started, 4),
            "units": unit_diagnostics,
        }
        return None, request_warning, pd.DataFrame()

    footer_size = max(
        _ABSOLUTE_MIN_FONT_PX,
        int(round(statistics.median(source_start_sizes)))
        if source_start_sizes
        else _ABSOLUTE_MIN_FONT_PX,
    )
    footer_resolution = _resolve_overlay_font(footer_size, output_mode)
    final_image, footer_height = _render_translation_footer(
        canvas,
        footer_entries,
        output_mode,
        footer_resolution.font,
        footer_resolution.font,
        padding,
    )
    diagnostics = {
        "renderer": "source_replacement",
        "original_dimensions": (width, height),
        "final_dimensions": final_image.size,
        "footer_entry_count": len(footer_entries),
        "footer_height": footer_height,
        **counts,
        "max_expansion_x": round(max_expansion_x, 1),
        "max_expansion_y": round(max_expansion_y, 1),
        "protected_region_collision_rejections": collision_rejections,
        "font_resolver": resolver_summary,
        "footer_font_size": footer_size,
        "absolute_minimum_font_size": _ABSOLUTE_MIN_FONT_PX,
        "final_font_size_summary": final_size_summary,
        "overlay_generation_time": round(time.perf_counter() - started, 4),
        "units": unit_diagnostics,
    }
    line_df.attrs["overlay_renderer_diagnostics"] = diagnostics
    legend_df = pd.DataFrame(legend_rows)
    legend_lines = []
    if request_warning:
        legend_lines.append(request_warning)
    for entry in legend_rows:
        prefix = f"{entry['Marker']} " if entry["Marker"] else ""
        legend_lines.append(
            f"{prefix}{entry['Original']} → {entry['Translation']}".strip()
        )
    return final_image, "\n".join(legend_lines), legend_df


@profile_function("overlay label preparation", "make_line_translation_overlay calls")
def make_line_translation_overlay(
    image: Image.Image,
    line_df: pd.DataFrame,
    output_mode: str,
    max_labels: int = 120,
    max_full_label_chars: int = 42,
    scale_to_source_text: bool = False,
    protected_ocr_rows: Optional[pd.DataFrame] = None,
) -> Tuple[Optional[Image.Image], str, pd.DataFrame]:
    """Render the legacy overlay or the complete feature-gated replacement mode."""
    if is_source_replacement_overlay_enabled():
        return _make_source_replacement_overlay(
            image,
            line_df,
            output_mode,
            max_labels=max_labels,
            protected_ocr_rows=protected_ocr_rows,
        )
    return _make_legacy_line_translation_overlay(
        image,
        line_df,
        output_mode,
        max_labels=max_labels,
        max_full_label_chars=max_full_label_chars,
        scale_to_source_text=scale_to_source_text,
    )


def image_to_png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
