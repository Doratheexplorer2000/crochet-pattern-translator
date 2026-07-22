# Crochet Pattern Translator - Project Brief

Last updated: 2026-07-16

## 1. Project Overview

Crochet Pattern Translator is a mobile-first OCR translation tool for crochet patterns. It helps users upload a crochet pattern image, select the area they want to translate, run OCR, translate crochet notation and instructions, and export both a translated text file and an annotated overlay image.

The product has evolved beyond stitch lookup. Its current scope includes:

- image upload and mobile-friendly Select Area cropping;
- Whole Pattern OCR as a secondary workflow;
- OCR-based pattern text extraction;
- crochet terminology translation across English, Traditional Chinese, Simplified Chinese, and Japanese;
- parser-assisted crochet instruction handling;
- translated overlay PNG export;
- line-by-line translation TXT export;
- Diagnostic Report export for UAT and issue investigation;
- Google Feedback Form workflow;
- regression framework with permanent real-world pattern IDs.

The application is currently prepared for External UAT Round 2.

## 2. Current Reference Build

Current Reference Build: **RC23a**

Application version: **Pattern OCR Translator (Beta RC23a)**

Promotion date: **2026-07-16**

Promotion status: **Accepted**

RC23a is the engineering baseline for future work. It passed regression validation and Human UAT after separating foundation-chain and turning-chain semantics:

- `起21个辫子针` remains a foundation-chain instruction: `Chain 21`.
- `立9CH` uses CSV-backed turning-chain semantics: `Turning chain 9 ch`.
- `立9CH，倒2回钩2SL` translates as `Turning chain 9 ch, Start in the 2nd chain from hook, 2 sl st`.

Reference metadata and detailed validation evidence live under:

- `Regression_Test/Current_Reference_Build/`
- `Regression_Test/Reports/RC23a_Raw_Evidence/`
- `Regression_Test/Reports/RC23_Sea_Salt_Phone_Bag_Real_Run/`

## 3. Current Development Status

The stable product path is:

Upload image -> preview -> Select Area by default -> OCR -> translation -> overlay/TXT/diagnostic downloads.

Select Area is the recommended workflow because it is usually faster, more accurate, and better for multi-section or multi-column patterns. Whole Pattern remains available for users who need it.

The current system has stable support for:

- Select Area mobile editing with display proxy;
- original-coordinate crop mapping;
- OCR resize behavior for cloud performance;
- Chinese chain-start parser support for `倒X針`, `倒X鉤`, `倒X回鉤`, and `倒數第X針`;
- OCR context recovery for bare `倒X` in clear crochet contexts;
- turning-chain parser precedence using CSV terminology;
- counted crochet shorthand such as `2SL`;
- decimal `mm` measurement protection;
- grouped expression translation such as `(X,V)` and `(3X,V)`;
- regression evidence with raw before/after outputs.

No current critical blocker is known.

## 4. Product Maturity

The project is in beta / external UAT preparation.

Maturity by area:

- OCR pipeline: usable and validated on real patterns, but still resource-sensitive on Streamlit Community Cloud.
- Select Area workflow: stable and preferred.
- Translation parser: useful for crochet notation and selected instruction patterns; still intentionally conservative.
- Overlay: functional annotation system, but not a finished layout engine.
- Regression framework: stable enough to guide future RC development.
- Public feedback workflow: ready for UAT.
- Deployment: previously validated on Streamlit Community Cloud with Python 3.11 and required Linux packages.

Future work should continue in small RCs with narrow scope.

## 5. Known Issues

Current known issues for External UAT Round 2:

1. **Android overlay font appears relatively small**
   - Status: Known Issue
   - Priority: Deferred
   - Action: wait for broader External UAT feedback before changing font or overlay scaling.

2. **Download session reset observed once on iPhone Safari**
   - Status: Monitoring only
   - Reproducibility: not reproducible
   - Action: do not change code unless repeated reports confirm a pattern.

Additional backlog items are tracked in `Regression_Test/Notes/Product_Backlog.md`.

## 6. Deferred Features

The following are intentionally deferred and should not be implemented unless explicitly selected for a future sprint:

- symbol chart recognition;
- finished-object-photo-to-pattern generation;
- automatic section detection;
- multi-column recognition beyond user-selected areas;
- Cover Original Mode / overlay display mode toggle;
- translation-only page redesign;
- advanced marker legend UX;
- broad natural-language translation of all prose;
- major overlay engine redesign;
- new OCR engine or OCR model changes.

These are product decisions, not accidental omissions.

## 7. Regression Library Summary

The Regression Framework uses permanent Pattern IDs. Pattern IDs never change, even if display names improve.

Current permanent patterns:

| Pattern ID | Display Name | Main Purpose |
|---|---|---|
| `Pattern_001` | Alien | Core grouped-expression and overlay regression |
| `Pattern_002` | Jellycat Potato | Dense Chinese multi-section OCR and Select Area validation |
| `Pattern_003` | Mushroom Social Post | Real phone screenshot with text/photo/social UI chrome |
| `Pattern_004` | Capybara English | Clean English-source pattern and US/UK terminology |
| `Pattern_005` | Flowerpot Soil Block | Two-column Chinese Select Area regression |
| `Pattern_006` | Carnation Chart Page | Mixed prose/photo/symbol-chart stress boundary |
| `Pattern_007` | Fisherman Hat | Social-media compact text and cropper fit regression |
| `Pattern_008` | French Rose Notes | Tall note screenshot and long Select Area regression |
| `Pattern_009` | Sea Salt Phone Bag | Foundation-chain, turning-chain, chain-start parser regression |

Regression outputs should include raw evidence, not only summaries:

- Translation RC: raw TXT before/after/diff.
- Overlay RC: overlay PNG before/after.
- OCR RC: OCR TXT before/after.
- Performance RC: timing comparison.
- Parser RC: at least one real pattern output, not only unit tests.

## 8. Engineering Principles

Long-term principles established during development:

- Parser handles crochet instructions; CSV handles terminology.
- CSV is the source of truth for stitch and terminology meaning.
- Do not treat different crochet instructions as equivalent unless the product specification says so.
- Keep parser changes narrow and evidence-backed.
- Preserve OCR, translation, overlay, Select Area, and deployment logic unless the current sprint explicitly targets them.
- Human UAT is required before promotion.
- Accepted RC becomes the Current Reference Build.
- Future RCs compare against the Current Reference Build, not against a permanent golden baseline.
- Regression evidence must contain raw outputs, not just PASS summaries.
- Add new regression patterns only when they provide long-term engineering value.
- Overlay is an annotation system, not a replacement system.
- Overlay should preserve original pattern readability wherever reasonably possible.
- Prefer small scoped RCs over broad multi-area changes.

## 9. Development Workflow

Standard lifecycle:

1. Define a narrow RC objective.
2. Confirm out-of-scope areas explicitly.
3. Implement the smallest safe change.
4. Run syntax checks.
5. Generate raw regression evidence.
6. Compare against the Current Reference Build.
7. Fix regressions if found.
8. Perform Human UAT.
9. Promote only after approval.
10. Archive the previous Current Reference Build.
11. Update regression documentation.

Before modifying overlay behavior, read `Overlay_Engineering_Design_Rules.md`.

Before changing regression expectations, read:

- `Regression_Test/README.md`
- `Regression_Test/Promotion_Checklist.md`
- `Regression_Test/Current_Reference_Build/Current_Reference_Metadata.md`

## 10. Next Sprint

Recommended next step: **External UAT Round 2 preparation and monitoring**.

Suggested scope:

- use RC23a as the release candidate;
- do not add new parser or overlay behavior before External UAT Round 2 unless a blocker appears;
- collect feedback on Android overlay readability, download reliability, translation gaps, and Select Area usability;
- require diagnostic reports and screenshots for user-reported issues;
- only create the next RC after feedback identifies a clear, high-value target.

If a technical sprint is required before External UAT Round 2, the safest candidates are documentation cleanup or deployment packaging. Parser, OCR, overlay, and UI changes should wait for evidence.
