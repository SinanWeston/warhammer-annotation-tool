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
# Legacy tag for Grounding-DINO-only pseudo runs. The ensemble pipeline
# sets richer tags per-image based on tier breakdown; see `tag_for()`.
ANNOTATED_BY_LEGACY = "pseudo-grounding-dino-v1"
ANNOTATED_BY = ANNOTATED_BY_LEGACY  # back-compat for existing callers


def tag_for(has_auto: bool, has_review: bool) -> str:
    """Tag an ensemble-pipeline import by the tier mix in its boxes.
    auto-only → `pseudo-ensemble-auto-v1` (light review).
    mixed     → `pseudo-ensemble-mixed-v1` (surfaces in review queue).
    review-only → `pseudo-ensemble-review-v1` (all low-confidence)."""
    if has_auto and has_review:
        return "pseudo-ensemble-mixed-v1"
    if has_auto:
        return "pseudo-ensemble-auto-v1"
    return "pseudo-ensemble-review-v1"


def _extract_boxes(pseudo: dict) -> list[dict]:
    """Normalise old and new pseudo schemas to a uniform box list.

    Legacy schema (pre-ensemble): {boxes_xywh: [[x,y,w,h]...], scores: [...]}.
    Ensemble schema: {boxes: [{xywh:[...], score, supporters:[...],
                               refinement_iou}...], detectors_used:[...]}.
    Output is a list of dicts with keys: xywh, score, supporters,
    refinement_iou.
    """
    if isinstance(pseudo.get("boxes"), list):
        # New ensemble schema.
        out = []
        for b in pseudo["boxes"]:
            out.append({
                "xywh": b["xywh"],
                "score": float(b.get("score", 0.0)),
                "supporters": tuple(b.get("supporters") or ()),
                "refinement_iou": float(b.get("refinement_iou", 0.0)),
            })
        return out
    # Legacy schema.
    out = []
    for xywh, score in zip(pseudo.get("boxes_xywh", []), pseudo.get("scores", [])):
        out.append({
            "xywh": list(xywh),
            "score": float(score),
            "supporters": ("grounding-dino",),
            "refinement_iou": 0.0,
        })
    return out


def convert(pseudo: dict) -> dict:
    """Map our per-image pseudo-label JSON onto the annotator's schema."""
    faction = pseudo.get("faction") or "_unknown"

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

    # Rescale pseudo coords if the pseudo run was against a downscaled
    # copy (prepare_colab_bundle.py caps long-edge at 1333 for tarball
    # size). The annotator serves the full-resolution original, so coords
    # in 1333-space would land in the top-left corner of a 2560-wide image.
    # Compare the pseudo's recorded width/height against the actual file.
    pseudo_w = pseudo.get("width")
    pseudo_h = pseudo.get("height")
    actual_w = actual_h = None
    try:
        from PIL import Image as _PILImage
        with _PILImage.open(abs_path) as _im:
            actual_w, actual_h = _im.size
    except Exception:
        pass

    sx = sy = 1.0
    if actual_w and actual_h and pseudo_w and pseudo_h:
        if (actual_w, actual_h) != (pseudo_w, pseudo_h):
            sx = actual_w / pseudo_w
            sy = actual_h / pseudo_h

    boxes_norm = _extract_boxes(pseudo)
    annotations = []
    has_auto = has_review = False
    for b in boxes_norm:
        x, y, w, h = b["xywh"]
        supporters = b["supporters"]
        agreement = len(supporters)
        if agreement >= 2:
            has_auto = True
        elif agreement == 1:
            has_review = True
        annotations.append({
            "id": f"pseudo-{uuid.uuid4().hex[:12]}",
            "modelBbox": {
                "x": x * sx, "y": y * sy,
                "width": w * sx, "height": h * sy,
            },
            # BboxAnnotator requires classLabel on every bbox. Tier 1 is
            # class-agnostic so we fall back to the image's faction; the
            # user can re-class per-bbox if a given photo is multi-faction.
            "classLabel": faction,
            # Confidence + ensemble provenance, non-standard but harmless —
            # the frontend ignores unknown fields. Downstream review tools
            # use `supporters` / `agreement_count` to prioritise queues.
            "pseudoScore": round(float(b["score"]), 4),
            "supporters": list(supporters),
            "agreement_count": agreement,
            "refinement_iou": round(float(b["refinement_iou"]), 4),
        })

    # Tag by tier — auto-only / review-only / mixed. Legacy Grounding-DINO
    # imports (no supporter info) get the legacy tag for back-compat.
    if any(a.get("supporters") for a in annotations):
        annotated_by = tag_for(has_auto, has_review)
    else:
        annotated_by = ANNOTATED_BY_LEGACY

    return {
        "imageId": pseudo["imageId"],
        "imagePath": abs_path,
        "faction": faction,
        "source": pseudo.get("source"),
        # Use actual image dims when we have them; fall back to pseudo's
        # recorded values if the file couldn't be opened.
        "width": actual_w or pseudo_w,
        "height": actual_h or pseudo_h,
        "annotations": annotations,
        "rejectedPredictions": [],
        "redrawnPredictions": [],
        "annotatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "annotatedBy": annotated_by,
        "detectors_used": pseudo.get("detectors_used", []),
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
        # Accept both legacy (boxes_xywh) and ensemble (boxes) schemas.
        if not pseudo.get("boxes_xywh") and not pseudo.get("boxes"):
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
