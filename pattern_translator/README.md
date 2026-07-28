# Crochet Pattern OCR Translator

Mobile-first OCR translation for crochet pattern images.

Current stable build: **RC26**

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

RC26 is the current Pattern Translator stable local build. The first External UAT phase has concluded with positive results from real crochet users. RC27 validated Railway as the preferred production deployment platform.

Key validated behavior:

- Core OCR and translation workflow was successfully validated by real crochet users.
- Overlay translation concept was validated.
- Google Sheets analytics successfully collected real-world usage data.
- The primary remaining issues are UX improvements rather than translation accuracy.
- Whole Pattern proved more reliable in real-world testing and is now the default workflow.
- Select Area remains available as an advanced / experimental feature until a future deployment platform improves cropper reliability.
- RC26 passed local developer validation and Human UAT.
- RC26 is intentionally local only: no commit, no push, and no Streamlit Community Cloud deployment.
- RC27a Railway preparation completed, and RC27b Railway deployment spike passed.
- Pattern Translator successfully runs on Railway using Docker.
- Railway validation passed for PaddleOCR initialization, Google Sheets analytics, downloads, overlay generation, restart recovery, and post-restart OCR.
- Railway Hobby usage during the spike remained suitable for low-volume production: peak RAM approximately 1.84 GB, normal RAM approximately 1.29 GB, and peak CPU approximately 1.39 vCPU.
- Railway is now the production deployment direction. Streamlit Community Cloud remains a temporary backup platform during migration.
- `app_open` analytics behavior remains unchanged. Duplicate passive `app_open` rows are a known Streamlit Community Cloud lifecycle limitation and will be revisited after migration to a new deployment platform.
- `knowledge_base/data/master_stitches.csv` is the current production database.
- `stitches_1_8e.csv` is archived as the accepted source snapshot.
- Chinese foundation-chain and turning-chain semantics are separated.
- Anonymous Google Sheets Usage Analytics records app events and performance metrics without storing personal information, IP addresses, uploaded images, OCR text, or translations.
- Translation lookup performance was improved in RC24c by replacing repeated pandas row retrieval with a lightweight row lookup cache.
- Regression evidence is stored under `regression/regression_test/Reports/`.

## Current Project Status

- Official version: `Pattern OCR Translator (Beta RC26)`
- Current phase: Railway migration preparation after RC27 validation
- Current production database: `knowledge_base/data/master_stitches.csv`
- Current focus: prepare the production migration path on Railway, keep Streamlit Community Cloud temporarily as backup, then revisit Analytics v2 and landing-page hosting decisions once Railway production deployment is ready.
- Future testing: continue with occasional trusted-user testing and incremental fixes based on production evidence. Plan for a Soft Launch after Landing Page completion instead of another formal External UAT cycle.

## Run Locally

```bash
python3 -m streamlit run pattern_translator/app.py
```

## Deployment Direction

Recommended workflow:

```text
Developer
↓
Local development
↓
Local validation
↓
Human UAT
↓
Railway deployment
↓
Production validation
```

Railway is the preferred production deployment platform after RC27 validation. Streamlit Community Cloud is retained temporarily as a backup platform during migration.

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
