# Crochet Pattern Translator Project Status

Last updated: 2026-08-01

## Current Version

Production baseline: `RC28`

Application version string: `Pattern OCR Translator (Beta RC26)`

Entry point:

```text
pattern_translator/app.py
```

## Current Production Status

Crochet Pattern OCR Translator is the current OCR-based pattern translation app. RC28 is the current production baseline. The first External UAT phase has concluded with positive results from real crochet users. Railway is now the primary production deployment platform.

RC42 completed the first local Engine Extraction by moving the CSV terminology / lookup engine into `pattern_translator/engine/terminology.py`. RC43 extracted pure line-translation logic into `pattern_translator/engine/line_translation.py`. RC44 extracted Diagnostic Report construction and formatting into `pattern_translator/engine/diagnostic_report.py`. RC45 completed Boundary Cleanup. RC46 extracted overlay rendering into `pattern_translator/engine/overlay.py`. RC47 extracted Pattern Document responsibilities into `pattern_translator/engine/pattern_document.py`. RC48 extracted OCR line assembly into `pattern_translator/engine/ocr_lines.py`. RC49 extracted deterministic OCR cleanup into `pattern_translator/engine/ocr_cleanup.py`, completing Engine Migration and Domain Layer extraction. Regression and Human UAT passed with no user-visible behavior changes. Engine migration remains local only with no production deployment and no GitHub push.

RC50A completed the custom uploader technical spike. RC50B replaced the native Streamlit file uploader with a production Streamlit Components V1 uploader while preserving the existing Python and domain-engine boundary. Physical iPhone Safari and Android Chrome Human UAT passed with no functional regression. RC50 remains local only; RC28 remains the production baseline.

## Current Database

Production database:

```text
knowledge_base/data/master_stitches.csv
```

Accepted source snapshot:

```text
stitches_1_8e.csv
```

## Completed Features

- Anonymous Google Sheets Usage Analytics for Pattern Translator events.
- Mobile-first upload and Select Area workflow.
- OCR-based pattern text extraction.
- Pattern translation with CSV terminology and parser-assisted instruction handling.
- Overlay PNG export.
- Translation TXT export.
- Diagnostic Report export and feedback workflow.
- Streamlit Components V1 custom image uploader with native mobile selection, desktop drag-and-drop, Replace and Remove, multilingual text, and light/dark theme support.
- Regression framework with real-world pattern evidence.

## Current Priorities

Current Phase: Phase 2 – Streamlit Constraint Audit & Future UI Strategy.

Purpose:

- Identify every UI/UX limitation caused by Streamlit.
- Determine which limitations can be solved within Streamlit.
- Determine which limitations require a different frontend.
- Produce future frontend requirements before selecting any new framework.

Roadmap decisions:

- Preserve RC28 as the current Railway production baseline and rollback target.
- Keep the completed Engine Migration and Domain Layer extraction local until further approval.
- Analytics cleanup is intentionally deferred.
- Do not pursue `app_open` cleanup before the Landing Page.
- Address human-visit analytics after the Landing Page exists, using browser analytics.
- Frontend technology remains intentionally undecided until Phase 2 is complete; React has not been selected.
- Continue occasional testing with trusted users and incremental fixes based on real production usage.
- Keep OCR, parser, overlay, and database changes small and evidence-based.
- Preserve the shared database strategy with Crochet Stitch Translator.

## Landing Page Strategy

The Landing Page is a separate product from Pattern Translator.

The default assumption is that the Landing Page will not be built with Streamlit. It is expected to provide:

- marketing;
- human visitor analytics;
- a CTA funnel;
- browser analytics, currently planned with Plausible.

## Known Issues

- Android overlay font may appear relatively small.
- Version number is not currently shown in the UI.
- Minor overlay text box alignment refinement is deferred.
- JellyCat 元寶 overlay placement has a minor cosmetic placement difference. Translation correctness, anchor position, readability, and functionality are unaffected; this is future overlay placement tuning rather than an RC47 regression.

## Current Release Notes

### RC50

- RC50A validated the technical upload boundary; RC50B completed the production custom uploader.
- Architecture: `custom uploader -> BytesIO -> image_upload_signature() -> Image.open()`. OCR, translation, overlay, diagnostics, exports, and the analytics schema were preserved.
- Formats and interaction: JPG, JPEG, PNG, and WebP; four interface languages; native mobile picker; desktop drag-and-drop; Replace and Remove; light and dark modes.
- Limit: 25 MB is intentional because Streamlit Components V1 uses base64 transport.
- Validation: physical iPhone Safari and Android Chrome Human UAT passed; real image upload and downstream workflows passed; unrelated-image/no-crochet-content handling was validated and its message improved; no functional regression was observed.
- Boundary: one native Streamlit UI widget has been replaced. Streamlit still owns runtime, session state, and component communication.
- Deferred: visual branding, corporate colour palette, logo work, GIF/onboarding guidance, and upload-button restyling await the separate visual identity decision.
- Status: RC50 complete locally. The project is ready to move to the next UI/UX limitation after that visual identity decision. No production deployment or GitHub push; RC28 remains the production baseline.

### RC49

- Mission: final local Engine Extraction for deterministic OCR cleanup.
- Scope: extract `clean_ocr_text()` and `normalize_pattern_rounds()` into `pattern_translator/engine/ocr_cleanup.py`.
- App impact: `pattern_translator/app.py` reduced from 2,971 lines to 2,868 lines.
- Validation: automated regression passed; Human UAT passed; OCR cleanup fixtures, round normalization, and stored OCR fixtures were identical; overlay, TXT, Pattern Export, and Diagnostic Report outputs remained identical; `220 / 220` translation corpus cases were identical.
- Architecture: Engine Migration and Domain Layer extraction are complete. The seven Streamlit-independent engines are `engine/terminology.py`, `engine/line_translation.py`, `engine/diagnostic_report.py`, `engine/overlay.py`, `engine/pattern_document.py`, `engine/ocr_lines.py`, and `engine/ocr_cleanup.py`.
- Intentional boundary: Streamlit UI, application orchestration, OCR runtime/provider lifecycle, session state, downloads, analytics, localization, Cropper / Select Area, and runtime infrastructure remain in `app.py` because they are application, framework, or runtime responsibilities rather than domain-engine responsibilities.
- Future direction: product features, runtime improvements, deployment, or Application Layer work may proceed when justified. Application Layer separation is deferred until it provides clear product value.
- Behavior: no user-visible behavior changes.
- Release handling: local only. No production deployment and no GitHub push. RC28 remains the current production baseline.

### RC48

- Mission: local OCR Line Assembly Engine extraction after RC47 Pattern Document Engine extraction.
- Scope: extract `merge_ocr_boxes_into_visual_lines()`, `_merge_ocr_cluster()`, and `build_ocr_line_translations()` into `pattern_translator/engine/ocr_lines.py`.
- Architecture: OCR visual-line grouping and translated line-record construction are now independent of Streamlit. The six Streamlit-independent engines are `engine/terminology.py`, `engine/line_translation.py`, `engine/ocr_lines.py`, `engine/pattern_document.py`, `engine/overlay.py`, and `engine/diagnostic_report.py`.
- App impact: `pattern_translator/app.py` reduced from 3,089 lines to 2,971 lines.
- Validation: automated regression passed; Human UAT passed; stored OCR fixtures and intermediate OCR-line records were identical; overlay, TXT, Pattern Export, and Diagnostic Report outputs remained identical.
- Behavior: no user-visible behavior changes.
- Release handling: local only. No production deployment and no GitHub push. RC28 remains the current production baseline.
- Architecture status at RC48: Engine Migration entered its final stage, completed subsequently by RC49.

### RC47

- Mission: local Pattern Document Engine extraction after RC46 Overlay Rendering Engine extraction.
- Scope: extract pattern noise filtering, section detection, section grouping, readable section formatting, and pattern export construction into `pattern_translator/engine/pattern_document.py`.
- Architecture: Pattern Document responsibilities are now independent of Streamlit and encapsulated in the engine layer. `app.py` delegates directly to the Pattern Document Engine without compatibility wrappers. Current engine modules are `engine/terminology.py`, `engine/line_translation.py`, `engine/diagnostic_report.py`, `engine/overlay.py`, and `engine/pattern_document.py`.
- Validation: automated regression passed; Human UAT passed; translation, TXT export, section export, pattern export, Diagnostic Report, overlay PNG bytes, overlay pixels, overlay legend, and `220 / 220` direct corpus outputs were identical.
- Known validation limitation: OCR was intentionally not rerun during automated regression because RC47 only extracted Pattern Document responsibilities.
- Human UAT note: JellyCat 元寶 overlay placement shows a minor cosmetic placement difference. Translation correctness, anchor position, readability, and functionality are unaffected. This is recorded as future Overlay placement tuning rather than an RC47 regression.
- Behavior: no user-visible behavior changes.
- Release handling: local only. No production deployment and no GitHub push. RC28 remains the current production baseline.
- Architecture status: Engine Migration is now in the late stage following RC47. A fresh post-RC47 architecture assessment will determine whether additional engine extraction is warranted or whether the project should transition to the next architectural phase.

### RC46

- Mission: local Overlay Rendering Engine extraction after RC45 Boundary Cleanup.
- Scope: extract overlay rendering responsibilities into `pattern_translator/engine/overlay.py`.
- Architecture: overlay rendering is now independent of Streamlit. The Streamlit UI calls the Overlay Engine directly, and no compatibility wrapper was retained because no Streamlit-specific behavior was required. Current engine modules are `engine/terminology.py`, `engine/line_translation.py`, `engine/diagnostic_report.py`, and `engine/overlay.py`.
- App impact: `pattern_translator/app.py` reduced from approximately 4229 lines to approximately 3789 lines.
- Validation: automated regression passed; Human UAT passed; overlay PNG byte comparison passed; overlay pixel comparison passed; overlay legend comparison passed; translation regression, TXT regression, Diagnostic Report regression, and `220 / 220` direct corpus outputs were identical.
- Known validation limitation: OCR was intentionally not rerun during automated regression because RC46 only refactored overlay rendering.
- Behavior: no user-visible behavior changes.
- Release handling: local only. No production deployment and no GitHub push. RC28 remains the current production baseline. RC46 is another major milestone in the ongoing Engine Migration, but Engine Migration is not complete.
- Remaining `app.py` responsibilities are increasingly concentrated around application orchestration, OCR, session management, localization, downloads, and Streamlit integration.

### RC45

- Mission: local Boundary Cleanup after RC44 Diagnostic Report Engine extraction.
- Scope: remove redundant pass-through wrappers between `app.py` and the existing engine modules; update internal call sites to invoke the owning engine directly where appropriate.
- Architecture: `engine/terminology.py`, `engine/line_translation.py`, and `engine/diagnostic_report.py` now own their extracted business logic more clearly. `app.py` primarily contains application orchestration, Streamlit integration, OCR, overlay rendering, session state, and remaining application-specific responsibilities.
- App impact: `pattern_translator/app.py` reduced from approximately 4468 lines to approximately 4229 lines, a net reduction of approximately 239 lines.
- Validation: translation regression identical; TXT regression identical; Diagnostic Report regression identical; `220 / 220` direct corpus outputs identical; Human UAT passed.
- Behavior: no user-visible behavior changes.
- Release handling: local only. No production deployment and no GitHub push. RC28 remains the current production baseline.

### RC44

- Mission: third Engine Extraction RC after RC43 line translation extraction.
- Scope: extract Diagnostic Report construction and formatting into `pattern_translator/engine/diagnostic_report.py`.
- App impact: `pattern_translator/app.py` reduced from approximately 5432 lines to approximately 4462 lines.
- Validation: representative Diagnostic Report diff was zero bytes; translation regression and TXT regression were identical; the existing regression corpus was unchanged; Human UAT passed.
- Human UAT finding: a missing `_debug_cell` helper reference caused a NameError during OCR diagnostic metadata generation. The hotfix restored `_debug_cell` only where required inside `app.py`, while the Diagnostic Report Engine retained its own private helper. Repeated Human UAT passed.
- Behavior: no user-visible behavior changes.
- Release handling: local only. No production deployment and no GitHub push. RC28 remains the current production baseline.

### RC43

- Mission: second Engine Extraction RC after RC42 terminology extraction.
- Scope: extract pure line-translation logic into `pattern_translator/engine/line_translation.py`.
- App impact: `pattern_translator/app.py` reduced by approximately 759 lines.
- Validation: automated regression confirmed `220 / 220` direct corpus cases identical; Human UAT passed.
- Behavior: no user-visible behavior changes.
- Release handling: local only. No production deployment and no GitHub push. RC28 remains the current production baseline.

### RC42

- Mission: first Engine Extraction RC after RC41 architecture analysis.
- Scope: extract only the CSV terminology / lookup engine into `pattern_translator/engine/terminology.py`.
- Cache handling: Streamlit cache behavior intentionally preserved through app-level wrappers.
- Validation: automated regression confirmed `209 / 209` translation cases identical; Human UAT passed.
- Behavior: no user-visible behavior changes.
- Release handling: local only. No production deployment and no GitHub push. RC28 remains the current production baseline.

### RC28

- Mission: finalize Railway production release after RC26 Whole Pattern default workflow, RC27 Railway migration, and the Diagnostic Report download hotfix.
- Status: completed.
- Diagnostic Report fix: Railway session-state regression after Diagnostic Report download was fixed by preventing the Diagnostic Report download button from triggering a Streamlit rerun.
- Validation: local validation passed, Railway production deployment passed, and Railway Desktop Human UAT passed.
- Production baseline: RC28 is now the Pattern Translator production baseline.
- Deployment platform: Railway is now the primary production deployment platform. Streamlit Community Cloud remains available as a backup platform.
- Non-blocking items: version number is not currently shown in the UI; minor overlay text box alignment refinement is deferred.

### RC40 Architecture Decision

- Decision: begin a phased post-Streamlit migration after RC40 architecture review.
- Rationale: RC28 is a stable production baseline, and RC30b confirmed Streamlit is now the primary architectural limitation rather than Railway.
- Migration rule: start locally only. Do not create a GitHub migration branch, push, deploy, or change production until local extraction work has been reviewed and validated.
- First objective: separate OCR, parser, translation, overlay, diagnostics, analytics integration, and knowledge-base access from Streamlit UI/session code while preserving current behavior.
- Rollback target: RC28 Railway production remains the fully recoverable production path.

### External UAT Phase 1

- Status: completed.
- Core OCR and translation workflow was successfully validated by real crochet users.
- Overlay translation concept was validated.
- Google Sheets analytics successfully collected real-world usage data.
- Primary remaining issues are UX improvements rather than translation accuracy.
- Whole Pattern mode proved more reliable than Select Area in real-world testing. Translation speed difference between Whole Pattern and Select Area is small, and Whole Pattern provides better future opportunities for overlay placement improvements.
- Decision: Whole Pattern is the default workflow. Select Area remains available as an advanced / experimental feature until future deployment platform improvements make the cropper more reliable.

### RC26

- Mission: restore Whole Pattern as the default workflow while preserving Select Area as an optional advanced / experimental feature.
- Status: completed locally.
- Validation: passed local developer validation and Human UAT.
- Release handling: intentionally local only. No commit, no push, and no Streamlit Community Cloud deployment for RC26.
- Analytics decision at RC26: restored the original `app_open` semantics. The current Phase 2 decision supersedes the earlier platform-migration timing assumption: `app_open` cleanup is deferred until the Landing Page can provide browser analytics.

### RC27

- Mission: select and validate the long-term deployment platform.
- RC27a: Railway deployment preparation completed with Docker-based deployment support.
- RC27b: Railway deployment spike passed.
- Result: Railway is validated as the preferred production deployment platform for Pattern Translator.
- Evidence: Pattern Translator ran successfully on Railway using Docker. PaddleOCR initialization, Pattern_001 Whole Pattern OCR, English HDC OCR, translation, overlay PNG export, TXT export, Google Sheets analytics append, feedback link configuration, restart validation, and post-restart OCR all passed.
- Railway Hobby resource usage during the spike: peak RAM approximately `1.84 GB`, normal RAM approximately `1.29 GB`, peak CPU approximately `1.39 vCPU`.
- Cost assessment: observed Railway usage is suitable for low-volume production.
- Deployment direction: Railway is now the production deployment direction. Streamlit Community Cloud is retained temporarily as a backup platform during migration.

### RC25

- Mission: prepare the latest Pattern Translator release for deployment with analytics infrastructure merged.
- Includes: RC24c translation lookup performance optimization, anonymous Google Sheets usage analytics, current shared master database, and migrated company-owned Feedback Form URL.
- Analytics status: completed and validated on Streamlit Cloud.
- Analytics implementation: Google Sheets writes use `open_by_key()`, removing the Google Drive API dependency.
- Feedback workflow: single-step Feedback link opens the company-owned Google Form directly.

### RC24c

- Mission: optimize only repeated DataFrame row retrieval inside the translation lookup path.
- Root cause: repeated `df.loc[...]` pandas row retrieval during translation caused excessive time in `lookup_row()`.
- Change: a lightweight precomputed row lookup cache replaced repeated DataFrame row retrieval while preserving the same lookup indexes and row IDs.
- Evidence: slow English HDC benchmark improved from `84.091s` to `24.215s` (~71% faster); normal Fisherman Hat benchmark improved from `22.272s` to `4.208s` (~81% faster).
- Regression: translation output and overlay export output showed no differences; multi-language smoke checks passed.
- Human UAT: passed. The project owner confirmed the app feels substantially faster in real use.
- Status: accepted stable performance baseline included in RC25. No further performance optimization is planned unless new real-world evidence shows another bottleneck.

### RC21 Infrastructure: Google Sheets Usage Analytics

- Mission: add anonymous Google Sheets usage analytics for Pattern Translator without changing OCR, parser, translation, overlay, Select Area, or CSV behavior.
- Status: completed. Analytics has been validated on Streamlit Cloud.
- Destination: `Crochet Intelligence Usage Analytics` spreadsheet, `pattern_translation` worksheet.
- Events: `app_open`, `image_uploaded`, `select_area_started`, `select_area_confirmed`, `translation_completed`, `translation_failed`, `download_png`, and `download_txt`.
- Privacy: only anonymous usage statistics are collected, including country, app usage, and performance. IP addresses, personal information, uploaded images, OCR text, and translations are not stored in analytics.
- Fail-safe rule: analytics failures must never interrupt OCR, translation, downloads, or feedback workflow.
- Feedback migration: Pattern Translator Feedback Form migration to `crochetintelligence@gmail.com` is complete.

## Future Work

After Phase 2:

1. Build the Landing Page.
2. Migrate Stitch Translator to Railway.
3. Introduce shared infrastructure improvements when appropriate.
4. Evaluate future frontend frameworks only if Phase 2 demonstrates that Streamlit is the limiting factor.

Additional deferred work:

- Improve discoverability of editable line-by-line translation before TXT download. The feature already exists, but users may not realise the translation text can be edited before downloading. Consider clearer UI guidance in a future UX enhancement; implementation is not scheduled now.
- Revisit human-visit and `app_open` analytics after the Landing Page browser-analytics foundation exists.
- Review the Google Feedback Form questions and workflow.
- Reuse the improved analytics and feedback design when implementing Stitch Translator analytics.

### RC23b Hotfix 1

- Root cause: RC23b Mission 1 changed `streamlit-cropper` to `realtime_update=False`, which made crop coordinates update only after a cropper double-click event. On touch devices, pressing **Use This Area** could therefore confirm stale crop coordinates.
- Engineering decision: restore `realtime_update=True` because Select Area correctness has higher priority than cropper smoothness.
- Resolution: visible crop rectangle, confirmed crop area, selected-area preview, and OCR input are expected to synchronize again. Human UAT is still required on iPhone Safari and Android.

### RC23c

- Mission: simplify the mobile Select Area workflow without changing OCR, parser, translation, overlay, diagnostics, image quality, or crop coordinate calculations.
- UX decision: move the primary **Cancel** / **Use This Area** controls above the interactive cropper so mobile users do not need to scroll through the touch-capturing cropper to confirm a selection.
- Workflow simplification: remove the repeated full-image dimmed crop confirmation preview. The final cropped-area preview remains before OCR.
- Cropper visual polish: increase the supported cropper border stroke width for better visibility. The current cropper library does not expose a supported resize-handle size option.

### RC23d

- Mission: final mobile Select Area polish after Human UAT.
- Cropper visual polish: reduce Select Area crop border stroke width from `5` to `4` because Human UAT found width `5` too thick for small or dense pattern text.
- Wording polish: rename the Select Area editing **Cancel** button to **Start Over** so the action more clearly communicates abandoning the current draft selection.
- Deferred limitation: crop handle visibility remains a current Streamlit / `streamlit-cropper` frontend limitation. No CSS or JavaScript workaround is planned before a future frontend migration.
- Accepted limitation: Android cropper rerender flash remains accepted for now.

## Important Design Decisions

- Parser rules handle instructions; the CSV remains the source of truth for terminology.
- Accepted RCs become the Current Reference Build only after regression and Human UAT.
- Regression evidence should include raw outputs, not only summaries.
- Shared Python modules for Pattern Translator may now be introduced only as part of the approved local post-Streamlit migration, beginning with business-logic extraction from Streamlit.
