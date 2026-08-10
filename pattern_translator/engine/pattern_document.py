"""Pattern structure, section grouping, and export helpers.

This module owns pure pattern-document business logic that does not depend on
Streamlit orchestration, session state, downloads, OCR execution, or analytics.
"""

import re
import unicodedata
from typing import Dict, List, Optional, Tuple

import pandas as pd

from pattern_translator.engine import line_translation as line_translation_engine
from pattern_translator.engine import section_headings
from pattern_translator.engine import terminology as terminology_engine

# -----------------------------
# Watermark / noise filtering
# -----------------------------
WATERMARK_KEYWORDS = [
    "HANDMADE", "handmade", "小红书", "小紅書", "小红书号", "小紅書號",
    "禁商用", "禁盗图", "禁盜圖", "禁止商用", "禁止盗图", "禁止盜圖",
    "转载请", "請標明", "请标明", "轉載請", "转载请", "转载", "轉載",
    "cookie_", "cookie", "ID:", "id:", "號:", "号:", "书号", "書號",
]

WATERMARK_TRAILING_PATTERNS = [
    r"[\.。·、,，\s]*小[红紅]書(?:號|号)?\s*[:：]?\s*[A-Za-z0-9_\-]*.*$",
    r"[\.。·、,，\s]*布丁\s*HANDMADE.*$",
    r"[\.。·、,，\s]*HANDMADE.*$",
    r"[\.。·、,，\s]*(?:禁商用|禁盗图|禁盜圖|禁止商用|禁止盗图|禁止盜圖).*$",
    r"[\.。·、,，\s]*(?:转载请|轉載請|转载请|轉載|转载).*$",
]


def strip_watermark_substrings(text: str) -> str:
    s = str(text or "").strip()
    for pat in WATERMARK_TRAILING_PATTERNS:
        s = re.sub(pat, "", s, flags=re.I)
    return s.strip(" .。·、,，;；")


def looks_like_section_header_text(text: str) -> bool:
    return detect_section_header(str(text or ""), "English — US") is not None


def looks_like_pattern_text(text: str) -> bool:
    """Protect real crochet content from watermark removal.

    Do not remove repeated R1/R2/6V/X/V/A lines. Repeated watermarks are only
    removed when they do *not* look like crochet notation, section headers, or
    instructions.
    """
    s = unicodedata.normalize("NFKC", str(text or "")).strip()
    if not s:
        return False
    if looks_like_section_header_text(s):
        return True
    patterns = [
        r"\b[Rr]\s*\d+\b",                         # R1 / R20
        r"\b[Rr]\s*\d+\s*[-~～]\s*\d+\b",          # R5-6 / R5~6
        r"\d+\s*[xXvVaAtTfFeE]\b",                 # 6V / 18x / 2T
        r"[xXvVaAtTfFeE]\s*[\.．,，、]\s*[xXvVaAtTfFeE]",  # X.V / T.v
        r"\d+\s*ch\b|\bch\s*\d+",                 # 6ch / ch6
        r"\b(?:MR|mr|sc|SC|dc|DC|hdc|HDC|tr|TR|sl\s*st|SLST|inc|INC|dec|DEC|blo|BLO|flo|FLO)\b",
        r"環起|环起|環|环|起針|起针|針|针|半針|半针|外半針|内半针|內半針|加針|加针|減針|减针|不加減|不加减|交叉|倒\d+",
    ]
    return any(re.search(pat, s, flags=re.I) for pat in patterns)


def is_watermark_like_text(text: str, repeated_count: int = 1) -> bool:
    s = unicodedata.normalize("NFKC", str(text or "")).strip()
    if not s:
        return True
    # Strong blacklist, but only remove if it is not also a real pattern line.
    if any(k.lower() in s.lower() for k in WATERMARK_KEYWORDS) and not looks_like_pattern_text(s):
        return True
    # Repeated text filter: safe version. Never remove crochet-looking content.
    if repeated_count >= 5 and not looks_like_pattern_text(s):
        return True
    # Very short decorative leftovers with no crochet meaning.
    if len(s) <= 2 and not looks_like_pattern_text(s):
        return True
    return False


def filter_noise_and_watermarks(ocr_rows: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Remove common watermark/noise rows without deleting real pattern rows.

    Also strips trailing watermark fragments from otherwise useful rows, e.g.
    R9: ... 小紅書號:7110260553
    """
    if ocr_rows is None or ocr_rows.empty:
        return pd.DataFrame(), pd.DataFrame()

    rows = ocr_rows.copy().reset_index(drop=True)
    rows["original_text_before_filter"] = rows["text"].astype(str)
    rows["text"] = rows["text"].astype(str).map(strip_watermark_substrings)

    norm_counts = rows["text"].map(lambda x: terminology_engine.norm_text(x)).value_counts().to_dict()
    keep = []
    removed = []
    for _, r in rows.iterrows():
        txt = str(r.get("text", "")).strip()
        original_txt = str(r.get("original_text_before_filter", "")).strip()
        nkey = terminology_engine.norm_text(txt)
        repeated = int(norm_counts.get(nkey, 0)) if nkey else 0
        reason = ""
        if original_txt and txt != original_txt and not txt:
            reason = "watermark substring only"
        elif is_watermark_like_text(txt, repeated_count=repeated):
            reason = f"watermark/noise; repeated={repeated}"
        if reason:
            rr = r.to_dict()
            rr["removed_reason"] = reason
            removed.append(rr)
        else:
            keep.append(r.to_dict())

    keep_df = pd.DataFrame(keep)
    removed_df = pd.DataFrame(removed)
    if not keep_df.empty and "original_text_before_filter" in keep_df.columns:
        # Keep this hidden unless debugging removed rows.
        pass
    return keep_df, removed_df


# -----------------------------
# Section detection / section-aware output
# -----------------------------
SECTION_TRANSLATIONS = section_headings.SECTION_TRANSLATIONS


def _clean_section_candidate(text: str) -> str:
    return section_headings.clean_section_candidate(text)


def detect_section_header(original: str, output_mode: str) -> Optional[str]:
    """Return translated section title if this OCR line looks like a section header.

    Be conservative. A line containing 手 in a note like 靠近自己手半针 should NOT
    become a section. Short standalone labels such as （上半部分） or 脚丫: should.
    """
    return section_headings.detect_section_header(original, output_mode)


def extract_round_label_from_line(original: str) -> Optional[str]:
    """Extract round labels including ranges such as R10~15 / R10-15 / Rnd 3-4."""
    s = unicodedata.normalize("NFKC", str(original or "")).strip()
    s = s.replace("：", ":").replace("；", ":").replace(";", ":")
    # Support common range separators used in Chinese / Japanese / English patterns.
    sep = r"[-–—~～〜－]"
    # Accept both compact R labels and English "Rnd" labels.
    m = re.match(rf"^(?:Rnd\s*)?R?\s*([lI]?[0-9gq]+(?:\s*{sep}\s*R?\s*[0-9gq]+)?)\s*:", s, flags=re.I)
    if not m:
        return None
    label = "R" + line_translation_engine.repair_ocr_round_token(m.group(1)).replace(" ", "")
    label = re.sub(r"^RR", "R", label, flags=re.I)
    # Normalise all range separators for display and downstream parsing.
    label = re.sub(sep, "-", label)
    return label


def _line_to_section_item(row: pd.Series, assigned_by: str = "") -> Dict[str, object]:
    original = str(row.get("Original", "")).strip()
    translated = str(row.get("Translation", "")).strip()
    round_label = extract_round_label_from_line(original) or ""
    return {
        "Original": original,
        "Translation": translated or original,
        "Round": round_label,
        "Confidence": row.get("Confidence", ""),
        "Changed": row.get("Changed", ""),
        "x": float(row.get("min_x", 0) or 0),
        "y": float(row.get("min_y", 0) or 0),
        "assigned_by": assigned_by,
    }


def _round_number(label: str) -> Optional[int]:
    m = re.match(r"^R(\d+)", str(label or ""), flags=re.I)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _row_has_pattern_tokens(original: str) -> bool:
    s = unicodedata.normalize("NFKC", str(original or ""))
    return bool(
        extract_round_label_from_line(s)
        or re.search(r"\d+\s*[xXvVaAtTfFeE]", s)
        or re.search(r"[xXvVaAtTfFeE]\s*[.．,，]", s)
        or re.search(r"\d+\s*(?:ch|sc|dc|hdc|tr|inc|dec|slst|sts?)\b", s, flags=re.I)
        or re.search(r"\b(ch|mr|magic\s*ring|sc|dc|hdc|tr|inc|dec|blo|flo|slst|sl\s*st|sts?|stitch(?:es)?)\b", s, flags=re.I)
        or re.search(r"[環环]\s*\d+\s*[xX]", s)
    )


def _looks_like_instruction_continuation(original: str) -> bool:
    """Detect non-R instruction lines that belong to the current pattern block.

    Example: 雪絨花內半針扭花短針48 is an instruction under R16, not a new section title.
    """
    s = unicodedata.normalize("NFKC", str(original or "")).strip()
    if not s or extract_round_label_from_line(s):
        return False
    # Chinese stitch / loop / crochet instruction with a count usually continues the previous row.
    if re.search(r"[針针半外內内短長长中扭翻圈繞绕鈎钩加減减]", s) and re.search(r"\d+", s):
        return True
    # English-style instruction with a count, but no round label. Handles compact terms: 8sc, 6ch, slst (8).
    if re.search(r"\d+\s*(?:ch|sc|dc|hdc|tr|inc|dec|slst|sts?)\b", s, flags=re.I):
        return True
    if re.search(r"\b(?:start\s+with|start\s+from|magic\s+ring|slst|sl\s*st|blo|flo|turn|join|sew|place)\b", s, flags=re.I) and re.search(r"\d+|\b(?:sc|dc|hdc|tr|ch|inc|dec|slst|mr)\b", s, flags=re.I):
        return True
    return False


def _looks_like_block_title(original: str) -> bool:
    """Heuristic title detector. No fixed title dictionary.

    A title is a short non-round line that is near pattern rows. We do not need
    to know what 蛋糕主體 / 櫻桃 / 蠟燭 means; we only need to avoid treating it as
    a crochet instruction row.
    """
    s = unicodedata.normalize("NFKC", str(original or "")).strip()
    if not s:
        return False
    if extract_round_label_from_line(s):
        return False
    if _row_has_pattern_tokens(s):
        # e.g. 起83CH... is an instruction, not a title.
        return False
    if _looks_like_instruction_continuation(s):
        return False
    if len(s) > 28:
        return False
    # Chinese part names or short English headings/material labels, without hard-coding every title.
    if re.search(r"[\u4e00-\u9fff]", s):
        return True
    # English part headings tend to be short Title Case words: Body, Cover, Legs, Strap, Sleeve.
    if re.fullmatch(r"[A-Z][A-Za-z ]{1,24}", s) and len(s.split()) <= 4:
        return True
    # Material headings such as <white yarn> should stay with the upcoming section.
    if re.fullmatch(r"<[^>]{2,40}>", s):
        return True
    return False


def is_title_heading_context(original: str, nearby_lines: List[str]) -> bool:
    """Return whether an existing block-title signal is supported by pattern context."""
    if not _looks_like_block_title(original):
        return False
    if re.search(r"\b(?:pattern|pat|patt)\b", str(original or ""), flags=re.I):
        return True
    return any(_row_has_pattern_tokens(line) for line in nearby_lines)


def _cluster_rows_by_x(rows: pd.DataFrame) -> Dict[int, List[int]]:
    """Cluster rows into rough visual columns using x-start of pattern rows.

    This is intentionally simple. It helps with layouts where left and right
    columns contain separate parts but OCR reading order interleaves them.
    """
    if rows.empty:
        return {0: []}

    rows = rows.copy()
    canvas_width = float(max(rows["max_x"].max(), 1.0))
    pattern_indices = []
    xs = []
    for idx, row in rows.iterrows():
        original = str(row.get("Original", ""))
        if _row_has_pattern_tokens(original) or _looks_like_block_title(original):
            pattern_indices.append(idx)
            xs.append(float(row.get("min_x", 0) or 0))

    if not xs:
        return {0: list(rows.index)}

    points = sorted(xs)
    # A gap of roughly a fifth of the page usually separates columns.
    gap_threshold = max(170.0, canvas_width * 0.18)
    centers = []
    cur = [points[0]]
    for x in points[1:]:
        if x - cur[-1] > gap_threshold:
            centers.append(sum(cur) / len(cur))
            cur = [x]
        else:
            cur.append(x)
    centers.append(sum(cur) / len(cur))

    if len(centers) > 4:
        # Too many means decorative text polluted clustering. Collapse a little.
        merged = []
        for c in centers:
            if not merged or abs(c - merged[-1]) > gap_threshold:
                merged.append(c)
            else:
                merged[-1] = (merged[-1] + c) / 2
        centers = merged[:4]

    groups: Dict[int, List[int]] = {i: [] for i in range(len(centers))}
    for idx, row in rows.iterrows():
        original = str(row.get("Original", ""))
        if not (_row_has_pattern_tokens(original) or _looks_like_block_title(original)):
            # General noise/instruction goes to nearest column only if close; otherwise leave for group 0.
            pass
        x = float(row.get("min_x", 0) or 0)
        nearest = min(range(len(centers)), key=lambda i: abs(x - centers[i]))
        # If far from every column and not pattern-like, keep in first group as detected text.
        if abs(x - centers[nearest]) > max(260.0, gap_threshold * 1.2) and not _row_has_pattern_tokens(original):
            nearest = 0
        groups[nearest].append(idx)
    return groups


def _make_section_title_from_pending(pending_titles: List[Tuple[float, str]], default_title: str) -> str:
    if not pending_titles:
        return default_title
    # Use the closest preceding title. If it has bracket notes, keep it; user can judge.
    title = pending_titles[-1][1].strip()
    # Remove common punctuation around it.
    title = re.sub(r"^[\s:：()（）]+|[\s:：()（）]+$", "", title)
    return title or default_title


def _build_layout_blocks_without_headers(rows: pd.DataFrame, output_mode: str) -> List[Dict[str, object]]:
    """Fallback layout parser v1.

    When no explicit known section headers are detected, infer blocks from visual
    columns + round sequence. This avoids merging left-column and right-column
    parts into one section when titles are arbitrary, such as 蛋糕主體 / 櫻桃.
    """
    groups = _cluster_rows_by_x(rows)
    all_sections: List[Dict[str, object]] = []
    unsectioned_lines: List[Dict[str, object]] = []
    section_counter = 1

    # Process columns visually left-to-right.
    for group_id, idxs in sorted(groups.items(), key=lambda kv: float(rows.loc[kv[1], "min_x"].median()) if kv[1] else 0):
        group = rows.loc[idxs].copy().sort_values(["min_y", "min_x"]).reset_index(drop=True)
        current: Optional[Dict[str, object]] = None
        last_round_num: Optional[int] = None
        pending_titles: List[Tuple[float, str]] = []
        current_has_rounds = False

        for _, row in group.iterrows():
            original = str(row.get("Original", "")).strip()
            if not original:
                continue
            round_label = extract_round_label_from_line(original)
            round_num = _round_number(round_label or "")
            y = float(row.get("min_y", 0) or 0)

            if round_label:
                # Start a new block when a new R1 appears, or when numbering goes
                # backwards / repeats after the current block already has rounds.
                restart = False
                if current is None:
                    restart = True
                elif round_num == 1 and current_has_rounds:
                    restart = True
                elif round_num is not None and last_round_num is not None:
                    # R3 followed by another R3/R2 in the same visual column usually
                    # means another nearby part was interleaved, so start a new block.
                    if round_num <= last_round_num and current_has_rounds:
                        restart = True

                if restart:
                    if current and current.get("lines"):
                        all_sections.append(current)
                        section_counter += 1
                    title = _make_section_title_from_pending(pending_titles, f"Section {section_counter}")
                    current = {"title": title, "lines": [], "explicit": False, "x": float(row.get("min_x", 0) or 0), "y": y}
                    pending_titles = []
                    last_round_num = None
                    current_has_rounds = False

                if current is None:
                    current = {"title": f"Section {section_counter}", "lines": [], "explicit": False, "x": float(row.get("min_x", 0) or 0), "y": y}
                current["lines"].append(_line_to_section_item(row, assigned_by=f"layout/col{group_id}"))
                current_has_rounds = True
                if round_num is not None:
                    last_round_num = round_num
                continue

            # Non-round rows.
            if _looks_like_instruction_continuation(original) and current is not None:
                current["lines"].append(_line_to_section_item(row, assigned_by=f"instruction-cont/col{group_id}"))
                continue

            if _looks_like_block_title(original):
                # A title after a block has begun usually starts a new nearby part.
                # Close current so the next R1/R2 can become a clean new block.
                if current and current_has_rounds and current.get("lines"):
                    all_sections.append(current)
                    section_counter += 1
                    current = None
                    last_round_num = None
                    current_has_rounds = False
                pending_titles.append((y, original))
                # Keep only the closest few title candidates.
                pending_titles = pending_titles[-3:]
                continue

            if _row_has_pattern_tokens(original) or _looks_like_instruction_continuation(original):
                # Continuation of previous pattern line, e.g. x.Tv.3Fv... after R6.
                if current is None:
                    title = _make_section_title_from_pending(pending_titles, f"Section {section_counter}")
                    current = {"title": title, "lines": [], "explicit": False, "x": float(row.get("min_x", 0) or 0), "y": y}
                    pending_titles = []
                current["lines"].append(_line_to_section_item(row, assigned_by=f"layout-cont/col{group_id}"))
            else:
                # General non-pattern text: keep only before any sections as Detected text.
                if current is None and not all_sections:
                    unsectioned_lines.append(_line_to_section_item(row, assigned_by="non-pattern"))

        if current and current.get("lines"):
            all_sections.append(current)
            section_counter += 1

    # Sort final sections visually: top-to-bottom, then left-to-right, but keep unsectioned first.
    all_sections = sorted(all_sections, key=lambda sec: (float(sec.get("y", 0) or 0), float(sec.get("x", 0) or 0)))
    if unsectioned_lines:
        return [{"title": "Detected text", "lines": unsectioned_lines, "explicit": False}] + all_sections
    return all_sections or [{"title": "Detected text", "lines": [_line_to_section_item(r, assigned_by="fallback") for _, r in rows.iterrows()], "explicit": False}]



def merge_section_continuation_lines(sections: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Merge OCR-wrapped continuation lines back into the previous round row.

    Long rows are often split by OCR, e.g.
        R1 In a magic ring: 1sc, 2hdc, ...
        1hdc, 1dc, 2hdc, 2sc, ch1 (12)
        slst and fo, leave a long tail for sewing.

    The second/third lines do not start with R1, but they clearly continue the
    previous round. We merge only conservative continuation-looking rows:
    - no own round label
    - previous row has a round label
    - contains crochet tokens or starts with a formula-like token
    This avoids swallowing ordinary notes such as "At the end you should...".
    """
    if not sections:
        return sections

    def continuation_like(text: str) -> bool:
        t = unicodedata.normalize("NFKC", str(text or "")).strip()
        if not t or extract_round_label_from_line(t):
            return False
        if re.match(r"^[,，.;；)）]", t):
            return True
        if re.match(r"^\d+\s*(?:ch|sc|hdc|dc|tr|inc|dec|slst|sl\s*st|sts?|[XVAFTES])\b", t, flags=re.I):
            return True
        if re.match(r"^(?:slst|sl\s*st|fo|fasten\s+off|turn|join|ch|sc|hdc|dc|tr|inc|dec)\b", t, flags=re.I):
            return True
        # Formula fragments without a round prefix.
        if re.search(r"\d+\s*(?:ch|sc|hdc|dc|tr|inc|dec|slst|sl\s*st|sts?)\b", t, flags=re.I):
            return True
        if re.search(r"[()]|[XVAFTES]\s*[,.]", t, flags=re.I) and re.search(r"\d", t):
            return True
        return False

    for sec in sections:
        merged = []
        for line in sec.get("lines", []):
            original = str(line.get("Original", "")).strip()
            if (
                merged
                and not str(line.get("Round", "")).strip()
                and str(merged[-1].get("Round", "")).strip()
                and continuation_like(original)
            ):
                prev = merged[-1]
                prev["Original"] = (str(prev.get("Original", "")).rstrip() + " " + original).strip()
                prev["Translation"] = (str(prev.get("Translation", "")).rstrip() + " " + str(line.get("Translation", "")).strip()).strip()
                # Keep the lower confidence as a conservative signal.
                try:
                    prev["Confidence"] = round(min(float(prev.get("Confidence", 1)), float(line.get("Confidence", 1))), 3)
                except Exception:
                    pass
                if line.get("Changed"):
                    prev["Changed"] = "✓"
            else:
                merged.append(line)
        sec["lines"] = merged
    return sections

def build_section_blocks(line_df: pd.DataFrame, output_mode: str) -> List[Dict[str, object]]:
    """Group OCR line translations into human-readable pattern sections.

    V19 adds Layout Parser v1 for pages with arbitrary titles. Instead of
    relying on a title dictionary, it groups by visual columns and round-number
    sequences, then uses the nearest short non-pattern line above as the block
    title. This handles titles like 蛋糕主體 / 櫻桃 without knowing the words.
    """
    if line_df is None or line_df.empty:
        return []

    rows = line_df.copy().reset_index(drop=True)
    for c in ["min_x", "max_x", "min_y", "max_y"]:
        if c not in rows.columns:
            rows[c] = 0.0
        rows[c] = pd.to_numeric(rows[c], errors="coerce").fillna(0.0)
    rows["cx"] = (rows["min_x"] + rows["max_x"]) / 2
    rows["cy"] = (rows["min_y"] + rows["max_y"]) / 2

    header_rows: List[Dict[str, object]] = []
    for idx, row in rows.iterrows():
        title = detect_section_header(str(row.get("Original", "")), output_mode)
        if title:
            header_rows.append({
                "idx": idx,
                "title": title,
                "x": float(row["min_x"]),
                "cx": float(row["cx"]),
                "y": float(row["min_y"]),
                "cy": float(row["cy"]),
                "lines": [],
                "explicit": True,
            })

    # Position-based path: explicit section headers were found.
    if header_rows:
        header_rows = sorted(header_rows, key=lambda h: (h["y"], h["x"]))
        unsectioned = {"title": "Unsectioned text", "lines": [], "explicit": False, "x": 0, "y": 0}

        for idx, row in rows.iterrows():
            original = str(row.get("Original", "")).strip()
            if not original:
                continue
            if any(h["idx"] == idx for h in header_rows):
                continue

            cy = float(row["cy"])
            cx = float(row["cx"])
            min_x = float(row["min_x"])
            max_x = float(row["max_x"])
            width = max(1.0, max_x - min_x)

            is_roundish = bool(extract_round_label_from_line(original)) or bool(re.match(r"^\s*[Rr][0-9lIgq]+", original))
            has_crochet_tokens = bool(re.search(r"[0-9]+\s*[xXvVaAtTfFeE]|[xXvVaAtTfFeE]\s*[.．,，]", original))
            if is_roundish or has_crochet_tokens or width > 260:
                anchor_x = min_x
                anchor_reason = "start-x"
            else:
                anchor_x = cx
                anchor_reason = "center-x"

            candidates = []
            for h in header_rows:
                if h["cy"] <= cy + 35:
                    vertical_gap = max(0.0, cy - h["cy"])
                    horizontal_gap = abs(anchor_x - h["x"])
                    score = vertical_gap + horizontal_gap * 1.25
                    candidates.append((score, vertical_gap, horizontal_gap, h, anchor_reason))

            if candidates:
                candidates.sort(key=lambda x: (x[0], x[1], x[2]))
                chosen = candidates[0][3]
                chosen["lines"].append(_line_to_section_item(row, assigned_by=f"position/{candidates[0][4]}"))
            else:
                unsectioned["lines"].append(_line_to_section_item(row, assigned_by="above first header"))

        sections: List[Dict[str, object]] = []
        if unsectioned["lines"]:
            sections.append(unsectioned)
        for h in header_rows:
            if h["lines"]:
                sections.append({
                    "title": h["title"],
                    "lines": h["lines"],
                    "explicit": True,
                    "x": h["x"],
                    "y": h["y"],
                })
        return merge_section_continuation_lines(sections)

    # V19 fallback: no explicit known headers. Infer layout blocks.
    return merge_section_continuation_lines(_build_layout_blocks_without_headers(rows, output_mode))

def section_blocks_to_debug_df(sections: List[Dict[str, object]]) -> pd.DataFrame:
    rows = []
    for i, sec in enumerate(sections, start=1):
        lines = sec.get("lines", [])
        rows.append({
            "#": i,
            "Section": sec.get("title", f"Section {i}"),
            "Lines": len(lines),
            "Header x": round(float(sec.get("x", 0) or 0), 1) if sec.get("explicit") else "",
            "Header y": round(float(sec.get("y", 0) or 0), 1) if sec.get("explicit") else "",
            "Round labels": ", ".join([l.get("Round", "") for l in lines if l.get("Round", "")])[:120],
        })
    return pd.DataFrame(rows)


def build_section_readable_text(sections: List[Dict[str, object]]) -> str:
    chunks = []
    for sec in sections:
        title = str(sec.get("title", "Section")).strip()
        lines = sec.get("lines", [])
        if not lines:
            continue
        chunks.append(f"## {title}")
        for line in lines:
            original = str(line.get("Original", "")).strip()
            translated = str(line.get("Translation", "")).strip()
            if terminology_engine.norm_text(original) == terminology_engine.norm_text(translated):
                chunks.append(original)
            else:
                chunks.append(f"{original}\n→ {translated}")
        chunks.append("")
    return "\n".join(chunks).strip()




def build_section_export_text(sections: List[Dict[str, object]], clean_text: str = "", raw_text: str = "") -> str:
    """Plain-text export for users to copy/edit after OCR.

    Keeps both original and translated lines when they differ.
    """
    parts = [
        "Crochet OCR Translation Export",
        "Generated by Crochet OCR Prototype",
        "",
        "Note: OCR and translation may contain mistakes. Please check against the original pattern image.",
        "",
    ]
    readable = build_section_readable_text(sections) if sections else ""
    if readable:
        parts.append("=== Section translation ===")
        parts.append(readable)
        parts.append("")
    if clean_text.strip():
        parts.append("=== Cleaned OCR text ===")
        parts.append(clean_text.strip())
        parts.append("")
    if raw_text.strip():
        parts.append("=== Raw OCR text ===")
        parts.append(raw_text.strip())
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def build_pattern_export_text(interpretation_df: pd.DataFrame, clean_text: str = "", raw_text: str = "", output_mode: str = "Traditional Chinese") -> str:
    parts = [
        "Crochet OCR Pattern Export",
        "Generated by Crochet OCR Prototype",
        "",
        "Note: OCR and pattern interpretation may contain mistakes. Please check against the original pattern image.",
        "",
    ]
    line_text = line_translation_engine.build_line_by_line_text(interpretation_df, output_mode) if interpretation_df is not None and not interpretation_df.empty else ""
    if line_text:
        parts.append("=== Pattern interpretation ===")
        parts.append(line_text)
        parts.append("")
    if clean_text.strip():
        parts.append("=== Cleaned OCR text ===")
        parts.append(clean_text.strip())
        parts.append("")
    if raw_text.strip():
        parts.append("=== Raw OCR text ===")
        parts.append(raw_text.strip())
        parts.append("")
    return "\n".join(parts).strip() + "\n"
