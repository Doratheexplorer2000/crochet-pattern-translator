"""Conservative GPT fallback for unresolved crochet instruction prose."""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping, Optional, Tuple, Union

import pandas as pd

from pattern_translator.engine import terminology


GENERAL_MODEL = "gpt-5.6-luna"
TITLE_MODEL = "gpt-5.6-luna"
GENERAL_REASONING = "low"
TITLE_REASONING = "low"
GENERAL_MAX_OUTPUT_TOKENS = 400
TITLE_MAX_OUTPUT_TOKENS = 180
DEFAULT_TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True)
class TitleTranslationRequest:
    subject: str


ProviderInput = Union[str, TitleTranslationRequest]
Provider = Callable[[str, ProviderInput, str, str], str]
DiagnosticLogger = Callable[..., None]


@dataclass(frozen=True)
class _ProviderDiagnosticContext:
    logger: DiagnosticLogger
    call_ordinal: int
    model: str
    route: str


_PROVIDER_DIAGNOSTIC_CONTEXT: ContextVar[Optional[_ProviderDiagnosticContext]] = (
    ContextVar("pattern_llm_provider_diagnostic_context", default=None)
)


class _DiagnosedMalformedResponse(ValueError):
    """Internal marker for a malformed provider result already safely diagnosed."""


def _emit_timing(phase: str, **fields: object) -> None:
    context = _PROVIDER_DIAGNOSTIC_CONTEXT.get()
    if context is None:
        return
    try:
        context.logger(
            phase,
            call_ordinal=context.call_ordinal,
            model=context.model,
            route=context.route,
            **fields,
        )
    except Exception:
        pass

_TRUE_VALUES = {"1", "true", "yes", "on"}
_ENGLISH_OUTPUTS = {"English — US", "English — UK", "English US terms", "English UK terms"}
_CHINESE_OUTPUTS = {"Traditional Chinese", "Simplified Chinese"}
_CHINESE_SOURCE_MODES = {"Traditional Chinese", "Simplified Chinese"}
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
_LATIN_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]*(?:[-'’][A-Za-z0-9]+)*)(?![A-Za-z0-9])"
)
_URL_OR_DOMAIN_RE = re.compile(
    r"(?:https?://|www\.|(?<![A-Za-z0-9])(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,24}\b)",
    re.IGNORECASE,
)
_PAGE_LABEL_RE = re.compile(
    r"(?:[-–—]?\s*\d+\s*[-–—]?|(?:第\s*)?\d+\s*[頁页]|[頁页]\s*\d+)",
    re.IGNORECASE,
)
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
AI_TERMINAL_REASON_CODES = frozenset({
    "success",
    "no_improvement",
    "validation_rejected_residual_cjk",
    "validation_rejected_placeholder_contract",
    "validation_rejected_other",
    "timeout",
    "network_error",
    "malformed_response",
    "empty_response",
    "provider_error",
})


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


def should_use_llm(
    source: str,
    deterministic: str,
    output_mode: str,
    source_mode: Optional[str] = None,
) -> bool:
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
        if _PAGE_LABEL_RE.fullmatch(source) or _PAGE_LABEL_RE.fullmatch(deterministic):
            return False
        if unresolved >= 2:
            return len(source) >= 4
        if unresolved != 1 or source_mode not in _CHINESE_SOURCE_MODES:
            return False
        if _URL_OR_DOMAIN_RE.search(source) or _URL_OR_DOMAIN_RE.search(deterministic):
            return False
        return True
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


def structural_terminology_view(
    index: Dict[str, int], df: pd.DataFrame
) -> Tuple[Dict[str, int], pd.DataFrame]:
    """Exclude historical ordinary-prose rows from the Luna-facing terminology view."""
    if df is None or df.empty or "category" not in df.columns:
        return dict(index), df
    categories = df["category"].fillna("").astype(str).map(terminology.norm_text)
    structural_df = df[categories != "pattern_instruction"].copy()
    retained_rows = set(structural_df.index)
    structural_index = {
        term: row_index for term, row_index in index.items() if row_index in retained_rows
    }
    return structural_index, structural_df


def build_translation_scope_context(
    lines: List[str], df: pd.DataFrame, output_mode: str
) -> str:
    """Build compact semantic clues once from the OCR lines in the requested scope."""
    fragments: List[str] = []
    seen = set()
    for line in lines:
        protected, _ = protect_authoritative_content(line, df, output_mode)
        remainder = _PLACEHOLDER_RE.sub(" ", protected)
        remainder = re.sub(r"\b(?:R|Rnd|Round|Row)\s*[:：]?", " ", remainder, flags=re.I)
        remainder = re.sub(r"\b(?:sc|dc|hdc|tr|inc|dec|mr|blo|flo|ch|sts?|fo|slst)\b", " ", remainder, flags=re.I)
        remainder = re.sub(r"[\d×*]+", " ", remainder)
        remainder = re.sub(r"(?:重複|重复|針|针|次)", " ", remainder)
        for fragment in re.split(r"[|,，;；:：/\\]+", remainder):
            compact = re.sub(r"[()（）\[\]{}<>]", " ", fragment)
            compact = re.sub(r"\s+", " ", compact).strip(" .。-_~")
            if not compact:
                continue
            english_words = re.findall(r"[A-Za-z]{3,}", compact)
            cjk_runs = re.findall(r"[\u3400-\u9fff]{2,}", compact)
            if not english_words and not cjk_runs:
                continue
            key = compact.casefold()
            if key in seen:
                continue
            seen.add(key)
            fragments.append(compact)
    return " | ".join(fragments)


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
    def translate(semantic_context: str, current: ProviderInput, _following: str, target: str) -> str:
        is_title_request = isinstance(current, TitleTranslationRequest)
        if is_title_request:
            prompt = (
                f"You are translating the subject of a crochet pattern title into {target}. "
                "Classify the supplied subject as either an ordinary descriptive noun or a genuine brand/proper name. "
                "Translate an ordinary descriptive noun; preserve a genuine brand/proper name unchanged. "
                "Title Case alone does not make a word a proper name. "
                "Return JSON only with exactly these keys: classification, translated_or_preserved_text. "
                "Use classification ordinary_descriptive_noun or brand_or_proper_name.\n"
                f"SUBJECT: {current.subject}"
            )
        else:
            prompt = (
                "DOMAIN: crochet pattern\n"
                "INSTRUCTION: Interpret ordinary words according to crochet-pattern context. "
                "When context supports it, interpret object, part, and material words as components "
                f"of the item being crocheted. Translate only CURRENT LINE into {target}. "
                "PATTERN CONTEXT contains semantic clues only: do not copy context words into the output "
                "unless they belong to CURRENT LINE. Preserve every opaque __ciq...__ placeholder exactly "
                "once and unchanged. Do not repair OCR, invent crochet terminology, or reinterpret designer "
                "shorthand. Return only the translated CURRENT LINE.\n"
                f"PATTERN CONTEXT: {semantic_context or '[none]'}\n"
                f"CURRENT LINE: {current}"
            )
        failure_stage = "request_build"
        http_status = None
        try:
            request = urllib.request.Request(
                "https://api.openai.com/v1/responses",
                data=json.dumps({
                    "model": TITLE_MODEL if is_title_request else GENERAL_MODEL,
                    "reasoning": {"effort": TITLE_REASONING if is_title_request else GENERAL_REASONING},
                    "input": prompt,
                    "max_output_tokens": TITLE_MAX_OUTPUT_TOKENS if is_title_request else GENERAL_MAX_OUTPUT_TOKENS,
                }).encode("utf-8"),
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                method="POST",
            )
            failure_stage = "http_open"
            http_open_start = time.perf_counter()
            _emit_timing("http_open_begin")
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                http_status = getattr(response, "status", None)
                _emit_timing(
                    "http_headers_received",
                    elapsed_seconds=time.perf_counter() - http_open_start,
                    outcome="success",
                )
                failure_stage = "json_parse"
                response_parse_start = time.perf_counter()
                payload = json.load(response)
                _emit_timing(
                    "response_parse_end",
                    elapsed_seconds=time.perf_counter() - response_parse_start,
                    outcome="success",
                )
                failure_stage = "extract_output"
                text = _extract_output_text(payload, http_status=http_status)
                if not text:
                    raise _DiagnosedMalformedResponse()
                return text
        except _DiagnosedMalformedResponse:
            raise
        except ValueError as error:
            if failure_stage == "json_parse":
                _emit_timing(
                    "response_parse_end",
                    elapsed_seconds=time.perf_counter() - response_parse_start,
                    outcome="parse_error",
                )
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


def _restore_with_reason(
    raw: str,
    protected: str,
    deterministic: str,
    replacements: Dict[str, str],
) -> Tuple[Optional[str], str]:
    if not raw or not raw.strip():
        return None, "empty_response"
    placeholders = _PLACEHOLDER_RE.findall(raw)
    expected = _PLACEHOLDER_RE.findall(protected)
    if placeholders != expected:
        return None, "validation_rejected_placeholder_contract"
    if re.search(r"\d|[()（）\[\]{}]", _PLACEHOLDER_RE.sub("", raw)):
        return None, "validation_rejected_placeholder_contract"

    restored = raw.strip()
    for key, value in replacements.items():
        restored = restored.replace(key, value)
    if not restored:
        return None, "validation_rejected_other"

    baseline_abbreviations = {value.lower().replace(" ", "") for value in _ABBREVIATION_RE.findall(deterministic)}
    result_abbreviations = {value.lower().replace(" ", "") for value in _ABBREVIATION_RE.findall(restored)}
    if result_abbreviations - baseline_abbreviations:
        return None, "validation_rejected_other"
    return restored, "success"


def _restore_if_valid(raw: str, protected: str, deterministic: str, replacements: Dict[str, str]) -> Optional[str]:
    restored, _reason = _restore_with_reason(
        raw,
        protected,
        deterministic,
        replacements,
    )
    return restored


def _has_unsupported_latin_output(
    candidate: str, source: str, deterministic: str, output_mode: str
) -> bool:
    """Reject new Latin/alphanumeric tokens when Latin is not the target script."""
    if output_mode in _ENGLISH_OUTPUTS:
        return False
    if output_mode not in _CHINESE_OUTPUTS and output_mode != "Japanese":
        return False

    def tokens(text: str) -> set:
        return {match.group(1).casefold() for match in _LATIN_TOKEN_RE.finditer(text)}

    authorised = tokens(source) | tokens(deterministic)
    authorised.update(term.replace(" ", "").casefold() for term in _KNOWN_ABBREVIATIONS)
    return bool(tokens(candidate) - authorised)


def _extract_title_subject(protected: str) -> Optional[str]:
    subject = _PLACEHOLDER_RE.sub("", str(protected or "")).strip()
    if not subject or not re.fullmatch(r"[A-Za-z][A-Za-z' -]{0,79}", subject):
        return None
    return subject


def _single_embedded_prose_span(
    protected: str,
    output_mode: str,
    source_mode: Optional[str] = None,
) -> Optional[Tuple[int, int, str]]:
    """Return one unresolved prose span surrounded by protected structure."""
    placeholder_matches = list(_PLACEHOLDER_RE.finditer(protected))
    if not placeholder_matches:
        return None

    spans: List[Tuple[int, int, str]] = []
    boundaries = [(0, placeholder_matches[0].start())]
    boundaries.extend(
        (left.end(), right.start())
        for left, right in zip(placeholder_matches, placeholder_matches[1:])
    )
    boundaries.append((placeholder_matches[-1].end(), len(protected)))

    for start, end in boundaries:
        raw = protected[start:end]
        leading = len(raw) - len(raw.lstrip(" \t\r\n,，;；:："))
        trailing = len(raw) - len(raw.rstrip(" \t\r\n,，;；:："))
        prose_start = start + leading
        prose_end = end - trailing
        if prose_start >= prose_end:
            continue
        prose = protected[prose_start:prose_end]
        if output_mode in _ENGLISH_OUTPUTS:
            cjk_matches = list(_CJK_RE.finditer(prose))
            unresolved = len(cjk_matches) >= 2
            if unresolved:
                prose_start += cjk_matches[0].start()
                prose_end = prose_start + cjk_matches[-1].end() - cjk_matches[0].start()
                prose = protected[prose_start:prose_end]
        elif output_mode in _CHINESE_OUTPUTS:
            ignored = {term.replace(" ", "") for term in _KNOWN_ABBREVIATIONS}
            word_matches = [
                match
                for match in _ENGLISH_WORD_RE.finditer(prose)
                if match.group(0).lower().replace(" ", "") not in ignored
            ]
            unresolved = bool(word_matches)
            if unresolved:
                prose_start += word_matches[0].start()
                prose_end = prose_start + word_matches[-1].end() - word_matches[0].start()
                prose = protected[prose_start:prose_end]
        else:
            unresolved = False
        if unresolved:
            spans.append((prose_start, prose_end, prose))

    if len(spans) != 1:
        return None
    selected = spans[0]
    if output_mode in _ENGLISH_OUTPUTS and source_mode in _CHINESE_SOURCE_MODES:
        if any(
            match.start() < selected[0] or match.end() > selected[1]
            for match in _CJK_RE.finditer(protected)
        ):
            return None
    return selected


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
    semantic_context: Optional[str] = None,
    llm_input_text: Optional[str] = None,
    llm_df: Optional[pd.DataFrame] = None,
    diagnostic_logger: Optional[DiagnosticLogger] = None,
    call_ordinal: Optional[int] = None,
    source_mode: Optional[str] = None,
) -> str:
    """Return a validated improvement or the unchanged deterministic result."""
    candidate_input = deterministic if llm_input_text is None else llm_input_text
    if not should_use_llm(source, candidate_input, output_mode, source_mode):
        _debug_outcome(_skip_outcome(source, candidate_input, output_mode))
        return deterministic
    if provider is None:
        outcome = "no_api_key" if is_fallback_enabled() else "not_eligible"
        _debug_outcome(outcome)
        return deterministic
    llm_input, outer_parentheses = _unwrap_outer_parentheses(candidate_input)
    protection_df = df if llm_df is None else llm_df
    protected, replacements = protect_authoritative_content(llm_input, protection_df, output_mode)
    title_subject = _extract_title_subject(protected) if title_context else None
    embedded_prose = (
        None
        if title_subject
        else _single_embedded_prose_span(protected, output_mode, source_mode)
    )
    route = "title" if title_subject else "general"
    model = TITLE_MODEL if title_subject else GENERAL_MODEL
    provider_context_token = None
    ai_request_started = time.perf_counter()
    ai_request_finished = False

    def finish_ai_request(
        outcome: str,
        reason: str,
        deterministic_fallback_returned: bool,
    ) -> None:
        nonlocal ai_request_finished
        if ai_request_finished or diagnostic_logger is None or call_ordinal is None:
            return
        ai_request_finished = True
        try:
            diagnostic_logger(
                "ai_request_end",
                elapsed_seconds=time.perf_counter() - ai_request_started,
                call_ordinal=call_ordinal,
                model=model,
                route=route,
                outcome=outcome,
                reason=reason,
                deterministic_fallback_returned=deterministic_fallback_returned,
                source_mode=source_mode or "unknown",
                target_mode=output_mode,
            )
        except Exception:
            pass

    if diagnostic_logger is not None and call_ordinal is not None:
        try:
            diagnostic_logger(
                "ai_request_begin",
                call_ordinal=call_ordinal,
                model=model,
                route=route,
            )
        except Exception:
            pass
        provider_context_token = _PROVIDER_DIAGNOSTIC_CONTEXT.set(
            _ProviderDiagnosticContext(
                logger=diagnostic_logger,
                call_ordinal=call_ordinal,
                model=model,
                route=route,
            )
        )
    failure_stage = "provider_call"
    try:
        provider_input: ProviderInput = (
            TitleTranslationRequest(title_subject)
            if title_subject
            else embedded_prose[2] if embedded_prose else protected
        )
        provider_context = previous if semantic_context is None else semantic_context
        provider_following = following if semantic_context is None else ""
        raw = provider(provider_context, provider_input, provider_following, output_mode)
        if not raw or not raw.strip():
            _debug_response_structure(
                None,
                json_parsed=None,
                failure_stage="provider_empty_result",
            )
            _debug_outcome("malformed_response")
            finish_ai_request("parse_error", "empty_response", True)
            return deterministic
        failure_stage = "validation"
        candidate = raw
        if title_subject:
            translated_subject = _parse_title_result(raw, title_subject)
            if translated_subject is None:
                _debug_outcome("validation_rejected")
                finish_ai_request(
                    "validation_rejected",
                    "validation_rejected_other",
                    True,
                )
                return deterministic
            candidate = protected.replace(title_subject, translated_subject, 1)
        elif embedded_prose:
            candidate = (
                protected[:embedded_prose[0]]
                + raw.strip()
                + protected[embedded_prose[1]:]
            )
        restored, restore_reason = _restore_with_reason(
            candidate,
            protected,
            llm_input,
            replacements,
        )
        if restored is None:
            _debug_outcome("validation_rejected")
            finish_ai_request("validation_rejected", restore_reason, True)
            return deterministic
        if _has_unsupported_latin_output(
            restored, source, deterministic, output_mode
        ):
            _debug_outcome("validation_rejected")
            finish_ai_request(
                "validation_rejected",
                "validation_rejected_other",
                True,
            )
            return deterministic
        if (
            source_mode in _CHINESE_SOURCE_MODES
            and output_mode in _ENGLISH_OUTPUTS
            and _CJK_RE.search(restored)
        ):
            _debug_outcome("validation_rejected")
            finish_ai_request(
                "validation_rejected",
                "validation_rejected_residual_cjk",
                True,
            )
            return deterministic
        if outer_parentheses is not None:
            restored = f"{outer_parentheses[0]}{restored}{outer_parentheses[1]}"
        outcome = "called_no_improvement" if restored.strip() == deterministic.strip() else "called_accepted"
        _debug_outcome(outcome)
        finish_ai_request(
            "fallback_used" if outcome == "called_no_improvement" else "success",
            "no_improvement" if outcome == "called_no_improvement" else "success",
            False,
        )
        return restored
    except TimeoutError:
        _debug_outcome("timeout")
        finish_ai_request("timeout", "timeout", True)
        return deterministic
    except urllib.error.URLError:
        _debug_outcome("api_error")
        finish_ai_request("network_error", "network_error", True)
        return deterministic
    except _DiagnosedMalformedResponse:
        _debug_outcome("malformed_response")
        finish_ai_request("parse_error", "malformed_response", True)
        return deterministic
    except ValueError:
        _debug_response_structure(
            None,
            json_parsed=None,
            failure_stage=f"{failure_stage}_value_error",
        )
        _debug_outcome("malformed_response")
        finish_ai_request("parse_error", "malformed_response", True)
        return deterministic
    except OSError:
        _debug_outcome("api_error")
        finish_ai_request("network_error", "network_error", True)
        return deterministic
    except Exception:
        _debug_outcome("api_error")
        finish_ai_request("provider_error", "provider_error", True)
        return deterministic
    finally:
        if provider_context_token is not None:
            _PROVIDER_DIAGNOSTIC_CONTEXT.reset(provider_context_token)
