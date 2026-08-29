"""Overlay rendering engine for the Pattern Translator.

This module owns pure image overlay generation: font loading, label wrapping,
collision checks, marker placement, legend generation, and PNG byte encoding.
It intentionally does not depend on Streamlit, session state, downloads,
analytics, UI localization, or deployment configuration.
"""

import io
import re
import time
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from pattern_translator.engine import line_translation as line_translation_engine
from pattern_translator.engine import terminology as terminology_engine


ProfileGetter = Callable[[], object]
ProfileCount = Callable[[str, float], None]
ProfileAddTime = Callable[[str, float], None]

_profile_getter: ProfileGetter = lambda: None
_profile_count_func: ProfileCount = lambda name, amount=1.0: None
_profile_add_time_func: ProfileAddTime = lambda name, seconds: None


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


def _load_overlay_font(size: int):
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
    font = _load_overlay_font(font_size)
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


@profile_function("overlay label preparation", "make_line_translation_overlay calls")
def make_line_translation_overlay(
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

    img = image.convert("RGBA")
    w, h = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_size = line_overlay_font_size(w, line_df, scale_to_source_text)
    font = _load_overlay_font(font_size)
    marker_font = _load_overlay_font(max(font_size, 20))

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
