# Goh Betoch Mapping — Goh Betoch Bank
Source: https://www.gohbetbank.com/todays-exchange-rate/
Fetch timestamp: 2026-10-10T07:33:58Z — HTTP 200 — static HTML
Fixture: docs/evidence/wave_survey/survey_results.json (GOH_BETOCH entry)

## Table structure (KNOWN)

One table, 5 data rows:
Headers: `Currency cODE | Currency Name | buying | SELLING | Weighted Average Buying Rate | Weighted Average Selling Rate`

Columns: col0=code, col1=name, col2=buying, col3=selling, col4=weighted_buy, col5=weighted_sell

Sample (2026-10-10):
- USD: buy=161.7128 sell=164.9471 w_buy=163.9699 w_sell=166.4471
- EUR: buy=186.2605 sell=189.9857 w_buy=186.2605 w_sell=189.9857
- GBP: buy=213.8209 sell=218.0973 w_buy=213.8209 w_sell=218.0973
- AED: buy=43.8917 sell=44.7695 w_buy=43.8917 w_sell=44.7695

Also has a link to /yesterdays-exchange-rate/ — history available.

## Key observations
- Single table combines buying/selling and weighted average. Category of plain buying/selling is unresolved (cash or transactional?). TO VERIFY.
- No date in table. effective_date_basis = collection_date_fallback → identity_status = ambiguous for plain pair.
- Weighted average in same table — no separate date for weighted average. TO VERIFY if weighted avg has a different effective date.
- Yesterday's rate page exists — useful for identity verification.

## Identity strategy (PROPOSED)
- No source-published date → identity_status = ambiguous
- source_record_key: none

## Remaining TO VERIFY
1. Category of plain buying/selling (cash or transactional?)
2. Effective date source
3. Whether weighted average has a different date
4. Official-display comparison
5. Terms of use
