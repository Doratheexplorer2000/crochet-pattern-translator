# Regression Test Log

## Regression Framework v2

- Replaced permanent baseline language with Current Reference Build.
- Current Reference Build means the latest accepted RC that passed regression testing and internal UAT with no known major regression.
- Future RCs should compare against `Current_Reference_Build/`.
- After approval, a future RC may be promoted to Current Reference Build.
- Previous reference builds should be preserved in `Archive/`.

## RC17a

- Larger overlay font.
- Grouped expression parser work.
- First unit-level grouped-expression smoke tests.

## RC17b

- Completed real OCR grouped-expression fix.
- Alien Pattern verification.
- OCR boxes began to be treated as protected regions.
- No-above placement for full labels.
- Improved marker fallback.

## RC18

- Dynamic pixel-aware label wrapping.
- Improved marker placement.
- Reading-order placement policy.
- Protected OCR boxes.
- Reduced markers compared with earlier builds.

## RC18a

- Horizontal search sweep.
- R5 / R7 / R9 recovered from markers.
- Alien Pattern result: 28 full labels, 2 markers.
- Became preferred RC18 base.

## RC18b

- Right-edge placement experiment.
- Changed decision path only.
- RC18b output was byte-for-byte identical to RC18a for Alien Pattern.
- Not currently preferred over RC18a unless otherwise decided.

## RC20

- Select Area productization regression executed against five new real-world candidate patterns.
- Registered `Pattern_002` through `Pattern_006`.
- Confirmed Select Area materially reduces OCR runtime on dense, screenshot, two-column, and chart-heavy pages.
- Recorded RC20 outputs in `Test_Output/Overlay`, `Test_Output/OCR_Text`, and `Test_Output/Diagnostics`.
- Added product backlog notes for parser, dictionary/prose coverage, overlay, and symbol-chart follow-up work.

## RC20c

- Added Select Area editing display proxy to improve mobile cropper fit while preserving original-coordinate crop boxes.
- Registered `Pattern_007` Fisherman Hat and `Pattern_008` French Rose Notes as permanent Real_User regression patterns.
- Added coordinate round-trip checks for original-to-display-to-original crop mapping.

## RC20d Promotion

- RC20d completed internal regression.
- Desktop Human UAT completed successfully.
- iPhone Human UAT completed successfully.
- Android Human UAT completed successfully.
- Safari testing completed successfully.
- Chrome testing completed successfully.
- No outstanding critical issues remain at promotion time.
- RC20d promoted as the Current Reference Build on 2026-07-08.
- RC18a reference artifacts copied to `Archive/RC18a_Reference_Build/` for historical comparison.

## RC20 - Select Area Production Release

- Select Area became the recommended and default workflow.
- Whole Pattern remains available as a secondary workflow.
- Mobile Select Area editing workflow completed.
- Display Proxy architecture introduced for mobile cropper usability.
- Coordinate mapping fixed to avoid bottom/right crop truncation.
- Regression Framework successfully used throughout RC20 development.

## RC21a

- Introduced the first Pattern Instruction Rule Parser.
- Added Chinese chain-start instruction support for `倒X針`, `倒X鉤`, `倒X回鉤`, and `倒數第X針`.
- Validated against real-world Chinese crochet patterns.
- RC21a validation found one OCR edge case where the trailing unit was dropped, e.g. `倒2`.

## RC21a1 Promotion

- Added conservative OCR Context Recovery for bare `倒X` only in clear crochet chain-start context.
- Negative controls confirmed unrelated `倒2` text does not trigger the parser.
- Parser implementation completed.
- OCR recovery enhancement completed.
- Internal validation completed successfully.
- Regression validation completed successfully.
- Performance validation completed successfully.
- No outstanding critical issues remain at promotion time.
- RC21a1 promoted as the Current Reference Build on 2026-07-09.
- RC20d reference archived to `Archive/RC20d_Reference_Build/`.

## RC23

- Added `Pattern_009` Sea Salt Phone Bag as a permanent Real_User regression pattern.
- Validated real-image Whole Pattern OCR and translation for Sea Salt Phone Bag.
- Confirmed `起21个辫子针倒2回钩19X,W` preserves foundation chain, chain-start instruction, counted `X`, and `W`.
- Investigation found `立` was incorrectly captured by the foundation-chain parser before CSV lookup.
- Raw evidence recorded under `Reports/RC23_Sea_Salt_Phone_Bag_Real_Run/` and `Reports/RC23_Raw_Evidence/`.

## RC23a Promotion

- Separated foundation-chain semantics from turning-chain semantics.
- Foundation-chain parser now handles `起...`.
- Turning-chain instructions such as `立9CH` use CSV-backed `st_047_turning_chain` semantics.
- Verified expected examples:
  - `起21个辫子针` -> `Chain 21`
  - `立9CH` -> `Turning chain 9 ch`
  - `立12CH` -> `Turning chain 12 ch`
  - `立9CH，倒2回钩2SL` -> `Turning chain 9 ch, Start in the 2nd chain from hook, 2 sl st`
- Confirmed no regression for `倒X回钩`, `2SL`, `mm` measurements, grouped expressions, and English US-to-UK translation.
- RC23a completed Human UAT and was accepted by the product owner.
- No outstanding critical issues remain at promotion time.
- RC23a promoted as the Current Reference Build on 2026-07-16.
- RC21a1 reference archived to `Archive/RC21a1_Reference_Build/`.
