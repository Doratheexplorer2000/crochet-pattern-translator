"""CSV terminology and lookup engine for the Pattern Translator."""

import hashlib
import re
import sys
import time
import unicodedata
from typing import Callable, Dict, List, Mapping, Optional, Tuple

import pandas as pd


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


ZH_VARIANTS = str.maketrans({
    "钩": "鈎", "勾": "鈎", "针": "針", "锁": "鎖", "长": "長",
    "编": "編", "织": "織", "线": "線", "绕": "繞", "组": "組",
    "环": "環", "双": "雙", "单": "單", "减": "減", "裏": "裡",
    "里": "裡", "辫": "辮", "结": "結", "记": "記", "内": "內",
    "后": "後",
})

SIMP_MAP = str.maketrans({
    "針": "针", "鎖": "锁", "長": "长", "環": "环", "編": "编", "織": "织",
    "線": "线", "減": "减", "鈎": "钩", "鉤": "钩", "雙": "双", "單": "单",
    "組": "组", "記": "记", "裡": "里", "辮": "辫", "結": "结", "狀": "状",
    "內": "内", "後": "后",
})


def norm_text(value: object) -> str:
    _profile_count("norm_text calls")
    if _profile_active():
        try:
            caller = sys._getframe(1).f_code.co_name
        except Exception:
            caller = "unknown"
        _profile_count(f"norm_text caller: {caller}")
    profile_start = time.perf_counter() if _profile_active() else None
    if value is None or pd.isna(value):
        if profile_start is not None:
            _profile_add_time("OCR text normalization", time.perf_counter() - profile_start)
        return ""
    text = str(value).strip()
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(ZH_VARIANTS)
    text = text.lower()
    text = re.sub(r"[\u200b\u200c\u200d]", "", text)
    text = re.sub(r"[“”‘’'\"`´]", "", text)
    text = re.sub(r"\s+", " ", text)
    out = text.strip()
    if profile_start is not None:
        _profile_add_time("OCR text normalization", time.perf_counter() - profile_start)
    return out


def split_aliases(value: object) -> List[str]:
    if value is None or pd.isna(value):
        return []
    raw = str(value)
    parts = re.split(r"[|,;；，/]+", raw)
    return [p.strip() for p in parts if p.strip()]


def get_active_search_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "search_status" not in df.columns:
        return df
    status = df["search_status"].fillna("").astype(str).str.strip().str.lower()
    return df[(status == "") | (status == "active")].copy()


def get_source_columns(source_mode: str) -> List[str]:
    if source_mode in ["English — UK", "English UK terms"]:
        return ["UK_term", "UK_term_alias", "UK_abb", "UK_abb1"]
    if source_mode in ["English — US", "English US terms"]:
        return ["US_term", "US_term_alias", "US_abb", "US_abb1"]
    if source_mode in ["Traditional Chinese", "Simplified Chinese", "Chinese"]:
        return ["Chinese_term", "Chinese_term_alias", "Chinese_abb"]
    if source_mode == "Japanese":
        return ["Japanese", "Japanese_alias"]
    return [
        "US_term", "US_term_alias", "US_abb", "US_abb1",
        "UK_term", "UK_term_alias", "UK_abb", "UK_abb1",
        "Chinese_term", "Chinese_term_alias", "Chinese_abb",
        "Japanese", "Japanese_alias",
    ]


def build_term_index(df: pd.DataFrame, source_mode: str) -> Dict[str, int]:
    df = get_active_search_df(df)
    cols = [c for c in get_source_columns(source_mode) if c in df.columns]
    index: Dict[str, int] = {}
    for i, row in df.iterrows():
        for col in cols:
            values = [row.get(col, "")] + split_aliases(row.get(col, ""))
            for v in values:
                key = norm_text(v)
                if key and key not in index:
                    index[key] = i
    return index


def build_all_term_index(df: pd.DataFrame) -> Dict[str, int]:
    df = get_active_search_df(df)
    fallback_cols = [
        "US_term", "US_term_alias", "US_abb", "US_abb1",
        "UK_term", "UK_term_alias", "UK_abb", "UK_abb1",
        "Chinese_term", "Chinese_term_alias", "Chinese_abb",
        "Japanese", "Japanese_alias",
    ]
    all_index: Dict[str, int] = {}
    for i, row in df.iterrows():
        for col in fallback_cols:
            if col not in df.columns:
                continue
            values = [row.get(col, "")] + split_aliases(row.get(col, ""))
            for value in values:
                key = norm_text(value)
                if key and key not in all_index:
                    all_index[key] = i
    return all_index


def to_simplified(text: str) -> str:
    return str(text).translate(SIMP_MAP)


def term_from_row(row: Mapping[str, object], output_mode: str, prefer_abbrev: bool = False) -> str:
    """Return the same crochet concept in the user's chosen output language."""
    if output_mode == "Traditional Chinese":
        return str(row.get("Chinese_term", "") or row.get("US_term", "")).strip()
    if output_mode == "Simplified Chinese":
        return to_simplified(str(row.get("Chinese_term", "") or row.get("US_term", "")).strip())
    if output_mode in ["English — US", "English US terms"]:
        return str((row.get("US_abb", "") if prefer_abbrev else row.get("US_term", "")) or row.get("US_term", "")).strip()
    if output_mode in ["English — UK", "English UK terms"]:
        return str((row.get("UK_abb", "") if prefer_abbrev else row.get("UK_term", "")) or row.get("UK_term", "") or row.get("US_term", "")).strip()
    if output_mode == "Japanese":
        return str(row.get("Japanese", "") or row.get("US_term", "")).strip()
    return str(row.get("Chinese_term", "") or row.get("US_term", "")).strip()


NORMALIZED_LOOKUP_INDEX_STATS = {
    "enabled": "Yes",
    "last_key": "",
    "build_count": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "index_size": 0,
    "duplicate_keys": 0,
    "indexed_lookup_attempts": 0,
    "indexed_lookup_hits": 0,
    "indexed_lookup_misses": 0,
    "fallback_lookup_attempts": 0,
    "fallback_lookup_hits": 0,
    "fallback_lookup_misses": 0,
    "index_error": "",
}


def build_normalized_lookup_index(
    index: Dict[str, int],
    all_term_index: Dict[str, int],
    source_mode: str,
) -> Dict[str, int]:
    NORMALIZED_LOOKUP_INDEX_STATS["last_key"] = f"source_mode:{source_mode}"
    NORMALIZED_LOOKUP_INDEX_STATS["cache_misses"] += 1
    NORMALIZED_LOOKUP_INDEX_STATS["build_count"] += 1
    combined: Dict[str, int] = {}
    duplicate_count = 0
    for term_key, row_idx in index.items():
        if term_key and term_key not in combined:
            combined[term_key] = row_idx
        elif term_key:
            duplicate_count += 1
    for term_key, row_idx in all_term_index.items():
        if term_key and term_key not in combined:
            combined[term_key] = row_idx
        elif term_key:
            duplicate_count += 1
    NORMALIZED_LOOKUP_INDEX_STATS["index_size"] = len(combined)
    NORMALIZED_LOOKUP_INDEX_STATS["duplicate_keys"] = duplicate_count
    return combined


def build_row_lookup_cache(df: pd.DataFrame) -> Dict[int, Dict[str, object]]:
    row_cache = df.attrs.get("row_lookup_cache")
    if isinstance(row_cache, dict):
        return row_cache
    row_cache = {row_idx: row.to_dict() for row_idx, row in df.iterrows()}
    df.attrs["row_lookup_cache"] = row_cache
    return row_cache


def cached_lookup_row(df: pd.DataFrame, row_idx: int) -> Optional[Dict[str, object]]:
    return build_row_lookup_cache(df).get(row_idx)


def lookup_row(term: str, index: Dict[str, int], df: pd.DataFrame) -> Optional[Dict[str, object]]:
    _profile_count("lookup_row calls")
    profile_start = time.perf_counter() if _profile_active() else None
    key = norm_text(term)
    try:
        NORMALIZED_LOOKUP_INDEX_STATS["indexed_lookup_attempts"] += 1
        normalized_index = df.attrs.get("normalized_lookup_index", {})
        if normalized_index and key in normalized_index:
            NORMALIZED_LOOKUP_INDEX_STATS["indexed_lookup_hits"] += 1
            _profile_count("lookup_row normalized index hits")
            if profile_start is not None:
                _profile_add_time("term lookup: lookup_row", time.perf_counter() - profile_start)
            return cached_lookup_row(df, normalized_index[key])
        NORMALIZED_LOOKUP_INDEX_STATS["indexed_lookup_misses"] += 1
    except Exception as e:
        NORMALIZED_LOOKUP_INDEX_STATS["index_error"] = str(e)
        NORMALIZED_LOOKUP_INDEX_STATS["indexed_lookup_misses"] += 1

    NORMALIZED_LOOKUP_INDEX_STATS["fallback_lookup_attempts"] += 1
    if key in index:
        NORMALIZED_LOOKUP_INDEX_STATS["fallback_lookup_hits"] += 1
        _profile_count("lookup_row fast hits")
        if profile_start is not None:
            _profile_add_time("term lookup: lookup_row", time.perf_counter() - profile_start)
        return cached_lookup_row(df, index[key])
    all_term_index = df.attrs.get("all_term_index", {})
    if not all_term_index:
        all_term_index = build_all_term_index(df)
        df.attrs["all_term_index"] = all_term_index
    _profile_count("lookup_row fallback dictionary checks")
    if key in all_term_index:
        NORMALIZED_LOOKUP_INDEX_STATS["fallback_lookup_hits"] += 1
        _profile_count("lookup_row fallback hits")
        if profile_start is not None:
            _profile_add_time("term lookup: lookup_row", time.perf_counter() - profile_start)
        return cached_lookup_row(df, all_term_index[key])
    NORMALIZED_LOOKUP_INDEX_STATS["fallback_lookup_misses"] += 1
    if profile_start is not None:
        _profile_add_time("term lookup: lookup_row", time.perf_counter() - profile_start)
    return None


def lookup_term(
    term: str,
    index: Dict[str, int],
    df: pd.DataFrame,
    output_mode: str = "Traditional Chinese",
    prefer_abbrev: bool = False,
) -> str:
    _profile_count("lookup_term calls")
    profile_start = time.perf_counter() if _profile_active() else None
    try:
        row = lookup_row(term, index, df)
        if row is not None:
            return term_from_row(row, output_mode, prefer_abbrev=prefer_abbrev)
        fallback_zh = {
            "sc": "短針", "x": "短針", "inc": "加針", "v": "加針", "dec": "減針", "a": "減針", "mr": "環狀起針",
            "magic ring": "環狀起針", "magic circle": "環狀起針", "adjustable ring": "環狀起針",
            "slst": "引拔針", "sl st": "引拔針", "sl": "引拔針", "hdc": "中長針", "t": "中長針", "dc": "長針", "f": "長針", "tr": "長長針", "e": "長長針",
            "fo": "收線", "blo": "後半針", "flo": "前半針", "ch": "鎖針", "chain": "鎖針", "chains": "鎖針", "st": "針", "sts": "針", "stitch": "針", "stitches": "針",
        }
        fallback_us = {
            "x": "sc", "v": "inc", "a": "dec", "t": "hdc", "f": "dc", "e": "tr", "sl": "sl st",
            "sc": "sc", "inc": "inc", "dec": "dec", "mr": "MR", "magic ring": "MR", "magic circle": "MR", "adjustable ring": "MR", "slst": "sl st", "sl st": "sl st", "ch": "ch", "chain": "ch", "chains": "ch", "st": "st", "sts": "sts", "stitch": "stitch", "stitches": "stitches",
        }
        key = norm_text(term)
        if output_mode == "Simplified Chinese":
            return to_simplified(fallback_zh.get(key, term))
        if output_mode == "Traditional Chinese":
            return fallback_zh.get(key, term)
        if output_mode in ["English — US", "English — UK", "English US terms", "English UK terms"]:
            return fallback_us.get(key, term)
        if output_mode == "Japanese":
            zh = fallback_zh.get(key, term)
            jp = {"短針":"細編み", "加針":"増し目", "減針":"減らし目", "環狀起針":"輪の作り目", "引拔針":"引き抜き編み", "中長針":"中長編み", "長針":"長編み"}
            return jp.get(zh, term)
        return term
    finally:
        if profile_start is not None:
            _profile_add_time("term lookup: lookup_term", time.perf_counter() - profile_start)


CSV_TERM_CACHE: Dict[Tuple[object, ...], Tuple[str, ...]] = {}
CSV_TERM_CACHE_STATS = {
    "hits": 0,
    "misses": 0,
    "generation_count": 0,
    "served_from_cache_count": 0,
    "last_key": "",
    "last_error": "",
    "last_terms_returned": 0,
}


def csv_term_cache_key(df: pd.DataFrame) -> Tuple[object, ...]:
    try:
        content_hash = hashlib.md5(
            pd.util.hash_pandas_object(df.astype(str), index=True).values.tobytes()
        ).hexdigest()
    except Exception:
        content_hash = "content-hash-unavailable"
    return (
        int(len(df)),
        tuple(str(col) for col in df.columns),
        tuple(int(v) for v in df.shape),
        content_hash,
    )


def generate_all_csv_terms_uncached(df: pd.DataFrame) -> List[str]:
    """Return all searchable terms/aliases from the crochet CSV."""
    cols = [
        "US_term", "US_term_alias", "US_abb", "US_abb1",
        "UK_term", "UK_term_alias", "UK_abb", "UK_abb1",
        "Chinese_term", "Chinese_term_alias", "Chinese_abb",
        "Japanese", "Japanese_alias",
    ]
    df = get_active_search_df(df)
    seen = set()
    terms: List[str] = []
    for _, row in df.iterrows():
        _profile_count("get_all_csv_terms row scans")
        for col in cols:
            if col not in df.columns:
                continue
            vals = [row.get(col, "")] + split_aliases(row.get(col, ""))
            for v in vals:
                _profile_count("alias values inspected")
                t = unicodedata.normalize("NFKC", str(v)).strip()
                if not t:
                    continue
                key = norm_text(t)
                if len(key) == 1 and key not in {"x", "v", "a", "t", "f", "e"}:
                    continue
                if key not in seen:
                    seen.add(key)
                    terms.append(t)
    terms.sort(key=lambda x: len(norm_text(x)), reverse=True)
    _profile_count("protected terms generated", len(terms))
    return terms


def get_all_csv_terms(df: pd.DataFrame) -> List[str]:
    _profile_count("get_all_csv_terms calls")
    profile_start = time.perf_counter() if _profile_active() else None
    try:
        key = csv_term_cache_key(df)
        key_text = hashlib.md5(repr(key).encode("utf-8")).hexdigest()
        CSV_TERM_CACHE_STATS["last_key"] = key_text
        if key in CSV_TERM_CACHE:
            CSV_TERM_CACHE_STATS["hits"] += 1
            CSV_TERM_CACHE_STATS["served_from_cache_count"] += 1
            terms = list(CSV_TERM_CACHE[key])
            CSV_TERM_CACHE_STATS["last_terms_returned"] = len(terms)
            _profile_count("get_all_csv_terms served from cache")
            _profile_count("protected terms returned from cache", len(terms))
            return terms
        CSV_TERM_CACHE_STATS["misses"] += 1
        CSV_TERM_CACHE_STATS["generation_count"] += 1
        terms = generate_all_csv_terms_uncached(df)
        CSV_TERM_CACHE[key] = tuple(terms)
        CSV_TERM_CACHE_STATS["last_terms_returned"] = len(terms)
        return list(terms)
    except Exception as e:
        CSV_TERM_CACHE_STATS["last_error"] = str(e)
        terms = generate_all_csv_terms_uncached(df)
        CSV_TERM_CACHE_STATS["last_terms_returned"] = len(terms)
        return terms
    finally:
        if profile_start is not None:
            _profile_add_time("alias lookup / CSV term list", time.perf_counter() - profile_start)


def _ascii_term_regex(term: str) -> str:
    escaped = re.escape(term.strip())
    escaped = re.sub(r"\\\s+", r"\\s+", escaped)
    return rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"


def looks_like_prose_line(text: str) -> bool:
    """Return True for ordinary instruction sentences mixed with crochet terms."""
    s = str(text or "").strip()
    if not s:
        return False
    crochet_words = {
        "sc", "inc", "dec", "hdc", "dc", "tr", "slst", "sl", "st", "sts",
        "ch", "mr", "blo", "flo", "fo", "magic", "ring", "circle",
        "stitch", "stitches", "chain", "chains",
    }
    words = re.findall(r"[A-Za-z]{3,}", s)
    non_crochet = [w for w in words if w.lower() not in crochet_words]
    return bool(non_crochet)


def term_kind(term: str, index: Dict[str, int], df: pd.DataFrame) -> str:
    row = lookup_row(term, index, df)
    if row is not None:
        cat = norm_text(row.get("category", ""))
        if "increase" in cat:
            return "increase"
        if "decrease" in cat:
            return "decrease"
    key = norm_text(term)
    if key in ["inc", "v"]:
        return "increase"
    if key in ["dec", "a"]:
        return "decrease"
    return "stitch"


def replace_csv_terms_in_line(
    text: str,
    index: Dict[str, int],
    df: pd.DataFrame,
    output_mode: str,
    *,
    normalize_decimal_mm_func: Callable[[str], str],
    replace_turning_chain_instructions_func: Callable[..., str],
    replace_foundation_chain_instructions_func: Callable[..., str],
    replace_chain_start_instructions_func: Callable[..., str],
    format_stitch_count_func: Callable[[str, str], str],
    translate_counted_token_func: Callable[..., str],
    format_counted_term_func: Callable[[str, str, str, str], str],
    translate_around_connector_func: Callable[[str, str], str],
    counted_token_term_pattern: str,
) -> str:
    """Replace known crochet terms inside a normal sentence."""
    _profile_count("replace_csv_terms_in_line calls")
    profile_start = time.perf_counter() if _profile_active() else None
    s = normalize_decimal_mm_func(unicodedata.normalize("NFKC", str(text or "")).strip())
    if not s:
        if profile_start is not None:
            _profile_add_time("CSV replacement loops", time.perf_counter() - profile_start)
        return ""

    generated_terms: List[str] = []

    def protect_generated_term(value: str) -> str:
        marker = f"@@RC9D_TERM_{len(generated_terms)}@@"
        generated_terms.append(str(value))
        return marker

    def restore_generated_terms(value: str) -> str:
        out_value = str(value)
        for i, original_value in enumerate(generated_terms):
            out_value = out_value.replace(f"@@RC9D_TERM_{i}@@", original_value)
        return out_value

    s = replace_turning_chain_instructions_func(s, index, df, output_mode, protect=protect_generated_term)
    s = replace_foundation_chain_instructions_func(s, output_mode, protect=protect_generated_term)
    s = replace_chain_start_instructions_func(s, df, output_mode, protect=protect_generated_term)

    def stitch_count_repl(m: re.Match) -> str:
        return protect_generated_term(format_stitch_count_func(m.group(1), output_mode))

    _profile_count("regex passes estimated")
    s = re.sub(r"(?<![A-Za-z0-9.])(\d+)\s*[針针](?![A-Za-z0-9])", stitch_count_repl, s)

    counted_pat = re.compile(
        rf"(?<![A-Za-z0-9])(\d+)\s*({counted_token_term_pattern})\b",
    )

    def counted_repl(m: re.Match) -> str:
        n, term = m.groups()
        return translate_counted_token_func(n, term, index, df, output_mode, protect=protect_generated_term)

    _profile_count("regex passes estimated")
    out = counted_pat.sub(counted_repl, s)

    term_number_pat = re.compile(
        r"(?<![A-Za-z0-9])(sl\s*st|slst|sts?|stitches?|sc|inc|dec|hdc|dc|tr|mr|ch|blo|flo|fo)\s*(\d+)(?![A-Za-z0-9])",
        flags=re.I,
    )

    def term_number_repl(m: re.Match) -> str:
        term, n = m.groups()
        term_clean = re.sub(r"\s+", "", term)
        key = norm_text(term_clean)
        if key in {"st", "sts", "stitch", "stitches"}:
            if output_mode == "Simplified Chinese":
                return protect_generated_term(f"{n}针")
            if output_mode == "Traditional Chinese":
                return protect_generated_term(f"{n}針")
            if output_mode == "Japanese":
                return protect_generated_term(f"{n}目")
            return f"{n} {protect_generated_term(lookup_term(term_clean, index, df, output_mode, prefer_abbrev=True))}"
        term_text = lookup_term(term_clean, index, df, output_mode, prefer_abbrev=(output_mode in ["English — US", "English — UK", "English US terms", "English UK terms"]))
        return format_counted_term_func(protect_generated_term(term_text), n, term_kind(term_clean, index, df), output_mode)

    _profile_count("regex passes estimated")
    out = term_number_pat.sub(term_number_repl, out)

    _profile_count("regex passes estimated")
    out = re.sub(r"(?<![A-Za-z0-9])linc(?![A-Za-z0-9])", lambda m: term_number_repl(type('M', (), {'groups': lambda self: ('inc','1')})()), out, flags=re.I)

    protected_terms = get_all_csv_terms(df)
    protected_terms.extend([
        "slst", "sl st", "magic ring", "magic circle", "adjustable ring",
        "stitch", "stitches", "sts", "turn", "fasten off", "weave in ends",
    ])
    seen_terms = set()
    protected_terms = sorted(
        [t for t in protected_terms if not (norm_text(t) in seen_terms or seen_terms.add(norm_text(t)))],
        key=lambda x: len(norm_text(x)),
        reverse=True,
    )
    for term in protected_terms:
        _profile_count("protected terms looped")
        key = norm_text(term)
        if not key:
            continue
        if re.fullmatch(r"[A-Za-z]", key):
            _profile_count("regex passes estimated")
            continue
        replacement = lookup_term(term, index, df, output_mode, prefer_abbrev=(output_mode in ["English — US", "English — UK", "English US terms", "English UK terms"]))
        if not replacement:
            continue
        if re.fullmatch(r"[A-Za-z0-9 ]+", term):
            _profile_count("regex passes estimated")
            if norm_text(replacement) == key:
                continue
            pat = re.compile(_ascii_term_regex(term), flags=re.I)
            _profile_count("regex passes estimated")
            out = pat.sub(replacement, out)
        else:
            out = out.replace(term, replacement)
            cjk_variants = {
                "針": "[針针]", "內": "[內内]", "後": "[後后]", "環": "[環环]",
                "鎖": "[鎖锁]", "長": "[長长]", "減": "[減减]", "線": "[線线]",
                "繞": "[繞绕]", "鈎": "[鈎钩勾]", "鉤": "[鉤钩勾]",
            }
            variant_pat = "".join(cjk_variants.get(ch, re.escape(ch)) for ch in term)
            _profile_count("regex passes estimated")
            out = re.sub(variant_pat, replacement, out)

    _profile_count("regex passes estimated")
    has_crochet_context = bool(re.search(
        r"\b(sc|inc|dec|hdc|dc|tr|sl\s*st|slst|ch|sts?|stitches?|blo|flo|fo|mr|magic\s+ring|x|v|a)\b",
        s,
        flags=re.I,
    )) or bool(re.search(r"\b(?:work\s+|rnd\s+)?around\b", s, flags=re.I))
    if has_crochet_context:
        _profile_count("regex passes estimated")
        out = translate_around_connector_func(out, output_mode)

    if profile_start is not None:
        _profile_add_time("CSV replacement loops", time.perf_counter() - profile_start)
    return restore_generated_terms(out)

