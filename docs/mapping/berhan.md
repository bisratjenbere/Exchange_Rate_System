# Berhan Mapping — Berhan Bank
Source: https://berhanbanksc.com/exchange-rates/
Fetch timestamp: 2026-10-10T07:33:53Z — HTTP 200 — static HTML (rates in page text, no table)
Fixture: docs/evidence/wave_survey/survey_results.json (BERHAN entry)

## Structure (KNOWN)

No table elements. Rates visible in page text:
"Buying", "Selling", "1 USD ($)", "1 EUR (€)"

## Key observations
- Currency labels use "1 USD ($)" format — unit multiplier = 1 confirmed, ISO code present.
- Buying/Selling labels present but values not captured in survey snippet. Full page parse needed.
- No date visible. effective_date_basis = collection_date_fallback → identity_status = ambiguous.
- No category label visible. TO VERIFY.
- Rate page: berhanbanksc.com/exchange-rates/ — dedicated page exists.

## Status
Partial structure visible. Full page parse required. TO VERIFY all fields.

## Remaining TO VERIFY
1. Full rate values and currency list
2. Category of buying/selling
3. Effective date source
4. Official-display comparison
5. Terms of use
