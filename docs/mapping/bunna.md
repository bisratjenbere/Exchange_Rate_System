# Bunna Mapping — Bunna Bank
Source: https://bunnabanksc.com/foreign-exchange/
Fetch timestamp: 2026-10-10T07:33:55Z — HTTP 200 — static HTML
Fixture: docs/evidence/wave_survey/survey_results.json (BUNNA entry)

## Table structure (KNOWN)

One wide table with all three categories:

Headers row 0: ` | CASH | TRANSACTION | AVERAGE`
Headers row 1: `Currency | Code | Buying | Selling | Buying | Selling | Buying | Selling`

Columns: col0=Currency name, col1=Code, col2=cash_buy, col3=cash_sell, col4=txn_buy, col5=txn_sell, col6=avg_buy, col7=avg_sell

Sample (2026-10-10):
- USD: cash_buy=164.3201 cash_sell=167.6065 txn_buy=161.6865 txn_sell=164.9202 avg_buy=... avg_sell=...
- EUR: cash_buy=190.2415 cash_sell=194.0463 txn_buy=187.5051 txn_sell=191.2552

Note: avg columns show "..." in survey — likely JS-rendered or empty. TO VERIFY.

## Key observations
- Cash and transactional values differ (e.g. USD cash_buy=164.3201 vs txn_buy=161.6865). These are distinct observations.
- No date visible in table headers. effective_date_basis = collection_date_fallback → identity_status = ambiguous.
- "AVERAGE" columns may be weighted average. TO VERIFY category label and whether values are populated.
- 9 data rows (10 rows total including header).

## Identity strategy (PROPOSED)
- No source-published date → identity_status = ambiguous for all categories
- source_record_key: none

## Remaining TO VERIFY
1. Whether AVERAGE columns are populated (JS-rendered?)
2. Effective date source
3. Official-display comparison
4. Terms of use
