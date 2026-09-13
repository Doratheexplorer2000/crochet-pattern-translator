"""Cheap, conservative crochet relevance checks for cleaned OCR text."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass

import pandas as pd

from pattern_translator.engine import terminology


_TERM_COLUMNS = (
    "US_term",
    "US_term_alias",
    "US_abb",
    "US_abb1",
    "UK_term",
    "UK_term_alias",
    "UK_abb",
    "UK_abb1",
    "Chinese_term",
    "Chinese_term_alias",
    "Chinese_abb",
    "Japanese",
    "Japanese_alias",
)
_ABBREVIATION_COLUMNS = (
    "US_abb",
    "US_abb1",
    "UK_abb",
    "UK_abb1",
    "Chinese_abb",
)
_ROW_MARKER_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:r(?:nd|ow|ound)?\s*\d+|第?\s*\d+\s*[段行圈])"
)
_REPEAT_RE = re.compile(r"(?i)(?:[×x＊*]\s*\d+|repeat\b|重[複复覆]|繰り返)")
_COUNT_RE = re.compile(r"[（(]\s*\d{1,4}\s*(?:st(?:s|itches?)?|針|针|目)?\s*[)）]")
_COMPACT_SEQUENCE_RE = re.compile(
    r"(?i)(?:^|[\s:：,(（])(?:\d*\s*)?[xvtafe](?:\s*[,，+＋]\s*(?:\d*\s*)?[xvtafe]){2,}(?:$|[\s)）])"
)
_EXPLICIT_CROCHET_RE = re.compile(
    r"(?i)\bcrochet(?:ing)?\b|かぎ針|鉤針|鈎針|钩针|鈎織|鉤織|钩织"
)


@dataclass(frozen=True)
class CrochetRelevanceResult:
    evaluated: bool
    allowed: bool
    reason: str
    glossary_hit_count: int = 0
    structure_signal_count: int = 0
    explicit_domain_signal_count: int = 0

    def diagnostics(self) -> dict[str, object]:
        return asdict(self)


def _term_values(frame: pd.DataFrame) -> list[tuple[str, str]]:
    """Return active glossary values paired with their existing category."""
    active = terminology.get_active_search_df(frame)
    values: list[tuple[str, str]] = []
    seen: set[str] = set()
    for _, row in active.iterrows():
        category = terminology.norm_text(row.get("category", ""))
        for column in _TERM_COLUMNS:
            if column not in active.columns:
                continue
            raw = row.get(column, "")
            candidates = [raw, *terminology.split_aliases(raw)]
            if column.startswith("Chinese"):
                chinese_candidates = list(candidates)
                candidates.extend(
                    terminology.to_simplified(str(item))
                    for item in chinese_candidates
                )
            for candidate in candidates:
                value = unicodedata.normalize("NFKC", str(candidate or "")).strip()
                key = terminology.norm_text(value)
                if not key or key in seen:
                    continue
                seen.add(key)
                values.append((value, category))
    return values


def _term_matches(text: str, term: str) -> bool:
    normalized_term = unicodedata.normalize("NFKC", term).strip()
    if not normalized_term:
        return False
    if normalized_term.isascii():
        return bool(
            re.search(
                rf"(?i)(?<![A-Za-z0-9]){re.escape(normalized_term)}(?![A-Za-z0-9])",
                text,
            )
        )
    return normalized_term in text


def _has_counted_known_abbreviation(
    text: str,
    terminology_dataframe: pd.DataFrame,
) -> bool:
    active = terminology.get_active_search_df(terminology_dataframe)
    abbreviations: set[str] = set()
    for column in _ABBREVIATION_COLUMNS:
        if column not in active.columns:
            continue
        for raw in active[column]:
            for candidate in (raw, *terminology.split_aliases(raw)):
                if candidate is None or pd.isna(candidate):
                    continue
                value = unicodedata.normalize(
                    "NFKC", str(candidate or "")
                ).strip()
                if value:
                    abbreviations.add(value)
    if not abbreviations:
        return False
    alternatives = "|".join(
        re.escape(value)
        for value in sorted(abbreviations, key=lambda value: (-len(value), value))
    )
    return bool(
        re.search(
            rf"(?i)(?<![A-Za-z0-9])\d+\s*(?:{alternatives})(?![A-Za-z0-9])",
            text,
        )
    )


def evaluate_crochet_relevance(
    clean_text: str,
    terminology_dataframe: pd.DataFrame,
) -> CrochetRelevanceResult:
    """Reject only readable text with no credible crochet-domain evidence.

    This gate is deliberately not a strict pattern validator. Single-letter
    notation is counted only through a compact sequence, a count paired with an
    active glossary abbreviation, or another structural signal.
    """
    text = unicodedata.normalize("NFKC", str(clean_text or "")).strip()
    if not text:
        return CrochetRelevanceResult(False, True, "no_usable_text_existing_path")

    alphanumeric_count = len(re.findall(r"[A-Za-z0-9\u3400-\u9fff]", text))
    explicit_count = len(_EXPLICIT_CROCHET_RE.findall(text))
    structure_signals = sum(
        bool(pattern.search(text))
        for pattern in (_ROW_MARKER_RE, _REPEAT_RE, _COUNT_RE, _COMPACT_SEQUENCE_RE)
    )
    structure_signals += int(
        _has_counted_known_abbreviation(text, terminology_dataframe)
    )

    hits: set[str] = set()
    for term, category in _term_values(terminology_dataframe):
        key = terminology.norm_text(term)
        # Bare one-letter notation is far too common outside patterns. Its
        # legitimate use is represented by the compact-structure signal above.
        if len(key) <= 1 or (term.isascii() and len(key) <= 2):
            continue
        # Generic instruction words require corroboration; retaining them as
        # evidence still lets prose pages pass without creating a second lexicon.
        if _term_matches(text, term):
            hits.add(f"{category}:{key}")

    glossary_hit_count = len(hits)
    if alphanumeric_count < 12:
        allowed = bool(explicit_count or structure_signals or glossary_hit_count)
        reason = (
            "ambiguous_sparse_text"
            if allowed
            else "readable_text_without_crochet_evidence"
        )
    elif explicit_count:
        reason = "explicit_crochet_language"
        allowed = True
    elif glossary_hit_count >= 2:
        reason = "multiple_glossary_signals"
        allowed = True
    elif glossary_hit_count >= 1 and structure_signals >= 1:
        reason = "glossary_and_structure"
        allowed = True
    elif structure_signals >= 2:
        reason = "multiple_pattern_structure_signals"
        allowed = True
    elif glossary_hit_count == 1 or structure_signals == 1:
        reason = "ambiguous_weak_evidence"
        allowed = True
    else:
        reason = "readable_text_without_crochet_evidence"
        allowed = False

    return CrochetRelevanceResult(
        True,
        allowed,
        reason,
        glossary_hit_count=glossary_hit_count,
        structure_signal_count=structure_signals,
        explicit_domain_signal_count=explicit_count,
    )
