# RC20c Select Area Display Proxy Regression Report

## Summary

RC20c adds a Select Area editing display proxy for mobile cropper usability.

The uploaded image remains unchanged. During Select Area editing only, the cropper receives a temporary display-sized image, then the confirmed crop is converted back to original-image coordinates before OCR. Whole Pattern processing is unchanged.

## Scope

- Application file: `Crochet_Translator_Beta_RC20c.py`
- Base: `Crochet_Translator_Beta_RC20b.py`
- Focus: Select Area editing experience for wide and unusual social-media screenshots
- Out of scope: OCR pipeline, translation, overlay generation, downloads, deployment, and regression framework logic

## Implementation Notes

The display proxy uses a bounded editing image with maximum dimensions:

- maximum display width: `380 px`
- maximum display height: `720 px`

Coordinate flow:

1. Original image is loaded unchanged.
2. Select Area editing creates a temporary display image.
3. Existing original-coordinate crop box is mapped to display coordinates.
4. User edits the display-coordinate crop box.
5. The cropper result is mapped back to original-image coordinates.
6. Confirmed crop is stored in original-image coordinates.
7. OCR continues to use original-image coordinates.

## Syntax Check

PASS

Command:

```bash
PYTHONPYCACHEPREFIX=/tmp/codex_pycache_rc20c python3 -m py_compile Crochet_Translator_Beta_RC20c.py
```

## Coordinate Integrity Checks

| Original Image | Display Image | Original Box | Display Box | Round Trip Box | Result |
|---|---:|---:|---:|---:|---|
| 1600 x 800 | 380 x 190 | 400,200,1200,600 | 95,48,285,142 | 400,202,1200,598 | PASS |
| 780 x 1008 | 380 x 491 | 195,252,585,756 | 95,123,285,368 | 195,253,585,755 | PASS |
| 567 x 1384 | 295 x 720 | 100,300,500,900 | 52,156,260,468 | 100,300,500,900 | PASS |

Small one-to-two pixel round-trip differences are expected from integer rounding and remain within cropper-coordinate tolerance.

## Registered New Patterns

| Pattern ID | Display Name | Category | Reason Added |
|---|---|---|---|
| `Pattern_007` | Fisherman Hat | Real_User | Social-media screenshot with compact text, product image, and a common wide/mobile editing challenge |
| `Pattern_008` | French Rose Notes | Real_User | Tall social-media note screenshot with long crochet instructions and mobile cropper fit risk |

## Regression Results

| Pattern | Workflow | Status | OCR Time | Total Time | Rows | Full Labels | Markers | Display Proxy |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Pattern_007 Fisherman Hat | Whole Pattern | PASS | 33.832 s | 46.775 s | 33 | 25 | 7 | 380 x 491 |
| Pattern_007 Fisherman Hat | Select Area Row List | PASS | 3.480 s | 15.163 s | 31 | 1 | 30 | 380 x 491 |
| Pattern_008 French Rose Notes | Whole Pattern | PASS | 8.388 s | 26.729 s | 28 | 18 | 3 | 295 x 720 |
| Pattern_008 French Rose Notes | Select Area Flower Support | PASS | 2.891 s | 9.294 s | 9 | 6 | 2 | 295 x 720 |
| Pattern_003 Mushroom Social Post | Select Area Smoke | PASS | 6.265 s | 16.433 s | 18 | 15 | 0 | 332 x 720 |
| Pattern_005 Flowerpot Soil Block | Select Area Column Smoke | PASS | 4.044 s | 18.752 s | 19 | 10 | 2 | 380 x 506 |

Raw regression data:

`Regression_Test/Reports/RC20c_Select_Area_Display_Proxy_Data.json`

## Display Proxy Performance

Display-image creation time was negligible in all measured cases:

- Pattern_007: `0.008879 s`
- Pattern_008: `0.008711 s`
- Pattern_003 smoke: `0.009725 s`
- Pattern_005 smoke: `0.008919 s`

This is small compared with OCR time and should not materially affect runtime.

## Findings

- Whole Pattern remains available and unchanged.
- Select Area editing now uses a smaller, mobile-friendlier cropper image.
- Confirmed crop boxes remain stored in original-image coordinates.
- OCR uses original-coordinate crops after confirmation.
- New social-media regression patterns are valuable and should remain permanent regression patterns.

## Remaining UX Observations

- Very dense Select Area outputs may still fall back to many markers because overlay space is limited after cropping.
- Display proxy improves editability, but it does not change the cropper component's underlying touch model.
- Future work could add clearer cropper instructions or a visual "selected region" summary, but no further changes are required for RC20c validation.
