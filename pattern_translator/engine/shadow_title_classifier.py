"""Shadow-only Luna title-route heading classifier.

Predictions are recorded for comparison against existing production rules.
They never change translation output, title routing, or overlay behavior.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, List, Mapping, Optional, Sequence, Set

from pattern_translator.engine import pattern_document

SHADOW_FLAG = "PATTERN_LUNA_TITLE_SHADOW_ENABLED"
SHADOW_LOG_PREFIX = "[pattern_shadow_title]"
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "low"
MAX_OUTPUT_TOKENS = 600
TIMEOUT_SECONDS = 8.0
_TRUE_VALUES = {"1", "true", "yes", "on"}

ClassifierCallable = Callable[[Sequence[str], str, float], "ShadowClassifierCallResult"]

_classifier_callable: Optional[ClassifierCallable] = None
_last_shadow_telemetry: Optional[dict] = None


@dataclass(frozen=True)
class ShadowClassifierCallResult:
    indices: Optional[List[int]]
    latency_seconds: float
    failure_category: Optional[str]


def is_shadow_classifier_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    values = os.environ if environ is None else environ
    return str(values.get(SHADOW_FLAG, "")).strip().lower() in _TRUE_VALUES


def get_last_shadow_telemetry() -> Optional[dict]:
    """Return the last safe metadata record for tests; never includes OCR text."""
    return _last_shadow_telemetry


def set_classifier_callable(callable_obj: Optional[ClassifierCallable]) -> None:
    global _classifier_callable
    _classifier_callable = callable_obj


def build_classifier_prompt(cleaned_lines: Sequence[str]) -> str:
    numbered = "\n".join(f"{index}: {line}" for index, line in enumerate(cleaned_lines))
    return (
        "TASK: Identify which OCR line indices are document titles or section/subsection "
        "headings that should be eligible for title translation.\n"
        "Do NOT translate. Do NOT explain. Return JSON only.\n\n"
        "Return exactly one JSON object with exactly one key:\n"
        '{"title_route_indices": [0, 1, 10]}\n\n'
        "Each index must refer to a line in the numbered list below. Indices are zero-based.\n\n"
        "INCLUDE only:\n"
        "- Document or pattern names at the top of the page\n"
        "- Generic section headings such as materials, gauge, notes, finishing, or assembly\n"
        "- Part or subsection headings naming a crochet component\n\n"
        "DO NOT include indices for:\n"
        "- Material values or specifications such as yarn weights, hook sizes, or wire gauges\n"
        "- Yarn colours or simple colour words\n"
        "- Crochet instructions, round or row lines, or assembly steps\n"
        "- Standalone verbs or courtesy phrases\n"
        "- Stitch notation, abbreviations, or legend lines\n"
        "- OCR noise, page numbers, watermarks, or chart debris\n\n"
        f"LINES:\n{numbered}"
    )


def validate_classifier_payload(payload: object, line_count: int) -> List[int]:
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON must be an object")
    if set(payload.keys()) != {"title_route_indices"}:
        raise ValueError("payload must contain exactly title_route_indices")
    indices = payload["title_route_indices"]
    if not isinstance(indices, list):
        raise ValueError("title_route_indices must be a list")
    validated: List[int] = []
    seen: Set[int] = set()
    for item in indices:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError("title_route_indices must contain integers only")
        if item < 0 or item >= line_count:
            raise ValueError(f"index out of range: {item}")
        if item in seen:
            raise ValueError(f"duplicate index: {item}")
        seen.add(item)
        validated.append(item)
    return validated


def _extract_output_text(payload: dict) -> str:
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                text = str(content.get("text", "")).strip()
                if text:
                    return text
    return ""


def _safe_failure_result(
    started: float,
    failure_category: str,
) -> ShadowClassifierCallResult:
    return ShadowClassifierCallResult(
        indices=None,
        latency_seconds=time.perf_counter() - started,
        failure_category=failure_category,
    )


def _default_classifier_call(
    cleaned_lines: Sequence[str],
    api_key: str,
    timeout_seconds: float,
) -> ShadowClassifierCallResult:
    started = time.perf_counter()
    prompt = build_classifier_prompt(cleaned_lines)
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps({
            "model": MODEL,
            "reasoning": {"effort": REASONING_EFFORT},
            "input": prompt,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            try:
                payload = json.load(response)
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                return _safe_failure_result(started, "response_decode_error")
    except TimeoutError:
        return _safe_failure_result(started, "timeout")
    except urllib.error.HTTPError as exc:
        category = "rate_limit" if exc.code == 429 else "provider_error"
        return _safe_failure_result(started, category)
    except urllib.error.URLError:
        return _safe_failure_result(started, "provider_error")
    except Exception:
        return _safe_failure_result(started, "provider_error")

    latency = time.perf_counter() - started
    try:
        raw_text = _extract_output_text(payload)
    except Exception:
        return ShadowClassifierCallResult(
            indices=None,
            latency_seconds=latency,
            failure_category="response_decode_error",
        )
    if not raw_text:
        return ShadowClassifierCallResult(
            indices=None,
            latency_seconds=latency,
            failure_category="empty_model_output",
        )
    try:
        parsed = json.loads(raw_text)
        validated = validate_classifier_payload(parsed, len(cleaned_lines))
    except (json.JSONDecodeError, ValueError, TypeError):
        return ShadowClassifierCallResult(
            indices=None,
            latency_seconds=latency,
            failure_category="parse_or_schema_error",
        )
    return ShadowClassifierCallResult(
        indices=validated,
        latency_seconds=latency,
        failure_category=None,
    )


def classify_title_route_shadow(
    cleaned_lines: Sequence[str],
    api_key: str,
    *,
    timeout_seconds: float = TIMEOUT_SECONDS,
) -> ShadowClassifierCallResult:
    try:
        if _classifier_callable is not None:
            return _classifier_callable(cleaned_lines, api_key, timeout_seconds)
        return _default_classifier_call(cleaned_lines, api_key, timeout_seconds)
    except Exception:
        return ShadowClassifierCallResult(
            indices=None,
            latency_seconds=0.0,
            failure_category="classifier_runtime_error",
        )


def compute_production_title_route_indices(cleaned_lines: Sequence[str]) -> List[int]:
    """Baseline production title-context indices from is_title_heading_context only."""
    indices: List[int] = []
    for position, cleaned in enumerate(cleaned_lines):
        nearby_lines = [
            cleaned_lines[nearby_position]
            for nearby_position in range(
                max(0, position - 2),
                min(len(cleaned_lines), position + 3),
            )
            if nearby_position != position
        ]
        if pattern_document.is_title_heading_context(cleaned, nearby_lines):
            indices.append(position)
    return indices


def build_safe_telemetry_record(
    *,
    event: str,
    line_count: int,
    call_result: ShadowClassifierCallResult,
    rule_indices: Optional[List[int]] = None,
    failure_category: Optional[str] = None,
) -> dict:
    duration = round(call_result.latency_seconds, 4)
    if failure_category is not None:
        return {
            "event": event,
            "outcome": "failure",
            "failure_category": failure_category,
            "duration": duration,
            "line_count": line_count,
        }

    luna_indices = call_result.indices or []
    rule_indices = rule_indices or []
    rule_set = set(rule_indices)
    luna_set = set(luna_indices)
    success = call_result.failure_category is None
    return {
        "event": event,
        "outcome": "success" if success else "failure",
        "failure_category": call_result.failure_category or "none",
        "duration": duration,
        "line_count": line_count,
        "predicted_heading_count": len(luna_indices),
        "rule_heading_count": len(rule_indices),
        "agreement_count": len(rule_set & luna_set),
        "luna_only_count": len(luna_set - rule_set),
        "rule_only_count": len(rule_set - luna_set),
    }


def emit_shadow_telemetry(record: dict) -> None:
    """Emit compact structured shadow telemetry; must never raise."""
    try:
        allowed_keys = (
            "event",
            "outcome",
            "failure_category",
            "duration",
            "line_count",
            "predicted_heading_count",
            "rule_heading_count",
            "agreement_count",
            "luna_only_count",
            "rule_only_count",
        )
        safe = {
            key: record[key]
            for key in allowed_keys
            if key in record
        }
        print(
            f"{SHADOW_LOG_PREFIX} {json.dumps(safe, separators=(',', ':'), sort_keys=True)}",
            file=sys.stderr,
            flush=True,
        )
    except Exception:
        pass


def _store_safe_telemetry(record: dict) -> None:
    global _last_shadow_telemetry
    _last_shadow_telemetry = dict(record)


def record_shadow_comparison_if_enabled(
    *,
    cleaned_lines: Sequence[str],
    environ: Optional[Mapping[str, str]] = None,
) -> None:
    """Run shadow classifier when enabled. Never raises; never affects translation."""
    global _last_shadow_telemetry
    if not cleaned_lines or not is_shadow_classifier_enabled(environ):
        _last_shadow_telemetry = None
        return

    line_count = len(cleaned_lines)
    started = time.perf_counter()
    values = os.environ if environ is None else environ
    api_key = str(values.get("OPENAI_API_KEY", "")).strip()

    try:
        if not api_key:
            call_result = ShadowClassifierCallResult(
                indices=None,
                latency_seconds=time.perf_counter() - started,
                failure_category="missing_api_key",
            )
        else:
            call_result = classify_title_route_shadow(cleaned_lines, api_key)

        try:
            rule_indices = compute_production_title_route_indices(cleaned_lines)
        except Exception:
            failure_record = build_safe_telemetry_record(
                event="shadow_title_classifier_end",
                line_count=line_count,
                call_result=ShadowClassifierCallResult(
                    indices=None,
                    latency_seconds=call_result.latency_seconds,
                    failure_category=call_result.failure_category,
                ),
                failure_category="comparison_error",
            )
            _store_safe_telemetry(failure_record)
            emit_shadow_telemetry(failure_record)
            return

        if call_result.failure_category is not None:
            failure_record = build_safe_telemetry_record(
                event="shadow_title_classifier_end",
                line_count=line_count,
                call_result=call_result,
                failure_category=call_result.failure_category,
            )
            _store_safe_telemetry(failure_record)
            emit_shadow_telemetry(failure_record)
            return

        success_record = build_safe_telemetry_record(
            event="shadow_title_classifier_end",
            line_count=line_count,
            call_result=call_result,
            rule_indices=rule_indices,
        )
        _store_safe_telemetry(success_record)
        emit_shadow_telemetry(success_record)
    except Exception:
        failure_record = build_safe_telemetry_record(
            event="shadow_title_classifier_end",
            line_count=line_count,
            call_result=ShadowClassifierCallResult(
                indices=None,
                latency_seconds=time.perf_counter() - started,
                failure_category=None,
            ),
            failure_category="shadow_internal_error",
        )
        _store_safe_telemetry(failure_record)
        try:
            emit_shadow_telemetry(failure_record)
        except Exception:
            pass
