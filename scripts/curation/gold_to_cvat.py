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

import fiftyone as fo

ANNO_KEY = "gold_v1"
CLASSES = ["space_marines", "necrons", "tyranids", "death_guard",
           "unknown", "out_of_scope"]


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    ds = fo.load_dataset("wh40k_pile")
    gold = ds.match_tags("gold")

    if cmd == "push":
        if ANNO_KEY in ds.list_annotation_runs():
            print(f"'{ANNO_KEY}' already exists. Pull it or delete with:")
            print(f"  ds.delete_annotation_run('{ANNO_KEY}')")
            return
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
