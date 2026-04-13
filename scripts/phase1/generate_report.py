#!/usr/bin/env python3
"""
Phase 1 — generate the benchmark markdown report from results/*.json.

Consumes:
    scripts/phase1/results/retrieval_summary.json
    scripts/phase1/results/detection_summary.json  (optional)

Emits:
    docs/benchmarks/YYYY-MM-DD-phase1-prototype.md  (first draft)
    - Headline metrics table with Wilson 95% CIs on all percentages
    - Comparison row vs Phase 0 YOLO baseline
    - Per-faction block split (YOLO-easy vs YOLO-problem)
    - Named failure examples (3 worst queries)
    - Placeholder "Qualitative notes" for human edit on Day 3

Usage:
    yolo_env/bin/python3 scripts/phase1/generate_report.py
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE1 = REPO_ROOT / "scripts" / "phase1"
RESULTS_DIR = PHASE1 / "results"
BENCHMARKS_DIR = REPO_ROOT / "docs" / "benchmarks"

YOLO_EASY = {"tyranids", "space_marines"}
YOLO_PROBLEM = {"chaos_space_marines", "death_guard", "genestealer_cult"}

# From Phase 0 baseline for side-by-side comparison:
PHASE0_BASELINE = {
    "detection_recall": 0.660,
    "detection_precision": 0.763,
    "mAP50": 0.547,
    "mAP50_95": 0.391,
    "faction_top1": 0.638,  # on matched boxes, 15 classes
}


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% confidence interval for a proportion. Returns (lo, hi) in [0, 1]."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def fmt_pct_ci(value: float, successes: int, n: int) -> str:
    lo, hi = wilson_ci(successes, n)
    return f"{value:.1%} ({lo:.1%}–{hi:.1%})"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=None, help="Override output path")
    p.add_argument("--date", default=None, help="Override date in filename (YYYY-MM-DD)")
    return p.parse_args()


def main():
    args = parse_args()

    retrieval_path = RESULTS_DIR / "retrieval_summary.json"
    detection_path = RESULTS_DIR / "detection_summary.json"

    if not retrieval_path.exists():
        raise SystemExit(f"Missing {retrieval_path}. Run eval_retrieval.py first.")

    retrieval = json.loads(retrieval_path.read_text())
    detection = json.loads(detection_path.read_text()) if detection_path.exists() else None

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    out_path = Path(args.out) if args.out else BENCHMARKS_DIR / f"{date_str}-phase1-prototype.md"

    n_q = retrieval["num_queries"]
    per_q = retrieval["per_query"]
    m = retrieval["metrics"]

    # Recompute successes so we can give Wilson CIs.
    n_top1 = sum(1 for q in per_q if q["is_top1"])
    n_top3 = sum(1 for q in per_q if q["is_top3"])
    n_top5 = sum(1 for q in per_q if q["is_top5"])
    n_fac1 = sum(1 for q in per_q if q["ranked_units"] and q["ranked_units"][0]["faction"] == q["true_faction"])

    # Per-faction split.
    by_faction: dict[str, list[dict]] = defaultdict(list)
    for q in per_q:
        by_faction[q["true_faction"]].append(q)

    lines = []
    lines.append(f"# Phase 1 prototype — retrieval pipeline (OWLv2 + DINOv3)")
    lines.append("")
    lines.append(f"**Date**: {date_str}")
    lines.append(f"**Phase**: 1 (Prototype Tier 1 + Tier 3, no training)")
    lines.append(f"**Retrieval model**: `{retrieval['model_id']}`")
    if detection:
        lines.append(f"**Detector**: `{detection['model_id']}`")
    lines.append(f"**Gallery**: {retrieval['num_gallery_images']} images across {retrieval['num_gallery_units']} unique units")
    lines.append(f"**Queries**: {n_q}")
    lines.append("")
    lines.append("## Headline metrics (Wilson 95% CI)")
    lines.append("")
    lines.append("| Metric | Value (95% CI) | Notes |")
    lines.append("|---|---|---|")
    lines.append(f"| Unit top-1 | {fmt_pct_ci(m['top1'], n_top1, n_q)} | Cosine k-NN, max-sim aggregation |")
    lines.append(f"| Unit top-3 | {fmt_pct_ci(m['top3'], n_top3, n_q)} | |")
    lines.append(f"| Unit top-5 | {fmt_pct_ci(m['top5'], n_top5, n_q)} | Exit criterion: ≥ 50% |")
    lines.append(f"| Unit MRR | {m['mrr']:.3f} | Mean reciprocal rank |")
    lines.append(f"| Faction top-1 (via retrieval) | {fmt_pct_ci(m['faction_top1'], n_fac1, n_q)} | Faction of top-1 unit |")
    if detection:
        d_m = detection["metrics"]
        d_tot = detection["totals"]
        d_recall_n = d_tot["ground_truth_boxes"]
        d_recall_k = d_tot["true_positives"]
        d_prec_n = d_tot["predicted_boxes"]
        lines.append(f"| Detection recall @ IoU 0.5 | {fmt_pct_ci(d_m['detection_recall_iou50'], d_recall_k, d_recall_n)} | OWLv2 vs YOLO {PHASE0_BASELINE['detection_recall']:.1%} baseline. Exit criterion: ≥ 66%. |")
        lines.append(f"| Detection precision @ IoU 0.5 | {fmt_pct_ci(d_m['detection_precision_iou50'], d_recall_k, d_prec_n)} | OWLv2 vs YOLO {PHASE0_BASELINE['detection_precision']:.1%} baseline. |")
    if m.get("unknown_threshold_sim_at_fpr10pct") is not None:
        lines.append(f"| \"Unknown\" threshold | {m['unknown_threshold_sim_at_fpr10pct']:.3f} | Cosine sim at FPR 10% — Phase 4 calibration input |")
    lines.append("")
    lines.append("## Comparison vs Phase 0 baseline")
    lines.append("")
    lines.append("| Metric | Phase 0 YOLO | Phase 1 retrieval | Delta |")
    lines.append("|---|---|---|---|")
    lines.append(f"| Faction top-1 (aggregate) | {PHASE0_BASELINE['faction_top1']:.1%} (15-class softmax on matched) | {m['faction_top1']:.1%} (via retrieval) | {(m['faction_top1'] - PHASE0_BASELINE['faction_top1']) * 100:+.1f} pp |")
    if detection:
        lines.append(f"| Detection recall @ 0.5 | {PHASE0_BASELINE['detection_recall']:.1%} (YOLO) | {detection['metrics']['detection_recall_iou50']:.1%} (OWLv2) | {(detection['metrics']['detection_recall_iou50'] - PHASE0_BASELINE['detection_recall']) * 100:+.1f} pp |")
        lines.append(f"| Detection precision @ 0.5 | {PHASE0_BASELINE['detection_precision']:.1%} (YOLO) | {detection['metrics']['detection_precision_iou50']:.1%} (OWLv2) | {(detection['metrics']['detection_precision_iou50'] - PHASE0_BASELINE['detection_precision']) * 100:+.1f} pp |")
    lines.append("")
    lines.append("## Per-faction breakdown")
    lines.append("")
    for block_name, factions in [("YOLO-easy (Phase 0 ≥ 90% faction top-1)", YOLO_EASY),
                                  ("YOLO-problem (Phase 0 ≤ 15% faction top-1)", YOLO_PROBLEM)]:
        lines.append(f"### {block_name}")
        lines.append("")
        lines.append("| Faction | Queries | Top-1 | Top-3 | Top-5 | MRR |")
        lines.append("|---|---|---|---|---|---|")
        for fac in sorted(factions):
            qs = by_faction.get(fac, [])
            if not qs:
                lines.append(f"| {fac} | 0 | — | — | — | — |")
                continue
            n = len(qs)
            t1 = sum(1 for q in qs if q["is_top1"])
            t3 = sum(1 for q in qs if q["is_top3"])
            t5 = sum(1 for q in qs if q["is_top5"])
            mrr = sum(q["reciprocal_rank"] for q in qs) / n
            lines.append(f"| {fac} | {n} | {t1}/{n} = {t1/n:.0%} | {t3}/{n} = {t3/n:.0%} | {t5}/{n} = {t5/n:.0%} | {mrr:.3f} |")
        lines.append("")

    # Named failures — 3 worst by reciprocal rank (0 = true unit not in top-5).
    failures = sorted(per_q, key=lambda q: (q["reciprocal_rank"], q["true_unit"]))[:3]
    lines.append("## Named failure examples")
    lines.append("")
    for q in failures:
        lines.append(f"**`{q['query_path']}`** — true unit: `{q['true_faction']}/{q['true_unit']}`, true rank: {q['true_rank'] or 'not in top-5'}")
        for i, r in enumerate(q["ranked_units"], 1):
            lines.append(f"  {i}. `{r['faction']}/{r['unit']}` — sim {r['sim']:.3f}")
        lines.append("")

    lines.append("## Qualitative notes (fill by hand on Day 3)")
    lines.append("")
    lines.append("- [ ] Are correct matches at high sim (≥0.7) while wrong are at ≤0.5? Flat distribution is a red flag.")
    lines.append("- [ ] Failure mode bucket counts: (a) unit not in gallery, (b) paint-scheme cross-match, (c) semantically similar but wrong unit.")
    lines.append("- [ ] Does DINOv3 vs DINOv2 matter? Include the swap delta.")
    lines.append("- [ ] How does the YOLO-easy block compare to YOLO-problem? Does retrieval move the problem block more?")
    lines.append("- [ ] Are there under-represented gallery units affecting their queries?")
    lines.append("")
    lines.append("## Exit criteria assessment")
    lines.append("")
    t5_lo, _ = wilson_ci(n_top5, n_q)
    lines.append(f"- Unit top-5 ≥ 50%: **{m['top5']:.1%}** — {'✅ PASS' if t5_lo >= 0.5 else '❌ MISS (Wilson lower bound ' + f'{t5_lo:.1%} < 50%)'}")
    if detection:
        d_recall = detection["metrics"]["detection_recall_iou50"]
        d_tp = detection["totals"]["true_positives"]
        d_gt = detection["totals"]["ground_truth_boxes"]
        d_lo, _ = wilson_ci(d_tp, d_gt)
        lines.append(f"- OWLv2 detection recall ≥ 66%: **{d_recall:.1%}** — {'✅ PASS' if d_lo >= 0.66 else '❌ MISS (Wilson lower bound ' + f'{d_lo:.1%} < 66%)'}")
    else:
        lines.append(f"- OWLv2 detection recall ≥ 66%: N/A (detection eval not completed for this run)")
    lines.append("")
    lines.append("## Reproduction")
    lines.append("")
    lines.append("```bash")
    lines.append("yolo_env/bin/python3 scripts/phase1/extract_gt_crops.py")
    lines.append("# fill scripts/phase1/labels.csv by hand")
    lines.append("yolo_env/bin/python3 scripts/phase1/auto_split.py")
    lines.append("yolo_env/bin/python3 scripts/phase1/build_gallery.py")
    lines.append("yolo_env/bin/python3 scripts/phase1/embed_gallery.py")
    lines.append("yolo_env/bin/python3 scripts/phase1/eval_retrieval.py")
    lines.append("yolo_env/bin/python3 scripts/phase1/eval_detection.py")
    lines.append("yolo_env/bin/python3 scripts/phase1/generate_report.py")
    lines.append("```")
    lines.append("")

    BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))
    print(f"Report draft: {out_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
