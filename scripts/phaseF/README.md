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

```bash
# Smoke-test on 20 images first
yolo_env/bin/python scripts/phaseF/autolabel.py --limit 20

# Full run (~4–8h on a 4090, resumable)
yolo_env/bin/python scripts/phaseF/autolabel.py
```

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
