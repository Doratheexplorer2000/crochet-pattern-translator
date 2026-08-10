"""Conservative GPT fallback for unresolved crochet instruction prose."""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping, Optional, Tuple, Union

import pandas as pd

from pattern_translator.engine import terminology


MODEL = "gpt-5-nano"
DEFAULT_TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True)
class TitleTranslationRequest:
    subject: str


ProviderInput = Union[str, TitleTranslationRequest]
Provider = Callable[[str, ProviderInput, str, str], str]


class _DiagnosedMalformedResponse(ValueError):
    """Internal marker for a malformed provider result already safely diagnosed."""

_TRUE_VALUES = {"1", "true", "yes", "on"}
_ENGLISH_OUTPUTS = {"English — US", "English — UK", "English US terms", "English UK terms"}
_CHINESE_OUTPUTS = {"Traditional Chinese", "Simplified Chinese"}
_DESIGNER_SHORTHAND_MARKERS = ("not yet confirmed", "交叉x", "交叉×")
_KNOWN_ABBREVIATIONS = {
    "sc", "dc", "hdc", "tr", "inc", "dec", "mr", "blo", "flo", "ch", "st", "sts", "fo", "slst", "sl st",
}

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_ENGLISH_WORD_RE = re.compile(r"[A-Za-z]{3,}")
_ORDINARY_SINGLE_WORD_RE = re.compile(r"[A-Z]?[a-z]{2,}")
_ROUND_RE = re.compile(r"\b(?:R|Rnd|Row)\s*\d+(?:\s*[-–—~～〜－]\s*\d+)?\s*[:：]?", re.IGNORECASE)
_REPEAT_RE = re.compile(r"(?:\bx\s*\d+\b|[×*]\s*\d+)", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?(?:\s*[-–—~～〜－]\s*\d+)?")
_BRACKET_RE = re.compile(r"[()（）\[\]{}]")
_ABBREVIATION_RE = re.compile(r"\b(?:sl\s*st|slst|sc|dc|hdc|tr|inc|dec|mr|blo|flo|ch|sts?|fo)\b", re.IGNORECASE)
_UNKNOWN_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,7}\b")
_PLACEHOLDER_RE = re.compile(r"__ciq[a-z]+__")
_DEBUG_OUTCOMES = {
    "not_eligible",
    "no_api_key",
    "called_accepted",
    "called_no_improvement",
    "validation_rejected",
    "timeout",
    "api_error",
    "malformed_response",
    "skipped_designer_shorthand",
    "skipped_resolved",
}


def is_fallback_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    values = os.environ if environ is None else environ
    return str(values.get("PATTERN_LLM_FALLBACK_ENABLED", "")).strip().lower() in _TRUE_VALUES


def is_debug_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    values = os.environ if environ is None else environ
    return str(values.get("PATTERN_LLM_DEBUG", "")).strip().lower() in _TRUE_VALUES


def _debug_outcome(outcome: str, environ: Optional[Mapping[str, str]] = None) -> None:
    if outcome not in _DEBUG_OUTCOMES or not is_debug_enabled(environ):
        return
    print(f"[pattern_llm] outcome={outcome}", file=sys.stderr, flush=True)


def _meaningful_english_words(text: str) -> List[str]:
    ignored = {term.replace(" ", "") for term in _KNOWN_ABBREVIATIONS}
    return [word for word in _ENGLISH_WORD_RE.findall(text) if word.lower().replace(" ", "") not in ignored]


def _has_context_backed_single_unresolved_word(source: str, deterministic: str) -> bool:
    unresolved = _meaningful_english_words(deterministic)
    if len(unresolved) != 1 or not _CJK_RE.search(deterministic):
        return False

    word = unresolved[0]
    if not _ORDINARY_SINGLE_WORD_RE.fullmatch(word):
        return False
    if not re.search(rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", deterministic):
        return False

    source_words = _meaningful_english_words(source)
    return len(source_words) >= 2 and any(
        source_word.lower() != word.lower() for source_word in source_words
    )


def should_use_llm(source: str, deterministic: str, output_mode: str) -> bool:
    """Return true only for clear unresolved or mixed ordinary-language content."""
    source = str(source or "").strip()
    deterministic = str(deterministic or "").strip()
    if not source or not deterministic or output_mode == "Japanese":
        return False
    lowered = (source + " " + deterministic).lower()
    if any(marker.lower() in lowered for marker in _DESIGNER_SHORTHAND_MARKERS):
        return False

    if output_mode in _ENGLISH_OUTPUTS:
        unresolved = len(_CJK_RE.findall(deterministic))
        return unresolved >= 2 and len(source) >= 4
    if output_mode in _CHINESE_OUTPUTS:
        unresolved = _meaningful_english_words(deterministic)
        return len(unresolved) >= 2 or _has_context_backed_single_unresolved_word(
            source, deterministic
        )
    return False


def _skip_outcome(source: str, deterministic: str, output_mode: str) -> str:
    source = str(source or "").strip()
    deterministic = str(deterministic or "").strip()
    lowered = (source + " " + deterministic).lower()
    if any(marker.lower() in lowered for marker in _DESIGNER_SHORTHAND_MARKERS):
        return "skipped_designer_shorthand"
    if output_mode in _ENGLISH_OUTPUTS and not _CJK_RE.search(deterministic):
        return "skipped_resolved"
    if output_mode in _CHINESE_OUTPUTS and not _meaningful_english_words(deterministic):
        return "skipped_resolved"
    return "not_eligible"


def _placeholder_name(index: int) -> str:
    letters = ""
    value = index
    while True:
        letters = chr(ord("a") + value % 26) + letters
        value = value // 26 - 1
        if value < 0:
            return f"__ciq{letters}__"


def _target_terms(df: pd.DataFrame, output_mode: str) -> List[str]:
    if df is None or df.empty:
        return []
    terms: List[str] = []
    active = terminology.get_active_search_df(df)
    for column in terminology.get_source_columns(output_mode):
        if column not in active.columns:
            continue
        for value in active[column].fillna(""):
            raw = str(value).strip()
            if raw:
                terms.append(terminology.to_simplified(raw) if output_mode == "Simplified Chinese" else raw)
            aliases = terminology.split_aliases(value)
            if output_mode == "Simplified Chinese":
                terms.extend(terminology.to_simplified(alias) for alias in aliases)
            else:
                terms.extend(aliases)
    terms.extend(_KNOWN_ABBREVIATIONS)
    return sorted(set(terms), key=len, reverse=True)


def protect_authoritative_content(text: str, df: pd.DataFrame, output_mode: str) -> Tuple[str, Dict[str, str]]:
    replacements: Dict[str, str] = {}

    def protect_match(match: re.Match) -> str:
        key = _placeholder_name(len(replacements))
        replacements[key] = match.group(0)
        return key

    protected = str(text or "")
    for pattern in (_ROUND_RE, _REPEAT_RE, _UNKNOWN_TOKEN_RE):
        protected = pattern.sub(protect_match, protected)

    for term in _target_terms(df, output_mode):
        if term not in protected:
            continue
        if term.isascii() and term.replace(" ", "").isalnum():
            pattern = re.compile(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", re.IGNORECASE)
            protected = pattern.sub(protect_match, protected)
        else:
            protected = re.sub(re.escape(term), protect_match, protected)

    for pattern in (_NUMBER_RE, _BRACKET_RE):
        protected = pattern.sub(protect_match, protected)
    return protected, replacements


def _extract_output_text(response: dict, http_status: object = None) -> str:
    output_text_present = False
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                output_text_present = True
                text = str(content.get("text", "")).strip()
                if text:
                    return text
    _debug_response_structure(
        response,
        http_status=http_status,
        failure_stage="parsed_no_output_text",
        output_text_present=output_text_present,
    )
    return ""


def _safe_debug_atom(value: object) -> str:
    atom = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return atom[:64] or "unavailable"


def _debug_response_structure(
    response: Optional[dict],
    *,
    http_status: object = None,
    json_parsed: Optional[bool] = True,
    failure_stage: str = "unknown",
    output_text_present: bool = False,
) -> None:
    if not is_debug_enabled():
        return
    payload = response if isinstance(response, dict) else {}
    output = payload.get("output", [])
    output = output if isinstance(output, list) else []
    output_types: List[str] = []
    content_types: List[str] = []
    for item in output:
        if not isinstance(item, dict):
            output_types.append("invalid")
            continue
        output_types.append(_safe_debug_atom(item.get("type")))
        content = item.get("content", [])
        if not isinstance(content, list):
            content_types.append("invalid")
            continue
        for part in content:
            content_types.append(
                _safe_debug_atom(part.get("type")) if isinstance(part, dict) else "invalid"
            )
    incomplete = payload.get("incomplete_details")
    incomplete_reason = incomplete.get("reason") if isinstance(incomplete, dict) else None
    fields = {
        "failure_stage": _safe_debug_atom(failure_stage),
        "json_parsed": "unavailable" if json_parsed is None else str(json_parsed).lower(),
        "http_status": _safe_debug_atom(http_status),
        "response_status": _safe_debug_atom(payload.get("status")),
        "incomplete_reason": _safe_debug_atom(incomplete_reason),
        "output_item_count": len(output),
        "output_item_types": ",".join(output_types) or "none",
        "content_types": ",".join(content_types) or "none",
        "output_text_present": str(output_text_present).lower(),
        "output_text_nonempty": "false",
    }
    details = " ".join(f"{key}={value}" for key, value in fields.items())
    print(f"[pattern_llm] response_structure {details}", file=sys.stderr, flush=True)


def create_openai_provider(api_key: str, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> Provider:
    """Create a one-attempt Responses API provider without exposing its key."""
    def translate(previous: str, current: ProviderInput, following: str, target: str) -> str:
        previous_context = previous or "[none]"
        following_context = following or "[none]"
        if isinstance(current, TitleTranslationRequest):
            prompt = (
                f"Translate the subject of a crochet pattern title into {target}. "
                "Classify it as ordinary_descriptive_noun or brand_or_proper_name. "
                "Translate an ordinary descriptive noun; preserve a genuine brand/proper name unchanged. "
                "Title Case alone does not make a word a proper name. "
                "Return JSON only with exactly these keys: classification, translated_or_preserved_text.\n"
                f"SUBJECT: {current.subject}"
            )
        else:
            prompt = (
                f"Translate only CURRENT into {target}. This is crochet pattern text. "
                "Opaque __ciq...__ tokens are authoritative: copy each exactly once and unchanged. "
                "Translate ordinary prose, including descriptive nouns in pattern titles and headings. "
                "Title Case alone does not make a word a proper name; normally translate title subjects such as animals, plants, foods, objects, body parts, colours, and materials. "
                "Preserve genuine brand names, designer names, usernames, product names, and contextually clear proper names. "
                "Do not repair OCR, invent meanings for unknown crochet abbreviations or designer shorthand, change crochet terminology, or add instructions. "
                "PREVIOUS and NEXT are context only. Return only the translated CURRENT line.\n"
                f"PREVIOUS: {previous_context}\nCURRENT: {current}\nNEXT: {following_context}"
            )
        failure_stage = "request_build"
        http_status = None
        try:
            request = urllib.request.Request(
                "https://api.openai.com/v1/responses",
                data=json.dumps({
                    "model": MODEL,
                    "reasoning": {"effort": "minimal"},
                    "input": prompt,
                    "max_output_tokens": 180,
                }).encode("utf-8"),
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                method="POST",
            )
            failure_stage = "http_open"
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                http_status = getattr(response, "status", None)
                failure_stage = "json_parse"
                payload = json.load(response)
                failure_stage = "extract_output"
                text = _extract_output_text(payload, http_status=http_status)
                if not text:
                    raise _DiagnosedMalformedResponse()
                return text
        except _DiagnosedMalformedResponse:
            raise
        except ValueError as error:
            _debug_response_structure(
                None,
                http_status=http_status,
                json_parsed=False if failure_stage == "json_parse" else None,
                failure_stage=f"{failure_stage}_value_error",
            )
            raise _DiagnosedMalformedResponse() from error

    return translate


def get_openai_provider_from_env(environ: Optional[Mapping[str, str]] = None) -> Optional[Provider]:
    values = os.environ if environ is None else environ
    if not is_fallback_enabled(values):
        return None
    api_key = str(values.get("OPENAI_API_KEY", "")).strip()
    return create_openai_provider(api_key) if api_key else None


def _restore_if_valid(raw: str, protected: str, deterministic: str, replacements: Dict[str, str]) -> Optional[str]:
    if not raw or not raw.strip():
        return None
    placeholders = _PLACEHOLDER_RE.findall(raw)
    expected = _PLACEHOLDER_RE.findall(protected)
    if placeholders != expected:
        return None
    if re.search(r"\d|[()（）\[\]{}]", _PLACEHOLDER_RE.sub("", raw)):
        return None

    restored = raw.strip()
    for key, value in replacements.items():
        restored = restored.replace(key, value)
    if not restored:
        return None

    baseline_abbreviations = {value.lower().replace(" ", "") for value in _ABBREVIATION_RE.findall(deterministic)}
    result_abbreviations = {value.lower().replace(" ", "") for value in _ABBREVIATION_RE.findall(restored)}
    if result_abbreviations - baseline_abbreviations:
        return None
    return restored


def _extract_title_subject(protected: str) -> Optional[str]:
    subject = _PLACEHOLDER_RE.sub("", str(protected or "")).strip()
    if not subject or not re.fullmatch(r"[A-Za-z][A-Za-z' -]{0,79}", subject):
        return None
    return subject


def _parse_title_result(raw: str, subject: str) -> Optional[str]:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or set(payload) != {
        "classification", "translated_or_preserved_text"
    }:
        return None

    classification = payload.get("classification")
    translated = payload.get("translated_or_preserved_text")
    if classification not in {"ordinary_descriptive_noun", "brand_or_proper_name"}:
        return None
    if not isinstance(translated, str) or not translated.strip():
        return None
    translated = translated.strip()
    if classification == "brand_or_proper_name" and translated != subject:
        return None
    return translated


def _unwrap_outer_parentheses(text: str) -> Tuple[str, Optional[Tuple[str, str]]]:
    value = str(text or "").strip()
    pairs = {"(": ")", "（": "）"}
    opening = value[:1]
    closing = pairs.get(opening)
    if not closing or not value.endswith(closing):
        return value, None

    depth = 0
    for position, character in enumerate(value):
        if character in pairs:
            depth += 1
        elif character in pairs.values():
            depth -= 1
            if depth == 0 and position != len(value) - 1:
                return value, None
        if depth < 0:
            return value, None
    if depth != 0:
        return value, None

    inner = value[1:-1].strip()
    return (inner, (opening, closing)) if inner else (value, None)


def apply_llm_fallback(
    source: str,
    deterministic: str,
    previous: str,
    following: str,
    output_mode: str,
    df: pd.DataFrame,
    provider: Optional[Provider],
    title_context: bool = False,
) -> str:
    """Return a validated improvement or the unchanged deterministic result."""
    if not should_use_llm(source, deterministic, output_mode):
        _debug_outcome(_skip_outcome(source, deterministic, output_mode))
        return deterministic
    if provider is None:
        outcome = "no_api_key" if is_fallback_enabled() else "not_eligible"
        _debug_outcome(outcome)
        return deterministic
    llm_input, outer_parentheses = _unwrap_outer_parentheses(deterministic)
    protected, replacements = protect_authoritative_content(llm_input, df, output_mode)
    title_subject = _extract_title_subject(protected) if title_context else None
    failure_stage = "provider_call"
    try:
        provider_input: ProviderInput = (
            TitleTranslationRequest(title_subject) if title_subject else protected
        )
        raw = provider(previous, provider_input, following, output_mode)
        if not raw or not raw.strip():
            _debug_response_structure(
                None,
                json_parsed=None,
                failure_stage="provider_empty_result",
            )
            _debug_outcome("malformed_response")
            return deterministic
        failure_stage = "validation"
        candidate = raw
        if title_subject:
            translated_subject = _parse_title_result(raw, title_subject)
            if translated_subject is None:
                _debug_outcome("validation_rejected")
                return deterministic
            candidate = protected.replace(title_subject, translated_subject, 1)
        restored = _restore_if_valid(candidate, protected, llm_input, replacements)
        if restored is None:
            _debug_outcome("validation_rejected")
            return deterministic
        if outer_parentheses is not None:
            restored = f"{outer_parentheses[0]}{restored}{outer_parentheses[1]}"
        outcome = "called_no_improvement" if restored.strip() == deterministic.strip() else "called_accepted"
        _debug_outcome(outcome)
        return restored
    except TimeoutError:
        _debug_outcome("timeout")
        return deterministic
    except urllib.error.URLError:
        _debug_outcome("api_error")
        return deterministic
    except _DiagnosedMalformedResponse:
        _debug_outcome("malformed_response")
        return deterministic
    except ValueError:
        _debug_response_structure(
            None,
            json_parsed=None,
            failure_stage=f"{failure_stage}_value_error",
        )
        _debug_outcome("malformed_response")
        return deterministic
    except OSError:
        _debug_outcome("api_error")
        return deterministic
    except Exception:
        _debug_outcome("api_error")
        return deterministic
