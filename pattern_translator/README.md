# Crochet Pattern OCR Translator

Mobile-first OCR translation for crochet pattern images.

Current deployment candidate: **RC25**

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

RC25 is the current Pattern Translator deployment candidate. It includes the accepted RC24c performance optimization plus the completed Pattern Translator analytics infrastructure.

Key validated behavior:

- Select Area is the recommended default workflow.
- Whole Pattern remains available.
- `knowledge_base/data/master_stitches.csv` is the current production database.
- `stitches_1_8e.csv` is archived as the accepted source snapshot.
- Chinese foundation-chain and turning-chain semantics are separated.
- Anonymous Google Sheets Usage Analytics is implemented locally and records app events and performance metrics without storing personal information, IP addresses, uploaded images, OCR text, or translations. Live Google Sheets append is awaiting Streamlit secrets configuration and live smoke testing.
- Translation lookup performance was improved in RC24c by replacing repeated pandas row retrieval with a lightweight row lookup cache.
- Regression evidence is stored under `regression/regression_test/Reports/`.

## Current Project Status

- Official version: `Pattern OCR Translator (Beta RC25)`
- Development phase: deployment preparation and analytics live validation before the next External UAT round
- Current production database: `knowledge_base/data/master_stitches.csv`
- Next planned milestone: configure Streamlit secrets, deploy RC25 manually, and validate live Google Sheets append

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
