# Crochet Pattern OCR Translator

Mobile-first OCR translation for crochet pattern images.

Current production baseline: **RC28**

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

RC28 is the current Pattern Translator production baseline. The first External UAT phase has concluded with positive results from real crochet users. RC27 validated Railway as the preferred production deployment platform, and RC28 completed the Railway production release.

Key validated behavior:

- Core OCR and translation workflow was successfully validated by real crochet users.
- Overlay translation concept was validated.
- Google Sheets analytics successfully collected real-world usage data.
- The primary remaining issues are UX improvements rather than translation accuracy.
- Whole Pattern proved more reliable in real-world testing and is now the default workflow.
- Select Area remains available as an advanced / experimental feature until a future deployment platform improves cropper reliability.
- RC26 passed local developer validation and Human UAT.
- RC27a Railway preparation completed, and RC27b Railway deployment spike passed.
- Pattern Translator successfully runs on Railway using Docker.
- Railway validation passed for PaddleOCR initialization, Google Sheets analytics, downloads, overlay generation, restart recovery, and post-restart OCR.
- RC28 fixed the Diagnostic Report Railway session-state regression.
- Railway production validation completed successfully.
- Desktop Human UAT passed on Railway production.
- Railway Hobby usage during the spike remained suitable for low-volume production: peak RAM approximately 1.84 GB, normal RAM approximately 1.29 GB, and peak CPU approximately 1.39 vCPU.
- Railway is now the primary production deployment platform. Streamlit Community Cloud remains a backup platform.
- `app_open` analytics behavior remains unchanged. Duplicate passive `app_open` rows are a known Streamlit Community Cloud lifecycle limitation and will be revisited after migration to a new deployment platform.
- `knowledge_base/data/master_stitches.csv` is the current production database.
- `stitches_1_8e.csv` is archived as the accepted source snapshot.
- Chinese foundation-chain and turning-chain semantics are separated.
- Anonymous Google Sheets Usage Analytics records app events and performance metrics without storing personal information, IP addresses, uploaded images, OCR text, or translations.
- Translation lookup performance was improved in RC24c by replacing repeated pandas row retrieval with a lightweight row lookup cache.
- RC42 completed the first local Engine Extraction by moving the CSV terminology / lookup engine into `pattern_translator/engine/terminology.py`.
- Streamlit cache behavior was intentionally preserved through app-level wrappers.
- RC42 regression confirmed `209 / 209` translation cases identical, Human UAT passed, and no user-visible behavior changed.
- RC43 completed the second local Engine Extraction by moving pure line-translation logic into `pattern_translator/engine/line_translation.py`.
- RC43 regression confirmed `220 / 220` direct corpus cases identical, Human UAT passed, and no user-visible behavior changed.
- RC43 reduced `pattern_translator/app.py` by approximately 759 lines.
- RC44 completed the third local Engine Extraction by moving Diagnostic Report construction and formatting into `pattern_translator/engine/diagnostic_report.py`.
- RC44 reduced `pattern_translator/app.py` from approximately 5432 lines to approximately 4462 lines.
- RC44 regression confirmed zero-byte representative Diagnostic Report diff, identical translation/TXT regressions, unchanged existing regression corpus, Human UAT passed, and no user-visible behavior changed.
- RC44 Human UAT found a missing `_debug_cell` helper reference during OCR diagnostic metadata generation. A local hotfix restored the helper only where required in `app.py`, while the Diagnostic Report Engine retained its own private helper; repeated Human UAT passed.
- Engine extraction remains local only: no production deployment and no GitHub push. RC28 remains the current production baseline.
- Regression evidence is stored under `regression/regression_test/Reports/`.

## Current Project Status

- Official production baseline: `RC28`
- Current app version string: `Pattern OCR Translator (Beta RC26)`
- Current phase: phased post-Streamlit migration preparation
- Latest local extraction: `RC44` diagnostic report engine extraction completed and Human UAT passed.
- Current production database: `knowledge_base/data/master_stitches.csv`
- Current focus: preserve RC28 as the Railway production baseline, begin migration locally only, and separate business logic from Streamlit before replacing the frontend.
- Future testing: continue with occasional trusted-user testing and incremental fixes based on production evidence. Plan for a Soft Launch after Landing Page completion instead of another formal External UAT cycle.

Known non-blocking polish items:

- Version number is not currently shown in the UI.
- Minor overlay text box alignment refinement is deferred.

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

Railway is the primary production deployment platform after RC28 production validation. Streamlit Community Cloud is retained as a backup platform.

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

RC40 approved a phased post-Streamlit migration for Pattern Translator. The migration starts locally only and should not change GitHub, Railway production, or the Streamlit backup path until validated.

The first migration objective is to separate OCR, parser, translation, overlay, diagnostics, analytics integration, and knowledge-base access from Streamlit UI/session code. RC28 on Railway remains the production rollback target throughout migration.

See:

```text
docs/FUTURE_ARCHITECTURE.md
```
