# Siinqee Mapping — Siinqee Bank
Source: https://siinqeebank.com/
Fetch timestamp: 2026-10-10T07:34:37Z — HTTP 200 — static HTML
Fixture: docs/evidence/wave_survey/survey_results.json (SIINQEE entry)

## Table structure (KNOWN)

One table, 7 rows:
Headers: `Currency | Buying | Selling`
Sample: USD buy=160.8993 sell=164.1173; EUR buy=186.6020 sell=190.3340; GBP buy=210.4047 sell=214.6128

## Key observations
- Single buying/selling pair. Category unresolved (cash or transactional?). TO VERIFY.
- No date in table. effective_date_basis = collection_date_fallback → identity_status = ambiguous.
- No currency code column — only currency name. TO VERIFY code mapping.
- Rate page is the homepage (siinqeebank.com/). Dedicated rate page at siinqeebank.com/foreign-currency/ may have more detail. TO VERIFY.

## Remaining TO VERIFY
1. Category of buying/selling
2. Effective date source
3. Currency name → code mapping
4. Whether dedicated rate page has more structure
5. Official-display comparison
6. Terms of use
