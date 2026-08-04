# Crochet Intelligence

Repository for the current Crochet Intelligence applications.

## Applications

- `portal/`
  Streamlit-independent Astro Portal and current Crochet Intelligence platform entry point.

- `pattern_translator/app.py`
  Crochet Pattern OCR Translator for image OCR, translation overlays, TXT export, and diagnostic reports.

- `stitch_translator/app.py`
  Crochet Stitch Translator for dictionary-style stitch lookup.

Pattern Translator and Stitch Translator remain independent, equally important tools. They share the same production stitch database and are reached through the Portal.

## Current Cross-App Priorities

Current focus:

- The Portal Skeleton is functionally complete and frozen after Human UAT. Its Information Architecture is finalized; visual refinement and branding are scheduled after Platform Analytics.
- The Astro Portal is independent of Streamlit and is now the platform entry point. Streamlit is no longer required for the platform entry page.
- The Portal currently supports English, Traditional Chinese, Simplified Chinese, and Japanese; configurable tool routing; inline Privacy & Terms; and a contact email link.
- Pattern Translator and Stitch Translator are presented as equal tools. Two future-tool entries remain available through configuration but are hidden from the current UI.
- The Portal has been deployed independently to Railway and is now the primary platform entry point: `https://crochet-intelligence-portal-production.up.railway.app`.
- RC54 Phase 1 integrated Plausible Starter into the Portal. Human UAT confirmed Portal pageview tracking and the `portal_pattern_selected` custom event.
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
- Pattern Translator's existing tool analytics remains implemented and validated. RC54 Phase 1 added the Portal Plausible foundation; remaining Pattern Translator and Stitch Translator analytics events are planned for RC54 Phase 2.
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
- Phase A Brand Identity Foundation is complete. `Brand identity & UI/UI_SPEC.md` is the authoritative Living Design Specification for shared Crochet Intelligence UI work.
- RC51 completed the first Phase B implementation. Physical-iPhone Human Visual UAT approved the Pattern Translator Home Screen, custom uploader, privacy card, and equal secondary treatment for Replace and Remove as the current baseline. Product workflows and domain behavior remain unchanged.
- The selected Streamlit radio state uses the supported `theme.primaryColor` setting with Primary Teal; the top-right menu uses supported minimal-toolbar configuration.
- RC52 completed the custom Select Area boundary using Streamlit Components V1. Selecting Select Area now opens the cropper immediately, without the duplicate preview or extra launch step.
- The custom cropper provides browser-local editing, four edge handles, a Precision Arrow Pad, distinct Reset and Start Over flows, immediate OCR-running feedback, and light/dark theme support.
- RC52 Human UAT passed on physical iPhone Safari, Android Chrome, and Desktop Chrome. The custom uploader and cropper demonstrate that targeted Streamlit UI limitations can be overcome with supported custom components while preserving the existing Python processing pipeline.
- Future UI work follows the Product-driven approval workflow in `ENGINEERING_RULES.md`, with `UI_SPEC.md` updated only after Human Visual UAT and explicit Product Owner approval.
- Logo work and GIF/onboarding guidance remain deferred.

Next:

- Implement RC54 Phase 2: add the remaining approved analytics events for Pattern Translator and Stitch Translator using the validated browser-side analytics transport.
- Keep the Portal Skeleton architecture and Information Architecture stable while analytics work proceeds.
- Keep Google Sheets Product Facts as a later RC54 milestone; they are intentionally not implemented yet.
- Defer Portal visual polish and branding until after analytics.
- RC52 remains frozen as a production-ready local release. Do not add further cropper polish unless a functional regression is found.
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

Portal:

```bash
cd portal
npm install
npm run dev
```

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

## Platform Architecture

The Portal is an independent Astro application and the permanent platform entry point. It is deployed to Railway at `https://crochet-intelligence-portal-production.up.railway.app`. It routes to Pattern Translator and Stitch Translator without coupling their implementations to the Portal. New tools should be enabled through the Portal's tool configuration rather than through an Information Architecture redesign.

Pattern Translator remains a Streamlit application, and its current RC28 Railway deployment remains the production baseline and rollback target.

## Documentation

- `knowledge_base/DATABASE.md`
- `knowledge_base/CSV_SPEC.md`
- `docs/FUTURE_ARCHITECTURE.md`
- `ANALYTICS_SCHEMA.md`
- each app's `README.md`
- each app's `PROJECT_STATUS.md`

Regression assets live under `regression/`.
