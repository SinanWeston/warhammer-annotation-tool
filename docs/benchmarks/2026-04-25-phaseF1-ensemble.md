# Phase F1 ensemble benchmark — 2026-04-25

Eval set: `data/scene_benchmark/eval_200.json` (48 images, 318 GT boxes).

## Aggregate (IoU 0.5)

| Detector | mAP@50 | Recall (0.3/0.5/0.7) | Precision | Pred / GT | Time (s) |
|---|---|---|---|---|---|
| sam3 | 0.322 | 0.59/0.53/0.43 | 0.26 | 648 / 318 | 373.6 |
| sam3_refined | 0.000 | 0.00/0.00/0.00 | 0.00 | 0 / 318 | 419.5 |

## Per-density bucket (IoU 0.5)

| Detector | single R/P | sparse R/P | medium R/P | crowded R/P |
|---|---|---|---|---|
| sam3 | 0.40/0.05 | 0.45/0.19 | 0.29/0.10 | 0.63/0.51 |
| sam3_refined | 0.00/0.00 | 0.00/0.00 | 0.00/0.00 | 0.00/0.00 |
