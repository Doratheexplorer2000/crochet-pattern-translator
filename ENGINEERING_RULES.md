# Crochet Intelligence Engineering Constitution

Version: 1.0

This document defines the engineering workflow and collaboration rules for the Crochet Intelligence project.

These rules apply to all engineering work unless explicitly overridden.

---

# 1. Primary Objective

The objective is to build the best possible product while maximizing engineering efficiency.

Always optimize for:

- product quality
- engineering reliability
- execution speed
- maintainability
- minimum unnecessary complexity

Documentation exists only to support engineering work.

---

# 2. Root Cause Before Implementation

Never assume the cause of a bug.

Always identify the root cause before proposing or implementing a fix.

For OCR-related issues, investigate the complete pipeline:

Image
↓
OCR
↓
OCR Cleanup
↓
Parser
↓
CSV Lookup
↓
Translation
↓
Overlay

Do not modify downstream components unless evidence shows they are responsible.

---

# 3. Evidence Before Conclusions

Never claim that an issue has been fixed without evidence.

Every engineering change must include supporting evidence.

Examples include:

- before/after screenshots
- overlay comparisons
- raw OCR output
- cleaned OCR output
- parser output
- diagnostic reports
- regression results

Engineering conclusions must be supported by evidence.

---

# 4. Regression Requirements

Every engineering change must include regression testing.

Regression reports must include raw evidence, not only a summary.

Whenever practical, include:

- test patterns used
- before/after comparison
- known limitations
- remaining risks

Do not simply report:

"Regression passed."

---

# 5. Human UAT

Human UAT is mandatory before public release.

Workflow:

Engineering Changes
↓

Regression
↓

Raw Evidence Review
↓

Human UAT
↓

External UAT (if required)
↓

Release

Engineering work is not considered complete until Human UAT is finished.

---

# 6. Real Device Validation

Do not claim improvements for hardware or platforms that cannot be verified.

Examples:

- Android
- iPhone
- iPad

If testing cannot be performed, clearly state:

"Human verification required."

---

# 7. RC Scope

Keep each Release Candidate focused.

Prefer one engineering mission per RC whenever practical.

Avoid mixing unrelated engineering work in the same RC.

---

# 8. Minimize Engineering Risk

Prefer:

- localized code changes
- modifying existing functions
- simple solutions

Avoid:

- unnecessary refactoring
- architecture redesign
- replacing working components

unless clearly justified.

---

# 9. Product Before Documentation

Do not create documentation unless it directly improves engineering execution.

Do not suggest documentation simply because it is considered good practice.

---

# 10. Deliverables

Every completed engineering task should include:

1. Summary of code changes
2. Files modified
3. Regression evidence
4. Known limitations
5. Remaining risks
6. Human UAT checklist

---

# 11. Communication

All responses intended for implementation must be delivered as one complete instruction.

Do not append additional important instructions afterwards.

Think first.

Deliver one final version.

---

# 12. External UAT

Feedback from External UAT should be treated as engineering evidence.

Classify findings into:

- confirmed bugs
- probable bugs
- UX issues
- workflow issues
- feature requests
- user expectation issues

Do not implement fixes until evidence has been reviewed.

---

# 13. Evidence Preservation

Never discard valuable UAT evidence.

When External UAT reveals a meaningful real-world case,
preserve it for future regression.

Where practical, store:

- original pattern
- diagnostic report
- expected behaviour
- screenshots

Real-world UAT evidence is more valuable than synthetic test cases.

---

# 14. Evidence-driven Human UAT

Human UAT should be driven by engineering evidence.

Prioritize validation on:

- the platform where the issue was originally observed;
- the device reported during External UAT;
- any platform where the engineering change could reasonably introduce regressions.

Avoid creating generic Human UAT checklists.

The checklist should reflect the actual engineering changes and the available evidence.

---

# 15. Engineering Reporting

Engineering reports should clearly distinguish between:

Evidence

- Raw observations.
- Before/after comparisons.
- Regression outputs.

Assessment

- Engineering interpretation of the evidence.

Conclusion

- Only claims that are fully supported by the evidence.

Do not mix these three sections together.
