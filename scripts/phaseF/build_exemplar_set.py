"""Phase F1.4 — Build a stratified set of gold crops to use as OWLv2
visual exemplars. Output: ~30 JPEGs under `data/exemplars/` plus a
manifest listing each crop's source (imageId, bbox, faction).

Stratification: aim for 1–2 exemplars per faction × 3 bbox scale
buckets (small / medium / large fraction of image area). Prefer
high-quality crops — annotations tagged with a real person's name,
not pseudo-origin — and with well-shaped (non-degenerate) bboxes.

Usage:
    yolo_env/bin/python scripts/phaseF/build_exemplar_set.py
    yolo_env/bin/python scripts/phaseF/build_exemplar_set.py --count 40
"""
from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

ANN_DIR = Path("backend/training_data_annotations")
OUT_DIR = Path("data/exemplars")
MANIFEST = OUT_DIR / "manifest.json"


@dataclass
class Candidate:
    image_id: str
    image_path: Path
    faction: str
    bbox: tuple[float, float, float, float]   # x, y, w, h
    area_frac: float                           # bbox area / image area
    source: str
    annotator: str


def scale_bucket(area_frac: float) -> str:
    """Small < 2% of image, large > 10%, medium between."""
    if area_frac < 0.02: return "small"
    if area_frac > 0.10: return "large"
    return "medium"


def collect_candidates() -> list[Candidate]:
    out: list[Candidate] = []
    for p in ANN_DIR.glob("*.json"):
        if p.name.endswith(".skip.json"): continue
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        if data.get("pseudoLabelled"): continue
        annotator = data.get("annotatedBy") or ""
        if annotator.startswith("pseudo-"): continue
        img_path = Path(data["imagePath"])
        if not img_path.exists(): continue
        img_w = data.get("width") or 0
        img_h = data.get("height") or 0
        if not (img_w > 0 and img_h > 0): continue
        img_area = float(img_w * img_h)
        faction = data.get("faction") or "_unknown"
        source = data.get("source") or "?"
        for ann in data.get("annotations", []):
            b = ann.get("modelBbox") or {}
            x, y, w, h = b.get("x"), b.get("y"), b.get("width"), b.get("height")
            if not all(isinstance(v, (int, float)) for v in (x, y, w, h)):
                continue
            if w <= 0 or h <= 0: continue
            # Aspect-ratio sanity: reject extreme ratios that likely
            # indicate a label error or a banner fragment.
            ar = w / h if h > 0 else 0
            if ar < 0.2 or ar > 5: continue
            # Area sanity: too-tiny crops are unreliable exemplars.
            if w * h < 40 * 40: continue
            area_frac = (w * h) / img_area if img_area else 0
            out.append(Candidate(
                image_id=data["imageId"],
                image_path=img_path,
                faction=faction,
                bbox=(float(x), float(y), float(w), float(h)),
                area_frac=area_frac,
                source=source,
                annotator=annotator,
            ))
    return out


def stratified_pick(cands: list[Candidate], count: int, seed: int) -> list[Candidate]:
    """Pick ~count exemplars, stratified by faction × scale bucket.
    Aim for even faction coverage first, fill remaining slots at random."""
    rng = random.Random(seed)
    by_faction_bucket: dict[tuple[str, str], list[Candidate]] = {}
    for c in cands:
        key = (c.faction, scale_bucket(c.area_frac))
        by_faction_bucket.setdefault(key, []).append(c)

    for lst in by_faction_bucket.values():
        rng.shuffle(lst)

    picked: list[Candidate] = []
    seen_images: set[str] = set()
    # Round-robin through faction-bucket keys so early quota goes to
    # breadth, not one faction dominating.
    keys = sorted(by_faction_bucket.keys())
    rng.shuffle(keys)
    while len(picked) < count:
        progressed = False
        for k in keys:
            if len(picked) >= count: break
            pool = by_faction_bucket[k]
            while pool:
                c = pool.pop()
                if c.image_id in seen_images:  # keep exemplars diverse
                    continue
                picked.append(c)
                seen_images.add(c.image_id)
                progressed = True
                break
        if not progressed:
            break
    return picked


def crop_one(c: Candidate, dst: Path, padding: float = 0.05) -> None:
    """Save the bbox crop with a small fractional padding so the
    exemplar captures base + silhouette generously — OWLv2 matches
    whole shapes, not silhouettes alone."""
    im = Image.open(c.image_path).convert("RGB")
    W, H = im.size
    x, y, w, h = c.bbox
    pad_w = w * padding
    pad_h = h * padding
    x0 = max(0, int(x - pad_w))
    y0 = max(0, int(y - pad_h))
    x1 = min(W, int(x + w + pad_w))
    y1 = min(H, int(y + h + pad_h))
    im.crop((x0, y0, x1, y1)).save(dst, format="JPEG", quality=92)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=30, help="Exemplars to pick (default 30).")
    ap.add_argument("--seed", type=int, default=42, help="Deterministic pick seed.")
    ap.add_argument("--force", action="store_true", help="Overwrite existing exemplars.")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if MANIFEST.exists() and not args.force:
        print(f"Manifest already exists at {MANIFEST}; use --force to rebuild.")
        return 1

    print("Scanning annotations…")
    cands = collect_candidates()
    print(f"  {len(cands)} gold bbox candidates across "
          f"{len({c.faction for c in cands})} factions")
    picked = stratified_pick(cands, args.count, args.seed)
    print(f"  picked {len(picked)}")

    # Clean existing crops when --force.
    if args.force:
        for f in OUT_DIR.glob("*.jpg"):
            f.unlink()

    manifest: list[dict] = []
    for i, c in enumerate(picked):
        dst = OUT_DIR / f"exemplar_{i:03d}_{c.faction}.jpg"
        crop_one(c, dst)
        manifest.append({
            "file": dst.name,
            "imageId": c.image_id,
            "faction": c.faction,
            "bbox": {"x": c.bbox[0], "y": c.bbox[1], "w": c.bbox[2], "h": c.bbox[3]},
            "area_frac": round(c.area_frac, 4),
            "scale_bucket": scale_bucket(c.area_frac),
            "source": c.source,
            "annotator": c.annotator,
        })
    MANIFEST.write_text(json.dumps({
        "version": 1,
        "seed": args.seed,
        "count": len(manifest),
        "exemplars": manifest,
    }, indent=2))
    print(f"Wrote {len(manifest)} crops + manifest to {OUT_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
