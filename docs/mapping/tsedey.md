# Tsedey Mapping — Tsedey Bank
Source: https://www.tsedeybank.com.et/
Fetch timestamp: 2026-10-10T07:34:40Z — HTTP 200 — static HTML
Fixture: docs/evidence/wave_survey/survey_results.json (TSEDEY entry)

## Table structure (KNOWN)

Two tables, both with headers including weighted average columns:

**Table 0**: `Currency | Buying | Selling | W. Avg Buy | W. Avg Sell` — 2 rows (1 header + 1 data, but data row is empty in survey)
**Table 1**: `Currency | Buying | Selling | Weighted Avg Buying | Weighted Avg Selling` — 2 rows (same issue)

## Key observations
- Both tables have only 2 rows total (1 header + 1 data) and data cells are empty in static fetch. Rates are likely JS-rendered.
- collection_method should be `browser` not `html`. TO VERIFY.
- Rate page is the homepage. TO VERIFY if a dedicated rate page exists.

## Status: BLOCKED for static HTML collection

Rates appear to be JavaScript-rendered. Browser rendering required. Adapter deferred to Wave 4 investigation.

## Remaining TO VERIFY
1. Confirm JS rendering (browser fetch)
2. Actual table structure and values
3. Effective date source
4. Category mapping
5. Official-display comparison
6. Terms of use
