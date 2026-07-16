# RC20 New Pattern Internal Regression Report

Date: 2026-07-07

Application: `Crochet_Translator_Beta_RC20.py`

Purpose: expand the regression pattern library using five real-world crochet pattern images and validate RC20 Whole Pattern / Select Area behavior.

Raw run data:

- `Regression_Test/Reports/RC20_New_Patterns_Internal_Regression_Data.json`

Generated outputs:

- `Regression_Test/Test_Output/Overlay/`
- `Regression_Test/Test_Output/OCR_Text/`
- `Regression_Test/Test_Output/Diagnostics/`

## Summary

All five candidate patterns produced OCR output, translated line output, and overlay PNG output through the RC20 pipeline.

Select Area is confirmed as valuable for real-world dense pages:

- Pattern_002 body-column crop reduced OCR time from 48.761s to 12.947s.
- Pattern_003 text-only crop reduced OCR time from 45.619s to 10.027s.
- Pattern_004 body-text crop reduced OCR time from 81.825s to 14.998s.
- Pattern_005 column crops reduced OCR time from 72.124s to 7.539s / 5.960s.
- Pattern_006 instruction crop reduced OCR time from 216.884s to 9.119s.

No application code was modified during this regression run.

## Candidate Pattern Registration

| Pattern ID | Display Name | Category | Recommendation |
|---|---|---|---|
| Pattern_002 | Jellycat Potato | Difficult | Add as permanent regression pattern |
| Pattern_003 | Mushroom Social Post | Real_User | Add as permanent regression pattern |
| Pattern_004 | Capybara English | Stable | Add as permanent regression pattern |
| Pattern_005 | Flowerpot Soil Block | Difficult | Add as permanent regression pattern |
| Pattern_006 | Carnation Chart Page | Stress_Test | Add as stress/boundary pattern, not routine release-gating |

## Regression Results

### Pattern_002 - Jellycat Potato

Classification: Difficult

Engineering analysis:

- Sections: foot section, body section, notes/copyright area.
- Layout: dense multi-section / two-column.
- Language: Simplified Chinese with shorthand.
- OCR difficulty: high.
- Select Area usefulness: high.
- Overlay difficulty: high due to narrow columns.

Results:

| Workflow | Result | OCR Time | Total Time | OCR Boxes | Translated Rows | Full Labels | Markers |
|---|---:|---:|---:|---:|---:|---:|---:|
| Whole Pattern | PASS | 48.761s | 90.816s | 44 | 39 | 15 | 20 |
| Select Area - Body Column | PASS | 12.947s | 33.165s | 27 | 27 | 7 | 19 |

Findings:

- Select Area works and significantly reduces OCR time.
- Body-column translation handles many grouped X/V/A expressions.
- OCR produced at least one compact expression (`v2x`) that remained partially untranslated.
- Narrow columns still create marker pressure.

Library decision: include permanently as `Pattern_002`.

### Pattern_003 - Mushroom Social Post

Classification: Real_User

Engineering analysis:

- Sections: mushroom stem and mushroom cap.
- Layout: single-column text plus social UI and product photo.
- Language: Traditional Chinese with shorthand.
- OCR difficulty: medium.
- Select Area usefulness: high.
- Overlay difficulty: low to medium.

Results:

| Workflow | Result | OCR Time | Total Time | OCR Boxes | Translated Rows | Full Labels | Markers |
|---|---:|---:|---:|---:|---:|---:|---:|
| Whole Pattern | PASS | 45.619s | 65.501s | 21 | 21 | 17 | 0 |
| Select Area - Text Only | PASS | 10.027s | 26.324s | 18 | 18 | 15 | 0 |

Findings:

- Select Area cleanly isolates text from phone UI/photo content.
- Overlay output is readable with no marker fallback in both tested modes.
- Space-separated groups such as `3(x v)` and `3(x a)` are not fully translated.

Library decision: include permanently as `Pattern_003`.

### Pattern_004 - Capybara English

Classification: Stable

Engineering analysis:

- Sections: body, stuffing, ear/hand notes.
- Layout: mostly single-column English text with a right-side photo.
- Language: English.
- OCR difficulty: medium.
- Select Area usefulness: medium to high.
- Overlay difficulty: medium because Traditional Chinese labels are long.

Results:

| Workflow | Result | OCR Time | Total Time | OCR Boxes | Translated Rows | Full Labels | Markers |
|---|---:|---:|---:|---:|---:|---:|---:|
| Whole Pattern | PASS | 81.825s | 109.289s | 22 | 22 | 11 | 6 |
| Select Area - Body Text | PASS | 14.998s | 32.304s | 15 | 15 | 4 | 9 |

Findings:

- Strong stable English-source regression pattern.
- Square-bracket stitch totals are preserved and localized.
- Long Chinese translations use marker fallback, especially in the cropped text area.
- English prose coverage remains partial but stitch terms translate.

Library decision: include permanently as `Pattern_004`.

### Pattern_005 - Flowerpot Soil Block

Classification: Difficult

Engineering analysis:

- Sections: flowerpot and soil block.
- Layout: two-column decorative framed page.
- Language: Simplified Chinese with shorthand.
- OCR difficulty: medium to high.
- Select Area usefulness: very high.
- Overlay difficulty: medium.

Results:

| Workflow | Result | OCR Time | Total Time | OCR Boxes | Translated Rows | Full Labels | Markers |
|---|---:|---:|---:|---:|---:|---:|---:|
| Whole Pattern | PASS | 72.124s | 105.683s | 37 | 24 | 9 | 10 |
| Select Area - Left Column | PASS | 7.539s | 31.519s | 19 | 19 | 10 | 2 |
| Select Area - Right Column | PASS | 5.960s | 25.555s | 16 | 16 | 9 | 3 |

Findings:

- Excellent Select Area regression pattern.
- Column crops greatly improve runtime and overlay readability.
- Grouped expressions such as `(3X.V)` and `(2X.A.2X)` translate successfully.
- Some non-stitch instruction prose remains untranslated.

Library decision: include permanently as `Pattern_005`.

### Pattern_006 - Carnation Chart Page

Classification: Stress_Test

Engineering analysis:

- Sections: materials, receptacle, petals, photo, symbol chart.
- Layout: mixed prose, decorative image, and large chart.
- Language: English.
- OCR difficulty: high in Whole Pattern due to symbol chart.
- Select Area usefulness: very high.
- Overlay difficulty: high because prose translations are long.

Results:

| Workflow | Result | OCR Time | Total Time | OCR Boxes | Translated Rows | Full Labels | Markers |
|---|---:|---:|---:|---:|---:|---:|---:|
| Whole Pattern | PASS | 216.884s | 266.588s | 27 | 27 | 6 | 7 |
| Select Area - Instructions | PASS | 9.119s | 42.320s | 10 | 10 | 0 | 8 |

Findings:

- Whole Pattern is too slow to use as a routine release-gating test.
- Select Area is the correct workflow for instruction text.
- Symbol chart support remains out of current scope.
- English prose translation is partial.

Library decision: include as `Pattern_006` Stress_Test only.

## New Issues / Product Backlog

Detailed backlog entries are recorded in:

- `Regression_Test/Notes/Product_Backlog.md`

New backlog items:

- Space-separated grouped shorthand.
- OCR spacing inside grouped shorthand.
- Chinese instruction phrase coverage.
- English prose coverage.
- Overlay label placement in narrow selected columns.
- Symbol chart support as future/out-of-scope.

## Recommendation

Add all five patterns to the permanent Test Pattern Library, with Pattern_006 clearly marked as Stress_Test and not routine release-gating.

For normal RC regression, prioritize:

- Pattern_001 Alien
- Pattern_003 Mushroom Social Post
- Pattern_004 Capybara English
- Pattern_005 Flowerpot Soil Block Select Area columns

Use Pattern_002 and Pattern_006 for targeted difficult/stress testing when the change affects OCR, overlay, Select Area, or parser behavior.
