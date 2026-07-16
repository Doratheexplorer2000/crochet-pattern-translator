# Future Test Workflow

This is the standard engineering workflow for future release candidates.

## Release Candidate Lifecycle

Engineering change

↓

Internal testing

↓

Run Regression Test Suite

↓

Compare against Current Reference Build

↓

If regression found: fix regression and repeat testing

↓

Internal UAT

↓

Promote to new Current Reference Build only after approval

↓

Archive previous Reference Build

↓

Begin next RC

## Regression Test Steps

Use this workflow for every release candidate.

1. Run syntax check.
2. Run local Streamlit startup test.
3. Run `Pattern_001_Alien`.
4. Save overlay PNG into `Regression_Test/Test_Output/Overlay/`.
5. Save diagnostic report into `Regression_Test/Test_Output/Diagnostics/`.
6. Save OCR / translated text output into `Regression_Test/Test_Output/OCR_Text/` if available.
7. Compare generated outputs against `Regression_Test/Current_Reference_Build/`.
8. Compare full label count and marker count with the Current Reference Build.
9. Check whether grouped expressions still translate correctly.
10. Check whether markers cover round labels.
11. Check whether labels cover other OCR text.
12. Check whether reading order is preserved.
13. Record results in `Regression_Test_Log.md`.
14. Only recommend deployment after local smoke test and human review.

## Promotion Rule

Do not automatically promote a new RC just because it passes one regression run.

A release candidate may become the new Current Reference Build only after:

- regression testing passes;
- internal UAT passes;
- no known major regression remains;
- the project owner approves promotion.

Use `Promotion_Checklist.md` before updating the Current Reference Build.

## Pattern ID Rule

Reports and logs should identify patterns by permanent Pattern ID first, then display name.

Example:

- Pattern ID: `Pattern_001`
- Display Name: `Alien`

Pattern names may change, but Pattern IDs should not.
