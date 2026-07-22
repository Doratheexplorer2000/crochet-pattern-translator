# Overlay Engineering Design Rules

This document is for future Codex and developer reference. Any future version that modifies overlay translation rendering should read and follow this document first.

## Purpose

The overlay system is an annotation system, not a full replacement system.

Its purpose is to help users read translated crochet pattern text while preserving access to the original pattern. The original image remains the source of truth. Translation labels should clarify the pattern, not erase or obscure it.

## Approved Design Principles

- Preserve original OCR text whenever possible.
- Do not cover OCR boxes belonging to other lines.
- Limited overlap with the current line's own OCR box is acceptable if it improves readability and does not obscure important content.
- Preserve crochet reading order: top-to-bottom, left-to-right.
- Do not place full translation labels above their own OCR row.
- Prefer full translation labels over markers.
- Marker fallback is the final safety mechanism, not a normal placement preference.
- Use horizontal search sweep before falling back to markers.
- Use dynamic pixel-aware wrapping rather than fixed character wrapping where practical.
- Avoid adding pattern-specific special cases unless there is a clear general rule.
- Do not add global placement-priority changes to fix a single image.

## Current RC18a Behavior

- OCR boxes are treated as protected regions.
- Existing overlay labels are obstacles.
- Right-side placement is preferred.
- Horizontal search sweep is used to recover additional full labels.
- Markers should avoid covering original round labels.
- Above placement for full labels is disabled.
- Alien Pattern regression improved from many markers to mostly full labels.

## Future Ideas / Not Yet Approved

- Cover Original Mode / overlay display mode toggle.
- Translation-only export.
- More advanced row-aware placement scoring.
- Better marker legend UX.
- Multi-column pattern layout testing.
- Symbol chart support is out of current scope.
- Finished-object-photo-to-pattern generation is out of current scope.

## Regression Test Reminder

Alien Pattern should remain Regression Test #001.

Future overlay changes should be checked against:

- full label count
- marker count
- whether markers cover round labels
- whether labels cover other OCR text
- whether reading order is preserved
- whether grouped expressions still translate correctly

## RC18b Experiment Note

RC18b was an experiment.

RC18b changed the decision path for right-edge cases but produced identical pixel output to RC18a for the Alien Pattern. Therefore RC18a remains the preferred base for further work unless otherwise decided.
