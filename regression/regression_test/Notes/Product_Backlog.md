# Product Backlog

This backlog records issues discovered during regression testing. Do not implement fixes from this file unless a future RC explicitly selects them.

## RC20 Regression Additions

## Current Known Issues For External UAT Round 2

### Android overlay font appears relatively small

- Priority: Deferred
- Category: Overlay / mobile readability
- Status: Known Issue
- Description: Android Human UAT indicates overlay labels may appear relatively small compared with iPhone/desktop. Defer until more External UAT feedback confirms whether this is a broad issue or device-specific.

### Download session reset observed once on iPhone Safari

- Priority: Monitoring
- Category: Browser / download workflow
- Status: Monitoring only
- Description: One iPhone Safari test observed a session reset after download. The issue is not currently reproducible. Keep monitoring during External UAT Round 2 before changing code.

### Space-separated grouped shorthand

- Priority: P1
- Category: Translation parser
- Source patterns: `Pattern_003`, possibly other social screenshots
- Description: Expressions such as `3(x v)` and `3(x a)` are not translated as grouped stitch expressions because the parser expects punctuation separators such as comma or dot. Expected examples: `3(x v)` -> `(sc, inc) x3`; `3(x a)` -> `(sc, dec) x3`.

### OCR spacing inside grouped shorthand

- Priority: P2
- Category: Translation parser / OCR cleanup
- Source patterns: `Pattern_002`
- Description: OCR can produce grouped shorthand without a separator, such as `v2x` inside `3(2x,v2x)`. This leaves part of the expression untranslated. Needs careful parser work to avoid changing valid terms.

### Chinese instruction phrase coverage

- Priority: P2
- Category: Dictionary / phrase translation
- Source patterns: `Pattern_002`, `Pattern_005`
- Description: Instructional prose such as color/material names, stuffing notes, and closing notes often remains untranslated. This is not a Select Area regression, but it affects user-perceived completeness.

### English prose coverage

- Priority: P2
- Category: Dictionary / phrase translation
- Source patterns: `Pattern_004`, `Pattern_006`
- Description: English prose instructions translate partially. Stitch terms translate, but ordinary instruction phrases such as `Join with`, `Break off yarn`, `Stuffing`, and material notes need broader phrase coverage.

### Overlay label placement in narrow selected columns

- Priority: P3
- Category: Overlay
- Source patterns: `Pattern_002`, `Pattern_005`
- Description: Select Area improves runtime and readability, but narrow columns can still produce markers or labels that sit close to source text. Future overlay work may need better column-aware placement.

### Symbol chart support

- Priority: Future / out of current scope
- Category: OCR / product scope
- Source patterns: `Pattern_006`
- Description: Symbol chart recognition is outside current OCR-text translation scope. Pattern_006 should remain a stress/boundary pattern unless chart support becomes an approved product direction.

## Knowledge Base Research

### Cross Single Crochet

- Priority: Backlog research
- Category: Shared stitch database / terminology
- Status: Research only; do not edit the CSV until terminology is validated.
- Known Chinese names to investigate: `交叉短針`, `短針交叉針`, `交叉 X`
- Validation required before adding: English names and aliases, US/UK usage, abbreviations, Traditional and Simplified Chinese names, Japanese name, tutorial search terms, stitch symbol if a recognised symbol exists, and whether the listed Chinese terms truly describe the same stitch.
