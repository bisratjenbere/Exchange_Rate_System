# Global Bank Mapping — Global Bank Ethiopia
Source: https://www.globalbankethiopia.com/
Fetch timestamp: 2026-10-10T07:34:32Z — HTTP 200 — static HTML
Fixture: docs/evidence/wave_survey/survey_results.json (GLOBAL entry)

## Table structure (KNOWN)

Two tables, both with headers: `Currency | Buying | Selling`

**Table 0** — 5 rows: USD buy=161.5581 sell=164.7893; EUR buy=186.6421 sell=190.3749; GBP buy=212.9912 sell=217.2510
**Table 1** — 5 rows (weighted average?): USD buy=164.9606 sell=164.7893; EUR=No Trade/No Trade; GBP=No Trade/No Trade

Note: USD in table 1 has buy=164.9606 > sell=164.7893 — buying above selling. Review signal.

## Key observations
- No date in either table. effective_date_basis = collection_date_fallback → identity_status = ambiguous.
- Category of table 0 is unresolved (cash or transactional?). TO VERIFY.
- Table 1 category unresolved (weighted average?). TO VERIFY.
- USD table 1: buying > selling — suspicious. Flag for review.
- "No Trade" = NULL. TO VERIFY.
- No currency code column — only currency name. TO VERIFY code mapping.

## Remaining TO VERIFY
1. Category of each table
2. Effective date source
3. USD buying > selling in table 1 (review signal)
4. Currency name → code mapping
5. Official-display comparison
6. Terms of use
