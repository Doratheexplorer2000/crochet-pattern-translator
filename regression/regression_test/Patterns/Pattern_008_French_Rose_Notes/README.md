# Pattern_008

Display Name: French Rose Notes

Category: Real_User

Source Image:

- `Test_Pattern_Library/Real_User/Pattern_008_French_Rose_Notes/Pattern_008_French_Rose_Notes_Source.jpeg`

## Why This Pattern Exists

This is a tall social-media note screenshot containing a long crochet pattern. It represents a common mobile workflow where the user saves a clean text screenshot rather than a formal pattern page.

## Engineering Characteristics

- Sections: flower petals, center, large petals, flower support, leaves.
- Layout: tall single-column social-media note.
- Language: Simplified Chinese with mixed letter shorthand.
- OCR difficulty: medium; text is clean but the screenshot is tall.
- Select Area usefulness: high; users may translate one section at a time.
- Overlay difficulty: medium; long lines may wrap or use markers.

## Recommended Regression Workflow

- Whole Pattern: confirm tall screenshot can process.
- Select Area: crop one practical text section.
- Cropper UX: verify portrait/tall images remain usable after the RC20c display proxy change.

## Expected Engineering Checks

- Cropper display should remain within mobile-friendly dimensions.
- Crop coordinates should map back to the original image.
- Select Area OCR should process the chosen section only.
- The workflow should remain scrollable outside crop editing mode.
