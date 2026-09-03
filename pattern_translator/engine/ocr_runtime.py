from __future__ import annotations

import atexit
import json
import multiprocessing
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

from pattern_translator.engine.ocr_worker import run_worker


DEFAULT_OCR_TIMEOUT_SECONDS = 90.0
DEFAULT_MAX_JOBS_PER_WORKER = 4
_WORKER_STOP_GRACE_SECONDS = 3.0
_BROAD_DIAGNOSTIC_FIELDS = frozenset(
    {
        "failed_rule",
        "source_segment_ids",
        "expected_source_segment_ids",
        "returned_source_segment_ids",
        "missing_source_segment_ids",
        "duplicate_source_segment_ids",
        "unknown_source_segment_ids",
        "failed_source_excerpt",
        "failed_translation_excerpt",
        "failing_source_excerpt",
        "failing_translation_excerpt",
        "failed_source_excerpt_truncated",
        "failed_translation_excerpt_truncated",
        "source_digit_multiset",
        "translation_digit_multiset",
        "missing_digits",
        "extra_digits",
        "required_round_identities",
        "present_round_identities",
        "missing_round_identities",
        "required_row_identities",
        "present_row_identities",
        "missing_row_identities",
        "required_totals",
        "missing_totals",
        "required_repeat_multipliers",
        "missing_repeat_multipliers",
        "measurement_facts",
        "failed_measurement_number",
        "failed_measurement_unit",
        "measurement_failure",
        "semantic_unit_count",
        "expected_segment_count",
        "stage",
        "exception_type",
        "reason",
        "expected_top_level_shape",
        "actual_top_level_json_type",
        "route_glossary_entry_count",
        "scoped_glossary_entry_count",
        "route_glossary_char_count",
        "scoped_glossary_char_count",
    }
)


def _safe_log_token(value: object) -> str:
    return "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in str(value or "")
    )[:80] or "unavailable"


def _request_uuid(value: Optional[str] = None) -> str:
    try:
        return uuid.UUID(str(value)).hex if value else uuid.uuid4().hex
    except (TypeError, ValueError, AttributeError):
        return uuid.uuid4().hex


def log_ocr_timing(
    request_id: str,
    phase: str,
    *,
    elapsed_seconds: Optional[float] = None,
    attempt: Optional[int] = None,
    worker_pid: Optional[int] = None,
    worker_generation: Optional[int] = None,
    queue_seconds: Optional[float] = None,
    outcome: str = "",
    session_generation: str = "",
    request_lifecycle: str = "",
    active_image: Optional[bool] = None,
    script_run_no: Optional[int] = None,
    visual_line_count: Optional[int] = None,
    eligible_line_count: Optional[int] = None,
    call_ordinal: Optional[int] = None,
    model: str = "",
    route: str = "",
    **diagnostic_fields: object,
) -> None:
    """Emit content-free OCR lifecycle timing for production diagnosis."""
    fields = [
        f"request_id={_safe_log_token(request_id)}",
        f"phase={_safe_log_token(phase)}",
        f"monotonic_ms={time.perf_counter() * 1000:.1f}",
    ]
    if elapsed_seconds is not None:
        fields.append(f"elapsed_ms={max(0.0, elapsed_seconds) * 1000:.1f}")
    if attempt is not None:
        fields.append(f"attempt={int(attempt)}")
    if worker_pid is not None:
        fields.append(f"worker_pid={int(worker_pid)}")
    if worker_generation is not None:
        fields.append(f"worker_generation={int(worker_generation)}")
    if queue_seconds is not None:
        fields.append(f"queue_wait_ms={max(0.0, queue_seconds) * 1000:.1f}")
    if outcome:
        fields.append(f"outcome={_safe_log_token(outcome)}")
    if session_generation:
        fields.append(f"session_generation={_safe_log_token(session_generation)}")
    if request_lifecycle:
        fields.append(f"request_lifecycle={_safe_log_token(request_lifecycle)}")
    if active_image is not None:
        fields.append(f"active_image={str(bool(active_image)).lower()}")
    if script_run_no is not None:
        fields.append(f"script_run_no={int(script_run_no)}")
    if visual_line_count is not None:
        fields.append(f"visual_line_count={int(visual_line_count)}")
    if eligible_line_count is not None:
        fields.append(f"eligible_line_count={int(eligible_line_count)}")
    if call_ordinal is not None:
        fields.append(f"call_ordinal={int(call_ordinal)}")
    if model:
        fields.append(f"model={_safe_log_token(model)}")
    if route:
        fields.append(f"route={_safe_log_token(route)}")
    for key in sorted(_BROAD_DIAGNOSTIC_FIELDS):
        if key not in diagnostic_fields:
            continue
        try:
            encoded = json.dumps(
                diagnostic_fields[key],
                ensure_ascii=False,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            continue
        fields.append(f"{key}={encoded}")
    print("[pattern_ocr_timing] " + " ".join(fields), file=sys.stderr, flush=True)


class OCRWorkerError(RuntimeError):
    def __init__(self, stage: str, exception_type: str = "OCRWorkerError") -> None:
        super().__init__(f"OCR worker failed at {stage}")
        self.stage = stage
        self.exception_type = exception_type


def _positive_float_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


class OCRWorkerManager:
    """Serialize Streamlit callers through one isolated PaddleOCR process."""

    def __init__(
        self,
        timeout_seconds: Optional[float] = None,
        max_jobs_per_worker: Optional[int] = None,
        process_context=None,
        worker_target=run_worker,
    ) -> None:
        self.timeout_seconds = timeout_seconds or _positive_float_env(
            "PATTERN_OCR_WORKER_TIMEOUT_SECONDS",
            DEFAULT_OCR_TIMEOUT_SECONDS,
        )
        self.max_jobs_per_worker = max_jobs_per_worker or _positive_int_env(
            "PATTERN_OCR_MAX_JOBS_PER_WORKER",
            DEFAULT_MAX_JOBS_PER_WORKER,
        )
        self._context = process_context or multiprocessing.get_context("spawn")
        self._worker_target = worker_target
        self._request_lock = threading.Lock()
        self._process = None
        self._connection = None
        self._language: Optional[str] = None
        self._successful_jobs = 0
        self._worker_generation = 0

    @property
    def worker_pid(self) -> Optional[int]:
        return getattr(self._process, "pid", None)

    @property
    def successful_jobs(self) -> int:
        return self._successful_jobs

    def _start_worker(self, language: str, request_id: str, attempt: int) -> None:
        spawn_start = time.perf_counter()
        next_generation = self._worker_generation + 1
        log_ocr_timing(
            request_id,
            "worker_spawn_begin",
            attempt=attempt,
            worker_generation=next_generation,
        )
        parent_connection, child_connection = self._context.Pipe(duplex=True)
        process = self._context.Process(
            target=self._worker_target,
            args=(child_connection, language),
            daemon=True,
            name=f"pattern-ocr-{language}",
        )
        try:
            process.start()
        except Exception as error:
            parent_connection.close()
            child_connection.close()
            raise OCRWorkerError("worker_start", type(error).__name__) from error
        child_connection.close()
        self._process = process
        self._connection = parent_connection
        self._language = language
        self._successful_jobs = 0
        self._worker_generation = next_generation
        log_ocr_timing(
            request_id,
            "worker_process_spawned",
            elapsed_seconds=time.perf_counter() - spawn_start,
            attempt=attempt,
            worker_pid=self.worker_pid,
            worker_generation=self._worker_generation,
        )

    def _stop_worker(
        self,
        graceful: bool,
        request_id: str = "",
        attempt: Optional[int] = None,
        reason: str = "",
    ) -> None:
        process = self._process
        connection = self._connection
        worker_pid = getattr(process, "pid", None)
        worker_generation = self._worker_generation
        stop_start = time.perf_counter()
        if request_id:
            log_ocr_timing(
                request_id,
                "worker_stop_begin",
                attempt=attempt,
                worker_pid=worker_pid,
                worker_generation=worker_generation,
                outcome=reason,
            )
        self._process = None
        self._connection = None
        self._language = None
        self._successful_jobs = 0

        if process is None:
            if connection is not None:
                connection.close()
            if request_id:
                log_ocr_timing(
                    request_id,
                    "worker_stop_end",
                    elapsed_seconds=time.perf_counter() - stop_start,
                    attempt=attempt,
                    worker_generation=worker_generation,
                    outcome=reason,
                )
            return

        if process.is_alive():
            if graceful and connection is not None:
                try:
                    connection.send({"type": "shutdown"})
                except (BrokenPipeError, EOFError, OSError, ValueError):
                    pass
                process.join(_WORKER_STOP_GRACE_SECONDS)
            else:
                process.terminate()
                process.join(_WORKER_STOP_GRACE_SECONDS)
        if process.is_alive():
            process.terminate()
            process.join(_WORKER_STOP_GRACE_SECONDS)
        if process.is_alive() and hasattr(process, "kill"):
            process.kill()
            process.join(_WORKER_STOP_GRACE_SECONDS)
        if connection is not None:
            connection.close()
        try:
            process.close()
        except (AttributeError, ValueError):
            pass
        if request_id:
            log_ocr_timing(
                request_id,
                "worker_stop_end",
                elapsed_seconds=time.perf_counter() - stop_start,
                attempt=attempt,
                worker_pid=worker_pid,
                worker_generation=worker_generation,
                outcome=reason,
            )

    def _ensure_worker(self, language: str, request_id: str, attempt: int) -> None:
        worker_exists = self._process is not None
        worker_alive = bool(worker_exists and self._process.is_alive())
        if not worker_exists:
            check_outcome = "missing"
        elif self._language != language:
            check_outcome = "language_change"
        elif not worker_alive:
            check_outcome = "not_alive"
        else:
            check_outcome = "healthy"
        log_ocr_timing(
            request_id,
            "worker_health_check",
            attempt=attempt,
            worker_pid=self.worker_pid,
            worker_generation=self._worker_generation,
            outcome=check_outcome,
        )
        if self._process is not None:
            if self._language != language or not self._process.is_alive():
                self._stop_worker(
                    graceful=self._process.is_alive(),
                    request_id=request_id,
                    attempt=attempt,
                    reason=check_outcome,
                )
        if self._process is None:
            self._start_worker(language, request_id, attempt)

    @staticmethod
    def _validate_result(response: object, request_id: str) -> Dict[str, object]:
        if not isinstance(response, dict):
            raise OCRWorkerError("malformed_response")
        if "request_id" not in response:
            raise OCRWorkerError("malformed_response")
        if response.get("request_id") != request_id:
            raise OCRWorkerError("request_id_mismatch")
        if response.get("type") == "error":
            raise OCRWorkerError(
                str(response.get("stage") or "worker_exception"),
                str(response.get("exception_type") or "OCRWorkerError"),
            )
        if response.get("type") != "result":
            raise OCRWorkerError("malformed_response")
        if not isinstance(response.get("rows"), list):
            raise OCRWorkerError("malformed_rows")
        if not isinstance(response.get("reader_metadata"), dict):
            raise OCRWorkerError("malformed_metadata")
        try:
            response["inference_seconds"] = float(response.get("inference_seconds", 0.0))
        except (TypeError, ValueError):
            raise OCRWorkerError("malformed_timing")
        return response

    def _run_once(
        self,
        image_path: str,
        language: str,
        diagnostic_request_id: str,
        attempt: int,
    ) -> Dict[str, object]:
        self._ensure_worker(language, diagnostic_request_id, attempt)
        ipc_request_id = uuid.uuid4().hex
        request = {
            "type": "ocr",
            "request_id": ipc_request_id,
            "diagnostic_request_id": diagnostic_request_id,
            "attempt": attempt,
            "worker_generation": self._worker_generation,
            "image_path": image_path,
            "language": language,
        }
        send_start = time.perf_counter()
        try:
            self._connection.send(request)
        except (BrokenPipeError, EOFError, OSError, ValueError) as error:
            raise OCRWorkerError("request_send", type(error).__name__) from error
        log_ocr_timing(
            diagnostic_request_id,
            "ipc_request_sent",
            elapsed_seconds=time.perf_counter() - send_start,
            attempt=attempt,
            worker_pid=self.worker_pid,
            worker_generation=self._worker_generation,
        )

        response_wait_start = time.perf_counter()
        try:
            if not self._connection.poll(self.timeout_seconds):
                raise OCRWorkerError("timeout")
            response = self._connection.recv()
        except OCRWorkerError:
            raise
        except (BrokenPipeError, EOFError, OSError, ValueError) as error:
            raise OCRWorkerError("worker_exit", type(error).__name__) from error
        log_ocr_timing(
            diagnostic_request_id,
            "ipc_response_received",
            elapsed_seconds=time.perf_counter() - response_wait_start,
            attempt=attempt,
            worker_pid=self.worker_pid,
            worker_generation=self._worker_generation,
        )
        return self._validate_result(response, ipc_request_id)

    def run_ocr(
        self,
        image_path: str,
        language: str,
        diagnostic_request_id: Optional[str] = None,
    ) -> Dict[str, object]:
        request_id = _request_uuid(diagnostic_request_id)
        manager_start = time.perf_counter()
        log_ocr_timing(request_id, "manager_request_begin")
        if not Path(image_path).is_file():
            log_ocr_timing(
                request_id,
                "manager_request_end",
                elapsed_seconds=time.perf_counter() - manager_start,
                outcome="missing_temp_image",
            )
            raise OCRWorkerError("missing_temp_image", "FileNotFoundError")

        queue_start = time.perf_counter()
        log_ocr_timing(request_id, "manager_lock_requested")
        self._request_lock.acquire()
        queue_seconds = time.perf_counter() - queue_start
        lock_start = time.perf_counter()
        log_ocr_timing(
            request_id,
            "manager_lock_acquired",
            queue_seconds=queue_seconds,
            worker_pid=self.worker_pid,
            worker_generation=self._worker_generation,
        )
        manager_outcome = "failed"
        try:
            last_error: Optional[OCRWorkerError] = None
            for attempt in range(2):
                attempt_number = attempt + 1
                try:
                    result = self._run_once(
                        image_path,
                        language,
                        request_id,
                        attempt_number,
                    )
                except OCRWorkerError as error:
                    last_error = error
                    self._log_failure(error, attempt)
                    log_ocr_timing(
                        request_id,
                        "retry_triggered" if attempt == 0 else "attempt_failed",
                        elapsed_seconds=time.perf_counter() - manager_start,
                        attempt=attempt_number,
                        worker_pid=self.worker_pid,
                        worker_generation=self._worker_generation,
                        outcome=error.stage,
                    )
                    self._stop_worker(
                        graceful=False,
                        request_id=request_id,
                        attempt=attempt_number,
                        reason="retry" if attempt == 0 else "failed",
                    )
                    continue

                self._successful_jobs += 1
                result["worker_recovered"] = attempt == 1
                result["worker_recycled"] = self._successful_jobs >= self.max_jobs_per_worker
                if result["worker_recycled"]:
                    self._stop_worker(
                        graceful=True,
                        request_id=request_id,
                        attempt=attempt_number,
                        reason="job_limit_recycle",
                    )
                manager_outcome = "recovered" if attempt == 1 else "success"
                return result

            assert last_error is not None
            manager_outcome = last_error.stage
            raise last_error
        finally:
            self._request_lock.release()
            log_ocr_timing(
                request_id,
                "manager_lock_released",
                elapsed_seconds=time.perf_counter() - lock_start,
                queue_seconds=queue_seconds,
                worker_pid=self.worker_pid,
                worker_generation=self._worker_generation,
                outcome=manager_outcome,
            )
            log_ocr_timing(
                request_id,
                "manager_request_end",
                elapsed_seconds=time.perf_counter() - manager_start,
                queue_seconds=queue_seconds,
                outcome=manager_outcome,
            )

    @staticmethod
    def _log_failure(error: OCRWorkerError, attempt: int) -> None:
        print(
            "[pattern_ocr_worker] "
            f"outcome={'retry' if attempt == 0 else 'failed'} "
            f"stage={error.stage} exception_type={error.exception_type}",
            file=sys.stderr,
            flush=True,
        )

    def close(self) -> None:
        with self._request_lock:
            self._stop_worker(graceful=True)


_PROCESS_MANAGER: Optional[OCRWorkerManager] = None
_PROCESS_MANAGER_LOCK = threading.Lock()


def get_process_ocr_manager() -> OCRWorkerManager:
    global _PROCESS_MANAGER
    with _PROCESS_MANAGER_LOCK:
        if _PROCESS_MANAGER is None:
            _PROCESS_MANAGER = OCRWorkerManager()
        return _PROCESS_MANAGER


def close_process_ocr_manager() -> None:
    global _PROCESS_MANAGER
    with _PROCESS_MANAGER_LOCK:
        manager = _PROCESS_MANAGER
        _PROCESS_MANAGER = None
    if manager is not None:
        manager.close()


atexit.register(close_process_ocr_manager)
