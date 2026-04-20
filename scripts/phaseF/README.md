# Phase F — Tier 1 detector bootstrap

Auto-label the ~37k unlabelled images in `backend/training_data/`, fine-tune
RF-DETR-Medium on the union with the 929 gold annotations, then tighten the
result with one round of human review on the disagreement set. See
`STRATEGY.md` §3.1 for the full rationale; this directory holds the code.

## Sub-phase layout

| Step | Script | Status |
|---|---|---|
| F1 · Auto-label | `autolabel.py` (+ `setup.sh`) | scaffold ready, not yet run |
| F2 · Train RF-DETR v1 | `train_rfdetr_v1.py` | not written |
| F3 · Self-relabel + human review | `find_disagreements.py` | not written |
| F4 · Train RF-DETR v2 + Nano | `train_rfdetr_v2.py` | not written |

## F1 — Auto-label with Grounding DINO

**Why Grounding DINO, not Grounded-SAM-2?** The strategy doc names Grounded-SAM-2
because SAM 2's mask refinement yields slightly tighter boxes. In practice the
accuracy delta for single-class "figurine" detection is ~1–2 mAP and Grounded-SAM-2
requires compiling CUDA Deformable-Attention kernels (frequent install pain).
Grounding DINO via Hugging Face Transformers is a clean `pip install` and
outputs the same boxes. If F1's pseudo-label quality disappoints in F2 training,
upgrading to Grounded-SAM-2 is a one-day swap.

Prompt + thresholds are fixed per the April 2026 reference:

- Prompt: `painted miniature . figurine . tabletop model .` (lowercase,
  dot-separated, trailing period — this is how Grounding DINO expects
  multi-concept prompts)
- box_threshold = 0.25, text_threshold = 0.20
- SAHI tiling for images > 1200 px on the long edge: 640² slices, 0.2 overlap
- Class-agnostic NMS at IoU 0.5
- Drop boxes < 0.5% or > 80% of image area (terrain artefacts and framing mis-fires)

### One-time setup

```bash
scripts/phaseF/setup.sh    # installs transformers, supervision, torchvision into yolo_env
```

Needs a GPU with ~6 GB VRAM for `grounding-dino-base` (larger `grounding-dino-tiny`
works on CPU at ~5× slower).

### Running F1

#### Option A — Colab free tier (recommended; no local GPU required)

`autolabel_colab.ipynb` drives the whole run. The notebook is resumable
via Drive — if Colab disconnects mid-run, reopening it and hitting Run
All picks up where the previous session stopped.

```bash
# 1. Build the bundle (images + annotations + phaseF scripts → ~4 GB tar).
#    Run once per dataset refresh; takes ~5–10 min.
bash scripts/phaseF/prepare_colab_bundle.sh

# 2. Upload two files to the ROOT of your Google Drive (MyDrive):
#      /tmp/photoanalyzer_f1_bundle.tar
#      scripts/phaseF/autolabel_colab.ipynb
#    Drag-and-drop in the Drive web UI.

# 3. In Drive: double-click autolabel_colab.ipynb → "Open with Google Colab".
#    Runtime → Change runtime type → T4 GPU.
#    Runtime → Run all. Walk away (~10h on T4).

# 4. Download /content/drive/MyDrive/f1_outputs.tar from Drive to the repo
#    root, then:
tar -xf f1_outputs.tar       # yields data/pseudo_labels/
```

Resumable across disconnects: the notebook's cell 4 restores the
previous Drive bundle at the start of each session, and cell 6 writes
a fresh bundle at the end. Enable cell 7's periodic checkpoint if you
want Drive updated mid-run.

#### Option B — Local

```bash
# Smoke-test on 20 images first
yolo_env/bin/python scripts/phaseF/autolabel.py --limit 20

# Full run (~5–10h on a 4090, resumable)
yolo_env/bin/python scripts/phaseF/autolabel.py

# Add --shuffle if you want early progress to sample all sources
# (useful when running in batches you'll audit as you go).
yolo_env/bin/python scripts/phaseF/autolabel.py --shuffle --limit 50
```

On CPU the local run is ~18s/image → impractical for the full 36,975
pool (would take ~185 h). Use CPU only for smoke tests and batch QA
against Option A's outputs.

Output layout:

```
data/pseudo_labels/
├── boxes/<imageId>.json         # one file per image — {boxes: [[x,y,w,h], ...], scores: [...]}
├── manifest.json                 # {n_done, n_images_with_boxes, mean_boxes_per_image, ...}
└── errors.log                    # any image-level failures (corrupt files etc.)
```

The runner is **resumable**: images whose `boxes/<imageId>.json` already
exists are skipped. Safe to kill with Ctrl-C and rerun.

### Excluded from labelling

- All 929 already-annotated image IDs (gold labels take precedence)
- Implicitly, the 200 Phase C eval images (subset of the 929)

### When to stop F1 and move to F2

Rough rule of thumb: if ≥ 90% of images have at least one box drawn and mean
boxes-per-image lands in the 1–8 range (not 0, not 50+), the pseudo-labels are
healthy. Check `manifest.json` after a full pass; if not, reconsider prompt /
threshold before feeding F2.
