# Crochet Pattern Translator Project Status

Last updated: 2026-07-28

## Current Version

Application version: `Pattern OCR Translator (Beta RC26)`

Entry point:

```text
pattern_translator/app.py
```

## Current Production Status

Crochet Pattern OCR Translator is the current OCR-based pattern translation app. RC26 is the current stable local build. The first External UAT phase has concluded with positive results from real crochet users. RC27 validated Railway as the preferred production deployment platform.

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

Current Phase: Railway migration preparation after RC27 validation.

Current focus:

1. Prepare the production migration path on Railway.
2. Keep Streamlit Community Cloud temporarily as a backup platform during migration.
3. Revisit Analytics v2 and landing-page hosting decisions after the Railway production path is ready.

- Continue occasional testing with trusted users and incremental fixes based on real production usage.
- Plan for a Soft Launch after Landing Page completion instead of another formal External UAT cycle.
- Keep OCR, parser, overlay, and database changes small and evidence-based.
- Preserve the shared database strategy with Crochet Stitch Translator.

## Known Issues

- Android overlay font may appear relatively small.
- A download session reset was observed once on iPhone Safari and remains under monitoring.

## Current Release Notes

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
- Shared Python modules are intentionally postponed until after a future platform migration.
