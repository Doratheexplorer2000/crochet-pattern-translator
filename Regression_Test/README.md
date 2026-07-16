# Regression Test

This folder stores reusable regression test assets, reference artifacts, test outputs, reports, and engineering notes for the Crochet Pattern Translator.

Use this folder before deploying future release candidate versions. Each release candidate should be tested against selected regression patterns, and outputs should be saved with versioned filenames so changes can be compared clearly over time.

`Pattern_001_Alien` is currently the primary regression pattern. RC20 added seven additional registered patterns for broader Select Area, OCR, translation, mobile social-media screenshot, and overlay coverage. RC23a added `Pattern_009_Sea_Salt_Phone_Bag` for Chinese instruction parser and turning-chain precedence validation.

Current Reference Build: **RC23a**

RC23a was promoted after Human UAT acceptance and regression validation of Chinese foundation-chain, turning-chain, chain-start, counted-token, measurement, grouped-expression, and English US-to-UK behavior.

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

## Current Reference Build

This framework does not use a permanent "Golden Baseline".

Instead, it uses a **Current Reference Build**.

The Current Reference Build is the latest stable RC that has:

- passed regression testing;
- passed internal UAT;
- contains no known major regression;
- has been accepted as the new engineering reference.

Future RCs should always be compared against the Current Reference Build.

After a future RC successfully passes all validation and receives approval, it may become the new Current Reference Build. The previous reference build should then be moved or copied into `Archive/`.

Before promotion, use `Promotion_Checklist.md`.

The current active reference metadata is stored in `Current_Reference_Build/Current_Reference_Metadata.md`.

## Folder Structure

- `Current_Reference_Build/` stores the accepted reference artifacts for the current baseline.
- `Archive/` preserves previous reference builds after promotion.
- `Expected_Output/` stores measurable expectation checklists and templates.
- `Test_Output/` stores newly generated outputs from candidate RC testing.
- `Reports/` stores regression report templates and completed reports.
- `Notes/` stores additional engineering notes.
- `Patterns/` preserves regression pattern notes and pattern-specific documentation.

## Current Reference Build Contents

Each pattern may eventually contain:

- overlay image
- raw OCR text
- diagnostic report
- translation output
- metadata

Not every file must exist today. The framework is designed to support future expansion.

## What Regression Outputs Should Compare

- OCR quality
- translation accuracy
- overlay placement
- full label count
- marker count
- grouped-expression behavior
- reading order
- OCR protection
- long-label wrapping
- visible regressions across versions

## Registered Pattern Library

| Pattern ID | Display Name | Category | Routine Use |
|---|---|---|---|
| `Pattern_001` | Alien | Stable | Core release regression |
| `Pattern_002` | Jellycat Potato | Difficult | Targeted OCR / Select Area / overlay testing |
| `Pattern_003` | Mushroom Social Post | Real_User | Routine real-user screenshot regression |
| `Pattern_004` | Capybara English | Stable | Routine English-source regression |
| `Pattern_005` | Flowerpot Soil Block | Difficult | Routine Select Area column regression |
| `Pattern_006` | Carnation Chart Page | Stress_Test | Stress/boundary testing only |
| `Pattern_007` | Fisherman Hat | Real_User | Social-media Select Area and cropper fit regression |
| `Pattern_008` | French Rose Notes | Real_User | Tall social-media note and cropper fit regression |
| `Pattern_009` | Sea Salt Phone Bag | Real_User | Chinese foundation-chain / turning-chain / chain-start regression |

## Suggested Output Naming

Use descriptive, versioned filenames, for example:

- `Alien_RC18a_Overlay.png`
- `Alien_RC18a_DiagnosticReport.txt`
- `Alien_RC18a_OCR_Text.txt`

## Framework Status

Regression Framework v2.1 is considered stable.

Future work should focus on product areas such as Select Area, OCR improvements, overlay improvements, UI / Landing Page, and translation improvements. The framework itself should only be modified if a genuine engineering need is discovered.

## Latest Promotion

RC23a was promoted as the Current Reference Build on 2026-07-16.

Milestone: `Notes/Engineering_Milestones.md`
