"""Shared deterministic translations for recognized pattern section headings."""

import re
import unicodedata
from typing import Dict, Optional


_LETTERED_CJK_HEADING_RE = re.compile(
    r"^(?P<prefix>[A-Za-z])\s*\.\s*(?P<label>[\u3400-\u9fff][\u3400-\u9fff\s]{0,7})$"
)
_CROCHET_EXPRESSION_CJK_MARKERS = frozenset(
    "針针鎖锁辮辫短長长鉤钩鈎勾加減减引拔環环圈起立"
)


SECTION_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "上半部分": {"Traditional Chinese": "上半部分", "Simplified Chinese": "上半部分", "English — US": "Upper section", "English — UK": "Upper section", "Japanese": "上半分"},
    "上半部份": {"Traditional Chinese": "上半部分", "Simplified Chinese": "上半部分", "English — US": "Upper section", "English — UK": "Upper section", "Japanese": "上半分"},
    "下半部分": {"Traditional Chinese": "下半部分", "Simplified Chinese": "下半部分", "English — US": "Lower section", "English — UK": "Lower section", "Japanese": "下半分"},
    "下半部份": {"Traditional Chinese": "下半部分", "Simplified Chinese": "下半部分", "English — US": "Lower section", "English — UK": "Lower section", "Japanese": "下半分"},
    "腳丫": {"Traditional Chinese": "腳丫", "Simplified Chinese": "脚丫", "English — US": "Feet", "English — UK": "Feet", "Japanese": "足"},
    "脚丫": {"Traditional Chinese": "腳丫", "Simplified Chinese": "脚丫", "English — US": "Feet", "English — UK": "Feet", "Japanese": "足"},
    "腳Y": {"Traditional Chinese": "腳丫", "Simplified Chinese": "脚丫", "English — US": "Feet", "English — UK": "Feet", "Japanese": "足"},
    "脚Y": {"Traditional Chinese": "腳丫", "Simplified Chinese": "脚丫", "English — US": "Feet", "English — UK": "Feet", "Japanese": "足"},
    "頭": {"Traditional Chinese": "頭", "Simplified Chinese": "头", "English — US": "Head", "English — UK": "Head", "Japanese": "頭"},
    "头": {"Traditional Chinese": "頭", "Simplified Chinese": "头", "English — US": "Head", "English — UK": "Head", "Japanese": "頭"},
    "身體": {"Traditional Chinese": "身體", "Simplified Chinese": "身体", "English — US": "Body", "English — UK": "Body", "Japanese": "体"},
    "身体": {"Traditional Chinese": "身體", "Simplified Chinese": "身体", "English — US": "Body", "English — UK": "Body", "Japanese": "体"},
    "耳朵": {"Traditional Chinese": "耳朵", "Simplified Chinese": "耳朵", "English — US": "Ears", "English — UK": "Ears", "Japanese": "耳"},
    "尾巴": {"Traditional Chinese": "尾巴", "Simplified Chinese": "尾巴", "English — US": "Tail", "English — UK": "Tail", "Japanese": "しっぽ"},
    "手臂": {"Traditional Chinese": "手臂", "Simplified Chinese": "手臂", "English — US": "Arms", "English — UK": "Arms", "Japanese": "腕"},
    "腿": {"Traditional Chinese": "腿", "Simplified Chinese": "腿", "English — US": "Legs", "English — UK": "Legs", "Japanese": "脚"},
}


def clean_section_candidate(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).strip()
    value = value.replace("（", "(").replace("）", ")")
    value = re.sub(r"^[\s\-~:：;；,，、.。()]+|[\s\-~:：;；,，、.。()]+$", "", value)
    return re.sub(r"\s+", "", value)


def detect_section_header(original: str, output_mode: str) -> Optional[str]:
    normalized = unicodedata.normalize("NFKC", str(original or "")).strip()
    lettered = _LETTERED_CJK_HEADING_RE.fullmatch(normalized)
    if lettered and not any(
        marker in lettered.group("label")
        for marker in _CROCHET_EXPRESSION_CJK_MARKERS
    ):
        label = re.sub(r"\s+", "", lettered.group("label"))
        return f"{lettered.group('prefix')}.{label}"

    candidate = clean_section_candidate(original)
    if not candidate:
        return None

    for key, outputs in SECTION_TRANSLATIONS.items():
        if candidate == key or candidate.startswith(key + ":") or candidate.startswith(key + "："):
            return outputs.get(output_mode, outputs.get("Traditional Chinese", key))
        if key in {"上半部分", "上半部份", "下半部分", "下半部份"} and key in candidate and len(candidate) <= 12:
            return outputs.get(output_mode, outputs.get("Traditional Chinese", key))

    if re.fullmatch(r"[腳脚][丫Yy]", candidate):
        return SECTION_TRANSLATIONS["腳丫"].get(output_mode, "腳丫")

    short_part_map = {
        "耳": "Ears", "耳朵": "Ears", "尾": "Tail", "尾巴": "Tail",
        "花瓣": "Petals", "葉子": "Leaves", "叶子": "Leaves", "翅膀": "Wings",
    }
    if len(candidate) <= 4 and candidate in short_part_map:
        if output_mode == "Traditional Chinese":
            return {"叶子": "葉子"}.get(candidate, candidate)
        if output_mode == "Simplified Chinese":
            return {"葉子": "叶子"}.get(candidate, candidate)
        return short_part_map[candidate]
    return None
