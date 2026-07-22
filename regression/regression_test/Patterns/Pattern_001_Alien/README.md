# Pattern_001_Alien

## Pattern Name

Pattern_001_Alien

## Status

Primary regression test pattern.

Current Reference Build: RC23a.

Historical RC18a overlay artifacts are archived under `Regression_Test/Archive/RC18a_Reference_Build/`.

## Source Image

- `Test_Pattern_Library/Pattern_001_Alien/Pattern_001_Alien_Source.jpeg`

This is the official permanent Pattern_001 source image for future regression tests.

## Purpose

This pattern is used to test real-world OCR, translation, and overlay placement behavior.

## What It Tests

- grouped expression translation
- repeat groups such as `(X,V)*6 (18)`
- decrease groups with `A`
- OCR-merged prose after formula text
- dense single-column pattern layout
- overlay full label placement
- marker fallback
- dynamic label wrapping
- horizontal search sweep
- whether markers cover round labels
- whether overlay labels cover original OCR text
- long material/instruction lines

## Known Historical Issues

- RC17 left `V` / `A` untranslated inside some grouped expressions.
- RC17 / RC17a overlay labels were too small on mobile.
- RC17b / RC18 introduced protected OCR regions and no-above placement.
- RC18a introduced horizontal sweep and recovered R5 / R7 / R9 from marker fallback.
- RC18b was an experiment for right-edge placement; it changed decision path but produced identical output to RC18a for this pattern.

## Expected Success Criteria

- R3, R5, R6 and other `V` groups translate `V` to `inc`.
- R18, R20, R22, R24, R26, R27, R29-R34 translate `A` to `dec` where appropriate.
- R5, R7 and R9 should be full labels, not markers.
- Markers should not cover round labels.
- Full overlay labels should not be placed above their own OCR row.
- Overlay should preserve reading order.
- Material/instruction text may be imperfect, but should not break pattern-line translation.

## Current Reference Build Workflow

Future candidate RCs should be compared against the artifacts in:

`Regression_Test/Current_Reference_Build/Pattern_001_Alien/`

If a future RC passes regression testing, internal UAT, and approval, it may become the new Current Reference Build. The previous reference artifacts should then be archived.
