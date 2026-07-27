# Crochet Pattern OCR Translator

Mobile-first OCR translation for crochet pattern images.

Current stable build: **RC25**

Application entry point:

```text
pattern_translator/app.py
```

## What This App Does

- Uploads crochet pattern images.
- Lets users translate a selected area or the whole pattern.
- Runs OCR on crochet pattern text.
- Translates crochet stitches, grouped expressions, and selected Chinese pattern instructions.
- Generates an annotated overlay PNG.
- Exports line-by-line translation TXT.
- Exports a Diagnostic Report for feedback and troubleshooting.

## Current Product Status

RC25 is the current Pattern Translator stable build. The first External UAT phase has concluded with positive results from real crochet users.

Key validated behavior:

- Core OCR and translation workflow was successfully validated by real crochet users.
- Overlay translation concept was validated.
- Google Sheets analytics successfully collected real-world usage data.
- The primary remaining issues are UX improvements rather than translation accuracy.
- Whole Pattern proved more reliable in real-world testing and will become the default workflow.
- Select Area remains available as an advanced / experimental feature until a future deployment platform improves cropper reliability.
- `knowledge_base/data/master_stitches.csv` is the current production database.
- `stitches_1_8e.csv` is archived as the accepted source snapshot.
- Chinese foundation-chain and turning-chain semantics are separated.
- Anonymous Google Sheets Usage Analytics records app events and performance metrics without storing personal information, IP addresses, uploaded images, OCR text, or translations.
- Translation lookup performance was improved in RC24c by replacing repeated pandas row retrieval with a lightweight row lookup cache.
- Regression evidence is stored under `regression/regression_test/Reports/`.

## Current Project Status

- Official version: `Pattern OCR Translator (Beta RC25)`
- Current phase: Phase 1 - Product Hardening
- Current production database: `knowledge_base/data/master_stitches.csv`
- Phase 1 priorities: make Whole Pattern the default workflow, upgrade Analytics to v2, build the Crochet Intelligence Landing Page, then evaluate and migrate to a more suitable deployment platform if appropriate.
- Future testing: continue with occasional trusted-user testing and incremental fixes based on production evidence. Plan for a Soft Launch after Landing Page completion instead of another formal External UAT cycle.

## Run Locally

```bash
python3 -m streamlit run pattern_translator/app.py
```

## Required Runtime Files

- `pattern_translator/app.py`
- `knowledge_base/data/master_stitches.csv`
- `knowledge_base/symbols/`
- `requirements.txt`
- `runtime.txt`
- `packages.txt`

Analytics writes require Google service account credentials in Streamlit secrets. If credentials or Google Sheets access are unavailable, analytics is skipped and the app continues normally. Pattern Translator Feedback Form migration to `crochetintelligence@gmail.com` is complete.

## Database Direction

The long-term database direction is:

```text
one master stitch database shared by:
- Crochet Stitch Translator
- Crochet Pattern OCR Translator
```

Current production database:

```text
knowledge_base/data/master_stitches.csv
```

See:

- `knowledge_base/DATABASE.md`
- `knowledge_base/CSV_SPEC.md`

## Regression Framework

The regression framework lives under:

```text
regression/
```

Future RCs should provide raw evidence, not only PASS/FAIL summaries.

## Future Architecture

Both current apps should remain independent during Streamlit deployment.

Shared Python utilities and a unified Crochet Intelligence platform are future migration topics, not current implementation requirements.

See:

```text
docs/FUTURE_ARCHITECTURE.md
```
