"""Import Phase F1 pseudo-labels into the existing annotator for visual
review. Each per-image JSON under data/pseudo_labels/boxes/ becomes an
annotation JSON under backend/training_data_annotations/ so the
existing UI can display it with bboxes pre-drawn, and the user can
correct / save as a regular annotation.

Safety:
- Never overwrites an existing gold annotation (same imageId).
- Every imported file has `pseudoLabelled: true` + `annotatedBy:
  "pseudo-grounding-dino-v1"` so downstream training / export can
  filter them out, and a human save clears the flag.
- Writes `data/pseudo_labels/imported_manifest.json` listing every
  imageId touched, so reverting is one grep + rm away.

Usage:
    yolo_env/bin/python scripts/phaseF/import_pseudo_to_annotator.py
    yolo_env/bin/python scripts/phaseF/import_pseudo_to_annotator.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

PSEUDO_BOXES = Path("data/pseudo_labels/boxes")
ANN_DIR = Path("backend/training_data_annotations")
MANIFEST = Path("data/pseudo_labels/imported_manifest.json")
ANNOTATED_BY = "pseudo-grounding-dino-v1"


def convert(pseudo: dict) -> dict:
    """Map our per-image pseudo-label JSON onto the annotator's schema."""
    faction = pseudo.get("faction") or "_unknown"
    annotations = []
    for box, score in zip(pseudo.get("boxes_xywh", []), pseudo.get("scores", [])):
        x, y, w, h = box
        annotations.append({
            "id": f"pseudo-{uuid.uuid4().hex[:12]}",
            "modelBbox": {"x": x, "y": y, "width": w, "height": h},
            # BboxAnnotator requires classLabel on every bbox. Tier 1 is
            # class-agnostic so we fall back to the image's faction; the
            # user can re-class per-bbox if a given photo is multi-faction.
            "classLabel": faction,
            # Retain the auto-labeler's confidence as a debug crumb —
            # non-standard but harmless; the frontend just ignores
            # unknown fields.
            "pseudoScore": round(float(score), 4),
        })
    # Normalise imagePath to absolute. Colab's bundle produced paths like
    # `backend/training_data/...` (relative to the bundle root); the
    # annotator backend serves by absolute path. Use abspath (which does
    # NOT follow symlinks) so CMON symlinks stay as
    # `backend/training_data/_unknown/cmon/...` rather than resolving to
    # their `scripts/cmon/images/...` target — matches the convention the
    # gold annotations use.
    import os
    raw_path = pseudo["imagePath"]
    abs_path = raw_path if os.path.isabs(raw_path) else os.path.abspath(raw_path)
    return {
        "imageId": pseudo["imageId"],
        "imagePath": abs_path,
        "faction": faction,
        "source": pseudo.get("source"),
        "width": pseudo.get("width"),
        "height": pseudo.get("height"),
        "annotations": annotations,
        "rejectedPredictions": [],
        "redrawnPredictions": [],
        "annotatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "annotatedBy": ANNOTATED_BY,
        # Marker — downstream training MUST filter by this. A human save
        # via the annotator overwrites `annotatedBy` with the user's name
        # and drops this field, promoting the annotation to reviewed.
        "pseudoLabelled": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would happen without writing anything.")
    args = ap.parse_args()

    if not PSEUDO_BOXES.is_dir():
        print(f"No pseudo-labels found at {PSEUDO_BOXES}", file=sys.stderr)
        return 1
    ANN_DIR.mkdir(parents=True, exist_ok=True)

    imported: list[str] = []
    skipped_gold: list[str] = []
    skipped_empty: list[str] = []
    for p in sorted(PSEUDO_BOXES.glob("*.json")):
        try:
            pseudo = json.loads(p.read_text())
        except Exception as e:
            print(f"  skip unreadable {p.name}: {e}")
            continue
        img_id = pseudo.get("imageId")
        if not img_id:
            continue
        target = ANN_DIR / f"{img_id}.json"
        if target.exists():
            # Don't touch gold. The existing file might itself be a
            # prior pseudo import — re-running is allowed but only for
            # images that don't yet have any annotation at all, to
            # keep review progress intact.
            try:
                existing = json.loads(target.read_text())
                if not existing.get("pseudoLabelled"):
                    skipped_gold.append(img_id)
                    continue
            except Exception:
                skipped_gold.append(img_id)
                continue
        if not pseudo.get("boxes_xywh"):
            skipped_empty.append(img_id)
            continue
        record = convert(pseudo)
        if not args.dry_run:
            target.write_text(json.dumps(record, indent=2))
        imported.append(img_id)

    if not args.dry_run:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps({
            "version": 1,
            "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "annotated_by_tag": ANNOTATED_BY,
            "count": len(imported),
            "image_ids": imported,
        }, indent=2))

    mode = "DRY-RUN — nothing written" if args.dry_run else "imported"
    print(f"{mode}: {len(imported)} pseudo-labels")
    print(f"  skipped (gold already exists):  {len(skipped_gold)}")
    print(f"  skipped (pseudo had 0 boxes):   {len(skipped_empty)}")
    if not args.dry_run:
        print(f"  manifest: {MANIFEST}")
        print()
        print("Next:")
        print("  1. Start backend + frontend: `npm run dev`")
        print(f"  2. Open http://localhost:5173 and filter by annotatedBy = '{ANNOTATED_BY}'")
        print("     (or just filter by source and look for the pseudo marker in the header)")
        print("  3. Review / correct / save. Saving clears the pseudoLabelled flag.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
