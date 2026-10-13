# Ahadu Mapping — Ahadu Bank
Source: https://ahadubank.com/
Fetch timestamp: 2026-10-10T07:34:17Z — HTTP 200 — static HTML (rates in page text, no table)
Fixture: docs/evidence/wave_survey/survey_results.json (AHADU entry)

## Structure (KNOWN)

No table elements. Rates visible in page text:
"Buying: 161.2929", "Selling: 164.5188", "Buying: 215.6425", "Selling: 219.9554"

## Key observations
- Rate values present in static HTML but no currency labels visible in the text snippet. Full page parse needed to associate values with currencies.
- No date visible in text snippet. effective_date_basis = collection_date_fallback → identity_status = ambiguous.
- No category label visible. TO VERIFY.
- Rate page is the homepage. TO VERIFY if a dedicated rate page exists.

## Status
Partial data visible in static HTML. Full page parse required to extract currency labels. TO VERIFY structure.

## Remaining TO VERIFY
1. Full page structure — currency labels for each rate pair
2. Effective date source
3. Category of buying/selling
4. Official-display comparison
5. Terms of use
