# Pattern_007

Display Name: Fisherman Hat

Category: Real_User

Source Image:

- `Test_Pattern_Library/Real_User/Pattern_007_Fisherman_Hat/Pattern_007_Fisherman_Hat_Source.jpeg`

## Why This Pattern Exists

This is a real social-media crochet pattern image with a large decorative/product image and a compact row list. It represents common saved patterns from Xiaohongshu, Pinterest, Instagram, or Facebook where users expect the app to adapt to the image geometry.

## Engineering Characteristics

- Sections: single compact round list plus title and product image.
- Layout: image-heavy page with pattern text on the left.
- Language: Simplified Chinese with X/V shorthand.
- OCR difficulty: medium; text is clear but small relative to the full image.
- Select Area usefulness: high; users should crop the left text column.
- Overlay difficulty: medium; the row list is narrow and dense.

## Recommended Regression Workflow

- Whole Pattern: confirm OCR ignores/handles large non-text visual area.
- Select Area: crop the left row-list text.
- Cropper UX: verify mobile editing remains fit-to-width and the crop rectangle is visible.

## Expected Engineering Checks

- Cropper display should fit mobile width.
- Crop coordinates should map back to the original image.
- Select Area OCR should process only the selected row-list region.
- X/V grouped expressions should remain consistent with the current parser baseline.
