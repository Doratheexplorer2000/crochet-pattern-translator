# RC23a Regression Finalization Report

Date: 2026-07-16

## Promotion Result

- Current Reference Build: **RC23a**
- Application version: **Pattern OCR Translator (Beta RC23a)**
- Promotion status: **Accepted**
- Human UAT: **PASS**
- External UAT Round 2 readiness: **Prepared**

## Promoted Evidence

- `Regression_Test/Reports/RC23a_Raw_Evidence/`
- `Regression_Test/Reports/RC23_Sea_Salt_Phone_Bag_Real_Run/Sea_Salt_Phone_Bag/`

## Pattern Library Inventory

| Pattern ID | Display Name | Category | Source Image | Regression README | Library README | Metadata | Missing Items | Purpose |
|---|---|---|---|---|---|---|---|---|
| Pattern_001 | Alien | Stable | Present | Present | Present | Covered by pattern README | None | Core grouped-expression, overlay, marker, and Whole Pattern regression |
| Pattern_002 | Jellycat Potato | Difficult | Present | Present | Missing | Covered by pattern README | Test_Pattern_Library pattern README | Dense Chinese multi-section OCR and Select Area regression |
| Pattern_003 | Mushroom Social Post | Real_User | Present | Present | Missing | Covered by pattern README | Test_Pattern_Library pattern README | Phone screenshot with social UI chrome and real-user text/photo layout |
| Pattern_004 | Capybara English | Stable | Present | Present | Missing | Covered by pattern README | Test_Pattern_Library pattern README | Clean English-source stitch totals and US/UK translation regression |
| Pattern_005 | Flowerpot Soil Block | Difficult | Present | Present | Missing | Covered by pattern README | Test_Pattern_Library pattern README | Two-column Chinese Select Area and overlay placement regression |
| Pattern_006 | Carnation Chart Page | Stress_Test | Present | Present | Missing | Covered by pattern README | Test_Pattern_Library pattern README | Mixed prose/photo/symbol-chart boundary and stress test |
| Pattern_007 | Fisherman Hat | Real_User | Present | Present | Missing | Covered by pattern README | Test_Pattern_Library pattern README | Social-media compact text and mobile cropper fit regression |
| Pattern_008 | French Rose Notes | Real_User | Present | Present | Missing | Covered by pattern README | Test_Pattern_Library pattern README | Tall social-media note, long Select Area, bottom/right crop mapping regression |
| Pattern_009 | Sea Salt Phone Bag | Real_User | Present | Present | Present | Covered by pattern README | None | Chinese foundation-chain, turning-chain, chain-start, grouped-expression, and mm protection regression |

## Remaining Missing Items

- `Pattern_002`: Test_Pattern_Library pattern README
- `Pattern_003`: Test_Pattern_Library pattern README
- `Pattern_004`: Test_Pattern_Library pattern README
- `Pattern_005`: Test_Pattern_Library pattern README
- `Pattern_006`: Test_Pattern_Library pattern README
- `Pattern_007`: Test_Pattern_Library pattern README
- `Pattern_008`: Test_Pattern_Library pattern README

## Known Issues For External UAT Round 2

1. Android overlay font appears relatively small.
   - Status: Known Issue
   - Priority: Deferred until more External UAT feedback.
2. Download session reset observed once on iPhone Safari.
   - Status: Monitoring only
   - Reproducibility: Not reproducible.

## Report Organization

- RC23a raw evidence is retained as promoted reference evidence.
- RC23 Sea Salt real-image run is retained as historical promotion evidence.
- Older RC20/RC22/RC23 reports are retained for historical comparison.
- Scratch outputs should not be copied into `Current_Reference_Build/` unless explicitly promoted as reference artifacts.
