"""Primary translation-result delivery helpers."""

import json
import math
import re
from dataclasses import dataclass
from collections.abc import Callable, Mapping, MutableMapping
import threading
import time
import sys
from typing import Any, Dict, Iterable, Optional, Tuple

import pandas as pd

from pattern_translator.engine import diagnostic_report as diagnostic_report_engine
from pattern_translator.engine import line_translation as line_translation_engine


RESULT_STATE_KEY = "rc3_ocr_result"
DEFAULT_HANDOFF_TTL_SECONDS = 300.0
DEFAULT_HANDOFF_MAX_ENTRIES = 8
DIAGNOSTIC_SNAPSHOT_SCHEMA_VERSION = 1
MAX_DIAGNOSTIC_SNAPSHOT_BYTES = 3 * 1024 * 1024
MAX_DIAGNOSTIC_FRAME_ROWS = 500
MAX_DIAGNOSTIC_FRAME_COLUMNS = 64
MAX_DIAGNOSTIC_COLLECTION_ITEMS = 1000
MAX_DIAGNOSTIC_STRING_CHARS = 200_000
_DIAGNOSTIC_RESULT_BUDGET = 220_000
_DIAGNOSTIC_LINE_FRAME_BUDGET = 240_000
_DIAGNOSTIC_MATCH_FRAME_BUDGET = 120_000
_DIAGNOSTIC_OCR_FRAME_BUDGET = 180_000
_DIAGNOSTIC_INPUT_BUDGET = 70_000
_DIAGNOSTIC_STAT_BUDGET = 11_000
_DIAGNOSTIC_LINE_COLUMNS = ("Original", "Translation")
_DIAGNOSTIC_OCR_COLUMNS = (
    "text",
    "confidence",
    "min_x",
    "max_x",
    "min_y",
    "max_y",
)
SIGNATURE_FIELD_NAMES = (
    "image_signature",
    "source_language",
    "target_language",
    "area_mode",
    "crop_box",
)
SIGNATURE_EXTRA_FIELD_NAMES = (
    "downscale_flag",
    "downscale_option",
    "ocr_resize_option",
)


def _safe_log_token(value: object) -> str:
    return "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in str(value or "")
    )[:80] or "unavailable"


def differing_signature_fields(
    stored_signature: object,
    current_signature: object,
) -> Tuple[str, ...]:
    """Return only structural field names whose signature values differ."""
    if not isinstance(stored_signature, (tuple, list)) or not isinstance(
        current_signature, (tuple, list)
    ):
        return ("signature_shape",)

    differences = []
    for index, field_name in enumerate(SIGNATURE_FIELD_NAMES):
        stored_value = stored_signature[index] if index < len(stored_signature) else None
        current_value = current_signature[index] if index < len(current_signature) else None
        if stored_value != current_value:
            differences.append(field_name)

    stored_extra = stored_signature[5] if len(stored_signature) > 5 else ()
    current_extra = current_signature[5] if len(current_signature) > 5 else ()
    if not isinstance(stored_extra, (tuple, list)) or not isinstance(
        current_extra, (tuple, list)
    ):
        differences.append("signature_shape")
    else:
        for index, field_name in enumerate(SIGNATURE_EXTRA_FIELD_NAMES):
            stored_value = stored_extra[index] if index < len(stored_extra) else None
            current_value = current_extra[index] if index < len(current_extra) else None
            if stored_value != current_value:
                differences.append(field_name)

    if len(stored_signature) != len(current_signature):
        differences.append("signature_shape")
    return tuple(dict.fromkeys(differences))


def log_result_state(
    request_id: str,
    phase: str,
    *,
    session_generation: str,
    script_run_no: Optional[int],
    lifecycle: str,
    result_present: bool,
    active_image: bool,
    accepted_upload_generation: Optional[int],
    action: str = "",
    reason: str = "",
    uploader_event: str = "",
    area_mode: str = "",
    select_area_editing: Optional[bool] = None,
    crop_confirmed: Optional[bool] = None,
    stored_signature_present: Optional[bool] = None,
    current_signature_present: Optional[bool] = None,
    signature_match: Optional[bool] = None,
    mismatch_fields: Iterable[str] = (),
) -> None:
    """Emit structural result diagnostics without pattern or signature values."""
    fields = [
        f"request_id={_safe_log_token(request_id)}",
        f"phase={_safe_log_token(phase)}",
        f"monotonic_ms={time.perf_counter() * 1000:.1f}",
        f"session_generation={_safe_log_token(session_generation)}",
        f"lifecycle={_safe_log_token(lifecycle)}",
        f"result_present={str(bool(result_present)).lower()}",
        f"active_image={str(bool(active_image)).lower()}",
    ]
    if script_run_no is not None:
        fields.append(f"script_run_no={int(script_run_no)}")
    if accepted_upload_generation is not None:
        fields.append(
            f"accepted_upload_generation={int(accepted_upload_generation)}"
        )
    for name, value in (
        ("action", action),
        ("reason", reason),
        ("uploader_event", uploader_event),
        ("area_mode", area_mode),
    ):
        if value:
            fields.append(f"{name}={_safe_log_token(value)}")
    for name, value in (
        ("select_area_editing", select_area_editing),
        ("crop_confirmed", crop_confirmed),
        ("stored_signature_present", stored_signature_present),
        ("current_signature_present", current_signature_present),
        ("signature_match", signature_match),
    ):
        if value is not None:
            fields.append(f"{name}={str(bool(value)).lower()}")
    safe_mismatch_fields = [
        field
        for field in mismatch_fields
        if field in SIGNATURE_FIELD_NAMES
        or field in SIGNATURE_EXTRA_FIELD_NAMES
        or field == "signature_shape"
    ]
    if safe_mismatch_fields:
        fields.append("mismatch_fields=" + ",".join(safe_mismatch_fields))
    print("[pattern_result_state] " + " ".join(fields), file=sys.stderr, flush=True)


@dataclass(frozen=True)
class _HandoffEntry:
    payload: Dict[str, Any]
    published_at: float


class CompletedResultHandoff:
    """Bounded process-local delivery for results completed between reruns."""

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_HANDOFF_TTL_SECONDS,
        max_entries: int = DEFAULT_HANDOFF_MAX_ENTRIES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._ttl_seconds = float(ttl_seconds)
        self._max_entries = int(max_entries)
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: Dict[Tuple[str, str], _HandoffEntry] = {}

    @staticmethod
    def _key(session_generation: str, request_id: str) -> Tuple[str, str]:
        if not session_generation or not request_id:
            raise ValueError("session_generation and request_id are required")
        return str(session_generation), str(request_id)

    def _cleanup_locked(self, now: float) -> int:
        expired = [
            key
            for key, entry in self._entries.items()
            if now - entry.published_at >= self._ttl_seconds
        ]
        for key in expired:
            del self._entries[key]
        return len(expired)

    def publish(
        self,
        session_generation: str,
        request_id: str,
        payload: Dict[str, Any],
    ) -> Tuple[bool, int]:
        """Publish once, pruning expired and oldest abandoned deliveries."""
        key = self._key(session_generation, request_id)
        now = self._clock()
        with self._lock:
            expired_count = self._cleanup_locked(now)
            if key in self._entries:
                return False, expired_count
            while len(self._entries) >= self._max_entries:
                oldest_key = min(
                    self._entries,
                    key=lambda item: self._entries[item].published_at,
                )
                del self._entries[oldest_key]
            self._entries[key] = _HandoffEntry(payload=payload, published_at=now)
            return True, expired_count

    def claim(
        self,
        session_generation: str,
        request_id: str,
        deliver: Callable[[Dict[str, Any]], None],
    ) -> Tuple[Optional[Dict[str, Any]], int]:
        """Deliver once and remove only after the consumer commits successfully."""
        key = self._key(session_generation, request_id)
        now = self._clock()
        with self._lock:
            expired_count = self._cleanup_locked(now)
            entry = self._entries.get(key)
            if entry is None:
                return None, expired_count
            deliver(entry.payload)
            del self._entries[key]
            return entry.payload, expired_count

    def cleanup_expired(self) -> int:
        with self._lock:
            return self._cleanup_locked(self._clock())

    def entry_count(self) -> int:
        with self._lock:
            self._cleanup_locked(self._clock())
            return len(self._entries)


_COMPLETED_RESULT_HANDOFF = CompletedResultHandoff()


def publish_completed_result(
    session_generation: str,
    request_id: str,
    payload: Dict[str, Any],
) -> Tuple[bool, int]:
    return _COMPLETED_RESULT_HANDOFF.publish(
        session_generation,
        request_id,
        payload,
    )


def claim_completed_result(
    session_generation: str,
    request_id: str,
    deliver: Callable[[Dict[str, Any]], None],
) -> Tuple[Optional[Dict[str, Any]], int]:
    return _COMPLETED_RESULT_HANDOFF.claim(
        session_generation,
        request_id,
        deliver,
    )


def store_primary_result(
    session_state: MutableMapping[str, Any],
    result: Dict[str, Any],
) -> None:
    """Commit the primary translation result before optional artifacts."""
    session_state[RESULT_STATE_KEY] = result


def generate_optional_diagnostic_report(
    result: Dict[str, Any],
    builder: Callable[[], str],
) -> Tuple[bool, str]:
    """Attach a diagnostic report without invalidating an existing result."""
    try:
        report = builder()
    except Exception:
        return False, "generation_error"
    result["debug_report_txt"] = report
    return True, "success"


class _JsonBudget:
    def __init__(self, remaining: int) -> None:
        self.remaining = max(0, int(remaining))

    def consume(self, amount: int) -> bool:
        amount = max(0, int(amount))
        if amount > self.remaining:
            self.remaining = 0
            return False
        self.remaining -= amount
        return True


def _bounded_json_text(value: object, budget: _JsonBudget) -> str:
    text = str(value or "")
    allowed = min(len(text), MAX_DIAGNOSTIC_STRING_CHARS, budget.remaining)
    bounded = text[:allowed]
    budget.consume(len(bounded))
    return bounded


def _json_safe_value(
    value: object,
    budget: _JsonBudget,
    *,
    depth: int = 0,
) -> object:
    if depth > 10:
        return None
    if budget.remaining <= 0:
        if isinstance(value, str):
            return ""
        if isinstance(value, Mapping):
            return {}
        if isinstance(value, (list, tuple)):
            return []
        return None
    if value is None or isinstance(value, (bool, int)):
        budget.consume(16)
        return value
    if isinstance(value, float):
        budget.consume(24)
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return _bounded_json_text(value, budget)
    if isinstance(value, Mapping):
        output: Dict[str, object] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_DIAGNOSTIC_COLLECTION_ITEMS or budget.remaining <= 0:
                break
            safe_key = str(key)[:256]
            budget.consume(len(safe_key) + 4)
            output[safe_key] = _json_safe_value(item, budget, depth=depth + 1)
        return output
    if isinstance(value, (list, tuple)):
        output_list = []
        for item in value[:MAX_DIAGNOSTIC_COLLECTION_ITEMS]:
            if budget.remaining <= 0:
                break
            budget.consume(4)
            output_list.append(_json_safe_value(item, budget, depth=depth + 1))
        return output_list
    try:
        scalar = value.item()  # type: ignore[attr-defined]
    except Exception:
        scalar = value
    if scalar is not value:
        return _json_safe_value(scalar, budget, depth=depth + 1)
    try:
        if bool(pd.isna(value)):
            return None
    except Exception:
        pass
    return _bounded_json_text(value, budget)


def _dataframe_snapshot(
    value: object,
    budget: _JsonBudget,
    *,
    columns: Optional[Tuple[str, ...]] = None,
) -> Dict[str, object]:
    if not isinstance(value, pd.DataFrame):
        return {"columns": [], "data": []}
    frame = value
    if columns is not None:
        frame = value.reindex(columns=list(columns))
    column_count = min(len(frame.columns), MAX_DIAGNOSTIC_FRAME_COLUMNS)
    columns = [
        _bounded_json_text(str(frame.columns[index])[:256], budget)
        for index in range(column_count)
    ]
    data = []
    for row in frame.iloc[:MAX_DIAGNOSTIC_FRAME_ROWS, :column_count].itertuples(
        index=False,
        name=None,
    ):
        if budget.remaining <= 0:
            break
        data.append(
            [
                _json_safe_value(cell, budget, depth=1)
                for cell in row
            ]
        )
    return {"columns": columns, "data": data}


def _row_count(value: object) -> int:
    return min(
        len(value) if isinstance(value, pd.DataFrame) else 0,
        100_000,
    )


def create_diagnostic_snapshot(
    result: Mapping[str, object],
    *,
    terminology_row_count: int,
    csv_term_cache_stats: Optional[Mapping[str, object]] = None,
    normalized_lookup_index_stats: Optional[Mapping[str, object]] = None,
) -> Dict[str, object]:
    """Project a completed result into a bounded, JSON-safe diagnostic snapshot."""
    result_budget = _JsonBudget(_DIAGNOSTIC_RESULT_BUDGET)
    input_budget = _JsonBudget(_DIAGNOSTIC_INPUT_BUDGET)
    inputs = result.get("diagnostic_report_inputs", {})
    if not isinstance(inputs, Mapping):
        inputs = {}
    diagnostic_values = {
        "ocr_engine": inputs.get("ocr_engine")
        if isinstance(inputs.get("ocr_engine"), str)
        else "",
        "image_quality_status": inputs.get("image_quality_status")
        if isinstance(inputs.get("image_quality_status"), str)
        else "",
        "session_diagnostics": inputs.get("session_diagnostics")
        if isinstance(inputs.get("session_diagnostics"), Mapping)
        else {},
        "events": inputs.get("events")
        if isinstance(inputs.get("events"), (list, tuple))
        else [],
        "ai_fallback_diagnostics": inputs.get("ai_fallback_diagnostics")
        if isinstance(inputs.get("ai_fallback_diagnostics"), (list, tuple))
        else [],
        "ocr_workload_diagnostics": inputs.get("ocr_workload_diagnostics")
        if isinstance(inputs.get("ocr_workload_diagnostics"), Mapping)
        else {},
        "ocr_call_diagnostics": inputs.get("ocr_call_diagnostics")
        if isinstance(inputs.get("ocr_call_diagnostics"), Mapping)
        else {},
        "ocr_call_trace": inputs.get("ocr_call_trace")
        if isinstance(inputs.get("ocr_call_trace"), (list, tuple))
        else [],
        "downscale_diagnostics": inputs.get("downscale_diagnostics")
        if isinstance(inputs.get("downscale_diagnostics"), Mapping)
        else {},
        "ocr_resize_test": inputs.get("ocr_resize_test")
        if isinstance(inputs.get("ocr_resize_test"), str)
        else "Auto",
    }
    snapshot = {
        "schema_version": DIAGNOSTIC_SNAPSHOT_SCHEMA_VERSION,
        "result": {
            key: _json_safe_value(result.get(key), result_budget)
            for key in (
                "source_mode",
                "output_mode",
                "area_mode",
                "crop_box",
                "quality_metrics",
                "timings",
                "runtime_profile",
                "translation_profile",
                "overlay_legend",
                "raw_ocr_text",
                "clean_text",
                "unmatched",
            )
        },
        "frames": {
            "line_df": _dataframe_snapshot(
                result.get("line_df"),
                _JsonBudget(_DIAGNOSTIC_LINE_FRAME_BUDGET),
                columns=_DIAGNOSTIC_LINE_COLUMNS,
            ),
            "matches_df": _dataframe_snapshot(
                result.get("matches_df"),
                _JsonBudget(_DIAGNOSTIC_MATCH_FRAME_BUDGET),
            ),
            "ocr_box_rows": _dataframe_snapshot(
                inputs.get("ocr_box_rows"),
                _JsonBudget(_DIAGNOSTIC_OCR_FRAME_BUDGET),
                columns=_DIAGNOSTIC_OCR_COLUMNS,
            ),
        },
        "counts": {
            "ocr_rows": _row_count(result.get("ocr_rows")),
            "overlay_legend_rows": _row_count(result.get("overlay_legend_df")),
            "terminology_rows": max(0, min(int(terminology_row_count), 100_000)),
        },
        "diagnostics": {
            key: _json_safe_value(value, input_budget)
            for key, value in diagnostic_values.items()
        },
        "csv_term_cache_stats": _json_safe_value(
            dict(csv_term_cache_stats or {}),
            _JsonBudget(_DIAGNOSTIC_STAT_BUDGET),
        ),
        "normalized_lookup_index_stats": _json_safe_value(
            dict(normalized_lookup_index_stats or {}),
            _JsonBudget(_DIAGNOSTIC_STAT_BUDGET),
        ),
    }
    encoded = json.dumps(
        snapshot,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > MAX_DIAGNOSTIC_SNAPSHOT_BYTES:
        raise ValueError("diagnostic snapshot exceeds size bound")
    return snapshot


def _validate_snapshot_tree(value: object, *, depth: int = 0) -> None:
    if depth > 12:
        raise ValueError("diagnostic snapshot nesting is invalid")
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("diagnostic snapshot number is invalid")
        return
    if isinstance(value, str):
        if len(value) > MAX_DIAGNOSTIC_STRING_CHARS:
            raise ValueError("diagnostic snapshot string is too long")
        return
    if isinstance(value, dict):
        if len(value) > MAX_DIAGNOSTIC_COLLECTION_ITEMS:
            raise ValueError("diagnostic snapshot object is too large")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 256:
                raise ValueError("diagnostic snapshot key is invalid")
            _validate_snapshot_tree(item, depth=depth + 1)
        return
    if isinstance(value, list):
        if len(value) > MAX_DIAGNOSTIC_COLLECTION_ITEMS:
            raise ValueError("diagnostic snapshot list is too large")
        for item in value:
            _validate_snapshot_tree(item, depth=depth + 1)
        return
    raise ValueError("diagnostic snapshot value is invalid")


def _restore_dataframe(
    value: object,
    *,
    expected_columns: Optional[Tuple[str, ...]] = None,
) -> pd.DataFrame:
    if not isinstance(value, dict):
        raise ValueError("diagnostic frame is invalid")
    columns = value.get("columns")
    data = value.get("data")
    if not isinstance(columns, list) or not isinstance(data, list):
        raise ValueError("diagnostic frame is invalid")
    if len(columns) > MAX_DIAGNOSTIC_FRAME_COLUMNS:
        raise ValueError("diagnostic frame has too many columns")
    if len(data) > MAX_DIAGNOSTIC_FRAME_ROWS:
        raise ValueError("diagnostic frame has too many rows")
    if any(not isinstance(column, str) for column in columns):
        raise ValueError("diagnostic frame columns are invalid")
    if len(set(columns)) != len(columns):
        raise ValueError("diagnostic frame columns are duplicated")
    if expected_columns is not None and tuple(columns) != expected_columns:
        raise ValueError("diagnostic frame columns are invalid")
    for row in data:
        if not isinstance(row, list) or len(row) != len(columns):
            raise ValueError("diagnostic frame row is invalid")
    return pd.DataFrame(data, columns=columns)


def _validated_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("diagnostic count is invalid")
    if not 0 <= value <= 100_000:
        raise ValueError("diagnostic count is out of range")
    return value


@dataclass(frozen=True)
class RestoredDiagnosticContext:
    result: Dict[str, object]
    terminology_row_count: int
    csv_term_cache_stats: Dict[str, object]
    normalized_lookup_index_stats: Dict[str, object]


def restore_diagnostic_snapshot(
    snapshot: object,
    *,
    interface_language: str,
    platform: str,
) -> RestoredDiagnosticContext:
    """Validate and restore report inputs without any OCR or translation path."""
    _validate_snapshot_tree(snapshot)
    if not isinstance(snapshot, dict):
        raise ValueError("diagnostic snapshot is invalid")
    schema_version = snapshot.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != DIAGNOSTIC_SNAPSHOT_SCHEMA_VERSION
    ):
        raise ValueError("diagnostic snapshot version is invalid")
    result_payload = snapshot.get("result")
    frames = snapshot.get("frames")
    counts = snapshot.get("counts")
    diagnostics = snapshot.get("diagnostics")
    if not all(
        isinstance(value, dict)
        for value in (result_payload, frames, counts, diagnostics)
    ):
        raise ValueError("diagnostic snapshot shape is invalid")

    area_mode = result_payload.get("area_mode")
    if area_mode not in {"Whole Pattern", "Select Area"}:
        raise ValueError("diagnostic area mode is invalid")
    crop_box = result_payload.get("crop_box")
    if (
        not isinstance(crop_box, list)
        or len(crop_box) != 4
        or any(isinstance(value, bool) or not isinstance(value, int) for value in crop_box)
    ):
        raise ValueError("diagnostic crop box is invalid")
    for key in ("source_mode", "output_mode"):
        if not isinstance(result_payload.get(key), str) or not result_payload.get(key):
            raise ValueError("diagnostic language mode is invalid")

    for key in (
        "quality_metrics",
        "timings",
        "runtime_profile",
        "translation_profile",
    ):
        if not isinstance(result_payload.get(key), dict):
            raise ValueError("diagnostic result value is invalid")
    for key in ("overlay_legend", "raw_ocr_text", "clean_text"):
        if not isinstance(result_payload.get(key), str):
            raise ValueError("diagnostic result text is invalid")
    unmatched = result_payload.get("unmatched")
    if not isinstance(unmatched, list) or any(
        not isinstance(value, str) for value in unmatched
    ):
        raise ValueError("diagnostic unmatched terms are invalid")

    for key in (
        "session_diagnostics",
        "ocr_workload_diagnostics",
        "ocr_call_diagnostics",
        "downscale_diagnostics",
    ):
        if not isinstance(diagnostics.get(key), dict):
            raise ValueError("diagnostic detail is invalid")
    events = diagnostics.get("events")
    if not isinstance(events, list) or any(
        not isinstance(event, dict) for event in events
    ):
        raise ValueError("diagnostic events are invalid")
    ai_fallback_diagnostics = diagnostics.get("ai_fallback_diagnostics", [])
    if not isinstance(ai_fallback_diagnostics, list) or any(
        not isinstance(record, dict) for record in ai_fallback_diagnostics
    ):
        raise ValueError("AI fallback diagnostics are invalid")
    trace = diagnostics.get("ocr_call_trace")
    if not isinstance(trace, list) or any(
        not isinstance(item, str) for item in trace
    ):
        raise ValueError("diagnostic trace is invalid")
    for key in ("ocr_engine", "ocr_resize_test"):
        if not isinstance(diagnostics.get(key), str):
            raise ValueError("diagnostic detail text is invalid")

    line_df = _restore_dataframe(
        frames.get("line_df"),
        expected_columns=_DIAGNOSTIC_LINE_COLUMNS,
    )
    matches_df = _restore_dataframe(frames.get("matches_df"))
    ocr_box_rows = _restore_dataframe(
        frames.get("ocr_box_rows"),
        expected_columns=_DIAGNOSTIC_OCR_COLUMNS,
    )
    ocr_row_count = _validated_count(counts.get("ocr_rows"))
    overlay_legend_row_count = _validated_count(counts.get("overlay_legend_rows"))
    terminology_row_count = _validated_count(counts.get("terminology_rows"))

    restored_inputs = dict(diagnostics)
    restored_inputs["ocr_box_rows"] = ocr_box_rows
    restored_inputs["interface_language"] = str(interface_language)[:128]
    restored_inputs["platform"] = str(platform or "Not captured")[:512]
    restored_result = dict(result_payload)
    readable_translation = (
        line_translation_engine.build_readable_line_translation(line_df)
        if not line_df.empty
        else ""
    )
    restored_result.update(
        {
            "crop_box": tuple(crop_box),
            "line_df": line_df,
            "matches_df": matches_df,
            "readable_translation": readable_translation,
            "ocr_rows": pd.DataFrame(index=range(ocr_row_count)),
            "overlay_legend_df": pd.DataFrame(
                index=range(overlay_legend_row_count)
            ),
            "diagnostic_report_inputs": restored_inputs,
        }
    )
    cache_stats = snapshot.get("csv_term_cache_stats")
    lookup_stats = snapshot.get("normalized_lookup_index_stats")
    if not isinstance(cache_stats, dict) or not isinstance(lookup_stats, dict):
        raise ValueError("diagnostic statistics are invalid")
    return RestoredDiagnosticContext(
        result=restored_result,
        terminology_row_count=terminology_row_count,
        csv_term_cache_stats=dict(cache_stats),
        normalized_lookup_index_stats=dict(lookup_stats),
    )


def build_deferred_diagnostic_report(
    result: Dict[str, object],
    *,
    terminology_dataframe: Optional[pd.DataFrame] = None,
    terminology_row_count: Optional[int] = None,
    csv_term_cache_stats: Optional[Mapping[str, object]] = None,
    normalized_lookup_index_stats: Optional[Mapping[str, object]] = None,
    app_version: str = "",
    interface_language: Optional[str] = None,
    platform: Optional[str] = None,
) -> str:
    """Build the optional report from an already-completed translation result."""
    inputs = result.get("diagnostic_report_inputs", {})
    if not isinstance(inputs, dict):
        inputs = {}
    else:
        inputs = dict(inputs)
    if interface_language is not None:
        inputs["interface_language"] = interface_language
    if platform is not None:
        inputs["platform"] = platform
    timings = result.get("timings", {})
    if not isinstance(timings, dict):
        timings = {}
    runtime_profile = result.get("runtime_profile", {})
    if not isinstance(runtime_profile, dict):
        runtime_profile = {}
    translation_profile = result.get("translation_profile", {})
    if not isinstance(translation_profile, dict):
        translation_profile = {}
    if terminology_dataframe is None and terminology_row_count is not None:
        terminology_dataframe = pd.DataFrame(index=range(terminology_row_count))

    report_start = time.perf_counter()
    line_df = result.get("line_df")
    ocr_rows = result.get("ocr_rows")
    overlay_legend_df = result.get("overlay_legend_df")
    readable_translation = str(result.get("readable_translation", "") or "")
    rc11c_translation_diagnostics = (
        diagnostic_report_engine.build_rc11c_translation_diagnostics(
            translation_profile,
            timings,
            ocr_rows,
            line_df,
            overlay_legend_df,
        )
    )
    rc11d_validation_diagnostics = (
        diagnostic_report_engine.build_rc11d_validation_diagnostics(
            translation_profile,
            rc11c_translation_diagnostics,
        )
    )
    rc11e_normalization_diagnostics = (
        diagnostic_report_engine.build_rc11e_normalization_diagnostics(
            translation_profile,
            terminology_dataframe,
        )
    )
    rc11f_cache_diagnostics = (
        diagnostic_report_engine.build_rc11f_cache_diagnostics(
            translation_profile,
            timings,
            readable_translation,
            csv_term_cache_stats=dict(csv_term_cache_stats or {}),
        )
    )
    rc11g_lookup_index_diagnostics = (
        diagnostic_report_engine.build_rc11g_lookup_index_diagnostics(
            translation_profile,
            timings,
            readable_translation,
            normalized_lookup_index_stats=dict(
                normalized_lookup_index_stats or {}
            ),
        )
    )
    report_text = diagnostic_report_engine.build_debug_report_text(
        line_df,
        legend_text=str(result.get("overlay_legend", "") or ""),
        clean_text=str(result.get("clean_text", "") or ""),
        raw_text=str(result.get("raw_ocr_text", "") or ""),
        source_mode=str(result.get("source_mode", "") or ""),
        output_mode=str(result.get("output_mode", "") or ""),
        area_mode=str(result.get("area_mode", "") or ""),
        crop_box=result.get("crop_box"),
        matches_df=result.get("matches_df"),
        unmatched=result.get("unmatched"),
        ocr_engine=str(inputs.get("ocr_engine", "") or ""),
        image_quality_status=str(inputs.get("image_quality_status", "") or ""),
        quality_metrics=result.get("quality_metrics"),
        session_diagnostics=inputs.get("session_diagnostics"),
        events=inputs.get("events"),
        ai_fallback_diagnostics=inputs.get("ai_fallback_diagnostics"),
        timings=timings,
        ocr_workload_diagnostics=inputs.get("ocr_workload_diagnostics"),
        ocr_box_rows=inputs.get("ocr_box_rows"),
        ocr_call_diagnostics=inputs.get("ocr_call_diagnostics"),
        ocr_call_trace=inputs.get("ocr_call_trace"),
        downscale_diagnostics=inputs.get("downscale_diagnostics"),
        ocr_resize_test=str(inputs.get("ocr_resize_test", "Auto") or "Auto"),
        interface_language=str(inputs.get("interface_language", "") or ""),
        platform=str(inputs.get("platform", "Not captured") or "Not captured"),
        app_version=app_version,
        rc11c_translation_diagnostics=rc11c_translation_diagnostics,
        rc11d_validation_diagnostics=rc11d_validation_diagnostics,
        rc11e_normalization_diagnostics=rc11e_normalization_diagnostics,
        rc11f_cache_diagnostics=rc11f_cache_diagnostics,
        rc11g_lookup_index_diagnostics=rc11g_lookup_index_diagnostics,
    )
    report_seconds = time.perf_counter() - report_start
    runtime_profile["diagnostic_report_generation"] = report_seconds
    try:
        runtime_profile["total"] = (
            float(runtime_profile.get("total") or 0.0) + report_seconds
        )
    except Exception:
        pass
    timings["Diagnostic Report generation"] = report_seconds
    if runtime_profile.get("total") is not None:
        timings["Total runtime"] = runtime_profile["total"]
    return "\n".join(
        [
            report_text.rstrip(),
            "",
            "=== Performance: Runtime Profile ===",
            diagnostic_report_engine.format_runtime_profile(runtime_profile),
            "",
        ]
    )


def diagnostic_report_filename(app_version: str) -> str:
    version = (
        app_version.split("Beta ", 1)[-1].rstrip(")")
        if "Beta " in app_version
        else app_version
    )
    safe_version = re.sub(r"[^A-Za-z0-9]+", "", version) or "RC"
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return f"PatternOCR_DiagnosticReport_{safe_version}_{timestamp}.txt"
