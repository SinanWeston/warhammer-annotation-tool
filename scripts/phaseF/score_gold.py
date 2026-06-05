"""Score a detector's pseudo-labels against the frozen gold set (gold_v2).

Thin CLI over `photoanalyzer.eval.gold`. Consumes the Phase F1 box output
(`data/pseudo_labels/boxes/<id>.json`, pixel xywh) and reports the metrics that
actually matter for Tier 1: count-MAE sliced by scene density (the headline),
per-faction recall (DG/Necron/Tyranid flagged wide-CI), and a recall@IoU sweep
that surfaces box-convention mismatch (gold = model+base, SAM = mask-tight).

  fiftyone_env/bin/python scripts/phaseF/score_gold.py \
      --preds data/pseudo_labels/boxes [--score-thresh 0.25] \
      [--base-pad 0.10] [--json out.json]

`--base-pad F` applies the box-convention fix (extend pred boxes' bottom edge by
F·h) before scoring — use it once the recall@IoU sweep shows a base-clip gap.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from photoanalyzer.eval import boxconv, gold  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default="data/gold/gold_v2.json")
    ap.add_argument("--preds", required=True, help="dir of per-image box JSONs")
    ap.add_argument("--score-thresh", type=float, default=0.0)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--base-pad", type=float, default=0.0,
                    help="bottom-pad pred boxes by this fraction (convention fix)")
    ap.add_argument("--json", help="write the full report dict here")
    args = ap.parse_args()

    G = gold.load_gold(args.gold)
    preds = gold.load_predictions(args.preds, score_thresh=args.score_thresh)
    if args.base_pad > 0:
        dims = {g.basename: (g.width, g.height) for g in G}
        preds = boxconv.apply_base_extension(preds, args.base_pad, dims)

    # always print the convention diagnostic — it's the cheapest insurance
    diag = boxconv.convention_diagnostic(
        {g.basename: g.boxes for g in G}, preds)
    report = gold.score_gold(G, preds, iou_threshold=args.iou)

    print(gold.format_report(report))
    print(f"\n  box-convention diagnostic: {diag.as_dict()}")
    if diag.base_clip_signature and args.base_pad == 0:
        print("  → base-clip detected; re-run with --base-pad 0.10 to reconcile.")

    if args.json:
        out = report.as_dict()
        out["box_convention_diagnostic"] = diag.as_dict()
        out["params"] = vars(args)
        Path(args.json).write_text(json.dumps(out, indent=2))
        print(f"\n  wrote {args.json}")


if __name__ == "__main__":
    main()
