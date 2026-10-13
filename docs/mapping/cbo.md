# CBO Mapping — Cooperative Bank of Oromia
Source: https://coopbankoromia.com.et/daily-exchange-rates/
Fetch timestamp: 2026-10-10T07:33:45Z — HTTP 200 — static HTML
Fixture: docs/evidence/wave_survey/survey_results.json (CBO entry)

## Table structure (KNOWN)

Two tables:

**Table 0 — Cash + Transactional combined**
Header row 0: `Exchange Rate October 10, 2026` (date embedded in header — effective_date confirmed)
Header row 1: `Currency | Cash | Transaction`
Header row 2: `Buying | Selling | Buying | Selling`
Data: 7 rows. Sample: USD cash_buy=160.8853 cash_sell=164.1030 txn_buy=160.8853 txn_sell=164.1030

**Table 1 — Weighted Average**
Headers: `Currency | Weighted Average Rate | (Buying | Selling)`
Data: 8 rows. Sample: USD buy=163.5992 sell=164.0979; GBP buy=- sell=- (dash = no trade)

## Key observations
- Effective date is in table 0 header: "Exchange Rate October 10, 2026". effective_date_basis = source_published for both tables.
- Dash `-` means no trade → NULL (not zero). TO VERIFY.
- Cash and transactional values identical for USD in this fetch. TO VERIFY if always the same.
- No explicit category label for weighted average table — inferred from header text. TO VERIFY.

## Identity strategy (PROPOSED)
- effective_date from table 0 header (parse "Exchange Rate Month DD, YYYY")
- source_record_key: none available — identity via source_id + currency + category + effective_date
- identity_status = derived

## Remaining TO VERIFY
1. Dash `-` = NULL (no trade) confirmation
2. Official-display comparison
3. Whether cash and transactional always match
4. Terms of use
