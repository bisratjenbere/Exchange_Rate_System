# Addis International Bank (ADIB) — source mapping

Source: https://api.addisbanksc.com/api/exchange-rates  
Adapter key: adib_api  
Adapter family: B2  
Capture: docs/evidence/addis/2026-10-10-exchange-rates.json  
Capture timestamp: 2026-10-10 (exact time not recorded)  
Official-display comparison: NOT DONE — API currently 403  
Mapping status: partially_verified  

## Field map

| Source field | Pipeline field | Status | Notes |
|---|---|---|---|
| id | source_record_key | KNOWN | Row number, not publication id. Stable across fetches TO VERIFY. |
| currency | source_currency_code | KNOWN | ISO code string. ETB row (id=1) skipped — quote currency. |
| buying | (skipped) | TO VERIFY | Equals transactionBuying for USD/EUR/GBP. Category unconfirmed. ADR-006 §6: skip plain pair until confirmed. |
| selling | (skipped) | TO VERIFY | Same as above. |
| transactionBuying | buying_rate (category=transactional) | KNOWN | Non-zero positive values observed. "0.0000" → None. |
| transactionSelling | selling_rate (category=transactional) | KNOWN | Same. |
| weightedBuying | buying_rate (category=weighted_average) | KNOWN | "0.0000" and null both → None. |
| weightedSelling | selling_rate (category=weighted_average) | KNOWN | Same. |
| createdAt | (not used) | KNOWN | Identical across rows — row creation time, not publication date. |
| updatedAt | (not used as effective_date) | TO VERIFY | Last-edit time. Meaning as effective date unverified. Not used for identity. |

## Identity

- No source-published effective_date field → effective_date_basis = unknown → identity_status = ambiguous
- source_record_key = str(id) — row number, not a publication discriminator
- ADR-007: value-change deduplication applies (same fingerprint = no new row)

## Category decisions

- transactional: KNOWN from field name transactionBuying/transactionSelling
- weighted_average: KNOWN from field name weightedBuying/weightedSelling
- plain buying/selling: SKIPPED — category TO VERIFY (equals transactional for USD/EUR/GBP in fixture)

## Sentinel normalization

- "0.0000" → None (not offered)
- null → None (not offered)
- ETB row (id=1, buying="1.0000") → skipped entirely (quote currency)

## Review signals (from fixture)

- GBP weightedBuying 224.5035 is exactly 10.0000 above buying 214.5035 — suspicious
- USD weightedSelling 170.4175 well above selling 164.9103 — suspicious
- KWD: all transaction values "0.0000" — entire row would produce no valid observations

## Open items (TO VERIFY)

- Official-display comparison for at least 3 currencies
- Repeat fetch to confirm id stability
- updatedAt semantics as effective date
- Category of plain buying/selling
- Zero-value meaning confirmed as not-offered
- HTTP status and headers on successful fetch
- Empty and error response behavior
