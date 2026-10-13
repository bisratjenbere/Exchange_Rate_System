# NIB Mapping — Nib International Bank
Source: https://www.nibbanksc.com/exchange-rate/
Fetch timestamp: 2026-10-10T07:34:01Z — HTTP 200 — static HTML
Fixture: docs/evidence/wave_survey/survey_results.json (NIB entry)

## Table structure (KNOWN)

Three tables:

**Table 0** — 1 row, header only: `Oct 10, 2026` — date header for the page. effective_date = 2026-10-10 confirmed.

**Table 1** — Cash + Transactional (8 rows)
Headers: `Country | Currency | Buying | Selling | Buying | Selling`
Note: two Buying/Selling pairs — likely cash and transactional but column labels are ambiguous. TO VERIFY which pair is which.
Sample: USD col2=160.9077 col3=164.1259 col4=160.9077 col5=164.1259 (identical in this fetch)

**Table 2** — Weighted Average (9 rows)
Headers: `Country | Currency | Buying | Selling`
Sample: USD buy=167.0678 sell=168.3352; GBP=No Trade; EUR buy=No Trade sell=194.7032; AED buy=46 sell=No Trade

## Key observations
- Date confirmed in table 0 header: "Oct 10, 2026". effective_date_basis = source_published.
- "No Trade" = NULL (not offered). TO VERIFY.
- AED weighted buy = "46" — truncated value? Likely "46.xxxx". TO VERIFY.
- Table 1 has two buying/selling pairs with no column labels distinguishing cash vs transactional. TO VERIFY column assignment.
- Country column is empty in data rows (only header has "Country").

## Identity strategy (PROPOSED)
- effective_date from table 0 header
- source_record_key: none — identity via source_id + currency + category + effective_date
- identity_status = derived

## Remaining TO VERIFY
1. Which pair in table 1 is cash vs transactional
2. "No Trade" = NULL confirmation
3. AED weighted buy truncation
4. Official-display comparison
5. Terms of use
