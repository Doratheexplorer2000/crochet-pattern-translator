"""Deterministic OCR text cleanup for crochet pattern text."""

import re
import unicodedata

from pattern_translator.engine import line_translation as line_translation_engine


def normalize_pattern_rounds(text: str) -> str:
    """Repair common OCR mistakes around amigurumi round labels.

    Examples:
    - 9; (2SC, 1DEC)x6 [18]  -> R9: (2SC, 1DEC)x6 [18]
    - 10: (1SC, 1DEC)x6 [12] -> R10: (1SC, 1DEC)x6 [12]
    - Rs-R8:                  -> R5-R8:
    - RI1 / Rl1 / R1o         -> R11 / R11 / R10
    """
    # Character-level / short-token repairs often caused by OCR.
    repairs = {
        "R1o": "R10", "R1O": "R10", "R10;": "R10:",
        "RI1": "R11", "Rl1": "R11", "Rll": "R11", "R11;": "R11:",
        "Rs-R8": "R5-R8", "RS-R8": "R5-R8", "R$-R8": "R5-R8",
        "Rs - R8": "R5-R8", "RS - R8": "R5-R8",
    }
    for bad, good in repairs.items():
        text = text.replace(bad, good)

    # Normalise R 1 / R1; / R1. to R1:
    text = re.sub(r"\bR\s*(\d+)", r"R\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\bR(\d+)\s*[;.]", r"R\1:", text, flags=re.IGNORECASE)

    # If OCR drops the R at the start of a line, restore it when the line looks like a round row.
    # Example: 9; (2SC, 1DEC)x6 [18] / 10: (1SC, 1DEC)x6 [12]
    fixed_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^\d{1,2}\s*[:;]\s*", stripped) and re.search(
            r"\b(SC|INC|DEC|HDC|DC|TR|SLST|MR)\b|\[[0-9]+\]",
            stripped,
            flags=re.IGNORECASE,
        ):
            stripped = re.sub(r"^(\d{1,2})\s*[:;]\s*", r"R\1: ", stripped)
            fixed_lines.append(stripped)
        else:
            fixed_lines.append(line)

    text = "\n".join(fixed_lines)

    # Sometimes OCR reads R5-R8 as R5 R8 or R5-RB. Handle the obvious safe cases only.
    text = re.sub(r"\bR5\s*[-–]\s*R?8\s*[:;]", "R5-R8:", text, flags=re.IGNORECASE)
    return text


def clean_ocr_text(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw)
    text = line_translation_engine.normalize_decimal_mm(text)
    # Common OCR repairs in amigurumi patterns.
    replacements = {
        "；": ":",
        "：": ":",
        "IINC": "1INC",
        "IInc": "1INC",
        "lINC": "1INC",
        "InC": "INC",
        "INc": "INC",
        "DEc": "DEC",
        "IDEC": "1DEC",
        "ISc": "1SC",
        "IS C": "1SC",
        "S LST": "SLST",
        "SL ST": "SLST",
        "S L ST": "SLST",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)

    text = normalize_pattern_rounds(text)

    # V27: English patterns often use Rnd 1 / Rnd 3-4 instead of R1 / R3-4.
    # Normalise only the crochet round abbreviation, not the ordinary word "round".
    text = re.sub(r"\bRnd\s*(\d+)", r"R\1", text, flags=re.IGNORECASE)

    # More Chinese-pattern OCR normalization. Many mainland screenshots mix R labels,
    # digits, Chinese characters, and X/V/A shorthand.
    text = re.sub(r"\br\s*(\d+)", r"R\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\bR(\d+)\s*[;.]", r"R\1:", text, flags=re.IGNORECASE)
    text = re.sub(r"\bR[gq]\s*[:：]", "R9:", text, flags=re.IGNORECASE)
    text = re.sub(r"\bR[lI]\s*[:：]", "R1:", text, flags=re.IGNORECASE)
    text = re.sub(r"\bR114\s*[:：]", "R14:", text, flags=re.IGNORECASE)
    text = re.sub(r"\bR[lI]0\s*[:：]", "R10:", text, flags=re.IGNORECASE)
    text = re.sub(r"\bR[lI]{2}\s*[:：]", "R11:", text, flags=re.IGNORECASE)
    text = text.replace("。", ".").replace("，", ",").replace("、", ",")
    text = line_translation_engine.normalize_decimal_mm(text)
    text = re.sub(r"([xvaftesl])\s*[.]\s*([xvaftesl])", r"\1,\2", text, flags=re.I)
    text = re.sub(r"([XVAFTESL])\s*[.]\s*([XVAFTESL])", r"\1,\2", text)

    text = re.sub(r"\b(\d+)\s*(SC|INC|DEC|HDC|DC|TR|SLST|SL\s*ST|MR|CH|BLO|FLO|FO|STS?|STITCHES?)\b", r"\1\2", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(SLST|SC|INC|DEC|HDC|DC|TR|MR)\b", lambda m: m.group(1).upper(), text, flags=re.IGNORECASE)

    # Mainland Chinese crochet shorthand often uses X/V/A/T/F/E.
    # Uppercase them when they appear as stitch symbols, without touching ordinary words.
    text = re.sub(r"(?<=\d)\s*([xvatfe])\b", lambda m: m.group(1).upper(), text, flags=re.I)
    text = re.sub(r"(?<=[(,，、.。\s])([xvatfe])(?=[),，、.。\s])", lambda m: m.group(1).upper(), text, flags=re.I)
    text = re.sub(r"(?<=[不加減交叉])([xvatfe])\b", lambda m: m.group(1).upper(), text, flags=re.I)
    text = line_translation_engine.normalize_decimal_mm(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
