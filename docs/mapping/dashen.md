# Dashen Mapping — Dashen Bank
Source: https://dashenbanksc.com/daily-exchange-rates/
Fetch timestamp: 2026-10-10T07:23:34Z
HTTP status: 200
Content-type: text/html; charset=UTF-8
Fixture: docs/evidence/dashen/2026-10-10-exchange-rates.html

## Response structure (VERIFIED from fixture)

Static HTML page. Three `<table>` elements in document order.

## Table 0 — Transactional (VERIFIED)

Header row: `Currency Code | Currency Name | Transaction Buying | Transaction Selling | Spread`

| Source column | Canonical target | Status |
|--------------|-----------------|--------|
| Currency Code | source_currency_code | VERIFIED |
| Currency Name | currency_name | VERIFIED |
| Transaction Buying | buying_rate, category=transactional | VERIFIED |
| Transaction Selling | selling_rate, category=transactional | VERIFIED |
| Spread | ignore (derived value) | VERIFIED |

Currencies seen (9 rows): USD, GBP, AED, EUR, SAR, CAD, CHF, CNY, KWD

Sample values (2026-10-10):
- USD: buying=160.8707, selling=164.0881
- GBP: buying=212.8460, selling=217.1029
- EUR: buying=187.2025, selling=190.9465

## Table 1 — Cash (VERIFIED)

Header row: `Currency Code | Currency Name | Cash Buying | Cash Selling | Spread`

| Source column | Canonical target | Status |
|--------------|-----------------|--------|
| Currency Code | source_currency_code | VERIFIED |
| Currency Name | currency_name | VERIFIED |
| Cash Buying | buying_rate, category=cash | VERIFIED |
| Cash Selling | selling_rate, category=cash | VERIFIED |
| Spread | ignore | VERIFIED |

Currencies seen (7 rows): USD, EUR, GBP, CAD, CHF, CNY, KWD

Sample values (2026-10-10):
- USD: buying=160.8707, selling=164.0881
- EUR: buying=187.2025, selling=190.9465
- GBP: buying=212.8460, selling=217.1029

Note: Cash and transactional values are identical for USD/EUR/GBP on this date. Whether this is always the case is TO VERIFY.

## Table 2 — Weighted Average (VERIFIED structure; date semantics VERIFIED)

Header row: `Currency Code | Currency Name | Weighted Average Rate on <date>`
Sub-header: `Buying | Selling`

**Key finding:** The weighted average table header explicitly states the date: "Weighted Average Rate on October 09, 2026" — one day before the page fetch date of 2026-10-10. This confirms per-table dates can differ.

| Source column | Canonical target | Status |
|--------------|-----------------|--------|
| Currency Code | source_currency_code | VERIFIED |
| Currency Name | currency_name | VERIFIED |
| Buying (col 3) | buying_rate, category=weighted_average | VERIFIED |
| Selling (col 4) | selling_rate, category=weighted_average | VERIFIED |

Currencies seen (5 rows): USD, EUR, SAR, GBP, CNY (fewer than transactional/cash)

Sample values (effective 2026-10-09):
- USD: buying=163.8186, selling=166.0636
- EUR: buying=190.8878, selling=194.9876
- SAR: buying=45.2519, selling=46.1569

## Date semantics (VERIFIED)

- Transactional and cash tables: no explicit date in the table. The page was fetched 2026-10-10; these are assumed to be the current day's rates. **effective_date_basis = collection_date_fallback for transactional/cash** (no source-published date found in the table itself).
- Weighted average table: date is embedded in the column header text. Parse with regex. **effective_date_basis = source_published for weighted_average**.
- Per-table dates must be preserved separately (gap review test F). Do not apply a page-wide date to all tables.

## Identity strategy (PROPOSED — TO VERIFY)

No stable record ID in the HTML. Identity candidates:
- Transactional/cash: `source_id + currency_code + category + collection_date_fallback`. Since fallback dates never participate in identity (LOCKED rule), these records will have `identity_status = ambiguous` until a source-published date is found in the page.
- Weighted average: `source_id + currency_code + category + effective_date` (date from header). `identity_status = derived`.

**This is the primary identity risk for Dashen.** Transactional and cash observations will be ambiguous unless a publication date is found elsewhere on the page (e.g. a page-level date element). TO VERIFY: whether the page contains a publication date outside the weighted average header.

## Selectors (VERIFIED)

- All three tables: `soup.find_all("table")` — index 0=transactional, 1=cash, 2=weighted_average.
- Header row: `table.find("tr")` — first row is headers.
- Data rows: remaining `<tr>` elements.
- Weighted average date: regex on header cell text, e.g. `r"on\s+(\w+ \d+, \d{4})"`.

## Partial failure behavior (TO VERIFY)

If one table is missing or malformed, the other tables must still be processed independently. This is a requirement (acceptance test 9 analogue for Dashen), not yet tested against a live partial-failure scenario.

## Official display comparison (TO VERIFY)

The page is static HTML and the values are directly visible. A browser comparison is straightforward but has not been performed in this session. The values above are from the raw HTML fetch and are consistent with expected ETB/foreign-currency rates for October 2026.

**Status: TO VERIFY** — need to confirm fetched values match what a user sees in a browser for USD, EUR, GBP across both buying and selling sides.

## Currency codes (TO VERIFY)

Codes seen: USD, GBP, AED, EUR, SAR, CAD, CHF, CNY, KWD. All appear to be standard ISO 4217. TO VERIFY: confirm no non-standard codes appear across multiple fetches.

## Quote currency and unit multiplier (TO VERIFY)

No explicit quote_currency or unit_multiplier field. ETB implied. TO VERIFY.

## Terms of use (TO VERIFY)

Not checked in this session. TO VERIFY: robots.txt and terms of use for dashenbanksc.com.

## Remaining TO VERIFY items

1. Browser comparison of fetched values vs official display (USD, EUR, GBP)
2. Whether transactional/cash tables have a publication date anywhere on the page
3. Zero or missing values behavior
4. Partial table failure behavior
5. Currency codes across multiple fetches
6. Terms of use / robots.txt
7. Whether cash and transactional values always match (or differ on some dates)
