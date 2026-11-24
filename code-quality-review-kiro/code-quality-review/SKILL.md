---
name: code-quality-review
description: Review a codebase for clean code, SOLID, design-pattern fit, correctness, security, and testability, then produce an evidence-based prioritized report, a refactor plan, or implement one approved work package. Use this skill whenever the user asks to review, audit, assess, or grade code quality, check best practices or SOLID principles, find code smells or technical debt, judge whether design patterns fit, assess test quality, or plan a refactor, even if they do not say "skill" or "review". Works for any language or project. Read-only by default; never edits code unless explicitly told to implement.
---

# Code Quality Review

## Modes
- **Review** (default): analyze and report. Do not create, edit, or delete any file.
- **Plan**: turn an existing review into ordered, independently shippable work packages.
- **Implement**: only when explicitly asked, and only one approved work package at a time.

If the mode is unclear, use Review.

## Core rules
1. **Evidence over opinion.** Every finding cites `path:lines`, names a concrete failure scenario, and was verified by tracing real call sites. No citation, no finding.
2. **Problems before patterns.** Recommend a design pattern, abstraction, or new layer only when a verified smell requires it. Check `references/smell-to-pattern.md` and state why the simpler option (a function, a dataclass, a parameter) is not enough.
3. **Principles conflict. Decide, don't recite.** When two principles pull apart (DRY vs coupling, SRP vs locality, abstraction vs YAGNI), state the trade-off and pick the option that fits this codebase's size and rate of change.
4. **Respect the language's idioms.** Do not flag idiomatic style of the ecosystem as a violation. Do not port patterns from other languages (no Java-style factories in Python, no inheritance hierarchies where functions suffice).
5. **Calibrate to context.** A 300-line script and a multi-team service get different standards. State which you assumed.
6. **Fewer, higher-value findings.** Prefer 8 verified findings that matter over 40 nitpicks. Group repeated instances into one finding with a count.
7. **Mark uncertainty.** Use "Needs confirmation" and state what would settle it. Never guess.
8. **Review the code, not the author.** No commentary about the author or their experience.

## Procedure
1. **Orient.** Detect language, framework, build and test commands. Read `REVIEW_CONTEXT.md` at the repo root if present, then the README, architecture docs, and any steering files in `.kiro/steering/`. If `REVIEW_CONTEXT.md` is missing, say so and list the assumptions you are making about intentional design choices.
2. **Gather objective signals first.** Run what already exists and note the results: tests, coverage, linter, type checker, complexity or duplication tools, dependency audit. If a tool is missing, say so; do not install anything silently. Treat tool output as leads to verify, not as findings.
3. **Map.** Produce modules, responsibilities, and dependency direction (max 15 lines). Flag any dependency pointing the wrong way (domain depending on infrastructure).
4. **Slice large repos.** If the codebase is too large to verify properly in one pass, review one layer or module at a time and say which slice you covered. Do not skim the whole repo and report impressions.
5. **Evaluate by lens, in this priority order.** Read `references/principles.md` for the criteria of each lens.
   1. Correctness and data integrity (races, transactions, invariants, silent failure, determinism)
   2. Architecture and boundaries (layering, coupling, cohesion, dependency direction)
   3. Design principles (SOLID, composition over inheritance, Law of Demeter, separation of concerns)
   4. Clean code (naming, function size, duplicated knowledge, error handling, dead code)
   5. Testability and tests (hidden I/O, clocks, randomness, global state; test quality and gaps)
   6. Security and operations (injection, secrets, authorization, logging, observability, configuration)
6. **Verify.** For each candidate finding, find the callers, the tests, and the data flow. Drop any finding that does not survive.
7. **Pattern check.** For each verified smell, consult `references/smell-to-pattern.md`. Recommend a pattern only if its "use when" matches and no "avoid when" applies.
8. **Rank.** Severity is impact times likelihood, not rule count:
   - **Critical**: data loss, corruption, security hole, or wrong results in normal use
   - **High**: breaks under realistic concurrency, load, or input; blocks safe change
   - **Medium**: raises cost of change or defect risk; fix when touching the area
   - **Low**: readability or consistency

## Output format (Review mode)
1. **Context assumed**: language, size, maturity, tools run and their results, slice covered
2. **Architecture map**
3. **Strengths**: max 5, specific
4. **Findings** by severity, each with:
   - Title
   - Location: `path:lines`
   - Problem and failure scenario
   - Principle or rule involved
   - Fix: the smallest change that resolves it (sketch or description)
   - Pattern (only if justified): name, and why the simpler option fails
   - Effort: S / M / L
5. **Refactoring roadmap**: ordered safest and highest value first; tests that pin current behavior come first; mark steps that change behavior or stored data
6. **Test gaps**: the 5 most valuable missing tests
7. **Questions for the owner**: decisions only they can make

For a worked example of a finding at the right depth, read `assets/example-finding.md`.

## Plan mode
Write the plan to `docs/refactor-plan.md`. Before planning, re-verify every finding against the current code and drop any that no longer hold. Group findings into work packages, each one reviewable change that can ship on its own.

Order packages: (1) tests that pin current behavior, (2) data-integrity fixes, (3) changes that alter stored or computed values, isolated with a migration or backfill and rollback strategy, (4) pure refactors.

Each package states: findings fixed, files touched, behavior change (none / internal only / affects stored data), data safety, migration and rollback if any, verification and pass condition, risk, effort, dependencies. List decisions only the owner can make under "Decisions needed" with a recommended default and the impact if wrong. Plan mode creates only the plan file.

## Implement mode
Only on explicit request, for one named work package:
1. Confirm its dependencies are already merged; if not, stop and report.
2. Re-verify the problem in the current code; if it no longer exists, stop and report.
3. Work on a branch named `refactor/<package-id>-<short-name>`.
4. Write the verification tests first and confirm they fail for the expected reason.
5. Make the smallest change that fixes the problem; touch only the files the package lists.
6. Run the full test suite; fix only failures caused by the change.
7. Review your own diff and remove anything the package did not require.
8. Commit once, then report: files changed, test results, deviations from the plan, risks noticed but not acted on, and the commands to verify and roll back.

Never run migrations or backfills against any database except a local or test one. Never push, merge, or force anything. If the plan is ambiguous or wrong, stop and report instead of improvising.

## Never
- Edit files in Review or Plan mode (Plan mode may only write the plan file).
- Report a style preference as a defect.
- Recommend a rewrite where a small targeted change fixes the problem.
- Pad the report to look thorough.
