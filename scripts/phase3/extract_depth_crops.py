#!/usr/bin/env python3
"""
Phase 3a.1 — depth-focused extraction.

Phase 3a hit the faction-breadth target but missed the unit-depth one:
109 / 139 gallery units (78%) sit at depth=1. Every named retrieval failure
with rank > 5 was a singleton unit. The fix is not more faction coverage,
it's *more crops of the specific units we already know about.*

This script:

1. Reads scripts/phase3/labels.csv, finds every (faction, unit_slug) with
   gallery depth < --min-depth (default 3). These are the "thin" units.
2. Embeds the existing gallery crop(s) of those thin units with DINOv2.
3. Walks the full annotation corpus (backend/training_data_annotations/),
   builds a pool of bboxes that are:
     - from the same faction as at least one thin unit,
     - not already materialised in scripts/phase3/crops/,
     - at least MIN_CROP_SIDE px per side,
     - bias: post-YOLO-export images first (never seen by current model).
4. Embeds every candidate, computes max cosine similarity against the
   thin-unit embeddings *restricted to candidates of the same faction*.
5. Ranks candidates by similarity, materialises the top-N into
   scripts/phase3/crops/{faction}/*.jpg and appends unlabelled rows to
   scripts/phase3/labels.csv with a hint in the `notes` column:
   "target: {unit_slug} sim={:.2f}".

The hint nudges the labeller toward the target — the user can accept,
correct, or drop the hint.

Usage:
    yolo_env/bin/python3 scripts/phase3/extract_depth_crops.py
    yolo_env/bin/python3 scripts/phase3/extract_depth_crops.py --target 200 --min-depth 3
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from io import BytesIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE3 = REPO_ROOT / "scripts" / "phase3"
LABELS_CSV = PHASE3 / "labels.csv"
CROPS_DIR = PHASE3 / "crops"
ANNOT_DIR = REPO_ROOT / "backend" / "training_data_annotations"
TRAIN_IMG = REPO_ROOT / "backend" / "yolo_dataset" / "images" / "train"
VAL_IMG = REPO_ROOT / "backend" / "yolo_dataset" / "images" / "val"

MIN_CROP_SIDE = 80
PADDING_PCT = 0.05
DEFAULT_MODEL = "facebook/dinov2-base"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from scraper_utils import compute_md5  # noqa: E402


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", type=int, default=200,
                   help="Total number of new unlabelled rows to add to labels.csv")
    p.add_argument("--min-depth", type=int, default=3,
                   help="Units below this gallery depth are targeted for expansion")
    p.add_argument("--per-unit-cap", type=int, default=4,
                   help="Max candidates surfaced per thin (faction, unit) target")
    p.add_argument("--per-faction-cap", type=int, default=30,
                   help="Safety cap on new crops per faction")
    p.add_argument("--min-sim", type=float, default=0.45,
                   help="Discard candidates whose best similarity is below this")
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--device", default=None)
    return p.parse_args()


def yolo_box_to_xyxy_padded(x, y, w, h, img_w, img_h, pad_pct):
    pad_w = w * pad_pct
    pad_h = h * pad_pct
    return (
        max(0, int(round(x - pad_w))),
        max(0, int(round(y - pad_h))),
        min(img_w, int(round(x + w + pad_w))),
        min(img_h, int(round(y + h + pad_h))),
    )


def load_labels_rows() -> list[dict]:
    with LABELS_CSV.open() as f:
        return list(csv.DictReader(f))


def find_thin_targets(rows: list[dict], min_depth: int) -> dict[tuple[str, str], list[str]]:
    """Return (faction, unit_slug) -> list of existing gallery crop paths for thin units."""
    gallery_paths: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in rows:
        if r.get("split") == "gallery" and r.get("unit_slug"):
            gallery_paths[(r["faction"], r["unit_slug"])].append(r["crop_path"])
    return {k: v for k, v in gallery_paths.items() if len(v) < min_depth}


def walk_corpus_candidates(existing_crop_names: set[str], target_factions: set[str]):
    """Yield dicts of bboxes from the corpus that are NOT already materialised."""
    train_stems = {p.stem for p in TRAIN_IMG.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")}
    val_stems = {p.stem for p in VAL_IMG.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")}
    for f in sorted(ANNOT_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        faction = data.get("faction", "")
        if faction not in target_factions:
            continue
        image_path = data.get("imagePath")
        if not image_path:
            continue
        abs_img = Path(image_path)
        if not abs_img.is_absolute():
            abs_img = REPO_ROOT / abs_img
        if not abs_img.exists():
            candidates = list((REPO_ROOT / "backend" / "training_data").rglob(abs_img.name))
            if not candidates:
                continue
            abs_img = candidates[0]
        is_post_export = abs_img.stem not in train_stems and abs_img.stem not in val_stems
        for bi, bbox in enumerate(data.get("annotations", [])):
            m = bbox.get("modelBbox")
            if not m:
                continue
            fname = f"{abs_img.stem}__{bi:02d}.jpg"
            if fname in existing_crop_names:
                continue
            yield {
                "image_path": abs_img,
                "faction": faction,
                "bbox": m,
                "bi": bi,
                "fname": fname,
                "is_post_export": is_post_export,
            }


def embed_paths(model, processor, device, paths: list[Path], batch: int):
    """L2-normalised embeddings for a list of absolute image paths. Returns np.ndarray."""
    import numpy as np
    import torch
    from PIL import Image

    out = []
    with torch.no_grad():
        for i in range(0, len(paths), batch):
            chunk = paths[i:i + batch]
            imgs = [Image.open(p).convert("RGB") for p in chunk]
            inputs = processor(images=imgs, return_tensors="pt").to(device)
            outputs = model(**inputs)
            if getattr(outputs, "pooler_output", None) is not None:
                e = outputs.pooler_output
            else:
                e = outputs.last_hidden_state[:, 0]
            e = torch.nn.functional.normalize(e, p=2, dim=-1)
            out.append(e.cpu().numpy())
    return np.concatenate(out, axis=0).astype(np.float32)


def embed_pil_batch(model, processor, device, pil_images):
    """Single-batch embedding for already-loaded PIL images."""
    import torch
    with torch.no_grad():
        inputs = processor(images=pil_images, return_tensors="pt").to(device)
        outputs = model(**inputs)
        if getattr(outputs, "pooler_output", None) is not None:
            e = outputs.pooler_output
        else:
            e = outputs.last_hidden_state[:, 0]
        e = torch.nn.functional.normalize(e, p=2, dim=-1)
        return e.cpu().numpy().astype("float32")


def main():
    args = parse_args()
    try:
        import numpy as np
        import torch
        from PIL import Image
        from transformers import AutoImageProcessor, AutoModel
    except ImportError as e:
        sys.exit(f"Missing dependency: {e}. Run from yolo_env.")

    device = args.device or ("cuda:0" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    rows = load_labels_rows()
    thin = find_thin_targets(rows, args.min_depth)
    if not thin:
        print(f"No thin units (all {len({(r['faction'], r['unit_slug']) for r in rows if r.get('unit_slug')})} units already ≥ {args.min_depth} depth). Nothing to do.")
        return
    target_factions = {f for (f, _) in thin.keys()}
    print(f"Thin targets: {len(thin)} (faction, unit) pairs across {len(target_factions)} factions")

    # ── Load DINOv2 ────────────────────────────────────────────────────
    print(f"Loading {args.model}...")
    processor = AutoImageProcessor.from_pretrained(args.model)
    model = AutoModel.from_pretrained(args.model).to(device).eval()

    # ── Step 1: embed existing thin-unit gallery crops ─────────────────
    target_entries: list[tuple[str, str, str]] = []  # (faction, unit, abs_path_str)
    for (faction, unit), crop_paths in thin.items():
        for rel in crop_paths:
            target_entries.append((faction, unit, str(REPO_ROOT / rel)))
    print(f"Embedding {len(target_entries)} existing thin-unit gallery crops...")
    target_embs = embed_paths(model, processor, device,
                              [Path(p) for (_, _, p) in target_entries], args.batch)

    # Group target embeddings by faction for per-faction candidate scoring.
    by_fac_target_embs: dict[str, list[tuple[str, np.ndarray]]] = defaultdict(list)
    for (faction, unit, _), emb in zip(target_entries, target_embs):
        by_fac_target_embs[faction].append((unit, emb))

    # ── Step 2: enumerate corpus candidates ────────────────────────────
    existing_names = {p.name for f in CROPS_DIR.iterdir() if f.is_dir() for p in f.iterdir()}
    print(f"Existing materialised crops: {len(existing_names)} filenames")

    candidates = list(walk_corpus_candidates(existing_names, target_factions))
    print(f"Candidate bboxes (same faction, not already on disk): {len(candidates)}")

    # Materialise each candidate to bytes in memory, keep only those >= MIN_CROP_SIDE.
    print("Cropping candidates (in-memory)...")
    kept = []
    for c in candidates:
        try:
            with Image.open(c["image_path"]) as im:
                img_w, img_h = im.size
                xyxy = yolo_box_to_xyxy_padded(
                    c["bbox"]["x"], c["bbox"]["y"],
                    c["bbox"]["width"], c["bbox"]["height"],
                    img_w, img_h, PADDING_PCT,
                )
                if (xyxy[2] - xyxy[0]) < MIN_CROP_SIDE or (xyxy[3] - xyxy[1]) < MIN_CROP_SIDE:
                    continue
                crop = im.convert("RGB").crop(xyxy)
                buf = BytesIO()
                crop.save(buf, format="JPEG", quality=92)
                data = buf.getvalue()
                c["pil"] = crop
                c["bytes"] = data
                c["md5"] = compute_md5(data)
                kept.append(c)
        except Exception as e:
            print(f"  skip {c['fname']}: {e}")
            continue
    print(f"Kept {len(kept)} viable candidates.")

    if not kept:
        print("Nothing to embed. Done.")
        return

    # Dedup by MD5
    seen = set()
    unique = []
    for c in kept:
        if c["md5"] in seen:
            continue
        seen.add(c["md5"])
        unique.append(c)
    print(f"After MD5 dedup: {len(unique)}")

    # ── Step 3: embed candidates in batches ────────────────────────────
    print("Embedding candidates...")
    cand_embs = []
    for i in range(0, len(unique), args.batch):
        chunk = unique[i:i + args.batch]
        embs = embed_pil_batch(model, processor, device, [c["pil"] for c in chunk])
        cand_embs.append(embs)
        print(f"  {min(i + args.batch, len(unique))}/{len(unique)}")
    cand_embs_arr = np.concatenate(cand_embs, axis=0)

    # ── Step 4: score each candidate against same-faction target embs ──
    print("Scoring candidates...")
    for c, e in zip(unique, cand_embs_arr):
        tgt_list = by_fac_target_embs[c["faction"]]
        # Best similarity against any target of this faction
        t_mat = np.stack([t[1] for t in tgt_list], axis=0)  # [T, D]
        sims = t_mat @ e  # [T]
        best_idx = int(np.argmax(sims))
        c["best_unit"] = tgt_list[best_idx][0]
        c["best_sim"] = float(sims[best_idx])

    # ── Step 5: rank + pick top-N with per-unit and per-faction caps ───
    unique.sort(key=lambda c: (-c["best_sim"], not c["is_post_export"]))

    per_unit_count: dict[tuple[str, str], int] = defaultdict(int)
    per_faction_count: dict[str, int] = defaultdict(int)
    selected = []
    skipped_low_sim = 0
    skipped_cap = 0
    for c in unique:
        if c["best_sim"] < args.min_sim:
            skipped_low_sim += 1
            continue
        tup = (c["faction"], c["best_unit"])
        if per_unit_count[tup] >= args.per_unit_cap:
            skipped_cap += 1
            continue
        if per_faction_count[c["faction"]] >= args.per_faction_cap:
            skipped_cap += 1
            continue
        selected.append(c)
        per_unit_count[tup] += 1
        per_faction_count[c["faction"]] += 1
        if len(selected) >= args.target:
            break
    print(f"Selected {len(selected)} / target {args.target}  "
          f"(skipped: {skipped_low_sim} low-sim, {skipped_cap} cap)")

    # ── Step 6: materialise + append rows to labels.csv ────────────────
    new_rows = []
    for c in selected:
        dst = CROPS_DIR / c["faction"] / c["fname"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            dst.write_bytes(c["bytes"])
        hint = f"target: {c['best_unit']} sim={c['best_sim']:.2f}"
        new_rows.append({
            "crop_path": f"scripts/phase3/crops/{c['faction']}/{c['fname']}",
            "faction": c["faction"],
            "unit_slug": "",
            "notes": hint,
            "source": "post_export" if c["is_post_export"] else "yolo_split",
            "split": "",
        })

    # ── Step 7: write out labels.csv (merge on crop_path) ──────────────
    headers = ["crop_path", "faction", "unit_slug", "notes", "source", "split"]
    merged: dict[str, dict] = {}
    for r in rows:
        merged[r["crop_path"]] = {h: r.get(h, "") for h in headers}
    for r in new_rows:
        if r["crop_path"] in merged:
            continue  # never overwrite existing
        merged[r["crop_path"]] = r

    with LABELS_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for k in sorted(merged):
            w.writerow(merged[k])

    labelled = sum(1 for r in merged.values() if r["unit_slug"])
    unlabelled = len(merged) - labelled
    print(f"\nlabels.csv now: {len(merged)} rows  ({labelled} labelled, {unlabelled} unlabelled — +{len(selected)} new)")

    # ── Step 8: per-faction/per-unit report ────────────────────────────
    print("\nPer-faction breakdown of added rows:")
    for f in sorted(per_faction_count, key=lambda x: -per_faction_count[x]):
        print(f"  {f:28s} +{per_faction_count[f]}")

    print("\nTop unit targets receiving candidates:")
    unit_tallies = sorted(per_unit_count.items(), key=lambda kv: -kv[1])
    for (f, u), n in unit_tallies[:20]:
        print(f"  {f}/{u:30s} +{n}")

    print("\nNext: re-point the labeller at phase3 and label the new rows.")


if __name__ == "__main__":
    main()
