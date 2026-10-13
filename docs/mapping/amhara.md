# Amhara Mapping — Amhara Bank
Source: https://www.amharabank.com/daily-exchange-rate/
Fetch timestamp: 2026-10-10 (SSL cert error bypassed with verify=False for investigation only)
HTTP status: 200 — static HTML

## Table structure (KNOWN)

Two tables:

**Table 0** — Cash + Transactional (9 rows)
Headers: `Currency | Cash Buying | Cash Selling | Transaction Buying | Transaction Selling`
Sample: USD cash_buy=161.6999 cash_sell=164.9339 txn_buy=161.6999 txn_sell=164.9339
GBP: cash_buy=213.7188 cash_sell=217.9931 txn_buy=213.7188 txn_sell=217.9931

Currency format: "US Dollar (USD)" — name with code in parentheses. Parse code from parentheses.

**Table 1** — Weighted Average (8 rows)
Headers: `Currency | Buying | Selling`
Sample: USD buy=164.1179 sell=164.9339; GBP=NO TRADE/NO TRADE

## Key observations
- Clear column headers for cash and transactional — no ambiguity.
- "NO TRADE" = NULL. TO VERIFY.
- Cash and transactional values identical for USD and GBP in this fetch.
- No date in either table. effective_date_basis = collection_date_fallback → identity_status = ambiguous.
- SSL certificate verification fails — same issue as Hibret.
- Currency format "US Dollar (USD)" — extract code from parentheses.

## SSL finding
Same as Hibret — server SSL certificate cannot be verified. Adapter needs `verify=False` or custom CA.

## Remaining TO VERIFY
1. Effective date source
2. "NO TRADE" = NULL confirmation
3. Official-display comparison
4. SSL certificate resolution
5. Terms of use
