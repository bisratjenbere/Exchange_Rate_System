# BOA Mapping — Bank of Abyssinia
Source: https://www.bankofabyssinia.com/exchange-rate-2/
Fetch timestamp: 2026-10-10 (SSL cert error bypassed with verify=False for investigation only)
HTTP status: 200 — static HTML

## Table structure (KNOWN)

One table, 34 rows. Date confirmed in table header: "October 10, 2026".

The page text reveals the full structure clearly:

**Cash Rates section:**
Headers: `Currency type | Cash Buying Rate | Cash Selling Rate`
Currencies (10): USD, GBP, EUR, AED, CHF, SEK, NOK, CAD, SAR, CNY

Sample: USD cash_buy=161.3129 cash_sell=164.5392; GBP cash_buy=215.4173 cash_sell=219.7256; EUR cash_buy=187.9632 cash_sell=191.7225

**Transaction Rates section:**
Headers: `Currency type | Transaction Buying Rate | Transaction Selling Rate`
Currencies (17): USD, GBP, CHF, SEK, NOK, DKK, DJF, INR, KES, JPY, CAD, AUD, SAR, AED, EUR, ZAR, CNY, KWD

Sample: USD txn_buy=160.8768 txn_sell=164.0943; GBP txn_buy=214.9223 txn_sell=219.2207

## Key observations
- Date confirmed: "October 10, 2026". effective_date_basis = source_published.
- Cash and transaction are separate sections within one table — parse by section header row.
- Cash and transactional values differ (USD cash_buy=161.3129 vs txn_buy=160.8768). Distinct observations.
- More currencies in transaction (17) than cash (10).
- No weighted average section visible.
- SWIFT code: ABYSETAA.
- SSL certificate verification fails — same issue as Hibret/Amhara.
- Currency format: "USD " with trailing space, or "US Dollar" — TO VERIFY exact format in table cells.

## Identity strategy (PROPOSED)
- effective_date from table header "October 10, 2026" — parse month name format
- source_record_key: none — identity via source_id + currency + category + effective_date
- identity_status = derived

## SSL finding
Same as Hibret/Amhara — server SSL certificate cannot be verified.

## Remaining TO VERIFY
1. Exact currency format in table cells (code vs name)
2. Official-display comparison
3. SSL certificate resolution
4. Terms of use
5. Whether weighted average exists on a different page
