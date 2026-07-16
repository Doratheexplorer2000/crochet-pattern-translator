# Current Reference Metadata

## Reference Build

- Reference Build version: RC23a
- Application version: Pattern OCR Translator (Beta RC23a)
- Date promoted: 2026-07-16
- Promotion title: RC23a - Turning Chain Semantics
- Promotion status: Accepted

## Validation Summary

- Internal regression: PASS
- Parser implementation: PASS
- OCR recovery enhancement: PASS
- Turning-chain precedence validation: PASS
- Sea Salt Phone Bag real-image regression: PASS
- Internal validation: PASS
- Regression validation: PASS
- Negative control validation: PASS
- Performance validation: PASS
- Human UAT: PASS
- Outstanding critical issues: None known

## Engineering Scope Covered

- Select Area became the recommended workflow.
- Mobile Select Area editing workflow completed.
- Display Proxy architecture introduced for cropper editing.
- Crop coordinates remain stored and processed in original-image coordinates.
- Bottom/right coordinate mapping was fixed to avoid selected-content truncation.
- Whole Pattern remains available and verified.
- Regression Framework was used throughout RC20 development.
- First Pattern Instruction Rule Parser introduced.
- Chinese chain-start instruction support added for `倒X針`, `倒X鉤`, `倒X回鉤`, and `倒數第X針`.
- OCR Context Recovery added for bare `倒X` when clear crochet context is present.
- Negative control validation added for unrelated `倒X` text.
- Real-world Chinese crochet patterns validated for RC21 parser behavior.
- Sea Salt Phone Bag registered as `Pattern_009`.
- `起...` and `立...` semantics separated:
  - `起21个辫子针` remains a foundation-chain instruction.
  - `立9CH` uses CSV-backed turning-chain semantics.
- RC23a raw evidence generated under `Regression_Test/Reports/RC23a_Raw_Evidence/`.

## Reference Patterns

The active regression pattern library contains:

- `Pattern_001` Alien
- `Pattern_002` Jellycat Potato
- `Pattern_003` Mushroom Social Post
- `Pattern_004` Capybara English
- `Pattern_005` Flowerpot Soil Block
- `Pattern_006` Carnation Chart Page
- `Pattern_007` Fisherman Hat
- `Pattern_008` French Rose Notes
- `Pattern_009` Sea Salt Phone Bag

## Notes

RC23a is the engineering baseline for future Select Area, OCR, overlay, translation, parser, and UI work.

Existing RC18a artifacts are retained for historical overlay comparison and archived under `Regression_Test/Archive/RC18a_Reference_Build/`.
The previous RC20d reference is archived under `Regression_Test/Archive/RC20d_Reference_Build/`.
The previous RC21a1 reference is archived under `Regression_Test/Archive/RC21a1_Reference_Build/`.
