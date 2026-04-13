#!/usr/bin/env python3
"""
Phase 2 — generate the benchmark markdown report.

Consumes:
    scripts/phase2/results/retrieval_summary.json
    (Phase 1's detection_summary.json carries over for the detection KPI.)

Emits:
    docs/benchmarks/YYYY-MM-DD-phase2-scoped.md
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE2_RESULTS = REPO_ROOT / "scripts" / "phase2" / "results"
PHASE1_RESULTS = REPO_ROOT / "scripts" / "phase1" / "results"
BENCHMARKS_DIR = REPO_ROOT / "docs" / "benchmarks"

PHASE1_BASELINE = {
    "top1": 0.667,
    "top3": 0.667,
    "top5": 0.833,
    "mrr": 0.722,
    "faction_top1": 0.667,
    "detection_recall": 0.833,
    "detection_precision": 0.006,
}


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def fmt_pct_ci(value: float, k: int, n: int) -> str:
    lo, hi = wilson_ci(k, n)
    return f"{value:.1%} ({lo:.1%}–{hi:.1%})"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=None)
    p.add_argument("--date", default=None)
    return p.parse_args()


def variant_row(label: str, v: dict, n: int, bold_pass_threshold: float | None = None) -> str:
    """Format one row of the headline metrics table."""
    cells = [label]
    for key in ("top1", "top3", "top5"):
        counts_key = key
        k = v["counts"][counts_key]
        val = v[key]
        formatted = fmt_pct_ci(val, k, n)
        if bold_pass_threshold is not None and key == "top3" and val >= bold_pass_threshold:
            formatted = f"**{formatted}** ✓"
        cells.append(formatted)
    cells.append(f"{v['mrr']:.3f}")
    return "| " + " | ".join(cells) + " |"


def main():
    args = parse_args()
    retrieval = json.loads((PHASE2_RESULTS / "retrieval_summary.json").read_text())
    det = None
    det_path = PHASE2_RESULTS / "detection_summary.json"
    if det_path.exists():
        det = json.loads(det_path.read_text())
    elif (PHASE1_RESULTS / "detection_summary.json").exists():
        det = json.loads((PHASE1_RESULTS / "detection_summary.json").read_text())

    m = retrieval["metrics"]
    n = m["num_queries"]
    per_q = retrieval["per_query"]

    tier2_k = sum(1 for q in per_q if q["tier2_correct"])

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    out_path = Path(args.out) if args.out else BENCHMARKS_DIR / f"{date_str}-phase2-scoped.md"

    lines = []
    lines.append("# Phase 2 — scoped retrieval (Tier 1 + Tier 2 + Tier 3)")
    lines.append("")
    lines.append(f"**Date**: {date_str}")
    lines.append(f"**Phase**: 2 (Tier 2 faction classifier + scoped Tier 3)")
    lines.append(f"**Retrieval model**: `{retrieval['model_id']}`")
    lines.append(f"**Tier 2 classifier**: KNN-vote on DINOv2 gallery embeddings (k={retrieval.get('tier2_k', 5)})")
    lines.append(f"**Queries**: {n}")
    lines.append("")
    lines.append("## Exit criteria")
    lines.append("")
    lines.append("- **Faction top-1 ≥ 90%** (Tier 2 accuracy on the query crops)")
    lines.append("- **Unit top-3 ≥ 70%** within-faction (Tier 3 scoped by Tier 2)")
    lines.append("")
    tier2_val = m["tier2_faction_top1"]
    tier2_lo, _ = wilson_ci(tier2_k, n)
    tier2_pass = "✅ PASS" if tier2_lo >= 0.90 else "❌ MISS"
    scoped_actual = m["scoped_actual"]
    sa_top3_lo, _ = wilson_ci(scoped_actual["counts"]["top3"], n)
    retrieval_pass = "✅ PASS" if sa_top3_lo >= 0.70 else "❌ MISS"
    lines.append(f"- Tier 2 faction top-1: **{tier2_val:.1%}** (Wilson lower bound {tier2_lo:.1%}) — {tier2_pass}")
    lines.append(f"- Scoped unit top-3: **{scoped_actual['top3']:.1%}** (Wilson lower bound {sa_top3_lo:.1%}) — {retrieval_pass}")
    lines.append("")

    lines.append("## Tier 2 — faction classifier")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Faction top-1 | {fmt_pct_ci(tier2_val, tier2_k, n)} |")
    lines.append("")

    lines.append("## Tier 3 retrieval — three variants side-by-side")
    lines.append("")
    lines.append("| Variant | Unit top-1 | Unit top-3 | Unit top-5 | MRR |")
    lines.append("|---|---|---|---|---|")
    lines.append(variant_row("unscoped (Phase 1-style)", m["unscoped"], n))
    lines.append(variant_row("scoped_actual (production)", m["scoped_actual"], n, bold_pass_threshold=0.70))
    lines.append(variant_row("scoped_oracle (upper bound)", m["scoped_oracle"], n))
    lines.append("")

    # Comparison vs Phase 1 on the unscoped number.
    lines.append("## Delta vs Phase 1")
    lines.append("")
    lines.append("| Metric | Phase 1 (6q) | Phase 2 unscoped | Phase 2 scoped_actual |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| Unit top-1 | {PHASE1_BASELINE['top1']:.1%} | {m['unscoped']['top1']:.1%} | "
        f"{m['scoped_actual']['top1']:.1%} |"
    )
    lines.append(
        f"| Unit top-3 | {PHASE1_BASELINE['top3']:.1%} | {m['unscoped']['top3']:.1%} | "
        f"{m['scoped_actual']['top3']:.1%} |"
    )
    lines.append(
        f"| Unit top-5 | {PHASE1_BASELINE['top5']:.1%} | {m['unscoped']['top5']:.1%} | "
        f"{m['scoped_actual']['top5']:.1%} |"
    )
    lines.append(
        f"| MRR | {PHASE1_BASELINE['mrr']:.3f} | {m['unscoped']['mrr']:.3f} | "
        f"{m['scoped_actual']['mrr']:.3f} |"
    )
    lines.append("")

    # Tier 2 + Tier 3 confusion.
    # If Tier 2 was right, how well did scoped_actual perform? If Tier 2 was
    # wrong, scoped_actual will likely fail — good to quantify.
    right = [q for q in per_q if q["tier2_correct"]]
    wrong = [q for q in per_q if not q["tier2_correct"]]
    right_top3 = sum(1 for q in right if q["scoped_actual_rank"] and q["scoped_actual_rank"] <= 3)
    wrong_top3 = sum(1 for q in wrong if q["scoped_actual_rank"] and q["scoped_actual_rank"] <= 3)
    lines.append("## Tier 2 ⇒ Tier 3 cascade")
    lines.append("")
    lines.append("| Tier 2 verdict | queries | Tier 3 top-3 |")
    lines.append("|---|---|---|")
    lines.append(f"| Tier 2 correct | {len(right)} | {right_top3}/{len(right)} = {right_top3/max(len(right),1):.0%} |")
    lines.append(f"| Tier 2 wrong | {len(wrong)} | {wrong_top3}/{len(wrong)} = {wrong_top3/max(len(wrong),1):.0%} |")
    lines.append("")

    # Per-faction breakdown on scoped_actual.
    lines.append("## Per-faction breakdown (scoped_actual)")
    lines.append("")
    lines.append("| Faction | Queries | Top-1 | Top-3 | Top-5 | Tier 2 correct |")
    lines.append("|---|---|---|---|---|---|")
    by_faction: dict[str, list[dict]] = defaultdict(list)
    for q in per_q:
        by_faction[q["true_faction"]].append(q)
    for fac in sorted(by_faction):
        qs = by_faction[fac]
        fn = len(qs)
        t1 = sum(1 for q in qs if q["scoped_actual_rank"] == 1)
        t3 = sum(1 for q in qs if q["scoped_actual_rank"] and q["scoped_actual_rank"] <= 3)
        t5 = sum(1 for q in qs if q["scoped_actual_rank"] and q["scoped_actual_rank"] <= 5)
        t2 = sum(1 for q in qs if q["tier2_correct"])
        lines.append(f"| {fac} | {fn} | {t1}/{fn} ({t1/fn:.0%}) | {t3}/{fn} ({t3/fn:.0%}) | "
                     f"{t5}/{fn} ({t5/fn:.0%}) | {t2}/{fn} ({t2/fn:.0%}) |")
    lines.append("")

    # Named failure examples: 3 queries with worst scoped_actual rank.
    fails = sorted(per_q, key=lambda q: (q["scoped_actual_rank"] or 999))[-3:]
    lines.append("## Named failure examples")
    lines.append("")
    for q in fails:
        r = q["scoped_actual_rank"]
        lines.append(f"**`{q['query_path']}`** — true `{q['true_faction']}/{q['true_unit']}`, "
                     f"Tier 2 → `{q['tier2_pred']}` ({q['tier2_conf']:.0%}), scoped rank: {r or '>5'}")
        for i, t in enumerate(q.get("scoped_actual_top5", [])[:3], 1):
            match = " ←" if t["unit"] == q["true_unit"] else ""
            lines.append(f"  {i}. {t['faction']}/{t['unit']} — sim {t['sim']:.3f}{match}")
        lines.append("")

    # Detection stays at Phase 1 measured values unless re-measured.
    if det:
        lines.append("## Detection (unchanged from Phase 1; re-run only if Tier 1 is swapped)")
        lines.append("")
        d_m = det["metrics"]
        lines.append(f"- OWLv2 detection recall @ IoU 0.5: **{d_m['detection_recall_iou50']:.1%}** "
                     f"(vs YOLO baseline {PHASE1_BASELINE['detection_recall']:.1%})")
        lines.append(f"- OWLv2 detection precision @ IoU 0.5: **{d_m['detection_precision_iou50']:.1%}** "
                     f"(score threshold {det.get('score_threshold', 0.1)}; tune for precision in a follow-up)")
        lines.append("")

    lines.append("## Reproduction")
    lines.append("")
    lines.append("```bash")
    lines.append("yolo_env/bin/python3 scripts/phase2/extract_more_crops.py")
    lines.append("# fill remaining unit_slug rows via warhammer-analyzer labeller")
    lines.append("yolo_env/bin/python3 scripts/phase2/auto_split.py")
    lines.append("yolo_env/bin/python3 scripts/phase2/build_gallery.py")
    lines.append("yolo_env/bin/python3 scripts/phase2/embed_gallery.py")
    lines.append("yolo_env/bin/python3 scripts/phase2/eval_scoped_retrieval.py")
    lines.append("yolo_env/bin/python3 scripts/phase2/generate_report.py")
    lines.append("```")
    lines.append("")

    lines.append("See [../../STRATEGY.md](../../STRATEGY.md) §7.2 for the phase spec.")

    BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))
    print(f"Report: {out_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
