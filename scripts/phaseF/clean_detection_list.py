"""Emit the clean auto-label image list for the SAM 3 Tier 1 run.

The canonical answer to "which images does the SAM 3 auto-labeller process?":
the detection pool, minus every junk layer accumulated during curation —

  excluded ─ pool membership (near-dups already parked as pool=excluded)
  lowq      ─ cheap technical junk  (quality_scan.py: blur / tiny / strip)
  low_unique ─ legacy junk-seed tag (near-uniform / low-information)
  junk_clip ─ CLIP semantic junk    (semantic_junk_scan.py: meme/terrain/...)

Writes the surviving filepaths (one per line) so the Colab bundle / autolabel
driver consumes a vetted list instead of re-deriving it. Also prints how many
each layer removed, so the filtering stays auditable.

Usage:
  fiftyone_env/bin/python scripts/phaseF/clean_detection_list.py \
      [--out data/phaseF/autolabel_images.txt] [--exclude lowq low_unique junk_clip]
"""
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_EXCLUDE = ["lowq", "low_unique", "junk_clip"]
DEFAULT_OUT = "data/phaseF/autolabel_images.txt"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="detection")
    ap.add_argument("--exclude", nargs="*", default=DEFAULT_EXCLUDE)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    import fiftyone as fo
    from fiftyone import ViewField as F

    ds = fo.load_dataset("wh40k_pile")
    pool = ds.match(F("pool") == args.pool)
    start = pool.count()
    print(f"{args.pool} pool: {start}")

    # report each layer's marginal removal (over the running clean view)
    clean = pool
    for tag in args.exclude:
        before = clean.count()
        clean = clean.match_tags(tag, bool=False)
        removed = before - clean.count()
        present = ds.match_tags(tag).count()
        print(f"  − {tag:11} removed {removed:5}  (tag total in dataset: {present})")

    kept = clean.count()
    print(f"clean auto-label set: {kept}  ({100*kept/start:.1f}% of pool, "
          f"{start - kept} filtered)")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(clean.values("filepath")) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
