# DBE Mapping — Development Bank of Ethiopia
Source: https://dbe.com.et/
Fetch timestamp: 2026-10-10T07:34:18Z — HTTP 200 — static HTML
Fixture: docs/evidence/wave_survey/survey_results.json (DBE entry)

## Table structure (KNOWN)

Two tables, both with headers: `Currency | Code | Buying | Selling`

**Table 0** — 20 rows with data: USD buy=161.6278 sell=164.8604; GBP buy=213.3810 sell=217.6486; EUR buy=180.6514 sell=184.2644
**Table 1** — 20 rows but all cells empty in survey sample. Likely a duplicate or JS-rendered section.

## Key observations
- No date in table. effective_date_basis = collection_date_fallback → identity_status = ambiguous.
- Single buying/selling pair. Category unresolved. TO VERIFY.
- Currency and Code columns present — good for mapping.
- Table 1 is empty in static fetch — may be JS-rendered or a template. TO VERIFY.
- 20 rows — larger currency set than most banks.
- Rate page is the homepage. TO VERIFY if a dedicated rate page exists.

## Remaining TO VERIFY
1. Category of buying/selling
2. Effective date source
3. Table 1 content (JS-rendered?)
4. Official-display comparison
5. Terms of use
