"""Pure line-translation engine for the Pattern Translator.

This module contains parser and line-translation logic extracted from the
Streamlit app. It intentionally depends on the terminology engine, but not on
Streamlit UI/session code, OCR execution, overlay placement, downloads, or
analytics.
"""

import re
import time
import unicodedata
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

from pattern_translator.engine import terminology


ProfileGetter = Callable[[], object]
ProfileCount = Callable[[str, float], None]
ProfileAddTime = Callable[[str, float], None]

_profile_getter: ProfileGetter = lambda: None
_profile_count_func: ProfileCount = lambda name, amount=1.0: None
_profile_add_time_func: ProfileAddTime = lambda name, seconds: None


def configure_profile_context(
    profile_getter: ProfileGetter,
    profile_count_func: ProfileCount,
    profile_add_time_func: ProfileAddTime,
) -> None:
    """Attach app-level profiling without making this module depend on Streamlit."""
    global _profile_getter, _profile_count_func, _profile_add_time_func
    _profile_getter = profile_getter
    _profile_count_func = profile_count_func
    _profile_add_time_func = profile_add_time_func


def _profile_active() -> bool:
    try:
        return _profile_getter() is not None
    except Exception:
        return False


def _profile_count(name: str, amount: float = 1.0) -> None:
    try:
        _profile_count_func(name, amount)
    except Exception:
        pass


def _profile_add_time(name: str, seconds: float) -> None:
    try:
        _profile_add_time_func(name, seconds)
    except Exception:
        pass


def profile_function(time_name: str, count_name: str):
    def decorator(func):
        def wrapped(*args, **kwargs):
            _profile_count(count_name)
            profile_start = time.perf_counter() if _profile_active() else None
            try:
                return func(*args, **kwargs)
            finally:
                if profile_start is not None:
                    _profile_add_time(time_name, time.perf_counter() - profile_start)
        return wrapped
    return decorator


norm_text = terminology.norm_text
split_aliases = terminology.split_aliases
get_active_search_df = terminology.get_active_search_df
to_simplified = terminology.to_simplified
term_from_row = terminology.term_from_row
lookup_row = terminology.lookup_row
lookup_term = terminology.lookup_term
term_kind = terminology.term_kind
_looks_like_prose_line = terminology.looks_like_prose_line

def format_counted_term(term_text: str, number: str, kind: str, output_mode: str) -> str:
    kind = kind.lower()
    n = str(number)
    if output_mode == "Traditional Chinese":
        if kind in ["increase", "decrease"]:
            return f"{term_text}{n}次"
        return f"{term_text}{n}針"
    if output_mode == "Simplified Chinese":
        if kind in ["increase", "decrease"]:
            return f"{term_text}{n}次"
        return f"{term_text}{n}针"
    if output_mode in ["English — US", "English — UK", "English US terms", "English UK terms"]:
        if kind in ["increase", "decrease"]:
            return f"{term_text} x{n}"
        return f"{n} {term_text}"
    if output_mode == "Japanese":
        if kind in ["increase", "decrease"]:
            return f"{term_text}{n}回"
        return f"{term_text}{n}目"
    return f"{term_text}{n}"

def format_stitch_count(number: str, output_mode: str) -> str:
    n = str(number).strip()
    if output_mode == "Simplified Chinese":
        return f"{n}针"
    if output_mode == "Traditional Chinese":
        return f"{n}針"
    if output_mode == "Japanese":
        return f"{n}目"
    return f"{n} sts"

CHAIN_START_INSTRUCTION_ID = "st_090_start_in_stitch"

FOUNDATION_CHAIN_INSTRUCTION_RE = re.compile(
    r"(?<![環环圈])起\s*(?P<number>\d+|[一二三四五六七八九十]+)\s*(?:个|個)?\s*(?:辮子針|辫子针|鎖針|锁针|CH|ch|chain)"
)

TURNING_CHAIN_INSTRUCTION_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:起立針|起立针|立針|立针|立)\s*(?P<number>\d+|[一二三四五六七八九十]+)\s*(?:CH|ch|chain|鎖針|锁针|辮子針|辫子针)(?![A-Za-z0-9])"
)

CHAIN_START_INSTRUCTION_RE = re.compile(
    r"倒\s*(?:[數数]\s*第\s*)?(?P<number>\d+|[一二三四五六七八九十]+)\s*(?:[針针]|(?:回\s*)?[鉤钩鈎勾])"
)

BARE_CHAIN_START_RECOVERY_RE = re.compile(
    r"倒\s*(?![數数])(?P<number>\d+|[一二三四五六七八九十]+)\s*(?P<context_sep>[\.:：,，;；、。．])?"
)

CHAIN_START_BEFORE_CONTEXT_RE = re.compile(
    r"(?:ch|chain|鎖針|锁针|辮子針|辫子针)\s*[\.:：,，;；、。．]*\s*$",
    flags=re.I,
)

CHAIN_START_AFTER_CONTEXT_RE = re.compile(
    r"^\s*[\.:：,，;；、。．]*\s*(?:sl\s*st|slst|sc|dc|tr|hdc|inc|dec|mr|ch|[XVAWFTESLM])(?=$|[^A-Za-z])",
    flags=re.I,
)

INSTRUCTION_CONTINUATION_RE = re.compile(
    r"^\s*(?:倒|sl\s*st|slst|sc|dc|tr|hdc|inc|dec|mr|ch|[XxVvAaTtFfEeSsLlWw]|M{1,2}|\d+\s*(?:sl\s*st|slst|sc|dc|tr|hdc|ch|blo|flo|fo|[XxVvAaTtFfEeSsLlWw]|M{1,2}))",
    flags=re.I,
)

def parse_small_chinese_number(value: str) -> Optional[int]:
    token = str(value or "").strip()
    if not token:
        return None
    if token.isdigit():
        return int(token)
    digits = {
        "零": 0,
        "一": 1,
        "二": 2,
        "兩": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if token in digits:
        return digits[token]
    if token == "十":
        return 10
    if "十" in token:
        left, _, right = token.partition("十")
        tens = digits.get(left, 1 if left == "" else None)
        ones = digits.get(right, 0 if right == "" else None)
        if tens is not None and ones is not None:
            return tens * 10 + ones
    return None

def english_ordinal(number: int) -> str:
    suffix = "th"
    if number % 100 not in {11, 12, 13}:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"

def get_chain_start_instruction_row(df: pd.DataFrame) -> Optional[pd.Series]:
    if df is None or df.empty or "stitch_id" not in df.columns:
        return None
    active_df = get_active_search_df(df)
    matches = active_df[active_df["stitch_id"].astype(str).str.strip() == CHAIN_START_INSTRUCTION_ID]
    if matches.empty:
        return None
    return matches.iloc[0]

def chain_start_template_from_row(row: pd.Series, output_mode: str) -> str:
    if row is None:
        return ""
    if output_mode in ["English — US", "English US terms"]:
        options = [row.get("US_term", "")] + split_aliases(row.get("US_term_alias", ""))
        return next((str(v).strip() for v in options if "the ..." in str(v)), str(row.get("US_term", "")).strip())
    if output_mode in ["English — UK", "English UK terms"]:
        options = [row.get("UK_term", "")] + split_aliases(row.get("UK_term_alias", ""))
        return next((str(v).strip() for v in options if "the ..." in str(v)), str(row.get("UK_term", "") or row.get("US_term", "")).strip())
    if output_mode == "Japanese" and not str(row.get("Japanese", "")).strip():
        options = [row.get("US_term", "")] + split_aliases(row.get("US_term_alias", ""))
        return next((str(v).strip() for v in options if "the ..." in str(v)), str(row.get("US_term", "")).strip())
    return term_from_row(row, output_mode)

def format_chain_start_instruction(number: int, df: pd.DataFrame, output_mode: str) -> str:
    row = get_chain_start_instruction_row(df)
    if row is None:
        if output_mode == "Simplified Chinese":
            return f"倒{number}针"
        if output_mode == "Traditional Chinese":
            return f"倒{number}針"
        return f"Start in the {english_ordinal(number)} chain from hook"
    template = chain_start_template_from_row(row, output_mode)
    if not template:
        template = str(row.get("US_term", "") or "start in ... chain from hook").strip()
    replacement = english_ordinal(number) if output_mode in ["English — US", "English — UK", "English US terms", "English UK terms", "Japanese"] else str(number)
    out = template.replace("...", replacement)
    if output_mode == "Simplified Chinese":
        out = to_simplified(out)
    if output_mode in ["English — US", "English — UK", "English US terms", "English UK terms", "Japanese"] and out:
        out = out[0].upper() + out[1:]
    return out

def format_foundation_chain_instruction(number: int, output_mode: str) -> str:
    if output_mode == "Simplified Chinese":
        return f"起{number}锁针"
    if output_mode == "Traditional Chinese":
        return f"起{number}鎖針"
    if output_mode == "Japanese":
        return f"鎖編み{number}目"
    return f"Chain {number}"

def format_turning_chain_instruction(number: int, index: Dict[str, int], df: pd.DataFrame, output_mode: str) -> str:
    turning = lookup_term("立", index, df, output_mode, prefer_abbrev=False).strip()
    if not turning:
        turning = "turning chain"
    chain_term = lookup_term("CH", index, df, output_mode, prefer_abbrev=(output_mode in ["English — US", "English — UK", "English US terms", "English UK terms"])).strip()
    if not chain_term:
        chain_term = "ch"
    chain_count = format_counted_term(chain_term, str(number), term_kind("CH", index, df), output_mode)
    out = f"{turning} {chain_count}".strip()
    if output_mode == "Simplified Chinese":
        out = to_simplified(out)
    if output_mode in ["English — US", "English — UK", "English US terms", "English UK terms"] and out:
        out = out[0].upper() + out[1:]
    return out

def instruction_suffix(source: str, end: int) -> str:
    after = str(source or "")[end:]
    if not after:
        return ""
    first = after[0]
    if first.isspace() or first in ")]）}：:,，;；、.":
        return ""
    return ", " if INSTRUCTION_CONTINUATION_RE.match(after) else " "

def instruction_prefix(source: str, start: int) -> str:
    before = str(source or "")[start - 1] if start > 0 else ""
    return " " if before and not before.isspace() and before not in "([（{：:,，;；、" else ""

def replace_foundation_chain_instructions(
    text: str,
    output_mode: str,
    protect: Optional[Callable[[str], str]] = None,
) -> str:
    def repl(m: re.Match) -> str:
        number = parse_small_chinese_number(m.group("number"))
        if number is None:
            return m.group(0)
        translated = format_foundation_chain_instruction(number, output_mode)
        rendered = protect(translated) if protect is not None else translated
        return f"{instruction_prefix(m.string, m.start())}{rendered}{instruction_suffix(m.string, m.end())}"

    return FOUNDATION_CHAIN_INSTRUCTION_RE.sub(repl, str(text or ""))

def replace_turning_chain_instructions(
    text: str,
    index: Dict[str, int],
    df: pd.DataFrame,
    output_mode: str,
    protect: Optional[Callable[[str], str]] = None,
) -> str:
    def repl(m: re.Match) -> str:
        number = parse_small_chinese_number(m.group("number"))
        if number is None:
            return m.group(0)
        translated = format_turning_chain_instruction(number, index, df, output_mode)
        rendered = protect(translated) if protect is not None else translated
        return f"{instruction_prefix(m.string, m.start())}{rendered}{instruction_suffix(m.string, m.end())}"

    return TURNING_CHAIN_INSTRUCTION_RE.sub(repl, str(text or ""))

def has_bare_chain_start_context(source: str, start: int, end: int) -> bool:
    before = str(source or "")[:start]
    after = str(source or "")[end:]
    before_window = before[-40:]
    after_window = after[:40]
    return bool(
        CHAIN_START_BEFORE_CONTEXT_RE.search(before_window)
        or CHAIN_START_AFTER_CONTEXT_RE.search(after_window)
    )

def replace_chain_start_instructions(
    text: str,
    df: pd.DataFrame,
    output_mode: str,
    protect: Optional[Callable[[str], str]] = None,
) -> str:
    def repl(m: re.Match) -> str:
        number = parse_small_chinese_number(m.group("number"))
        if number is None:
            return m.group(0)
        translated = format_chain_start_instruction(number, df, output_mode)
        rendered = protect(translated) if protect is not None else translated
        return f"{instruction_prefix(m.string, m.start())}{rendered}{instruction_suffix(m.string, m.end())}"

    s = CHAIN_START_INSTRUCTION_RE.sub(repl, str(text or ""))

    def bare_repl(m: re.Match) -> str:
        if not has_bare_chain_start_context(m.string, m.start(), m.end()):
            return m.group(0)
        return repl(m)

    return BARE_CHAIN_START_RECOVERY_RE.sub(bare_repl, s)

def translate_chain_start_expression_if_full(text: str, df: pd.DataFrame, output_mode: str) -> Optional[str]:
    s = unicodedata.normalize("NFKC", str(text or "")).strip()
    m = re.fullmatch(CHAIN_START_INSTRUCTION_RE, s)
    if not m:
        return None
    number = parse_small_chinese_number(m.group("number"))
    if number is None:
        return None
    return format_chain_start_instruction(number, df, output_mode)

def contains_chinese_stitch_count(text: str) -> bool:
    return bool(re.search(r"(?<![A-Za-z0-9.])\d+\s*[針针](?![A-Za-z0-9])", str(text)))

def format_group_with_stitch_count(inner: str, count: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str) -> str:
    parts = [translate_group_part(part, index, df, output_mode) for part in split_expression_parts(inner)]
    return f"({', '.join(parts)})({format_stitch_count(count, output_mode)})"

def format_symbol_with_stitch_count(term: str, count: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str) -> str:
    term_clean = re.sub(r"\s+", "", term).upper()
    term_text = lookup_expression_symbol(term_clean, index, df, output_mode)
    return f"{term_text}({format_stitch_count(count, output_mode)})"

def lookup_expression_symbol(term: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str) -> str:
    term_clean = re.sub(r"\s+", "", str(term or "")).upper()
    if term_clean == "M":
        m_key = norm_text(term_clean)
        for _, row in get_active_search_df(df).iterrows():
            aliases = split_aliases(row.get("Chinese_abb", ""))
            values = [row.get("Chinese_abb", "")] + aliases
            if any(norm_text(value) == m_key for value in values):
                us_abb = norm_text(row.get("US_abb", ""))
                uk_abb = norm_text(row.get("UK_abb", ""))
                if us_abb == "sc3tog" or uk_abb == "dc3tog":
                    return term_from_row(row, output_mode, prefer_abbrev=(output_mode in ["English — US", "English — UK", "English US terms", "English UK terms"]))
    return lookup_term(term_clean, index, df, output_mode, prefer_abbrev=(output_mode in ["English — US", "English — UK", "English US terms", "English UK terms"]))

COUNTED_TOKEN_TERM_PATTERN = (
    r"(?i:sl\s*st|slst|sts?|stitches?|sc|inc|dec|hdc|dc|tr|mr|ch|blo|flo|fo)"
    r"|[XxVvAaTtFfEeSsLlWw]{1,2}|M{1,2}"
)

def translate_counted_token(
    number: str,
    term: str,
    index: Dict[str, int],
    df: pd.DataFrame,
    output_mode: str,
    protect: Optional[Callable[[str], str]] = None,
) -> str:
    """Translate compact number-before-term tokens consistently across paths."""
    n = str(number)
    term_clean = re.sub(r"\s+", "", str(term or ""))
    key = norm_text(term_clean)
    if key in {"st", "sts", "stitch", "stitches"}:
        if output_mode == "Simplified Chinese":
            return protect(f"{n}针") if protect is not None else f"{n}针"
        if output_mode == "Traditional Chinese":
            return protect(f"{n}針") if protect is not None else f"{n}針"
        if output_mode == "Japanese":
            return protect(f"{n}目") if protect is not None else f"{n}目"
        term_text = lookup_term(term_clean, index, df, output_mode, prefer_abbrev=True)
        term_text = protect(term_text) if protect is not None else term_text
        return f"{n} {term_text}"
    term_text = lookup_expression_symbol(term_clean, index, df, output_mode)
    term_text = protect(term_text) if protect is not None else term_text
    return format_counted_term(term_text, n, term_kind(term_clean, index, df), output_mode)

def normalize_decimal_mm(text: str) -> str:
    return re.sub(r"\b(\d+)\s*[\.,，]\s*(\d)\s*m\s*m\b", r"\1.\2mm", str(text), flags=re.I)

def translate_around_connector(text: str, output_mode: str) -> str:
    if output_mode == "Traditional Chinese":
        return re.sub(r"\b(?:work\s+|rnd\s+)?around\b", "一圈", text, flags=re.I)
    if output_mode == "Simplified Chinese":
        return re.sub(r"\b(?:work\s+|rnd\s+)?around\b", "一圈", text, flags=re.I)
    if output_mode == "Japanese":
        return re.sub(r"\b(?:work\s+|rnd\s+)?around\b", "1周", text, flags=re.I)
    return text

def join_parts(parts: List[str], output_mode: str) -> str:
    parts = [p for p in parts if p]
    if output_mode in ["Traditional Chinese", "Simplified Chinese", "Japanese"]:
        return "，".join(parts)
    return ", ".join(parts)

def repeat_phrase(inner: str, repeat: str, output_mode: str) -> str:
    if output_mode == "Traditional Chinese":
        return f"（{inner}）重複{repeat}次"
    if output_mode == "Simplified Chinese":
        return f"（{inner}）重复{repeat}次"
    if output_mode == "Japanese":
        return f"（{inner}）を{repeat}回繰り返す"
    return f"({inner}) x{repeat}"

def row_to_chinese(row: pd.Series) -> str:
    zh = str(row.get("Chinese_term", "")).strip()
    return zh or str(row.get("US_term", "")).strip()

def replace_csv_terms_in_line(text: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str) -> str:
    return terminology.replace_csv_terms_in_line(
        text,
        index,
        df,
        output_mode,
        normalize_decimal_mm_func=normalize_decimal_mm,
        replace_turning_chain_instructions_func=replace_turning_chain_instructions,
        replace_foundation_chain_instructions_func=replace_foundation_chain_instructions,
        replace_chain_start_instructions_func=replace_chain_start_instructions,
        format_stitch_count_func=format_stitch_count,
        translate_counted_token_func=translate_counted_token,
        format_counted_term_func=format_counted_term,
        translate_around_connector_func=translate_around_connector,
        counted_token_term_pattern=COUNTED_TOKEN_TERM_PATTERN,
    )

@profile_function("expression parsing: split_expression_parts", "split_expression_parts calls")
def split_expression_parts(text: str) -> List[str]:
    """Split crochet expressions on separators, but keep commas/dots inside brackets.

    Naive splitting breaks common rows such as:
    - ch, (sc, inc)x8, slst (24)
    - 6(X,V)
    - 2T.7X.3T.2Tv

    This helper only splits when we are not inside parentheses/brackets.
    """
    if text is None:
        return []
    s = unicodedata.normalize("NFKC", str(text)).strip()
    parts: List[str] = []
    buf: List[str] = []
    depth = 0
    for i, ch in enumerate(s):
        if ch in "([{（【":
            depth += 1
            buf.append(ch)
            continue
        if ch in ")]）】}":
            depth = max(0, depth - 1)
            buf.append(ch)
            continue
        # Dot is a separator in mainland symbol strings, but only outside brackets.
        if depth == 0 and ch == ".":
            prev_ch = s[i - 1] if i > 0 else ""
            next_ch = s[i + 1] if i + 1 < len(s) else ""
            if prev_ch.isdigit() and next_ch.isdigit():
                buf.append(ch)
                continue
        if depth == 0 and ch in [",", "，", "、", ";", "；", "。", "."]:
            item = "".join(buf).strip()
            if item:
                parts.append(item)
            buf = []
            continue
        buf.append(ch)
    item = "".join(buf).strip()
    if item:
        parts.append(item)
    return parts

def translate_group_part(part: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str = "Traditional Chinese") -> str:
    part_text = normalize_decimal_mm(unicodedata.normalize("NFKC", str(part or "")).strip())
    if not part_text:
        return ""
    translated = translate_expression(part_text, index, df, output_mode)
    return translated if translated else translate_piece(part_text, index, df, output_mode)

@profile_function("translate_piece()", "translate_piece calls")
def translate_piece(piece: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str = "Traditional Chinese") -> str:
    p = normalize_decimal_mm(unicodedata.normalize("NFKC", piece).strip())
    if not p:
        return ""

    turning_chain = re.fullmatch(TURNING_CHAIN_INSTRUCTION_RE, p)
    if turning_chain:
        number = parse_small_chinese_number(turning_chain.group("number"))
        if number is not None:
            return format_turning_chain_instruction(number, index, df, output_mode)

    foundation_chain = re.fullmatch(FOUNDATION_CHAIN_INSTRUCTION_RE, p)
    if foundation_chain:
        number = parse_small_chinese_number(foundation_chain.group("number"))
        if number is not None:
            return format_foundation_chain_instruction(number, output_mode)

    chain_start = translate_chain_start_expression_if_full(p, df, output_mode)
    if chain_start is not None:
        return chain_start

    # Repeat group as one comma-split part, e.g. (sc, inc)x8 / (2sc, dec, 2sc)x8.
    m = re.fullmatch(r"\((.*?)\)\s*(?:[xX×]|\*)\s*(\d+)\s*[（(]\s*(\d+)\s*[)）]", p)
    if m:
        inside, repeat, total = m.groups()
        parts = [translate_group_part(part, index, df, output_mode) for part in split_expression_parts(inside)]
        return f"{repeat_phrase(join_parts(parts, output_mode), repeat, output_mode)} ({total})"

    m = re.fullmatch(r"\((.*?)\)\s*(?:[xX×]|\*)\s*(\d+)", p)
    if m:
        inside, repeat = m.groups()
        parts = [translate_group_part(part, index, df, output_mode) for part in split_expression_parts(inside)]
        return repeat_phrase(join_parts(parts, output_mode), repeat, output_mode)

    m = re.fullmatch(r"\((.*?)\)\s*[（(]\s*(\d+)\s*[針针]\s*[)）]", p)
    if m:
        inside, count = m.groups()
        return format_group_with_stitch_count(inside, count, index, df, output_mode)

    # Bare bracketed group without explicit repeat, e.g. (10X,V).
    m = re.fullmatch(r"\((.*?)\)", p)
    if m:
        parts = [translate_group_part(part, index, df, output_mode) for part in split_expression_parts(m.group(1))]
        return f"（{join_parts(parts, output_mode)}）" if output_mode in ["Traditional Chinese", "Simplified Chinese", "Japanese"] else f"({join_parts(parts, output_mode)})"

    # Term with total count note, e.g. slst (24) / turn (6). Keep the count.
    m = re.fullmatch(r"(SLST|SL\s*ST|CH|SC|INC|DEC|HDC|DC|TR|MR|BLO|FLO|FO)\s*[（(]\s*(\d+)\s*[)）]", p, flags=re.I)
    if m:
        term, total = m.groups()
        term_text = lookup_term(term.replace(" ", ""), index, df, output_mode, prefer_abbrev=(output_mode in ["English — US", "English — UK", "English US terms", "English UK terms"]))
        return f"{term_text} ({total})"

    m = re.fullmatch(r"([XVATFESLWM]{1,2}|SC|INC|DEC|HDC|DC|TR|SLST|MR)\s*[（(]\s*(\d+)\s*[針针]\s*[)）]", p, flags=re.I)
    if m:
        term, count = m.groups()
        return format_symbol_with_stitch_count(term, count, index, df, output_mode)

    m = re.fullmatch(r"(\d+)\s*[針针]", p)
    if m:
        return format_stitch_count(m.group(1), output_mode)

    # Bare English crochet terms.
    if re.fullmatch(r"SLST|SL\s*ST|CH|SC|INC|DEC|HDC|DC|TR|MR|BLO|FLO|FO|ST|STS|STITCH|STITCHES", p, flags=re.I):
        return lookup_term(p.replace(" ", ""), index, df, output_mode, prefer_abbrev=(output_mode in ["English — US", "English — UK", "English US terms", "English UK terms"]))

    # Chinese-mainland shorthand: 2X / 10x / 1V / 6A / 2SL
    m = re.fullmatch(r"(\d+)\s*([XxVvAaTtFfEeSsLlWw]{1,2}|M{1,2})", p)
    if m:
        n, term = m.groups()
        return translate_counted_token(n, term, index, df, output_mode)

    # English shorthand: 6SC / 1DEC / 2 SC
    m = re.fullmatch(r"(\d+)\s*(SC|INC|DEC|HDC|DC|TR|SLST|SL\s*ST|MR|CH|BLO|FLO|FO|STS?|STITCHES?)", p, flags=re.I)
    if m:
        n, term = m.groups()
        return translate_counted_token(n, term, index, df, output_mode)

    # Bare V / X / A or SC / INC / DEC
    if re.fullmatch(r"[XVATFESLWM]{1,2}|SC|INC|DEC|HDC|DC|TR|SLST|MR", p, flags=re.I):
        return lookup_expression_symbol(p.upper(), index, df, output_mode)

    # SC all around / 不加減 / 不加減交叉X
    if re.search(r"\bSC\s+all\s+around\b", p, flags=re.I) or "不加減" in p or "不加减" in p:
        cross = "交叉" in p
        # Safe rule: 不加減X / 不加减X means no increase/decrease, usually X all around.
        # For 交叉X, keep the wording conservative because the exact stitch is not confirmed in CSV yet.
        if output_mode == "Simplified Chinese":
            return "交叉X，不加不减一圈" if cross else "短针不加不减一圈"
        if output_mode == "Traditional Chinese":
            return "交叉X，不加不減一圈" if cross else "短針不加不減一圈"
        if output_mode == "Japanese":
            return "交差X、増減なしで1周" if cross else "細編みで増減なし1周"
        return "cross X all around (not yet confirmed)" if cross else "sc all around"

    # in MR / 環起 / 环起
    if re.search(r"\bin\s+MR\b", p, flags=re.I):
        before = re.sub(r"\bin\s+MR\b", "", p, flags=re.I).strip()
        before_out = translate_piece(before, index, df, output_mode) if before else ""
        if output_mode == "Simplified Chinese":
            return f"在环状起针中钩{before_out}" if before_out else "环状起针"
        if output_mode == "Traditional Chinese":
            return f"在環狀起針中鈎{before_out}" if before_out else "環狀起針"
        if output_mode == "Japanese":
            return f"輪の作り目に{before_out}" if before_out else "輪の作り目"
        return f"{before_out} in MR" if before_out else "MR"

    m = re.search(r"(?:環起|环起|環狀起針|环状起针|環形起針|环形起针|圈起|起圈|環|环)\s*(\d+)\s*([XVATFESLWM]|SC|INC|DEC)?", p, flags=re.I)
    if m:
        n, term = m.groups()
        term = term or "X"
        counted = translate_piece(f"{n}{term}", index, df, output_mode)
        if output_mode == "Simplified Chinese":
            return f"环状起针，{counted}"
        if output_mode == "Traditional Chinese":
            return f"環狀起針，{counted}"
        if output_mode == "Japanese":
            return f"輪の作り目、{counted}"
        return f"MR, {counted}"

    # V26 fallback: expression fragments can contain embedded terms rather than
    # being a single clean token, e.g. "40sc in BLO" or "6sts in between".
    # Run the CSV replacement engine before giving up.
    csv_replaced = replace_csv_terms_in_line(p, index, df, output_mode)
    if csv_replaced and (norm_text(csv_replaced) != norm_text(p) or (contains_chinese_stitch_count(p) and csv_replaced != p)):
        return csv_replaced

    return p

@profile_function("translate_expression()", "translate_expression calls")
def translate_expression(expr: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str = "Traditional Chinese") -> str:
    original = unicodedata.normalize("NFKC", expr).strip()
    if not original:
        return ""

    chain_start = translate_chain_start_expression_if_full(original, df, output_mode)
    if chain_start is not None:
        return chain_start

    generated_chain_terms: List[str] = []

    def protect_chain_start_term(value: str) -> str:
        marker = f"@@R21A_{len(generated_chain_terms)}@@"
        generated_chain_terms.append(str(value))
        return marker

    def restore_chain_start_terms(value: str) -> str:
        out_value = str(value)
        for i, original_value in enumerate(generated_chain_terms):
            out_value = out_value.replace(f"@@R21A_{i}@@", original_value)
        return out_value

    chain_start_recovered = replace_turning_chain_instructions(original, index, df, output_mode, protect=protect_chain_start_term)
    chain_start_recovered = replace_foundation_chain_instructions(chain_start_recovered, output_mode, protect=protect_chain_start_term)
    chain_start_recovered = replace_chain_start_instructions(chain_start_recovered, df, output_mode, protect=protect_chain_start_term)
    if chain_start_recovered != original:
        original = chain_start_recovered

    total_counts = re.findall(r"\[\s*(\d+)\s*\]", original)
    total_suffix = " ".join(f"({format_stitch_count(count, output_mode)})" for count in total_counts)

    def with_total(value: str) -> str:
        value = restore_chain_start_terms(str(value or "").strip())
        if total_suffix:
            return f"{value} {total_suffix}".strip()
        return value

    expr_no_total = re.sub(r"\[[^\]]+\]", "", original).strip()
    expr_no_total = expr_no_total.replace("×", "x")

    # OCR can merge a formula row with nearby prose, e.g.
    # "(9X,A.9X)*3(57) 把它们粘在脸上". Translate the leading formula
    # through the normal parser, then keep/rewrite the trailing text normally.
    m = re.fullmatch(r"(\([^)]*\)\s*(?:[xX]|\*)\s*\d+\s*(?:[（(]\s*\d+\s*[)）])?)(\s+.+)", expr_no_total)
    if m:
        leading_expr, trailing_text = m.groups()
        trailing = replace_csv_terms_in_line(trailing_text.strip(), index, df, output_mode)
        return with_total(f"{translate_expression(leading_expr, index, df, output_mode)} {trailing}".strip())

    # Chinese shorthand with prefix repeat: 8(X,V) / 8 (2x.v)
    m = re.search(r"^(\d+)\s*\((.*?)\)$", expr_no_total, flags=re.I)
    if m:
        repeat, inside = m.groups()
        parts = [translate_group_part(p, index, df, output_mode) for p in split_expression_parts(inside)]
        return with_total(repeat_phrase(join_parts(parts, output_mode), repeat, output_mode))

    # English/general repeat: (2SC, 1DEC)x6 / (1INC, 1SC)x6 / (10X,V)
    m = re.fullmatch(r"\((.*?)\)\s*(?:[xX×]|\*)\s*(\d+)\s*[（(]\s*(\d+)\s*[)）]", expr_no_total)
    if m:
        inside, repeat, total = m.groups()
        parts = [translate_group_part(p, index, df, output_mode) for p in split_expression_parts(inside)]
        return with_total(f"{repeat_phrase(join_parts(parts, output_mode), repeat, output_mode)} ({total})")

    m = re.fullmatch(r"\((.*?)\)\s*(?:[xX×]|\*)\s*(\d+)", expr_no_total)
    if m:
        inside, repeat = m.groups()
        parts = [translate_group_part(p, index, df, output_mode) for p in split_expression_parts(inside)]
        return with_total(repeat_phrase(join_parts(parts, output_mode), repeat, output_mode))

    m = re.fullmatch(r"\((.*?)\)\s*[（(]\s*(\d+)\s*[針针]\s*[)）]", expr_no_total)
    if m:
        inside, count = m.groups()
        return with_total(format_group_with_stitch_count(inside, count, index, df, output_mode))

    # A bracketed group without explicit repeat, e.g. (10X,V)
    m = re.fullmatch(r"\((.*?)\)", expr_no_total)
    if m:
        parts = [translate_group_part(p, index, df, output_mode) for p in split_expression_parts(m.group(1))]
        return with_total(f"（{join_parts(parts, output_mode)}）" if output_mode in ["Traditional Chinese", "Simplified Chinese", "Japanese"] else f"({join_parts(parts, output_mode)})")

    if re.search(r"\bin\s+MR\b", expr_no_total, flags=re.I) or re.search(r"環起|环起|環狀起針|环状起针|環形起針|环形起针|圈起|起圈|環\s*\d|环\s*\d", expr_no_total):
        return with_total(translate_piece(expr_no_total, index, df, output_mode))

    if "," in expr_no_total or "，" in expr_no_total or "、" in expr_no_total or "." in expr_no_total:
        split_parts = split_expression_parts(expr_no_total)
        if len(split_parts) == 1 and split_parts[0] == expr_no_total:
            return with_total(translate_piece(expr_no_total, index, df, output_mode))
        parts = [translate_expression(p, index, df, output_mode) for p in split_parts]
        return with_total(join_parts(parts, output_mode))

    return with_total(translate_piece(expr_no_total, index, df, output_mode))

def repair_ocr_round_token(token: str) -> str:
    """Repair common OCR round labels such as Rl14, RI6, R2g."""
    t = unicodedata.normalize("NFKC", token).strip()
    t = t.replace("：", ":").replace("；", ":").replace(";", ":")
    t = re.sub(r"^r", "R", t, flags=re.I)
    t = re.sub(r"^R[gq](?=\s*:)", "R9", t, flags=re.I)
    t = re.sub(r"^R[lI](?=\s*:)", "R1", t, flags=re.I)
    t = re.sub(r"^R114(?=\s*:)", "R14", t, flags=re.I)
    t = re.sub(r"^R2[gq](?=\s*:)", "R29", t, flags=re.I)

    m = re.match(r"^R([lI])([0-9]+)(.*)$", t)
    if m:
        digits = m.group(2)
        rest = m.group(3)
        # Rl0 / RI0 usually means R10. Rl1 alone usually means R11.
        if digits == "0":
            return "R10" + rest
        if digits == "1":
            return "R11" + rest
        # Rl14 / RI6 means an extra l/I was inserted after R. Drop it.
        return "R" + digits + rest

    t = re.sub(r"^R114", "R14", t)
    t = re.sub(r"^Rl0", "R10", t)
    t = re.sub(r"^Rl1", "R11", t)
    t = re.sub(r"^RI1", "R11", t)
    return t




def get_output_column_name(output_mode: str) -> str:
    return "解讀" if output_mode in ["Traditional Chinese", "Simplified Chinese"] else "Interpretation"

def build_line_by_line_text(interpretation_df: pd.DataFrame, output_mode: str) -> str:
    if interpretation_df.empty:
        return ""
    output_col = get_output_column_name(output_mode)
    lines = []
    for _, row in interpretation_df.iterrows():
        round_label = str(row.get("Round", "")).strip()
        interp = str(row.get(output_col, "")).strip()
        total = str(row.get("Total stitches", "")).strip()
        if not round_label and not interp:
            continue
        suffix = ""
        if total:
            if output_mode == "Simplified Chinese":
                suffix = f"（共{total}针）"
            elif output_mode == "Traditional Chinese":
                suffix = f"（共{total}針）"
            elif output_mode == "Japanese":
                suffix = f"（合計{total}目）"
            else:
                suffix = f" [{total} sts]"
        lines.append(f"{round_label}: {interp}{suffix}".strip())
    return "\n".join(lines)

@profile_function("OCR text normalization: clean_single_ocr_line", "clean_single_ocr_line calls")
def clean_single_ocr_line(text: str) -> str:
    """Clean one OCR box/line without trying to rebuild sections or columns."""
    s = unicodedata.normalize("NFKC", str(text)).strip()
    if not s:
        return ""
    s = normalize_decimal_mm(s)
    # Keep this conservative. Do not invent missing separators such as XV -> X,V.
    s = s.replace("：", ":").replace("；", ":").replace(";", ":")
    s = s.replace("，", ",").replace("、", ",").replace("。", ".")
    s = normalize_decimal_mm(s)
    s = repair_ocr_round_token(s)
    # Common OCR repairs only when very safe.
    repairs = {
        "Rl:": "R1:", "RI:": "R1:", "Rg:": "R9:", "R2g:": "R29:",
        "Rl0:": "R10:", "RI0:": "R10:", "Rl1:": "R11:", "RI1:": "R11:",
        "R114:": "R14:", "IOX": "10X", "I0X": "10X", "GX": "6X", "SXV": "5XV",
        "S LST": "SLST", "SL ST": "SLST", "S L ST": "SLST", "IDEC": "1DEC", "ISc": "1SC",
    }
    for bad, good in repairs.items():
        s = s.replace(bad, good)
    # Safe OCR fixes in English patterns. 6cc is almost always 6ch in crochet; avoid changing ordinary words.
    s = re.sub(r"(?<=\d)\s*cc\b", "ch", s, flags=re.I)
    s = re.sub(r"\bsl\s*st\b", "slst", s, flags=re.I)
    s = re.sub(r"\bsl\s*st(s)?\b", "slst", s, flags=re.I)
    s = re.sub(r"\bR\s*(\d+)", r"R\1", s, flags=re.I)
    s = re.sub(r"\bR(\d+)\s*[.]", r"R\1:", s, flags=re.I)
    # Normalize punctuation between stitch symbols only if OCR already saw a dot/comma.
    s = re.sub(r"([xvatfeXVATFE])\s*[.]\s*([xvatfeXVATFE])", r"\1,\2", s)
    s = normalize_decimal_mm(s)
    return s.strip()

def translate_common_instruction_line(s: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str) -> Optional[str]:
    """Conservative translation for common non-round crochet instruction lines.

    This is not a general translator. It only handles high-frequency pattern
    phrases safely, while preserving the original when uncertain.
    """
    raw = unicodedata.normalize("NFKC", str(s)).strip()
    if not raw:
        return None

    # Normalise compact stitch counts inside ordinary sentences: 6sts, 8sc, 4ch.
    def counted(n: str, term: str) -> str:
        return translate_piece(f"{n}{term}", index, df, output_mode)

    # Start with 8sc in a Magic ring, slst (8)
    m = re.search(
        r"^Start\s+with\s+(\d+)\s*(sc|sts?|stitches?|ch|dc|hdc|tr)\s+in\s+a\s+Magic\s+ring\s*,?\s*(sl\s*st|slst)?\s*(?:\((\d+)\))?\s*$",
        raw,
        flags=re.I,
    )
    if m:
        n, term, join_term, total = m.groups()
        main = counted(n, "sc" if term.lower().startswith("st") else term)
        mr = lookup_term("mr", index, df, output_mode)
        join = lookup_term("slst", index, df, output_mode) if join_term else ""
        if output_mode == "Simplified Chinese":
            out = f"以{mr}起针，钩{main}"
            if join:
                out += f"，{join}"
            if total:
                out += f"（共{total}针）"
            return out
        if output_mode == "Traditional Chinese":
            out = f"以{mr}起針，鈎{main}"
            if join:
                out += f"，{join}"
            if total:
                out += f"（共{total}針）"
            return out
        if output_mode == "Japanese":
            out = f"{mr}で始め、{main}"
            if join:
                out += f"、{join}"
            if total:
                out += f"（合計{total}目）"
            return out
        out = f"Start with {main} in {mr}"
        if join:
            out += f", {join}"
        if total:
            out += f" ({total})"
        return out

    # Start from 4ch / Start with 6ch / Start with 6cc (OCR-safe)
    m = re.search(r"^Start\s+(?:from|with)\s+(\d+)\s*(ch|cc)\s*$", raw, flags=re.I)
    if m:
        n, term = m.groups()
        main = counted(n, "ch")
        if output_mode == "Simplified Chinese":
            return f"从{main}开始"
        if output_mode == "Traditional Chinese":
            return f"從{main}開始"
        if output_mode == "Japanese":
            return f"{main}から始める"
        return f"Start from {main}"

    # Pure explanatory sentence with embedded stitch count, e.g. "6sts in between".
    # Keep it conservative to avoid Argos-style nonsense.
    m = re.search(r"^(?:Place\s+the\s+eyes\s+on\s+the\s+center\s+of\s+the\s+sleeve,\s*)?(\d+)\s*sts?\s+in\s+between\.?$", raw, flags=re.I)
    if m:
        n = m.group(1)
        stitch_word = counted(n, "st")
        if output_mode == "Simplified Chinese":
            return f"将眼睛放在袖子中央，中间相隔{stitch_word}。" if raw.lower().startswith("place") else f"中间相隔{stitch_word}。"
        if output_mode == "Traditional Chinese":
            return f"將眼睛放在袖子中央，中間相隔{stitch_word}。" if raw.lower().startswith("place") else f"中間相隔{stitch_word}。"
        if output_mode == "Japanese":
            return f"目を袖の中央に付け、間を{stitch_word}空ける。" if raw.lower().startswith("place") else f"間を{stitch_word}空ける。"
        return raw

    # Simple sewing line.
    if re.fullmatch(r"Sew\s+the\s+mouth\.?", raw, flags=re.I):
        if output_mode == "Simplified Chinese":
            return "缝上嘴巴。"
        if output_mode == "Traditional Chinese":
            return "縫上嘴巴。"
        if output_mode == "Japanese":
            return "口を縫い付ける。"
        return raw

    return None

@profile_function("line-by-line translation: translate_ocr_line", "translate_ocr_line calls")
def translate_ocr_line(original: str, index: Dict[str, int], df: pd.DataFrame, output_mode: str) -> str:
    """Translate one OCR text box. If uncertain, return the cleaned original.

    This deliberately behaves like a conservative Google-Translate-ish reader:
    translate recognisable crochet shorthand; keep unrecognised text intact.
    """
    s = clean_single_ocr_line(original)
    if not s:
        return ""

    # V24: avoid hard-coded full-sentence translations.
    # First try CSV term replacement inside the whole line; this lets CSV terms
    # such as turn / slst / magic ring / ch / sts translate wherever they appear.
    csv_replaced = replace_csv_terms_in_line(s, index, df, output_mode)

    # Section headers / ordinary structural labels.
    section_map = {
        "上半部分": {"Traditional Chinese": "上半部分", "Simplified Chinese": "上半部分", "English — US": "Upper section", "English — UK": "Upper section", "Japanese": "上半分"},
        "上半部份": {"Traditional Chinese": "上半部分", "Simplified Chinese": "上半部分", "English — US": "Upper section", "English — UK": "Upper section", "Japanese": "上半分"},
        "下半部分": {"Traditional Chinese": "下半部分", "Simplified Chinese": "下半部分", "English — US": "Lower section", "English — UK": "Lower section", "Japanese": "下半分"},
        "下半部份": {"Traditional Chinese": "下半部分", "Simplified Chinese": "下半部分", "English — US": "Lower section", "English — UK": "Lower section", "Japanese": "下半分"},
        "腳丫": {"Traditional Chinese": "腳丫", "Simplified Chinese": "脚丫", "English — US": "Feet", "English — UK": "Feet", "Japanese": "足"},
        "脚丫": {"Traditional Chinese": "腳丫", "Simplified Chinese": "脚丫", "English — US": "Feet", "English — UK": "Feet", "Japanese": "足"},
    }
    for key, outputs in section_map.items():
        if key in s:
            return outputs.get(output_mode, outputs.get("Traditional Chinese", key))

    # Round label plus expression: R1: 环6x / R3: 6(X,V) / Rnd 1: sc 6
    m = re.match(r"^(?:Rnd\s*)?R?\s*([lI]?[0-9gq]+(?:\s*[-–—~～〜－]\s*R?\d+)?)\s*[:：]\s*(.*)$", s, flags=re.I)
    if m:
        label_core, expr = m.groups()
        label = "R" + repair_ocr_round_token(label_core).replace(" ", "")
        label = re.sub(r"^RR", "R", label, flags=re.I)
        label = re.sub(r"[-–—~～〜－]", "-", label)
        expr = expr.strip()
        if not expr:
            return label
        translated = translate_expression(expr, index, df, output_mode)
        # If no useful change, keep original expression.
        return f"{label}: {translated}"

    # A line can be a raw crochet formula without R label.
    translated = translate_expression(s, index, df, output_mode)

    # V25: for ordinary instruction sentences, prefer CSV term replacement.
    # This avoids partial expression-parser output such as leaving 8sc / Magic ring
    # untranslated in "Start with 8sc in a Magic ring, slst (8)".
    if _looks_like_prose_line(s):
        if csv_replaced and (norm_text(csv_replaced) != norm_text(s) or (contains_chinese_stitch_count(s) and csv_replaced != s)):
            return csv_replaced
        return translated if translated else s

    # Prefer full pattern-expression translation when it clearly changed the line.
    if translated and norm_text(translated) != norm_text(s):
        return translated

    # Otherwise return CSV term replacement. Unknown ordinary language remains as-is.
    if csv_replaced and (norm_text(csv_replaced) != norm_text(s) or (contains_chinese_stitch_count(s) and csv_replaced != s)):
        return csv_replaced

    return translated if translated else s

@profile_function("line-by-line translation: build_readable_line_translation", "build_readable_line_translation calls")
def build_readable_line_translation(line_df: pd.DataFrame) -> str:
    if line_df is None or line_df.empty:
        return ""
    lines = []
    for _, row in line_df.iterrows():
        original = str(row.get("Original", "")).strip()
        translated = str(row.get("Translation", "")).strip()
        if not original and not translated:
            continue
        if norm_text(original) == norm_text(translated):
            lines.append(original)
        else:
            lines.append(f"{original}\n→ {translated}")
    return "\n\n".join(lines)

@profile_function("line-by-line translation: build_overlay_export_text", "build_overlay_export_text calls")
def build_overlay_export_text(line_df: pd.DataFrame, legend_text: str = "", clean_text: str = "", raw_text: str = "") -> str:
    """User-facing TXT export: line-by-line translation only."""
    readable = build_readable_line_translation(line_df) if line_df is not None and not line_df.empty else ""
    return readable.strip() + "\n" if readable.strip() else ""
