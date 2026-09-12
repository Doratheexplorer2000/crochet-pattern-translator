"""Broad Luna translation for validated crochet pattern language routes."""

from __future__ import annotations

import csv
import http.client
import json
import os
import re
import socket
import ssl
import time
import urllib.error
import urllib.request
from collections import Counter
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from pattern_translator.engine import terminology

DiagnosticLogger = Callable[..., None]
ProfileCount = Callable[[str, float], None]
ProfileAddTime = Callable[[str, float], None]

_REPO_ROOT = Path(__file__).resolve().parents[2]
GLOSSARY_PATH = _REPO_ROOT / "knowledge_base" / "data" / "master_stitches.csv"

BROAD_MODEL = "gpt-5.6-luna"
BROAD_REASONING = "low"
BROAD_MAX_OUTPUT_TOKENS = 6000
BROAD_TIMEOUT_SECONDS = 90.0
BROAD_MIN_RETRY_BUDGET_SECONDS = 1.0
BROAD_FAST_TRANSIENT_SECONDS = 10.0
BROAD_FLAG_ENV = "PATTERN_BROAD_TRANSLATION_ENABLED"
BROAD_DEBUG_CAPTURE_ENV = "PATTERN_BROAD_DEBUG_CAPTURE"
VALIDATION_DIAGNOSTIC_EXCERPT_CHARS = 400
REQUEST_WARNING_ATTR = "request_warning"
BROAD_DEBUG_CAPTURE_ATTR = "broad_raw_candidate_debug"

EN_US_SOURCE = "English — US"
TRADITIONAL_CHINESE_TARGET = "Traditional Chinese"
TRADITIONAL_CHINESE_SOURCE = TRADITIONAL_CHINESE_TARGET
SIMPLIFIED_CHINESE_SOURCE = "Simplified Chinese"
EN_US_TARGET = "English — US"
EN_UK_TARGET = "English — UK"
EN_UK_SOURCE = EN_UK_TARGET
SIMPLIFIED_CHINESE_TARGET = SIMPLIFIED_CHINESE_SOURCE
JAPANESE_TARGET = "Japanese"
JAPANESE_SOURCE = JAPANESE_TARGET

_REQUEST_WARNING_BY_TARGET = {
    TRADITIONAL_CHINESE_TARGET: "⚠ 自動翻譯未能可靠完成；部分內容可能保留原文。",
    SIMPLIFIED_CHINESE_TARGET: "⚠ 自动翻译未能可靠完成；部分内容可能保留原文。",
    EN_US_TARGET: (
        "⚠ Automatic translation could not be completed reliably; "
        "some original text may remain."
    ),
    EN_UK_TARGET: (
        "⚠ Automatic translation could not be completed reliably; "
        "some original text may remain."
    ),
    "Japanese": "⚠ 自動翻訳を確実に完了できなかったため、一部に原文が残る場合があります。",
}

_BROAD_CALL_TIMEOUT_SECONDS: ContextVar[float] = ContextVar(
    "broad_call_timeout_seconds",
    default=BROAD_TIMEOUT_SECONDS,
)

_TRUE_VALUES = {"1", "true", "yes", "on"}
KEYED_RESPONSE_SHAPE = "object_with_segment_assignments_and_semantic_units_objects"

DOMAIN_CRITICAL_PATTERN_INSTRUCTION_IDS = frozenset(
    {
        "st_034_yarn_over",
        "st_035_yarn_over_hook",
        "st_036_round",
        "st_093_rounds",
        "st_094_row",
        "st_095_rows",
        "st_037_skip",
        "st_038_turn",
        "st_039_back_bumps",
        "st_042_leave_a_long_tail",
        "st_045_repeat",
        "st_076_marker",
        "st_077_main_color",
        "st_078_pattern",
        "st_079_place_marker",
        "st_082_right_side",
        "st_085_space",
        "st_086_stitch",
        "st_088_together",
        "st_089_wrong_side",
        "st_090_start_in_stitch",
        "st_091_fasten_off",
        "st_096_around",
        "st_098_change_ color",
        "st_099_change_yarn",
        "st_100_join_with_sl_st",
        "st_101_work_even",
        "st_102_attach",
        "st_103_sew",
        "st_104_hook",
        "st_106_leave_yarn",
        "st_108_close_opening",
    }
)
HANDLE_RE = re.compile(r"(?<![A-Za-z0-9_])@[A-Za-z0-9_.-]+")


class BroadTranslationError(RuntimeError):
    """Controlled broad-translation failure without provider or OCR details."""


class BroadRecoverableError(BroadTranslationError):
    """Typed terminal translation-layer failure safe for deterministic fallback."""

    def __init__(
        self,
        reason: str,
        failure_classification: str,
        *,
        attempt_count: int,
    ) -> None:
        super().__init__()
        self.reason = reason
        self.failure_classification = failure_classification
        self.attempt_count = attempt_count
        self.retry_attempted = attempt_count > 1


class _UnitIntegrityError(BroadTranslationError):
    """One mapped semantic unit failed an objectively provable integrity rule."""

    def __init__(self, failed_rule: str, diagnostic_fields: Mapping[str, object]) -> None:
        super().__init__()
        self.failed_rule = failed_rule
        self.diagnostic_fields = dict(diagnostic_fields)


class _BroadResponseParsingError(BroadTranslationError):
    """Internal response-shape failure carrying only safe structural metadata."""

    def __init__(
        self,
        stage: str,
        reason: str,
        *,
        exception_type: str = "_BroadResponseParsingError",
        expected_top_level_shape: str = "",
        actual_top_level_json_type: str = "",
        semantic_unit_count: Optional[int] = None,
    ) -> None:
        super().__init__()
        self.stage = stage
        self.reason = reason
        self.exception_type = exception_type
        self.expected_top_level_shape = expected_top_level_shape
        self.actual_top_level_json_type = actual_top_level_json_type
        self.semantic_unit_count = semantic_unit_count


class _DuplicateJsonObjectKeyError(ValueError):
    """Internal signal that JSON object ownership was not actually unique."""


@dataclass(frozen=True)
class _RouteConfig:
    source_mode: str
    output_mode: str
    source_language: str
    target_language: str
    en_us_source: bool


_LANGUAGE_LABELS = {
    EN_US_SOURCE: "English US",
    EN_UK_SOURCE: "English UK",
    TRADITIONAL_CHINESE_SOURCE: "Traditional Chinese",
    SIMPLIFIED_CHINESE_SOURCE: "Simplified Chinese",
    JAPANESE_SOURCE: "Japanese",
}

_ROUTE_CONFIGS: Dict[Tuple[str, str], _RouteConfig] = {
    (source_mode, output_mode): _RouteConfig(
        source_mode,
        output_mode,
        source_language,
        target_language,
        source_mode == EN_US_SOURCE,
    )
    for source_mode, source_language in _LANGUAGE_LABELS.items()
    for output_mode, target_language in _LANGUAGE_LABELS.items()
    if source_mode != output_mode
}


def is_broad_translation_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    values = os.environ if environ is None else environ
    return str(values.get(BROAD_FLAG_ENV, "")).strip().lower() in _TRUE_VALUES


def is_broad_debug_capture_enabled(
    environ: Optional[Mapping[str, str]] = None,
) -> bool:
    values = os.environ if environ is None else environ
    return str(values.get(BROAD_DEBUG_CAPTURE_ENV, "")).strip().lower() in _TRUE_VALUES


def is_broad_translation_route(source_mode: str, output_mode: str) -> bool:
    return (source_mode, output_mode) in _ROUTE_CONFIGS


def _route_config(source_mode: str, output_mode: str) -> _RouteConfig:
    config = _ROUTE_CONFIGS.get((source_mode, output_mode))
    if config is None:
        raise BroadTranslationError()
    return config


def _us_aliases(row: dict[str, str]) -> List[str]:
    values = [row.get("US_term", ""), row.get("US_abb", ""), row.get("US_abb1", "")]
    values.extend(row.get("US_term_alias", "").split("|"))
    return [value.strip() for value in values if value.strip()]


def _uk_aliases(row: dict[str, str]) -> List[str]:
    values = [row.get("UK_term", ""), row.get("UK_abb", ""), row.get("UK_abb1", "")]
    uk_term_aliases = row.get("UK_term_alias", "").split("|")
    values.extend(uk_term_aliases)
    if not any(
        str(value).strip()
        for value in (row.get("UK_term", ""), *uk_term_aliases)
    ):
        # A missing UK field means the concept has no dialect-specific rename.
        # At present this applies only to magic ring; retain its shared long form.
        values.extend((row.get("US_term", ""), row.get("US_term_alias", "")))
    return [value.strip() for value in values if value.strip()]


def _chinese_forms(row: dict[str, str]) -> List[str]:
    values = [str(row.get("Chinese_term", "")).strip()]
    values.extend(row.get("Chinese_term_alias", "").split("|"))
    abb = str(row.get("Chinese_abb", "")).strip()
    if abb:
        values.append(abb)
    return [value for value in values if value]


def _simplified_forms(row: dict[str, str]) -> List[str]:
    return list(
        dict.fromkeys(
            terminology.to_simplified(value)
            for value in _chinese_forms(row)
        )
    )


def _japanese_forms(row: dict[str, str]) -> List[str]:
    values = [str(row.get("Japanese", "")).strip()]
    values.extend(str(row.get("Japanese_alias", "")).split("|"))
    return [value.strip() for value in values if value.strip()]


def _load_glossary_rows() -> List[dict[str, str]]:
    with GLOSSARY_PATH.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_glossary(source_mode: str, output_mode: str) -> List[Dict[str, Any]]:
    """Build one consolidated glossary for the approved Broad route."""
    config = _route_config(source_mode, output_mode)
    grouped: Dict[str, List[dict[str, str]]] = {}
    stitch_ids: Dict[str, str] = {}
    categories: Dict[str, str] = {}

    for row in _load_glossary_rows():
        if row.get("search_status", "").strip().lower() != "active":
            continue
        chinese = str(row.get("Chinese_term", "")).strip()
        if not chinese:
            continue
        category = row.get("category", "").strip()
        stitch_id = row.get("stitch_id", "").strip()
        if category == "pattern_instruction" and stitch_id not in DOMAIN_CRITICAL_PATTERN_INSTRUCTION_IDS:
            continue
        us_aliases = _us_aliases(row)
        if not us_aliases:
            continue
        concept_key = row.get("equivalence_group", "").strip() or stitch_id
        grouped.setdefault(concept_key, []).append(row)
        stitch_ids.setdefault(concept_key, stitch_id)
        categories.setdefault(concept_key, category)

    if not grouped:
        raise BroadTranslationError()

    terms: List[Dict[str, Any]] = []
    for concept_key, rows in grouped.items():
        english_aliases: List[str] = []
        english_abbreviations: List[str] = []
        english_uk_aliases: List[str] = []
        english_uk_abbreviations: List[str] = []
        traditional_terms: List[str] = []
        simplified_terms: List[str] = []
        traditional_abbreviations: List[str] = []
        simplified_abbreviations: List[str] = []
        japanese_terms: List[str] = []

        for row in rows:
            for alias in _us_aliases(row):
                if alias not in english_aliases:
                    english_aliases.append(alias)
            for abb in (row.get("US_abb", ""), row.get("US_abb1", "")):
                value = str(abb).strip()
                if value and value.lower() != "st" and value not in english_abbreviations:
                    english_abbreviations.append(value)
            for alias in _uk_aliases(row):
                if alias not in english_uk_aliases:
                    english_uk_aliases.append(alias)
            for abb in (row.get("UK_abb", ""), row.get("UK_abb1", "")):
                value = str(abb).strip()
                if value and value.lower() != "st" and value not in english_uk_abbreviations:
                    english_uk_abbreviations.append(value)
            for value in _chinese_forms(row):
                if value not in traditional_terms:
                    traditional_terms.append(value)
            for value in _simplified_forms(row):
                if value not in simplified_terms:
                    simplified_terms.append(value)
            chinese_abb = str(row.get("Chinese_abb", "")).strip()
            if chinese_abb:
                if chinese_abb not in traditional_abbreviations:
                    traditional_abbreviations.append(chinese_abb)
                simplified_abb = terminology.to_simplified(chinese_abb)
                if simplified_abb not in simplified_abbreviations:
                    simplified_abbreviations.append(simplified_abb)
            for value in _japanese_forms(row):
                if value not in japanese_terms:
                    japanese_terms.append(value)

        if not english_aliases or not traditional_terms or not simplified_terms:
            continue

        entry: Dict[str, Any] = {
            "concept_id": stitch_ids[concept_key],
            "category": categories[concept_key],
        }
        if config.source_mode == EN_US_SOURCE or config.output_mode == EN_US_TARGET:
            entry["english_us"] = english_aliases[0]
            entry["english_us_aliases"] = english_aliases[1:]
            entry["english_us_abbreviations"] = english_abbreviations
        if config.source_mode == EN_UK_SOURCE or config.output_mode == EN_UK_TARGET:
            if not english_uk_aliases:
                continue
            entry["english_uk"] = english_uk_aliases[0]
            entry["english_uk_aliases"] = english_uk_aliases[1:]
            entry["english_uk_abbreviations"] = english_uk_abbreviations
        if (
            config.source_mode == TRADITIONAL_CHINESE_SOURCE
            or config.output_mode == TRADITIONAL_CHINESE_TARGET
        ):
            entry["traditional_chinese"] = traditional_terms[0]
            entry["traditional_chinese_aliases"] = traditional_terms[1:]
            if traditional_abbreviations:
                entry["traditional_chinese_abbreviation"] = traditional_abbreviations[0]
        if (
            config.source_mode == SIMPLIFIED_CHINESE_SOURCE
            or config.output_mode == SIMPLIFIED_CHINESE_TARGET
        ):
            entry["simplified_chinese_authoritative_term"] = simplified_terms[0]
            entry["simplified_chinese_aliases"] = simplified_terms[1:]
            if simplified_abbreviations:
                entry["simplified_chinese_abbreviation"] = simplified_abbreviations[0]
        if config.source_mode == JAPANESE_SOURCE or config.output_mode == JAPANESE_TARGET:
            if not japanese_terms:
                continue
            entry["japanese"] = japanese_terms[0]
            entry["japanese_aliases"] = japanese_terms[1:]
        terms.append(entry)

    if not terms:
        raise BroadTranslationError()
    return terms


def _glossary_char_count(terms: Sequence[Dict[str, Any]]) -> int:
    return len(json.dumps(list(terms), ensure_ascii=False, separators=(",", ":")))


def build_source_segments(rows: pd.DataFrame) -> Tuple[List[Dict[str, str]], List[pd.Series]]:
    segments: List[Dict[str, str]] = []
    segment_rows: List[pd.Series] = []
    for _, row in rows.iterrows():
        semantic_text = str(row.get("semantic_text", row.get("text", ""))).strip()
        if not semantic_text:
            continue
        segment_id = f"segment-{len(segments):04d}"
        segments.append({"source_segment_id": segment_id, "text": semantic_text})
        segment_rows.append(row)
    return segments, segment_rows


def _protect_segment_url_domains(
    segments: Sequence[Dict[str, str]],
) -> Tuple[List[Dict[str, str]], Dict[str, Dict[str, str]]]:
    protected_segments: List[Dict[str, str]] = []
    replacements_by_segment: Dict[str, Dict[str, str]] = {}
    placeholder_offset = 0
    for segment in segments:
        source_id = segment["source_segment_id"]
        protected, replacements = terminology.protect_url_domains(
            segment["text"],
            placeholder_start_index=placeholder_offset,
        )
        placeholder_offset += len(replacements)
        protected_segments.append(
            {"source_segment_id": source_id, "text": protected}
        )
        replacements_by_segment[source_id] = replacements
    return protected_segments, replacements_by_segment


def _restore_semantic_unit_url_domains(
    units: Sequence[dict[str, Any]],
    replacements_by_segment: Mapping[str, Mapping[str, str]],
) -> List[dict[str, Any]]:
    restored_units: List[dict[str, Any]] = []
    for unit in units:
        replacements: Dict[str, str] = {}
        for source_id in unit["source_segment_ids"]:
            replacements.update(replacements_by_segment.get(source_id, {}))
        restored = terminology.restore_url_domains(
            unit["translation"],
            replacements,
        )
        restored_unit = dict(unit)
        restored_unit["translation"] = (
            restored if restored is not None else "__ciurlinvalid__"
        )
        restored_units.append(restored_unit)
    return restored_units


def _broad_debug_protected_spans(
    source_segment_ids: Sequence[str],
    source_by_id: Mapping[str, str],
    replacements_by_segment: Mapping[str, Mapping[str, str]],
) -> List[Dict[str, str]]:
    spans: List[Dict[str, str]] = []
    seen: set[Tuple[str, str, str]] = set()
    for source_id in source_segment_ids:
        for text in replacements_by_segment.get(source_id, {}).values():
            key = (source_id, "url_or_domain", str(text))
            if key not in seen:
                spans.append(
                    {
                        "source_segment_id": source_id,
                        "kind": "url_or_domain",
                        "text": str(text),
                    }
                )
                seen.add(key)
        source = source_by_id.get(source_id, "")
        for match in HANDLE_RE.finditer(source):
            key = (source_id, "handle", match.group(0))
            if key not in seen:
                spans.append(
                    {
                        "source_segment_id": source_id,
                        "kind": "handle",
                        "text": match.group(0),
                    }
                )
                seen.add(key)
    return spans


def _build_broad_debug_capture(
    raw_units: Sequence[dict[str, Any]],
    processed_units: Sequence[dict[str, Any]],
    resolved_units: Sequence[dict[str, Any]],
    segments: Sequence[Dict[str, str]],
    config: _RouteConfig,
    replacements_by_segment: Mapping[str, Mapping[str, str]],
) -> Dict[str, object]:
    source_by_id = {
        segment["source_segment_id"]: segment["text"] for segment in segments
    }
    processed_by_id = {
        str(unit.get("semantic_unit_id", "")): unit for unit in processed_units
    }
    resolved_by_id = {
        str(unit.get("semantic_unit_id", "")): unit for unit in resolved_units
    }
    captured_units: List[Dict[str, object]] = []
    route = f"{config.source_language} -> {config.target_language}"
    for raw_unit in raw_units:
        unit_id = str(raw_unit.get("semantic_unit_id", ""))
        source_ids = [str(value) for value in raw_unit["source_segment_ids"]]
        processed_unit = processed_by_id[unit_id]
        resolved_unit = resolved_by_id[unit_id]
        raw_candidate = str(raw_unit.get("translation", ""))
        processed_candidate = str(processed_unit.get("translation", ""))
        rejected = str(resolved_unit.get("validation_status", "")) == "unresolved"
        captured: Dict[str, object] = {
            "semantic_unit_id": unit_id,
            "source_text": "\n".join(source_by_id[source_id] for source_id in source_ids),
            "raw_candidate": raw_candidate,
            "validation_status": "rejected" if rejected else "accepted",
            "rejection_reason": str(
                resolved_unit.get("validation_failure_reason", "")
            ),
            "route": route,
            "protected_spans": _broad_debug_protected_spans(
                source_ids,
                source_by_id,
                replacements_by_segment,
            ),
        }
        if processed_candidate != raw_candidate:
            captured["processed_candidate"] = processed_candidate
        captured_units.append(captured)
    return {"enabled": True, "route": route, "units": captured_units}


def build_prompt(
    segments: Sequence[Dict[str, str]],
    terms: Sequence[Dict[str, Any]],
    config: _RouteConfig,
) -> str:
    payload = {
        "source_language": config.source_language,
        "target_language": config.target_language,
        "source_segments": list(segments),
        "authoritative_crochet_glossary": list(terms),
    }
    dialect = ""
    if config.output_mode == EN_US_TARGET:
        dialect = " Use US English crochet terminology."
    elif config.output_mode == EN_UK_TARGET:
        dialect = " Use UK English crochet terminology."
    return (
        "You are a specialist crochet-pattern translation agent. Translate the complete "
        f"cleaned OCR pattern from {config.source_language} to {config.target_language}."
        + dialect
        + " Use the supplied full route-relevant glossary as terminology context, while allowing "
        "natural target-language expression. Preserve crochet meaning, quantities, units, "
        "rows and rounds, repeats, and operation order. Translate clear titles, headings, and "
        "prose. Do not invent missing instructions or silently repair genuinely ambiguous OCR. "
        "Preserve every opaque __ciurl...__ URL/domain placeholder exactly once, unchanged, and "
        "within the semantic unit assigned to its source segment. Segments are visual OCR "
        "fragments with stable IDs; combine only adjacent segments when they form one "
        "instruction. Return JSON only with exactly two object keys: segment_assignments and "
        "semantic_units. Every input source_segment_id must appear exactly once as a key in "
        "segment_assignments. Each value is a semantic unit ID. Multiple adjacent source "
        "segments may map to the same semantic unit ID when they form one instruction. "
        "semantic_units is an object keyed by semantic unit ID; every value is an object with "
        "exactly one key translated_text. Every assignment must reference an existing semantic "
        "unit, and every semantic unit must be referenced by at least one assignment. Example: "
        '{"segment_assignments":{"segment-0000":"unit-0000","segment-0001":"unit-0000"},'
        '"semantic_units":{"unit-0000":{"translated_text":"..."}}}.\n'
        f"INPUT: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
    )


def _json_type_name(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    return "unknown"


def _parse_response_payload(payload: object) -> object:
    if not isinstance(payload, dict):
        raise _BroadResponseParsingError(
            "provider_envelope",
            "provider_response_not_object",
            expected_top_level_shape="object_with_output_array",
        )
    output = payload.get("output")
    if not isinstance(output, list):
        raise _BroadResponseParsingError(
            "provider_envelope",
            "provider_output_not_array",
            expected_top_level_shape="object_with_output_array",
        )
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "output_text":
                continue
            text = str(block.get("text", "")).strip()
            if text:
                return _parse_model_json(text)
    raise _BroadResponseParsingError(
        "provider_envelope",
        "output_text_not_found",
        expected_top_level_shape="object_with_output_array",
    )


def _parse_model_json(raw: str) -> object:
    raw = raw.strip()
    if raw.startswith("```") and raw.endswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw, object_pairs_hook=_json_object_with_unique_keys)
    except _DuplicateJsonObjectKeyError:
        raise _BroadResponseParsingError(
            "semantic_unit_schema",
            "duplicate_json_object_key",
            expected_top_level_shape=KEYED_RESPONSE_SHAPE,
        ) from None
    except json.JSONDecodeError:
        raise _BroadResponseParsingError(
            "json_decode",
            "model_output_not_valid_json",
            exception_type="JSONDecodeError",
            expected_top_level_shape="json_object",
        ) from None
    return parsed


def _json_object_with_unique_keys(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {}
    for key, value in pairs:
        if key in parsed:
            raise _DuplicateJsonObjectKeyError()
        parsed[key] = value
    return parsed


def _parse_semantic_units(
    parsed: object,
    expected_ids: Sequence[str],
    diagnostic_logger: Optional[DiagnosticLogger] = None,
) -> List[dict[str, Any]]:
    expected_shape = KEYED_RESPONSE_SHAPE
    if not isinstance(parsed, dict):
        raise _BroadResponseParsingError(
            "semantic_unit_schema",
            "decoded_json_not_object",
            expected_top_level_shape=expected_shape,
            actual_top_level_json_type=_json_type_name(parsed),
        )
    if set(parsed) != {"segment_assignments", "semantic_units"}:
        raise _BroadResponseParsingError(
            "semantic_unit_schema",
            "unexpected_top_level_keys",
            expected_top_level_shape=expected_shape,
            actual_top_level_json_type="object",
        )
    assignments = parsed.get("segment_assignments")
    semantic_units = parsed.get("semantic_units")
    if not isinstance(assignments, dict):
        raise _BroadResponseParsingError(
            "semantic_unit_schema",
            "segment_assignments_not_object",
            expected_top_level_shape=expected_shape,
            actual_top_level_json_type="object",
        )
    if not isinstance(semantic_units, dict):
        raise _BroadResponseParsingError(
            "semantic_unit_schema",
            "semantic_units_not_object",
            expected_top_level_shape=expected_shape,
            actual_top_level_json_type="object",
        )
    semantic_unit_count = len(semantic_units)
    if not all(
        isinstance(source_id, str)
        and source_id
        and isinstance(unit_id, str)
        and unit_id
        for source_id, unit_id in assignments.items()
    ):
        raise _BroadResponseParsingError(
            "semantic_unit_schema",
            "segment_assignment_fields_invalid",
            expected_top_level_shape=expected_shape,
            actual_top_level_json_type="object",
            semantic_unit_count=semantic_unit_count,
        )

    translations_by_unit: Dict[str, str] = {}
    for unit_id, unit in semantic_units.items():
        if (
            not isinstance(unit_id, str)
            or not unit_id
            or not isinstance(unit, dict)
            or set(unit) != {"translated_text"}
            or not isinstance(unit.get("translated_text"), str)
        ):
            raise _BroadResponseParsingError(
                "semantic_unit_schema",
                "semantic_unit_shape_invalid",
                expected_top_level_shape=expected_shape,
                actual_top_level_json_type="object",
                semantic_unit_count=semantic_unit_count,
            )
        translations_by_unit[unit_id] = unit["translated_text"]

    returned_ids = list(assignments)
    expected_set = set(expected_ids)
    returned_set = set(returned_ids)
    missing_ids = [source_id for source_id in expected_ids if source_id not in returned_set]
    unknown_ids = [source_id for source_id in returned_ids if source_id not in expected_set]
    if missing_ids or unknown_ids:
        _log(
            diagnostic_logger,
            "id_coverage_validation_failed",
            expected_source_segment_ids=list(expected_ids),
            returned_source_segment_ids=returned_ids,
            missing_source_segment_ids=missing_ids,
            duplicate_source_segment_ids=[],
            unknown_source_segment_ids=unknown_ids,
            semantic_unit_count=semantic_unit_count,
            expected_segment_count=len(expected_ids),
        )
        raise _BroadResponseParsingError(
            "semantic_unit_schema",
            "source_segment_coverage_invalid",
            expected_top_level_shape=expected_shape,
            actual_top_level_json_type="object",
            semantic_unit_count=semantic_unit_count,
        )

    referenced_unit_ids = set(assignments.values())
    defined_unit_ids = set(translations_by_unit)
    if not referenced_unit_ids.issubset(defined_unit_ids):
        raise _BroadResponseParsingError(
            "semantic_unit_schema",
            "assignment_references_unknown_semantic_unit",
            expected_top_level_shape=expected_shape,
            actual_top_level_json_type="object",
            semantic_unit_count=semantic_unit_count,
        )
    if defined_unit_ids != referenced_unit_ids:
        raise _BroadResponseParsingError(
            "semantic_unit_schema",
            "orphan_semantic_unit",
            expected_top_level_shape=expected_shape,
            actual_top_level_json_type="object",
            semantic_unit_count=semantic_unit_count,
        )

    normalized: List[dict[str, Any]] = []
    unit_indexes: Dict[str, int] = {}
    for source_id in expected_ids:
        unit_id = assignments[source_id]
        if unit_id not in unit_indexes:
            unit_indexes[unit_id] = len(normalized)
            normalized.append(
                {
                    "semantic_unit_id": unit_id,
                    "source_segment_ids": [source_id],
                    "translation": translations_by_unit[unit_id],
                }
            )
            continue
        unit_index = unit_indexes[unit_id]
        if unit_index != len(normalized) - 1:
            raise _BroadResponseParsingError(
                "semantic_unit_schema",
                "semantic_unit_assignments_not_contiguous",
                expected_top_level_shape=expected_shape,
                actual_top_level_json_type="object",
                semantic_unit_count=semantic_unit_count,
            )
        normalized[unit_index]["source_segment_ids"].append(source_id)
    return normalized


def _validate_id_coverage(
    units: Sequence[dict[str, Any]],
    expected_ids: Sequence[str],
    diagnostic_logger: Optional[DiagnosticLogger] = None,
) -> None:
    claimed: List[str] = []
    for unit in units:
        claimed.extend(unit["source_segment_ids"])

    def fail() -> None:
        claimed_counts = Counter(claimed)
        expected_set = set(expected_ids)
        missing_source_segment_ids = [
            source_id for source_id in expected_ids if claimed_counts[source_id] == 0
        ]
        duplicate_source_segment_ids = list(
            dict.fromkeys(source_id for source_id in claimed if claimed_counts[source_id] > 1)
        )
        unknown_source_segment_ids = list(
            dict.fromkeys(source_id for source_id in claimed if source_id not in expected_set)
        )
        _log(
            diagnostic_logger,
            "id_coverage_validation_failed",
            expected_source_segment_ids=list(expected_ids),
            returned_source_segment_ids=list(claimed),
            missing_source_segment_ids=missing_source_segment_ids,
            duplicate_source_segment_ids=duplicate_source_segment_ids,
            unknown_source_segment_ids=unknown_source_segment_ids,
            semantic_unit_count=len(units),
            expected_segment_count=len(expected_ids),
        )
        raise _BroadResponseParsingError(
            "semantic_unit_schema",
            "normalized_source_segment_coverage_invalid",
            expected_top_level_shape=KEYED_RESPONSE_SHAPE,
            actual_top_level_json_type="object",
            semantic_unit_count=len(units),
        )

    if claimed != list(expected_ids):
        fail()
    positions = {source_id: index for index, source_id in enumerate(expected_ids)}
    for unit in units:
        indexes = [positions[source_id] for source_id in unit["source_segment_ids"]]
        if indexes != list(range(indexes[0], indexes[0] + len(indexes))):
            fail()


def _url_domain_counts(text: str) -> Counter[str]:
    return Counter(
        identity
        for _start, _end, identity in terminology.iter_url_domain_spans(text)
    )


def _validate_url_domains(source: str, translation: str) -> bool:
    if terminology.URL_PLACEHOLDER_RE.search(translation):
        return False
    return _url_domain_counts(translation) == _url_domain_counts(source)


def _validation_diagnostic_excerpt(text: str) -> Tuple[str, bool]:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= VALIDATION_DIAGNOSTIC_EXCERPT_CHARS:
        return compact, False
    return compact[:VALIDATION_DIAGNOSTIC_EXCERPT_CHARS] + "…", True


def _unit_integrity_failure_fields(
    source: str,
    translation: str,
    failed_rule: str,
    source_segment_ids: Optional[Sequence[str]] = None,
) -> Dict[str, object]:
    source_excerpt, source_truncated = _validation_diagnostic_excerpt(source)
    translation_excerpt, translation_truncated = _validation_diagnostic_excerpt(
        translation
    )
    fields: Dict[str, object] = {
        "failed_rule": failed_rule,
        "failed_source_excerpt": source_excerpt,
        "failed_translation_excerpt": translation_excerpt,
        "failed_source_excerpt_truncated": source_truncated,
        "failed_translation_excerpt_truncated": translation_truncated,
    }
    if source_segment_ids is not None:
        fields["source_segment_ids"] = list(source_segment_ids)
    if failed_rule == "protected_url_or_domain":
        fields["required_url_or_domains"] = list(
            _url_domain_counts(source).elements()
        )
        fields["present_url_or_domains"] = list(
            _url_domain_counts(translation).elements()
        )
    return fields


def _validate_unit_integrity(
    source: str,
    translation: str,
    *,
    diagnostic_logger: Optional[DiagnosticLogger] = None,
    source_segment_ids: Optional[Sequence[str]] = None,
) -> None:
    failed_rule = ""
    if not translation.strip():
        failed_rule = "blank_translation"
    elif not _validate_url_domains(source, translation):
        failed_rule = "protected_url_or_domain"
    if not failed_rule:
        return

    fields = _unit_integrity_failure_fields(
        source,
        translation,
        failed_rule,
        source_segment_ids,
    )
    _log(diagnostic_logger, "unit_integrity_validation_failed", **fields)
    raise _UnitIntegrityError(failed_rule, fields)


def validate_semantic_units(
    units: Sequence[dict[str, Any]],
    segments: Sequence[Dict[str, str]],
    config: _RouteConfig,
    diagnostic_logger: Optional[DiagnosticLogger] = None,
    terms: Optional[Sequence[Dict[str, Any]]] = None,
) -> None:
    del config, terms
    expected_ids = [segment["source_segment_id"] for segment in segments]
    _validate_id_coverage(units, expected_ids, diagnostic_logger=diagnostic_logger)
    source_by_id = {
        segment["source_segment_id"]: segment["text"] for segment in segments
    }
    for unit in units:
        source = "\n".join(
            source_by_id[item] for item in unit["source_segment_ids"]
        )
        _validate_unit_integrity(
            source,
            unit["translation"],
            diagnostic_logger=diagnostic_logger,
            source_segment_ids=unit["source_segment_ids"],
        )


def request_warning_for_target(output_mode: str) -> str:
    """Return the localized, content-free request warning for safe partial output."""
    return _REQUEST_WARNING_BY_TARGET.get(
        output_mode,
        _REQUEST_WARNING_BY_TARGET[EN_US_TARGET],
    )


def _resolve_unit_integrity_failures(
    units: Sequence[dict[str, Any]],
    segments: Sequence[Dict[str, str]],
    diagnostic_logger: Optional[DiagnosticLogger] = None,
) -> Tuple[List[dict[str, Any]], int]:
    """Preserve source only for blank or protected-literal-corrupt units."""
    expected_ids = [segment["source_segment_id"] for segment in segments]
    _validate_id_coverage(units, expected_ids, diagnostic_logger=diagnostic_logger)
    source_by_id = {
        segment["source_segment_id"]: segment["text"] for segment in segments
    }
    resolved_units: List[dict[str, Any]] = []
    failures: List[_UnitIntegrityError] = []

    for unit in units:
        resolved = dict(unit)
        source = "\n".join(
            source_by_id[source_id] for source_id in unit["source_segment_ids"]
        )
        try:
            _validate_unit_integrity(
                source,
                unit["translation"],
                diagnostic_logger=diagnostic_logger,
                source_segment_ids=unit["source_segment_ids"],
            )
        except _UnitIntegrityError as error:
            failures.append(error)
            resolved["translation"] = source
            resolved["validation_status"] = "unresolved"
            resolved["validation_failure_reason"] = error.failed_rule
        else:
            resolved["validation_status"] = "validated"
            resolved["validation_failure_reason"] = ""
        resolved_units.append(resolved)

    for error in failures:
        _log(
            diagnostic_logger,
            (
                "all_units_integrity_failed"
                if len(failures) == len(resolved_units)
                else "partial_unit_integrity_failure"
            ),
            partial_unit_integrity_failure=True,
            all_units_integrity_failed=len(failures) == len(resolved_units),
            **error.diagnostic_fields,
        )

    return resolved_units, len(failures)


def call_luna_once(prompt: str, api_key: str) -> Tuple[dict[str, Any], float]:
    body = {
        "model": BROAD_MODEL,
        "reasoning": {"effort": BROAD_REASONING},
        "input": prompt,
        "max_output_tokens": BROAD_MAX_OUTPUT_TOKENS,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    timeout_seconds = max(
        0.001,
        min(BROAD_TIMEOUT_SECONDS, _BROAD_CALL_TIMEOUT_SECONDS.get()),
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.load(response)
    return payload, time.perf_counter() - started


def _row_geometry_value(row: pd.Series, primary: str, fallback: str, default: float) -> float:
    if primary in row.index and pd.notna(row.get(primary)):
        return float(row.get(primary))
    if fallback in row.index and pd.notna(row.get(fallback)):
        return float(row.get(fallback))
    return default


def adapt_semantic_units_to_line_df(
    semantic_units: Sequence[dict[str, Any]],
    segments: Sequence[Dict[str, str]],
    segment_rows: Sequence[pd.Series],
) -> pd.DataFrame:
    segment_row_by_id = {
        segments[index]["source_segment_id"]: segment_rows[index]
        for index in range(len(segments))
    }
    out: List[Dict[str, object]] = []
    for unit in semantic_units:
        ids = unit["source_segment_ids"]
        member_rows = [segment_row_by_id[source_id] for source_id in ids]
        source_regions: List[Dict[str, object]] = []
        for source_id, row in zip(ids, member_rows):
            row_min_x = _row_geometry_value(row, "min_x", "x", 0.0)
            row_max_x = _row_geometry_value(row, "max_x", "x", row_min_x + 80.0)
            row_min_y = _row_geometry_value(row, "min_y", "y", 0.0)
            row_max_y = _row_geometry_value(row, "max_y", "y", row_min_y + 20.0)
            raw_member_boxes = row.get("Member Boxes", ())
            member_boxes = tuple(
                dict(member)
                for member in raw_member_boxes
                if isinstance(member, dict)
            ) if isinstance(raw_member_boxes, (list, tuple)) else ()
            if not member_boxes:
                member_boxes = (
                    {
                        "text": str(row.get("text", "")).strip(),
                        "confidence": round(float(row.get("confidence", 0) or 0), 3),
                        "min_x": row_min_x,
                        "max_x": row_max_x,
                        "min_y": row_min_y,
                        "max_y": row_max_y,
                    },
                )
            source_regions.append(
                {
                    "source_segment_id": source_id,
                    "visual_line_id": str(row.get("Visual Line ID", "")),
                    "reading_order": int(row.get("Reading Order", len(source_regions)) or 0),
                    "text": str(row.get("text", "")).strip(),
                    "confidence": round(float(row.get("confidence", 0) or 0), 3),
                    "member_boxes": member_boxes,
                    "min_x": row_min_x,
                    "max_x": row_max_x,
                    "min_y": row_min_y,
                    "max_y": row_max_y,
                }
            )
        original = "\n".join(
            str(row.get("text", "")).strip() for row in member_rows
        )
        translation = unit["translation"]
        confidences = [float(row.get("confidence", 0) or 0) for row in member_rows]
        min_x = min(_row_geometry_value(row, "min_x", "x", 0.0) for row in member_rows)
        max_x = max(
            _row_geometry_value(row, "max_x", "x", min_x + 80.0) for row in member_rows
        )
        min_y = min(_row_geometry_value(row, "min_y", "y", 0.0) for row in member_rows)
        max_y = max(
            _row_geometry_value(row, "max_y", "y", min_y + 20.0) for row in member_rows
        )
        changed = terminology.norm_text(original) != terminology.norm_text(translation)
        out.append(
            {
                "Original": original,
                "Translation": translation,
                "Confidence": round(min(confidences), 3) if confidences else 0.0,
                "Changed": "✓" if changed else "",
                "Semantic Unit ID": str(unit.get("semantic_unit_id", "")),
                "Source Segment IDs": tuple(ids),
                "Validation Status": str(unit.get("validation_status", "validated")),
                "Validation Failure Reason": str(
                    unit.get("validation_failure_reason", "")
                ),
                "Source Regions": tuple(source_regions),
                "Visual Line IDs": tuple(
                    str(region.get("visual_line_id", "")) for region in source_regions
                ),
                "Reading Order": min(
                    int(region.get("reading_order", 0) or 0) for region in source_regions
                ),
                "min_x": min_x,
                "max_x": max_x,
                "min_y": min_y,
                "max_y": max_y,
            }
        )
    return pd.DataFrame(out)


def _resolve_api_key(environ: Optional[Mapping[str, str]] = None) -> str:
    values = os.environ if environ is None else environ
    api_key = str(values.get("OPENAI_API_KEY", "")).strip()
    if not api_key:
        raise BroadTranslationError()
    return api_key


def _safe_diagnostic_atom(value: object) -> str:
    atom = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return atom[:80] or "unavailable"


def _provider_failure_diagnostics(error: BaseException) -> Dict[str, str]:
    """Return safe provider-failure metadata without prompts, keys, or response bodies."""
    fields: Dict[str, str] = {
        "exception_type": type(error).__name__,
        "failure_classification": "provider_error",
    }
    if isinstance(error, urllib.error.HTTPError):
        fields["provider_failure_type"] = "http_error"
        fields["failure_classification"] = "http_transport_rejected"
        fields["http_status"] = _safe_diagnostic_atom(error.code)
        fields["http_reason"] = _safe_diagnostic_atom(error.reason)
        return fields
    if isinstance(error, urllib.error.URLError):
        fields["provider_failure_type"] = "url_error"
        reason = error.reason
        if isinstance(reason, TimeoutError):
            fields["failure_classification"] = "url_transport_timeout"
            fields["url_error_reason"] = "TimeoutError"
        else:
            fields["failure_classification"] = "url_transport_failed"
            fields["url_error_reason"] = _safe_diagnostic_atom(
                reason if not isinstance(reason, BaseException) else type(reason).__name__
            )
        return fields
    if isinstance(error, TimeoutError):
        fields["provider_failure_type"] = "timeout"
        fields["failure_classification"] = "request_timeout"
        return fields
    if isinstance(error, json.JSONDecodeError):
        fields["provider_failure_type"] = "json_decode"
        fields["failure_classification"] = "response_json_parse_failed"
        return fields
    if isinstance(error, ValueError):
        fields["provider_failure_type"] = "value_error"
        fields["failure_classification"] = "provider_value_error"
        return fields
    if isinstance(error, OSError):
        fields["provider_failure_type"] = "os_error"
        fields["failure_classification"] = "provider_os_error"
        return fields
    if isinstance(error, TypeError):
        fields["provider_failure_type"] = "type_error"
        fields["failure_classification"] = "provider_type_error"
        return fields
    if isinstance(error, AttributeError):
        fields["provider_failure_type"] = "attribute_error"
        fields["failure_classification"] = "provider_attribute_error"
        return fields
    fields["provider_failure_type"] = _safe_diagnostic_atom(type(error).__name__)
    return fields


def _provider_failure_policy(
    error: BaseException,
    elapsed_seconds: float,
) -> Tuple[str, str, bool]:
    """Classify documented transport failures without inspecting provider content."""
    if isinstance(error, urllib.error.HTTPError):
        status = int(error.code)
        retryable = status in {500, 502, 503, 504}
        return (
            f"http_{status}",
            "http_transient" if retryable else "http_non_retryable",
            retryable,
        )

    reason: object = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, TimeoutError):
        return "timeout", "request_timeout", False
    if isinstance(reason, (ConnectionResetError, http.client.RemoteDisconnected)):
        retryable = elapsed_seconds <= BROAD_FAST_TRANSIENT_SECONDS
        return (
            "connection_reset",
            "fast_transient_disconnect" if retryable else "transport_failure",
            retryable,
        )
    if isinstance(reason, ConnectionRefusedError):
        return "connection_refused", "transport_non_retryable", False
    if isinstance(reason, socket.gaierror):
        return "dns_failure", "transport_non_retryable", False
    if isinstance(reason, ssl.SSLError):
        return "tls_failure", "transport_non_retryable", False
    if isinstance(error, json.JSONDecodeError):
        retryable = elapsed_seconds <= BROAD_FAST_TRANSIENT_SECONDS
        return (
            "provider_json_malformed",
            "malformed_response" if retryable else "late_malformed_response",
            retryable,
        )
    if isinstance(error, (urllib.error.URLError, OSError)):
        return "transport_failure", "transport_non_retryable", False
    return "provider_failure", "unexpected_provider_failure", False


def _log(diagnostic_logger: Optional[DiagnosticLogger], phase: str, **fields: object) -> None:
    if diagnostic_logger is None:
        return
    try:
        diagnostic_logger(phase, **fields)
    except Exception:
        pass


def _log_response_parsing_failure(
    diagnostic_logger: Optional[DiagnosticLogger],
    error: _BroadResponseParsingError,
    elapsed_seconds: float,
    call_ordinal: int,
) -> None:
    fields: Dict[str, object] = {
        "stage": error.stage,
        "exception_type": error.exception_type,
        "reason": error.reason,
        "route": "broad",
        "model": BROAD_MODEL,
        "call_ordinal": call_ordinal,
        "elapsed_seconds": elapsed_seconds,
    }
    if error.expected_top_level_shape:
        fields["expected_top_level_shape"] = error.expected_top_level_shape
    if error.actual_top_level_json_type:
        fields["actual_top_level_json_type"] = error.actual_top_level_json_type
    if error.semantic_unit_count is not None:
        fields["semantic_unit_count"] = error.semantic_unit_count
    _log(diagnostic_logger, "broad_response_parse_failed", **fields)


def translate_merged_ocr_lines_broad(
    rows: pd.DataFrame,
    source_mode: str,
    output_mode: str,
    diagnostic_logger: Optional[DiagnosticLogger] = None,
    profile_count: Optional[ProfileCount] = None,
    profile_add_time: Optional[ProfileAddTime] = None,
    environ: Optional[Mapping[str, str]] = None,
    luna_caller: Optional[Callable[[str, str], Tuple[dict[str, Any], float]]] = None,
) -> pd.DataFrame:
    config = _route_config(source_mode, output_mode)
    debug_capture_enabled = is_broad_debug_capture_enabled(environ)
    segments, segment_rows = build_source_segments(rows)
    if not segments:
        return pd.DataFrame()
    protected_segments, url_replacements_by_segment = (
        _protect_segment_url_domains(segments)
    )

    terms = build_glossary(source_mode, output_mode)
    prompt = build_prompt(protected_segments, terms, config)
    _log(
        diagnostic_logger,
        "broad_glossary_scope",
        route_glossary_entry_count=len(terms),
        request_glossary_entry_count=len(terms),
        route_glossary_char_count=_glossary_char_count(terms),
        request_glossary_char_count=_glossary_char_count(terms),
        prompt_char_count=len(prompt),
    )
    api_key = _resolve_api_key(environ)
    caller = luna_caller or call_luna_once

    broad_start = time.perf_counter()
    _log(diagnostic_logger, "broad_translation_begin", visual_line_count=len(segments))
    expected_ids = [segment["source_segment_id"] for segment in segments]
    attempt = 1
    while attempt <= 2:
        luna_start = time.perf_counter()
        remaining_budget = BROAD_TIMEOUT_SECONDS - (luna_start - broad_start)
        if remaining_budget <= 0:
            raise BroadRecoverableError(
                "shared_budget_exhausted",
                "request_timeout",
                attempt_count=attempt - 1,
            )
        _log(
            diagnostic_logger,
            "ai_request_begin",
            call_ordinal=attempt,
            model=BROAD_MODEL,
            route="broad",
            remaining_budget_seconds=remaining_budget,
        )
        timeout_token = _BROAD_CALL_TIMEOUT_SECONDS.set(remaining_budget)
        luna_elapsed = 0.0
        try:
            payload, luna_elapsed = caller(prompt, api_key)
        except (
            TimeoutError,
            urllib.error.HTTPError,
            urllib.error.URLError,
            json.JSONDecodeError,
            OSError,
        ) as error:
            elapsed_seconds = time.perf_counter() - luna_start
            reason, classification, retryable = _provider_failure_policy(
                error,
                elapsed_seconds,
            )
            remaining_after_failure = BROAD_TIMEOUT_SECONDS - (
                time.perf_counter() - broad_start
            )
            retry_scheduled = (
                attempt == 1
                and retryable
                and remaining_after_failure >= BROAD_MIN_RETRY_BUDGET_SECONDS
            )
            provider_diagnostics = _provider_failure_diagnostics(error)
            provider_diagnostics["failure_classification"] = classification
            _log(
                diagnostic_logger,
                "ai_request_end",
                elapsed_seconds=elapsed_seconds,
                call_ordinal=attempt,
                model=BROAD_MODEL,
                route="broad",
                outcome="provider_error",
                retry_scheduled=retry_scheduled,
                remaining_budget_seconds=max(0.0, remaining_after_failure),
                **provider_diagnostics,
            )
            if retry_scheduled:
                _log(
                    diagnostic_logger,
                    "broad_retry_scheduled",
                    call_ordinal=attempt,
                    reason=reason,
                    failure_classification=classification,
                    retry_scheduled=True,
                )
                attempt += 1
                continue
            raise BroadRecoverableError(
                reason,
                classification,
                attempt_count=attempt,
            ) from None
        finally:
            _BROAD_CALL_TIMEOUT_SECONDS.reset(timeout_token)
            if profile_count is not None:
                profile_count("broad Luna translation calls", 1.0)
            if profile_add_time is not None:
                profile_add_time(
                    "broad Luna translation",
                    luna_elapsed or max(0.0, time.perf_counter() - luna_start),
                )

        try:
            raw_units = _parse_semantic_units(
                _parse_response_payload(payload),
                expected_ids,
                diagnostic_logger=diagnostic_logger,
            )
            units = _restore_semantic_unit_url_domains(
                raw_units,
                url_replacements_by_segment,
            )
            if not any(unit["translation"].strip() for unit in units):
                raise _BroadResponseParsingError(
                    "semantic_unit_schema",
                    "all_translations_blank",
                    expected_top_level_shape=KEYED_RESPONSE_SHAPE,
                    actual_top_level_json_type="object",
                    semantic_unit_count=len(units),
                )
        except _BroadResponseParsingError as error:
            elapsed_seconds = time.perf_counter() - luna_start
            _log_response_parsing_failure(
                diagnostic_logger,
                error,
                elapsed_seconds,
                attempt,
            )
            remaining_after_failure = BROAD_TIMEOUT_SECONDS - (
                time.perf_counter() - broad_start
            )
            retry_scheduled = (
                attempt == 1
                and elapsed_seconds <= BROAD_FAST_TRANSIENT_SECONDS
                and remaining_after_failure >= BROAD_MIN_RETRY_BUDGET_SECONDS
            )
            _log(
                diagnostic_logger,
                "ai_request_end",
                elapsed_seconds=elapsed_seconds,
                call_ordinal=attempt,
                model=BROAD_MODEL,
                route="broad",
                outcome="validation_rejected",
                reason=error.reason,
                failure_classification="malformed_response",
                retry_scheduled=retry_scheduled,
                remaining_budget_seconds=max(0.0, remaining_after_failure),
            )
            if retry_scheduled:
                _log(
                    diagnostic_logger,
                    "broad_retry_scheduled",
                    call_ordinal=attempt,
                    reason=error.reason,
                    failure_classification="malformed_response",
                    retry_scheduled=True,
                )
                attempt += 1
                continue
            raise BroadRecoverableError(
                error.reason,
                "malformed_response",
                attempt_count=attempt,
            ) from None

        processed_units = units
        units, partial_failure_count = _resolve_unit_integrity_failures(
            units,
            segments,
            diagnostic_logger=diagnostic_logger,
        )
        result = adapt_semantic_units_to_line_df(units, segments, segment_rows)
        if debug_capture_enabled:
            result.attrs[BROAD_DEBUG_CAPTURE_ATTR] = _build_broad_debug_capture(
                raw_units,
                processed_units,
                units,
                segments,
                config,
                url_replacements_by_segment,
            )
        all_units_invalid = bool(units) and partial_failure_count == len(units)
        if all_units_invalid:
            result.attrs[REQUEST_WARNING_ATTR] = request_warning_for_target(output_mode)
        _log(
            diagnostic_logger,
            "ai_request_end",
            elapsed_seconds=luna_elapsed,
            call_ordinal=attempt,
            model=BROAD_MODEL,
            route="broad",
            outcome="partial_success" if partial_failure_count else "success",
            partial_unit_integrity_failure_count=partial_failure_count,
            all_units_integrity_failed=all_units_invalid,
            retry_scheduled=False,
        )
        _log(
            diagnostic_logger,
            "line_reconstruction_end",
            elapsed_seconds=time.perf_counter() - broad_start,
            visual_line_count=len(result),
            outcome="partial_success" if partial_failure_count else "success",
            partial_unit_integrity_failure_count=partial_failure_count,
            all_units_integrity_failed=all_units_invalid,
        )
        return result

    raise BroadTranslationError()
