# Engineering Milestones

## RC20 - Select Area Production Release

RC20 completed the productization of Select Area and promoted it to the recommended workflow.

Milestone summary:

- Select Area became the default and recommended workflow.
- Whole Pattern remains available as a secondary workflow.
- Mobile Select Area editing workflow was completed.
- Display Proxy architecture was introduced for mobile cropper usability.
- Crop coordinate mapping was fixed so bottom/right selected content is not truncated.
- Multi-device Human UAT passed on desktop, iPhone, Android, Safari, and Chrome.
- Regression Framework was used throughout development and promotion.
- RC20d was promoted as the Current Reference Build.

Promotion date: 2026-07-08

## RC21 - Chinese Pattern Instruction Parser

RC21 introduced the first lightweight Pattern Instruction Rule Parser for Chinese crochet instructions.

Milestone summary:

- Introduced the first Pattern Instruction Rule Parser.
- Added support for `倒X針`, `倒X鉤`, `倒X回鉤`, and `倒數第X針`.
- Added OCR Context Recovery for bare `倒X` in clear crochet chain-start contexts.
- Introduced Negative Control validation.
- Successfully validated using real-world Chinese crochet patterns.
- RC21a1 was promoted as the Current Reference Build.

Promotion date: 2026-07-09

## RC23 - Turning Chain Semantics

RC23 completed the first parser precedence correction after the Chinese Pattern Instruction pipeline entered Human UAT.

Milestone summary:

- Added `Pattern_009` Sea Salt Phone Bag as a permanent Real_User regression pattern.
- Validated the Sea Salt Phone Bag source image through real Whole Pattern OCR and translation.
- Confirmed foundation-chain instructions such as `起21个辫子针` remain translated as `Chain 21`.
- Separated turning-chain instructions such as `立9CH` from foundation-chain semantics.
- Used the CSV `st_047_turning_chain` entry as the source of truth for `立`.
- Verified `立9CH，倒2回钩2SL` as `Turning chain 9 ch, Start in the 2nd chain from hook, 2 sl st`.
- Regression confirmed no change to `倒X回钩`, counted tokens, `mm` measurements, grouped expressions, or English US-to-UK translation.
- RC23a passed Human UAT and was promoted as the Current Reference Build.

Promotion date: 2026-07-16
