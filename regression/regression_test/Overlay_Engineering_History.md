# Overlay Engineering History

## Original Overlay

- Fixed-width / character-based wrapping.
- Labels could be small.
- Overlay placement was mainly candidate-based.

## RC17a / RC17b

- Larger overlay labels.
- Grouped expression translation repaired.
- OCR boxes started to influence overlay placement.

## RC18

- Overlay became rule-based rather than only nearest-space based.
- OCR boxes treated as protected regions.
- Existing overlay labels treated as obstacles.
- Full labels should not be placed above their own OCR row.
- Marker fallback improved.

## RC18a

- Horizontal search sweep added.
- Algorithm no longer gives up after a few fixed candidates.
- More full labels recovered in dense rows.

## Current Design Principles

- Overlay is an annotation system, not a replacement system.
- Preserve original OCR text whenever possible.
- Do not cover OCR boxes belonging to other lines.
- Limited overlap with the current line's own OCR box is acceptable if it improves readability and does not obscure important content.
- Preserve crochet reading order: top-to-bottom, left-to-right.
- Do not place full translation labels above their own OCR row.
- Prefer full translation labels over markers.
- Marker fallback is the final safety mechanism.
- Use horizontal search sweep before marker fallback.
- Use dynamic pixel-aware wrapping where practical.
- Avoid image-specific special cases unless they reflect a general rule.
- Do not add global placement-priority changes to fix a single image.

## Current Reference Build Rule

Overlay changes should be compared against the Current Reference Build, not against a permanent golden image.

When a future overlay change passes regression testing, internal UAT, and approval, it may become the new Current Reference Build. The previous reference should be archived for historical comparison.
