# Sidama Mapping — Sidama Bank
Source: https://sidamabanksc.com/exchange-rate/
Fetch timestamp: 2026-10-10T07:34:04Z — HTTP 200 — static HTML (rates in page text, no table)
Fixture: docs/evidence/wave_survey/survey_results.json (SIDAMA entry)

## Structure (KNOWN)

No table elements. Rates embedded in page text per currency block:
"USD United States Dollar Cash Buying 161.7237 Birr Cash Selling 164.9582 Birr Transactional Buying 161.7237 Birr Transactional Selling 164.9582 Birr Prev Weighted Buying No Trade Prev Weighted Selling No Trade"
"EUR Euro Cash Buying 184.1252 Birr Cash Selling 187.8075 Birr Transactional Buying 184.1252 Birr Transactional Selling 187.8075 Birr Prev Weighted Buying No Trade Prev Weighted Selling No Trade"

## Key observations
- All three categories present in text: Cash Buying/Selling, Transactional Buying/Selling, Prev Weighted Buying/Selling.
- "Prev Weighted" label — weighted average is for the previous period. effective_date for weighted may differ. TO VERIFY.
- "No Trade" = NULL. TO VERIFY.
- "Birr" unit label confirms quote currency = ETB.
- No date visible in text snippet. effective_date_basis = collection_date_fallback → identity_status = ambiguous.
- Cash and transactional values identical for USD and EUR in this fetch.
- Dedicated rate page: sidamabanksc.com/exchange-rate/ — good.

## Status
Rich data in static HTML text. Parser must extract structured data from text blocks. No table — text extraction required.

## Remaining TO VERIFY
1. Effective date source
2. "Prev Weighted" date semantics
3. "No Trade" = NULL confirmation
4. Official-display comparison
5. Terms of use
