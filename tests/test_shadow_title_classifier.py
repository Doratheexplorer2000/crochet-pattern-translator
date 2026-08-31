import io
import json
import os
import sys
import unittest
from unittest import mock

import pandas as pd

from pattern_translator.engine import (
    line_translation,
    llm_fallback,
    ocr_lines,
    shadow_title_classifier,
    terminology,
)


class ShadowClassifierValidationTests(unittest.TestCase):
    def test_validate_accepts_unique_in_range_indices(self):
        payload = {"title_route_indices": [0, 2, 5]}
        self.assertEqual(shadow_title_classifier.validate_classifier_payload(payload, 6), [0, 2, 5])

    def test_validate_rejects_unknown_key(self):
        with self.assertRaises(ValueError):
            shadow_title_classifier.validate_classifier_payload(
                {"title_route_indices": [0], "extra": 1},
                2,
            )

    def test_validate_rejects_missing_key(self):
        with self.assertRaises(ValueError):
            shadow_title_classifier.validate_classifier_payload({}, 2)

    def test_validate_rejects_duplicate_index(self):
        with self.assertRaises(ValueError):
            shadow_title_classifier.validate_classifier_payload(
                {"title_route_indices": [0, 0]},
                2,
            )

    def test_validate_rejects_out_of_range_index(self):
        with self.assertRaises(ValueError):
            shadow_title_classifier.validate_classifier_payload(
                {"title_route_indices": [2]},
                2,
            )

    def test_validate_rejects_non_integer_index(self):
        with self.assertRaises(ValueError):
            shadow_title_classifier.validate_classifier_payload(
                {"title_route_indices": ["0"]},
                2,
            )


class ShadowClassifierIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv("knowledge_base/data/master_stitches.csv")
        cls.english_index = terminology.build_term_index(cls.df, "English — US")
        cls.output_mode = "Traditional Chinese"
        cls.pattern_nearby = "Rnd 1: 3 ch + 1 dc together"

    def setUp(self):
        shadow_title_classifier.set_classifier_callable(None)
        shadow_title_classifier._last_shadow_telemetry = None

    def tearDown(self):
        shadow_title_classifier.set_classifier_callable(None)
        shadow_title_classifier._last_shadow_telemetry = None

    def ocr_rows(self, lines):
        return pd.DataFrame([
            {
                "text": line,
                "confidence": 0.99,
                "min_x": 0,
                "max_x": 220,
                "min_y": index * 30,
                "max_y": index * 30 + 20,
            }
            for index, line in enumerate(lines)
        ])

    def run_pipeline(self, lines, provider=None, *, environ=None):
        rows = self.ocr_rows(lines)
        env = {"PATTERN_LLM_FALLBACK_ENABLED": "1", "OPENAI_API_KEY": "test-key"}
        if environ:
            env.update(environ)
        with mock.patch.dict(os.environ, env, clear=False):
            return ocr_lines.build_ocr_line_translations(
                rows,
                self.english_index,
                self.df,
                self.output_mode,
                llm_provider=provider,
            )

    def capture_shadow_log(self):
        buffer = io.StringIO()
        return buffer, mock.patch("sys.stderr", buffer)

    def test_flag_off_makes_zero_classifier_calls(self):
        calls = []

        def fake_classifier(lines, _api_key, _timeout):
            calls.append(list(lines))
            return shadow_title_classifier.ShadowClassifierCallResult(
                indices=[0],
                latency_seconds=0.01,
                failure_category=None,
            )

        shadow_title_classifier.set_classifier_callable(fake_classifier)
        provider = mock.Mock(return_value="wrong")
        self.run_pipeline(["PETALS", self.pattern_nearby], provider)
        self.assertEqual(calls, [])

    def test_flag_off_uses_baseline_should_use_llm_routing(self):
        source = "Body (brown yarn)"
        lines = [source, self.pattern_nearby]
        provider = mock.Mock(return_value="身體 (棕色毛線)")
        original_should_use_llm = llm_fallback.should_use_llm

        def capture_calls(storage):
            def side_effect(*args, **kwargs):
                result = original_should_use_llm(*args, **kwargs)
                storage.append((args, result))
                return result
            return side_effect

        baseline_calls = []
        with mock.patch.object(
            llm_fallback,
            "should_use_llm",
            side_effect=capture_calls(baseline_calls),
        ):
            self.run_pipeline(lines, provider)

        shadow_calls = []
        shadow_title_classifier.set_classifier_callable(
            lambda *_args: shadow_title_classifier.ShadowClassifierCallResult(
                indices=[1],
                latency_seconds=0.01,
                failure_category=None,
            )
        )
        with mock.patch.object(
            llm_fallback,
            "should_use_llm",
            side_effect=capture_calls(shadow_calls),
        ):
            self.run_pipeline(
                lines,
                provider,
                environ={"PATTERN_LUNA_TITLE_SHADOW_ENABLED": "1"},
            )

        self.assertEqual(baseline_calls, shadow_calls)

    def test_flag_on_makes_exactly_one_classifier_call_per_scope(self):
        calls = []

        def fake_classifier(lines, _api_key, _timeout):
            calls.append(list(lines))
            return shadow_title_classifier.ShadowClassifierCallResult(
                indices=[0],
                latency_seconds=0.02,
                failure_category=None,
            )

        shadow_title_classifier.set_classifier_callable(fake_classifier)
        self.run_pipeline(
            ["PETALS", self.pattern_nearby],
            mock.Mock(return_value="wrong"),
            environ={"PATTERN_LUNA_TITLE_SHADOW_ENABLED": "1"},
        )
        self.assertEqual(len(calls), 1)

    def test_shadow_success_output_unchanged(self):
        lines = ["Body (brown yarn)", self.pattern_nearby]
        provider = mock.Mock(return_value="身體 (棕色毛線)")

        with mock.patch.dict(
            os.environ,
            {"PATTERN_LLM_FALLBACK_ENABLED": "1", "OPENAI_API_KEY": "test-key"},
            clear=False,
        ):
            baseline = self.run_pipeline(lines, provider)

        shadow_title_classifier.set_classifier_callable(
            lambda *_args: shadow_title_classifier.ShadowClassifierCallResult(
                indices=[1],
                latency_seconds=0.01,
                failure_category=None,
            )
        )
        with mock.patch.dict(
            os.environ,
            {
                "PATTERN_LLM_FALLBACK_ENABLED": "1",
                "OPENAI_API_KEY": "test-key",
                "PATTERN_LUNA_TITLE_SHADOW_ENABLED": "1",
            },
            clear=False,
        ):
            shadow = self.run_pipeline(lines, provider)

        self.assertEqual(
            baseline["Translation"].tolist(),
            shadow["Translation"].tolist(),
        )

    def test_unexpected_classifier_runtime_error_output_unchanged(self):
        lines = ["Body (brown yarn)", self.pattern_nearby]
        expected = self.run_pipeline(lines, None)

        def explode(*_args):
            raise RuntimeError("classifier exploded")

        shadow_title_classifier.set_classifier_callable(explode)
        result = self.run_pipeline(
            lines,
            None,
            environ={"PATTERN_LUNA_TITLE_SHADOW_ENABLED": "1"},
        )
        self.assertEqual(result["Translation"].tolist(), expected["Translation"].tolist())
        telemetry = shadow_title_classifier.get_last_shadow_telemetry()
        self.assertEqual(telemetry["outcome"], "failure")
        self.assertEqual(telemetry["failure_category"], "classifier_runtime_error")

    def test_response_decode_error_output_unchanged(self):
        lines = ["PETALS", self.pattern_nearby]
        expected = self.run_pipeline(lines, None)

        response = mock.Mock()
        response.__enter__ = mock.Mock(return_value=response)
        response.__exit__ = mock.Mock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=response):
            with mock.patch(
                "pattern_translator.engine.shadow_title_classifier.json.load",
                side_effect=json.JSONDecodeError("bad", "doc", 0),
            ):
                result = self.run_pipeline(
                    lines,
                    None,
                    environ={"PATTERN_LUNA_TITLE_SHADOW_ENABLED": "1", "OPENAI_API_KEY": "k"},
                )
        self.assertEqual(result["Translation"].tolist(), expected["Translation"].tolist())
        self.assertEqual(
            shadow_title_classifier.get_last_shadow_telemetry()["failure_category"],
            "response_decode_error",
        )

    def test_comparison_exception_output_unchanged(self):
        lines = ["PETALS", self.pattern_nearby]
        expected = self.run_pipeline(lines, None)
        shadow_title_classifier.set_classifier_callable(
            lambda *_args: shadow_title_classifier.ShadowClassifierCallResult(
                indices=[0],
                latency_seconds=0.01,
                failure_category=None,
            )
        )
        with mock.patch.object(
            shadow_title_classifier,
            "compute_production_title_route_indices",
            side_effect=RuntimeError("comparison failed"),
        ):
            result = self.run_pipeline(
                lines,
                None,
                environ={"PATTERN_LUNA_TITLE_SHADOW_ENABLED": "1"},
            )
        self.assertEqual(result["Translation"].tolist(), expected["Translation"].tolist())
        self.assertEqual(
            shadow_title_classifier.get_last_shadow_telemetry()["failure_category"],
            "comparison_error",
        )

    def test_telemetry_logger_exception_output_unchanged(self):
        lines = ["PETALS", self.pattern_nearby]
        expected = self.run_pipeline(lines, None)
        shadow_title_classifier.set_classifier_callable(
            lambda *_args: shadow_title_classifier.ShadowClassifierCallResult(
                indices=[0],
                latency_seconds=0.01,
                failure_category=None,
            )
        )
        with mock.patch.object(
            shadow_title_classifier,
            "emit_shadow_telemetry",
            side_effect=RuntimeError("log failed"),
        ):
            result = self.run_pipeline(
                lines,
                None,
                environ={"PATTERN_LUNA_TITLE_SHADOW_ENABLED": "1"},
            )
        self.assertEqual(result["Translation"].tolist(), expected["Translation"].tolist())

    def test_timeout_missing_key_and_payload_failures_output_unchanged(self):
        lines = ["PETALS", self.pattern_nearby]
        baseline = self.run_pipeline(lines, None)

        cases = (
            (
                "timeout",
                lambda *_args: shadow_title_classifier.ShadowClassifierCallResult(
                    indices=None, latency_seconds=8.0, failure_category="timeout"
                ),
            ),
            ("missing_api_key", None),
            (
                "parse_or_schema_error",
                lambda *_args: shadow_title_classifier.ShadowClassifierCallResult(
                    indices=None, latency_seconds=0.03, failure_category="parse_or_schema_error"
                ),
            ),
        )
        for category, classifier in cases:
            with self.subTest(category=category):
                if classifier is not None:
                    shadow_title_classifier.set_classifier_callable(classifier)
                env = {"PATTERN_LUNA_TITLE_SHADOW_ENABLED": "1"}
                if category != "missing_api_key":
                    env["OPENAI_API_KEY"] = "test-key"
                else:
                    env["OPENAI_API_KEY"] = ""
                result = self.run_pipeline(lines, None, environ=env)
                self.assertEqual(
                    result["Translation"].tolist(),
                    baseline["Translation"].tolist(),
                )
                self.assertEqual(
                    shadow_title_classifier.get_last_shadow_telemetry()["failure_category"],
                    category,
                )

    def test_classifier_has_zero_retries(self):
        attempts = []

        def counting_classifier(_lines, _api_key, _timeout):
            attempts.append(1)
            return shadow_title_classifier.ShadowClassifierCallResult(
                indices=[0],
                latency_seconds=0.01,
                failure_category=None,
            )

        shadow_title_classifier.set_classifier_callable(counting_classifier)
        self.run_pipeline(
            ["PETALS", self.pattern_nearby],
            None,
            environ={"PATTERN_LUNA_TITLE_SHADOW_ENABLED": "1"},
        )
        self.assertEqual(len(attempts), 1)

    def test_success_telemetry_is_emitted(self):
        shadow_title_classifier.set_classifier_callable(
            lambda *_args: shadow_title_classifier.ShadowClassifierCallResult(
                indices=[0],
                latency_seconds=0.04,
                failure_category=None,
            )
        )
        buffer, stderr_patch = self.capture_shadow_log()
        with stderr_patch:
            self.run_pipeline(
                ["PETALS", self.pattern_nearby],
                None,
                environ={"PATTERN_LUNA_TITLE_SHADOW_ENABLED": "1"},
            )
        output = buffer.getvalue()
        self.assertIn(shadow_title_classifier.SHADOW_LOG_PREFIX, output)
        payload = json.loads(output.split(shadow_title_classifier.SHADOW_LOG_PREFIX, 1)[1].strip())
        self.assertEqual(payload["event"], "shadow_title_classifier_end")
        self.assertEqual(payload["outcome"], "success")
        self.assertIn("predicted_heading_count", payload)
        self.assertIn("rule_heading_count", payload)

    def test_failure_telemetry_is_emitted(self):
        buffer, stderr_patch = self.capture_shadow_log()
        with stderr_patch:
            self.run_pipeline(
                ["PETALS", self.pattern_nearby],
                None,
                environ={
                    "PATTERN_LUNA_TITLE_SHADOW_ENABLED": "1",
                    "OPENAI_API_KEY": "",
                },
            )
        payload = json.loads(buffer.getvalue().split(shadow_title_classifier.SHADOW_LOG_PREFIX, 1)[1].strip())
        self.assertEqual(payload["outcome"], "failure")
        self.assertEqual(payload["failure_category"], "missing_api_key")

    def test_telemetry_contains_no_ocr_text_or_secrets(self):
        secret = "sk-live-shadow-secret"
        shadow_title_classifier.set_classifier_callable(
            lambda *_args: shadow_title_classifier.ShadowClassifierCallResult(
                indices=[0],
                latency_seconds=0.01,
                failure_category=None,
            )
        )
        buffer, stderr_patch = self.capture_shadow_log()
        with stderr_patch:
            self.run_pipeline(
                ["SecretHeading", self.pattern_nearby],
                None,
                environ={
                    "PATTERN_LUNA_TITLE_SHADOW_ENABLED": "1",
                    "OPENAI_API_KEY": secret,
                },
            )
        combined = buffer.getvalue() + json.dumps(shadow_title_classifier.get_last_shadow_telemetry())
        self.assertNotIn("SecretHeading", combined)
        self.assertNotIn(secret, combined)
        self.assertNotIn("cleaned_lines", combined)

    def test_no_process_global_ocr_text_retention(self):
        shadow_title_classifier.set_classifier_callable(
            lambda *_args: shadow_title_classifier.ShadowClassifierCallResult(
                indices=[0],
                latency_seconds=0.01,
                failure_category=None,
            )
        )
        with mock.patch.dict(
            os.environ,
            {
                "PATTERN_LUNA_TITLE_SHADOW_ENABLED": "1",
                "OPENAI_API_KEY": "test-key",
                "PATTERN_LLM_DEBUG": "1",
            },
            clear=False,
        ):
            self.run_pipeline(["RetainMe", self.pattern_nearby], None)
        telemetry = shadow_title_classifier.get_last_shadow_telemetry()
        self.assertNotIn("RetainMe", json.dumps(telemetry))
        self.assertNotIn("cleaned_lines", telemetry)


class ShadowClassifierApiFailureTests(unittest.TestCase):
    def test_malformed_json_from_provider_is_rejected(self):
        response = mock.Mock()
        response.__enter__ = mock.Mock(return_value=response)
        response.__exit__ = mock.Mock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=response):
            with mock.patch(
                "pattern_translator.engine.shadow_title_classifier.json.load",
                side_effect=json.JSONDecodeError("bad", "doc", 0),
            ):
                result = shadow_title_classifier.classify_title_route_shadow(
                    ["PETALS", "Rnd 1: 6 sc"],
                    "test-key",
                )
        self.assertIsNone(result.indices)
        self.assertEqual(result.failure_category, "response_decode_error")

    def test_duplicate_index_from_provider_is_rejected(self):
        payload = {
            "output": [{
                "content": [{
                    "type": "output_text",
                    "text": json.dumps({"title_route_indices": [0, 0]}),
                }],
            }],
        }
        response = mock.Mock()
        response.__enter__ = mock.Mock(return_value=response)
        response.__exit__ = mock.Mock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=response):
            with mock.patch("json.load", return_value=payload):
                result = shadow_title_classifier.classify_title_route_shadow(
                    ["PETALS", "Rnd 1: 6 sc"],
                    "test-key",
                )
        self.assertIsNone(result.indices)
        self.assertEqual(result.failure_category, "parse_or_schema_error")


class ShadowClassifierPromptTests(unittest.TestCase):
    def test_prompt_is_narrow_and_unbiased(self):
        prompt = shadow_title_classifier.build_classifier_prompt(["Alpha", "Rnd 1: 6 sc"])
        self.assertIn("title_route_indices", prompt)
        self.assertIn("0: Alpha", prompt)
        self.assertNotIn("Carnation", prompt)
        self.assertNotIn("MATERIALS", prompt)


if __name__ == "__main__":
    unittest.main()
