# Agent pack: Ethiopian Bank Exchange Rate Intelligence System

1. Copy everything in this folder into the root of your repository (CLAUDE.md goes in the root).
2. Add the two files that are not included, because they are yours:
   - docs/handoff/design-handoff-2026-10-09.md  (your original handoff document)
   - docs/register/source-register.json         (your source register)
   Then delete the two PLACE_*_HERE.md notes.
3. Start the local agent in the repository (plan mode is not needed; the pack makes it autonomous).
4. Paste the contents of KICKOFF_PROMPT.md as the first message (everything below its title line).
5. Read docs/plan/STATUS.md whenever you want the agent's record of what is done, verified, and open.

Contents
- CLAUDE.md                                standing spec, reporting rules, autonomy rules
- KICKOFF_PROMPT.md                        first message for the agent
- docs/decisions/defaults.md               decisions already made for the agent
- docs/plan/execution-order.md             ordered work, per-source procedure, readiness checklist
- docs/plan/STATUS.md                      agent's running status record
- docs/register/waves.md                   register summary and rollout waves
- docs/review/gap-review.md                gaps and added acceptance tests
- docs/evidence/addis/                     2026-10-10 capture and notes (all TO VERIFY)
- docs/mapping/                            agent writes per-source mappings here
