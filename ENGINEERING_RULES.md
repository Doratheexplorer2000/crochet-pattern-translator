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

For custom frontend components and related UI/UX changes, approval requires Human UAT on physical iPhone, physical Android, and Desktop. Desktop browser validation alone is insufficient.

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

---

# 16. Local-only Release Candidates

Some RCs may be intentionally local only.

When an RC is marked local only:

- do not commit;
- do not push;
- do not deploy;
- record the local validation status in existing project documentation;
- wait for explicit approval before any repository or deployment action.

Local-only completion means the requested local engineering and Human UAT checks are complete. It does not imply public release or deployment readiness.

---

# 17. Deployment Workflow

Pattern Translator production deployment direction is Railway.

Recommended workflow:

Developer
↓
Local development
↓
Local validation
↓
Human UAT
↓
Railway deployment
↓
Production validation

Streamlit Community Cloud may remain as a temporary backup during migration, but should not be treated as the primary production platform unless explicitly reinstated.

---

# 18. Migration Safety

Architecture migration work must preserve the current production baseline as a rollback target.

For the approved post-Streamlit migration:

- begin locally only;
- do not push migration work to GitHub until the local baseline and first extraction step have been reviewed;
- do not deploy migration builds to Railway until explicitly approved;
- keep RC28 Railway production fully recoverable;
- separate business logic from Streamlit before replacing the frontend;
- do not rewrite business logic that has already passed Human UAT and regression simply because the presentation layer changes;
- prefer Git tags and local branches over duplicating the repository.

Migration commits should be small and organized by reversible engineering step, such as baseline capture, business-logic extraction, API introduction, frontend prototype, and deployment spike.

---

# 19. Goal-first Engineering Workflow

Before starting any RC, feature, refactor, migration, architectural change, or engineering task larger than a small bug fix, define and agree on:

Goal

- What product or business problem is being solved?

Success Criteria

- What observable outcome determines success?

Out of Scope

- What this work is explicitly not intended to solve.

Do not begin implementation until these three items are agreed.

At the start of every new RC or major engineering discussion, ChatGPT or Codex should restate the Goal, Success Criteria, and Out of Scope before proposing implementation.

If evidence discovered during implementation shows that the agreed Goal cannot realistically be achieved, stop and reassess before continuing.

Do not continue an architectural refactor solely because it improves code quality when it no longer serves the agreed Goal.

Architectural improvements are valuable, but they must not be presented as achieving the original Goal unless the agreed Success Criteria are actually met.

---

# 20. UI / Brand Development Workflow

Engineering quality remains the first priority. After engineering implementation is complete, UI decisions follow a Product-driven review process.

Use this workflow for new UI components and substantial visual changes:

Art Director
↓
UI_SPEC.md (Approved Design Specification)
↓
Codex Implementation
↓
Human Visual UAT
↓
Product Owner Review
↓
Approval
↓
Update UI_SPEC.md (if required)
↓
Commit

`Brand identity & UI/UI_SPEC.md` is a Living Design Specification, but it represents approved design decisions. Implementation alone does not constitute approval.

Do not update `UI_SPEC.md` immediately after implementation. Update it only when:

- Human Visual UAT has been completed;
- the Product Owner has explicitly approved the visual result; and
- the approved implementation differs from the current specification.

`UI_SPEC.md` defines the colour system, typography, spacing, component styling, layout principles, and visual hierarchy.

Product content remains under Product Owner control. This includes helper text, instructional text, upload hints, warnings, button wording, and marketing copy. Product decisions may override earlier `UI_SPEC.md` recommendations after Human Visual UAT.

Light Mode and Dark Mode are equally supported. Mobile UI evidence must come from physical mobile devices or equivalent mobile behaviour. Desktop browsers resized to mobile widths may be used only for responsive layout verification and must not be presented as Human Mobile UAT evidence.

### Portal Skeleton Baseline

The Crochet Intelligence Portal Skeleton architecture and Information Architecture are frozen after Human UAT. Preserve this baseline unless a new Goal, Success Criteria, and Out of Scope explicitly justify a structural change.

- RC54 Analytics, Portal Centralization, and custom-domain migration are completed and production-validated. The canonical public domains are `crochetintelligence.com`, `pattern.crochetintelligence.com`, and `stitch.crochetintelligence.com`; public navigation must not depend on Railway-generated domains.
- Pre-Launch sequence: Portal visual refinement and branding, final product-wide production smoke UAT, then Soft Launch. Do not add features before Soft Launch unless they fix a genuine Launch blocker.
- Add future tools through the Portal's tool configuration rather than redesigning its Information Architecture.
- Describe analytics capabilities only after validation is complete. RC54 production-validated shared Plausible analytics across the Portal, Pattern Translator, and Stitch Translator, with Production Human UAT PASS. Google Sheets Product Facts remain unimplemented and require separate approval.
