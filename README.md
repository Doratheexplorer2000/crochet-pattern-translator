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

- Pattern Translator RC28 is the current production baseline.
- Whole Pattern is now the default Pattern Translator workflow.
- Select Area remains available as an optional / experimental workflow.
- RC26 passed local developer validation and Human UAT.
- RC27a Railway preparation completed.
- RC27b Railway deployment spike passed.
- RC28 Railway production release completed.
- Railway is now the primary production deployment platform for Pattern Translator.
- Pattern Translator successfully runs on Railway using Docker.
- PaddleOCR, Google Sheets analytics, downloads, overlay generation, restart validation, and post-restart OCR all passed on Railway.
- The Diagnostic Report Railway session-state regression was fixed and verified in Railway production.
- Railway production validation and Desktop Human UAT passed.
- Railway Hobby resource usage during the spike was suitable for low-volume production: peak RAM approximately 1.84 GB, normal RAM approximately 1.29 GB, and peak CPU approximately 1.39 vCPU.
- Streamlit Community Cloud is retained as a backup platform.
- Pattern Translator Feedback Form migration to `crochetintelligence@gmail.com` is complete.
- Pattern Translator analytics is implemented and validated, but `app_open` duplicate passive entries are a known Streamlit Community Cloud lifecycle limitation. The analytics model will be revisited after migration to a new deployment platform.
- RC42 completed the first local Engine Extraction by moving the CSV terminology / lookup engine into `pattern_translator/engine/terminology.py`.
- RC43 completed the second local Engine Extraction by moving pure line-translation logic into `pattern_translator/engine/line_translation.py`.
- RC43 regression confirmed `220 / 220` direct corpus cases identical, Human UAT passed, and no user-visible behavior changed.
- RC43 reduced `pattern_translator/app.py` by approximately 759 lines.
- RC44 completed the third local Engine Extraction by moving Diagnostic Report construction and formatting into `pattern_translator/engine/diagnostic_report.py`.
- RC44 regression confirmed zero-byte representative Diagnostic Report diff, identical translation/TXT regressions, unchanged existing regression corpus, Human UAT passed, and no user-visible behavior changed.
- RC44 reduced `pattern_translator/app.py` from approximately 5432 lines to approximately 4462 lines.
- RC45 completed local Boundary Cleanup by removing redundant pass-through wrappers between `app.py` and the engine modules.
- Internal call sites now invoke the owning engine directly where appropriate; Streamlit cache wrappers and genuine application adapters were intentionally retained.
- RC45 reduced `pattern_translator/app.py` from approximately 4468 lines to approximately 4229 lines, a net reduction of approximately 239 lines.
- RC45 regression confirmed identical translation, TXT, Diagnostic Report, and `220 / 220` direct corpus outputs; Human UAT passed, and no user-visible behavior changed.
- Engine extraction remains local only: no production deployment and no GitHub push. RC28 remains the current production baseline.

Next:

- Begin the phased post-Streamlit migration locally only.
- First migration objective: separate Pattern Translator business logic from Streamlit before replacing the frontend.
- Keep the existing RC28 Railway production path fully recoverable as the rollback target.
- Add the reusable analytics implementation to Crochet Stitch Translator.
- Address non-blocking polish items: expose the version number in the UI and refine minor overlay text box alignment.

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

## Migration Strategy

The project has approved a phased post-Streamlit migration as a strategic initiative. Migration starts locally only: no GitHub migration branch, deployment, or production change should occur until the local baseline and first extraction steps have been validated.

The current RC28 Railway deployment remains the production baseline and rollback target. Preserve the production entry point, OCR pipeline, parser and translation logic, overlay generation, shared knowledge base, analytics module, Docker/Railway files, requirements, and current documentation through Git history and a local migration branch rather than duplicating the whole repository.

## Documentation

- `knowledge_base/DATABASE.md`
- `knowledge_base/CSV_SPEC.md`
- `docs/FUTURE_ARCHITECTURE.md`
- each app's `README.md`
- each app's `PROJECT_STATUS.md`

Regression assets live under `regression/`.
