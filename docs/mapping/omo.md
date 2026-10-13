# Omo Mapping — Omo Bank
Source: https://omobanksc.com/
Fetch timestamp: 2026-10-10T07:34:34Z — HTTP 200 — static HTML
Fixture: docs/evidence/wave_survey/survey_results.json (OMO entry)

## Table structure (KNOWN)

Three tables — date embedded in each table header:

**Table 0** — Cash (8 rows)
Header: `07/10/2026 | Cash Buying Rate | Cash Selling Rate`
Sample: USD buy=160.3720 sell=163.5794; EUR buy=182.5675 sell=186.2188; GBP buy=214.0325 sell=218.3131

**Table 1** — Transactional (8 rows)
Header: `07/10/2026 | Transaction Buying Rate | Transaction Selling Rate`
Sample: USD buy=159.7662 sell=162.9455; EUR buy=181.8778 sell=185.4972; GBP buy=213.2240 sell=217.4671

**Table 2** — Weighted Average (8 rows)
Header: `06/10/2026 | WEIGHTED AVR BUYING RATE | WEIGHTED AVR SELLING RATE`
Sample: USD=No Trade/No Trade; EUR=No Trade/No Trade; GBP=No Trade/No Trade

## Key observations
- Date in each table header in format DD/MM/YYYY. Cash and transactional = 07/10/2026; weighted = 06/10/2026. Per-table dates confirmed.
- effective_date_basis = source_published for all three tables.
- Cash and transactional values differ (USD cash_buy=160.3720 vs txn_buy=159.7662). Distinct observations.
- "No Trade" = NULL. TO VERIFY.
- Date format DD/MM/YYYY — must parse carefully (not YYYY-MM-DD).
- Currency field contains "USD – US Dollar" format — split on " – " to get code.

## Identity strategy (PROPOSED)
- effective_date from table header (parse DD/MM/YYYY)
- source_record_key: none — identity via source_id + currency + category + effective_date
- identity_status = derived

## Remaining TO VERIFY
1. "No Trade" = NULL confirmation
2. Official-display comparison
3. Terms of use
4. Whether the homepage always has the rate tables (not a dedicated rate page)
