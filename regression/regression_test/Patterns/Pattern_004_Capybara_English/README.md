# Pattern_004

Display Name: Capybara English

Category: Stable

Source Image:

- `Test_Pattern_Library/Stable/Pattern_004_Capybara_English/Pattern_004_Capybara_English_Source.jpeg`

## Why This Pattern Exists

This is a clean English crochet pattern page with round rows, stitch totals in square brackets, section headings, and a reference photo. It is suitable as a stable English-source regression pattern.

## Engineering Characteristics

- Sections: body, stuffing, ear/hand notes.
- Layout: mostly single-column text with a photo on the right.
- Language: English crochet terminology.
- OCR difficulty: medium; serif text and full-page scan increase runtime.
- Select Area usefulness: medium to high; cropping the body text reduces runtime.
- Overlay difficulty: medium; long translated Chinese labels can require markers.

## Recommended Regression Workflow

- Whole Pattern: stable English OCR and translation check.
- Select Area: crop body rows for faster focused validation.

## Expected Engineering Checks

- Square-bracket stitch totals should be preserved and localized.
- English stitch terms should translate consistently.
- Long translated labels may fall back to markers.
