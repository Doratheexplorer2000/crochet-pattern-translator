# Master Stitch Database CSV Specification

Current source snapshot: `stitches_1_8e.csv`

Future production filename: `master_stitches.csv`

Each row represents one searchable stitch, instruction term, symbol, or terminology entry. Empty optional fields are allowed. Search behavior should respect `search_status`.

This specification was checked against the current production `master_stitches.csv` columns:

```text
US_term, US_term_alias, US_abb, US_abb1,
UK_term, UK_term_alias, UK_abb, UK_abb1,
Chinese_term, Chinese_term_alias, Chinese_abb,
Japanese, Japanese_alias,
stitch_id, category, equivalence_group,
symbol_file, search_status, ambiguity_note,
tutorial_search
```

## Column Reference

| Column | Purpose | Format | Mandatory | Example |
|---|---|---|---|---|
| `stitch_id` | Stable internal identifier for a stitch or terminology entry. It exists so future features can reference a durable concept even if visible names change. | Lowercase ID, usually prefixed with `st_`. | Yes | `st_003_single_crochet` |
| `category` | Groups entries by database role or stitch type. It supports future filtering, QA, diagnostics, and possible admin tools. | Lowercase category string. | Recommended | `basic_stitch` |
| `US_term` | Canonical US English display term. Used for dictionary results and US output wording. | Text. | Recommended | `single crochet` |
| `US_term_alias` | Alternate US English names users may search for or OCR may produce. | Pipe-separated aliases. | Optional | `chain stitch` |
| `US_abb` | Primary US abbreviation. Used for lookup and concise output when abbreviations are preferred. | Text abbreviation. | Optional | `sc` |
| `US_abb1` | Additional US abbreviation or variant. Allows common alternates without replacing the primary abbreviation. | Text abbreviation. | Optional | `incr` |
| `UK_term` | Canonical UK English display term. Used for dictionary results and UK output wording. | Text. | Recommended | `double crochet` |
| `UK_term_alias` | Alternate UK English names users may search for or OCR may produce. | Pipe-separated aliases. | Optional | `back loop only|work in back loop only` |
| `UK_abb` | Primary UK abbreviation. Used for lookup and concise output when abbreviations are preferred. | Text abbreviation. | Optional | `dc` |
| `UK_abb1` | Additional UK abbreviation or variant. Allows common alternates without replacing the primary abbreviation. | Text abbreviation. | Optional | `ss` |
| `Chinese_term` | Canonical Traditional Chinese display term. This is the main Chinese terminology source. | Text. | Recommended | `短針` |
| `Chinese_term_alias` | Chinese aliases, Simplified variants, and OCR/search variants. This column helps both dictionary search and OCR recovery without changing the canonical term. | Pipe-separated aliases. | Optional | `辮子針|辫针` |
| `Chinese_abb` | Chinese-pattern symbol or shorthand. This supports notation-style patterns where symbols such as `X`, `V`, or `A` represent stitches. | Text abbreviation or symbol. | Optional | `X` |
| `Japanese` | Canonical Japanese display term. | Text. | Optional | `細編み` |
| `Japanese_alias` | Alternate Japanese names or variants. | Pipe-separated aliases. | Optional | `長々編み` |
| `equivalence_group` | Groups rows that are intentionally related, equivalent, or search-friendly duplicates. It exists so future QA can distinguish intentional duplicate-like entries from accidental duplicate data. | Stable group ID. | Optional | `eq_back_loop` |
| `symbol_file` | Links a database row to its crochet chart symbol asset. It keeps symbol rendering data-driven instead of hardcoded in app logic. | Filename only, no path. | Optional | `sc_x.svg` |
| `search_status` | Controls whether a row participates in production search/lookup. It allows obsolete, risky, or future rows to remain documented without affecting users. | `active`, `inactive`, or blank. Blank should be treated as active for backward compatibility. | Recommended | `active` |
| `ambiguity_note` | Developer-facing explanation for ambiguous terms, intentional duplicates, or search-friendly rows. It exists to prevent future maintainers from "fixing" deliberate database choices by mistake. | Free text. | Optional | `Intentional equivalent/search-friendly duplicate; do not treat as error.` |
| `tutorial_search` | Controls whether Crochet Stitch Translator shows a YouTube tutorial search button. It exists so tutorial UI stays data-driven without storing external URLs in the database. | `yes` or blank only. Blank hides the tutorial button. | Optional | `yes` |

## Alias Rules

- Use `|` to separate multiple aliases in one field.
- Keep canonical terminology in the main term columns.
- Add OCR variants to alias fields only when they are generally useful, not image-specific.
- Do not use aliases to override crochet semantics. If a phrase is an instruction, prefer parser logic plus database terminology.

## Search Status Rules

- `active`: row participates in search and lookup.
- `inactive`: row remains in the CSV for history or future use but should not be searchable.
- blank: treated as active for backward compatibility.

Inactive rows should remain visible to maintainers but should not appear in normal user search or pattern lookup. If a row is inactive because it was replaced by another entry, note the reason in `ambiguity_note` where practical.

## Symbol Rules

- `symbol_file` should contain only the SVG filename.
- The actual SVG should live under `knowledge_base/symbols/`.
- Missing symbol files should not block terminology lookup.

## Tutorial Search Rules

- Use `yes` only when a video tutorial would genuinely help users learn a crochet technique.
- Leave blank for general terminology, pattern instructions, measurements, direction words, and non-demonstration concepts.
- Do not store YouTube URLs in the CSV. Applications should generate search URLs dynamically.

## Database Release Checklist

Before promoting a new database snapshot:

- Required columns exist.
- `stitch_id` values are stable and unique.
- Search aliases are pipe-separated.
- `search_status` is reviewed.
- `tutorial_search` contains only `yes` or blank.
- Stitch Translator search still works.
- Pattern Translator regression still passes.
- Versioned snapshot is archived.
- Production `master_stitches.csv` is updated only after validation.
