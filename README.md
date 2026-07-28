# Crochet Intelligence

Repository for the current Crochet Intelligence applications.

## Applications

- `pattern_translator/app.py`  
  Crochet Pattern OCR Translator for image OCR, translation overlays, TXT export, and diagnostic reports.

- `stitch_translator/app.py`  
  Crochet Stitch Translator for dictionary-style stitch lookup.

Both applications remain independent. They now share the same production stitch database.

## Current Cross-App Priorities

Current focus:

- Pattern Translator RC26 is the current stable local build.
- Whole Pattern is now the default Pattern Translator workflow.
- Select Area remains available as an optional / experimental workflow.
- RC26 passed local developer validation and Human UAT.
- RC26 is intentionally local only: no commit, no push, and no Streamlit Community Cloud deployment.
- RC27a Railway preparation completed.
- RC27b Railway deployment spike passed.
- Railway is validated as the preferred production deployment platform for Pattern Translator.
- Pattern Translator successfully runs on Railway using Docker.
- PaddleOCR, Google Sheets analytics, downloads, overlay generation, restart validation, and post-restart OCR all passed on Railway.
- Railway Hobby resource usage during the spike was suitable for low-volume production: peak RAM approximately 1.84 GB, normal RAM approximately 1.29 GB, and peak CPU approximately 1.39 vCPU.
- Streamlit Community Cloud is retained temporarily as a backup platform during migration.
- Pattern Translator Feedback Form migration to `crochetintelligence@gmail.com` is complete.
- Pattern Translator analytics is implemented and validated, but `app_open` duplicate passive entries are a known Streamlit Community Cloud lifecycle limitation. The analytics model will be revisited after migration to a new deployment platform.

Next:

- Upgrade Analytics to v2.
- Prepare the Railway production deployment path.
- Decide where the Crochet Intelligence landing page should be hosted after the Railway production path is clearer.
- Add the reusable analytics implementation to Crochet Stitch Translator.

Later:

- Continue incremental trusted-user testing and prepare for Soft Launch.

## Shared Knowledge Base

The shared database lives at:

```text
knowledge_base/data/master_stitches.csv
```

The accepted source snapshot is archived at:

```text
knowledge_base/releases/database/stitches_1_8e.csv
```

Symbol assets live at:

```text
knowledge_base/symbols/
```

## Run Locally

Pattern Translator:

```bash
python3 -m streamlit run pattern_translator/app.py
```

Stitch Translator:

```bash
python3 -m streamlit run stitch_translator/app.py
```

## Deployment Workflow

Recommended Pattern Translator workflow:

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

Streamlit Community Cloud is no longer the primary deployment direction for Pattern Translator, but remains a temporary backup during migration.

## Documentation

- `knowledge_base/DATABASE.md`
- `knowledge_base/CSV_SPEC.md`
- `docs/FUTURE_ARCHITECTURE.md`
- each app's `README.md`
- each app's `PROJECT_STATUS.md`

Regression assets live under `regression/`.
