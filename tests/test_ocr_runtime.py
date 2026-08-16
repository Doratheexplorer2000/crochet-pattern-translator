import threading
import time
import unittest
from pathlib import Path

from pattern_translator.engine import ocr_runtime


class OCRRuntimeTests(unittest.TestCase):
    def test_paddle_operations_are_serialized_across_threads(self):
        state_lock = threading.Lock()
        barrier = threading.Barrier(2)
        active = 0
        maximum_active = 0
        results = []

        def operation(value):
            nonlocal active, maximum_active
            with state_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.03)
            with state_lock:
                active -= 1
            return value

        def worker(value):
            barrier.wait()
            results.append(ocr_runtime.run_serialized(operation, value))

        threads = [threading.Thread(target=worker, args=(value,)) for value in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(sorted(results), [1, 2])
        self.assertEqual(maximum_active, 1)

    def test_paddle_lock_is_released_after_failure(self):
        def fail():
            raise RuntimeError("synthetic Paddle failure")

        with self.assertRaises(RuntimeError):
            ocr_runtime.run_serialized(fail)

        self.assertEqual(ocr_runtime.run_serialized(lambda: "recovered"), "recovered")

    def test_app_serializes_reader_creation_and_inference(self):
        app_source = (
            Path(__file__).resolve().parents[1] / "pattern_translator" / "app.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "ocr_runtime_engine.run_serialized(get_paddle_reader, lang)",
            app_source,
        )
        self.assertIn(
            "ocr_runtime_engine.run_serialized(ocr.predict, image_path)",
            app_source,
        )
        self.assertIn("ocr_runtime_engine.run_serialized(\n                ocr.ocr,", app_source)

    def test_ocr_failure_does_not_render_raw_exception(self):
        app_source = (
            Path(__file__).resolve().parents[1] / "pattern_translator" / "app.py"
        ).read_text(encoding="utf-8")

        self.assertIn('st.error(t("ocr_failed"))', app_source)
        self.assertNotIn("st.exception(e)", app_source)


if __name__ == "__main__":
    unittest.main()
