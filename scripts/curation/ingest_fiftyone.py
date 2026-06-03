"""Ingest the WH40K image pile into a FiftyOne dataset (Battle Scanner Plan §4.1, D1).

Turns the scraped image pile into a *designed dataset*: every image gets weak
labels parsed from its path (faction, source, unit) plus a corpus tag, so we can
slice/dedup/role-split in FiftyOne downstream. Folder-faction is a WEAK label — the
corpus has taxonomy noise (genestealer_cult vs _cults, eldar vs aeldari, etc.); we
record it as-is and canonicalise later against photoanalyzer.taxonomy.

Path conventions handled:
  backend/training_data/{faction}/{source}/img            -> faction, source
  training_data_v2/{faction}/isolation/{unit}/img         -> faction, isolation, unit
  training_data_v2/{faction}/{combat_patrol|ebay|...}/img -> faction, source

Usage:
  fiftyone_env/bin/python scripts/curation/ingest_fiftyone.py [--name wh40k_pile] [--overwrite]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import fiftyone as fo

REPO = Path(__file__).resolve().parents[2]

# (root dir, corpus tag)
ROOTS = [
    (REPO / "backend" / "training_data", "td1"),
    (REPO / "training_data_v2", "td2"),
]

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def iter_images(root: Path):
    for p in root.rglob("*"):
        if p.suffix.lower() in IMG_EXTS and p.is_file():
            yield p


def parse_weak_labels(path: Path, root: Path) -> dict:
    parts = path.relative_to(root).parts  # (.., filename)
    faction = parts[0] if len(parts) >= 2 else "_unknown"
    source = parts[1] if len(parts) >= 3 else None
    unit = parts[2] if (source == "isolation" and len(parts) >= 4) else None
    return {"weak_faction": faction, "source": source, "weak_unit": unit}


def build_samples(root: Path, corpus: str):
    for p in iter_images(root):
        wl = parse_weak_labels(p, root)
        s = fo.Sample(filepath=str(p))
        s["weak_faction"] = wl["weak_faction"]
        s["source"] = wl["source"]
        s["weak_unit"] = wl["weak_unit"]
        s["corpus"] = corpus
        s.tags.append(corpus)
        if wl["source"]:
            s.tags.append(f"src:{wl['source']}")
        yield s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="wh40k_pile")
    ap.add_argument("--overwrite", action="store_true", help="delete existing dataset first")
    ap.add_argument("--batch", type=int, default=5000)
    args = ap.parse_args()

    if args.name in fo.list_datasets():
        if not args.overwrite:
            raise SystemExit(
                f"Dataset '{args.name}' already exists. Pass --overwrite to replace it."
            )
        fo.delete_dataset(args.name)

    ds = fo.Dataset(args.name, persistent=True)

    total = 0
    for root, corpus in ROOTS:
        if not root.exists():
            print(f"skip (missing): {root}")
            continue
        batch = []
        n_root = 0
        for s in build_samples(root, corpus):
            batch.append(s)
            if len(batch) >= args.batch:
                ds.add_samples(batch)
                n_root += len(batch)
                batch = []
        if batch:
            ds.add_samples(batch)
            n_root += len(batch)
        total += n_root
        print(f"{corpus}: {n_root:>6} images  <- {root}")

    print(f"\nTotal ingested: {total} into dataset '{args.name}' (persistent)")
    print("Weak-faction distribution:")
    for faction, count in sorted(
        ds.count_values("weak_faction").items(), key=lambda kv: -kv[1]
    ):
        print(f"  {count:>6}  {faction}")


if __name__ == "__main__":
    main()
