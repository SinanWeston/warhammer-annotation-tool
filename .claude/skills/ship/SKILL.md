---
name: ship
description: Pre-push checklist. Runs typechecks across all workspaces, the test suite, scans staged diff for secrets, checks that STRATEGY/TODO still parse. Use right before committing a batch of work.
---

Run the pre-ship checklist from `${CLAUDE_PROJECT_DIR}`. Report every step; fail loudly on anything that doesn't pass.

## Steps

1. **Git state**
   - `git status --short | head -20` — show what would be committed.
   - If working tree is clean and nothing staged, say "nothing to ship" and stop.

2. **Typechecks — all four workspaces**
   - `(cd backend && npx tsc --noEmit)` — must be clean
   - `(cd frontend && npx tsc --noEmit)` — must be clean
   - `(cd consumer && npx tsc --noEmit)` — must be clean
   - `(cd annotator-mobile && npx tsc --noEmit)` — must be clean

3. **Tests**
   - `(cd backend && npx vitest run)` — all passing (known-skipped are fine)
   - Frontend component tests are known-broken (jsdom/vitest dep conflict per TODO.md) — skip and say so.

4. **Python syntax check on touched scripts**
   - For each staged `.py` under `scripts/`, run `yolo_env/bin/python3 -m py_compile`.

5. **Secret scan on staged diff**
   - `git diff --cached` piped through a simple pattern scan for: `sk-`, `api_key`, `password=`, `-----BEGIN`, AWS-style IDs. List any matches with file:line.

6. **Doc parse sanity**
   - `awk` over STRATEGY.md Status table — must have the expected column headers and at least six `| N · ` rows.
   - `TODO.md` — warn if it still references deleted files.

## Exit shape

Report each step with ✓ or ✗. If any ✗, do **not** commit; surface the failure and let the user decide. If everything ✓, print a one-line "ready to ship" and remind the user to commit with a descriptive message (not auto-committed).

## Anti-patterns

- Don't commit for the user unless they ask.
- Don't skip steps because they're slow — typechecks and tests are the point.
- If a step times out, treat it as a failure to surface, not a pass.
