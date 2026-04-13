---
name: dev
description: Start development servers for the photoanalyzer workspaces. Use instead of remembering ports and flags. Accepts a workspace hint to start just that one.
argument-hint: "[frontend | backend | consumer | mobile | all]"
---

Start development servers for the Warhammer 40K monorepo.

## Ports and commands (from package.json at root)

| Workspace | Port | Command |
|---|---|---|
| Desktop annotator (frontend + backend concurrent) | 5173 + 3001 | `npm run dev` |
| Backend only | 3001 | `npm run dev:backend` |
| Frontend only | 5173 | `npm run dev:frontend` |
| Consumer PWA | 5174 | `npm run dev:consumer` |
| Mobile annotator PWA | 5175 (LAN) | `npm run dev:annotator-mobile` |

## How to choose

- `/dev all` or no arg → full stack (`npm run dev`) in the foreground-friendly way.
- `/dev frontend` → frontend dev server only.
- `/dev backend` → backend dev server only.
- `/dev consumer` → consumer PWA only.
- `/dev mobile` → mobile annotator PWA only. **Reminder**: access from iPhone at `http://<lan-ip>:5175` — the mobile annotator needs LAN exposure (`--host` flag is in the workspace config).

## Mobile annotator tip

To sync from the iPhone, the backend must also be running. Tell the user to run `/dev backend` in one terminal and `/dev mobile` in another.

## Anti-patterns

- Don't run in the foreground when the user is mid-task — use `run_in_background: true` on the Bash call and note the log path.
- Don't try to start two things on the same port. Check `lsof -i :<port>` first if a process is already bound.

$ARGUMENTS
