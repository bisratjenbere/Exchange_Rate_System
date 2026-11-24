# Principles: meaning, signals, and when NOT to apply

## Contents
- SOLID
- Beyond SOLID
- Correctness lens (check first)
- Clean code
- Testability and tests
- Security and operations

## SOLID
- **SRP**: one reason to change. Signal: a function that parses, validates, and persists; a module edited for unrelated requests. Do not split code that always changes together.
- **OCP**: add behavior without editing working code. Signal: every new variant edits an if/elif chain in several files. Do not add extension points for variants that do not exist (YAGNI).
- **LSP**: subtypes honor the base contract. Signal: overrides that raise NotImplemented or weaken guarantees; callers checking the concrete type.
- **ISP**: small, role-focused interfaces. Signal: implementers stubbing unused methods; mocks that need ten methods for one use.
- **DIP**: depend on abstractions at boundaries. Signal: domain logic importing the database driver or HTTP client; hard-coded construction of collaborators. Do not add interfaces with a single implementation and no test seam.

## Beyond SOLID
- **DRY means one source of knowledge**, not identical text. Duplicated business rules are defects; coincidentally similar code that changes for different reasons should stay separate. Rule of three before abstracting.
- **KISS / YAGNI**: simplest design that works; no speculative generality.
- **High cohesion, low coupling**: signals are shotgun surgery (one change touches many files) and divergent change (one file changes for many reasons).
- **Composition over inheritance**: inheritance only for true is-a relationships with stable contracts.
- **Law of Demeter**: avoid long chains reaching through objects (`a.b.c.d()`).
- **Separation of concerns and dependency direction**: the core domain has no dependency on frameworks, I/O, or UI.
- **Command-query separation**: functions either change state or return data, not a surprising mix.
- **Fail fast, explicit errors**: validate at boundaries; use specific exception types; no swallowed exceptions; no sentinel values that conflate different meanings.
- **Make illegal states unrepresentable**: enums, value objects, and database constraints instead of conventions and magic strings.
- **Principle of least surprise**: names and signatures match behavior; no hidden side effects.
- **Immutability by default** for data passed between layers.

## Correctness lens (check first)
- Check-then-act races; read-modify-write without locking or constraints
- Transaction scope: who commits, partial failure, atomicity of multi-step writes
- Invariants enforced only in code but not in the database
- Idempotency of retried operations
- Hidden clocks, randomness, timezones, locale, float for money, non-canonical serialization
- Silent data loss: swallowed errors, default values that mask bad input

## Clean code
- Names reveal intent; one level of abstraction per function; function length and parameter count as signals (more than about four parameters suggests a missing concept)
- Comments explain why, not what; delete dead code and unused imports
- One consistent error-handling strategy across the codebase

## Testability and tests
- Seams for time, randomness, network, filesystem, and database
- Tests are deterministic, independent, fast, and assert behavior, not implementation
- Pyramid shape: many unit tests, fewer integration tests, few end-to-end tests
- Critical logic has characterization or golden tests; mocks do not replace the thing under test
- Coverage is a lead, not a goal: check that assertions would actually fail if the logic broke

## Security and operations
- Parameterized queries, input validation, output encoding, secrets out of code, least privilege, safe deserialization
- Structured logging, no sensitive data in logs, timeouts and bounded retries, configuration via environment
