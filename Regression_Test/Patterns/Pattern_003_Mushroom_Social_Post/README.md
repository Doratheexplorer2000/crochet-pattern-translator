# Pattern_003

Display Name: Mushroom Social Post

Category: Real_User

Source Image:

- `Test_Pattern_Library/Real_User/Pattern_003_Mushroom_Social_Post/Pattern_003_Mushroom_Social_Post_Source.jpeg`

## Why This Pattern Exists

This pattern represents a realistic phone screenshot from a social platform. It includes app chrome, a text pattern, and a large photo below the text. It is useful for testing common public-UAT input where users upload screenshots rather than clean pattern sheets.

## Engineering Characteristics

- Sections: mushroom stem and mushroom cap.
- Layout: single-column text followed by a photo.
- Language: Traditional Chinese with shorthand symbols.
- OCR difficulty: medium; text is clean but mixed with phone UI and image content.
- Select Area usefulness: high; cropping the text area removes irrelevant photo/UI.
- Overlay difficulty: low to medium; text area has room for full labels.

## Recommended Regression Workflow

- Whole Pattern: confirm the app tolerates screenshot chrome and photo content.
- Select Area: crop the pattern text only.

## Expected Engineering Checks

- Select Area should preserve the pattern text and exclude the photo area.
- Overlay should use mostly full labels.
- Space-separated grouped expressions should be watched as a known translation gap.
