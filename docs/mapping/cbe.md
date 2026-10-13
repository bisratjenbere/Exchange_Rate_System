# CBE Mapping — Commercial Bank of Ethiopia
Source: https://combanketh.et/cbeapi/daily-exchange-rates/
Fetch timestamp: 2026-10-10T07:09:45Z (first fetch) and 2026-10-10T07:23:07Z (rates page check)
HTTP status: 200
Fixture: docs/evidence/cbe/2026-10-10-exchange-rates.json (100 records)

## Response structure (VERIFIED from fixture)

Top-level: JSON array. Each element is one publication record (one date).

| Field | Type | Example | Notes | Status |
|-------|------|---------|-------|--------|
| `id` | string (MongoDB ObjectID) | `"609278320e47d52aafd34f23"` | Stable per publication record. `id == _id`. | VERIFIED |
| `_id` | string | same as `id` | Duplicate of `id` | VERIFIED |
| `Date` | string `YYYY-MM-DD` | `"2021-09-22"` | Publication/effective date. One record per date. | VERIFIED |
| `published_at` | ISO timestamp | `"2021-09-22T08:24:51.191Z"` | CMS publish time, not the effective date | VERIFIED |
| `ExchangeRate` | array | 20 items | One item per currency | VERIFIED |
| `createdAt` | ISO timestamp | — | CMS record creation | KNOWN |
| `updatedAt` | ISO timestamp | — | CMS last update | KNOWN |
| `__v` | int | 0 | Mongoose version key; ignore | KNOWN |

## ExchangeRate array item fields (VERIFIED from fixture)

| Field | Type | Example | Canonical target | Status |
|-------|------|---------|-----------------|--------|
| `id` | string (ObjectID) | `"609278320e47d52aafd34f24"` | source_record_key (per currency within publication) | VERIFIED |
| `currency.CurrencyCode` | string | `"USD"` | source_currency_code → canonical currency_code after mapping verified | VERIFIED |
| `currency.CurrencyName` | string | `"US DOLLAR"` | currency_name | VERIFIED |
| `cashBuying` | number or 0 | `45.9571` | buying_rate for category=cash; 0 means not offered → NULL | TO VERIFY (zero=NULL rule needs official confirmation) |
| `cashSelling` | number or 0 | `46.8762` | selling_rate for category=cash | TO VERIFY (same) |
| `transactionalBuying` | number or 0 | `45.9571` | buying_rate for category=transactional | TO VERIFY (same) |
| `transactionalSelling` | number or 0 | `46.8762` | selling_rate for category=transactional | TO VERIFY (same) |
| `__component` | string | `"exchange-rate.exchange-rate"` | ignore | KNOWN |

## Identity strategy (VERIFIED from fixture)

- One publication record per `Date`. `id` (ObjectID) is stable per publication.
- `source_publication_key` = top-level `id` (ObjectID string)
- `source_record_key` = ExchangeRate item `id` (ObjectID string)
- `logical_observation_key` = `source_id + source_record_key` (stable, confirmed)
- `effective_date` = `Date` field; `effective_date_basis` = `source_published`

## Date semantics (VERIFIED from fixture)

- `Date` field is the effective date of the publication. `?Date=YYYY-MM-DD` filters to exactly one record.
- `published_at` is the CMS publish timestamp, not the effective date.
- Default fetch (no params) returns 100 records ordered oldest-first.

## _limit parameter (VERIFIED from live test)

- `_limit=1` returns exactly 1 record. **Never send `_limit=1`** — it silently truncates to one publication date.
- To fetch today's rates: use `?Date=YYYY-MM-DD` with today's date.

## Official display comparison

The CBE exchange-rates page (https://combanketh.et/exchange-rates) is JavaScript-rendered. No static HTML tables are present. The API at combanketh.et/cbeapi/ is CBE's own backend — it is the authoritative data source for the official display. A browser-rendered comparison is needed to confirm displayed values match API values.

**Status: TO VERIFY** — browser rendering required to confirm API values match what a user sees on the official page. The API is CBE's own domain and backend, making it the primary official source, but a visual comparison has not been performed.

## Zero values (TO VERIFY)

1205 zero values found across 100 records. Pattern: some currencies have cash=0 but transactional>0 (e.g. INR, KES, SDR, ZAR) and vice versa (SAR, AED have cash>0 but transactional=0). This strongly suggests zero means "not offered for this category" rather than a data error. **Recommendation: treat 0 as NULL (not offered), flag with validation_status=warning until confirmed by official display.**

## Categories (VERIFIED field names; semantics TO VERIFY)

- `cashBuying`/`cashSelling` → category=`cash`
- `transactionalBuying`/`transactionalSelling` → category=`transactional`
- No weighted average fields present in CBE API.

## Currency codes (TO VERIFY)

Codes seen: USD, GBP, EUR, CHF, SEK, NOK, DKK, DJF, JPY, CAD, SAR, AED, XAF, INR, KES, AUD, SDR, ZAR, CNY, KWD. All appear to be standard ISO 4217 codes except SDR (XDR in ISO). **TO VERIFY: whether SDR maps to XDR or is a bank-specific code.**

## Quote currency and unit multiplier (TO VERIFY)

No quote_currency or unit_multiplier field in the API. ETB is implied (rates are ETB per 1 foreign currency unit). TO VERIFY against official display.

## Terms of use

Documentation URL: https://combanketh.et/Exchange-rate-documentation (returns 404 in static fetch; likely JS-rendered). Terms of use finding: **TO VERIFY** — page not readable without browser rendering.

## Remaining TO VERIFY items

1. Browser-rendered comparison of API values vs official page display (USD, EUR, GBP minimum)
2. Zero = not offered confirmation from official display
3. SDR currency code mapping (ISO XDR vs bank-specific SDR)
4. Terms of use / robots.txt
5. Empty response behavior (date with no publication)
6. Error response behavior (invalid date, server error)
