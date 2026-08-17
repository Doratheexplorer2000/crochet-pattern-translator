"""Primary translation-result delivery helpers."""

from dataclasses import dataclass
from collections.abc import Callable, MutableMapping
import threading
import time
import sys
from typing import Any, Dict, Iterable, Optional, Tuple


RESULT_STATE_KEY = "rc3_ocr_result"
DEFAULT_HANDOFF_TTL_SECONDS = 300.0
DEFAULT_HANDOFF_MAX_ENTRIES = 8
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
