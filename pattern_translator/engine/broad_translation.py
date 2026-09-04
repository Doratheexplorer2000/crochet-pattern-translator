"""Broad Luna translation for validated crochet pattern language routes."""

from __future__ import annotations

import csv
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
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
BROAD_FLAG_ENV = "PATTERN_BROAD_TRANSLATION_ENABLED"
VALIDATION_DIAGNOSTIC_EXCERPT_CHARS = 400

EN_US_SOURCE = "English — US"
TRADITIONAL_CHINESE_TARGET = "Traditional Chinese"
SIMPLIFIED_CHINESE_SOURCE = "Simplified Chinese"
EN_US_TARGET = "English — US"
SIMPLIFIED_CHINESE_TARGET = SIMPLIFIED_CHINESE_SOURCE

_TRUE_VALUES = {"1", "true", "yes", "on"}
KEYED_RESPONSE_SHAPE = "object_with_segment_assignments_and_semantic_units_objects"
SHARED_ARABIC_DIGIT_PROMPT_CONTRACT = (
    "Preserve every explicit Arabic digit from the assigned source segments as the "
    "same Arabic digit in the translation. Do not spell it out as a number word, "
    "ordinal word, or frequency word, and do not replace it with language-specific "
    "numeric characters or words. For example, source 1 must remain 1, not one, once, "
    "first, 一, or 第一; source 2 must remain 2, not two, twice, second, 二, or 兩. Do "
    "not infer or invent Arabic digits absent from the assigned source segments. Natural "
    "fluency must never override explicit Arabic-digit preservation.\n"
)
SHARED_TRANSLATION_COMPLETENESS_PROMPT_CONTRACT = (
    "Translate all clear, legible source-language content into the target language, "
    "including ordinary prose and section headings. The glossary provides domain guidance "
    "and does not limit what may be translated; use normal language knowledge for clear "
    "ordinary words that are absent from it. Preserve source wording only when the OCR or "
    "input itself is genuinely unclear or ambiguous, and do not hallucinate missing meaning.\n"
)
ENGLISH_CROCHET_REPEAT_PROMPT_CONTRACT = (
    "Treat an explicit x multiplier before or after a crochet unit as repetition, not "
    "as a stitch count. For example, (sc, incr) 6x means repeat the grouped unit 6 "
    "times; it does not mean work 6 single crochet stitches. Preserve x6, x 6, 6x, "
    "and equivalent multiplication-sign forms as an explicit repetition fact.\n"
)

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
ARABIC_TOKEN_RE = re.compile(r"(?<!\d)\d+(?:\.\d+)?(?!\d)")
TRIO_EN_RE = re.compile(r"\btrio\b", re.IGNORECASE)
TRIO_TRADITIONAL_DIGIT_RE = re.compile(r"(?<!\d)3(?!\d)\s*顆")
TRIO_SIMPLIFIED_DIGIT_RE = re.compile(r"(?<!\d)3(?!\d)\s*颗")
ENGLISH_ORDINAL_WORD_TO_DIGIT = {
    "first": "1",
    "second": "2",
    "third": "3",
    "fourth": "4",
    "fifth": "5",
    "sixth": "6",
    "seventh": "7",
    "eighth": "8",
    "ninth": "9",
    "tenth": "10",
}
ENGLISH_ORDINAL_WORD_PATTERNS = {
    word: re.compile(
        rf"(?<![A-Za-z0-9_-]){re.escape(word)}(?![A-Za-z0-9_-])",
        re.IGNORECASE,
    )
    for word in ENGLISH_ORDINAL_WORD_TO_DIGIT
}
CHINESE_ARABIC_ORDINAL_PATTERNS = {
    digit: re.compile(rf"第\s*{re.escape(digit)}(?!\d)")
    for digit in ENGLISH_ORDINAL_WORD_TO_DIGIT.values()
}
ROUND_EN_RE = re.compile(
    r"\b(?:rnds?|rounds?|r)\s*(\d+)(?:\s*[-–—]\s*(?:r\s*)?(\d+))?",
    re.IGNORECASE,
)
ROW_EN_RE = re.compile(
    r"\brows?\s*(\d+)(?:\s*[-–—]\s*(\d+))?",
    re.IGNORECASE,
)
ROUND_CN_RE = re.compile(r"第\s*(\d+)(?:\s*[-–—]\s*(\d+))?\s*[圈輪]")
ROUND_SIMPLIFIED_CN_RE = re.compile(r"第\s*(\d+)(?:\s*[-–—]\s*(\d+))?\s*[圈轮]")
ROW_CN_RE = re.compile(r"第\s*(\d+)(?:\s*[-–—]\s*(\d+))?\s*行")
ROUND_SC_RE = re.compile(
    r"\bR(?:ND)?\s*(\d+)(?:\s*[-–—]\s*R?\s*(\d+))?",
    re.IGNORECASE,
)
TOTAL_PAREN_END_RE = re.compile(r"\((\d+)\)\s*$")
TOTAL_EQUALS_RE = re.compile(r"=(\d+)")
TOTAL_CN_RE = re.compile(r"共\s*(\d+)")
REPEAT_PREFIX_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:x|×|\*)\s*(\d+)(?!\d)",
    re.IGNORECASE,
)
REPEAT_SUFFIX_RE = re.compile(
    r"(?<!\d)(\d+)\s*(?:x|×)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
REPEAT_CHINESE_RE = re.compile(r"重[複覆复]\s*(\d+)\s*次")
MEASURE_RE = re.compile(
    r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)\s*"
    r"(mm|cm|in(?:ch(?:es)?)?|英寸|厘米|毫米)(?![A-Za-z])",
    re.IGNORECASE,
)
ROUND_ID_EN_RE = re.compile(
    r"\b(?:rnds?|rounds?)\s*(\d+)(?:\s*[-–—]\s*(\d+))?",
    re.IGNORECASE,
)
ROUND_ID_R_RE = re.compile(
    r"\bR\s*(\d+)(?:\s*[-–—]\s*R?\s*(\d+))?",
    re.IGNORECASE,
)
ROUND_ID_CN_RE = re.compile(r"第\s*(\d+)(?:\s*[-–—]\s*(\d+))?\s*[圈輪]")
ROUND_ID_SIMPLIFIED_CN_RE = re.compile(
    r"第\s*(\d+)(?:\s*[-–—]\s*(\d+))?\s*[圈轮]"
)
ROW_ID_EN_RE = re.compile(
    r"\brows?\s*(\d+)(?:\s*[-–—]\s*(\d+))?",
    re.IGNORECASE,
)
ROW_ID_CN_RE = re.compile(r"第\s*(\d+)(?:\s*[-–—]\s*(\d+))?\s*行")

MEASUREMENT_UNIT_CANONICAL = {
    "mm": "mm",
    "毫米": "mm",
    "cm": "cm",
    "厘米": "cm",
    "in": "inch",
    "inch": "inch",
    "inches": "inch",
    "英寸": "inch",
}
MEASUREMENT_TARGET_ALIASES = {
    TRADITIONAL_CHINESE_TARGET: {
        "mm": ("mm", "毫米", "公釐"),
        "cm": ("cm", "厘米"),
        "inch": ("inch", "inches", "英寸"),
    },
    SIMPLIFIED_CHINESE_TARGET: {
        "mm": ("mm", "毫米"),
        "cm": ("cm", "厘米"),
        "inch": ("inch", "inches", "英寸"),
    },
    EN_US_TARGET: {
        "mm": ("mm", "millimeter", "millimeters"),
        "cm": ("cm",),
        "inch": ("inch", "inches"),
    },
}


class BroadTranslationError(RuntimeError):
    """Controlled broad-translation failure without provider or OCR details."""


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


_ROUTE_CONFIGS: Dict[Tuple[str, str], _RouteConfig] = {
    (EN_US_SOURCE, TRADITIONAL_CHINESE_TARGET): _RouteConfig(
        EN_US_SOURCE,
        TRADITIONAL_CHINESE_TARGET,
        "English US",
        "Traditional Chinese",
        True,
    ),
    (SIMPLIFIED_CHINESE_SOURCE, EN_US_TARGET): _RouteConfig(
        SIMPLIFIED_CHINESE_SOURCE,
        EN_US_TARGET,
        "Simplified Chinese",
        "English US",
        False,
    ),
    (EN_US_SOURCE, SIMPLIFIED_CHINESE_TARGET): _RouteConfig(
        EN_US_SOURCE,
        SIMPLIFIED_CHINESE_TARGET,
        "English US",
        "Simplified Chinese",
        True,
    ),
}


def is_broad_translation_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    values = os.environ if environ is None else environ
    return str(values.get(BROAD_FLAG_ENV, "")).strip().lower() in _TRUE_VALUES


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
        traditional_terms: List[str] = []
        simplified_terms: List[str] = []
        traditional_abbreviations: List[str] = []
        simplified_abbreviations: List[str] = []

        for row in rows:
            for alias in _us_aliases(row):
                if alias not in english_aliases:
                    english_aliases.append(alias)
            for abb in (row.get("US_abb", ""), row.get("US_abb1", "")):
                value = str(abb).strip()
                if value and value.lower() != "st" and value not in english_abbreviations:
                    english_abbreviations.append(value)
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

        if not english_aliases or not traditional_terms or not simplified_terms:
            continue

        entry: Dict[str, Any] = {
            "concept_id": stitch_ids[concept_key],
            "category": categories[concept_key],
            "english_us": english_aliases[0],
            "english_us_aliases": english_aliases[1:],
            "english_us_abbreviations": english_abbreviations,
        }
        chinese_mode = config.output_mode if config.en_us_source else config.source_mode
        if chinese_mode == TRADITIONAL_CHINESE_TARGET:
            entry["traditional_chinese"] = traditional_terms[0]
            entry["traditional_chinese_aliases"] = traditional_terms[1:]
            if traditional_abbreviations:
                entry["traditional_chinese_abbreviation"] = traditional_abbreviations[0]
        else:
            entry["simplified_chinese_authoritative_term"] = simplified_terms[0]
            entry["simplified_chinese_aliases"] = simplified_terms[1:]
            if simplified_abbreviations:
                entry["simplified_chinese_abbreviation"] = simplified_abbreviations[0]
        terms.append(entry)

    if not terms:
        raise BroadTranslationError()
    return terms


def _glossary_values(value: object) -> List[str]:
    values = value if isinstance(value, list) else [value]
    out: List[str] = []
    for raw in values:
        for candidate in terminology.split_aliases(raw):
            if candidate and candidate not in out:
                out.append(candidate)
    return out


def _source_glossary_forms(
    entry: Mapping[str, Any], config: _RouteConfig
) -> Tuple[List[str], List[str]]:
    if config.en_us_source:
        primary = _glossary_values(entry.get("english_us", ""))
        secondary = _glossary_values(entry.get("english_us_aliases", []))
        secondary.extend(_glossary_values(entry.get("english_us_abbreviations", [])))
    else:
        primary = _glossary_values(
            entry.get("simplified_chinese_authoritative_term", "")
        )
        secondary = _glossary_values(entry.get("simplified_chinese_aliases", []))
        secondary.extend(
            _glossary_values(entry.get("simplified_chinese_abbreviation", ""))
        )
    return list(dict.fromkeys(primary)), list(dict.fromkeys(secondary))


def _ascii_phrase_present(normalized_source: str, normalized_phrase: str) -> bool:
    escaped = re.escape(normalized_phrase).replace(r"\ ", r"\s+")
    return bool(
        re.search(
            rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])",
            normalized_source,
        )
    )


def _form_present(
    normalized_source: str,
    case_preserved_source: str,
    form: str,
) -> bool:
    normalized_form = terminology.norm_text(form)
    if not normalized_form:
        return False
    if re.fullmatch(r"[a-z]", normalized_form):
        # Single-letter crochet abbreviations are conventionally uppercase. Keeping
        # this case-sensitive avoids treating prose letters as crochet evidence.
        token = normalized_form.upper()
        return bool(
            re.search(
                rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])",
                case_preserved_source,
            )
        )
    if re.search(r"[\u3400-\u9fff]", normalized_form):
        return normalized_form in normalized_source
    return _ascii_phrase_present(normalized_source, normalized_form)


def _explicit_abbreviation_resolutions(
    source_text: str,
    config: _RouteConfig,
    terms: Sequence[Dict[str, Any]],
    secondary_owners: Mapping[str, Sequence[str]],
) -> Dict[str, set[str]]:
    case_source = unicodedata.normalize("NFKC", source_text)
    entry_by_id = {str(entry["concept_id"]): entry for entry in terms}
    resolutions: Dict[str, set[str]] = {}
    for form_key, owners in secondary_owners.items():
        if len(owners) < 2 or not re.fullmatch(r"[a-z][a-z0-9]*", form_key):
            continue
        displayed = form_key.upper() if len(form_key) == 1 else form_key
        matches = re.finditer(
            rf"(?<![A-Za-z0-9]){re.escape(displayed)}(?![A-Za-z0-9])\s*=\s*([^\n\r]+)",
            case_source,
            flags=0 if len(form_key) == 1 else re.IGNORECASE,
        )
        for match in matches:
            normalized_rhs = terminology.norm_text(match.group(1))
            matched_owners: set[str] = set()
            for concept_id in owners:
                primary, _ = _source_glossary_forms(entry_by_id[concept_id], config)
                if any(
                    _form_present(normalized_rhs, match.group(1), primary_form)
                    for primary_form in primary
                ):
                    matched_owners.add(concept_id)
            if len(matched_owners) == 1:
                resolutions[form_key] = matched_owners
                break
    return resolutions


def _compound_form_evidenced(form: str, normalized_segment: str) -> bool:
    normalized_form = terminology.norm_text(form)
    components = normalized_form.split()
    if not (2 <= len(components) <= 3):
        return False
    if not all(re.fullmatch(r"[a-z0-9]+", component) for component in components):
        return False
    return all(
        _ascii_phrase_present(normalized_segment, component) for component in components
    )


def select_request_glossary(
    route_terms: Sequence[Dict[str, Any]],
    segments: Sequence[Dict[str, str]],
    config: _RouteConfig,
) -> List[Dict[str, Any]]:
    """Select exact source-evidenced entries from an authoritative route glossary."""
    source_text = "\n".join(str(segment.get("text", "")) for segment in segments)
    normalized_source = terminology.norm_text(source_text)
    case_source = unicodedata.normalize("NFKC", source_text)
    normalized_segments = [
        terminology.norm_text(str(segment.get("text", ""))) for segment in segments
    ]
    forms_by_id: Dict[str, Tuple[List[str], List[str]]] = {}
    secondary_owners: Dict[str, List[str]] = {}
    for entry in route_terms:
        concept_id = str(entry["concept_id"])
        primary, secondary = _source_glossary_forms(entry, config)
        forms_by_id[concept_id] = (primary, secondary)
        for form in secondary:
            key = terminology.norm_text(form)
            if key:
                secondary_owners.setdefault(key, [])
                if concept_id not in secondary_owners[key]:
                    secondary_owners[key].append(concept_id)

    explicit_resolutions = _explicit_abbreviation_resolutions(
        source_text, config, route_terms, secondary_owners
    )
    selected_ids: set[str] = set()
    for entry in route_terms:
        concept_id = str(entry["concept_id"])
        primary, secondary = forms_by_id[concept_id]
        if any(_form_present(normalized_source, case_source, form) for form in primary):
            selected_ids.add(concept_id)
        for form in secondary:
            if not _form_present(normalized_source, case_source, form):
                continue
            key = terminology.norm_text(form)
            owners = secondary_owners.get(key, [])
            if key in explicit_resolutions:
                selected_ids.update(explicit_resolutions[key])
            else:
                selected_ids.update(owners)

    # Compound aliases such as "sc inc" are retained only when every component
    # is independently evidenced within the same OCR segment.
    for entry in route_terms:
        concept_id = str(entry["concept_id"])
        if concept_id in selected_ids:
            continue
        _, secondary = forms_by_id[concept_id]
        if any(
            _compound_form_evidenced(form, segment)
            for form in secondary
            for segment in normalized_segments
        ):
            selected_ids.add(concept_id)

    return [
        entry for entry in route_terms if str(entry["concept_id"]) in selected_ids
    ]


def _glossary_char_count(terms: Sequence[Dict[str, Any]]) -> int:
    return len(json.dumps(list(terms), ensure_ascii=False, separators=(",", ":")))


def build_source_segments(rows: pd.DataFrame) -> Tuple[List[Dict[str, str]], List[pd.Series]]:
    segments: List[Dict[str, str]] = []
    segment_rows: List[pd.Series] = []
    for _, row in rows.iterrows():
        original = str(row.get("text", "")).strip()
        if not original:
            continue
        segment_id = f"segment-{len(segments):04d}"
        segments.append({"source_segment_id": segment_id, "text": original})
        segment_rows.append(row)
    return segments, segment_rows


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
    if (
        config.source_mode == EN_US_SOURCE
        and config.output_mode == TRADITIONAL_CHINESE_TARGET
    ):
        task = (
            "TASK: Translate this stored OCR text from an English-US crochet pattern "
            "into natural Traditional Chinese.\n"
            "Preserve crochet meaning, quantities, measurements, explicit round/row facts, "
            "repeat facts, and abbreviations/terminology. Use the authoritative glossary as "
            "terminology guidance, not as a phrase-replacement table. Do not repair or "
            "silently resolve ambiguous OCR.\n"
        )
    elif (
        config.source_mode == SIMPLIFIED_CHINESE_SOURCE
        and config.output_mode == EN_US_TARGET
    ):
        task = (
            "TASK: Translate this stored OCR text from a Simplified Chinese crochet pattern "
            "into natural US-English crochet instructions.\n"
            "Preserve crochet meaning, quantities, round/row facts, repeat facts, and stitch "
            "totals. Use the authoritative glossary as terminology guidance. Do not repair "
            "or silently resolve ambiguous OCR.\n"
        )
    else:
        task = (
            "TASK: Translate this stored OCR text from an English-US crochet pattern "
            "into natural Simplified Chinese.\n"
            "Preserve crochet meaning, quantities, measurements, explicit round/row facts, "
            "repeat facts, and abbreviations/terminology. Use the authoritative glossary as "
            "terminology guidance, not as a phrase-replacement table. Do not repair or "
            "silently resolve ambiguous OCR.\n"
        )
    repeat_contract = (
        ENGLISH_CROCHET_REPEAT_PROMPT_CONTRACT
        if config.en_us_source
        else ""
    )
    return (
        task
        + SHARED_TRANSLATION_COMPLETENESS_PROMPT_CONTRACT
        + SHARED_ARABIC_DIGIT_PROMPT_CONTRACT
        + repeat_contract
        + "Segments are visual OCR fragments. Combine adjacent segments when they form one "
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
        raise BroadTranslationError()

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
        raise BroadTranslationError()

    if claimed != list(expected_ids):
        fail()
    positions = {source_id: index for index, source_id in enumerate(expected_ids)}
    for unit in units:
        indexes = [positions[source_id] for source_id in unit["source_segment_ids"]]
        if indexes != list(range(indexes[0], indexes[0] + len(indexes))):
            fail()


def _arabic_multiset(text: str) -> Counter[str]:
    return Counter(ARABIC_TOKEN_RE.findall(text))


def _validate_arabic_digit_multiset(
    source: str,
    translation: str,
    config: _RouteConfig,
) -> bool:
    source_counts = _arabic_multiset(source)
    translation_counts = _arabic_multiset(translation)
    if source_counts - translation_counts:
        return False

    extras = translation_counts - source_counts
    if config.en_us_source and extras:
        for word, digit in ENGLISH_ORDINAL_WORD_TO_DIGIT.items():
            if not extras[digit]:
                continue
            ordinal_allowance = min(
                len(ENGLISH_ORDINAL_WORD_PATTERNS[word].findall(source)),
                len(CHINESE_ARABIC_ORDINAL_PATTERNS[digit].findall(translation)),
            )
            extras[digit] -= min(extras[digit], ordinal_allowance)
            if extras[digit] == 0:
                del extras[digit]
    if config.source_mode == EN_US_SOURCE and extras["3"]:
        trio_target_pattern = (
            TRIO_SIMPLIFIED_DIGIT_RE
            if config.output_mode == SIMPLIFIED_CHINESE_TARGET
            else TRIO_TRADITIONAL_DIGIT_RE
        )
        trio_allowance = min(
            len(TRIO_EN_RE.findall(source)),
            len(trio_target_pattern.findall(translation)),
        )
        extras["3"] -= min(extras["3"], trio_allowance)
        if extras["3"] == 0:
            del extras["3"]
    return not extras


def _numbers_present(text: str, numbers: Sequence[str]) -> bool:
    counts = Counter(numbers)
    available = _arabic_multiset(text)
    for number, needed in counts.items():
        if available[number] < needed:
            return False
    return True


def _identity_numbers(text: str, patterns: Sequence[re.Pattern[str]]) -> List[str]:
    numbers: List[str] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            for value in match.groups():
                if value:
                    numbers.append(value)
    return numbers


def _source_round_patterns(config: _RouteConfig) -> Tuple[re.Pattern[str], ...]:
    if config.en_us_source:
        return (ROUND_EN_RE,)
    return (ROUND_SC_RE, ROUND_CN_RE, ROUND_SIMPLIFIED_CN_RE)


def _target_round_patterns(config: _RouteConfig) -> Tuple[re.Pattern[str], ...]:
    patterns = (ROUND_ID_EN_RE, ROUND_ID_R_RE, ROUND_ID_CN_RE)
    if config.output_mode == SIMPLIFIED_CHINESE_TARGET:
        return (*patterns, ROUND_ID_SIMPLIFIED_CN_RE)
    return patterns


def _validate_round_numbers(
    source: str,
    translation: str,
    source_patterns: Sequence[re.Pattern[str]],
    config: _RouteConfig,
) -> bool:
    required = _identity_numbers(source, source_patterns)
    if not required:
        return True
    present = set(_identity_numbers(translation, _target_round_patterns(config)))
    return all(number in present for number in required)


def _validate_row_numbers(source: str, translation: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    required = _identity_numbers(source, patterns)
    if not required:
        return True
    present = set(_identity_numbers(translation, (ROW_ID_EN_RE, ROW_ID_CN_RE)))
    return all(number in present for number in required)


def _validate_totals(source: str, translation: str) -> bool:
    totals: List[str] = []
    totals.extend(TOTAL_EQUALS_RE.findall(source))
    totals.extend(TOTAL_PAREN_END_RE.findall(source))
    totals.extend(TOTAL_CN_RE.findall(source))
    if totals and not _numbers_present(translation, totals):
        return False
    return True


def _repeat_multipliers(
    text: str,
    patterns: Sequence[re.Pattern[str]],
) -> List[str]:
    return _identity_numbers(text, patterns)


def _validate_repeats(
    source: str,
    translation: str,
    config: _RouteConfig,
) -> bool:
    strict_repeat_markers = config.en_us_source
    source_patterns = (
        (REPEAT_PREFIX_RE, REPEAT_SUFFIX_RE)
        if strict_repeat_markers
        else (REPEAT_PREFIX_RE,)
    )
    multipliers = _repeat_multipliers(source, source_patterns)
    if not multipliers:
        return True
    if not strict_repeat_markers:
        return _numbers_present(translation, multipliers)
    present = Counter(
        _repeat_multipliers(
            translation,
            (REPEAT_PREFIX_RE, REPEAT_SUFFIX_RE, REPEAT_CHINESE_RE),
        )
    )
    return not (Counter(multipliers) - present)


def _measurement_fact_present(
    translation: str,
    number: str,
    canonical_unit: str,
    config: _RouteConfig,
) -> bool:
    aliases = MEASUREMENT_TARGET_ALIASES[config.output_mode][canonical_unit]
    unit_pattern = "|".join(
        rf"{re.escape(alias)}(?![A-Za-z])" if alias.isascii() else re.escape(alias)
        for alias in sorted(aliases, key=len, reverse=True)
    )
    return bool(
        re.search(
            rf"(?<!\d){re.escape(number)}(?!\d)\s*(?:{unit_pattern})",
            translation,
            re.IGNORECASE,
        )
    )


def _validate_measurements(source: str, translation: str, config: _RouteConfig) -> bool:
    for match in MEASURE_RE.finditer(source):
        number, unit = match.group(1), match.group(2).lower()
        if not _numbers_present(translation, [number]):
            return False
        canonical_unit = MEASUREMENT_UNIT_CANONICAL[unit]
        if not _measurement_fact_present(translation, number, canonical_unit, config):
            return False
    return True


def _digit_multiset_fields(source: str, translation: str) -> Dict[str, object]:
    source_counts = _arabic_multiset(source)
    translation_counts = _arabic_multiset(translation)
    return {
        "source_digit_multiset": dict(sorted(source_counts.items())),
        "translation_digit_multiset": dict(sorted(translation_counts.items())),
        "missing_digits": list((source_counts - translation_counts).elements()),
        "extra_digits": list((translation_counts - source_counts).elements()),
    }


def _round_identity_fields(
    source: str,
    translation: str,
    source_patterns: Sequence[re.Pattern[str]],
    target_patterns: Sequence[re.Pattern[str]],
) -> Dict[str, object]:
    required = _identity_numbers(source, source_patterns)
    present = sorted(set(_identity_numbers(translation, target_patterns)))
    return {
        "required_round_identities": required,
        "present_round_identities": present,
        "missing_round_identities": [number for number in required if number not in present],
    }


def _row_identity_fields(
    source: str,
    translation: str,
    source_patterns: Sequence[re.Pattern[str]],
) -> Dict[str, object]:
    required = _identity_numbers(source, source_patterns)
    present = sorted(set(_identity_numbers(translation, (ROW_ID_EN_RE, ROW_ID_CN_RE))))
    return {
        "required_row_identities": required,
        "present_row_identities": present,
        "missing_row_identities": [number for number in required if number not in present],
    }


def _total_fields(source: str, translation: str) -> Dict[str, object]:
    totals: List[str] = []
    totals.extend(TOTAL_EQUALS_RE.findall(source))
    totals.extend(TOTAL_PAREN_END_RE.findall(source))
    totals.extend(TOTAL_CN_RE.findall(source))
    required = Counter(totals)
    available = _arabic_multiset(translation)
    missing: List[str] = []
    for total, needed in required.items():
        if available[total] < needed:
            missing.extend([total] * (needed - available[total]))
    return {
        "required_totals": totals,
        "missing_totals": missing,
    }


def _repeat_fields(
    source: str,
    translation: str,
    config: _RouteConfig,
) -> Dict[str, object]:
    strict_repeat_markers = config.en_us_source
    source_patterns = (
        (REPEAT_PREFIX_RE, REPEAT_SUFFIX_RE)
        if strict_repeat_markers
        else (REPEAT_PREFIX_RE,)
    )
    multipliers = _repeat_multipliers(source, source_patterns)
    if strict_repeat_markers:
        present = _repeat_multipliers(
            translation,
            (REPEAT_PREFIX_RE, REPEAT_SUFFIX_RE, REPEAT_CHINESE_RE),
        )
        missing = list((Counter(multipliers) - Counter(present)).elements())
    else:
        present = list(_arabic_multiset(translation).elements())
        missing = list((Counter(multipliers) - Counter(present)).elements())
    return {
        "required_repeat_multipliers": multipliers,
        "present_repeat_multipliers": present,
        "missing_repeat_multipliers": missing,
    }


def _measurement_fields(
    source: str,
    translation: str,
    config: _RouteConfig,
) -> Dict[str, object]:
    measurements: List[Dict[str, str]] = []
    for match in MEASURE_RE.finditer(source):
        measurements.append(
            {
                "number": match.group(1),
                "unit": match.group(2).lower(),
            }
        )
    for match in MEASURE_RE.finditer(source):
        number, unit = match.group(1), match.group(2).lower()
        if not _numbers_present(translation, [number]):
            return {
                "measurement_facts": measurements,
                "failed_measurement_number": number,
                "failed_measurement_unit": unit,
                "measurement_failure": "number_missing",
            }
        canonical_unit = MEASUREMENT_UNIT_CANONICAL[unit]
        if canonical_unit == "cm":
            if _measurement_fact_present(translation, number, "inch", config):
                return {
                    "measurement_facts": measurements,
                    "failed_measurement_number": number,
                    "failed_measurement_unit": unit,
                    "measurement_failure": "unit_substituted_to_inch",
                }
        if not _measurement_fact_present(translation, number, canonical_unit, config):
            return {
                "measurement_facts": measurements,
                "failed_measurement_number": number,
                "failed_measurement_unit": unit,
                "measurement_failure": "unit_marker_missing",
            }
    return {"measurement_facts": measurements}


def _objective_validation_failure_fields(
    source: str,
    translation: str,
    config: _RouteConfig,
    failed_rule: str,
) -> Dict[str, object]:
    fields: Dict[str, object] = {"failed_rule": failed_rule}
    if failed_rule == "arabic_digit_multiset":
        fields.update(_digit_multiset_fields(source, translation))
    elif failed_rule == "round_identity":
        source_patterns = _source_round_patterns(config)
        fields.update(
            _round_identity_fields(
                source,
                translation,
                source_patterns,
                _target_round_patterns(config),
            )
        )
    elif failed_rule == "row_identity":
        source_patterns = (ROW_EN_RE,) if config.en_us_source else (ROW_CN_RE,)
        fields.update(_row_identity_fields(source, translation, source_patterns))
    elif failed_rule == "stitch_totals":
        fields.update(_total_fields(source, translation))
    elif failed_rule == "repeat_multiplier":
        fields.update(_repeat_fields(source, translation, config))
    elif failed_rule == "measurement_units":
        fields.update(_measurement_fields(source, translation, config))
    return fields


def _validation_diagnostic_excerpt(text: str) -> Tuple[str, bool]:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= VALIDATION_DIAGNOSTIC_EXCERPT_CHARS:
        return compact, False
    return compact[:VALIDATION_DIAGNOSTIC_EXCERPT_CHARS] + "…", True


def _validate_objective_facts(
    source: str,
    translation: str,
    config: _RouteConfig,
    *,
    diagnostic_logger: Optional[DiagnosticLogger] = None,
    source_segment_ids: Optional[Sequence[str]] = None,
) -> None:
    def fail(failed_rule: str) -> None:
        fields = _objective_validation_failure_fields(
            source,
            translation,
            config,
            failed_rule,
        )
        source_excerpt, source_truncated = _validation_diagnostic_excerpt(source)
        translation_excerpt, translation_truncated = _validation_diagnostic_excerpt(translation)
        fields["failed_source_excerpt"] = source_excerpt
        fields["failed_translation_excerpt"] = translation_excerpt
        fields["failed_source_excerpt_truncated"] = source_truncated
        fields["failed_translation_excerpt_truncated"] = translation_truncated
        if source_segment_ids is not None:
            fields["source_segment_ids"] = list(source_segment_ids)
        _log(diagnostic_logger, "objective_validation_failed", **fields)
        raise BroadTranslationError()

    if not translation.strip():
        fail("blank_translation")
    if not _validate_arabic_digit_multiset(source, translation, config):
        fail("arabic_digit_multiset")

    if config.en_us_source:
        if not _validate_round_numbers(source, translation, (ROUND_EN_RE,), config):
            fail("round_identity")
        if not _validate_row_numbers(source, translation, (ROW_EN_RE,)):
            fail("row_identity")
    else:
        if not _validate_round_numbers(
            source,
            translation,
            _source_round_patterns(config),
            config,
        ):
            fail("round_identity")
        if not _validate_row_numbers(source, translation, (ROW_CN_RE,)):
            fail("row_identity")

    if not _validate_totals(source, translation):
        fail("stitch_totals")
    if not _validate_repeats(source, translation, config):
        fail("repeat_multiplier")
    if not _validate_measurements(source, translation, config):
        fail("measurement_units")


def validate_semantic_units(
    units: Sequence[dict[str, Any]],
    segments: Sequence[Dict[str, str]],
    config: _RouteConfig,
    diagnostic_logger: Optional[DiagnosticLogger] = None,
) -> None:
    expected_ids = [segment["source_segment_id"] for segment in segments]
    _validate_id_coverage(units, expected_ids, diagnostic_logger=diagnostic_logger)
    source_by_id = {segment["source_segment_id"]: segment["text"] for segment in segments}
    for unit in units:
        source = "\n".join(source_by_id[item] for item in unit["source_segment_ids"])
        _validate_objective_facts(
            source,
            unit["translation"],
            config,
            diagnostic_logger=diagnostic_logger,
            source_segment_ids=unit["source_segment_ids"],
        )


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
    with urllib.request.urlopen(request, timeout=BROAD_TIMEOUT_SECONDS) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise _BroadResponseParsingError(
            "provider_envelope",
            "provider_response_not_object",
            expected_top_level_shape="object_with_output_array",
        )
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
    source_by_id = {segment["source_segment_id"]: segment["text"] for segment in segments}
    out: List[Dict[str, object]] = []
    for unit in semantic_units:
        ids = unit["source_segment_ids"]
        member_rows = [segment_row_by_id[source_id] for source_id in ids]
        original = "\n".join(source_by_id[source_id] for source_id in ids)
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
    segments, segment_rows = build_source_segments(rows)
    if not segments:
        return pd.DataFrame()

    route_terms = build_glossary(source_mode, output_mode)
    terms = select_request_glossary(route_terms, segments, config)
    _log(
        diagnostic_logger,
        "broad_glossary_scope",
        route_glossary_entry_count=len(route_terms),
        scoped_glossary_entry_count=len(terms),
        route_glossary_char_count=_glossary_char_count(route_terms),
        scoped_glossary_char_count=_glossary_char_count(terms),
    )
    prompt = build_prompt(segments, terms, config)
    api_key = _resolve_api_key(environ)
    caller = luna_caller or call_luna_once

    broad_start = time.perf_counter()
    _log(diagnostic_logger, "broad_translation_begin", visual_line_count=len(segments))
    luna_start = time.perf_counter()
    _log(
        diagnostic_logger,
        "ai_request_begin",
        call_ordinal=1,
        model=BROAD_MODEL,
        route="broad",
    )
    try:
        payload, luna_elapsed = caller(prompt, api_key)
        units = _parse_semantic_units(
            _parse_response_payload(payload),
            [segment["source_segment_id"] for segment in segments],
            diagnostic_logger=diagnostic_logger,
        )
        validate_semantic_units(
            units,
            segments,
            config,
            diagnostic_logger=diagnostic_logger,
        )
        result = adapt_semantic_units_to_line_df(units, segments, segment_rows)
        if profile_count is not None:
            profile_count("broad Luna translation calls", 1.0)
        if profile_add_time is not None:
            profile_add_time("broad Luna translation", luna_elapsed)
        _log(
            diagnostic_logger,
            "ai_request_end",
            elapsed_seconds=luna_elapsed,
            call_ordinal=1,
            model=BROAD_MODEL,
            route="broad",
            outcome="success",
        )
        _log(
            diagnostic_logger,
            "line_reconstruction_end",
            elapsed_seconds=time.perf_counter() - broad_start,
            visual_line_count=len(result),
            outcome="success",
        )
        return result
    except _BroadResponseParsingError as error:
        elapsed_seconds = time.perf_counter() - luna_start
        _log_response_parsing_failure(
            diagnostic_logger,
            error,
            elapsed_seconds,
            1,
        )
        _log(
            diagnostic_logger,
            "ai_request_end",
            elapsed_seconds=elapsed_seconds,
            call_ordinal=1,
            model=BROAD_MODEL,
            route="broad",
            outcome="validation_rejected",
        )
        raise BroadTranslationError() from None
    except BroadTranslationError:
        _log(
            diagnostic_logger,
            "ai_request_end",
            elapsed_seconds=time.perf_counter() - luna_start,
            call_ordinal=1,
            model=BROAD_MODEL,
            route="broad",
            outcome="validation_rejected",
        )
        raise
    except (
        TimeoutError,
        urllib.error.URLError,
        urllib.error.HTTPError,
        json.JSONDecodeError,
        ValueError,
        OSError,
        TypeError,
        AttributeError,
    ) as error:
        _log(
            diagnostic_logger,
            "ai_request_end",
            elapsed_seconds=time.perf_counter() - luna_start,
            call_ordinal=1,
            model=BROAD_MODEL,
            route="broad",
            outcome="provider_error",
            **_provider_failure_diagnostics(error),
        )
        raise BroadTranslationError() from None
