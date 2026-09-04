"""OCR visual-line assembly for the Pattern Translator.

This module owns the deterministic conversion from OCR box rows into translated
line records. It does not initialize or execute OCR, preprocess images, manage
Streamlit state, render overlays, or perform downloads.
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from threading import BoundedSemaphore
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

LEGACY_LLM_MAX_CONCURRENCY = 4
_LEGACY_LLM_CALL_SLOTS = BoundedSemaphore(LEGACY_LLM_MAX_CONCURRENCY)
_ENGLISH_OUTPUT_MODES = {
    "English — US",
    "English — UK",
    "English US terms",
    "English UK terms",
}
_CHINESE_SOURCE_MODES = {"Traditional Chinese", "Simplified Chinese"}
_RIGHT_SIDE_STITCH_TOTAL_RE = re.compile(r"^共\s*\d+\s*[針针]\s*$")
_CJK_CHARACTER_RE = re.compile(r"[\u3400-\u9fff]")
_URL_OR_DOMAIN_RE = re.compile(
    r"(?:https?://|www\.|(?<![A-Za-z0-9])(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,24}\b)",
    re.IGNORECASE,
)
_PAGE_LABEL_RE = re.compile(
    r"(?:[-–—]?\s*\d+\s*[-–—]?|(?:第\s*)?\d+\s*[頁页]|[頁页]\s*\d+)",
    re.IGNORECASE,
)
_FOOTNOTE_OR_CAPTION_RE = re.compile(
    r"(?:\[\s*\d+\s*\]|[＊*†‡]|(?:圖|图|表|Figure|Fig\.?)\s*\d+\b)",
    re.IGNORECASE,
)

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


def merge_ocr_boxes_into_visual_lines(
    ocr_rows: pd.DataFrame,
    *,
    correct_chinese_legacy_layout: bool = False,
) -> pd.DataFrame:
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
        line_rows = [row for _, row in line.iterrows()]
        if correct_chinese_legacy_layout and _reassociate_right_side_stitch_total(
            line_rows, merged_records, canvas_width=canvas_width, y_threshold=y_threshold
        ):
            continue
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

    if correct_chinese_legacy_layout:
        merged_records = _merge_parenthetical_continuation_records(
            merged_records,
            y_threshold=y_threshold,
        )
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


def _parenthesis_balance(text: str) -> int:
    value = str(text or "")
    return value.count("(") + value.count("（") - value.count(")") - value.count("）")


def _horizontal_overlap_ratio(first: object, second: object) -> float:
    first_min = float(first.get("min_x", 0) or 0)
    first_max = float(first.get("max_x", first_min) or first_min)
    second_min = float(second.get("min_x", 0) or 0)
    second_max = float(second.get("max_x", second_min) or second_min)
    overlap = max(0.0, min(first_max, second_max) - max(first_min, second_min))
    narrower_width = min(first_max - first_min, second_max - second_min)
    return overlap / narrower_width if narrower_width > 0 else 0.0


def _reassociate_right_side_stitch_total(
    line_rows: list,
    merged_records: list,
    *,
    canvas_width: float,
    y_threshold: float,
) -> bool:
    """Keep a right-column stitch total out of a vertically aligned open note."""
    if len(line_rows) < 2 or not merged_records:
        return False

    total = line_rows[-1]
    total_text = str(total.get("text", "")).strip()
    if not _RIGHT_SIDE_STITCH_TOTAL_RE.fullmatch(total_text):
        return False
    total_min_x = float(total.get("min_x", 0) or 0)
    if total_min_x < canvas_width * 0.80:
        return False

    competing = _merge_ocr_cluster(line_rows[:-1])
    competing_text = str(competing.get("text", "")).strip()
    if competing_text[:1] not in "(（" or _parenthesis_balance(competing_text) <= 0:
        return False

    previous = merged_records[-1]
    previous_text = str(previous.get("text", "")).strip()
    if (
        not previous_text
        or _RIGHT_SIDE_STITCH_TOTAL_RE.fullmatch(previous_text)
        or _parenthesis_balance(previous_text) != 0
        or _horizontal_overlap_ratio(previous, competing) < 0.70
    ):
        return False

    vertical_edge_gap = float(total.get("min_y", 0) or 0) - float(
        previous.get("max_y", 0) or 0
    )
    if vertical_edge_gap < 0 or vertical_edge_gap > y_threshold:
        return False

    merged_records[-1] = _merge_ocr_cluster([previous, total])
    merged_records.append(competing)
    return True


def _merge_parenthetical_continuation_records(
    records: list,
    *,
    y_threshold: float,
) -> list:
    """Join one tightly aligned wrapped parenthetical note into one logical row."""
    ordered = sorted(
        records,
        key=lambda record: (
            float(record.get("min_y", 0) or 0),
            float(record.get("min_x", 0) or 0),
        ),
    )
    merged = []
    position = 0
    while position < len(ordered):
        current = ordered[position]
        if position + 1 >= len(ordered):
            merged.append(current)
            break

        following = ordered[position + 1]
        current_text = str(current.get("text", "")).strip()
        following_text = str(following.get("text", "")).strip()
        vertical_edge_gap = float(following.get("min_y", 0) or 0) - float(
            current.get("max_y", 0) or 0
        )
        left_edge_delta = abs(
            float(current.get("min_x", 0) or 0)
            - float(following.get("min_x", 0) or 0)
        )
        current_center_x = (
            float(current.get("min_x", 0) or 0)
            + float(current.get("max_x", 0) or 0)
        ) / 2
        following_center_x = (
            float(following.get("min_x", 0) or 0)
            + float(following.get("max_x", 0) or 0)
        ) / 2
        closes_parenthetical = (
            _parenthesis_balance(current_text) > 0
            and _parenthesis_balance(current_text + following_text) == 0
            and any(character in following_text for character in ")）")
        )
        following_without_parentheses = following_text.strip("()（） ")
        excluded_following = (
            _URL_OR_DOMAIN_RE.search(following_text) is not None
            or _PAGE_LABEL_RE.fullmatch(following_without_parentheses) is not None
            or _FOOTNOTE_OR_CAPTION_RE.match(following_without_parentheses) is not None
            or _RIGHT_SIDE_STITCH_TOTAL_RE.fullmatch(following_text) is not None
        )
        if (
            closes_parenthetical
            and not excluded_following
            and 0 <= vertical_edge_gap <= y_threshold
            and left_edge_delta <= y_threshold
            and abs(current_center_x - following_center_x) <= y_threshold
            and _horizontal_overlap_ratio(current, following) >= 0.70
        ):
            combined = _merge_ocr_cluster([current, following])
            separator = " "
            if (
                current_text
                and following_text
                and _CJK_CHARACTER_RE.search(current_text[-1])
                and _CJK_CHARACTER_RE.search(following_text[0])
            ):
                separator = ""
            combined["text"] = current_text + separator + following_text
            merged.append(combined)
            position += 2
            continue

        merged.append(current)
        position += 1
    return merged


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

    broad_route = (
        broad_translation.is_broad_translation_enabled()
        and broad_translation.is_broad_translation_route(source_mode, output_mode)
    )
    correct_chinese_legacy_layout = (
        not broad_route
        and source_mode in _CHINESE_SOURCE_MODES
        and output_mode in _ENGLISH_OUTPUT_MODES
    )
    rows = merge_ocr_boxes_into_visual_lines(
        ocr_rows,
        correct_chinese_legacy_layout=correct_chinese_legacy_layout,
    )
    rows["confidence"] = pd.to_numeric(rows.get("confidence", 0), errors="coerce").fillna(0)
    rows = rows.sort_values(["min_y", "min_x"]).reset_index(drop=True)
    _profile_count("merged OCR lines", len(rows))

    if broad_route:
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
        if llm_fallback.should_use_llm(
            cleaned,
            llm_inputs[position],
            output_mode,
            source_mode,
        )
    }
    if diagnostic_logger is not None:
        diagnostic_logger(
            "ai_eligibility_summary",
            visual_line_count=len(prepared),
            eligible_line_count=len(eligible_positions),
            outcome="enabled" if llm_provider is not None else "disabled",
        )

    line_translation_start = time.perf_counter()
    call_ordinals = (
        {
            position: ordinal
            for ordinal, position in enumerate(sorted(eligible_positions), start=1)
        }
        if llm_provider is not None
        else {}
    )

    def apply_fallback(
        position: int,
        call_ordinal: Optional[int],
        use_bounded_slot: bool = False,
    ) -> str:
        _row, cleaned, translated = prepared[position]
        previous = prepared[position - 1][1] if position > 0 else ""
        following = prepared[position + 1][1] if position + 1 < len(prepared) else ""

        def invoke() -> str:
            return llm_fallback.apply_llm_fallback(
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
                source_mode=source_mode,
            )

        if use_bounded_slot:
            with _LEGACY_LLM_CALL_SLOTS:
                return invoke()
        return invoke()

    concurrent_positions = (
        sorted(eligible_positions) if llm_provider is not None else []
    )
    fallback_results: Dict[int, str] = {}
    if len(concurrent_positions) == 1:
        position = concurrent_positions[0]
        fallback_results[position] = apply_fallback(
            position,
            call_ordinals[position],
            True,
        )
    elif concurrent_positions:
        with ThreadPoolExecutor(
            max_workers=min(LEGACY_LLM_MAX_CONCURRENCY, len(concurrent_positions))
        ) as executor:
            futures = {
                position: executor.submit(
                    copy_context().run,
                    apply_fallback,
                    position,
                    call_ordinals[position],
                    True,
                )
                for position in concurrent_positions
            }
            for position in concurrent_positions:
                fallback_results[position] = futures[position].result()

    out = []
    for position, (row, cleaned, translated) in enumerate(prepared):
        if position in fallback_results:
            translated = fallback_results[position]
        else:
            translated = apply_fallback(position, None)
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
