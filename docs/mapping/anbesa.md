# Anbesa Mapping — Anbesa International Bank
Source investigated: https://anbesabank.com/
Fetch timestamp: 2026-10-10 — HTTP 200

## Finding
The official Anbesa website (anbesabank.com) exists and references exchange rates ("Exchange Rate", "Weighted Avg. Rates" in page text, "#exchangerate" anchor links). Rates appear to be JS-rendered (no table in static HTML).

**Official source exists.** The kehulum.com mirror in the register is not needed if the official site can be scraped. However, rates require JS rendering.

## Status
source_authority = official (anbesabank.com is the bank's own domain).
mapping_status = source_identified_schema_unverified.
collection_method = browser (JS-rendered).
Wave 5 — deferred.

## Remaining TO VERIFY
1. JS-rendered rate structure
2. Category and field mapping
3. Effective date source
4. Terms of use
