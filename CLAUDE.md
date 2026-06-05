# photoanalyzer — Warhammer 40K Miniature Annotation & Scanner

## Overview
Monorepo annotation tool (desktop) + consumer scanner (PWA). 4 workspaces: desktop frontend (React/TS), backend (Express/TS), consumer PWA, mobile annotator PWA.

**Current direction (2026-06): data-centric rebuild.** The project pivoted from
end-to-end YOLO to a three-tier CV pipeline (class-agnostic detection → faction
classifier → unit retrieval) and is now in active rebuild. The guiding docs are
`HANDOFF.md` (live state) and `BATTLE_SCANNER_PLAN.md`; `STRATEGY.md` holds the
architectural rationale. The Express `backend/` + the legacy end-to-end YOLO11x
model (Phase 0 baseline: 54.7% mAP50 / 66% detection recall) are the **v0** surface
— kept running for the annotator, not the rebuild target.

## Dev Commands

```bash
npm run dev                    # Desktop frontend + backend concurrently
npm run dev:frontend           # Vite dev server on port 5173
npm run dev:backend            # Express server on port 3001
npm run dev:consumer           # Consumer PWA on port 5174
npm run dev:annotator-mobile   # Mobile annotator PWA on port 5175 (--host for LAN)

# Mobile annotator typical workflow:
npm run dev:backend &
npm run dev:annotator-mobile
# Access from iPhone at http://<your-lan-ip>:5175

npm run build                  # Build everything
npm run build:frontend         # → frontend/dist/
npm run build:backend          # → backend/dist/
```

## Key Architecture
- **Command pattern** for undo/redo → `frontend/src/commands/` (AddModelBoxCommand, DeleteModelBoxCommand, ChangeClassCommand, ChangeUnitCommand; shared `BboxCommand` interface)
- **Annotator sub-components** → `frontend/src/components/annotation/` (HeaderProgressCard, StatusFilterRow, SourceFilterRow, FactionProgressGrid, ImageProvenanceCard, PredictionValidationPanel). `AnnotationInterface.tsx` is the parent orchestrator; the file is ~1250L after the May 2026 decomposition.
- **Filter state** → single `useReducer<FilterState, FilterAction>` in `AnnotationInterface.tsx`; status/faction/source/prioritize changes auto-fire `loadNextImage` via a reload-on-filters-change effect.
- **Wire schema marshalling** → `frontend/src/utils/annotationWire.ts` (`apiToBbox` / `bboxToApi`). The backend's `modelBbox: {x,y,w,h}` ↔ canvas's flat `{x,y,w,h}` always round-trips through these helpers.
- **Centralized coordinate transforms** → `frontend/src/utils/coordinates.ts`
- **Two-tier validation**: errors block save, warnings inform
- **YOLO-Pose export** for keypoint annotations (5 or 17 values per line)
- **DINO pipeline** for auto-annotation proposals via backend
- **Active learning** pipeline prioritizes low-confidence images
- **Mobile annotator**: IndexedDB offline storage, native touch events, WiFi sync

## iOS Safari / Mobile PWA — READ BEFORE ANY MOBILE CHANGES
- `crypto.randomUUID()` HTTPS-only — use `generateId()` fallback
- Buttons over canvas don't get touches — place outside canvas container
- Use native touch events, not pointer events (`setPointerCapture` breaks)
- IndexedDB ~1GB limit on iOS — batch imports to 500-1000
- `overscroll-behavior: none` to prevent pull-to-refresh on canvas
- `env(safe-area-inset-bottom)` on bottom toolbars
- Minimum 44px touch targets (Apple HIG)

Full details: `/debug` skill

## Data Paths
- **Images**: `backend/training_data/{faction}/{source}/`
- **Scene annotations** (bbox + faction): `backend/training_data_annotations/` (JSON)
- **YOLO export**: `backend/yolo_dataset/`
- **Confidence scores**: `backend/confidence_scores.json`
- **Model**: `runs/yolo11x_run2_best.pt` (15 classes; see `runs/yolo11x_run2_best.classes.txt` for the pinned class list). The older `runs/yolo11_colab_best.pt` has 8 classes and is no longer loaded by the backend — config points at the `x_run2` model.
- **Logs**: `backend/logs/all.log`, `backend/logs/error.log`
- **Unified labels** (v2 schema): `data/labels.csv` — ground truth for gallery + faction classifier. See `src/photoanalyzer/label/schema.py` for column definitions.
  - **Writers**: Python (`photoanalyzer.label.schema.write_labels_csv`) and the legacy warhammer-analyzer Node service (`warhammer-analyzer/backend/src/services/labelsCsvService.js` — `withCsvLock`). The desktop annotator backend (`backend/`) **does not write `data/labels.csv`** — it writes per-image JSONs to `backend/training_data_annotations/` only.
  - Cross-process lock at `data/labels.csv.lock` (directory, atomic `mkdir`); proper-lockfile auto-recovers stale locks after 10s. The lock matters only when both Python crop-extraction and warhammer-analyzer run concurrently. After a crash the `.lock` dir may need manual `rm -rf`.
- **Gold eval set** (frozen, trusted GT): `data/gold/gold_v2.json` (89 imgs / 283 boxes, all v1 factions ≥40). The measuring stick for the Tier 1 detector — score via `scripts/phaseF/score_gold.py`. The older Phase C `data/scene_benchmark/eval_200.json` uses the legacy (untrusted) annotations as GT — superseded.
- **Canonical taxonomy**: `scripts/data/units.json` — 24 factions (20 codex + 4 Chaos sub-factions split out 2026-04-19: death_guard, thousand_sons, world_eaters, emperors_children). Wrapped by `photoanalyzer.taxonomy`.

## photoanalyzer Python library (`src/photoanalyzer/`)
The CV pipeline is a proper Python package. The active env is `fiftyone_env`
(the old `yolo_env` was retired 2026-05):
```bash
fiftyone_env/bin/pip install -e ".[ml,server,dev]"   # install with all extras
fiftyone_env/bin/pytest tests/                       # run the test suite
```
Modules: `taxonomy` (factions + unit slugs, single source of truth) · `detect/` · `classify/` · `retrieve/` · `label/` (schema + LLM + active learning) · `scrape/` · `eval/` (scene + crop metrics) · `pipeline` · `server` (FastAPI).

**Never hardcode faction or unit strings** in any module; import from `photoanalyzer.taxonomy`.

Scripts under `scripts/` are thin CLI wrappers that import the library.

## STRATEGY.md
`STRATEGY.md` at repo root is the guiding-star architectural plan. **Read it before proposing any modelling change.** It sets the direction: move from end-to-end YOLO to a three-tier pipeline (class-agnostic detection → faction classifier → unit retrieval against a reference gallery). If a change would contradict STRATEGY.md, flag that explicitly and either update the strategy deliberately or reconsider the change.

## Phase F1 (Tier 1 detector bootstrap)
Active work area as of 2026-04-25. Architecture: **SAM 3 detection + SAM 2 mask refinement** (single-detector pipeline; the original 3-detector ensemble was simplified after Phase C bench showed SAM 3 outperforming alternatives 3×). Production runs go through Colab via `bash scripts/phaseF/sync.sh full N`, which uses rclone to ship a bundle to Drive and auto-pulls results.

- **Operations manual**: `scripts/phaseF/README.md` — what to run, when.
- **Implementation context (read this if picking up F1 work)**: `docs/PHASE_F1_HANDOFF.md` — why the architecture is what it is, what was tried and rejected, the gotchas (coord-space round-trips, transformers 5.0 box-format change, CMON symlinks, Drive cache, etc.).

## Skills
`/test` — full test suite (TS + Python). `/export` — YOLO dataset export/validation. `/debug` — troubleshooting, logs, iOS gotchas. `/strategy` — current STRATEGY.md phase + next step. `/bench` — run/review CV model benchmarks. `/ship` — pre-push checklist (typecheck+tests+secret-scan). `/dev` — start dev servers.

## .claude/ environment
See `.claude/README.md` for hooks, agents, skills, and status line. Specialist agents available: `cv-researcher` (literature review), `annotation-reviewer` (audit annotation corpus), `bench-runner` (record benchmark results).

## warhammer-analyzer/ sub-project — DEPRECATED (2026-04-19)
**Do not run or extend this.** The hand-labelling workflow has moved
entirely to the desktop annotator (`backend/` + `frontend/`, ports
3001/5173) which now writes `unit_slug` per-bbox. The
warhammer-analyzer labeller's CSV output (`data/labels.csv`) has been
migrated (see `scripts/migrate_labels_csv_to_annotator.py`) and the
sub-project is kept on disk purely for reference. If you start it up
again, you'll have two parallel labelling surfaces with their own
state — don't.

## Constraints
- NEVER commit files in `images/` or `runs/` to git (training data ~50GB)
- NEVER modify `runs/*.pt` — trained model files are read-only
- NEVER `git add -A` or `git add .` — always stage specific files
