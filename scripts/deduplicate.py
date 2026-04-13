#!/usr/bin/env python3
"""
pHash Deduplication Pass for Battle Scanner Training Data

Builds a perceptual hash index of all images in training_data_v2/, clusters
near-duplicate images using Union-Find (Hamming distance ≤ threshold), and
moves losers to training_data_v2/rejected/duplicate/.

Within each cluster, the "winner" is the image with the highest score:
    width * height * sqrt(file_size)

Prerequisites:
    pip install imagehash Pillow

Usage:
    python scripts/deduplicate.py --faction necrons --dry-run
    python scripts/deduplicate.py --faction necrons
    python scripts/deduplicate.py --dry-run          # all factions
    python scripts/deduplicate.py                    # full dedup pass
    python scripts/deduplicate.py --index-only       # build hash index only
    python scripts/deduplicate.py --rebuild-index    # recompute all hashes

Note on threshold: 10/64 bits finds exact duplicates at different resolutions.
Images of the same mini from different angles typically differ by >15 bits and
are correctly kept. Always test with --dry-run before committing.
"""

import argparse
import json
import math
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scraper_utils import OUTPUT_DIR, METADATA_DIR

PHASH_INDEX_FILE = METADATA_DIR / "phash_index.json"
REJECTED_DIR = OUTPUT_DIR / "rejected" / "duplicate"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
INDEX_SAVE_INTERVAL = 500


# ─── File Discovery ───────────────────────────────────────────────────────────

def find_images(faction: str | None = None) -> list[Path]:
    """Return all image paths under OUTPUT_DIR, excluding rejected/ and metadata/."""
    paths = []
    for p in sorted(OUTPUT_DIR.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in IMAGE_EXTS:
            continue
        rel = p.relative_to(OUTPUT_DIR)
        parts = rel.parts
        if parts[0] in ("rejected", "metadata"):
            continue
        if faction and parts[0] != faction:
            continue
        paths.append(p)
    return paths


# ─── pHash Index ─────────────────────────────────────────────────────────────

def compute_phash(path: Path) -> str | None:
    try:
        import imagehash
        from PIL import Image
        img = Image.open(path).convert("RGB")
        return str(imagehash.phash(img))
    except Exception:
        return None


def load_index() -> dict:
    if PHASH_INDEX_FILE.exists():
        with open(PHASH_INDEX_FILE) as f:
            return json.load(f)
    return {}


def save_index(index: dict):
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PHASH_INDEX_FILE, "w") as f:
        json.dump(index, f, indent=2)


def build_index(
    paths: list[Path],
    existing_index: dict,
    rebuild: bool = False,
) -> dict:
    """
    Compute pHash for each image not yet in the index.
    Saves every INDEX_SAVE_INTERVAL entries.
    """
    index = {} if rebuild else dict(existing_index)
    to_hash = [p for p in paths if str(p.relative_to(OUTPUT_DIR)) not in index]
    print(f"  {len(to_hash)} images to hash (already indexed: {len(index)})")

    for i, path in enumerate(to_hash):
        rel = str(path.relative_to(OUTPUT_DIR))
        h = compute_phash(path)
        if h:
            index[rel] = h

        if (i + 1) % INDEX_SAVE_INTERVAL == 0:
            save_index(index)
            print(f"  Hashed {i+1}/{len(to_hash)}", end="\r")

    save_index(index)
    print(f"\n  Index complete. {len(index)} entries.")
    return index


# ─── Union-Find ───────────────────────────────────────────────────────────────

class UnionFind:
    def __init__(self, items):
        self.parent = {x: x for x in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # path compression
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def clusters(self):
        from collections import defaultdict
        groups = defaultdict(list)
        for item in self.parent:
            groups[self.find(item)].append(item)
        return [v for v in groups.values() if len(v) > 1]


# ─── Hamming Distance ────────────────────────────────────────────────────────

def hamming(h1: str, h2: str) -> int:
    """Hamming distance between two hex pHash strings (each 16 hex chars = 64 bits)."""
    try:
        import imagehash
        return imagehash.hex_to_hash(h1) - imagehash.hex_to_hash(h2)
    except Exception:
        # Fallback: bit-by-bit comparison
        a = int(h1, 16)
        b = int(h2, 16)
        return bin(a ^ b).count("1")


# ─── Winner Selection ────────────────────────────────────────────────────────

def image_quality_score(path: Path) -> float:
    """Higher = better. Uses width * height * sqrt(file_size)."""
    try:
        from PIL import Image
        fsize = path.stat().st_size
        img = Image.open(path)
        w, h = img.size
        return w * h * math.sqrt(fsize)
    except Exception:
        return 0.0


# ─── Clustering ───────────────────────────────────────────────────────────────

def find_duplicate_clusters(index: dict, threshold: int) -> list[list[str]]:
    """
    Find all clusters of near-duplicate images using Union-Find.
    O(n²) pairwise comparison — ~5 min for 40K images.
    """
    keys = list(index.keys())
    hashes = list(index.values())
    n = len(keys)
    print(f"  Comparing {n} images pairwise (threshold={threshold})...")

    uf = UnionFind(keys)
    comparisons = 0

    for i in range(n):
        for j in range(i + 1, n):
            if hamming(hashes[i], hashes[j]) <= threshold:
                uf.union(keys[i], keys[j])
            comparisons += 1
            if comparisons % 5_000_000 == 0:
                print(f"  {comparisons:,} comparisons...", end="\r")

    clusters = uf.clusters()
    print(f"\n  Found {len(clusters)} duplicate clusters")
    return clusters


# ─── Main Dedup ───────────────────────────────────────────────────────────────

def deduplicate(
    clusters: list[list[str]],
    dry_run: bool = False,
) -> int:
    """Move losers to rejected/duplicate/. Returns count moved."""
    moved = 0
    for cluster in clusters:
        paths = [OUTPUT_DIR / rel for rel in cluster]
        scores = [(p, image_quality_score(p)) for p in paths if p.exists()]
        if len(scores) < 2:
            continue
        scores.sort(key=lambda x: x[1], reverse=True)
        # Keep the winner (scores[0]), move the rest
        for loser_path, score in scores[1:]:
            rel = loser_path.relative_to(OUTPUT_DIR)
            dst = REJECTED_DIR / rel
            if dry_run:
                print(f"  [DRY RUN] Would reject duplicate (score={score:.0f}): {rel}")
                moved += 1
            else:
                if loser_path.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(loser_path), str(dst))
                    moved += 1

    return moved


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Deduplicate images in training_data_v2/ using pHash"
    )
    parser.add_argument("--threshold", type=int, default=10,
                        help="Hamming distance threshold (default: 10). Lower = stricter.")
    parser.add_argument("--faction", metavar="SLUG", help="Limit to one faction directory")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be moved without making changes")
    parser.add_argument("--rebuild-index", action="store_true",
                        help="Recompute all hashes (ignores existing index)")
    parser.add_argument("--index-only", action="store_true",
                        help="Build/update hash index without deduplicating")
    args = parser.parse_args()

    try:
        import imagehash
    except ImportError:
        print("ERROR: imagehash is not installed. Run: pip install imagehash")
        sys.exit(1)

    print("=" * 60)
    print("pHash Deduplicator")
    print(f"Threshold: {args.threshold} bits")
    print(f"Faction: {args.faction or 'all'}")
    print(f"Dry run: {args.dry_run}")
    print(f"Rebuild index: {args.rebuild_index}")
    print("=" * 60)

    all_paths = find_images(args.faction)
    print(f"Found {len(all_paths)} images to process")

    existing_index = {} if args.rebuild_index else load_index()
    index = build_index(all_paths, existing_index, rebuild=args.rebuild_index)

    if args.index_only:
        print(f"\nIndex saved to: {PHASH_INDEX_FILE}")
        return

    # Filter index to only the current faction scope if specified
    if args.faction:
        scoped_index = {k: v for k, v in index.items() if k.startswith(args.faction + "/")}
    else:
        scoped_index = index

    clusters = find_duplicate_clusters(scoped_index, args.threshold)

    if not clusters:
        print("No duplicates found.")
        return

    total_dupes = sum(len(c) - 1 for c in clusters)
    print(f"  {total_dupes} duplicate images identified across {len(clusters)} clusters")

    moved = deduplicate(clusters, dry_run=args.dry_run)

    print(f"\n{'='*60}")
    if args.dry_run:
        print(f"DRY RUN complete. Would move {moved} duplicate images.")
    else:
        print(f"DONE. Moved {moved} duplicate images.")
    print(f"Rejected images moved to: {REJECTED_DIR}")
    print(f"Hash index: {PHASH_INDEX_FILE}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
