# Phase F — Tier 1 detector bootstrap

Auto-label the unlabelled images in `backend/training_data/`, fine-tune
RF-DETR-Medium on the union with the gold annotations, then tighten the
result with one round of human review on the disagreement set. See
`STRATEGY.md` §3.1 for the architectural rationale; this directory holds
the code.

## Sub-phase status

| Step | Script | Status |
|---|---|---|
| F1 · Auto-label | `autolabel_ensemble.py` | **shipping pipeline** — see below |
| F1 · Bench | `bench_ensemble.py` | runs on the 200-img Phase C frozen eval |
| F1 · Sync helper | `sync.sh` | replaces all manual file shuffling to/from Drive |
| F2 · Train RF-DETR v1 | `train_rfdetr_v1.py` | not written |
| F3 · Self-relabel + human review | `find_disagreements.py` | not written |
| F4 · Train RF-DETR v2 + Nano | `train_rfdetr_v2.py` | not written |

---

## Architecture (locked 2026-04-25)

**SAM 3 detection + SAM 2 mask refinement.** That's the entire pipeline.

The ensemble plan we initially shipped (SAM 3 + Grounding DINO + OWLv2 visual,
with agreement voting) was simplified after the first Phase C benchmark
showed SAM 3 outperforming the next-best detector by 3× on dense scenes.
Adding weaker votes degraded precision. See `docs/PHASE_F1_HANDOFF.md`
for the measurement detail.

```
Image ─► SAM 3 (text prompt — see HANDOFF §5.1; "miniature", not "painted")
            │
            ▼
       SAM 2 box-prompted segmentation → tight bbox from mask
            │  drop boxes whose refined IoU with the original < 0.10
            ▼
       Pseudo-label JSON (original-resolution coords)
```

Module layout under `src/photoanalyzer/detect/ensemble/`:

| Module | Role |
|---|---|
| `sam3.py` | SAM 3 detector — gated, needs `HUGGINGFACE_HUB_TOKEN` in env |
| `sam2_refine.py` | Mask-based bbox refinement + low-IoU FP filter |
| `voting.py` | Single-detector runner: SAM 3 → (optional) SAM 2 → IoU-dedup SAHI tile-seam duplicates. No voting (DINO/OWLv2 removed 2026-06-05). |
| `../sahi.py` | Shared SAHI tiling + post-process |

Thresholds:
- SAM 3 confidence threshold: see HANDOFF §5.1 (validate 0.30-0.50; 0.25 was the old default)
- NMS IoU: 0.5
- SAHI: images > 1200 px long edge, 640² slices, 0.2 overlap
- SAM 2 refinement: drop candidates whose refined IoU with the original < 0.10

---

## Daily workflow — one command

```bash
bash scripts/phaseF/sync.sh full 50
```

Builds a fresh 50-image stratified Phase C bundle, deletes any stale
outputs from Drive, uploads bundle + notebook, polls Drive every 30s
for results, auto-pulls + extracts + prints the markdown report.

Three minutes after launching this you'll see a "Run All in Colab"
prompt. Open the notebook in Colab (Drive → right-click → Open with
Colaboratory) and click **Runtime → Run all**. That's the only manual
step. Walk away. Come back to a report.

Other entry points:

```bash
bash scripts/phaseF/sync.sh push      # build + upload only
bash scripts/phaseF/sync.sh pull      # download + extract + show report
bash scripts/phaseF/sync.sh status    # what's currently on Drive
bash scripts/phaseF/sync.sh roundtrip # push, wait for Enter, pull (interactive)
```

`full N` is the standard. `push`/`pull` exist for debugging and partial flows.

---

## One-time setup

### 1. Python environment

```bash
fiftyone_env/bin/pip install -e '.[ml]'
```

This pulls `transformers ≥ 4.49` (needed for SAM 3 / SAM 2)
and the rest of the ML extras.

### 2. HuggingFace gated-model access

SAM 3 is gated. You need to:
- Accept the licence at https://huggingface.co/facebook/sam3 (Meta reviews
  the request — typically a few hours).
- Generate a Read-scope token at https://huggingface.co/settings/tokens.
- Add to `.env` (already gitignored):
  ```
  HUGGINGFACE_HUB_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  ```

The token also has to be set as a Colab Secret named
`HUGGINGFACE_HUB_TOKEN` for the notebook to download SAM 3 there
(left sidebar key icon → "+ Add new secret" → toggle "Notebook access" on).

SAM 2 (`facebook/sam2-hiera-large`) is **not** gated — the same token
works but no licence acceptance is needed.

### 3. Google Drive sync (rclone)

```bash
fiftyone_env/bin/rclone config create gdrive drive scope=drive
```

Walks you through an OAuth flow (browser opens, sign in, Allow). The
remote is named `gdrive` and persists in `~/.config/rclone/rclone.conf`
indefinitely. Re-do this only if you revoke the OAuth grant.

---

## Bundle internals — what `sync.sh push` ships

The Colab bundle (`~/Downloads/photoanalyzer_f1_bundle.tar`, ~20 MB for
50 images) contains:

| Path inside tar | Why |
|---|---|
| `backend/training_data/<faction>/<source>/*.jpg` | The actual image files for this run, downscaled to ≤ 1333 px long-edge |
| `backend/training_data_annotations/*.json` | Gold annotations (used by `bench_ensemble.py` as ground truth) |
| `data/scene_benchmark/eval_200.json` | Phase C frozen-eval manifest |
| `data/pseudo_labels/original_dims.json` | Coord rescale manifest — every image's pre-downscale (orig_w, orig_h). The ensemble auto-rescales output coords back to originals. |
| `src/photoanalyzer/` | Library — imported by the bench/autolabel scripts |
| `scripts/phaseF/` | The Python drivers + this README |
| `PHASE_C_BENCH_MODE` (when `--phase-c`) | Empty marker file — tells cell 13 to run `bench_ensemble.py` instead of `autolabel_ensemble.py` |

The notebook's cell 13 routes between **bench mode** (when the marker is
present) and **autolabel mode** (no marker) based on this file.

---

## Bench mode vs autolabel mode

`prepare_colab_bundle.py` has two distinct flows:

| Bundle type | Flag | Contents | Notebook does |
|---|---|---|---|
| **Bench bundle** | `--phase-c [--phase-c-limit N]` | The 200 Phase C eval images (or a stratified subset) | Run `bench_ensemble.py`, score against gold annotations, emit a markdown report |
| **Autolabel bundle** | `--sample N` or full | N unlabelled images from `backend/training_data/` | Run `autolabel_ensemble.py`, emit pseudo-label JSONs |

The user-facing `sync.sh full` always uses the bench flow because that's
the loop you iterate on. For the actual production 17k run we'll switch
to an autolabel bundle (separate command — see "Full 17k production run"
below).

---

## Full 17k production run

Once benchmarks are happy:

```bash
# Bigger bundle. ~5 GB after downscaling. Allow 20–30 GB GPU-hours on Colab.
fiftyone_env/bin/python scripts/phaseF/prepare_colab_bundle.py
bash scripts/phaseF/sync.sh push
# Now click Run All in Colab — this run takes ~10 hrs on T4 (Colab will
# disconnect; the notebook is resumable across sessions via the
# f1_outputs.tar checkpoint).
bash scripts/phaseF/sync.sh pull
# After enough sessions to cover all 17k, import to the annotator:
fiftyone_env/bin/python scripts/phaseF/import_pseudo_to_annotator.py
```

Across multiple Colab sessions the notebook's cell 11 restores prior
outputs from Drive on each new session, so the autolabel runner skips
images already labelled. A periodic checkpoint cell (cell 17) can be
uncommented to mirror outputs to Drive every 30 minutes for safety.

---

## Output layout

After `sync.sh pull` extracts `f1_outputs.tar` into the repo:

```
data/pseudo_labels/
├── boxes/<imageId>.json          # per-image pseudo-labels (SAM 3 schema)
├── manifest.json                 # {n_images_processed, mode, ...}
├── original_dims.json            # round-trip from the bundle
└── errors.log                    # per-image failures from the runner

docs/benchmarks/<date>-phaseF1-ensemble.md   # bench report (only in bench mode)
```

Per-image pseudo JSON (SAM 3 schema):

```json
{
  "imageId": "...",
  "imagePath": "backend/training_data/<faction>/<source>/<file>",
  "width": 2592, "height": 1944,
  "detectors_used": ["sam3"],
  "mode": "sam3",
  "boxes": [
    {
      "xywh": [x, y, w, h],
      "score": 0.87,
      "supporters": ["sam3"],
      "refinement_iou": 0.92,
      "tier": "auto"
    },
    ...
  ]
}
```

---

## Edge cases & recovery

- **Watcher polling forever**: cell 13 errored. Open Colab tab, find the
  red cell, paste the traceback into chat (Claude can patch + re-push
  without you re-uploading manually).
- **Wrong notebook served by Drive**: Drive caches old versions for ~30s
  after upload. `sync.sh push` waits for the upload to complete but
  Drive's rendering may lag. Force-refresh the Drive tab (Ctrl-Shift-R).
- **`sync.sh` says rclone remote `gdrive` not configured**: re-run the
  OAuth step from "One-time setup".
- **Coord-space drift**: every pseudo JSON's `width`/`height` should
  match the actual image file's dimensions. Mismatch ⇒ bug in the
  rescale path. `import_pseudo_to_annotator.py` rescales as a safety
  net before writing into the annotator.
- **Out of free Colab GPU hours**: paid Pro is ~$10/month; Modal is
  the cleanest paid alternative if you want to skip Drive entirely
  (see `docs/PHASE_F1_HANDOFF.md`).

---

## Excluded from labelling

- All currently-annotated image IDs (gold labels take precedence).
- Phase C eval images (subset of the gold corpus, never trained on).

The runner skips these via `load_annotated_ids()` filtering on
`pseudoLabelled != true`.
