"""Triage SAM 3 pseudo-labels → prioritized F3 review queue + zero-box bucket.

Thin CLI over `photoanalyzer.eval.triage`. Consumes the Phase F1 box output
(`data/pseudo_labels/boxes/<id>.json`) and emits:
  - <out>/review_queue.csv   — images needing review, highest-value first
                               (low-conf > count-outlier > geom-outlier > 0-box)
  - <out>/zero_box.txt       — the review bucket: "junk OR hard SAM-3 miss"
  - prints a bucket/reason summary

Per the decided strategy: zero-box images are NOT auto-dropped — the hard misses
among them are the valuable active-learning cases.

  fiftyone_env/bin/python scripts/phaseF/triage_pseudolabels.py \
      --preds data/pseudo_labels/boxes --out data/phaseF/triage
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from photoanalyzer.eval import triage  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preds", required=True, help="dir of per-image box JSONs")
    ap.add_argument("--out", default="data/phaseF/triage")
    ap.add_argument("--low-conf", type=float, default=triage.LOW_CONF)
    args = ap.parse_args()

    preds_dir = Path(args.preds)
    records = [json.loads(p.read_text()) for p in sorted(preds_dir.glob("*.json"))]
    if not records:
        raise SystemExit(f"no *.json under {preds_dir}")

    triaged = triage.triage_predictions(records, low_conf=args.low_conf)
    summary = triage.summarize(triaged)
    print(json.dumps(summary, indent=2))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    review = sorted((t for t in triaged if t.needs_review), key=lambda t: t.priority)
    with (out / "review_queue.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(triaged[0].as_dict()))
        w.writeheader()
        for t in review:
            w.writerow(t.as_dict())

    zero = [t.basename for t in triaged if t.bucket == "zero_box"]
    (out / "zero_box.txt").write_text("\n".join(zero) + ("\n" if zero else ""))

    print(f"\nwrote {out}/review_queue.csv ({len(review)} images) "
          f"+ zero_box.txt ({len(zero)} images)")


if __name__ == "__main__":
    main()
