# Crochet Intelligence Analytics Schema

## 1. Purpose

This document defines an implementation-neutral analytics model for the Crochet Intelligence Landing Page, Pattern Translator, Stitch Translator, and future Crochet Intelligence tools. It describes the product and business information that should be available without prescribing an analytics provider, datastore, transport, or dashboard technology.

The analytics system should answer practical questions such as:

- Where visitors come from.
- Which interface language they use.
- Which Crochet Intelligence tool they choose.
- How users interact with each tool.
- How many translations or searches occur within one visit.
- Which translation directions are used.
- Which stitches are searched.
- How long users engage with each tool.
- Which downloads and tutorial features are used.
- How often users click Feedback.
- Whether there is a large drop-off between Feedback clicks and Google Form submissions.
- How future tools can join the same analytics model.

Analytics is intended to support product decisions and business intelligence, not detailed technical debugging. Serious technical problems should continue to be investigated through user feedback and Diagnostic Reports. An unsuccessful translation, invalid upload, ordinary photograph, or unsupported document is not automatically a product error.

## 2. Analytics Principles

- Use anonymous session-level analytics. There is currently no user login or permanent user identity.
- Do not store uploaded images, translated pattern text, personal details, IP addresses, or unnecessary identifying information.
- Do not treat browser refreshes, Streamlit reruns, reconnects, health checks, or server starts as genuine user visits.
- Do not use the existing unreliable `app_open` approach as the basis of the platform analytics model.
- Distinguish platform visits from meaningful product activity.
- Treat invalid uploads, ordinary photographs, knitting patterns, symbol charts, and other unsupported content as normal user behaviour rather than automatically classifying them as application failures.
- Keep the schema implementation-neutral so that the storage or analytics provider can change later.
- Record only fields that can support a realistic product or business decision.
- Session duration is an estimate based on observable activity. It may not capture a perfect closing time when a browser, device, or connection terminates unexpectedly.
- Use UTC timestamps in a consistent machine-readable format.
- Use lower-case snake_case for event names and controlled values.

## 3. Session Model

A session represents one anonymous visit to a platform surface. Session identifiers are scoped to the relevant surface and must not become permanent user identifiers.

`duration_seconds` stores the raw numeric duration. Dashboards and reports may display it as `mm:ss` or another human-readable format. Session duration represents estimated active engagement time based on observable activity, not simply the length of time a browser remained open.

`interface_language`, `translate_from`, and `translate_to` are independent values and must not be assumed to match. For example, a user may use an English interface, translate from US terminology, and translate to Traditional Chinese.

### 3.1 Landing Session

A Landing Session represents one anonymous visit to the Crochet Intelligence Landing Page.

| Field | Description |
| --- | --- |
| `landing_session_id` | Anonymous identifier for this Landing Page visit. |
| `start_time` | First validated browser activity for the visit. |
| `end_time` | Last observable activity or estimated session end. |
| `duration_seconds` | Estimated elapsed engagement time. |
| `interface_language` | Interface language associated with the visit. |
| `country` | Coarse country-level location supplied or derived by the chosen analytics provider without retaining the IP address. |
| `browser` | Browser family, without unnecessary fingerprinting detail. |
| `device` | Coarse device category such as mobile, tablet, or desktop. |
| `referrer` | External source that brought the visitor to the platform. |
| `selected_tool` | `pattern_translator`, `stitch_translator`, a future registered tool identifier, or blank when no tool is selected. |

`referrer` identifies sources such as direct traffic, Google, Facebook, Instagram, YouTube, Threads, Reddit, or another referring site. Direct traffic must not be interpreted automatically as a bookmark or a returning user.

`selected_tool` records the tool that the visitor actually entered after leaving the Landing Page: Pattern Translator, Stitch Translator, another future tool, or no tool. A Landing Session records at most one selected tool. If the visitor returns from a tool to the Landing Page, that return begins a new Landing Session.

### 3.2 Pattern Translator Session

A Pattern Translator Session represents one anonymous visit to Pattern Translator.

| Field | Description |
| --- | --- |
| `pattern_session_id` | Anonymous identifier for this Pattern Translator visit. |
| `landing_session_id` | Nullable link to the originating Landing Session. |
| `start_time` | First validated browser or meaningful product activity for the tool visit. |
| `end_time` | Last observable activity or estimated session end. |
| `duration_seconds` | Estimated elapsed engagement time. |
| `interface_language` | Interface language associated with the tool session. |
| `entry_source` | Controlled description of how the session entered Pattern Translator. |
| `translation_count` | Number of successfully completed translations in the session. It excludes button clicks, translation attempts, and failed or cancelled operations. |
| `overlay_download_count` | Number of overlay image downloads in the session. |
| `txt_download_count` | Number of translation text downloads in the session. |
| `diagnostic_download_count` | Number of Diagnostic Report downloads in the session. |
| `feedback_click_count` | Number of Feedback link clicks in the session. |

Do not place a single `translate_from` or `translate_to` field in the session record. One session may contain multiple translations using different language directions.

`entry_source` must use at least these values:

- `landing`
- `direct`
- `external_referral`
- `unknown`

Direct traffic must not be inferred to mean a bookmark or a returning user.

### 3.3 Stitch Translator Session

A Stitch Translator Session represents one anonymous visit to Stitch Translator.

| Field | Description |
| --- | --- |
| `stitch_session_id` | Anonymous identifier for this Stitch Translator visit. |
| `landing_session_id` | Nullable link to the originating Landing Session. |
| `start_time` | First validated browser or meaningful product activity for the tool visit. |
| `end_time` | Last observable activity or estimated session end. |
| `duration_seconds` | Estimated elapsed engagement time. |
| `interface_language` | Interface language associated with the tool session. |
| `entry_source` | Controlled description of how the session entered Stitch Translator. |
| `search_count` | Number of submitted stitch searches in the session. It must not count individual keystrokes while the user is typing. |
| `tutorial_open_count` | Number of tutorial links opened in the session. |
| `feedback_click_count` | Number of Feedback link clicks in the session. |

Do not place a single `translate_to` field in the session record. A user may change the target language during one session.

Use the same `entry_source` definitions as Pattern Translator.

### 3.4 Future Tool Sessions

A future tool should add its own anonymous tool-session record using the same structure: a tool-specific session identifier, nullable `landing_session_id`, estimated timing, interface language, entry source, meaningful activity counts, and Feedback clicks where applicable. Tool-specific activity belongs in events or a separate history dataset. Adding a future tool must not require redesigning the Landing Session or the existing translator records.

## 4. Pattern Translation History

Pattern Translation History is a separate detailed dataset. Each completed translation creates one record.

| Field | Description |
| --- | --- |
| `pattern_session_id` | Owning Pattern Translator Session. |
| `timestamp` | UTC completion time. |
| `translate_from` | Source terminology or language mode used for this translation. |
| `translate_to` | Target terminology or language mode used for this translation. |

Timestamp naturally preserves event sequence, so no separate order field is required. A separate history dataset supports multiple translations and multiple language directions within one session.

The history must not store the uploaded image, OCR text, translated text, filename, or pattern content. `translation_count` in the Pattern Translator Session should be derived from, or remain consistent with, the number of completed Pattern Translation History records.

## 5. Stitch Search History

Stitch Search History is a separate detailed dataset. Each submitted stitch search creates one record.

| Field | Description |
| --- | --- |
| `stitch_session_id` | Owning Stitch Translator Session. |
| `timestamp` | UTC search submission time. |
| `search_keyword` | Submitted stitch query only. |
| `translate_to` | Target interface or result language used for this search. |
| `search_result_status` | Controlled result status. |

`search_result_status` uses this controlled set:

- `found`
- `not_found`

Timestamp naturally preserves event sequence, so no separate order field is required. `translate_to` belongs on each search record because a user may change the target language during one session.

Search terms are valuable product data because they reveal popular stitches and missing terminology. They must be limited to the submitted stitch query and must not be combined with personal data. `search_count` in the Stitch Translator Session should be derived from, or remain consistent with, the number of Stitch Search History records.

## 6. Analytics Events

Every event requires a UTC `timestamp` and the identifier of its owning session. Provider-supplied page, browser, device, country, and referrer metadata should not be copied into every event unless the chosen reporting implementation genuinely requires it.

### 6.1 Landing Page Events

| Event | Event meaning | Required properties | Optional properties | Session |
| --- | --- | --- | --- | --- |
| `landing_session_started` | A validated anonymous browser visit to the Landing Page began. | `landing_session_id`, `timestamp` | `interface_language` | Landing Session |
| `interface_language_changed` | The visitor selected a different interface language. | `landing_session_id`, `timestamp`, `interface_language` | `previous_interface_language` | Landing Session |
| `pattern_translator_selected` | The visitor selected Pattern Translator. | `landing_session_id`, `timestamp` | `destination_url` | Landing Session |
| `stitch_translator_selected` | The visitor selected Stitch Translator. | `landing_session_id`, `timestamp` | `destination_url` | Landing Session |
| `feedback_clicked` | The visitor clicked the Landing Page Feedback link. | `landing_session_id`, `timestamp` | `feedback_surface` | Landing Session |
| `ad_clicked` | The visitor clicked an enabled advertisement. | `landing_session_id`, `timestamp`, `ad_id` | `placement_id`, `campaign_id`, `destination_domain` | Landing Session |

`ad_clicked` applies only when an Ad Bar or other approved advertisement surface is enabled.

### 6.2 Pattern Translator Events

| Event | Event meaning | Required properties | Optional properties | Session |
| --- | --- | --- | --- | --- |
| `pattern_session_started` | A validated anonymous Pattern Translator visit began. | `pattern_session_id`, `timestamp` | `landing_session_id`, `entry_source`, `interface_language` | Pattern Translator Session |
| `image_uploaded` | The user supplied an image to the translator. | `pattern_session_id`, `timestamp` | `workflow_mode`, `file_type` | Pattern Translator Session |
| `translation_completed` | A translation completed and produced its product result. | `pattern_session_id`, `timestamp`, `translate_from`, `translate_to` | `workflow_mode`, `duration_seconds` | Pattern Translator Session and Pattern Translation History |
| `overlay_downloaded` | The user downloaded the translated overlay image. | `pattern_session_id`, `timestamp` | None | Pattern Translator Session |
| `txt_downloaded` | The user downloaded the translated text file. | `pattern_session_id`, `timestamp` | None | Pattern Translator Session |
| `diagnostic_downloaded` | The user downloaded a Diagnostic Report. | `pattern_session_id`, `timestamp` | None | Pattern Translator Session |
| `feedback_clicked` | The user clicked the Pattern Translator Feedback link. | `pattern_session_id`, `timestamp` | `feedback_surface` | Pattern Translator Session |

Do not automatically add every unsuccessful translation or unsupported upload as an analytics failure event. If technical exception monitoring is required later, it must remain separate from product analytics.

### 6.3 Stitch Translator Events

| Event | Event meaning | Required properties | Optional properties | Session |
| --- | --- | --- | --- | --- |
| `stitch_session_started` | A validated anonymous Stitch Translator visit began. | `stitch_session_id`, `timestamp` | `landing_session_id`, `entry_source`, `interface_language` | Stitch Translator Session |
| `stitch_searched` | The user submitted a stitch query and a result status was determined. | `stitch_session_id`, `timestamp`, `search_keyword`, `translate_to`, `search_result_status` | None | Stitch Translator Session and Stitch Search History |
| `tutorial_opened` | The user opened a tutorial search for a stitch. | `stitch_session_id`, `timestamp`, `search_keyword` | `translate_to`, `tutorial_destination` | Stitch Translator Session |
| `feedback_clicked` | The user clicked the Stitch Translator Feedback link. | `stitch_session_id`, `timestamp` | `feedback_surface` | Stitch Translator Session |

## 7. Feedback Funnel

The only Crochet Intelligence browser event in the feedback funnel is:

```text
feedback_clicked
```

Crochet Intelligence can reliably record `feedback_clicked` through browser-level interaction tracking. After the browser is redirected to Google Forms, Crochet Intelligence cannot reliably observe whether the Form was opened or submitted. Google Form submission totals must therefore come from Google Forms or its linked Google Sheet rather than from additional Crochet Intelligence browser events.

The future dashboard should compare:

- Feedback clicks.
- Google Form submissions.
- Click-to-submission conversion rate.

These measures should be available separately for Pattern Translator and Stitch Translator where possible. Crochet Intelligence must not claim it can link a specific anonymous analytics session to a specific Google Form submission unless a future privacy-reviewed implementation explicitly supports that attribution.

## 8. Dashboard Requirements

A future Google Sheets business intelligence workbook, or an equivalent reporting layer, should provide summary views while preserving access to the underlying anonymous detail records.

Suggested logical views:

- Overview
- Landing Summary
- Pattern Summary
- Stitch Summary
- Pattern Translation History
- Stitch Search History
- Feedback Funnel

### 8.1 Overview Metrics

- Unique or estimated visitors.
- Landing sessions.
- Pattern Translator sessions.
- Stitch Translator sessions.
- Tool selection rates.
- Average tool-session duration.
- Total completed translations.
- Total stitch searches.
- Feedback clicks.
- Google Form submissions.
- Feedback click-to-submission conversion rate.

### 8.2 Landing Page Metrics

- Visitors and sessions.
- Interface languages.
- Countries.
- Devices.
- Browsers.
- Referrers.
- Pattern Translator selections.
- Stitch Translator selections.
- No-tool exits where available.
- Advertisement clicks if an Ad Bar is enabled.

### 8.3 Pattern Translator Metrics

- Sessions.
- Completed translations.
- Average and median translations per session.
- Average and median session duration.
- Translate-from distribution.
- Translate-to distribution.
- Translation-direction combinations.
- Overlay download count and rate.
- TXT download count and rate.
- Diagnostic download count and rate.
- Feedback click count and rate.

### 8.4 Stitch Translator Metrics

- Sessions.
- Searches.
- Average and median searches per session.
- Average and median session duration.
- Most searched terms.
- Searches by target language.
- Found versus not-found searches.
- Tutorial open count and rate.
- Feedback click count and rate.

## 9. Proposed Provider Responsibilities

The responsibility split remains provisional and implementation-neutral:

- A privacy-focused web analytics provider such as Plausible may record visitors, sessions, page views, referrers, countries, devices, browsers, and selected custom events.
- Detailed anonymous Pattern Translation History and Stitch Search History may require a separate datastore or controlled reporting pipeline if the web analytics provider cannot retain the required detail appropriately.
- Google Sheets may serve as the business intelligence and reporting surface, with summary tabs plus detailed anonymous records.
- Google Sheets does not need to remain the direct event-ingestion system if a cleaner implementation is selected.
- Existing RC25 Pattern Translator analytics data and code do not need to be preserved for backward compatibility because Crochet Intelligence has not formally launched. RC25 analytics is a Pattern Translator-specific implementation, not an earlier version of this platform schema.

The final choice of Plausible, direct Google Sheets ingestion, APIs, Google Apps Script, another datastore, or a combination requires a separate implementation decision after this schema is approved.

## 10. Privacy Boundaries

This schema must not collect:

- Uploaded images.
- OCR output.
- Translated pattern content.
- Filenames.
- Email addresses.
- Names.
- IP addresses.
- Google Form answers.
- Diagnostic Report contents.
- Persistent cross-device user profiles.

Anonymous session identifiers should be short-lived and scoped to a relevant visit. They must not be used to identify an individual across unrelated visits unless a later privacy review explicitly approves that behaviour.

Country-level reporting may be supplied by a provider that processes network information transiently, but Crochet Intelligence must not store the visitor's IP address in its analytics records.

## 11. Open Decisions

- Which data Plausible can retain directly.
- Whether detailed Pattern Translation History and Stitch Search History require a lightweight first-party endpoint.
- How session IDs are transferred from the Landing Page to each tool.
- How session end and duration are estimated.
- How Plausible data is exported or summarised into Google Sheets.
- Whether Stitch Translator search terms require additional disclosure in the Privacy Statement.
- How advertisement clicks are recorded if the Landing Page Ad Bar is enabled.
- Whether analytics consent or an opt-out mechanism is required for the final configuration.
