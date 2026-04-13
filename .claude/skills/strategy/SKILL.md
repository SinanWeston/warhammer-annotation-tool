---
name: strategy
description: Print the current STRATEGY.md phase status table and the next concrete step. Use to re-orient at session start or when a decision needs checking against the guiding direction.
disable-model-invocation: false
---

Print the project's strategy state to the user.

1. Read `STRATEGY.md`.
2. Extract and show:
   - The **Status (living)** table (section near the end).
   - The **first phase** whose status is not "Not started" or "Deferred" — this is the active phase. Print its full section (roadmap §7.X) and its exit criteria.
3. If every phase is "Not started" (we haven't begun), print Phase 0's section as the active one.
4. Point to `docs/STRATEGY_SOURCES.md` for the bibliography.

Do not modify `STRATEGY.md` — this is a read-only status check. If the user wants to advance a phase, tell them to say so explicitly and update the table together.
