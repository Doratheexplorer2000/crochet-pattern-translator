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
- Human-visit and `app_open` event-quality cleanup remains deferred until the Landing Page can provide browser analytics.
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
- Engine extraction remains local only: no production deployment and no GitHub push. RC28 remains the current production baseline.
- RC50A completed the custom uploader technical spike, and RC50B completed the production Streamlit Components V1 custom uploader.
- The native Streamlit file uploader was replaced while preserving the boundary `custom uploader -> BytesIO -> image_upload_signature() -> Image.open()` and all downstream OCR, translation, overlay, diagnostics, exports, and analytics-schema behavior.
- Supported formats are JPG, JPEG, PNG, and WebP. The uploader supports all four interface languages, native mobile image selection, desktop drag-and-drop, Replace and Remove, and light and dark modes.
- The intentional upload limit is 25 MB because Components V1 uses base64 transport. Physical iPhone Safari and Android Chrome Human UAT passed with no functional regression.
- Unrelated-image/no-crochet-content handling was validated and its message improved.
- Streamlit remains the runtime and continues to provide session state and component communication. Visual branding, corporate colours, logo work, GIF/onboarding guidance, and upload-button restyling are deferred pending the separate visual identity decision.
- Regression evidence is stored under `regression/regression_test/Reports/`.

## Current Project Status

- Official production baseline: `RC28`
- Current app version string: `Pattern OCR Translator (Beta RC26)`
- Current phase: phased post-Streamlit migration preparation
- Latest local product step: `RC50` production custom uploader completed and physical-device Human UAT passed; Engine Migration remains complete.
- Current production database: `knowledge_base/data/master_stitches.csv`
- Current focus: preserve RC28 as the Railway production baseline and move to the next UI/UX limitation after the separate visual identity decision. Future Application Layer separation remains deferred until clear product value justifies it.
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
