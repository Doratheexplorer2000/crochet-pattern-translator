import threading
import unittest
from pathlib import Path

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
        export_position = app_source.index('"export_end"')
        publish_position = app_source.index(
            "result_delivery_engine.publish_completed_result(", export_position
        )
        post_export_before_publish = app_source[export_position:publish_position]

        self.assertNotIn("st.", post_export_before_publish)
        self.assertNotIn("st.session_state", post_export_before_publish)
        self.assertNotIn("rc10b_log_event(", post_export_before_publish)

    def test_producer_claims_in_same_run_without_forced_rerun(self):
        app_source = (
            Path(__file__).resolve().parents[1] / "pattern_translator" / "app.py"
        ).read_text(encoding="utf-8")
        export_position = app_source.index('"export_end"')
        publish_position = app_source.index(
            "result_delivery_engine.publish_completed_result(", export_position
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
