# Tsehay Mapping — Tsehay Bank
Source: https://tsehaybank.com.et/exchange-rate/
Fetch timestamp: 2026-10-10T07:34:10Z — HTTP 200 — static HTML
Fixture: docs/evidence/wave_survey/survey_results.json (TSEHAY entry)

## Table structure (KNOWN)

Two tables:

**Table 0** — Cash + Transactional (9 rows)
Headers row 0: `CURRENCY | CASH | TRANSACTION`
Headers row 1: `BUYING | SELLING | BUYING | SELLING`
Sample: USD cash_buy=161.6012 cash_sell=164.8332 txn_buy=161.6012 txn_sell=164.8332
GBP: cash_buy=215.0910 cash_sell=219.3928 txn_buy=215.0910 txn_sell=219.3928

**Table 1** — Weighted Average (7 rows)
Headers: `Currency | Code | Buying | Selling`
Sample: USD buy=No Trade sell=169.7764; GBP=No Trade/No Trade; EUR=No Trade/No Trade

## Key observations
- No date in either table. effective_date_basis = collection_date_fallback → identity_status = ambiguous.
- Cash and transactional values identical in this fetch. TO VERIFY if always the same.
- "No Trade" = NULL. TO VERIFY.
- Weighted average table has Currency (name) and Code columns — good for currency mapping.
- 8 currencies in table 0 (inferred from 9 rows - 1 header).

## Identity strategy (PROPOSED)
- No source-published date → identity_status = ambiguous
- source_record_key: none

## Remaining TO VERIFY
1. Effective date source
2. "No Trade" = NULL confirmation
3. Official-display comparison
4. Terms of use
