# Crochet Stitch Translator Project Status

Last updated: 2026-08-12

## Current Version

Current working version: `stitch_translator/app.py`

Application version: `v1.9a`

## Current Production Status

Crochet Stitch Translator is a stable dictionary-style Streamlit application deployed independently to Railway at `https://stitch-translator-production.up.railway.app/`. Production Alignment and Human UI UAT passed on desktop, iPhone, and Android across light and dark modes and all four interface languages. Production runs on the Crochet Intelligence Streamlit `1.51.0` baseline using the Stitch-specific Dockerfile and startup command. Shared Plausible analytics and Production Human UAT are complete.

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
- Crochet Intelligence Warm Modern visual alignment with light and dark mode support.
- Streamlit 1.51.0 runtime alignment.
- Stitch-specific Railway Dockerfile and startup command.
- Shared Plausible events `stitch_searched`, `tutorial_opened`, and `feedback_clicked`, validated in production.

## Current Priorities

1. Preserve the production-aligned search and UI baseline.
2. Preserve the production-validated RC54 analytics baseline.
3. Continue evidence-driven terminology and knowledge-base maintenance.

## Known Issues

- No known RC54 analytics blocker remains.

## Planned Next Version

The next Stitch Translator release step requires separate Product Owner approval. RC54 analytics is closed.

## Future Backlog

- Better database validation workflow.
- Possible admin/database contribution workflow.
- Research and add Cross Single Crochet to the shared stitch database after terminology validation.
- Centralize interface-language selection at the Portal, pass the selected language to each tool, and then reassess whether tool-level `interface_language` analytics remains necessary.

## Important Design Decisions

- Crochet Stitch Translator and Crochet Pattern Translator remain separate applications within Crochet Intelligence.
- Both applications should gradually share one master stitch database.
- `stitch_id` should become the durable reference for future features.
- Shared Python modules are introduced only when they remove real duplication without coupling the applications.
- Tutorial Search is data-driven by `tutorial_search`.
- YouTube tutorial URLs are generated dynamically, not stored in the CSV.
- New Stitch Railway deployments should use the dedicated Stitch Dockerfile and must not modify Pattern Translator or Portal services.

## Cross-App Strategy

- The independent Astro Portal is the platform entry point and presents Pattern Translator and Stitch Translator equally.
- Pattern Translator and Stitch Translator are deployed independently to Railway.
- Portal, Pattern Translator, and Stitch Translator share the production-validated Plausible analytics system.
