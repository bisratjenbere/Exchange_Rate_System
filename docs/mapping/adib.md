# Addis Mapping — Addis International Bank
Source: https://api.addisbanksc.com/api/exchange-rates
Original fixture: docs/evidence/addis/2026-10-10-exchange-rates.json (captured 2026-10-10, exact time unknown)
Re-fetch attempt: 2026-10-10T07:24:08Z → HTTP 403 (access blocked)

## Access status

The API returned HTTP 403 on the re-fetch attempt (2026-10-10T07:24:08Z). The original fixture was captured earlier and is the only available evidence. The official website (addisbanksc.com) is JavaScript-rendered with no static rate tables.

**Source status: BLOCKED for live verification this session.** The existing fixture is used for mapping analysis only. No official-display comparison has been performed.

## Response structure (KNOWN from fixture — not re-verified)

Top-level: JSON array of 8 records. No envelope.

| Field | Type | Example | Notes | Status |
|-------|------|---------|-------|--------|
| `id` | integer | 1–8 | Row number, not a publication ID. Not stable as a publication identity. | KNOWN |
| `currency` | string | `"USD"` | Source currency code | KNOWN |
| `buying` | string (decimal) | `"161.6768"` | Plain buying rate — category unresolved | TO VERIFY |
| `selling` | string (decimal) | `"164.9103"` | Plain selling rate — category unresolved | TO VERIFY |
| `transactionBuying` | string (decimal) | `"161.6768"` | Transactional buying | TO VERIFY |
| `transactionSelling` | string (decimal) | `"164.9103"` | Transactional selling | TO VERIFY |
| `weightedBuying` | string or null | `"162.9240"` or null | Weighted average buying; null for ETB and KWD | TO VERIFY |
| `weightedSelling` | string or null | `"170.4175"` or null | Weighted average selling | TO VERIFY |
| `createdAt` | ISO timestamp | `"2025-05-28T08:16:48.000Z"` | Identical across all rows — row creation, not publication date | KNOWN |
| `updatedAt` | ISO timestamp | varies per row | Last edit time; meaning as effective date unverified | TO VERIFY |

## Category mapping (TO VERIFY)

| Source fields | Proposed canonical category | Status |
|--------------|----------------------------|--------|
| `buying` / `selling` | Unknown — equals transactional for USD/EUR/GBP | TO VERIFY |
| `transactionBuying` / `transactionSelling` | transactional | TO VERIFY |
| `weightedBuying` / `weightedSelling` | weighted_average | TO VERIFY |

**Open decision (needs owner):** For USD, EUR, GBP the plain `buying`/`selling` values equal `transactionBuying`/`transactionSelling`. The plain pair may be a duplicate of transactional, or a distinct cash rate. Do not ingest plain buying/selling as a separate observation until category is confirmed.

## Zero values (TO VERIFY)

`"0.0000"` appears as a string in buying/selling fields for SAR, CHF, AED, KWD (cash side) and in weightedSelling for EUR and GBP. The difference between `"0.0000"` (string) and `null` (JSON null) in weighted fields is unverified. **Recommendation: treat "0.0000" as NULL (not offered), flag with validation_status=warning, pending official-display confirmation.**

## ETB row (id=1)

All values are `"1.0000"`. This is the quote currency itself. **Do not ingest as a rate observation.**

## Identity strategy (TO VERIFY)

- `id` is a row number (1–8), not a publication ID. The API appears to edit rows in place with no history.
- `updatedAt` varies per row and is the only candidate for effective date, but its meaning is unverified.
- No stable publication identity exists in the current fixture.
- **Identity status will be `ambiguous` for all Addis observations until updatedAt semantics are confirmed.**
- Fallback: `source_id + currency_code + category + updatedAt` — but fallback dates never participate in identity per LOCKED rule. These records will be ambiguous candidates until confirmed.

## Review signals from fixture

- GBP `weightedBuying` = 224.5035 is exactly 10.0000 above `buying` = 214.5035 — possible data entry error or unit issue.
- USD `weightedSelling` = 170.4175 is well above `selling` = 164.9103 — unusual spread.
- KWD: all transaction values are `"0.0000"` and weighted values are null — possibly not offered.
- Oldest `updatedAt`: KWD at 2025-08-20 (over a year before capture). Newest: USD at 2026-09-30 (10 days before capture).

## Official display comparison

Not performed. The official website is JavaScript-rendered and the API returned 403 on re-fetch. **TO VERIFY: browser comparison required.**

## Terms of use

Not checked. API returned 403 — may indicate access controls. **TO VERIFY: check terms of use and whether the API is intended for public programmatic access.**

## Remaining TO VERIFY items

1. API access — resolve 403 (may be rate limiting, IP block, or intentional restriction)
2. Category of plain buying/selling
3. Zero-value meaning (not offered vs data error)
4. updatedAt as effective date
5. Official-display comparison for USD, EUR, GBP
6. Repeat fetch behavior and whether data changes between fetches
7. HTTP status and headers on successful fetch
8. Empty response behavior
9. Terms of use
