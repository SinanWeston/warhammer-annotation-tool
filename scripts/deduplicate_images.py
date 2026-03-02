"""
Image Deduplication Script

Finds near-duplicate images in the training pool using perceptual hashing (pHash).
Writes a blocklist of duplicate image filenames that the backend can exclude from
annotation queues.

Usage:
    python3 deduplicate_images.py [--threshold 8] [--output backend/duplicate_images.json]

Dependencies:
    pip install imagehash Pillow
"""

import os
import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict

def main():
    parser = argparse.ArgumentParser(description="Find near-duplicate images using perceptual hashing")
    parser.add_argument("--threshold", type=int, default=8, help="Hamming distance threshold (lower = stricter, default: 8)")
    parser.add_argument("--output", type=str, default=None, help="Output JSON path")
    parser.add_argument("--faction", type=str, default=None, help="Only scan a specific faction")
    parser.add_argument("--dry-run", action="store_true", help="Show results without writing file")
    args = parser.parse_args()

    try:
        import imagehash
        from PIL import Image
    except ImportError:
        print("ERROR: Missing dependencies. Install with:")
        print("  pip install imagehash Pillow")
        sys.exit(1)

    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    training_data = project_root / "backend" / "training_data"
    output_path = args.output or str(project_root / "backend" / "duplicate_images.json")

    if not training_data.exists():
        print(f"ERROR: Training data directory not found: {training_data}")
        sys.exit(1)

    # Non-faction directories to skip
    skip_dirs = {"hormagaunts", "tyranid_ripper_swarm", "reddit", "dakkadakka"}

    # Collect all image paths
    all_images = []
    factions = sorted([
        d for d in os.listdir(training_data)
        if (training_data / d).is_dir() and d not in skip_dirs
    ])

    if args.faction:
        factions = [f for f in factions if f == args.faction]

    for faction in factions:
        faction_dir = training_data / faction
        for source in ["reddit", "dakkadakka"]:
            src_dir = faction_dir / source
            if not src_dir.exists():
                continue
            for f in sorted(src_dir.iterdir()):
                if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
                    all_images.append(f)

    print(f"Scanning {len(all_images)} images across {len(factions)} factions...")
    print(f"Threshold: {args.threshold} (hamming distance)")
    print()

    # Hash all images
    hashes = {}  # path -> hash
    errors = 0
    for i, img_path in enumerate(all_images):
        if (i + 1) % 500 == 0:
            print(f"  Hashing... {i + 1}/{len(all_images)}")
        try:
            h = imagehash.phash(Image.open(img_path))
            hashes[str(img_path)] = h
        except Exception as e:
            errors += 1
            if errors <= 10:
                print(f"  WARNING: Failed to hash {img_path.name}: {e}")

    print(f"Hashed {len(hashes)} images ({errors} errors)")
    print()

    # Find duplicates
    paths = list(hashes.keys())
    hash_values = list(hashes.values())
    duplicates = []
    duplicate_groups = defaultdict(list)

    seen = set()
    for i in range(len(paths)):
        if paths[i] in seen:
            continue
        for j in range(i + 1, len(paths)):
            if paths[j] in seen:
                continue
            distance = hash_values[i] - hash_values[j]
            if distance < args.threshold:
                # j is a duplicate of i — keep i, mark j
                seen.add(paths[j])
                rel_j = os.path.relpath(paths[j], training_data)
                rel_i = os.path.relpath(paths[i], training_data)
                duplicates.append({
                    "duplicate": rel_j,
                    "original": rel_i,
                    "distance": distance
                })
                duplicate_groups[rel_i].append(rel_j)

    print(f"Found {len(duplicates)} duplicate images")
    if duplicates:
        print(f"Unique images with duplicates: {len(duplicate_groups)}")
        print()

        # Show top duplicate groups
        top_groups = sorted(duplicate_groups.items(), key=lambda x: -len(x[1]))[:10]
        for original, dupes in top_groups:
            print(f"  {original} has {len(dupes)} duplicates")
            for d in dupes[:3]:
                print(f"    -> {d}")
            if len(dupes) > 3:
                print(f"    ... and {len(dupes) - 3} more")

    # Per-faction summary
    faction_dupes = defaultdict(int)
    for entry in duplicates:
        parts = entry["duplicate"].split(os.sep)
        if len(parts) >= 1:
            faction_dupes[parts[0]] += 1

    if faction_dupes:
        print()
        print("Per-faction duplicate counts:")
        for faction in sorted(faction_dupes, key=lambda f: -faction_dupes[f]):
            print(f"  {faction}: {faction_dupes[faction]}")

    # Write output
    if not args.dry_run:
        # Simple blocklist: just the duplicate relative paths
        blocklist = [entry["duplicate"] for entry in duplicates]

        output_data = {
            "threshold": args.threshold,
            "total_scanned": len(all_images),
            "total_duplicates": len(duplicates),
            "blocklist": blocklist,
            "details": duplicates
        }

        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)

        print(f"\nBlocklist written to: {output_path}")
        print(f"Backend can load this file to exclude {len(blocklist)} duplicate images from annotation queues.")
    else:
        print("\n(dry run — no file written)")

if __name__ == "__main__":
    main()
