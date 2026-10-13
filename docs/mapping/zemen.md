# Zemen Mapping — Zemen Bank
Source: https://zemenbank.com/exchange-rates/
Fetch timestamp: 2026-10-10T07:33:42Z — HTTP 200 — static HTML (no tables; rates in page text)
Fixture: docs/evidence/wave_survey/survey_results.json (ZEMEN entry)

## Structure (KNOWN)

No table elements. Page text contains: "USD", "EUR", "GBP", "Buying: --"

## Key observations
- "Buying: --" suggests rates are not populated in static HTML — likely JS-rendered via AJAX.
- The register notes Zemen may use an underlying AJAX request. This is consistent with "--" placeholder values.
- collection_method should be `ajax_endpoint` or `browser`. TO VERIFY.
- Rate page: zemenbank.com/exchange-rates/ — dedicated page exists.

## Status: BLOCKED for static HTML collection

Rates appear to be loaded via AJAX/JS. Need to identify the underlying request. Deferred to Wave 2 investigation with browser tools.

## Remaining TO VERIFY
1. Underlying AJAX endpoint and request parameters
2. Actual response schema
3. Category mapping
4. Effective date source
5. Official-display comparison
6. Terms of use
