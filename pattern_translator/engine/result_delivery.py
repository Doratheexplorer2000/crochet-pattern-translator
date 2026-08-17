"""Primary translation-result delivery helpers."""

from dataclasses import dataclass
from collections.abc import Callable, MutableMapping
import threading
import time
from typing import Any, Dict, Optional, Tuple


RESULT_STATE_KEY = "rc3_ocr_result"
DEFAULT_HANDOFF_TTL_SECONDS = 300.0
DEFAULT_HANDOFF_MAX_ENTRIES = 8


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
