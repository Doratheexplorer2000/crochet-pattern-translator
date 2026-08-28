# Crochet Pattern Translator Project Status

Last updated: 2026-08-28

## Current Version

Current production baseline: known-good pre-cache tree (`c49755b59686e58298febba445e5ae51a6cb6e05`)

Validated equivalent tree: `8dccd17518344d7d2152dc49fc3e13c0e95e3fd0`

Application version string: `Pattern OCR Translator (Beta RC26)`

Entry point:

```text
pattern_translator/app.py
```

## Current Production Status

Crochet Pattern OCR Translator is the current OCR-based pattern translation app at `https://pattern.crochetintelligence.com`. Revert commit `c49755b59686e58298febba445e5ae51a6cb6e05` is deployed from GitHub `main`; its tree is byte-identical to the known-good pre-cache tree at `8dccd17518344d7d2152dc49fc3e13c0e95e3fd0`. It includes the production-validated Portal Centralization, Contextual LLM translation, completed Components V2 analytics, custom-domain, isolated OCR-worker, canonical translation-state, and rerun-safe result-delivery baselines.

RC42 completed the first Engine Extraction by moving the CSV terminology / lookup engine into `pattern_translator/engine/terminology.py`. RC43 extracted pure line-translation logic into `pattern_translator/engine/line_translation.py`. RC44 extracted Diagnostic Report construction and formatting into `pattern_translator/engine/diagnostic_report.py`. RC45 completed Boundary Cleanup. RC46 extracted overlay rendering into `pattern_translator/engine/overlay.py`. RC47 extracted Pattern Document responsibilities into `pattern_translator/engine/pattern_document.py`. RC48 extracted OCR line assembly into `pattern_translator/engine/ocr_lines.py`. RC49 extracted deterministic OCR cleanup into `pattern_translator/engine/ocr_cleanup.py`, completing Engine Migration and Domain Layer extraction. Regression and Human UAT passed with no user-visible behavior changes, and the completed engine layer is included in the current production release.

RC50A completed the custom uploader technical spike. RC50B replaced the native Streamlit file uploader with a production Streamlit Components V1 uploader while preserving the existing Python and domain-engine boundary. Physical iPhone Safari and Android Chrome Human UAT passed with no functional regression. At RC50 closeout, the work remained local and RC28 was the production baseline.

Phase A Brand Identity Foundation is complete. RC51 completed the first Phase B implementation. Physical-iPhone Human Visual UAT approved the Pattern Translator Home Screen as the current baseline, including the custom uploader, privacy card, and equal secondary treatment for Replace and Remove. `Brand identity & UI/UI_SPEC.md` remains the authoritative Living Design Specification; this approval is not a final UI freeze. No product workflow or domain behavior was changed.

RC52 completed the custom Select Area component and finalized the upload-to-crop workflow. Human UAT passed on iPhone Safari, Android Chrome, and Desktop Chrome with no remaining functional issues. At RC52 closeout, the work was production-ready and frozen locally while RC28 was the deployed production baseline.

The independent Astro Portal is the Crochet Intelligence platform entry point. Portal Centralization is completed and closed after Production Human UAT: the Portal owns interface-language selection and general Privacy & Terms, passes canonical `ui_lang` values to both tools, and receives same-tab return navigation with language preservation. RC54 shared Plausible analytics remains closed and production-validated.

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
- Streamlit Components V1 custom Select Area cropper with immediate entry, browser-local editing, a Precision Arrow Pad, and finalized Reset / Start Over behavior.
- Regression framework with real-world pattern evidence.

## Current Priorities

Current Phase: Phase 3A browser UI migration is complete and approved. The approved local baseline is `6c8ab97b0731daa6cd61a4f919aa71cabc856d3b` (`Phase 3A: add FastAPI browser UI`). Phase 3B1 Diagnostic Report parity is next.

Purpose:

- Preserve the approved RC51 Pattern Translator Home Screen and frozen RC52 custom-component baseline.
- Preserve the production-validated RC54B Components V2 analytics transport baseline.
- All five current Pattern Translator Plausible events use the shared Components V2 bridge; no V1 Plausible analytics dependency remains.
- Preserve the shared browser-side analytics implementation across the Portal and both translators while keeping analytics observational and non-blocking.
- Keep Google Sheets Product Facts as separately approved future work; they are not implemented.
- Replace the unreliable Streamlit browser/session delivery boundary in reversible stages while preserving the validated translation engines and product behavior.
- Pause deterministic translation-performance work until the migration is stable.

Phase 1 Translation Service Extraction is complete. Commit `8cd522c696b45ba2025e41588e13ea599232c602` added the framework-neutral `pattern_translator/translation_service.py` application-service boundary and `translate_image()`. Streamlit continues to own UI, session state, request lifecycle, result handoff, rendering, and downloads. OCR, deterministic translation, Luna fallback, overlay/output behavior, and engine algorithms were preserved.

Final validation passed: `210 / 210` automated tests, `220 / 220` deterministic corpus parity, and local iPhone Human UAT. Human UAT confirmed deterministic translation, Whole Pattern and Select Area workflows, result rendering, and PNG/TXT output delivery. Luna was not exercised locally because the server lacked the required fallback/API-key environment configuration; this was an environment/setup issue, not a Phase 1 regression. The visible stale `OCR Running` indicators after completed translation were confirmed as pre-existing same-run Streamlit rendering behavior, not fixed in Phase 1 and not a Phase 1 extraction regression. Phase 1 received final Codex approval for Human UAT before completion.

Local `main` and `origin/main` were synchronized at the Phase 1 commit before this documentation update. Phase 1 Railway deployment is intentionally deferred; production remains on the pre-Phase-1 baseline. The existing Streamlit WebSocket/AppSession reliability issue remains unresolved and is a reason to continue the staged Streamlit removal.

Phase 2 is complete. The minimal FastAPI boundary invokes the existing framework-neutral `translate_image()` service through `POST /api/v1/translate`, with Whole Pattern and Select Area support, multipart image validation, crop validation, downscale parity, JSON translation output, and base64 PNG overlay output. Validation passed with 13 API tests, 30 translation/OCR regression tests, and 223 full-suite tests. Codex independent review returned **PASS WITH NON-BLOCKING NOTES**.

Phase 3A delivered the same-origin FastAPI-served browser UI: Whole Pattern; Select Area cropper and Precision Pad; original-image preview; loading/error recovery; overlay and line-by-line results; PNG/TXT downloads; four-language browser localization; and approved visual/typography parity. Desktop Chrome, iPhone Safari, and Android Chrome Human UAT all passed. Final validation passed `229 / 229` tests. Streamlit production has not been replaced, and no Phase 3A push or deployment occurred.

Deliberate Phase 3A deferrals: Diagnostic Report; image-quality assessment, gating, and force-run; and the download-completion destination popup. The popup absence is accepted as non-blocking/deferred. Image-quality work, gating, and force-run are separate later scope and must not be bundled into Phase 3B1.

Roadmap decisions:

- Preserve `c49755b59686e58298febba445e5ae51a6cb6e05` / the byte-identical `8dccd17518344d7d2152dc49fc3e13c0e95e3fd0` tree as the current Railway rollback target.
- Preserve the completed Engine Migration and Domain Layer extraction now included in the production release.
- Preserve the completed RC54B analytics transport baseline.
- Do not use the unreliable `app_open` event as the basis of platform visitor analytics.
- Plausible is shared across the Portal, Pattern Translator, and Stitch Translator. Production Human UAT confirmed Portal tool-selection analytics and both translators' approved event surfaces.
- Browser-side analytics transport is production-validated across both translators.
- Google Sheets Product Facts are intentionally not implemented yet.
- Continue occasional testing with trusted users and incremental fixes based on real production usage.
- Keep OCR, parser, overlay, and database changes small and evidence-based.
- Preserve the shared database strategy with Crochet Stitch Translator.

## Reliability Blocker And Migration Decision

Production testing on the known-good baseline still showed delayed browser updates and Translate actions that did not reach a backend script run. The corresponding upload backend run completed in approximately `246 ms`, while the visible preview took more than five seconds. Railway logs also recorded duplicate Streamlit AppSession connection messages. This bounds the active blocker to the browser/WebSocket/Streamlit AppSession delivery lifecycle rather than OCR, translation, or the reverted terminology cache, although the exact reconnect trigger remains unproven.

The terminology cache optimization `f7a48a076dbda066577e6117752dd859091cc760` reduced the controlled deterministic workload from about `4.21s` to `1.23s` cold and `1.02s` on immediate repeat with `220 / 220` identical output. It was reverted conservatively after the production interaction failure, but the same failure persisted on the byte-identical pre-cache tree. The optimization is paused, not rejected, and must not be reintroduced or investigated further until the migration is stable.

The approved direction is staged removal of Streamlit from Pattern Translator only:

1. Extract one framework-neutral `translate_image()` application service; the existing Streamlit app continues to call it. **Complete:** commit `8cd522c696b45ba2025e41588e13ea599232c602`.
2. Add a minimal FastAPI API that calls the same service. **Complete:** Phase 2.
3. Migrate the browser UI, uploader, cropper, results, and downloads to the API. **Complete:** Phase 3A, approved local commit `6c8ab97b0731daa6cd61a4f919aa71cabc856d3b`.
4. **Next:** Phase 3B1 Diagnostic Report parity.
5. **Later, separate scope:** Phase 3B2 image-quality assessment, gating, and force-run parity.
6. Cut the existing Pattern Translator Railway service over to FastAPI/Uvicorn without adding another service. **Not started; requires explicit approval.**
7. Complete Production Human UAT, then retire Streamlit lifecycle code only after parity is proven.

Phase 3B1 must begin with Goal, Success Criteria, and Out of Scope, followed by narrow architecture/forensic inspection before implementation. Diagnostic Report was deliberately deferred from Phase 3A; its absence is not a Phase 3A regression. Do not include the separately deferred image-quality assessment, gating, or force-run work in Phase 3B1.

Implementation workflow for this migration: the Product Owner and ChatGPT define scope and acceptance criteria; Cursor implements and validates the approved unit locally without pushing; Codex independently reviews the exact diff and evidence, runs release gates appropriate to risk, and owns commit/push/deployment only after approval.

## Portal Status

The Portal Skeleton is functionally complete and frozen. It is an independent Astro application, so Streamlit is no longer required for the platform entry page.

- Information Architecture finalized after Human UAT.
- Multilingual interface, configurable tool routing, inline Privacy & Terms, and contact email are functional.
- Pattern Translator and Stitch Translator are presented equally.
- Future Tool architecture is retained through configuration but hidden from the current UI.
- The Portal is the primary platform entry point at `https://crochetintelligence.com`; Pattern Translator is at `https://pattern.crochetintelligence.com`; Stitch Translator is at `https://stitch.crochetintelligence.com`.
- RC54 integrated shared Plausible analytics across the Portal and both tools. Production Human UAT passed.
- The Portal owns interface-language selection using `en`, `zh-Hant`, `zh-Hans`, and `ja`; both tools consume the selected language and retain browser-language/English fallback for direct entry.
- General Privacy & Terms are centralized in the Portal. Images are not sent to OpenAI; eligible extracted text and compact semantic context may be sent without identity or analytics identifiers.
- Pattern source/result language controls remain independent. Pattern's duplicate general Privacy UI was removed, while Stitch's tool-specific Google Forms feedback privacy note remains.
- Both tools return to the Portal in the same tab with interface-language preservation. Pattern uses the Crochet Intelligence eyebrow and English title `Crochet Pattern Translator`; Stitch Tutorial Search preserves the submitted stitch term across interface languages.
- All three services run in the Railway project `Crochet Intelligence`. Portal Centralization `5e975741a9a53c1835120f0cdb24a60f5af706b1` and custom-domain migration `22fded0fb39a389b87d767faa494d7ad48d3d799` passed production functional/navigation UAT and Plausible regression validation without analytics changes. RC54 Analytics remains closed with Site Domain `crochetintelligence.com`.
- Portal visual refinement is complete. Pattern Translator's staged Streamlit removal is the highest-priority remaining launch work.

## Known Issues

### Next Priority

1. **Phase 3B1 Diagnostic Report parity.** Begin with Goal, Success Criteria, and Out of Scope, then perform narrow architecture/forensic inspection before implementation. Diagnostic Report was deliberately deferred from Phase 3A, so its absence is not a Phase 3A regression. Do not include image-quality assessment, gating, or force-run; those are deferred Phase 3B2 work.

**Paused performance evidence:** the deterministic anomaly measured approximately `41.06s` total / `36.00s` translation with `0.89s` Paddle inference versus `6.79s` total / `5.70s` translation with `0.88s` Paddle inference after changing target. The controlled cache fix materially improved local deterministic timing and preserved output, but production interaction symptoms persisted after its revert. Resume the audit only after migration stability; dictionary size is not proven as the cause.

### Before Soft Launch

2. **Deterministic translation / dictionary simplification.** After the performance audit, review whether ordinary semantic entries such as Body and Head, historical rules added for weaker earlier LLM behavior, redundant regex/parser work, redundant semantic-context processing, and low-value dictionary entries remain necessary with the current Luna route. Protect translation quality; do not remove entries merely to reduce row count.
3. **OCR progress/status UI.** A completed Translation Result can coexist with a visible `OCR Running...` status because of pre-existing same-run Streamlit rendering behavior. This was investigated during Phase 1 UAT and is not a Phase 1 extraction regression; defer any UI change to a separately scoped task.
4. **Warning / popup / status-message UX audit.** Review the full page and reduce warnings, popups, success/status notices, OCR notices, settings messages, diagnostic/download notices, AI disclaimers, and repeated AI references unless they materially affect the user's next action. Present the product primarily as a crochet Pattern Translator.
5. **Image Quality traffic-light calibration.** Reassess red/yellow/green thresholds, Good/acceptable/poor classification, warning severity, crop recommendations, and when users should simply continue, using actual OCR outcomes rather than theoretical strictness.
6. **Overlay numbered remark mapping.** When long overlay text is replaced by `[1]`, `[2]`, or `[3]`, show the same marker beside the corresponding Line-to-line Translation entry so the PNG marker has an immediate reference.
7. **Line-to-line Translation must be read-only.** Keep output readable and preferably selectable/copyable, but not editable. The UI must not imply that manual edits update overlays, downloads, result state, or diagnostics.
8. **Language placeholder localization.** Preserve explicit no-selection behavior and localize the placeholder as `Choose an option`, `請選擇`, `请选择`, and `選択してください` for English, Traditional Chinese, Simplified Chinese, and Japanese. Do not restore automatic interface-language selection.
9. **Production Streamlit chrome/top-bar verification.** Before Soft Launch, verify whether unwanted production chrome, top bar, menu, or development controls remain visible and minimize them using the smallest safe supported approach.

### Enhancements / Reproduce Before Fixing

10. **Diagnostic Report UX.** The current safe prepare/generate then download flow is functional. Retain the desired one-action Download Diagnostic Report UX only if it can be achieved without returning report generation to the translation critical path.
11. **Initial upload-preview delay.** Physical-iPhone UAT occasionally shows several seconds before Pattern Preview appears. Reproduce and measure before changing uploader architecture.
12. **Select Area cropper first-render issue.** Physical-iPhone UAT previously showed server-side cropper execution without a stable visible cropper until another full rerender. Reproduce after the canonical-state fix before modifying or replacing the cropper.

### Post-Launch / Scale

13. **Genuine Safari/new-AppSession recovery.** Process/session-local recovery cannot guarantee state across a genuinely new Streamlit AppSession, Safari page-process destruction or reload, container/process restart, or handoff expiry. Do not solve pre-launch without evidence of material user impact.
14. **OCR concurrency/scaling.** The isolated serialized PaddleOCR worker is appropriate for current traffic and has passed reliability testing. At materially higher concurrency, consider a small fixed worker pool or separate OCR service only when traffic justifies it.
15. **Analytics / Feedback workflow review.** Retain deferred Pattern Translator analytics-schema review, investigation of system/non-user analytics activity, Feedback Form workflow/copy review, and later reuse of appropriate analytics/feedback design for Stitch Translator.

Other non-blocking polish already recorded:

- Android overlay font may appear relatively small.
- Version number is not currently shown in the UI.
- Minor overlay text box alignment refinement is deferred.
- JellyCat 元寶 overlay placement has a minor cosmetic placement difference. Translation correctness, anchor position, readability, and functionality are unaffected; this is future overlay placement tuning rather than an RC47 regression.

## Current Release Notes

### Phase 3A FastAPI browser UI migration (complete; approved)

- Approved local baseline: `6c8ab97b0731daa6cd61a4f919aa71cabc856d3b` (`Phase 3A: add FastAPI browser UI`).
- Delivered a same-origin FastAPI-served browser UI with Whole Pattern; Select Area cropper and Precision Pad; original-image preview; loading/error recovery; overlay and line-by-line results; PNG/TXT downloads; four-language browser localization; and approved visual/typography parity.
- Human UAT passed on Desktop Chrome, iPhone Safari, and Android Chrome. Final automated validation passed `229 / 229` tests.
- Diagnostic Report, image-quality assessment/gating/force-run, and the download-completion destination popup were deliberately deferred. The popup absence is accepted as non-blocking/deferred; image-quality work is separate Phase 3B2 scope, not Phase 3B1.
- Release handling: committed locally only; no Phase 3A push or deployment occurred. Streamlit remains the production service, and Railway cutover to FastAPI/Uvicorn has not started and requires explicit approval.

### Phase 2 FastAPI HTTP boundary (complete; Human UAT PASS)

- Added `pattern_translator/api.py` with `POST /api/v1/translate`, reusing the existing `translate_image()` service without changing translation, OCR, overlay, Streamlit, Stitch Translator, or Railway behavior.
- Supports validated multipart JPG/JPEG/PNG/WebP input, Whole Pattern and Select Area requests, original-coordinate crop boxes, the existing 25 MB ceiling, and JSON projection of translation text plus base64 PNG overlay output.
- Automated validation passed: 13 API tests, 30 translation/OCR regression tests, and 223 full-suite tests. Codex independent review returned **PASS WITH NON-BLOCKING NOTES**.
- Human UAT passed using the clean Pattern 001 source for Whole Pattern and Select Area. Known non-blocking observations are limited to pre-existing multi-column OCR/line-merging bleed, minor label offsets near the eye-instruction area, and partial neighboring text at Select Area crop boundaries.
- Release handling: committed locally on `main`; no Railway deployment, push, or Phase 3 implementation occurred.

### Canonical translation-state ownership (production complete; Human UAT PASS)

- Canonical source language, target language, and translation-area state are the semantic source of truth. Explicit widget callbacks update canonical state; harmless widget omission, cleanup, or remount hydrates presentation state from canonical values.
- Translation execution, crop/area branching, and compatibility signatures use canonical state. The existing signature guard remains active and still invalidates completed results after genuine source, target, area, crop, or relevant resize changes.
- Production Human UAT passed for Whole Pattern and Select Area result stability, PNG and TXT downloads without result loss, Diagnostic Report generation/download without result loss, and canonical state survival across harmless Streamlit reruns.
- Automated validation passed `199 / 199`, including PNG/TXT/Diagnostic early-rerun regressions. Existing OCR and result-state diagnostics remain active.
- Production revision: `a215fa38bebe1ac71d5cd2e251e67328275dc7ec`.

### Contextual LLM translation (production complete; Human UAT PASS)

- Architecture: the deterministic engine remains authoritative for crochet-critical terminology and structure. Eligible ordinary natural-language content is handled by `gpt-5.6-luna`, with a separate validated title route where applicable. The general Luna route uses low reasoning effort and `max_output_tokens=400`; `gpt-5-nano` is no longer an active production translation route.
- Context boundary: compact semantic context is derived from the active translation scope. Whole Pattern uses Whole Pattern OCR scope; Select Area uses only selected-area OCR scope.
- Translation ownership: historical ordinary `pattern_instruction` mappings do not constrain successful LLM translation, while deterministic translation remains the fail-open fallback. Mixed notation and prose spans are supported with rounds, stitches, counts, repeats, and other structural tokens protected.
- Validation boundary: Chinese- and Japanese-target output is checked for unsupported invented Latin or alphanumeric content. Missing credentials, timeouts, network/model failures, malformed responses, and validation failures all return deterministic output without interrupting the workflow.
- Privacy boundary: uploaded images are never sent to OpenAI. Requests contain only the extracted text and compact semantic context required for the eligible translation, without user identity or analytics identifiers.
- Uploader state: the custom uploader frontend hydrates from authoritative backend active-image state across Streamlit reruns, preserving Replace and Remove and allowing replacement after translation.
- Production configuration: requires `PATTERN_LLM_FALLBACK_ENABLED=1` and `OPENAI_API_KEY` as a Railway secret. `PATTERN_LLM_DEBUG` is diagnostic-only and should remain disabled in production.
- Validation: Hybrid/Human-UAT automated suite `73 / 73` passed; the feature-flag-OFF deterministic corpus remained `220 / 220` identical; Local Human UAT passed; Production Owner Smoke UAT passed; and Railway deployment passed at `cddd55cf06bea39b6879add00d8db0416e109092`.
- Maintenance direction: natural LLM wording variation is acceptable when meaning and crochet structure remain valid. Further translation-quality improvements must be driven by production evidence rather than speculative tuning.
- Deferred: minor overlay placement refinement remains non-blocking. Cross-column OCR/visual-line merging remains separate future work.

### RC54A (completed; Production Human UAT PASS)

- Runtime: upgraded Pattern Translator from Streamlit 1.50.0 to the minimum Components V2 release, Streamlit 1.51.0.
- Architecture: added one frameless Components V2 Plausible bridge that mounts near the start of `app.py`, reads the shared `PUBLIC_PLAUSIBLE_SCRIPT_URL`, and injects the personalized tracker once into the main browser page.
- Scope: migrated only `pattern_translation_completed`. Upload, PNG download, TXT download, and feedback remain on the existing Components V1 transport and are reserved for RC54B.
- Rerun handoff: one pending event slot carries a completed translation across the required `st.rerun()`; the previous V1 list/counter queue is not used for the migrated event.

- Local validation: Python compilation passed; Streamlit 1.51 startup passed; the bridge rendered without an analytics iframe; one tracker script remained after a Streamlit rerun; one completed-translation probe dispatched once and an unrelated rerun produced no duplicate; `git diff --check` passed.
- Production validation: Railway production tracks GitHub `main`; Chrome on macOS confirmed the personalized script and accepted Plausible event request in the main page. One completed translation generated exactly one `pattern_translation_completed` event, ordinary Streamlit reruns generated no duplicate, and the event appeared in the existing Portal Plausible dashboard.
- Single-site architecture: production uses one Plausible Starter site, `crochet-intelligence-portal-production.up.railway.app`. Pattern Translator uses the same personalized script/site while preserving its production URL in the event URL.
- Production event baseline at RC54A closeout: `pattern_image_uploaded`, `pattern_translation_completed`, `pattern_png_downloaded`, `pattern_txt_downloaded`, and `pattern_feedback_clicked` each appeared once during the smoke test. The four non-translation events still used V1 at that historical stage. Plausible `/` and `Outbound Link: Click` entries are platform page/outbound-link tracking, not Pattern Translator custom product goals.
- Regression smoke test: Streamlit 1.51 production testing passed for Whole Pattern, Select Area/cropper, overlay, PNG download, TXT download, and Feedback in Chrome on macOS, with no functional regression observed.
- Next step at RC54A closeout: RC54B had not started; its purpose was to migrate the remaining V1 Pattern analytics transport to the production-validated V2 bridge.
- Boundary: OCR, translation, overlay, diagnostics, exports, upload, cropper, and existing non-migrated analytics behavior are unchanged.

### RC54B (completed; Production Human UAT PASS)

- Production revision: `8b6a6195f85baf5967f42ef2d6acc105741950b3` on Railway at `https://pattern-translator-production.up.railway.app/`.
- Transport: `pattern_image_uploaded`, `pattern_translation_completed`, `pattern_png_downloaded`, `pattern_txt_downloaded`, and `pattern_feedback_clicked` all use the production-validated Components V2 bridge.
- Cleanup: the obsolete Components V1 Plausible analytics component and dependency were removed. The custom uploader and cropper remain Components V1 and are unaffected.
- Validation: five genuine production actions were verified successfully with no observed rerun duplicates, analytics UI regression, or Pattern Translator functional regression.
- Deliberate exclusion: Diagnostic Report analytics is not included because its `on_click="ignore"` download path would require a different browser-side tracking mechanism.

### RC52 (completed locally)

- Workflow: the custom uploader fully replaces the previous upload workflow, and selecting Select Area opens the cropper immediately without a duplicate image preview or extra launch button.
- Component: the custom Streamlit Components V1 cropper preserves browser-local editing and the existing Python/Pillow crop boundary. The Precision Arrow Pad, four-edge selection, Safari long-press/callout handling, and cross-platform light/dark themes are complete.
- State handling: Reset restores the initial crop locally; Start Over returns to the Whole Pattern default and starts a fresh Select Area session when reselected.
- OCR feedback: the existing running status is positioned above the disabled running-labelled action so feedback remains visible immediately on mobile.
- Validation: Human UAT passed on physical iPhone Safari, Android Chrome, and Desktop Chrome with no remaining functional issues.
- Architecture: the custom uploader and cropper replace targeted Streamlit UI limitations through supported component boundaries rather than framework workarounds. OCR, parser, translation, overlay, diagnostics, analytics, exports, coordinate conversion, and downstream engines remain unchanged.
- Status at RC52 closeout: production-ready and frozen locally. Further cropper visual polish was deferred until after Platform Analytics unless a functional regression was found. No RC52 deployment had yet been performed, and RC28 was the deployed production baseline at that stage.

### RC51 (completed locally)

- Mission: first Phase B implementation after the Phase A Brand Identity Foundation.
- Local implementation: Warm Modern colours, typography, spacing, controls, cards, disclosure styling, and the RC50 custom uploader now follow the Living Design Specification.
- Theme support: Light Mode and Dark Mode remain equally supported through the device colour-scheme preference.
- Streamlit menu: the top-right overflow menu is suppressed with supported `client.toolbarMode = "minimal"` configuration rather than private-DOM CSS.
- Radio control: the selected state uses supported Streamlit `theme.primaryColor = "#0F766E"`, avoiding private-DOM CSS and preserving native accessibility behavior.
- Product approval: physical-iPhone Human Visual UAT passed. The Pattern Translator Home Screen, custom uploader, privacy card, and identical secondary Replace / Remove controls are approved as the current baseline.
- UI governance: the Product-driven workflow in `ENGINEERING_RULES.md` is now standard; implementation alone does not constitute visual approval.
- Deferred: broader Pattern Translator UI standardisation will be revisited after Platform Analytics. This baseline is not a final UI freeze.
- Boundary: no OCR, translation, overlay, diagnostics, analytics, export, engine, or workflow behavior was changed.
- Status at RC51 closeout: complete locally, with no deployment or GitHub push; RC28 was the production baseline at that stage.

### RC50

- RC50A validated the technical upload boundary; RC50B completed the production custom uploader.
- Architecture: `custom uploader -> BytesIO -> image_upload_signature() -> Image.open()`. OCR, translation, overlay, diagnostics, exports, and the analytics schema were preserved.
- Formats and interaction: JPG, JPEG, PNG, and WebP; four interface languages; native mobile picker; desktop drag-and-drop; Replace and Remove; light and dark modes.
- Limit: 25 MB is intentional because Streamlit Components V1 uses base64 transport.
- Validation: physical iPhone Safari and Android Chrome Human UAT passed; real image upload and downstream workflows passed; unrelated-image/no-crochet-content handling was validated and its message improved; no functional regression was observed.
- Boundary: one native Streamlit UI widget has been replaced. Streamlit still owns runtime, session state, and component communication.
- Follow-on: Phase A subsequently established the brand direction and Living Design Specification. Logo work and GIF/onboarding guidance remain deferred.
- Status at RC50 closeout: complete locally, with no production deployment or GitHub push; RC28 was the production baseline at that stage. Its custom uploader subsequently became the approved reference implementation following RC51.

### RC49

- Mission: final local Engine Extraction for deterministic OCR cleanup.
- Scope: extract `clean_ocr_text()` and `normalize_pattern_rounds()` into `pattern_translator/engine/ocr_cleanup.py`.
- App impact: `pattern_translator/app.py` reduced from 2,971 lines to 2,868 lines.
- Validation: automated regression passed; Human UAT passed; OCR cleanup fixtures, round normalization, and stored OCR fixtures were identical; overlay, TXT, Pattern Export, and Diagnostic Report outputs remained identical; `220 / 220` translation corpus cases were identical.
- Architecture: Engine Migration and Domain Layer extraction are complete. The seven Streamlit-independent engines are `engine/terminology.py`, `engine/line_translation.py`, `engine/diagnostic_report.py`, `engine/overlay.py`, `engine/pattern_document.py`, `engine/ocr_lines.py`, and `engine/ocr_cleanup.py`.
- Intentional boundary: Streamlit UI, application orchestration, OCR runtime/provider lifecycle, session state, downloads, analytics, localization, Cropper / Select Area, and runtime infrastructure remain in `app.py` because they are application, framework, or runtime responsibilities rather than domain-engine responsibilities.
- Future direction: product features, runtime improvements, deployment, or Application Layer work may proceed when justified. Application Layer separation is deferred until it provides clear product value.
- Behavior: no user-visible behavior changes.
- Release handling at RC49 closeout: local only, with no production deployment or GitHub push; RC28 was the production baseline at that stage.

### RC48

- Mission: local OCR Line Assembly Engine extraction after RC47 Pattern Document Engine extraction.
- Scope: extract `merge_ocr_boxes_into_visual_lines()`, `_merge_ocr_cluster()`, and `build_ocr_line_translations()` into `pattern_translator/engine/ocr_lines.py`.
- Architecture: OCR visual-line grouping and translated line-record construction are now independent of Streamlit. The six Streamlit-independent engines are `engine/terminology.py`, `engine/line_translation.py`, `engine/ocr_lines.py`, `engine/pattern_document.py`, `engine/overlay.py`, and `engine/diagnostic_report.py`.
- App impact: `pattern_translator/app.py` reduced from 3,089 lines to 2,971 lines.
- Validation: automated regression passed; Human UAT passed; stored OCR fixtures and intermediate OCR-line records were identical; overlay, TXT, Pattern Export, and Diagnostic Report outputs remained identical.
- Behavior: no user-visible behavior changes.
- Release handling at RC48 closeout: local only, with no production deployment or GitHub push; RC28 was the production baseline at that stage.
- Architecture status at RC48: Engine Migration entered its final stage, completed subsequently by RC49.

### RC47

- Mission: local Pattern Document Engine extraction after RC46 Overlay Rendering Engine extraction.
- Scope: extract pattern noise filtering, section detection, section grouping, readable section formatting, and pattern export construction into `pattern_translator/engine/pattern_document.py`.
- Architecture: Pattern Document responsibilities are now independent of Streamlit and encapsulated in the engine layer. `app.py` delegates directly to the Pattern Document Engine without compatibility wrappers. Current engine modules are `engine/terminology.py`, `engine/line_translation.py`, `engine/diagnostic_report.py`, `engine/overlay.py`, and `engine/pattern_document.py`.
- Validation: automated regression passed; Human UAT passed; translation, TXT export, section export, pattern export, Diagnostic Report, overlay PNG bytes, overlay pixels, overlay legend, and `220 / 220` direct corpus outputs were identical.
- Known validation limitation: OCR was intentionally not rerun during automated regression because RC47 only extracted Pattern Document responsibilities.
- Human UAT note: JellyCat 元寶 overlay placement shows a minor cosmetic placement difference. Translation correctness, anchor position, readability, and functionality are unaffected. This is recorded as future Overlay placement tuning rather than an RC47 regression.
- Behavior: no user-visible behavior changes.
- Release handling at RC47 closeout: local only, with no production deployment or GitHub push; RC28 was the production baseline at that stage.
- Architecture status: Engine Migration is now in the late stage following RC47. A fresh post-RC47 architecture assessment will determine whether additional engine extraction is warranted or whether the project should transition to the next architectural phase.

### RC46

- Mission: local Overlay Rendering Engine extraction after RC45 Boundary Cleanup.
- Scope: extract overlay rendering responsibilities into `pattern_translator/engine/overlay.py`.
- Architecture: overlay rendering is now independent of Streamlit. The Streamlit UI calls the Overlay Engine directly, and no compatibility wrapper was retained because no Streamlit-specific behavior was required. Current engine modules are `engine/terminology.py`, `engine/line_translation.py`, `engine/diagnostic_report.py`, and `engine/overlay.py`.
- App impact: `pattern_translator/app.py` reduced from approximately 4229 lines to approximately 3789 lines.
- Validation: automated regression passed; Human UAT passed; overlay PNG byte comparison passed; overlay pixel comparison passed; overlay legend comparison passed; translation regression, TXT regression, Diagnostic Report regression, and `220 / 220` direct corpus outputs were identical.
- Known validation limitation: OCR was intentionally not rerun during automated regression because RC46 only refactored overlay rendering.
- Behavior: no user-visible behavior changes.
- Release handling at RC46 closeout: local only, with no production deployment or GitHub push; RC28 was the production baseline at that stage. RC46 was another major milestone in the ongoing Engine Migration, which was not yet complete.
- Remaining `app.py` responsibilities are increasingly concentrated around application orchestration, OCR, session management, localization, downloads, and Streamlit integration.

### RC45

- Mission: local Boundary Cleanup after RC44 Diagnostic Report Engine extraction.
- Scope: remove redundant pass-through wrappers between `app.py` and the existing engine modules; update internal call sites to invoke the owning engine directly where appropriate.
- Architecture: `engine/terminology.py`, `engine/line_translation.py`, and `engine/diagnostic_report.py` now own their extracted business logic more clearly. `app.py` primarily contains application orchestration, Streamlit integration, OCR, overlay rendering, session state, and remaining application-specific responsibilities.
- App impact: `pattern_translator/app.py` reduced from approximately 4468 lines to approximately 4229 lines, a net reduction of approximately 239 lines.
- Validation: translation regression identical; TXT regression identical; Diagnostic Report regression identical; `220 / 220` direct corpus outputs identical; Human UAT passed.
- Behavior: no user-visible behavior changes.
- Release handling at RC45 closeout: local only, with no production deployment or GitHub push; RC28 was the production baseline at that stage.

### RC44

- Mission: third Engine Extraction RC after RC43 line translation extraction.
- Scope: extract Diagnostic Report construction and formatting into `pattern_translator/engine/diagnostic_report.py`.
- App impact: `pattern_translator/app.py` reduced from approximately 5432 lines to approximately 4462 lines.
- Validation: representative Diagnostic Report diff was zero bytes; translation regression and TXT regression were identical; the existing regression corpus was unchanged; Human UAT passed.
- Human UAT finding: a missing `_debug_cell` helper reference caused a NameError during OCR diagnostic metadata generation. The hotfix restored `_debug_cell` only where required inside `app.py`, while the Diagnostic Report Engine retained its own private helper. Repeated Human UAT passed.
- Behavior: no user-visible behavior changes.
- Release handling at RC44 closeout: local only, with no production deployment or GitHub push; RC28 was the production baseline at that stage.

### RC43

- Mission: second Engine Extraction RC after RC42 terminology extraction.
- Scope: extract pure line-translation logic into `pattern_translator/engine/line_translation.py`.
- App impact: `pattern_translator/app.py` reduced by approximately 759 lines.
- Validation: automated regression confirmed `220 / 220` direct corpus cases identical; Human UAT passed.
- Behavior: no user-visible behavior changes.
- Release handling at RC43 closeout: local only, with no production deployment or GitHub push; RC28 was the production baseline at that stage.

### RC42

- Mission: first Engine Extraction RC after RC41 architecture analysis.
- Scope: extract only the CSV terminology / lookup engine into `pattern_translator/engine/terminology.py`.
- Cache handling: Streamlit cache behavior intentionally preserved through app-level wrappers.
- Validation: automated regression confirmed `209 / 209` translation cases identical; Human UAT passed.
- Behavior: no user-visible behavior changes.
- Release handling at RC42 closeout: local only, with no production deployment or GitHub push; RC28 was the production baseline at that stage.

### RC28

- Mission: finalize Railway production release after RC26 Whole Pattern default workflow, RC27 Railway migration, and the Diagnostic Report download hotfix.
- Status: completed.
- Diagnostic Report fix: Railway session-state regression after Diagnostic Report download was fixed by preventing the Diagnostic Report download button from triggering a Streamlit rerun.
- Validation: local validation passed, Railway production deployment passed, and Railway Desktop Human UAT passed.
- Historical production status: RC28 became the Pattern Translator production baseline at RC28 closeout.
- Deployment platform: Railway is now the primary production deployment platform. Streamlit Community Cloud remains available as a backup platform.
- Non-blocking items: version number is not currently shown in the UI; minor overlay text box alignment refinement is deferred.

### RC40 Architecture Decision

- Decision: begin a phased post-Streamlit migration after RC40 architecture review.
- Rationale at RC40: RC28 was the stable production baseline, and RC30b had confirmed Streamlit as the primary architectural limitation rather than Railway.
- Migration rule: start locally only. Do not create a GitHub migration branch, push, deploy, or change production until local extraction work has been reviewed and validated.
- First objective: separate OCR, parser, translation, overlay, diagnostics, analytics integration, and knowledge-base access from Streamlit UI/session code while preserving current behavior.
- Historical context: RC40's broad extraction direction has since been refined into the staged migration recorded under Current Priorities. The current rollback tree is `c49755b59686e58298febba445e5ae51a6cb6e05` / `8dccd17518344d7d2152dc49fc3e13c0e95e3fd0`, not RC28.

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
- Analytics decision at RC26: restored the original `app_open` semantics. This was later superseded by RC54; the unreliable `app_open` event is not used as the platform visitor model.

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

Current platform sequence:

1. **Complete:** Extract and validate the framework-neutral `translate_image()` service while Streamlit remains the caller.
2. **Complete:** Add and validate the minimal FastAPI boundary using that service.
3. **Complete:** Migrate the Pattern browser UI and components in Phase 3A (approved local commit `6c8ab97b0731daa6cd61a4f919aa71cabc856d3b`).
4. **Next:** Phase 3B1 Diagnostic Report parity, beginning with Goal, Success Criteria, Out of Scope, and narrow architecture/forensic inspection.
5. **Later, separate scope:** Phase 3B2 image-quality assessment, gating, and force-run parity; do not combine it with Phase 3B1.
6. **Not started:** Cut the existing Railway service to FastAPI/Uvicorn only after explicit approval and parity evidence. Streamlit production has not yet been replaced.
7. Resume translation-performance work and remaining product/UI items after migration stability. Translation-performance / terminology-cache optimization remains paused.
8. Run final product-wide production UAT and proceed to Soft Launch while preserving the completed RC54 analytics and custom-domain baselines.

Additional deferred work:

- Review the Google Feedback Form questions and workflow.

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
