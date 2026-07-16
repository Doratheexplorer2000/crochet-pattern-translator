# RC20 Select Area Productization Report

## Summary

- Candidate build: RC20
- Base build: RC19
- Primary regression pattern: Pattern_001 / Alien
- Test date: 2026-07-07
- Result: PASS for engineering smoke verification

## Scope Verified

- Whole Pattern workflow preserved.
- Select Area workflow uses cropped working image.
- OCR runs on the working image.
- Translation runs from OCR output of the working image.
- Overlay is generated on the working image.
- Downloaded overlay PNG is expected to match the working image dimensions.
- `streamlit-cropper` is available in the local environment.
- RC20 Streamlit startup check passed.

## Implementation Change

RC20 contains one Select Area stabilization change beyond the version update:

- Reset `rc10b_last_cropper_box` when a new uploaded image signature is detected.

This prevents stale cropper tracking from carrying across different images.

## Benchmark: Pattern_001 / Alien

### Whole Pattern

- Crop box: `(0, 0, 1242, 1660)`
- Working image size: `1242 x 1660`
- OCR input size: `748 x 1000`
- Downscale applied: Yes
- Crop extraction: `0.004 sec`
- OCR: `71.152 sec`
- PaddleOCR inference: `63.272 sec`
- Translation: `34.806 sec`
- Overlay generation: `0.112 sec`
- Total processing: `106.380 sec`
- OCR boxes: `36`
- Translated lines: `35`
- Full labels: `28`
- Numbered markers: `2`
- Output PNG: `/tmp/alien_rc20_whole_overlay.png`

### Select Area

- Crop box: `(0, 250, 430, 1525)`
- Working image size: `430 x 1275`
- OCR input size: `337 x 1000`
- Downscale applied: Yes
- Crop extraction: `0.020 sec`
- OCR: `15.060 sec`
- PaddleOCR inference: `14.980 sec`
- Translation: `32.379 sec`
- Overlay generation: `0.068 sec`
- Total processing: `47.623 sec`
- OCR boxes: `30`
- Translated lines: `30`
- Full labels: `13`
- Numbered markers: `16`
- Output PNG: `/tmp/alien_rc20_select_area_left_column_overlay.png`

## Translation Smoke Checks

Both Whole Pattern and Select Area preserved grouped-expression translation:

- `R3: (sc, inc) x6 (18)`
- `R5: (3 sc, inc) x6 (30)`
- `R7: (5 sc, inc) x6 (42)`
- `R9: (7 sc, inc) x6 (54)`
- `R20: (17 sc, dec) x3 (54)`

## Notes

- Select Area OCR was much faster than Whole Pattern OCR on this regression image.
- Translation time remains similar because the translation pipeline still processes many dictionary and normalization paths.
- Select Area marker count is higher because the cropped output has less available horizontal placement space.
- No OCR, translation, overlay, image processing, CSV, or UI redesign work was performed.

