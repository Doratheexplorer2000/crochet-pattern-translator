import copy
import json
import threading
import re
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
from streamlit.runtime.scriptrunner_utils.exceptions import RerunException
from streamlit.runtime.scriptrunner_utils.script_requests import (
    RerunData,
    ScriptRequests,
    ScriptRequestType,
)
from streamlit.runtime.state import SafeSessionState, SessionState

from pattern_translator.engine import diagnostic_report
from pattern_translator.engine import ocr_request_lifecycle
from pattern_translator.engine import result_delivery


class ResultDeliveryTests(unittest.TestCase):
    def test_producer_can_publish_claim_and_commit_in_same_run(self):
        handoff = result_delivery.CompletedResultHandoff()
        payload = {"primary_result": {"readable_translation": "translated"}}
        session_state = {}

        published, _ = handoff.publish("session-a", "request-a", payload)
        claimed, _ = handoff.claim(
            "session-a",
            "request-a",
            lambda delivery: result_delivery.store_primary_result(
                session_state, delivery["primary_result"]
            ),
        )

        self.assertTrue(published)
        self.assertIs(claimed, payload)
        self.assertEqual(
            session_state["rc3_ocr_result"]["readable_translation"],
            "translated",
        )
        self.assertEqual(handoff.entry_count(), 0)

    def test_streamlit_rerun_after_publish_preserves_result_for_next_run(self):
        handoff = result_delivery.CompletedResultHandoff()
        payload = {"primary_result": {"readable_translation": "translated"}}
        published, _ = handoff.publish("session-a", "request-a", payload)
        self.assertTrue(published)

        interrupted_state = SafeSessionState(
            SessionState(),
            lambda: (_ for _ in ()).throw(RerunException(RerunData())),
        )
        with self.assertRaises(RerunException):
            handoff.claim(
                "session-a",
                "request-a",
                lambda delivery: result_delivery.store_primary_result(
                    interrupted_state, delivery["primary_result"]
                ),
            )

        self.assertEqual(handoff.entry_count(), 1)
        next_run_state = {}
        claimed, _ = handoff.claim(
            "session-a",
            "request-a",
            lambda delivery: result_delivery.store_primary_result(
                next_run_state, delivery["primary_result"]
            ),
        )
        self.assertIs(claimed, payload)
        self.assertEqual(
            next_run_state["rc3_ocr_result"]["readable_translation"],
            "translated",
        )
        self.assertEqual(handoff.entry_count(), 0)

    def test_completed_result_is_claimed_exactly_once(self):
        handoff = result_delivery.CompletedResultHandoff()
        payload = {"primary_result": {"value": "complete"}}
        handoff.publish("session-a", "request-a", payload)
        deliveries = []

        first, _ = handoff.claim(
            "session-a", "request-a", deliveries.append
        )
        second, _ = handoff.claim(
            "session-a", "request-a", deliveries.append
        )

        self.assertIs(first, payload)
        self.assertIsNone(second)
        self.assertEqual(deliveries, [payload])

    def test_concurrent_claimers_deliver_only_once(self):
        handoff = result_delivery.CompletedResultHandoff()
        payload = {"primary_result": {"value": "complete"}}
        handoff.publish("session-a", "request-a", payload)
        delivery_started = threading.Event()
        release_delivery = threading.Event()
        delivered = []
        claim_results = []

        def deliver(delivery):
            delivered.append(delivery)
            delivery_started.set()
            release_delivery.wait(timeout=2)

        def claim():
            claim_results.append(
                handoff.claim("session-a", "request-a", deliver)[0]
            )

        first = threading.Thread(target=claim)
        second = threading.Thread(target=claim)
        first.start()
        self.assertTrue(delivery_started.wait(timeout=1))
        second.start()
        release_delivery.set()
        first.join(timeout=1)
        second.join(timeout=1)

        self.assertEqual(delivered, [payload])
        self.assertEqual(sum(result is payload for result in claim_results), 1)
        self.assertEqual(sum(result is None for result in claim_results), 1)

    def test_session_generations_and_request_ids_are_isolated(self):
        handoff = result_delivery.CompletedResultHandoff()
        payload = {"primary_result": {"value": "complete"}}
        handoff.publish("session-a", "request-a", payload)

        wrong_session, _ = handoff.claim(
            "session-b", "request-a", lambda delivery: None
        )
        wrong_request, _ = handoff.claim(
            "session-a", "request-b", lambda delivery: None
        )
        correct, _ = handoff.claim(
            "session-a", "request-a", lambda delivery: None
        )

        self.assertIsNone(wrong_session)
        self.assertIsNone(wrong_request)
        self.assertIs(correct, payload)

    def test_successful_claim_finishes_request_lifecycle(self):
        handoff = result_delivery.CompletedResultHandoff()
        request_id = "request-a"
        session_state = {
            "ocr_request_lifecycle": {
                "request_id": request_id,
                "state": ocr_request_lifecycle.RUNNING,
            }
        }
        payload = {"primary_result": {"value": "complete"}}
        handoff.publish("session-a", request_id, payload)

        def deliver(delivery):
            result_delivery.store_primary_result(
                session_state, delivery["primary_result"]
            )
            session_state["ocr_request_lifecycle"] = (
                ocr_request_lifecycle.finish_request(
                    session_state["ocr_request_lifecycle"],
                    request_id,
                    succeeded=True,
                )
            )

        handoff.claim("session-a", request_id, deliver)

        self.assertEqual(
            session_state["ocr_request_lifecycle"]["state"],
            ocr_request_lifecycle.COMPLETED,
        )

    def test_completed_delivery_cannot_replay_expensive_work(self):
        handoff = result_delivery.CompletedResultHandoff()
        payload = {"primary_result": {"area_mode": "Whole Pattern"}}
        handoff.publish("session-a", "request-a", payload)
        delivery_count = 0

        def deliver(delivery):
            nonlocal delivery_count
            delivery_count += 1

        handoff.claim("session-a", "request-a", deliver)
        handoff.claim("session-a", "request-a", deliver)

        self.assertEqual(delivery_count, 1)

    def test_whole_pattern_and_select_area_use_same_handoff(self):
        for area_mode in ("Whole Pattern", "Select Area"):
            with self.subTest(area_mode=area_mode):
                handoff = result_delivery.CompletedResultHandoff()
                payload = {"primary_result": {"area_mode": area_mode}}
                handoff.publish("session-a", area_mode, payload)
                delivered = []
                handoff.claim("session-a", area_mode, delivered.append)
                self.assertEqual(
                    delivered[0]["primary_result"]["area_mode"], area_mode
                )

    def test_expired_entries_are_removed(self):
        now = [10.0]
        handoff = result_delivery.CompletedResultHandoff(
            ttl_seconds=5.0,
            clock=lambda: now[0],
        )
        handoff.publish("session-a", "request-a", {"value": "old"})
        now[0] = 15.0

        self.assertEqual(handoff.cleanup_expired(), 1)
        self.assertEqual(handoff.entry_count(), 0)

    def test_handoff_has_a_hard_entry_bound(self):
        now = [0.0]
        handoff = result_delivery.CompletedResultHandoff(
            ttl_seconds=100.0,
            max_entries=2,
            clock=lambda: now[0],
        )
        for request_id in ("request-a", "request-b", "request-c"):
            handoff.publish("session-a", request_id, {"request": request_id})
            now[0] += 1.0

        self.assertEqual(handoff.entry_count(), 2)
        oldest, _ = handoff.claim(
            "session-a", "request-a", lambda delivery: None
        )
        self.assertIsNone(oldest)

    def test_primary_result_is_stored_without_diagnostic_report(self):
        session_state = {}
        result = {"readable_translation": "translated", "overlay_png": b"png"}

        result_delivery.store_primary_result(session_state, result)

        self.assertIs(session_state["rc3_ocr_result"], result)
        self.assertNotIn("debug_report_txt", result)

    def test_diagnostic_exception_does_not_destroy_primary_result(self):
        session_state = {}
        result = {"readable_translation": "translated", "overlay_png": b"png"}
        result_delivery.store_primary_result(session_state, result)

        def fail():
            raise RuntimeError("synthetic report failure")

        generated, outcome = result_delivery.generate_optional_diagnostic_report(
            result, fail
        )

        self.assertFalse(generated)
        self.assertEqual(outcome, "generation_error")
        self.assertEqual(
            session_state["rc3_ocr_result"]["readable_translation"], "translated"
        )
        self.assertNotIn("debug_report_txt", result)

    def test_diagnostic_stall_cannot_delay_primary_result_commit(self):
        session_state = {}
        result = {"readable_translation": "translated", "overlay_png": b"png"}
        result_delivery.store_primary_result(session_state, result)
        builder_started = threading.Event()
        release_builder = threading.Event()

        def stall():
            builder_started.set()
            release_builder.wait(timeout=2)
            return "report"

        worker = threading.Thread(
            target=result_delivery.generate_optional_diagnostic_report,
            args=(result, stall),
        )
        worker.start()
        self.assertTrue(builder_started.wait(timeout=1))
        self.assertEqual(
            session_state["rc3_ocr_result"]["readable_translation"], "translated"
        )
        self.assertNotIn("debug_report_txt", result)
        release_builder.set()
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result["debug_report_txt"], "report")

    def test_successful_diagnostic_report_remains_downloadable(self):
        result = {"readable_translation": "translated"}

        generated, outcome = result_delivery.generate_optional_diagnostic_report(
            result, lambda: "diagnostic report"
        )

        self.assertTrue(generated)
        self.assertEqual(outcome, "success")
        self.assertEqual(result["debug_report_txt"], "diagnostic report")

    def test_existing_report_builder_still_generates_normal_report(self):
        line_df = pd.DataFrame(
            [{"original": "R1", "translated": "Round 1"}]
        )

        report = diagnostic_report.build_debug_report_text(line_df)

        self.assertIn("Diagnostic Report", report)
        self.assertIn("Translation Output", report)

    def test_diagnostic_snapshot_round_trip_preserves_report_data(self):
        line_df = pd.DataFrame(
            [
                {
                    "Original": "R1: 6X",
                    "Translation": "R1: 6 sc",
                    "Confidence": 0.99,
                    "Changed": "✓",
                    "min_x": 1.0,
                    "max_x": 20.0,
                    "min_y": 2.0,
                    "max_y": 22.0,
                }
            ]
        )
        ocr_boxes = pd.DataFrame(
            [
                {
                    "text": "R1: 6X",
                    "confidence": 0.99,
                    "min_x": 1.0,
                    "max_x": 20.0,
                    "min_y": 2.0,
                    "max_y": 22.0,
                }
            ]
        )
        result = {
            "line_df": line_df,
            "ocr_rows": ocr_boxes.copy(),
            "overlay_legend": "[1] R1: 6 sc",
            "overlay_legend_df": pd.DataFrame([{"label": "[1]"}]),
            "raw_ocr_text": "R1: 6X",
            "clean_text": "R1: 6X",
            "matches_df": pd.DataFrame(
                [
                    {
                        "Original detected": "X",
                        "Category": "stitch",
                        "US abb": "sc",
                    }
                ]
            ),
            "unmatched": ["R1"],
            "readable_translation": "R1: 6X\n→ R1: 6 sc",
            "quality_metrics": {"width_px": 120, "height_px": 80},
            "timings": {"Translation processing": 0.2, "Total runtime": 1.0},
            "runtime_profile": {
                "translation": 0.2,
                "diagnostic_report_generation": None,
                "total": 1.0,
            },
            "translation_profile": {
                "counts": {"lookup_term calls": 1},
                "timings": {},
            },
            "source_mode": "Traditional Chinese",
            "output_mode": "English — US",
            "area_mode": "Whole Pattern",
            "crop_box": (0, 0, 120, 80),
            "diagnostic_report_inputs": {
                "ocr_engine": "PaddleOCR",
                "image_quality_status": "Not assessed",
                "session_diagnostics": {"ocr_running": False},
                "events": [{"event": "snapshot"}],
                "ocr_workload_diagnostics": {"ocr_box_count": 1},
                "ocr_box_rows": ocr_boxes,
                "ocr_call_diagnostics": {
                    "whole_pattern_sends_full_image": True
                },
                "ocr_call_trace": ["OCR results returned"],
                "downscale_diagnostics": {"downscale_applied": "No"},
                "ocr_resize_test": "1000 px",
                "interface_language": "English",
                "platform": "unit-test-agent",
            },
        }
        cache_stats = {"hits": 2, "misses": 1}
        lookup_stats = {"enabled": "Yes", "index_size": 3}
        snapshot = result_delivery.create_diagnostic_snapshot(
            result,
            terminology_row_count=7,
            csv_term_cache_stats=cache_stats,
            normalized_lookup_index_stats=lookup_stats,
        )
        encoded = json.dumps(snapshot, allow_nan=False).encode("utf-8")
        self.assertLessEqual(
            len(encoded),
            result_delivery.MAX_DIAGNOSTIC_SNAPSHOT_BYTES,
        )
        restored = result_delivery.restore_diagnostic_snapshot(
            json.loads(encoded),
            interface_language="English",
            platform="unit-test-agent",
        )

        with mock.patch(
            "pattern_translator.engine.result_delivery.time.perf_counter",
            side_effect=[10.0, 10.25, 20.0, 20.25],
        ), mock.patch(
            "pattern_translator.engine.diagnostic_report.time.strftime",
            return_value="2026-08-28 22:00:00",
        ):
            in_process = result_delivery.build_deferred_diagnostic_report(
                copy.deepcopy(result),
                terminology_dataframe=pd.DataFrame(index=range(7)),
                csv_term_cache_stats=cache_stats,
                normalized_lookup_index_stats=lookup_stats,
                app_version="Pattern OCR Translator (Beta RC26)",
            )
            round_tripped = result_delivery.build_deferred_diagnostic_report(
                restored.result,
                terminology_row_count=restored.terminology_row_count,
                csv_term_cache_stats=restored.csv_term_cache_stats,
                normalized_lookup_index_stats=(
                    restored.normalized_lookup_index_stats
                ),
                app_version="Pattern OCR Translator (Beta RC26)",
            )

        self.assertEqual(in_process, round_tripped)
        self.assertIn("Area selected: Whole Pattern", round_tripped)
        self.assertIn("R1: 6X", round_tripped)
        self.assertIn("R1: 6 sc", round_tripped)
        self.assertIn("CSV rows loaded: 7", round_tripped)

    def test_large_diagnostic_snapshot_remains_bounded_and_restorable(self):
        line_df = pd.DataFrame(
            [
                {
                    "Original": f"R{index}: 6X",
                    "Translation": f"Round {index}: 6 sc",
                    "Confidence": 0.99,
                    "min_x": 1.0,
                    "max_x": 20.0,
                    "min_y": float(index),
                    "max_y": float(index + 10),
                }
                for index in range(500)
            ]
        )
        ocr_boxes = pd.DataFrame(
            [
                {
                    "text": f"R{index}: 6X",
                    "confidence": 0.99,
                    "min_x": 1.0,
                    "max_x": 20.0,
                    "min_y": float(index),
                    "max_y": float(index + 10),
                    "unused": "not needed by the report",
                }
                for index in range(500)
            ]
        )
        result = {
            "source_mode": "English — US",
            "output_mode": "Japanese",
            "area_mode": "Select Area",
            "crop_box": (10, 20, 110, 120),
            "quality_metrics": {"width_px": 200, "height_px": 160},
            "timings": {},
            "runtime_profile": {},
            "translation_profile": {},
            "readable_translation": "Round 1",
            "overlay_legend": "x" * 300_000,
            "raw_ocr_text": "y" * 300_000,
            "clean_text": "z" * 300_000,
            "unmatched": [],
            "line_df": line_df,
            "matches_df": pd.DataFrame(
                [{"Original detected": "X", "Category": "stitch", "US abb": "sc"}]
            ),
            "ocr_rows": ocr_boxes.copy(),
            "overlay_legend_df": pd.DataFrame(index=range(1)),
            "diagnostic_report_inputs": {
                "ocr_box_rows": ocr_boxes,
                "session_diagnostics": {"note": "n" * 100_000},
            },
        }

        snapshot = result_delivery.create_diagnostic_snapshot(
            result,
            terminology_row_count=12,
            csv_term_cache_stats={"hits": 1},
            normalized_lookup_index_stats={"enabled": "Yes"},
        )
        encoded = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
        restored = result_delivery.restore_diagnostic_snapshot(
            json.loads(encoded),
            interface_language="Japanese",
            platform="large-snapshot-test",
        )

        self.assertLessEqual(
            len(encoded),
            result_delivery.MAX_DIAGNOSTIC_SNAPSHOT_BYTES,
        )
        self.assertEqual("Select Area", restored.result["area_mode"])
        self.assertEqual((10, 20, 110, 120), restored.result["crop_box"])
        self.assertEqual(500, len(restored.result["line_df"]))
        self.assertEqual(500, len(restored.result["diagnostic_report_inputs"]["ocr_box_rows"]))
        self.assertEqual(1, len(restored.result["matches_df"]))
        self.assertEqual("Round 0: 6 sc", restored.result["line_df"].iloc[0]["Translation"])
        self.assertEqual(
            ["Original", "Translation"],
            list(restored.result["line_df"].columns),
        )
        self.assertNotIn(
            "unused",
            restored.result["diagnostic_report_inputs"]["ocr_box_rows"].columns,
        )
        self.assertEqual(12, restored.terminology_row_count)

    def test_app_stores_primary_result_before_optional_report_generation(self):
        app_source = (
            Path(__file__).resolve().parents[1] / "pattern_translator" / "app.py"
        ).read_text(encoding="utf-8")
        store_position = app_source.index(
            "result_delivery_engine.store_primary_result("
        )
        store_success_position = app_source.index(
            '"translation_result_store_success"', store_position
        )
        report_button_position = app_source.index(
            'key="prepare_debug_report_download"', store_success_position
        )
        report_begin_position = app_source.index(
            '"diagnostic_report_begin"', report_button_position
        )

        self.assertLess(store_position, store_success_position)
        self.assertLess(store_success_position, report_button_position)
        self.assertLess(report_button_position, report_begin_position)

    def test_diagnostic_report_uses_one_localized_action_slot(self):
        app_source = (
            Path(__file__).resolve().parents[1] / "pattern_translator" / "app.py"
        ).read_text(encoding="utf-8")
        diagnostic_start = app_source.index("diagnostic_download_slot = st.empty()")
        diagnostic_end = app_source.index(
            'st.markdown(f"<div class=\'report-action\'>', diagnostic_start
        )
        diagnostic_source = app_source[diagnostic_start:diagnostic_end]

        self.assertEqual(diagnostic_source.count('t("download_debug_report")'), 2)
        self.assertNotIn('t("generate_debug_report")', diagnostic_source)
        self.assertIn("if diagnostic_requested:", diagnostic_source)
        self.assertIn(
            "result_delivery_engine.generate_optional_diagnostic_report(",
            diagnostic_source,
        )
        self.assertIn("diagnostic_download_slot.download_button(", diagnostic_source)

    def test_app_publishes_before_any_post_export_streamlit_access(self):
        app_source = (
            Path(__file__).resolve().parents[1] / "pattern_translator" / "app.py"
        ).read_text(encoding="utf-8")
        service_source = (
            Path(__file__).resolve().parents[1]
            / "pattern_translator"
            / "translation_service.py"
        ).read_text(encoding="utf-8")
        export_position = service_source.index('"export_end"')
        export_to_return = service_source[export_position:service_source.index("return TranslateImageResult", export_position)]
        self.assertIsNone(re.search(r"\bst\.", export_to_return))
        self.assertNotIn("st.session_state", export_to_return)

        translate_position = app_source.index("translation_result = translate_image(")
        publish_position = app_source.index(
            "result_delivery_engine.publish_completed_result(", translate_position
        )
        post_translate_before_publish = app_source[translate_position:publish_position]
        self.assertIsNone(re.search(r"\bst\.", post_translate_before_publish))
        self.assertNotIn("st.session_state", post_translate_before_publish)
        self.assertNotIn("rc10b_log_event(", post_translate_before_publish)

    def test_producer_claims_in_same_run_without_forced_rerun(self):
        app_source = (
            Path(__file__).resolve().parents[1] / "pattern_translator" / "app.py"
        ).read_text(encoding="utf-8")
        translate_position = app_source.index("translation_result = translate_image(")
        publish_position = app_source.index(
            "result_delivery_engine.publish_completed_result(", translate_position
        )
        claim_position = app_source.index(
            "claim_and_commit_completed_result(", publish_position
        )
        exception_position = app_source.index("            except Exception", claim_position)

        self.assertLess(publish_position, claim_position)
        self.assertNotIn("st.rerun()", app_source[publish_position:exception_position])

    def test_lifecycle_completion_is_final_result_state_mutation(self):
        app_source = (
            Path(__file__).resolve().parents[1] / "pattern_translator" / "app.py"
        ).read_text(encoding="utf-8")
        callback_start = app_source.index("    def commit_completed_delivery(")
        callback_end = app_source.index(
            "\n\n    claimed_delivery, expired_handoff_count", callback_start
        )
        callback_source = app_source[callback_start:callback_end]
        lifecycle_position = callback_source.rindex(
            'st.session_state["ocr_request_lifecycle"]'
        )

        self.assertEqual(lifecycle_position, callback_source.rindex('st.session_state["'))

    def test_streamlit_151_queues_and_coalesces_reruns_on_active_runner(self):
        requests = ScriptRequests()

        self.assertTrue(requests.request_rerun(RerunData(query_string="first")))
        self.assertTrue(requests.request_rerun(RerunData(query_string="latest")))
        queued = requests.on_scriptrunner_yield()

        self.assertIsNotNone(queued)
        self.assertEqual(queued.type, ScriptRequestType.RERUN)
        self.assertEqual(queued.rerun_data.query_string, "latest")

    def test_app_claims_handoff_before_pending_request_consumption(self):
        app_source = (
            Path(__file__).resolve().parents[1] / "pattern_translator" / "app.py"
        ).read_text(encoding="utf-8")
        handoff_claim_position = app_source.index(
            "result_delivery_engine.claim_completed_result("
        )
        pending_claim_position = app_source.index(
            "ocr_request_lifecycle_engine.claim_request("
        )

        self.assertLess(handoff_claim_position, pending_claim_position)


if __name__ == "__main__":
    unittest.main()
