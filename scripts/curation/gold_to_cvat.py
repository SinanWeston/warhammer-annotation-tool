"""Send the 50-image gold set to CVAT for hand-labeling, and pull it back (Plan §3).

Two subcommands:
  push  -> upload the 'gold' images to CVAT, create a labeling task
  pull  -> load the finished annotations back into FiftyOne as `ground_truth`

Credentials are read from ~/.fiftyone/annotation_config.json (your CVAT username +
password) — this script never contains secrets.

Label schema (per LABELING_GUIDE.md):
  box class  = faction  (space_marines / necrons / tyranids / death_guard /
                         unknown / out_of_scope)
  attribute  = unit  (free text, best-effort — leave blank if unsure)

Usage:
  fiftyone_env/bin/python scripts/curation/gold_to_cvat.py push
  fiftyone_env/bin/python scripts/curation/gold_to_cvat.py pull
"""
from __future__ import annotations

import sys
from pathlib import Path

import fiftyone as fo

ANNO_KEY = "gold_v1"
CLASSES = ["space_marines", "necrons", "tyranids", "death_guard",
           "unknown", "out_of_scope"]
ENV = Path(__file__).resolve().parents[2] / ".env"


def env(key: str) -> str | None:
    if not ENV.exists():
        return None
    for line in ENV.read_text().splitlines():
        if line.strip().startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    # feed CVAT creds from .env to FiftyOne (works for both push and pull)
    import os
    user, pw = env("CVAT_USERNAME"), env("CVAT_PASSWORD")
    if user and pw:
        os.environ["FIFTYONE_CVAT_USERNAME"] = user
        os.environ["FIFTYONE_CVAT_PASSWORD"] = pw
        os.environ.setdefault("FIFTYONE_CVAT_URL", "https://app.cvat.ai")

    ds = fo.load_dataset("wh40k_pile")
    gold = ds.match_tags("gold")

    if cmd == "push":
        if ANNO_KEY in ds.list_annotation_runs():
            print(f"'{ANNO_KEY}' already exists. Pull it or delete with:")
            print(f"  ds.delete_annotation_run('{ANNO_KEY}')")
            return
        if not (user and pw):
            raise SystemExit("Add CVAT_USERNAME and CVAT_PASSWORD to .env first.")
        gold.annotate(
            ANNO_KEY,
            backend="cvat",
            label_field="ground_truth",
            label_type="detections",
            classes=CLASSES,
            attributes={"unit": {"type": "text", "default": ""}},
            task_name="wh40k_gold_v1",
            segment_size=50,
        )
        print(f"pushed {gold.count()} images to CVAT as task 'wh40k_gold_v1'.")
        print("open the task at https://app.cvat.ai/tasks and label, then run: ... pull")

    elif cmd == "pull":
        ds.load_annotations(ANNO_KEY)
        n = ds.match_tags("gold").exists("ground_truth").count()
        print(f"loaded annotations into 'ground_truth' on {n}/{gold.count()} gold images")
        boxes = sum(len(s.ground_truth.detections)
                    for s in ds.match_tags("gold").exists("ground_truth"))
        print(f"total boxes: {boxes}")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
