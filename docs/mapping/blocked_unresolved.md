# Hijra Mapping — Hijra Bank
Fetch attempt: 2026-10-10 — DNS resolution failure (hijrabank.com does not resolve)

## Finding
hijrabank.com does not resolve. No official source found. Source remains unresolved.
mapping_status = official_source_unresolved.
Wave 5 — deferred. Retry with alternative domain search.

---

# Siket Mapping — Siket Bank
Source: https://siketbank.com/exchange-rate
Fetch timestamp: 2026-10-10 — HTTP 403 (access blocked)

## Finding
HTTP 403 on both the exchange-rate page and likely the homepage. Access is blocked for programmatic requests.
mapping_status = source_identified_schema_unverified.
verification_status = unverified.
Wave 3 — deferred. May require browser rendering or different User-Agent.

---

# ZamZam Mapping — ZamZam Bank
Source: https://zamzambank.com/exchange-rates/
Fetch timestamp: 2026-10-10 — HTTP 403 (access blocked)

## Finding
HTTP 403. Access blocked for programmatic requests.
mapping_status = source_identified_schema_unverified.
Wave 3 — deferred. May require browser rendering.

---

# Abay Mapping — Abay Bank
Source: https://www.abaybanksc.com/exchange-rate (tried) and https://www.abaybanksc.com/ (tried)
Fetch timestamp: 2026-10-10 — HTTP 403 on both

## Finding
HTTP 403 on homepage and exchange-rate path. Access blocked.
mapping_status = source_identified_schema_unverified.
Wave 4 — deferred.

---

# Gadaa Mapping — Gadaa Bank
Source: https://gadaabank.com.et/ (homepage) and https://gadaabank.com.et/exchange-rate (tried)
Fetch timestamp: 2026-10-10 — HTTP 200 on both but no rate data in static HTML

## Finding
Homepage and exchange-rate path return 200 but no rate text or tables in static HTML. Rates are JS-rendered.
mapping_status = source_identified_schema_unverified.
collection_method = browser (JS-rendered).
Wave 4 — deferred.
