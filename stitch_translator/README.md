# Crochet Stitch Translator

Dictionary-style crochet terminology lookup.

Crochet Stitch Translator is an independent application within the Crochet Intelligence platform. It shares the platform's visual language and master stitch database strategy while retaining its own focused search workflow and deployment boundary.

Current local working version:

```text
stitch_translator/app.py
```

Application version:

```text
v1.9a
```

## What This App Does

- Searches crochet stitch names and abbreviations.
- Supports English US / UK terminology, Traditional Chinese, Simplified Chinese, and Japanese.
- Handles aliases and typo-tolerant search.
- Shows available stitch symbols.
- Shows YouTube tutorial search for rows marked `tutorial_search=yes`.
- Provides a feedback form.

## Current Project Status

- Official version: `v1.9a`
- Runtime baseline: Streamlit `1.51.0`
- Development phase: Production Alignment deployed; Human UI UAT PASS
- Production URL: `https://stitch.crochetintelligence.com`
- Current production database: `knowledge_base/data/master_stitches.csv`
- Source snapshot: `stitches_1_8e.csv`
- Visual baseline: `Brand identity & UI/UI_SPEC.md`
- Analytics: shared Plausible analytics completed; Production Human UAT PASS
- Portal Centralization: completed and Production Human UAT PASS. The Portal supplies `ui_lang` (`en`, `zh-Hant`, `zh-Hans`, or `ja`); direct entry retains browser-language/English fallback, and same-tab return navigation preserves the selected language.

Production analytics events are `stitch_searched`, `tutorial_opened`, and `feedback_clicked`. Search and tutorial events record the current `interface_language`; Stitch Translator has no target translation language, so it does not use a Stitch-specific `translate_to` property.

## Current Database

Current production database:

```text
knowledge_base/data/master_stitches.csv
```

Accepted source snapshot:

```text
stitches_1_8e.csv
```

The app treats blank `search_status` values as active and excludes inactive rows from normal search.

## Run Locally

```bash
python3 -m streamlit run stitch_translator/app.py --client.toolbarMode=minimal --theme.primaryColor="#0F766E"
```

The repository's local Pattern Translator Python 3.11 environment may also be used when it contains the pinned Stitch dependencies.

## Railway Readiness

The local production-alignment candidate includes a Stitch-specific Docker image and startup command:

```text
stitch_translator/Dockerfile
stitch_translator/railway_start.sh
```

Railway uses `stitch_translator/Dockerfile` with the repository root as its build context. The independent Stitch Translator service is deployed from GitHub `main` at `https://stitch.crochetintelligence.com`.

## Visual Baseline

The interface uses the approved Crochet Intelligence Warm Modern system: Warm Linen White and charcoal page surfaces, Primary Teal controls, Noto-family typography, restrained bordered cards, visible focus states, mobile-first spacing, and system-aware light/dark presentation. The search, US/UK terminology, results, symbols, Tutorial Search, and Feedback workflows remain functionally unchanged.

## Tutorial Search

Rows marked with `tutorial_search=yes` display:

```text
Search tutorials
```

The YouTube search URL is generated dynamically from the matched canonical stitch and preserves the submitted stitch term across interface languages.

YouTube URLs are not stored in the CSV.
