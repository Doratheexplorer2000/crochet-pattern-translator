from __future__ import annotations

import atexit
import multiprocessing
import os
import sys
import threading
import uuid
from pathlib import Path
from typing import Dict, Optional

from pattern_translator.engine.ocr_worker import run_worker


DEFAULT_OCR_TIMEOUT_SECONDS = 90.0
DEFAULT_MAX_JOBS_PER_WORKER = 4
_WORKER_STOP_GRACE_SECONDS = 3.0


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

    @property
    def worker_pid(self) -> Optional[int]:
        return getattr(self._process, "pid", None)

    @property
    def successful_jobs(self) -> int:
        return self._successful_jobs

    def _start_worker(self, language: str) -> None:
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

    def _stop_worker(self, graceful: bool) -> None:
        process = self._process
        connection = self._connection
        self._process = None
        self._connection = None
        self._language = None
        self._successful_jobs = 0

        if process is None:
            if connection is not None:
                connection.close()
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

    def _ensure_worker(self, language: str) -> None:
        if self._process is not None:
            if self._language != language or not self._process.is_alive():
                self._stop_worker(graceful=self._process.is_alive())
        if self._process is None:
            self._start_worker(language)

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

    def _run_once(self, image_path: str, language: str) -> Dict[str, object]:
        self._ensure_worker(language)
        request_id = uuid.uuid4().hex
        request = {
            "type": "ocr",
            "request_id": request_id,
            "image_path": image_path,
            "language": language,
        }
        try:
            self._connection.send(request)
        except (BrokenPipeError, EOFError, OSError, ValueError) as error:
            raise OCRWorkerError("request_send", type(error).__name__) from error

        try:
            if not self._connection.poll(self.timeout_seconds):
                raise OCRWorkerError("timeout")
            response = self._connection.recv()
        except OCRWorkerError:
            raise
        except (BrokenPipeError, EOFError, OSError, ValueError) as error:
            raise OCRWorkerError("worker_exit", type(error).__name__) from error
        return self._validate_result(response, request_id)

    def run_ocr(self, image_path: str, language: str) -> Dict[str, object]:
        if not Path(image_path).is_file():
            raise OCRWorkerError("missing_temp_image", "FileNotFoundError")

        with self._request_lock:
            last_error: Optional[OCRWorkerError] = None
            for attempt in range(2):
                try:
                    result = self._run_once(image_path, language)
                except OCRWorkerError as error:
                    last_error = error
                    self._log_failure(error, attempt)
                    self._stop_worker(graceful=False)
                    continue

                self._successful_jobs += 1
                result["worker_recovered"] = attempt == 1
                result["worker_recycled"] = self._successful_jobs >= self.max_jobs_per_worker
                if result["worker_recycled"]:
                    self._stop_worker(graceful=True)
                return result

            assert last_error is not None
            raise last_error

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
