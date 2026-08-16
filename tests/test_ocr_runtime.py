import multiprocessing
import io
import os
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

import numpy as np

from pattern_translator.engine import ocr_runtime
from pattern_translator.engine import ocr_worker
from pattern_translator.engine.ocr_worker import normalize_paddle_result


def _result_response(request, language):
    return {
        "type": "result",
        "request_id": request["request_id"],
        "rows": [{
            "source": "PaddleOCR",
            "text": f"{language}:{request['request_id']}",
            "confidence": 0.99,
            "x": 1.0,
            "global_x": 1.0,
            "y": 1.0,
            "min_x": 0.0,
            "max_x": 2.0,
            "min_y": 0.0,
            "max_y": 2.0,
        }],
        "inference_seconds": 0.01,
        "reader_metadata": {"class": "FakeReader", "detector_model": "", "recognizer_model": ""},
        "worker_pid": os.getpid(),
    }


def echo_worker(connection, language):
    try:
        while True:
            request = connection.recv()
            if request.get("type") == "shutdown":
                return
            time.sleep(0.02)
            connection.send(_result_response(request, language))
    except (EOFError, BrokenPipeError, OSError):
        return


def fail_once_worker(connection, language):
    request = connection.recv()
    marker = request["image_path"] + ".attempt"
    if not os.path.exists(marker):
        Path(marker).write_text("failed", encoding="ascii")
        connection.send({
            "type": "error",
            "request_id": request["request_id"],
            "stage": "predict",
            "exception_type": "RuntimeError",
        })
        return
    connection.send(_result_response(request, language))


def always_error_worker(connection, _language):
    request = connection.recv()
    with open(request["image_path"] + ".attempts", "a", encoding="ascii") as output:
        output.write("x")
    connection.send({
        "type": "error",
        "request_id": request["request_id"],
        "stage": "predict",
        "exception_type": "RuntimeError",
    })


def mismatch_worker(connection, language):
    request = connection.recv()
    response = _result_response(request, language)
    response["request_id"] = "stale-request"
    connection.send(response)


def malformed_worker(connection, _language):
    connection.recv()
    connection.send({"unexpected": True})


def eof_worker(connection, _language):
    connection.recv()
    connection.close()


def crash_worker(connection, _language):
    connection.recv()
    os._exit(7)


def hanging_worker(connection, _language):
    connection.recv()
    time.sleep(2)


class OCRRuntimeTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        handle.write(b"fake-image")
        handle.close()
        self.image_path = handle.name
        self.context = multiprocessing.get_context("spawn")

    def tearDown(self):
        for suffix in ("", ".attempt", ".attempts"):
            try:
                os.unlink(self.image_path + suffix)
            except FileNotFoundError:
                pass

    def manager(self, worker_target=echo_worker, **kwargs):
        return ocr_runtime.OCRWorkerManager(
            timeout_seconds=kwargs.pop("timeout_seconds", 1),
            max_jobs_per_worker=kwargs.pop("max_jobs_per_worker", 10),
            process_context=self.context,
            worker_target=worker_target,
            **kwargs,
        )

    @staticmethod
    def timing_lines(output, request_id=None):
        lines = [
            line for line in output.splitlines()
            if line.startswith("[pattern_ocr_timing]")
        ]
        if request_id:
            lines = [line for line in lines if f"request_id={request_id}" in line]
        return lines

    def test_soft_launch_defaults_and_environment_overrides(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            manager = ocr_runtime.OCRWorkerManager(process_context=self.context)
            self.assertEqual(manager.timeout_seconds, 90.0)
            self.assertEqual(manager.max_jobs_per_worker, 4)
        with mock.patch.dict(
            os.environ,
            {
                "PATTERN_OCR_WORKER_TIMEOUT_SECONDS": "75",
                "PATTERN_OCR_MAX_JOBS_PER_WORKER": "3",
            },
            clear=True,
        ):
            manager = ocr_runtime.OCRWorkerManager(process_context=self.context)
            self.assertEqual(manager.timeout_seconds, 75.0)
            self.assertEqual(manager.max_jobs_per_worker, 3)

    def test_worker_starts_lazily_and_handles_sequential_requests(self):
        manager = self.manager()
        self.assertIsNone(manager.worker_pid)
        first = manager.run_ocr(self.image_path, "en")
        first_pid = first["worker_pid"]
        second = manager.run_ocr(self.image_path, "en")
        self.assertEqual(second["worker_pid"], first_pid)
        self.assertEqual(manager.successful_jobs, 2)
        manager.close()
        self.assertIsNone(manager.worker_pid)

    def test_concurrent_callers_are_serialized_and_correlated(self):
        manager = self.manager()
        results = []

        def call():
            results.append(manager.run_ocr(self.image_path, "en"))

        threads = [threading.Thread(target=call) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        texts = [result["rows"][0]["text"] for result in results]
        self.assertEqual(len(set(texts)), 3)
        self.assertEqual(len({result["worker_pid"] for result in results}), 1)
        manager.close()

    def test_concurrent_callers_log_distinct_lock_queue_waits(self):
        manager = self.manager()
        request_ids = ["a" * 32, "b" * 32]
        results = []
        logs = io.StringIO()

        def call(request_id):
            results.append(
                manager.run_ocr(
                    self.image_path,
                    "en",
                    diagnostic_request_id=request_id,
                )
            )

        with redirect_stderr(logs):
            first = threading.Thread(target=call, args=(request_ids[0],))
            second = threading.Thread(target=call, args=(request_ids[1],))
            first.start()
            time.sleep(0.01)
            second.start()
            first.join(timeout=5)
            second.join(timeout=5)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(len(results), 2)
        first_lines = self.timing_lines(logs.getvalue(), request_ids[0])
        second_lines = self.timing_lines(logs.getvalue(), request_ids[1])
        self.assertTrue(any("phase=manager_lock_acquired" in line for line in first_lines))
        second_acquired = next(
            line for line in second_lines if "phase=manager_lock_acquired" in line
        )
        queue_field = next(
            field for field in second_acquired.split() if field.startswith("queue_wait_ms=")
        )
        self.assertGreater(float(queue_field.split("=", 1)[1]), 0.0)
        self.assertTrue(any("phase=manager_lock_released" in line for line in first_lines))
        self.assertTrue(any("phase=manager_lock_released" in line for line in second_lines))
        manager.close()

    def test_inference_failure_restarts_and_retries_once(self):
        manager = self.manager(fail_once_worker)
        logs = io.StringIO()
        with redirect_stderr(logs):
            result = manager.run_ocr(
                self.image_path,
                "en",
                diagnostic_request_id="c" * 32,
            )
        self.assertTrue(result["worker_recovered"])
        self.assertTrue(os.path.exists(self.image_path + ".attempt"))
        timing_lines = self.timing_lines(logs.getvalue(), "c" * 32)
        self.assertTrue(any("phase=retry_triggered" in line for line in timing_lines))
        self.assertTrue(any("attempt=1" in line for line in timing_lines))
        self.assertTrue(any("attempt=2" in line for line in timing_lines))
        self.assertTrue(
            any(
                "phase=manager_request_end" in line and "outcome=recovered" in line
                for line in timing_lines
            )
        )
        manager.close()

    def test_second_failure_stops_after_exactly_two_attempts(self):
        manager = self.manager(always_error_worker)
        logs = io.StringIO()
        with redirect_stderr(logs):
            with self.assertRaisesRegex(ocr_runtime.OCRWorkerError, "predict"):
                manager.run_ocr(
                    self.image_path,
                    "en",
                    diagnostic_request_id="d" * 32,
                )
        attempts = Path(self.image_path + ".attempts").read_text(encoding="ascii")
        self.assertEqual(attempts, "xx")
        self.assertIsNone(manager.worker_pid)
        timing_lines = self.timing_lines(logs.getvalue(), "d" * 32)
        self.assertTrue(any("phase=manager_lock_released" in line for line in timing_lines))
        self.assertTrue(
            any(
                "phase=manager_request_end" in line and "outcome=predict" in line
                for line in timing_lines
            )
        )

    def test_timeout_retries_once_then_stops(self):
        manager = self.manager(hanging_worker, timeout_seconds=0.05)
        started = time.perf_counter()
        logs = io.StringIO()
        with redirect_stderr(logs):
            with self.assertRaisesRegex(ocr_runtime.OCRWorkerError, "timeout"):
                manager.run_ocr(
                    self.image_path,
                    "en",
                    diagnostic_request_id="e" * 32,
                )
        self.assertLess(time.perf_counter() - started, 2)
        self.assertIsNone(manager.worker_pid)
        timing_lines = self.timing_lines(logs.getvalue(), "e" * 32)
        self.assertEqual(
            sum("phase=retry_triggered" in line for line in timing_lines),
            1,
        )
        self.assertTrue(any("phase=manager_lock_released" in line for line in timing_lines))
        self.assertTrue(
            any(
                "phase=manager_request_end" in line and "outcome=timeout" in line
                for line in timing_lines
            )
        )

    def test_timing_logs_never_include_image_path_or_user_content(self):
        manager = self.manager()
        request_id = "f" * 32
        logs = io.StringIO()
        with redirect_stderr(logs):
            result = manager.run_ocr(
                self.image_path,
                "en",
                diagnostic_request_id=request_id,
            )
        output = logs.getvalue()
        self.assertTrue(result["rows"])
        self.assertNotIn(self.image_path, output)
        self.assertNotIn(result["rows"][0]["text"], output)
        self.assertNotIn("image_path", output)
        self.assertNotIn("language=en", output)
        manager.close()

    def test_worker_logs_initialization_and_inference_without_content(self):
        class FakeConnection:
            def __init__(self, requests):
                self.requests = iter(requests)
                self.responses = []

            def recv(self):
                return next(self.requests)

            def send(self, response):
                self.responses.append(response)

            def close(self):
                return None

        class FakeReader:
            def predict(self, _image_path):
                return []

        diagnostic_request_id = "1" * 32
        sensitive_path = "/tmp/private-pattern-owner-name.png"
        connection = FakeConnection([
            {
                "type": "ocr",
                "request_id": "2" * 32,
                "diagnostic_request_id": diagnostic_request_id,
                "attempt": 1,
                "worker_generation": 7,
                "image_path": sensitive_path,
                "language": "en",
            },
            {"type": "shutdown"},
        ])
        logs = io.StringIO()
        with mock.patch.object(ocr_worker, "_create_reader", return_value=FakeReader()):
            with redirect_stderr(logs):
                ocr_worker.run_worker(connection, "en")

        output = logs.getvalue()
        for phase in (
            "worker_ready",
            "reader_init_begin",
            "reader_init_end",
            "worker_inference_begin",
            "worker_inference_end",
        ):
            self.assertIn(f"phase={phase}", output)
        self.assertIn(f"request_id={diagnostic_request_id}", output)
        self.assertIn("monotonic_ms=", output)
        self.assertIn("worker_generation=7", output)
        self.assertNotIn(sensitive_path, output)
        self.assertEqual(connection.responses[0]["type"], "result")

    def test_crash_and_eof_fail_cleanly_after_one_retry(self):
        for target in (crash_worker, eof_worker):
            with self.subTest(target=target.__name__):
                manager = self.manager(target)
                with self.assertRaises(ocr_runtime.OCRWorkerError):
                    manager.run_ocr(self.image_path, "en")
                self.assertIsNone(manager.worker_pid)

    def test_malformed_and_mismatched_responses_are_never_accepted(self):
        for target, stage in (
            (malformed_worker, "malformed_response"),
            (mismatch_worker, "request_id_mismatch"),
        ):
            with self.subTest(target=target.__name__):
                manager = self.manager(target)
                with self.assertRaisesRegex(ocr_runtime.OCRWorkerError, stage):
                    manager.run_ocr(self.image_path, "en")
                self.assertIsNone(manager.worker_pid)

    def test_worker_recycles_after_configured_success_limit(self):
        manager = self.manager(max_jobs_per_worker=2)
        first = manager.run_ocr(self.image_path, "en")
        second = manager.run_ocr(self.image_path, "en")
        self.assertEqual(first["worker_pid"], second["worker_pid"])
        self.assertTrue(second["worker_recycled"])
        self.assertIsNone(manager.worker_pid)
        third = manager.run_ocr(self.image_path, "en")
        self.assertNotEqual(third["worker_pid"], first["worker_pid"])
        manager.close()

    def test_language_change_recycles_instead_of_retaining_two_readers(self):
        manager = self.manager()
        english = manager.run_ocr(self.image_path, "en")
        chinese = manager.run_ocr(self.image_path, "ch")
        self.assertNotEqual(english["worker_pid"], chinese["worker_pid"])
        self.assertTrue(chinese["rows"][0]["text"].startswith("ch:"))
        manager.close()

    def test_temp_file_remains_available_until_response(self):
        manager = self.manager()
        manager.run_ocr(self.image_path, "en")
        self.assertTrue(os.path.isfile(self.image_path))
        manager.close()

    def test_missing_temp_file_does_not_start_worker(self):
        manager = self.manager()
        os.unlink(self.image_path)
        with self.assertRaisesRegex(ocr_runtime.OCRWorkerError, "missing_temp_image"):
            manager.run_ocr(self.image_path, "en")
        self.assertIsNone(manager.worker_pid)

    def test_normalized_rows_preserve_current_order_confidence_and_boxes(self):
        result = [{
            "rec_texts": ["second", "first"],
            "rec_scores": np.array([0.87654, 0.99123]),
            "rec_polys": np.array([
                [[20, 20], [40, 20], [40, 30], [20, 30]],
                [[1, 2], [11, 2], [11, 8], [1, 8]],
            ]),
        }]
        rows = normalize_paddle_result(result)
        self.assertEqual([row["text"] for row in rows], ["first", "second"])
        self.assertEqual(rows[0]["confidence"], 0.991)
        self.assertEqual(
            {key: rows[0][key] for key in ("min_x", "max_x", "min_y", "max_y", "x", "y")},
            {"min_x": 1.0, "max_x": 11.0, "min_y": 2.0, "max_y": 8.0, "x": 6.0, "y": 5.0},
        )

    def test_streamlit_process_has_no_paddle_reader_or_direct_predict_call(self):
        app_source = (
            Path(__file__).resolve().parents[1] / "pattern_translator" / "app.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("from paddleocr import PaddleOCR", app_source)
        self.assertNotIn("get_paddle_reader", app_source)
        self.assertNotIn("reader.predict(", app_source)
        self.assertIn("ocr_runtime_engine.get_process_ocr_manager().run_ocr(", app_source)
        self.assertIn("diagnostic_request_id=diagnostic_request_id", app_source)
        for phase in (
            "translation_action_accepted",
            "pending_run_begin",
            "pre_ocr_preparation_begin",
            "pre_ocr_preparation_end",
            "temp_image_preparation_begin",
            "temp_image_preparation_end",
            "downstream_translation_begin",
            "translation_run_end",
        ):
            self.assertIn(f'"{phase}"', app_source)
        self.assertIn("finally:\n        try:\n            os.remove(image_path)", app_source)

        worker_source = (
            Path(__file__).resolve().parents[1]
            / "pattern_translator"
            / "engine"
            / "ocr_worker.py"
        ).read_text(encoding="utf-8")
        self.assertEqual(worker_source.count("from paddleocr import PaddleOCR"), 1)

    def test_ocr_failure_does_not_render_raw_exception(self):
        app_source = (
            Path(__file__).resolve().parents[1] / "pattern_translator" / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn('st.error(t("ocr_failed"))', app_source)
        self.assertNotIn("st.exception(e)", app_source)


if __name__ == "__main__":
    unittest.main()
