"""Send the 50-image gold set to CVAT for hand-labeling, and pull it back (Plan §3).

Two subcommands:
  push  -> upload the 'gold' images to CVAT, create a labeling task
  pull  -> load the finished annotations back into FiftyOne as `ground_truth`

Credentials: CVAT_USERNAME / CVAT_PASSWORD in .env. These are exported as
FIFTYONE_CVAT_* env vars BEFORE importing fiftyone — the annotation config is
built at import time, so setting them afterwards is too late.

Label schema (per LABELING_GUIDE.md):
  box class  = faction  (space_marines / necrons / tyranids / death_guard /
                         unknown / out_of_scope)
  attribute  = unit  (free text, best-effort — leave blank if unsure)

A profile (positional arg after the command, default 'v1') selects which image
set / CVAT task to act on, so later quota-fill rounds don't disturb finished work:
  v1 -> tag 'gold',     key 'gold_v1', task 'wh40k_gold_v1'  (the original 35)
  v2 -> tag 'gold_v2',  key 'gold_v2', task 'wh40k_gold_v2'  (DG+Necron fill)

Usage:
  fiftyone_env/bin/python scripts/curation/gold_to_cvat.py push [v1|v2]
  fiftyone_env/bin/python scripts/curation/gold_to_cvat.py pull [v1|v2]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

CLASSES = ["space_marines", "necrons", "tyranids", "death_guard",
           "unknown", "out_of_scope"]
PROFILES = {
    "v1": {"tag": "gold",    "key": "gold_v1", "task": "wh40k_gold_v1"},
    "v2": {"tag": "gold_v2", "key": "gold_v2", "task": "wh40k_gold_v2"},
    "v3": {"tag": "gold_v3", "key": "gold_v3", "task": "wh40k_gold_v3"},
    "v4": {"tag": "gold_v4", "key": "gold_v4", "task": "wh40k_gold_v4"},
}
ENV = Path(__file__).resolve().parents[2] / ".env"


def env(key: str) -> str | None:
    if not ENV.exists():
        return None
    for line in ENV.read_text().splitlines():
        if line.strip().startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


# --- set CVAT creds BEFORE importing fiftyone (annotation config is built at import) ---
_user, _pw = env("CVAT_USERNAME"), env("CVAT_PASSWORD")
if _user and _pw:
    os.environ["FIFTYONE_CVAT_USERNAME"] = _user
    os.environ["FIFTYONE_CVAT_PASSWORD"] = _pw
    os.environ.setdefault("FIFTYONE_CVAT_URL", "https://app.cvat.ai")

import fiftyone as fo  # noqa: E402


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    prof_name = sys.argv[2] if len(sys.argv) > 2 else "v1"
    if cmd in ("push", "pull") and not (_user and _pw):
        raise SystemExit("Add CVAT_USERNAME and CVAT_PASSWORD to .env first.")
    if cmd in ("push", "pull") and prof_name not in PROFILES:
        raise SystemExit(f"Unknown profile '{prof_name}'. Choose from: {', '.join(PROFILES)}")
    prof = PROFILES.get(prof_name, PROFILES["v1"])
    anno_key, tag, task = prof["key"], prof["tag"], prof["task"]

    ds = fo.load_dataset("wh40k_pile")
    gold = ds.match_tags(tag)

    if cmd == "push":
        if gold.count() == 0:
            raise SystemExit(f"No images tagged '{tag}'. Tag the candidate set first.")
        if anno_key in ds.list_annotation_runs():
            print(f"'{anno_key}' already exists. Delete it first with:")
            print(f"  ds.delete_annotation_run('{anno_key}')")
            return
        gold.annotate(
            anno_key,
            backend="cvat",
            label_field="ground_truth",
            label_type="detections",
            classes=CLASSES,
            task_name=task,
            segment_size=50,
        )
        print(f"pushed {gold.count()} images to CVAT as task '{task}'.")
        print("open the task at https://app.cvat.ai/tasks and label, then run: ... pull")

    elif cmd == "pull":
        ds.load_annotations(anno_key)
        n = ds.match_tags(tag).exists("ground_truth").count()
        print(f"loaded annotations into 'ground_truth' on {n}/{gold.count()} '{tag}' images")
        boxes = sum(len(s.ground_truth.detections)
                    for s in ds.match_tags(tag).exists("ground_truth"))
        print(f"total boxes: {boxes}")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
