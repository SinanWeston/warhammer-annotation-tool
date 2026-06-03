# Mothball state — 2026-05-14

Project is paused. Source code, training images, annotations, and the production model checkpoint are intact. Build artifacts, virtualenvs, and derivable retrieval data were removed to reclaim disk space.

## Resume in one shot

```bash
cd /home/sinan/Active/Projects/photoanalyzer

# 1. Node deps (all workspaces)
npm install

# 2. Python venv + photoanalyzer library
python3 -m venv yolo_env
yolo_env/bin/pip install -e ".[ml,server,dev]"

# 3. (Optional) Rebuild Phase 3 retrieval artifacts
yolo_env/bin/python scripts/phase3/extract_from_corpus.py
yolo_env/bin/python scripts/phase3/build_gallery.py
yolo_env/bin/python scripts/phase3/embed_gallery.py
```

## What was removed and why

### Build artifacts / environments (regenerable, big)
| Path | Size | Restore |
|---|---|---|
| `yolo_env/` | 8.1 G | `python3 -m venv yolo_env && yolo_env/bin/pip install -e ".[ml,server,dev]"` |
| `node_modules/` (root + all 5 workspaces) | ~1.1 G | `npm install` at repo root |
| `**/__pycache__/`, `**/dist/`, `**/.vite/`, `**/.pytest_cache/`, `**/.mypy_cache/` | small | Rebuilt on next run |

### Derivable Phase 1/2/3 retrieval data
| Path | Size | Restore |
|---|---|---|
| `scripts/phase3/gallery/` | 1.6 G | `scripts/phase3/build_gallery.py` |
| `scripts/phase3/crops/` + `crops_index.jsonl` | 140 M | `scripts/phase3/extract_from_corpus.py` |
| `scripts/phase3/gallery_embeddings.npz` | 14 M | `scripts/phase3/embed_gallery.py` |
| `scripts/phase2/gallery/` + `crops/` + embeddings + crops_index | 20 M | Same scripts under `scripts/phase2/` |
| `scripts/phase1/gallery/` + `crops/` + embeddings + crops_index | 5 M | Same scripts under `scripts/phase1/` |

### Genuinely obsolete (do not restore)
| Path | Size | Why |
|---|---|---|
| `runs/warhammer_yolo11x_r2/weights/epoch*.pt` | 3.7 G | Intermediate training checkpoints. `best.pt` + `last.pt` retained in same dir; `best.pt` also copied to `runs/yolo11x_run2_best.pt`. |
| `runs/yolo11_colab_best.pt` | 49 M | Superseded by `yolo11x_run2_best.pt` per CLAUDE.md ("no longer loaded by the backend"). |
| `backend/backend/yolo_dataset/` | 247 M | Accidental nested duplicate of `backend/yolo_dataset/`. |
| `backend/yolo_dataset (2)/` | 51 M | File-manager copy artifact. |
| `backend/training_data_annotations.bak-20260418T141405Z/` | 5.5 M | Stale annotation backup; live corpus in `backend/training_data_annotations/`. |
| `har_files/` | 176 M | Browser HAR captures used only as discovery seeds for scrapers in `scripts/warhammer_com/`, `scripts/cmon/`. Scrapes already ran. Re-record from the browser dev tools if scraping resumes. |
| `backend/logs/all.log` (Feb 22) + `all1.log` (Apr 22) | 10 M | Rotated logs superseded by `all2.log`. |

## What was NOT touched (load-bearing data, ~37 GB)

These are irreplaceable or non-trivially expensive to regenerate. Don't delete on resume.

- `backend/training_data/` (16 G) — the labelled training corpus across 35+ faction/source dirs.
- `training_data_v2/` (12 G) — older training corpus. Note: ~2000 files here are **not** in `backend/training_data` (the sync was partial). Keep until reconciled.
- `scripts/cmon/` (2.6 G), `scripts/warhammer_com/` (2.1 G), `scripts/warhammer_community/` (764 M) — three scrape outputs with **zero filename overlap**; all unique.
- `runs/warhammer_yolo11x_r2/weights/best.pt` + `last.pt` (220 M), `runs/yolo11x_run2_best.pt` (110 M) — production YOLO model.
- `backend/training_data_annotations/` (6.5 M, 1451 JSONs) — scene annotation ground truth.
- `backend/training_data_candidates/` (418 M), `backend/training_data_proposals/` (42 M) — candidate sets and DINO/YOLO bbox proposals consumed by the backend.
- `data/labels.csv` — unified label schema (v2). Ground truth for gallery + faction classifier.
- `models/`, `reference_gallery/`, all source code, `STRATEGY.md`, `TODO.md`, `docs/`, `.git/`.

## Where to pick up

Per `STRATEGY.md` at mothball time:
- Phase 0 (Baseline reality-check) — ✅ Complete
- Phase 1 (Prototype Tier 1+3) — ✅ Complete
- Phase 2 (Tier 2 + gallery expand) — ✅ Complete (unscoped path)
- Phase 3a (Gallery expansion from corpus) — 🟠 Partial pass; next is Phase 3a.1 depth-focused labelling (worklist at `docs/depth_focus_worklist.md`)
- Phase B (Labelling infrastructure + depth push) — most recent active work; reference walkthrough annotator mode landed in commit `6177829`.

Branch on mothball: `main`, 0 ahead, 13 dirty files (uncommitted Phase 3a.1 work).
