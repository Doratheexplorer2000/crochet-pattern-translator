# Test Pattern Library

This folder stores reusable pattern images for future testing.

Each pattern should have its own folder. Each pattern folder should include:

- source image if available
- notes file
- what the pattern is intended to test
- known historical issues
- expected success criteria

Future candidate categories may include:

- two-column pattern
- low-resolution phone camera image
- screenshot pattern
- Japanese pattern
- English pattern
- handwritten or decorative-font pattern
- symbol chart sample
- long multi-page pattern

Symbol chart support and finished-object-photo-to-pattern generation are out of current scope, but such samples may be saved as future candidates.

## Pattern ID Policy

Every regression pattern receives a permanent Pattern ID.

- Pattern IDs never change.
- Pattern names may be improved in the future.
- Documentation, reports, and regression history should reference the Pattern ID as the primary identifier.

Current example:

- Pattern ID: `Pattern_001`
- Display Name: `Alien`
- Current folder label: `Pattern_001_Alien`

Future examples:

- `Pattern_002`
- `Pattern_003`
- `Pattern_004`

## Pattern Categories

Use these categories to organize future test patterns.

### Stable

Patterns that are reliable, understood, and suitable for routine regression checks. These should be used for comparing new RCs against the Current Reference Build.

### Difficult

Patterns that are known to stress OCR, overlay placement, crop behavior, or translation parsing. These are useful for targeted engineering work.

### Real_User

Patterns collected from real user testing. These should preserve the context and observed issue where possible.

### Stress_Test

Patterns intended to test system limits, such as dense layouts, long pages, very large images, decorative fonts, poor contrast, or difficult multi-column arrangements.

### Future_Candidates

Unclassified samples that may become formal regression tests later.

## Registered Patterns

| Pattern ID | Display Name | Category | Primary Purpose |
|---|---|---|---|
| `Pattern_001` | Alien | Stable | Core grouped-expression and overlay regression |
| `Pattern_002` | Jellycat Potato | Difficult | Dense Chinese multi-section page and Select Area validation |
| `Pattern_003` | Mushroom Social Post | Real_User | Real phone screenshot with text plus photo/UI chrome |
| `Pattern_004` | Capybara English | Stable | Clean English-source pattern with stitch totals |
| `Pattern_005` | Flowerpot Soil Block | Difficult | Two-column Chinese Select Area regression |
| `Pattern_006` | Carnation Chart Page | Stress_Test | Mixed prose/photo/symbol-chart boundary test |
| `Pattern_007` | Fisherman Hat | Real_User | Social-media image with compact text and large product photo |
| `Pattern_008` | French Rose Notes | Real_User | Tall social-media note screenshot with long pattern text |
| `Pattern_009` | Sea Salt Phone Bag | Real_User | Chinese foundation-chain / turning-chain / chain-start instruction regression |
