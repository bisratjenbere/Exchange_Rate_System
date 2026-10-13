# Wegagen Mapping — Wegagen Bank
Source: https://weg.back.strapi.wegagen.com/api/exchange-rates?populate=*
Fetch timestamp: 2026-10-10T07:33:40Z — HTTP 200
Fixture: docs/evidence/wave_survey/WEGAGEN.json

## Response structure (KNOWN from fixture)

Strapi v4 envelope:

| Field | Type | Notes | Status |
|-------|------|-------|--------|
| `data` | array | 10 items, one per currency | KNOWN |
| `meta.pagination` | object | page=1, pageSize=25, total=10 | KNOWN |

Each `data` item has `id` (integer) and `attributes` object:

| Attribute | Type | Example | Canonical target | Status |
|-----------|------|---------|-----------------|--------|
| `date` | string YYYY-MM-DD | `"2026-10-08"` | effective_date; basis = source_published | KNOWN |
| `code` | string | `"USD"` | source_currency_code → canonical currency_code | KNOWN |
| `unit` | integer | `1` | unit_multiplier = 1 (confirmed for all 10 records) | KNOWN |
| `buying` | number | `161.7253` | buying_rate | KNOWN |
| `selling` | number | `164.9598` | selling_rate | KNOWN |
| `tra_buying` | number | `161.7253` | transactional buying — equals buying in all records | KNOWN |
| `tra_selling` | number | `164.9598` | transactional selling — equals selling in all records | KNOWN |
| `createdAt` | ISO timestamp | `"2024-08-06T07:40:29.494Z"` | row creation; ignore | KNOWN |
| `updatedAt` | ISO timestamp | `"2026-10-08T06:11:22.527Z"` | last edit; not effective date | KNOWN |
| `publishedAt` | ISO timestamp | `"2024-08-06T07:42:55.377Z"` | Strapi publish; not effective date | KNOWN |
| `flag` | nested object | image metadata | ignore | KNOWN |

## Key observations

- `unit = 1` for all 10 records. unit_multiplier = 1 confirmed.
- `buying == tra_buying` and `selling == tra_selling` for all records in this fixture. Category is ambiguous: are `buying`/`selling` cash and `tra_buying`/`tra_selling` transactional, or are they duplicates? TO VERIFY.
- `date` varies per currency (e.g. AED = 2026-09-26, JPY = 2026-10-05, CHF = 2026-10-07, USD/GBP/EUR = 2026-10-08). Rows updated independently.
- `id` values: 1, 2, 3, 4, 5, 7, 9, 13, 14, 15 — non-sequential, likely stable Strapi IDs. TO VERIFY.
- No weighted average fields. No zero values. No null rate values.
- 10 currencies: USD, GBP, EUR, CHF, SEK, CNY, AED, JPY, CAD, SAR.
- Pagination: total=10, pageSize=25 — all records fit in one page.

## Identity strategy (PROPOSED)

- `source_record_key` = `data[].id` (Strapi integer ID, likely stable)
- `effective_date` = `attributes.date`; basis = source_published
- `logical_observation_key` = `source_id + record_id`
- TO VERIFY: id stability across fetches

## Category (TO VERIFY)

`buying`/`selling` vs `tra_buying`/`tra_selling` — values are identical in this fixture. Possible interpretations: (a) cash vs transactional, (b) both are transactional duplicates. TO VERIFY against official Wegagen display.

## Official display comparison (TO VERIFY)

Not performed. TO VERIFY: compare USD, EUR, GBP values against official Wegagen page.

## Remaining TO VERIFY

1. Category of `buying`/`selling` vs `tra_buying`/`tra_selling`
2. Stability of `id` across fetches
3. Official-display comparison
4. Terms of use
5. Empty/error response behavior
6. Whether per-currency date differences are intentional
