# Pattern_002

Display Name: Jellycat Potato

Category: Difficult

Source Image:

- `Test_Pattern_Library/Difficult/Pattern_002_Jellycat_Potato/Pattern_002_Jellycat_Potato_Source.jpeg`

## Why This Pattern Exists

This pattern is a dense simplified Chinese real-world diagram with multiple sections, two-column content, decorative background elements, creator notes, copyright blocks, and a product photo. It is useful for testing whether Select Area can isolate one useful pattern section from a visually busy page.

## Engineering Characteristics

- Sections: foot section and body section, plus notes/copyright area.
- Layout: multi-section, visually two-column.
- Language: Simplified Chinese with crochet shorthand.
- OCR difficulty: high, due to dense text, decorative background, and notes.
- Select Area usefulness: high; users are likely to translate one section at a time.
- Overlay difficulty: high; narrow columns create marker pressure.

## Recommended Regression Workflow

- Whole Pattern: use as a stress comparison.
- Select Area: crop the body column or foot section separately.

## Expected Engineering Checks

- OCR should detect most round rows in the selected section.
- X/V/A shorthand should translate inside grouped expressions.
- Select Area should reduce OCR runtime compared with Whole Pattern.
- Overlay may require markers because the columns are narrow.
