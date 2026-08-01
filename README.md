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
- Pattern Translator analytics is implemented and validated. Human-visit and `app_open` event-quality cleanup remains deferred until the Landing Page can provide browser analytics.
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
- RC46 completed local Overlay Rendering Engine extraction into `pattern_translator/engine/overlay.py`.
- Overlay rendering is now independent of Streamlit, and the Streamlit UI calls the Overlay Engine directly without a compatibility wrapper.
- RC46 reduced `pattern_translator/app.py` from approximately 4229 lines to approximately 3789 lines.
- RC46 validation confirmed byte-identical overlay PNG output, identical overlay pixels, identical overlay legends, identical translation/TXT/Diagnostic Report regressions, and `220 / 220` direct corpus outputs; Human UAT passed, and no user-visible behavior changed.
- RC47 completed local Pattern Document Engine extraction into `pattern_translator/engine/pattern_document.py`.
- Pattern Document responsibilities now include pattern noise filtering, section detection, section grouping, readable section formatting, and pattern export construction.
- `pattern_translator/app.py` delegates Pattern Document responsibilities directly to the engine without compatibility wrappers.
- RC47 validation confirmed identical translation, TXT export, section export, pattern export, Diagnostic Report, overlay PNG bytes, overlay pixels, overlay legends, and `220 / 220` direct corpus outputs; Human UAT passed.
- RC48 completed local OCR Line Assembly Engine extraction into `pattern_translator/engine/ocr_lines.py`.
- OCR visual-line merging, cluster assembly, and translated line-record construction now belong to the OCR Line Assembly Engine.
- RC48 reduced `pattern_translator/app.py` from 3,089 lines to 2,971 lines.
- RC48 validation confirmed identical stored OCR-line fixtures and intermediate line records, with identical overlay, TXT, Pattern Export, and Diagnostic Report outputs; automated regression and Human UAT passed.
- RC49 completed local OCR Cleanup Engine extraction into `pattern_translator/engine/ocr_cleanup.py`.
- RC49 extracted `clean_ocr_text()` and `normalize_pattern_rounds()` and reduced `pattern_translator/app.py` from 2,971 lines to 2,868 lines.
- RC49 validation confirmed identical OCR cleanup fixtures, round normalization, stored OCR fixtures, overlay, TXT, Pattern Export, and Diagnostic Report outputs; the `220 / 220` translation corpus and Human UAT passed.
- Engine Migration is complete. The Streamlit-independent Pattern Translator engines are `terminology`, `line_translation`, `diagnostic_report`, `overlay`, `pattern_document`, `ocr_lines`, and `ocr_cleanup`.
- Remaining `app.py` responsibilities are intentionally application, framework, and runtime concerns: Streamlit UI, application orchestration, OCR runtime/provider lifecycle, session state, downloads, analytics, localization, Cropper / Select Area, and runtime infrastructure.
- Domain Layer extraction is complete. Application Layer separation is deferred until it provides clear product value.
- Engine extraction remains local only: no production deployment and no GitHub push. RC28 remains the current production baseline.
- RC50A proved the custom upload boundary, and RC50B completed the production custom uploader using Streamlit Components V1.
- The upload path remains `custom uploader -> BytesIO -> image_upload_signature() -> Image.open()`, preserving OCR, translation, overlay, diagnostics, exports, and the analytics schema.
- The uploader supports JPG, JPEG, PNG, and WebP; four interface languages; native mobile image selection; desktop drag-and-drop; Replace and Remove; and light and dark modes.
- The 25 MB limit is intentional because Components V1 transports the image as base64. Physical iPhone Safari and Android Chrome Human UAT passed with no functional regression.
- Unrelated-image handling was validated and the no-crochet-content message was improved. Streamlit still provides the runtime, session state, and component communication; RC50 replaced one native Streamlit UI widget.
- Visual branding, the corporate colour palette, logo work, GIF/onboarding guidance, and upload-button restyling remain deferred until the separate visual identity decision.

Next:

- Move to the next confirmed UI/UX limitation after the separate visual identity decision.
- Keep the completed Engine Migration local until a future integration decision is approved.
- Focus future work on product features, runtime improvements, deployment, or Application Layer work when justified by clear product value.
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
