# Crochet Stitch Translator

Dictionary-style crochet terminology lookup.

Crochet Stitch Translator is an independent application within the broader Crochet Intelligence ecosystem. It should remain separate from Crochet Pattern Translator during the current Streamlit phase, while gradually moving toward the same master stitch database strategy.

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
- Development phase: maintenance mode
- Current production database: `knowledge_base/data/master_stitches.csv`
- Source snapshot: `stitches_1_8e.csv`
- Future work: terminology updates, bug fixes, and knowledge-base improvements

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
python3 -m streamlit run stitch_translator/app.py
```

## Tutorial Search

Rows marked with `tutorial_search=yes` display:

```text
🎥 Search Tutorials
```

The YouTube search URL is generated dynamically from the canonical stitch name in the master database and the current interface language.

YouTube URLs are not stored in the CSV.
