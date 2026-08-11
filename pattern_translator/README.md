# Crochet Pattern OCR Translator

Mobile-first OCR translation for crochet pattern images.

Current production baseline: **Contextual LLM translation** (`cddd55cf06bea39b6879add00d8db0416e109092`)

Validated rollback baseline: **RC28**

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

The current production revision is RC54B at `8b6a6195f85baf5967f42ef2d6acc105741950b3`, deployed from GitHub `main` to Railway. It includes the production-validated Contextual LLM translation baseline and the completed Components V2 analytics transport. RC28 remains the validated rollback baseline. The first External UAT phase concluded with positive results from real crochet users.

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
- Human-visit and `app_open` event-quality cleanup remains deferred until the Landing Page can provide browser analytics.
- `knowledge_base/data/master_stitches.csv` is the current production database.
- `stitches_1_8e.csv` is archived as the accepted source snapshot.
- Chinese foundation-chain and turning-chain semantics are separated.
- Anonymous Google Sheets Usage Analytics records app events and performance metrics without storing personal information, IP addresses, uploaded images, OCR text, or translations.
- RC54A upgraded Pattern Translator to Streamlit 1.51.0 and introduced a frameless Components V2 Plausible bridge. Production Human UAT confirmed that the bridge loads the shared `PUBLIC_PLAUSIBLE_SCRIPT_URL` in the main browser page and sends exactly one `pattern_translation_completed` event per completed translation without rerun duplicates.
- RC54A production smoke testing passed in Chrome on macOS for Whole Pattern, Select Area/cropper, overlay, PNG and TXT downloads, and Feedback, with no functional regression observed.
- The production analytics baseline contains `pattern_image_uploaded`, `pattern_translation_completed`, `pattern_png_downloaded`, `pattern_txt_downloaded`, and `pattern_feedback_clicked`. RC54B migrated all five events to the Components V2 bridge and removed the obsolete V1 Plausible transport.
- The single Plausible Starter site architecture is production-validated: Pattern Translator uses the Portal's personalized Plausible script/site while preserving the Pattern Translator production URL in event data.
- RC54B Production Human UAT passed: five genuine actions produced the expected events with no observed rerun duplicates or functional regression. Diagnostic Report analytics remains intentionally excluded because its non-rerunning download path requires a different browser-side tracking mechanism.
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
- RC47 Human UAT noted that JellyCat 元寶 overlay placement has a minor cosmetic placement difference. Translation correctness, anchor position, readability, and functionality are unaffected; this is future overlay placement tuning rather than an RC47 regression.
- RC48 completed local OCR Line Assembly Engine extraction into `pattern_translator/engine/ocr_lines.py`.
- Extracted responsibilities are `merge_ocr_boxes_into_visual_lines()`, `_merge_ocr_cluster()`, and `build_ocr_line_translations()`.
- RC48 reduced `pattern_translator/app.py` from 3,089 lines to 2,971 lines.
- RC48 validation confirmed identical stored OCR fixtures and intermediate OCR-line records. Overlay, TXT, Pattern Export, and Diagnostic Report outputs remained identical; automated regression and Human UAT passed.
- RC49 completed local OCR Cleanup Engine extraction into `pattern_translator/engine/ocr_cleanup.py`.
- RC49 extracted `clean_ocr_text()` and `normalize_pattern_rounds()` and reduced `pattern_translator/app.py` from 2,971 lines to 2,868 lines.
- RC49 validation confirmed identical OCR cleanup fixtures, round normalization, stored OCR fixtures, overlay, TXT, Pattern Export, and Diagnostic Report outputs; the `220 / 220` translation corpus and Human UAT passed.
- Engine Migration is complete. The Streamlit-independent Pattern Translator engines are `terminology`, `line_translation`, `diagnostic_report`, `overlay`, `pattern_document`, `ocr_lines`, and `ocr_cleanup`.
- Remaining `app.py` responsibilities are intentionally application, framework, and runtime concerns: Streamlit UI, application orchestration, OCR runtime/provider lifecycle, session state, downloads, analytics, localization, Cropper / Select Area, and runtime infrastructure.
- Domain Layer extraction is complete. Application Layer separation is deferred until it provides clear product value.
- Engine Migration and Domain Layer extraction are included in the current production release. RC28 remains the validated rollback baseline.
- RC50A completed the custom uploader technical spike, and RC50B completed the production Streamlit Components V1 custom uploader.
- The native Streamlit file uploader was replaced while preserving the boundary `custom uploader -> BytesIO -> image_upload_signature() -> Image.open()` and all downstream OCR, translation, overlay, diagnostics, exports, and analytics-schema behavior.
- Supported formats are JPG, JPEG, PNG, and WebP. The uploader supports all four interface languages, native mobile image selection, desktop drag-and-drop, Replace and Remove, and light and dark modes.
- The intentional upload limit is 25 MB because Components V1 uses base64 transport. Physical iPhone Safari and Android Chrome Human UAT passed with no functional regression.
- Unrelated-image/no-crochet-content handling was validated and its message improved.
- Streamlit remains the runtime and continues to provide session state and component communication.
- Phase A Brand Identity Foundation is complete. `Brand identity & UI/UI_SPEC.md` is the authoritative Living Design Specification.
- RC51 completed the first local Brand Identity implementation. Physical-iPhone Human Visual UAT approved the Home Screen, custom uploader, privacy card, and equal secondary treatment for Replace and Remove as the current baseline. OCR, translation, overlay, diagnostics, analytics, exports, engines, and workflows are unchanged.
- The selected radio state uses Streamlit's supported Primary Teal theme setting, and the top-right menu uses supported minimal-toolbar configuration.
- UI development now follows the Product-driven approval workflow in `ENGINEERING_RULES.md`. `UI_SPEC.md` is updated only after Human Visual UAT and explicit Product Owner approval. Logo work and GIF/onboarding guidance remain deferred.
- Regression evidence is stored under `regression/regression_test/Reports/`.

## Contextual LLM Translation

The production Contextual LLM translation architecture keeps the deterministic engine authoritative for crochet-critical terminology and structure. Eligible ordinary natural-language content is handled by `gpt-5.6-luna`; the validated title route remains separate where applicable. The general Luna route uses low reasoning effort and `max_output_tokens=400`. `gpt-5-nano` is no longer an active production translation route.

Compact semantic context is derived from the active OCR translation scope: Whole Pattern uses the Whole Pattern OCR scope, while Select Area uses only the selected-area OCR scope. Historical ordinary `pattern_instruction` mappings do not constrain successful LLM translation; deterministic translation remains the fail-open result. Mixed notation and prose spans are supported while rounds, stitches, counts, repeats, and other structural tokens remain protected. Chinese- and Japanese-target output is also checked for unsupported invented Latin or alphanumeric content.

Uploaded images are never sent to OpenAI. Any missing key, timeout, network, model, malformed-response, or validation failure returns the deterministic translation without interrupting the workflow. Production requires `PATTERN_LLM_FALLBACK_ENABLED=1` and an `OPENAI_API_KEY` Railway secret. `PATTERN_LLM_DEBUG` is diagnostic-only and should remain disabled in production.

The custom uploader hydrates its frontend from the authoritative backend active-image state after Streamlit reruns, so Replace and Remove remain available and replacing the active image continues to work after translation.

Validation passed: Hybrid/Human-UAT automated suite `73 / 73`; feature-flag-OFF deterministic corpus `220 / 220` identical; Local Human UAT; Production Owner Smoke UAT; and Railway production deployment. Minor overlay placement refinement remains deferred and is not a release blocker. Natural LLM wording variation is acceptable when meaning and crochet structure remain valid; further translation-quality changes must be evidence-driven.

## Current Project Status

- Current production baseline: RC54B (`8b6a6195f85baf5967f42ef2d6acc105741950b3`)
- Validated rollback baseline: `RC28`
- Current app version string: `Pattern OCR Translator (Beta RC26)`
- Current phase: RC54 Analytics completed; Production Human UAT PASS across the Portal and both translators.
- Latest Pattern Translator analytics milestone: RC54B Analytics Transport Migration completed with Production Human UAT PASS.
- Current production database: `knowledge_base/data/master_stitches.csv`
- Current focus: preserve the production Pattern Translator and completed shared Plausible analytics baselines.
- Future testing: continue with occasional trusted-user testing and incremental fixes based on production evidence. Plan for a Soft Launch after Landing Page completion instead of another formal External UAT cycle.

Known non-blocking polish items:

- Version number is not currently shown in the UI.
- Minor overlay text box alignment refinement is deferred.
- JellyCat 元寶 overlay placement has a minor cosmetic placement difference; future overlay placement tuning may improve this.

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
