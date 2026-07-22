# Pattern_006

Display Name: Carnation Chart Page

Category: Stress_Test

Source Image:

- `Test_Pattern_Library/Stress_Test/Pattern_006_Carnation_Chart_Page/Pattern_006_Carnation_Chart_Page_Source.jpeg`

## Why This Pattern Exists

This English pattern page mixes prose instructions, decorative page design, a photo, and a large symbol chart. It is useful as a stress and boundary test. Symbol chart interpretation is out of current scope, so this pattern should not be treated as a normal release-gating success case.

## Engineering Characteristics

- Sections: materials, receptacle, petals, photo, and symbol chart.
- Layout: mixed prose, image, and chart regions.
- Language: English crochet prose.
- OCR difficulty: high for Whole Pattern because the chart contains many OCR-like marks.
- Select Area usefulness: very high; users should crop instruction text rather than the chart.
- Overlay difficulty: high; prose translations are long.

## Recommended Regression Workflow

- Whole Pattern: stress-test only.
- Select Area: crop instruction text for realistic workflow.

## Expected Engineering Checks

- Whole Pattern may be slow and should not be the primary workflow.
- Select Area should isolate prose instructions and avoid the symbol chart.
- Symbol chart support remains out of scope.
