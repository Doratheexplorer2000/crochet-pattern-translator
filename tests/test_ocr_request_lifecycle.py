import unittest

from pattern_translator.engine import ocr_request_lifecycle


class RequestHarness:
    def __init__(self):
        self.request = None
        self.ocr_calls = []

    def accept(self, request_id, workflow_mode="Whole Pattern", image_id="image-a"):
        self.request = {
            **ocr_request_lifecycle.new_request(request_id),
            "workflow_mode": workflow_mode,
            "image_id": image_id,
        }

    def consume(self, *, succeeds=True):
        request_id = self.request["request_id"] if self.request else "missing"
        self.request, claimed = ocr_request_lifecycle.claim_request(
            self.request, request_id
        )
        if not claimed:
            return False
        self.ocr_calls.append(
            (
                request_id,
                self.request["workflow_mode"],
                self.request["image_id"],
            )
        )
        self.request = ocr_request_lifecycle.finish_request(
            self.request, request_id, succeeded=succeeds
        )
        return True


class OCRRequestLifecycleTests(unittest.TestCase):
    def test_one_request_can_be_claimed_only_once_while_running(self):
        request = ocr_request_lifecycle.new_request("request-a")
        request, first_claim = ocr_request_lifecycle.claim_request(
            request, "request-a"
        )
        request, rerun_claim = ocr_request_lifecycle.claim_request(
            request, "request-a"
        )

        self.assertTrue(first_claim)
        self.assertFalse(rerun_claim)
        self.assertEqual(request["state"], ocr_request_lifecycle.RUNNING)

    def test_completed_request_cannot_be_replayed(self):
        harness = RequestHarness()
        harness.accept("request-a")

        self.assertTrue(harness.consume())
        self.assertFalse(harness.consume())
        self.assertEqual(len(harness.ocr_calls), 1)
        self.assertEqual(
            harness.request["state"], ocr_request_lifecycle.COMPLETED
        )

    def test_failed_request_cannot_replay_indefinitely(self):
        harness = RequestHarness()
        harness.accept("request-a")

        self.assertTrue(harness.consume(succeeds=False))
        self.assertFalse(harness.consume(succeeds=False))
        self.assertEqual(len(harness.ocr_calls), 1)
        self.assertEqual(harness.request["state"], ocr_request_lifecycle.FAILED)

    def test_new_request_id_runs_after_terminal_request(self):
        harness = RequestHarness()
        harness.accept("request-a")
        self.assertTrue(harness.consume())

        harness.accept("request-b")
        self.assertTrue(harness.consume())

        self.assertEqual(
            [call[0] for call in harness.ocr_calls], ["request-a", "request-b"]
        )

    def test_replace_or_remove_then_new_image_runs_once(self):
        harness = RequestHarness()
        harness.accept("request-a", image_id="image-a")
        self.assertTrue(harness.consume())

        harness.accept("request-b", image_id="image-b")
        self.assertTrue(harness.consume())
        self.assertFalse(harness.consume())

        self.assertEqual(
            [call[2] for call in harness.ocr_calls], ["image-a", "image-b"]
        )

    def test_whole_pattern_and_select_area_each_run_once(self):
        for workflow_mode in ("Whole Pattern", "Select Area"):
            with self.subTest(workflow_mode=workflow_mode):
                harness = RequestHarness()
                harness.accept("request-a", workflow_mode=workflow_mode)
                self.assertTrue(harness.consume())
                self.assertFalse(harness.consume())
                self.assertEqual(
                    harness.ocr_calls,
                    [("request-a", workflow_mode, "image-a")],
                )

    def test_mismatched_request_id_cannot_claim_pending_request(self):
        request = ocr_request_lifecycle.new_request("request-a")
        request, claimed = ocr_request_lifecycle.claim_request(
            request, "request-b"
        )

        self.assertFalse(claimed)
        self.assertEqual(request["state"], ocr_request_lifecycle.PENDING)


if __name__ == "__main__":
    unittest.main()
