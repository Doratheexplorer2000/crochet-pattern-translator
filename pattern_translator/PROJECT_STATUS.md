# Crochet Pattern Translator Project Status

Last updated: 2026-07-30

## Current Version

Production baseline: `RC28`

Application version string: `Pattern OCR Translator (Beta RC26)`

Entry point:

```text
pattern_translator/app.py
```

## Current Production Status

Crochet Pattern OCR Translator is the current OCR-based pattern translation app. RC28 is the current production baseline. The first External UAT phase has concluded with positive results from real crochet users. Railway is now the primary production deployment platform.

RC42 completed the first local Engine Extraction by moving the CSV terminology / lookup engine into `pattern_translator/engine/terminology.py`. RC43 completed the second local Engine Extraction by moving pure line-translation logic into `pattern_translator/engine/line_translation.py`. Regression confirmed `220 / 220` direct corpus cases identical, Human UAT passed, and no user-visible behavior changed. Engine extraction remains local only with no production deployment and no GitHub push.

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
- Regression framework with real-world pattern evidence.

## Current Priorities

Current Phase: phased post-Streamlit migration preparation.

Current focus:

1. Preserve RC28 as the current Railway production baseline and rollback target.
2. Begin migration locally only; no GitHub migration branch, deployment, or production change yet.
3. Continue small, validated Engine Extraction RCs after RC43 before replacing the frontend.
4. Keep Streamlit Community Cloud as a backup platform during migration.

- Continue occasional testing with trusted users and incremental fixes based on real production usage.
- Plan for a Soft Launch after Landing Page completion instead of another formal External UAT cycle.
- Keep OCR, parser, overlay, and database changes small and evidence-based.
- Preserve the shared database strategy with Crochet Stitch Translator.

## Known Issues

- Android overlay font may appear relatively small.
- Version number is not currently shown in the UI.
- Minor overlay text box alignment refinement is deferred.

## Current Release Notes

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
- Analytics decision: restored the original `app_open` semantics. Repeated passive `app_open` rows are treated as a Streamlit Community Cloud lifecycle limitation rather than an analytics implementation bug. Analytics will be revisited after a future platform migration.

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

After platform direction is clearer:

- Analytics v2 should keep raw logs while adding a cleaner summary/dashboard.
- Review and refine the Analytics schema based on real user data.
- Review the Google Feedback Form questions and workflow.
- Reuse the improved analytics/feedback design when implementing Stitch Translator analytics.

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
