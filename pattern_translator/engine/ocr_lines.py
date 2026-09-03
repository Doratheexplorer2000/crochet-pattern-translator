"""OCR visual-line assembly for the Pattern Translator.

This module owns the deterministic conversion from OCR box rows into translated
line records. It does not initialize or execute OCR, preprocess images, manage
Streamlit state, render overlays, or perform downloads.
"""

import re
import time
from typing import Callable, Dict, Optional

import pandas as pd

from pattern_translator.engine import broad_translation
from pattern_translator.engine import line_translation
from pattern_translator.engine import llm_fallback
from pattern_translator.engine import pattern_document
from pattern_translator.engine import shadow_title_classifier
from pattern_translator.engine import terminology


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
    """Attach app-level profiling without depending on Streamlit."""
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


def merge_ocr_boxes_into_visual_lines(ocr_rows: pd.DataFrame) -> pd.DataFrame:
    """Merge PaddleOCR text boxes that sit on the same visual line.

    PaddleOCR often returns English pattern rows as separate boxes:
        "Rnd 2:"   "6 inc around"   "(12)"
    Group boxes by vertical position, then merge nearby boxes left-to-right
    while avoiding large column gaps.
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
        for _, row in line.iterrows():
            min_x = float(row.get("min_x", row.get("x", 0)) or 0)
            if cluster and last_max_x is not None and min_x - last_max_x > gap_threshold:
                merged_records.append(_merge_ocr_cluster(cluster))
                cluster = []
            cluster.append(row)
            last_max_x = float(row.get("max_x", row.get("x", min_x) + 80) or (min_x + 80))
        if cluster:
            merged_records.append(_merge_ocr_cluster(cluster))

    out = pd.DataFrame(merged_records)
    if out.empty:
        return rows.drop(columns=[c for c in ["_cy", "_h"] if c in rows.columns], errors="ignore")
    return out.sort_values(["min_y", "min_x"]).reset_index(drop=True)


def _merge_ocr_cluster(cluster: list) -> Dict[str, object]:
    texts = [str(row.get("text", "")).strip() for row in cluster if str(row.get("text", "")).strip()]
    text = " ".join(texts)
    text = re.sub(r"\s+([:：,，;；)])", r"\1", text)
    text = re.sub(r"([(（])\s+", r"\1", text)
    text = re.sub(r"\b(Rnd|R)\s+(\d)", r"\1 \2", text, flags=re.I)
    confs = [float(row.get("confidence", 0) or 0) for row in cluster]
    min_x = min(float(row.get("min_x", row.get("x", 0)) or 0) for row in cluster)
    max_x = max(float(row.get("max_x", row.get("x", 0) + 80) or 80) for row in cluster)
    min_y = min(float(row.get("min_y", row.get("y", 0)) or 0) for row in cluster)
    max_y = max(float(row.get("max_y", row.get("y", 0) + 20) or 20) for row in cluster)
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
def build_ocr_line_translations(
    ocr_rows: pd.DataFrame,
    index: Dict[str, int],
    df: pd.DataFrame,
    output_mode: str,
    source_mode: str,
    llm_provider: Optional[llm_fallback.Provider] = None,
    diagnostic_logger: Optional[llm_fallback.DiagnosticLogger] = None,
) -> pd.DataFrame:
    if ocr_rows is None or ocr_rows.empty:
        return pd.DataFrame()

    rows = merge_ocr_boxes_into_visual_lines(ocr_rows)
    rows["confidence"] = pd.to_numeric(rows.get("confidence", 0), errors="coerce").fillna(0)
    rows = rows.sort_values(["min_y", "min_x"]).reset_index(drop=True)
    _profile_count("merged OCR lines", len(rows))

    if (
        broad_translation.is_broad_translation_enabled()
        and broad_translation.is_broad_translation_route(source_mode, output_mode)
    ):
        return broad_translation.translate_merged_ocr_lines_broad(
            rows,
            source_mode=source_mode,
            output_mode=output_mode,
            diagnostic_logger=diagnostic_logger,
            profile_count=_profile_count,
            profile_add_time=_profile_add_time,
        )

    deterministic_start = time.perf_counter()
    if diagnostic_logger is not None:
        diagnostic_logger("deterministic_translation_begin")
    prepared = []
    for _, row in rows.iterrows():
        original = str(row.get("text", "")).strip()
        if not original:
            continue
        _profile_count("OCR lines processed")
        cleaned = line_translation.clean_single_ocr_line(original)
        translated = line_translation.translate_ocr_line(cleaned, index, df, output_mode)
        prepared.append((row, cleaned, translated))
    if diagnostic_logger is not None:
        diagnostic_logger(
            "deterministic_translation_end",
            elapsed_seconds=time.perf_counter() - deterministic_start,
            visual_line_count=len(prepared),
            outcome="success",
        )

    cleaned_lines = [cleaned for _row, cleaned, _translated in prepared]
    shadow_title_classifier.record_shadow_comparison_if_enabled(
        cleaned_lines=cleaned_lines,
    )
    title_contexts = []
    for position, (_row, cleaned, _translated) in enumerate(prepared):
        nearby_lines = [
            prepared[nearby_position][1]
            for nearby_position in range(max(0, position - 2), min(len(prepared), position + 3))
            if nearby_position != position
        ]
        title_contexts.append(
            pattern_document.is_title_heading_context(cleaned, nearby_lines)
        )

    llm_df = df
    llm_inputs = [translated for _row, _cleaned, translated in prepared]
    semantic_context = ""
    semantic_context_start = time.perf_counter()
    if diagnostic_logger is not None:
        diagnostic_logger("semantic_context_begin")
    if llm_provider is not None:
        llm_index, llm_df = llm_fallback.structural_terminology_view(index, df)
        structural_inputs = [
            line_translation.translate_ocr_line(cleaned, llm_index, llm_df, output_mode)
            for _row, cleaned, _translated in prepared
        ]
        llm_inputs = [
            translated if title_contexts[position] else structural_inputs[position]
            for position, (_row, _cleaned, translated) in enumerate(prepared)
        ]
        semantic_context = llm_fallback.build_translation_scope_context(
            structural_inputs, llm_df, output_mode
        )
    if diagnostic_logger is not None:
        diagnostic_logger(
            "semantic_context_end",
            elapsed_seconds=time.perf_counter() - semantic_context_start,
            outcome="success" if llm_provider is not None else "disabled",
        )

    eligible_positions = {
        position
        for position, (_row, cleaned, _translated) in enumerate(prepared)
        if llm_fallback.should_use_llm(cleaned, llm_inputs[position], output_mode)
    }
    if diagnostic_logger is not None:
        diagnostic_logger(
            "ai_eligibility_summary",
            visual_line_count=len(prepared),
            eligible_line_count=len(eligible_positions),
            outcome="enabled" if llm_provider is not None else "disabled",
        )

    line_translation_start = time.perf_counter()
    out = []
    llm_call_ordinal = 0
    for position, (row, cleaned, translated) in enumerate(prepared):
        previous = prepared[position - 1][1] if position > 0 else ""
        following = prepared[position + 1][1] if position + 1 < len(prepared) else ""
        call_ordinal = None
        if llm_provider is not None and position in eligible_positions:
            llm_call_ordinal += 1
            call_ordinal = llm_call_ordinal
        translated = llm_fallback.apply_llm_fallback(
            source=cleaned,
            deterministic=translated,
            previous=previous,
            following=following,
            output_mode=output_mode,
            df=df,
            provider=llm_provider,
            title_context=title_contexts[position],
            semantic_context=semantic_context,
            llm_input_text=llm_inputs[position],
            llm_df=df if title_contexts[position] else llm_df,
            diagnostic_logger=diagnostic_logger,
            call_ordinal=call_ordinal,
        )
        changed = terminology.norm_text(cleaned) != terminology.norm_text(translated)
        out.append({
            "Original": cleaned,
            "Translation": translated,
            "Confidence": round(float(row.get("confidence", 0)), 3),
            "Changed": "✓" if changed else "",
            "min_x": float(row.get("min_x", row.get("x", 0))),
            "max_x": float(row.get("max_x", row.get("x", 0) + 80)),
            "min_y": float(row.get("min_y", row.get("y", 0))),
            "max_y": float(row.get("max_y", row.get("y", 0) + 20)),
        })
    if diagnostic_logger is not None:
        diagnostic_logger(
            "line_translation_end",
            elapsed_seconds=time.perf_counter() - line_translation_start,
            visual_line_count=len(prepared),
            eligible_line_count=len(eligible_positions),
            outcome="success",
        )
    reconstruction_start = time.perf_counter()
    result = pd.DataFrame(out)
    if diagnostic_logger is not None:
        diagnostic_logger(
            "line_reconstruction_end",
            elapsed_seconds=time.perf_counter() - reconstruction_start,
            visual_line_count=len(result),
            outcome="success",
        )
    return result
