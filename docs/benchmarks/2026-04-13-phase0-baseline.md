# Phase 0 baseline — YOLO11x Run 2

**Date**: 2026-04-13
**Phase**: 0 (baseline reality-check)
**Model**: `/home/sinan/Active/Projects/photoanalyzer/runs/yolo11x_run2_best.pt`
**Eval set**: `/home/sinan/Active/Projects/photoanalyzer/backend/yolo_dataset/images/val` (119 images)
**Confidence threshold**: 0.25
**IoU match threshold**: 0.5

## Headline metrics

| Metric | Value | Notes |
|---|---|---|
| Detection recall @ IoU 0.5 | **66.0%** | Fraction of GT boxes with a matching prediction |
| Detection precision @ IoU 0.5 | **76.3%** | Fraction of predictions that match a GT box |
| Faction top-1 on matched | **63.8%** | Given a true-positive detection, is the class right? |
| mAP50 (ultralytics) | **54.7%** | Ultralytics-reported (apples-to-apples with SPEC.md) |
| mAP50-95 (ultralytics) | 39.1% | Stricter IoU average |
| Unit top-1 | N/A | Current model is faction-only; unit labels not in annotations |
| Unit top-3 | N/A | Same reason |
| "Unknown" recall | N/A | Softmax forces a class — structural limitation |

## Totals
- Ground-truth boxes: 561
- Predicted boxes: 485
- True positives (matched GT at IoU ≥ 0.5): 370
- Correct class on matched: 236

## Per-class breakdown

| Class | GT | Predicted | TP (any class) | Correct class | Det recall | Class precision | Faction top-1 on matched |
|---|---|---|---|---|---|---|---|
| tyranids | 145 | 132 | 79 | 79 | 54.5% | 59.8% | 100.0% |
| necrons | 111 | 31 | 40 | 25 | 36.0% | 80.6% | 62.5% |
| eldar | 73 | 52 | 54 | 32 | 74.0% | 61.5% | 59.3% |
| adeptus_mechanicus | 36 | 43 | 28 | 25 | 77.8% | 58.1% | 89.3% |
| grey_knights | 32 | 27 | 32 | 19 | 100.0% | 70.4% | 59.4% |
| genestealer_cult | 30 | 7 | 15 | 1 | 50.0% | 14.3% | 6.7% |
| chaos_space_marines | 28 | 38 | 25 | 2 | 89.3% | 5.3% | 8.0% |
| orks | 27 | 28 | 22 | 11 | 81.5% | 39.3% | 50.0% |
| custodes | 22 | 26 | 21 | 10 | 95.5% | 38.5% | 47.6% |
| imperial_guard | 18 | 21 | 16 | 11 | 88.9% | 52.4% | 68.8% |
| death_guard | 13 | 41 | 13 | 1 | 100.0% | 2.4% | 7.7% |
| thousand_sons | 13 | 15 | 13 | 9 | 100.0% | 60.0% | 69.2% |
| space_marines | 7 | 10 | 6 | 6 | 85.7% | 60.0% | 100.0% |
| chaos_knights | 6 | 14 | 6 | 5 | 100.0% | 35.7% | 83.3% |
| deathwatch | 0 | 0 | 0 | 0 | 0.0% | 0.0% | 0.0% |

## Qualitative notes

- **Detection vs classification split is the headline finding.** The model locates miniatures far more reliably (~66% recall, ~76% precision at IoU 0.5) than it classifies them (~64% top-1 on matched). This is exactly the gap STRATEGY.md's three-tier architecture is designed to exploit: keep the detection stage, replace the classifier with a retrieval head.
- **Unit-level is N/A by construction.** Annotations are faction-only; no unit labels exist in the corpus. Tier 3 retrieval closes this without requiring unit-level annotations — it matches crop embeddings against a reference gallery.
- **The "39.9% mAP50" number in SPEC.md / OVERVIEW.md is actually mAP50-95.** Re-measured on the same val split: mAP50 = 54.7%, mAP50-95 = 39.1%. SPEC.md should be corrected.
- **Class-wise classification is highly bimodal.** Some classes are nearly solved at faction-top-1 (tyranids 100%, adeptus_mechanicus 89%, space_marines 100% but on only 7 TP), others are catastrophic (chaos_space_marines 8%, death_guard 8%, genestealer_cult 7%). The bottom three suggest the model confuses these with visually-similar loyalist/imperial classes. Embedding retrieval should improve these more than aggregate mAP50 implies.
- **`deathwatch` class sees zero GT in the val split** — the class is effectively untested. Same story for other under-sampled classes in the long tail.

## Reproduction

```bash
yolo_env/bin/python3 scripts/phase0_baseline.py \
    --model /home/sinan/Active/Projects/photoanalyzer/runs/yolo11x_run2_best.pt \
    --conf 0.25
```

See [../../STRATEGY.md](../../STRATEGY.md) §8 for the canonical KPI set and phase exit criteria.
