# Enat Mapping — Enat Bank
Source: https://www.enatbanksc.com/
Fetch timestamp: 2026-10-10T07:34:20Z — HTTP 200 — static HTML (rates in page text, no table)
Fixture: docs/evidence/wave_survey/survey_results.json (ENAT entry)

## Structure (KNOWN)

No table elements. Rates are embedded in page text as a structured block:
"Exchange Rate Oct 10, 2026 Swift ENATETAA Graph Cash Transaction Weighted Currency Buying Selling USD 161.3736 164.6011 EUR 187.0333 190.7740 GBP 215.1435 219.4464 CAD 114.3343 116.6210 AED 44.3507 45.2377 CNY 23.6960 24.1699"

## Key observations
- Date confirmed: "Oct 10, 2026". effective_date_basis = source_published.
- Three category tabs visible in text: "Cash Transaction Weighted" — but only one set of Buying/Selling values shown in static HTML. Active tab is likely "Cash". TO VERIFY which tab is default and whether other tabs load via JS.
- Currency and values are in page text, not a table. Parser must extract from text or find a hidden data structure.
- Swift code ENATETAA present — useful for bank identification.
- 6 currencies: USD, EUR, GBP, CAD, AED, CNY.

## Status
Static HTML contains rate data but not in table form. Text extraction possible but fragile. TO VERIFY which category the visible values represent and whether other categories require JS.

## Remaining TO VERIFY
1. Which category (Cash/Transaction/Weighted) is shown in static HTML
2. Whether other categories require JS rendering
3. Official-display comparison
4. Terms of use
