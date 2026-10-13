# Rammis Mapping — Rammis Bank
Source: https://rammisbank.et/api/v1/exchange-rates/latest?base_currency=ETB
Fetch timestamp: 2026-10-10T07:33:38Z — HTTP 200
Fixture: docs/evidence/wave_survey/RAMMIS.json

## Response structure (KNOWN from fixture)

Top-level object with three fields:

| Field | Type | Example | Notes | Status |
|-------|------|---------|-------|--------|
| `base_currency` | string | `"ETB"` | Quote currency — ETB confirmed | KNOWN |
| `effective_date` | string YYYY-MM-DD | `"2026-10-10"` | Top-level effective date | KNOWN |
| `rates` | array | 17 items | One item per currency | KNOWN |

Each rate item:

| Field | Type | Example | Canonical target | Status |
|-------|------|---------|-----------------|--------|
| `id` | integer | 5 | source_record_key — stable per currency row | TO VERIFY |
| `base_currency` | string | `"ETB"` | quote_currency_code = ETB | KNOWN |
| `currency` | string | `"USD"` | source_currency_code → canonical currency_code | KNOWN |
| `effective_date` | string YYYY-MM-DD | `"2026-10-10"` | effective_date; basis = source_published | KNOWN |
| `buying` | string decimal | `"161.356300"` | buying_rate | KNOWN |
| `selling` | string decimal | `"164.583400"` | selling_rate | KNOWN |
| `created_at` | ISO timestamp | `"2025-11-25T05:42:46.988873Z"` | row creation; not effective date | KNOWN |

## Key observations

- `base_currency = ETB` confirmed at both envelope and record level. Quote currency is ETB. Unit multiplier = 1 (implied).
- `effective_date` is explicit per record. Dates vary per currency (e.g. CHF = 2026-10-07, AED = 2026-09-26 vs USD = 2026-10-10) — rows are updated independently.
- No category field — only one rate pair (buying/selling) per currency. Category is unresolved: likely transactional but TO VERIFY.
- No zero values in this fixture. No null values.
- 17 currencies: AED, AUD, CAD, CHF, CNY, DJF, DKK, EUR, GBP, INR, JPY, KES, KWD, NOK, SAR, SEK, USD.
- `id` values are non-sequential (5, 26, 25, 18…) — likely stable database IDs, not row numbers. TO VERIFY across fetches.

## Identity strategy (PROPOSED)

- `source_record_key` = `id` (integer, per currency row)
- `effective_date` = per-record `effective_date` field; basis = source_published
- `logical_observation_key` = `source_id + id` (if id is stable) or `source_id + currency + effective_date`
- TO VERIFY: whether `id` is stable across fetches or changes when rates are updated

## Category (TO VERIFY)

No category field. Single buying/selling pair. Likely transactional. TO VERIFY against official Rammis display.

## Official display comparison (TO VERIFY)

Not performed. TO VERIFY: fetch official Rammis page and compare USD, EUR, GBP values.

## Remaining TO VERIFY

1. Category of buying/selling (transactional assumed)
2. Stability of `id` across fetches
3. Official-display comparison
4. Terms of use / robots.txt
5. Empty/error response behavior
6. Whether per-currency effective_date differences are intentional
