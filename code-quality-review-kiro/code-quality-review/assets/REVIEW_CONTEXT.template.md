# REVIEW_CONTEXT.md  (place at the repo root; keep it under 30 lines)

## What this system is
<one or two sentences: purpose, users, size, maturity>

## Stack and commands
- Language/framework:
- Run tests:
- Lint / type check:

## Layers and dependency direction
<e.g. domain <- pipeline <- persistence/adapters. Nothing in domain may import infrastructure.>

## Invariants that must never break
<e.g. exactly one current row per logical key; money uses Decimal; fingerprints are deterministic>

## Intentional choices (do not flag as defects)
<e.g. raw SQL instead of an ORM for performance; a single-file script by design>

## Known debt already tracked
<items the team already knows about, with ticket links if any>

## Out of scope
<generated code, vendored libraries, legacy folders>
