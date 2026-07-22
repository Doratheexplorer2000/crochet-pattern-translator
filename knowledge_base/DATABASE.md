# Crochet Intelligence Database Strategy

## Purpose

The Crochet Intelligence project should use one master stitch database for both current applications:

- Crochet Stitch Translator: dictionary / terminology lookup
- Crochet Pattern Translator: OCR pattern translation

The database is the source of truth for stitch names, abbreviations, aliases, symbols, and search status. Parser rules may interpret crochet instructions, but terminology meaning should come from the database wherever possible.

## Current Master Data

Current source snapshot: `stitches_1_8e.csv`

Production filename:

```text
master_stitches.csv
```

The production filename should remain stable. Future database updates should replace the content of `master_stitches.csv` without requiring Python code changes.

## Repository Folder Model

Current repository structure:

```text
crochet_intelligence/
  crochet-pattern-translator/
    knowledge_base/
    data/
      master_stitches.csv
    releases/
      database/
        stitches_1_8e.csv
    symbols/
    CSV_SPEC.md
    DATABASE.md
    archive/
      database_snapshots/
      stitches_1_8.csv
      stitches_1_8a.csv
      stitches_1_8d.csv
      stitches_1_8e.csv
```

Both current Streamlit applications read the same production file: `knowledge_base/data/master_stitches.csv`.

## Update Workflow

1. Edit the versioned working CSV outside production.
2. Validate the CSV structure against `CSV_SPEC.md`.
3. Run Stitch Translator search checks.
4. Run Pattern Translator regression checks.
5. If accepted, copy the validated CSV contents into `master_stitches.csv`.
6. Archive the versioned snapshot under `archive/database/`.
7. Update documentation with the new database release note.

## Database Governance

### Master Database Ownership

`master_stitches.csv` will become the single production database for Crochet Intelligence terminology.

All future additions, corrections, aliases, symbol links, and search-status changes should begin from the master database. Versioned CSV files are historical snapshots and should not become active working copies again after they have been archived.

The master database should be treated as product infrastructure, not as an app-specific asset. Crochet Stitch Translator and Crochet Pattern Translator may use different code paths, but the underlying stitch knowledge should come from the same source whenever possible.

### Release Workflow

Recommended database release flow:

```text
Working Copy
  ↓
Internal Verification
  ↓
Human Testing
  ↓
Regression Verification
  ↓
Production Master Database
  ↓
Archive Snapshot
```

Practical steps:

1. Create or edit a working CSV snapshot.
2. Verify the schema against `CSV_SPEC.md`.
3. Check dictionary search behavior in Crochet Stitch Translator.
4. Check OCR translation behavior in Crochet Pattern Translator.
5. Run focused human tests for changed terminology.
6. Run regression tests where the change could affect pattern translation.
7. Promote the validated content into `master_stitches.csv`.
8. Archive the exact promoted snapshot with a versioned filename.

### Stable Stitch Identifier

`stitch_id` is intended to be the permanent identifier for each stitch or terminology entry.

Human-readable names, translations, abbreviations, aliases, and notes may evolve over time. The `stitch_id` should remain stable whenever possible so future features can reference database rows safely.

Future systems should prefer `stitch_id` over translated names for durable references, including:

- Crochet Stitch Translator results
- Crochet Pattern Translator diagnostics
- Stitch Tutorial Search
- AI-assisted explanations
- user favourites
- statistics
- contribution workflows
- future APIs

If a row must be split, merged, or retired, preserve a clear historical note rather than silently reusing the old `stitch_id` for a different concept.

## Naming Convention

Use stable production name in code:

```text
master_stitches.csv
```

Use versioned names only for historical snapshots:

```text
stitches_1_8e.csv
stitches_1_9.csv
stitches_2_0.csv
```

Do not make production Python code depend on versioned CSV filenames.

## Current Implementation

- Crochet Pattern Translator reads `knowledge_base/data/master_stitches.csv`.
- Crochet Stitch Translator reads `knowledge_base/data/master_stitches.csv`.
- `stitches_1_8e.csv` is preserved as the accepted source snapshot.
- Shared Python utilities have not been extracted. Shared modules should wait until a future platform migration.
