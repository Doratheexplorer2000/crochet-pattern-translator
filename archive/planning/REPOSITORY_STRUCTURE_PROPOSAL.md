# Repository Structure Proposal

Status: proposal only  
Date: 2026-07-17  
Scope: Crochet Pattern Translator, Crochet Stitch Translator, and future Crochet Intelligence ecosystem

This document recommends a long-term repository and folder structure. It does not authorize moving, renaming, deleting, or reorganizing files yet.

## 1. Current Repository Structure

Current local workspace:

```text
crochet_intelligence/
  crochet-pattern-translator/
  crochet_translator/
  assorted historical CSV, Numbers, logs, and builder files
```

Current Git repository:

```text
crochet-pattern-translator/
```

The older `crochet_translator/` folder is not currently a Git repository. It contains the Stitch Translator, many historical Pattern OCR release candidates, OCR prototypes, database snapshots, search indexes, tests, and symbol assets.

### Strengths

- The current Pattern Translator repository has a stable app baseline: `Crochet_Translator_Beta_RC23a.py`.
- Regression documentation and test pattern material already exist.
- The project now has strong architecture documents:
  - `PROJECT_BRIEF.md`
  - `DATABASE.md`
  - `CSV_SPEC.md`
  - `FUTURE_ARCHITECTURE.md`
  - `Overlay_Engineering_Design_Rules.md`
- The Stitch Translator has a clear latest app file: `crochet_translator_streamlit_v1_8.py`.
- Both apps already use similar terminology data and symbol assets, which makes future consolidation realistic.

### Weaknesses

- The workspace mixes active code, historical RCs, experiments, local duplicates, `.numbers` files, and regression evidence.
- The Pattern Translator repo currently contains untracked historical RC files and duplicate files such as `Crochet_Translator_Beta_RC23a 2.py`, `PROJECT_BRIEF 2.md`, and `stitches_1_8e 2.csv`.
- The Stitch Translator folder contains many unrelated OCR prototypes and Pattern Translator RC files.
- The master database strategy is documented but not yet reflected in runtime filenames.
- The Pattern Translator and Stitch Translator currently use different CSV files.
- Some folders appear duplicated, such as `Regression_Test/Archive 2`, `Patterns 2`, and `Reports 2`.

### Future Maintenance Risks

- Developers may accidentally edit an archived or duplicate file instead of the active application.
- Future AI assistants may confuse historical RC files with the current release.
- Updating stitch terminology may require changes in more than one CSV unless the master database strategy is completed.
- Regression evidence may become hard to trust if source images, expected outputs, and reports are not consistently organized.
- Future features such as Tutorial Search, mobile app, API, or AI assistant may be added inconsistently if the ecosystem structure is not established early.

## 2. Recommended Long-Term Folder Structure

Recommended future workspace structure:

```text
crochet_intelligence/
  apps/
    stitch_translator/
      app.py
      README.md
      PROJECT_STATUS.md
      requirements.txt
      streamlit_config/

    pattern_translator/
      app.py
      README.md
      PROJECT_STATUS.md
      requirements.txt
      packages.txt
      runtime.txt
      streamlit_config/

    landing_page/
      README.md
      app_or_site_source/

  knowledge_base/
    data/
      master_stitches.csv
    symbols/
    CSV_SPEC.md
    DATABASE.md
    releases/
      database/

  regression/
    README.md
    current_reference_build/
    patterns/
    test_pattern_library/
    expected_output/
    test_output/
    reports/
    archive/

  docs/
    FUTURE_ARCHITECTURE.md

  archive/
    old_rcs/
    prototypes/
    database_snapshots/
    experiments/

  experiments/
    README.md
```

### Folder Purposes

`apps/`  
Contains independent deployable applications. Each app keeps its own app-specific README, status file, requirements, and deployment notes.

`knowledge_base/`  
Contains the shared master stitch database, symbol assets, and database documentation. This becomes the conceptual center of Crochet Intelligence.

`regression/`  
Contains reusable regression patterns, reference builds, raw evidence, and reports. It should support both automated checks and human UAT review.

`docs/`  
Contains only cross-project documents that need to remain permanently active. Keep this intentionally lightweight.

`archive/`  
Preserves history without cluttering active development. Archived files should be readable but clearly non-active.

`experiments/`  
Contains future exploratory work that is not yet productized. Experiments should not be imported by production apps.

## 3. Shared vs Independent Resources

### Should Remain Independent For Now

- Application source code.
- Streamlit deployment settings.
- App-specific README files.
- App-specific `PROJECT_STATUS.md`.
- App-specific UI text and workflow.
- App-specific requirements until dependencies are deliberately aligned.
- Pattern Translator regression execution details.
- Stitch Translator search UI and result-card behavior.

Reasoning: the current apps are stable as independent Streamlit applications. Premature code sharing would increase deployment risk and make small releases harder.

### Should Gradually Become Shared

- Master stitch database.
- Symbol assets.
- CSV/database documentation.
- Database release workflow.
- Engineering principles.
- Regression methodology.
- Naming conventions.
- Future Tutorial Search query rules.
- Future `stitch_id`-based references.

Reasoning: these are knowledge assets rather than application behavior. Sharing them improves consistency without forcing a platform merge.

### Should Become Shared Later, Not Now

- Database loader.
- Normalization utilities.
- Language utilities.
- Terminology lookup helpers.
- YouTube tutorial URL builder.
- API client/backend service layer.

Reasoning: shared Python modules should wait until a future platform migration or backend architecture exists.

## 4. Documentation Strategy

Permanent documentation should remain intentionally lightweight.

- `README.md`: user/developer entry point for each independent app.
- `PROJECT_STATUS.md`: concise state handoff for each independent app.
- `DATABASE.md`: database governance and release strategy.
- `CSV_SPEC.md`: database schema and column semantics.
- `FUTURE_ARCHITECTURE.md`: long-term conceptual direction.

Each application should keep its own:

```text
README.md
PROJECT_STATUS.md
```

Shared database / architecture documentation should remain limited to:

```text
DATABASE.md
CSV_SPEC.md
FUTURE_ARCHITECTURE.md
```

This proposal document is temporary. It can be removed after the repository reorganisation has been completed and accepted.

Do not introduce `ROADMAP.md`, `CHANGELOG.md`, or `ENGINEERING_GUIDELINES.md` at this stage. The project is still small enough that additional permanent Markdown files would increase maintenance cost more than clarity.

Specialized historical or engineering notes can remain in archive or regression folders when useful, but they should not become part of the permanent top-level documentation set.

## 5. Archive Strategy

Archive policy should preserve history while keeping active folders small.

### Archive These

- Old RC files no longer used as active baselines.
- OCR prototypes.
- Experimental scripts.
- Old database snapshots.
- Old search indexes.
- Numbers/Excel working files.
- One-off diagnostic outputs.
- Superseded regression reports.

### Keep Active

- Current app entrypoints.
- Current master database.
- Current symbol assets.
- Current reference regression artifacts.
- Current docs and status files.
- Current deployment configuration.

### Archive Naming

Use predictable folders:

```text
archive/
  old_rcs/pattern_translator/
  old_rcs/stitch_translator/
  prototypes/ocr/
  database_snapshots/
  experiments/
```

Archived files should keep their original filenames unless a short README is needed to explain provenance.

## 6. Test Resources

Recommended regression structure:

```text
regression/
  README.md
  current_reference_build/
    metadata.md
    Pattern_001/
    Pattern_002/

  patterns/
    Pattern_001/
      README.md
      metadata.md
      source_image.jpeg

  expected_output/
    Pattern_001/

  test_output/
    ocr_text/
    translation/
    overlays/
    diagnostics/

  reports/
    RCxx/

  archive/
```

### Principles

- Every permanent pattern must have a permanent Pattern ID.
- Source images must live inside the repository or designated test asset storage.
- Expected outputs should only be created for stable behavior.
- Raw evidence should be stored for every meaningful RC:
  - Translation RC: before/after/diff TXT.
  - Overlay RC: before/after PNG.
  - OCR RC: OCR TXT before/after.
  - Performance RC: raw timing data.
- Human UAT outputs should be clearly separated from automated regression outputs.

## 7. Naming Conventions

### Current Issues

- Mixed folder styles: `crochet-pattern-translator` and `crochet_translator`.
- Mixed file styles: `README.md` and `readme.md`.
- Versioned app files are useful historically but confusing as active entrypoints.
- Duplicate names with ` 2` suffixes are unsafe.
- Some folder names include spaces, such as `Archive 2`, which may cause confusion.

### Recommended Future Convention

Folders:

```text
snake_case
```

Examples:

```text
pattern_translator
stitch_translator
knowledge_base
test_pattern_library
current_reference_build
```

Active app entrypoints:

```text
app.py
```

Version is stored in the app constant:

```text
APP_VERSION = "Pattern OCR Translator (Beta RC23a)"
APP_VERSION = "Crochet Stitch Translator v1.9"
```

Historical files:

```text
archive/old_rcs/pattern_translator/Crochet_Translator_Beta_RC23a.py
```

Database:

```text
knowledge_base/data/master_stitches.csv
archive/database_snapshots/stitches_1_8e.csv
```

## 8. Future Growth

The proposed structure supports adding future components without another major reorganization.

### Landing Page / Portal

Add under:

```text
apps/landing_page/
```

Purpose: route users to Stitch Translator, Pattern Translator, future tutorials, and project information.

### PWA / Mobile App

Add under:

```text
apps/mobile_app/
```

It should consume the knowledge base or future API rather than duplicating stitch data.

### AI Assistant

Add under:

```text
apps/ai_assistant/
```

or, if backend-driven:

```text
services/ai_assistant/
```

It should reference `stitch_id` and knowledge-base records rather than free-form translated names.

### API

Add later under:

```text
services/api/
```

The API can expose stitch lookup, tutorial search, database metadata, OCR job submission, and diagnostics intake.

### Additional Tools

Add future crochet tools under `apps/` if user-facing, or `experiments/` if exploratory.

## 9. Implementation Plan For Repository Reorganisation

The next task can implement the reorganisation in small, reversible steps.

### Step 1: Safety Check

Before moving anything:

1. Confirm current Git status.
2. Confirm current official app files:
   - Pattern Translator: `Crochet_Translator_Beta_RC23a.py`
   - Stitch Translator: `crochet_translator_streamlit_v1_8.py`
3. Confirm which files are tracked and untracked.
4. Confirm no Streamlit deployment depends on a path that is about to move.

Stop if there are unexpected modified application files.

### Step 2: Create Target Folders Only

Create the long-term folders without moving app logic yet:

```text
apps/
knowledge_base/
docs/
archive/
experiments/
```

Keep the current applications runnable during this step.

### Step 3: Move Documentation First

Move only documentation into the target structure:

```text
apps/stitch_translator/README.md
apps/stitch_translator/PROJECT_STATUS.md
apps/pattern_translator/README.md
apps/pattern_translator/PROJECT_STATUS.md
knowledge_base/DATABASE.md
knowledge_base/CSV_SPEC.md
docs/FUTURE_ARCHITECTURE.md
```

Keep this proposal temporary. It may remain during migration and be removed after the new structure is accepted.

### Step 4: Introduce Master Database Location

Create the database target location:

```text
knowledge_base/data/master_stitches.csv
```

Populate it from the accepted database snapshot:

```text
stitches_1_8e.csv
```

Do not update application code in the same step unless the task explicitly includes it.

### Step 5: Archive Historical Database Snapshots

Move old database versions into:

```text
archive/database_snapshots/
```

Examples:

```text
stitches_1_8.csv
stitches_1_8a.csv
stitches_1_8d.csv
stitches_1_8e.csv
```

Do not delete historical snapshots.

### Step 6: Archive Old RCs And Prototypes

Move historical Pattern Translator RCs and OCR prototypes into:

```text
archive/old_rcs/
archive/prototypes/
```

Keep only the official current application file in the active app area.

### Step 7: Preserve Independent Apps

Keep both applications independent:

```text
apps/stitch_translator/
apps/pattern_translator/
```

Do not extract shared Python modules.

Do not merge Streamlit apps.

Do not introduce a shared backend.

### Step 8: Verify

After file movement:

1. Confirm both current app files still exist.
2. Confirm documentation links are updated.
3. Confirm no duplicate ` 2` files remain in active folders.
4. Confirm archived files are not referenced by active documentation.
5. Confirm Git status is understandable before committing.

### Step 9: Commit Reorganisation Separately

Commit only the repository reorganisation.

Do not combine it with:

- app logic changes;
- database behavior changes;
- Stitch Tutorial Search;
- deployment changes.

This keeps the reorganisation auditable.

## 10. Recommendation

Adopt the proposed structure as the long-term target, but do not execute it yet.

The next practical step should be repository cleanup and structure preparation only:

```text
Repository Reorganisation
  → create target folders
  → move documentation and inactive historical material
  → establish knowledge_base/data/master_stitches.csv
  → preserve independent app behavior
```

After the structure is accepted, the next functional sprint can be Crochet Stitch Translator v1.9 database migration.
