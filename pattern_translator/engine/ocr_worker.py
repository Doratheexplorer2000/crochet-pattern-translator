from __future__ import annotations

import gc
import os
import resource
import sys
import time
from typing import Dict, List, Tuple

import numpy as np


def _box_to_coords(box) -> Tuple[float, float, float, float]:
    try:
        arr = np.array(box, dtype=float)
        if arr.ndim == 1 and arr.size >= 4:
            xs = [arr[0], arr[2]]
            ys = [arr[1], arr[3]]
        else:
            xs = arr[:, 0]
            ys = arr[:, 1]
        return float(np.min(xs)), float(np.max(xs)), float(np.min(ys)), float(np.max(ys))
    except Exception:
        return 0.0, 80.0, 0.0, 20.0


def normalize_paddle_result(result: object) -> List[Dict[str, object]]:
    """Convert Paddle results into IPC-safe row dictionaries."""
    rows: List[Dict[str, object]] = []

    def add_row(text: object, confidence: object = None, box: object = None) -> None:
        clean = str(text).strip() if text is not None else ""
        if not clean:
            return
        try:
            conf = float(confidence) if confidence is not None else 0.0
        except Exception:
            conf = 0.0
        min_x, max_x, min_y, max_y = _box_to_coords(box)
        rows.append({
            "source": "PaddleOCR",
            "text": clean,
            "confidence": round(conf, 3),
            "x": round((min_x + max_x) / 2, 1),
            "global_x": round((min_x + max_x) / 2, 1),
            "y": round((min_y + max_y) / 2, 1),
            "min_x": round(min_x, 1),
            "max_x": round(max_x, 1),
            "min_y": round(min_y, 1),
            "max_y": round(max_y, 1),
        })

    if isinstance(result, list):
        for page in result:
            if isinstance(page, dict):
                texts = page.get("rec_texts")
                if texts is None:
                    texts = page.get("texts")
                scores = page.get("rec_scores")
                if scores is None:
                    scores = page.get("scores")
                boxes = page.get("rec_polys")
                if boxes is None:
                    boxes = page.get("dt_polys")
                if boxes is None:
                    boxes = page.get("boxes")
                texts = [] if texts is None else texts
                scores = [] if scores is None else scores
                boxes = [] if boxes is None else boxes
                if len(texts):
                    for index, text in enumerate(texts):
                        add_row(
                            text,
                            scores[index] if index < len(scores) else None,
                            boxes[index] if index < len(boxes) else None,
                        )
                    continue
            if isinstance(page, list):
                for item in page:
                    try:
                        box = item[0]
                        recognition = item[1]
                        if isinstance(recognition, (list, tuple)) and len(recognition) >= 2:
                            add_row(recognition[0], recognition[1], box)
                        elif isinstance(recognition, str):
                            add_row(recognition, None, box)
                    except Exception:
                        if isinstance(item, str):
                            add_row(item)

    return sorted(rows, key=lambda row: (row["y"], row["global_x"]))


def _create_reader(language: str):
    # PaddleOCR is deliberately imported only inside the isolated worker.
    from paddleocr import PaddleOCR

    try:
        return PaddleOCR(
            lang=language,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except TypeError:
        return PaddleOCR(lang=language, use_angle_cls=False)


def _safe_error_response(request_id: str, stage: str, error: Exception) -> Dict[str, object]:
    return {
        "type": "error",
        "request_id": request_id,
        "stage": stage,
        "exception_type": type(error).__name__,
    }


def _worker_rss_mb() -> float:
    statm = "/proc/self/statm"
    if os.path.isfile(statm):
        try:
            with open(statm, encoding="ascii") as status:
                resident_pages = int(status.read().split()[1])
            return round(resident_pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024), 1)
        except Exception:
            pass
    maximum_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return round(maximum_rss / divisor, 1)


def run_worker(connection, language: str) -> None:
    """Own one Paddle reader and process OCR requests serially."""
    reader = None
    try:
        while True:
            request = connection.recv()
            if not isinstance(request, dict):
                return
            if request.get("type") == "shutdown":
                return

            request_id = str(request.get("request_id") or "")
            if request.get("type") != "ocr" or request.get("language") != language:
                connection.send(_safe_error_response(request_id, "request", ValueError("invalid request")))
                return

            try:
                if reader is None:
                    stage = "reader_init"
                    reader = _create_reader(language)

                stage = "predict"
                inference_start = time.perf_counter()
                try:
                    raw_result = reader.predict(request["image_path"])
                except AttributeError:
                    stage = "legacy_ocr"
                    raw_result = reader.ocr(request["image_path"], cls=False)
                inference_seconds = time.perf_counter() - inference_start

                stage = "normalize"
                rows = normalize_paddle_result(raw_result)
                connection.send({
                    "type": "result",
                    "request_id": request_id,
                    "rows": rows,
                    "inference_seconds": inference_seconds,
                    "reader_metadata": {
                        "class": type(reader).__name__,
                        "detector_model": str(getattr(reader, "det_model_dir", "") or ""),
                        "recognizer_model": str(getattr(reader, "rec_model_dir", "") or ""),
                    },
                    "worker_pid": os.getpid(),
                    "worker_rss_mb": _worker_rss_mb(),
                })
            except Exception as error:
                try:
                    connection.send(_safe_error_response(request_id, stage, error))
                finally:
                    return
    except (EOFError, BrokenPipeError, OSError):
        return
    finally:
        if reader is not None:
            del reader
        gc.collect()
        try:
            connection.close()
        except Exception:
            pass
