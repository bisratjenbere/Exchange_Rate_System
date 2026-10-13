# Hibret Mapping — Hibret Bank
Source: https://www.hibretbank.com.et/about/exchange-rate/
Fetch timestamp: 2026-10-10 (SSL cert error bypassed with verify=False for investigation only)
HTTP status: 200 — static HTML

## Table structure (KNOWN)

One table, 9 rows:
Headers row 0: `| | CASH | | TRANSACTION |`
Headers row 1: `| CURRENCY | BUYING | SELLING | BUYING | SELLING`

Sample: USD cash_buy=163.3499 cash_sell=166.6169 txn_buy=161.7326 txn_sell=164.9673

## Key observations
- Cash and transactional values differ — distinct observations.
- No date in table. effective_date_basis = collection_date_fallback → identity_status = ambiguous.
- SSL certificate verification fails. **Production adapter must handle SSL or use verify=False with explicit acknowledgment.** Record as a terms-of-use / access finding.
- 8 data rows (9 rows - 1 header).

## SSL finding
The server's SSL certificate cannot be verified by the system's CA bundle. This is a server configuration issue, not an access restriction. The adapter will need `verify=False` or a custom CA bundle. Record this finding and flag for review.

## Remaining TO VERIFY
1. Effective date source
2. Official-display comparison
3. SSL certificate resolution
4. Terms of use
