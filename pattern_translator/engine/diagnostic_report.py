"""Diagnostic report construction for the Pattern Translator.

This module contains pure diagnostic report builders and formatting helpers
extracted from the Streamlit app. It accepts ordinary Python data structures and
returns dictionaries or text. Streamlit session state, widgets, downloads, and
analytics stay in app.py.
"""

import hashlib
import time
from typing import Dict, List, Optional, Tuple

import pandas as pd

from pattern_translator.engine.line_translation import build_readable_line_translation
from pattern_translator.engine.terminology import to_simplified


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
            "Top-level inclusive timing",
            "Measured from the top-level build_ocr_line_translations() call. Detailed nested parser timings are still available in debug output, but they are not summed here because nested calls overlap and can exceed total translation stage time.",
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
    csv_term_cache_stats: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    counts = translation_profile.get("counts", {}) if isinstance(translation_profile, dict) else {}
    if not isinstance(counts, dict):
        counts = {}
    stats = dict(csv_term_cache_stats or {})
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
    normalized_lookup_index_stats: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    counts = translation_profile.get("counts", {}) if isinstance(translation_profile, dict) else {}
    if not isinstance(counts, dict):
        counts = {}
    stats = dict(normalized_lookup_index_stats or {})
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
    app_version: str = "",
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
        platform = "Not captured"
    parts = [
        "================================================",
        "Diagnostic Report",
        "================================================",
        "",
        "Note: This report is for diagnosing OCR / dictionary / overlay issues.",
        "",
        "=== Application Information ===",
        f"App version: {app_version or 'Not captured'}",
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





