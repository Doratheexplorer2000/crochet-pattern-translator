# Crochet Stitch Translator Project Status

Last updated: 2026-07-22

## Current Version

Current working version: `stitch_translator/app.py`

Application version: `v1.9a`

## Current Production Status

Crochet Stitch Translator is a stable dictionary-style Streamlit application in maintenance mode. It remains independent from Crochet Pattern Translator during the current Streamlit deployment phase.

## Current Database Version

Current production database: `knowledge_base/data/master_stitches.csv`

Accepted source snapshot: `stitches_1_8e.csv`

## Completed Features

- Multilingual stitch search.
- English US / UK terminology display.
- Traditional Chinese, Simplified Chinese, and Japanese terminology display.
- Alias and typo-tolerant search.
- US / UK ambiguity handling.
- Symbol display when a symbol asset exists.
- Tutorial Search: YouTube tutorial search for rows marked `tutorial_search=yes`.
- Mobile-friendly Streamlit UI.
- Feedback form link.

## Current Priorities

1. Add Google Sheets anonymous usage analytics.
2. Migrate the feedback/error-reporting Google Form and related links from the user's private Gmail/Drive to `crochetintelligence@gmail.com`.
3. Maintain dictionary search stability.
4. Apply terminology updates and bug fixes as needed.
5. Improve the shared knowledge base without introducing unnecessary new features.
6. Keep the app independent from Crochet Pattern Translator.

## Known Issues

- Shared Python modules are intentionally not introduced yet.

## Planned Next Version

Recommended next-version scope:

- terminology updates;
- bug fixes;
- knowledge-base improvements;
- avoid UI redesign or new features unless Human UAT shows a clear need.

## Future Backlog

- Better database validation workflow.
- Possible admin/database contribution workflow.
- Research and add Cross Single Crochet to the shared stitch database after terminology validation.
- Future integration into a broader Crochet Intelligence platform.

## Important Design Decisions

- Crochet Stitch Translator and Crochet Pattern Translator remain separate applications for now.
- Both applications should gradually share one master stitch database.
- `stitch_id` should become the durable reference for future features.
- Shared Python modules are postponed until after a future platform migration.
- Tutorial Search is data-driven by `tutorial_search`.
- YouTube tutorial URLs are generated dynamically, not stored in the CSV.

## Cross-App Strategy

- Immediate work: add anonymous Google Sheets usage analytics to both Crochet Pattern Translator and Crochet Stitch Translator, and migrate feedback/error-reporting links to `crochetintelligence@gmail.com`.
- After analytics and error-report migration: conduct External UAT while collecting real usage, performance, failure, and reliability data.
- Use the collected evidence to evaluate Streamlit Community Cloud viability, including quota limits, sleeping, crashes, and resource failures.
- Later: evaluate a new deployment platform. The Crochet Intelligence landing page should wait until the deployment-platform direction is clearer, to avoid building and moving it twice.
