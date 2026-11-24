# Smell to pattern. Use a pattern only when the smell is verified in the code.

| Verified smell | Candidate | Use when | Avoid when |
|---|---|---|---|
| Long if/elif or switch on a type, repeated in many places | Strategy, or polymorphism | 3+ variants and new ones are expected | Two variants, or the switch lives in one place: keep it |
| Construction logic scattered; callers must know concrete classes | Factory function | Creation has real branching or configuration | A plain constructor suffices |
| Long parameter list; values always travel together | Parameter object (dataclass / value object) | 4+ related params passed through several layers | Params are unrelated |
| Data-access SQL mixed into business logic | Repository | Domain logic needs testing without a database | Simple script with one query |
| Business code depends on a third-party API shape | Adapter / anti-corruption layer | Vendor may change or differ per integration | Single stable dependency used in one place |
| Complex object needing step-by-step valid construction | Builder | Many optional fields with validation rules | Few fields; use keyword arguments |
| Behavior changes by state, with scattered state flags | State pattern or explicit state machine | 4+ states with transition rules | Two states and a boolean |
| Cross-cutting concern repeated (logging, retry, auth, caching) | Decorator / middleware | 3+ call sites need identical wrapping | One call site |
| Many components notify each other directly | Observer / events | Producers should not know consumers | Single consumer: call it directly |
| One operation with fixed steps, variable details | Template method (prefer composition via injected functions) | Steps are stable and variants differ in a few hooks | Variants share almost nothing |
| Undo, queueing, or audit of operations needed | Command | Operations must be stored, retried, or reversed | Fire-and-forget calls |
| Global mutable state, hidden singletons | Dependency injection (constructor or parameter) | Tests need to substitute it | Truly immutable constants |
| Primitive obsession (strings or ints carrying meaning) | Enum / value object | Same value validated or compared in several places | One-off local value |
| Inconsistent null handling | Null object / Optional with explicit handling | Many callers branch on None | Rare, local case |

Rules of thumb:
- In dynamic languages, prefer functions, closures, and dataclasses before classes and interfaces.
- A pattern that adds more files than it removes branches is probably wrong.
- If you cannot name the smell and the change it prevents, do not recommend the pattern.
