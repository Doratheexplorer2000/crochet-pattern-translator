# Future Crochet Intelligence Architecture Proposal

This document is informational only. It is not an implementation plan for the current Streamlit release.

## Current Direction

For now, keep two independent applications:

- Crochet Stitch Translator: direct dictionary lookup
- Crochet Pattern Translator: OCR pattern translation

Both applications should share one master stitch database, but they should not yet share Python packages or deployment infrastructure.

## Knowledge Base Direction

The long-term center of the project should be a Crochet Intelligence Knowledge Base, not a collection of unrelated apps.

Conceptually:

```text
Crochet Intelligence Knowledge Base
  ↓
Crochet Stitch Translator
  ↓
Crochet Pattern Translator
  ↓
Future Tutorial Search
  ↓
Future Mobile App
  ↓
Future AI Assistant
  ↓
Future API
```

The knowledge base should contain the master stitch database, symbol references, terminology relationships, parser-compatible identifiers, and eventually validated educational links or examples.

Applications should consume this knowledge base according to their own product needs.

## Future Platform Direction

After leaving the current Streamlit-only deployment model, Crochet Intelligence could evolve into a unified platform:

```text
Knowledge base
  master stitch database
  symbol library
  terminology metadata
  regression patterns

Frontend experiences
  Stitch Translator
  Pattern OCR Translator
  Tutorial Search
  Mobile App
  AI Assistant

Shared backend
  terminology API
  OCR job API
  translation/parser service
  feedback/report intake
```

## Shared Modules Later

After platform migration, good candidates for shared modules include:

- database loading and validation
- stitch lookup and normalized search
- terminology conversion
- language utilities
- symbol lookup
- localization resources
- YouTube tutorial search URL generation

These should not be extracted yet. Premature shared modules would increase deployment risk while both apps are still independent Streamlit applications.

## Future Database Options

Short term:

- CSV remains appropriate because it is easy to inspect, edit, version, and validate.

Medium term:

- SQLite could provide stronger validation and simpler local querying while staying lightweight.

Long term:

- PostgreSQL or another managed database may be useful if the project needs user feedback ingestion, admin editing, analytics, or multi-user contribution workflows.

## Deployment Considerations

Future deployment should consider:

- separating frontend from long-running OCR jobs;
- moving OCR to a worker or API service;
- storing diagnostic reports outside user sessions;
- centralizing the master database;
- adding database migration/versioning;
- keeping regression evidence reproducible.

## Stitch Tutorial Search Placement

The planned "Search Stitch Tutorial" feature should be added to Crochet Stitch Translator result cards after database consolidation.

Recommended behavior:

1. User searches for a stitch.
2. App displays the matched database row.
3. Result card shows `Search YouTube Tutorial`.
4. The URL is generated dynamically from the canonical stitch name.

Recommended query source:

- Prefer `US_term` for English UI.
- Use the visible canonical term for other UI languages when helpful.
- Do not store YouTube URLs in the CSV for the first version.

Future helper:

```python
build_youtube_tutorial_url(stitch_name: str, ui_language: str) -> str
```

This helper should stay local to Stitch Translator until shared Python modules are introduced.
