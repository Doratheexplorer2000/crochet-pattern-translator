# Crochet Intelligence

Repository for the current Crochet Intelligence Streamlit applications.

## Applications

- `pattern_translator/app.py`  
  Crochet Pattern OCR Translator for image OCR, translation overlays, TXT export, and diagnostic reports.

- `stitch_translator/app.py`  
  Crochet Stitch Translator for dictionary-style stitch lookup.

Both applications remain independent. They now share the same production stitch database.

## Current Cross-App Priorities

Immediate work:

- Pattern Translator analytics is implemented locally. Configure Streamlit secrets and run live Google Sheets append smoke testing.
- Pattern Translator RC25 is the current deployment candidate.
- Pattern Translator Feedback Form migration to `crochetintelligence@gmail.com` is complete.
- Add the reusable analytics implementation to Crochet Stitch Translator next.

After analytics live validation:

- Conduct External UAT while collecting real usage, performance, failure, and reliability data.
- Use collected evidence to evaluate Streamlit Community Cloud viability, including quota limits, sleeping, crashes, and resource failures.

Later:

- Evaluate a new deployment platform.
- Decide where the Crochet Intelligence landing page should be hosted only after the deployment-platform direction is clearer. Do not assume the landing page will be hosted on Streamlit.

## Shared Knowledge Base

The shared database lives at:

```text
knowledge_base/data/master_stitches.csv
```

The accepted source snapshot is archived at:

```text
knowledge_base/releases/database/stitches_1_8e.csv
```

Symbol assets live at:

```text
knowledge_base/symbols/
```

## Run Locally

Pattern Translator:

```bash
python3 -m streamlit run pattern_translator/app.py
```

Stitch Translator:

```bash
python3 -m streamlit run stitch_translator/app.py
```

## Documentation

- `knowledge_base/DATABASE.md`
- `knowledge_base/CSV_SPEC.md`
- `docs/FUTURE_ARCHITECTURE.md`
- each app's `README.md`
- each app's `PROJECT_STATUS.md`

Regression assets live under `regression/`.
