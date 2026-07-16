# Pattern_005

Display Name: Flowerpot Soil Block

Category: Difficult

Source Image:

- `Test_Pattern_Library/Difficult/Pattern_005_Flowerpot_Soil_Block/Pattern_005_Flowerpot_Soil_Block_Source.jpeg`

## Why This Pattern Exists

This simplified Chinese pattern has two practical crochet sections on a decorative framed page. It is a strong Select Area regression pattern because the left and right columns are both meaningful but should often be translated separately.

## Engineering Characteristics

- Sections: flowerpot and soil block.
- Layout: two-column text with decorative frame and watermark.
- Language: Simplified Chinese with X/V/A/F shorthand.
- OCR difficulty: medium to high.
- Select Area usefulness: very high; column crops are much faster and clearer than Whole Pattern.
- Overlay difficulty: medium; selected columns still have some narrow-line marker pressure.

## Recommended Regression Workflow

- Whole Pattern: stress comparison.
- Select Area: crop left column and right column separately.

## Expected Engineering Checks

- Column crops should reduce OCR runtime substantially.
- Grouped expressions such as `(3X.V)` and `(2X.A.2X)` should translate.
- Markers should remain limited in selected columns.
