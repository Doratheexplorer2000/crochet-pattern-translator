# Current Reference Build

## Active Reference

Current Reference Build: **RC23a**

Promotion date: **2026-07-16**

Promotion status: **Accepted for future engineering comparison**

RC23a is the active reference because it completed:

- RC23 Chinese Pattern Instruction pipeline validation;
- Sea Salt Phone Bag real-image regression;
- turning-chain parser precedence fix;
- targeted regression for `起...`, `立...`, `倒...`, counted tokens, `mm` measurements, grouped expressions, and English US-to-UK translation;
- Human UAT acceptance.

No outstanding critical issues remain at the time of promotion.

Historical RC18a overlay artifacts are retained for comparison and have been archived under `../Archive/RC18a_Reference_Build/`.
The previous RC20d reference has been archived under `../Archive/RC20d_Reference_Build/`.
The previous RC21a1 reference has been archived under `../Archive/RC21a1_Reference_Build/`.

## Definition

The Current Reference Build is the latest stable RC that has:

- passed regression testing;
- passed internal UAT;
- contains no known major regression;
- has been accepted as the new engineering reference.

Future RCs should be compared against the artifacts stored here.

After a future RC successfully passes all validation and receives approval, it may replace RC23a as the new Current Reference Build. The previous reference build should be preserved in `../Archive/`.

Before promotion, complete `../Promotion_Checklist.md`.

## Pattern ID Policy

Reference folders and metadata should use permanent Pattern IDs as the primary identifier.

Example:

- Pattern ID: `Pattern_001`
- Display Name: `Alien`
- Current folder label: `Pattern_001_Alien`

Each pattern folder may eventually contain:

- overlay image
- raw OCR text
- diagnostic report
- translation output
- metadata

Not every file must exist today.

## RC23a Reference Scope

RC23a establishes the current expected behavior for:

- Select Area as the recommended/default workflow;
- Whole Pattern as an available secondary workflow;
- mobile Select Area editing mode;
- display-proxy cropper architecture;
- original-coordinate crop mapping;
- bottom/right crop boundary preservation;
- Chinese Pattern Instruction Rule Parser support for chain-start instructions;
- OCR Context Recovery for bare `倒X` in clear crochet chain-start contexts;
- foundation-chain instructions such as `起21个辫子针` translating as `Chain 21`;
- turning-chain instructions such as `立9CH` translating as `Turning chain 9 ch`;
- chain-start continuation such as `立9CH，倒2回钩2SL`;
- negative controls for unrelated `倒X` text;
- existing OCR, translation, overlay, diagnostics, and download behavior.

## Promoted Evidence

Primary promoted evidence for RC23a is stored in:

- `../Reports/RC23a_Raw_Evidence/`
- `../Reports/RC23_Sea_Salt_Phone_Bag_Real_Run/Sea_Salt_Phone_Bag/`
