#!/usr/bin/env python3
"""
Scrape candidate reference images for Warhammer 40K unit types.

Reads coverage.json to find units with gaps, then scrapes images from
Bing/Google via icrawler. Applies quality filters (size, blur, aspect ratio,
duplicates) and saves candidates to backend/training_data_candidates/.

Prerequisites:
    pip install icrawler Pillow imagehash opencv-python

Usage:
    # First, generate coverage report
    python scripts/generate_coverage.py

    # Scrape all units with gaps
    python scripts/collect_unit_images.py

    # Scrape a specific faction
    python scripts/collect_unit_images.py --faction tyranids

    # Scrape a specific unit
    python scripts/collect_unit_images.py --faction space_marines --unit intercessors

    # Control candidates per unit (default: 30)
    python scripts/collect_unit_images.py --num 50

    # Dry run (show what would be scraped)
    python scripts/collect_unit_images.py --dry-run
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CANDIDATES_DIR = REPO_ROOT / "backend" / "training_data_candidates"
COVERAGE_JSON = CANDIDATES_DIR / "coverage.json"
CLEAN_REFS_DIR = REPO_ROOT / "backend" / "clean_references"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# Minimum image dimensions
MIN_WIDTH = 300
MIN_HEIGHT = 300
# Maximum aspect ratio (width/height or height/width)
MAX_ASPECT_RATIO = 3.0
# Laplacian variance threshold for blur detection
BLUR_THRESHOLD = 80.0


def build_search_queries(unit_name: str, faction_display: str, faction_aliases: list[str]) -> list[str]:
    """Generate diverse search queries for a unit."""
    queries = [
        f"warhammer 40k {unit_name} miniature painted",
        f"warhammer 40k {unit_name} model",
        f"{faction_display} {unit_name} miniature 40k",
    ]
    # Add alias-based queries
    for alias in faction_aliases[:1]:  # just the first alias
        queries.append(f"warhammer 40k {alias} {unit_name} miniature")
    return queries


def is_good_quality(image_path: str) -> tuple[bool, str]:
    """Check if an image meets quality requirements.

    Returns (is_good, reason_if_rejected).
    """
    try:
        from PIL import Image

        img = Image.open(image_path)
        w, h = img.size

        # Size check
        if w < MIN_WIDTH or h < MIN_HEIGHT:
            return False, f"too small ({w}x{h})"

        # Aspect ratio check
        ratio = max(w / h, h / w)
        if ratio > MAX_ASPECT_RATIO:
            return False, f"bad aspect ratio ({ratio:.1f})"

        # Blur check (requires opencv)
        try:
            import cv2

            cv_img = cv2.imread(image_path)
            if cv_img is not None:
                gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
                fm = cv2.Laplacian(gray, cv2.CV_64F).var()
                if fm < BLUR_THRESHOLD:
                    return False, f"blurry (variance={fm:.1f})"
        except ImportError:
            pass  # cv2 not available, skip blur check

        return True, ""
    except Exception as e:
        return False, f"error: {e}"


def compute_hash(image_path: str) -> str | None:
    """Compute perceptual hash for duplicate detection."""
    try:
        import imagehash
        from PIL import Image

        img = Image.open(image_path)
        return str(imagehash.phash(img))
    except ImportError:
        # Fallback to file hash
        h = hashlib.md5()
        with open(image_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def get_existing_hashes(dest_dir: str) -> set[str]:
    """Get perceptual hashes of existing images in a directory."""
    hashes = set()
    if not os.path.isdir(dest_dir):
        return hashes
    for f in os.listdir(dest_dir):
        if os.path.splitext(f)[1].lower() in IMAGE_EXTS:
            h = compute_hash(os.path.join(dest_dir, f))
            if h:
                hashes.add(h)
    return hashes


def scrape_unit(
    faction: str,
    unit_slug: str,
    unit_name: str,
    faction_display: str,
    faction_aliases: list[str],
    faction_dir: str,
    num_candidates: int = 30,
    existing_accepted: int = 0,
) -> dict:
    """Scrape candidate images for a single unit.

    Returns stats dict.
    """
    dest_dir = str(CANDIDATES_DIR / faction / unit_slug)
    # Already-accepted images live flat in clean_references/{faction_dir}/clean/
    clean_dir = str(CLEAN_REFS_DIR / faction_dir / "clean")
    os.makedirs(dest_dir, exist_ok=True)

    # Count existing candidates
    existing_candidates = sum(
        1 for f in os.listdir(dest_dir) if os.path.splitext(f)[1].lower() in IMAGE_EXTS
    ) if os.path.isdir(dest_dir) else 0

    if existing_candidates >= num_candidates:
        print(f"    Already have {existing_candidates} candidates, skipping scrape")
        return {"downloaded": 0, "accepted": existing_candidates, "filtered": 0}

    # Get hashes of existing accepted + candidate images for dedup
    existing_hashes = get_existing_hashes(clean_dir) | get_existing_hashes(dest_dir)

    queries = build_search_queries(unit_name, faction_display, faction_aliases)
    stats = {"downloaded": 0, "accepted": 0, "filtered": 0, "duplicates": 0}

    # Use a temp dir for raw downloads, then filter into candidates
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Try Bing first, then Google
        for engine_name, crawl_fn in _get_crawlers():
            if stats["accepted"] >= num_candidates:
                break

            for query in queries:
                if stats["accepted"] >= num_candidates:
                    break

                remaining = num_candidates - stats["accepted"]
                # Download more than needed since filtering will remove many
                download_count = min(remaining * 3, 50)

                print(f"    [{engine_name}] Searching: '{query}' (want {remaining} more)")

                try:
                    crawl_fn(query, tmp_dir, download_count)
                except Exception as e:
                    print(f"    [{engine_name}] Search failed: {e}")
                    continue

                # Process downloaded images
                for fname in sorted(os.listdir(tmp_dir)):
                    fpath = os.path.join(tmp_dir, fname)
                    if not os.path.isfile(fpath):
                        continue
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in IMAGE_EXTS:
                        continue

                    stats["downloaded"] += 1

                    # Quality filter
                    is_good, reason = is_good_quality(fpath)
                    if not is_good:
                        stats["filtered"] += 1
                        os.unlink(fpath)
                        continue

                    # Duplicate check
                    img_hash = compute_hash(fpath)
                    if img_hash and img_hash in existing_hashes:
                        stats["duplicates"] += 1
                        os.unlink(fpath)
                        continue

                    if img_hash:
                        existing_hashes.add(img_hash)

                    # Accept candidate
                    idx = existing_candidates + stats["accepted"] + 1
                    new_name = f"{unit_slug}_{idx:03d}{ext}"
                    dest_path = os.path.join(dest_dir, new_name)
                    shutil.move(fpath, dest_path)
                    stats["accepted"] += 1

                    if stats["accepted"] >= num_candidates:
                        break

                # Clean remaining files in tmp
                for f in os.listdir(tmp_dir):
                    fp = os.path.join(tmp_dir, f)
                    if os.path.isfile(fp):
                        os.unlink(fp)

    return stats


def _get_crawlers() -> list[tuple[str, callable]]:
    """Return available image crawlers."""
    crawlers = []

    try:
        from icrawler.builtin import BingImageCrawler

        def bing_crawl(query, output_dir, max_num):
            crawler = BingImageCrawler(
                storage={"root_dir": output_dir},
                log_level=40,  # ERROR only
            )
            crawler.crawl(keyword=query, max_num=max_num)

        crawlers.append(("Bing", bing_crawl))
    except ImportError:
        pass

    try:
        from icrawler.builtin import GoogleImageCrawler

        def google_crawl(query, output_dir, max_num):
            crawler = GoogleImageCrawler(
                storage={"root_dir": output_dir},
                log_level=40,
            )
            crawler.crawl(keyword=query, max_num=max_num)

        crawlers.append(("Google", google_crawl))
    except ImportError:
        pass

    if not crawlers:
        print("ERROR: icrawler is not installed. Install it with:")
        print("  pip install icrawler")
        sys.exit(1)

    return crawlers


def main():
    parser = argparse.ArgumentParser(
        description="Scrape candidate reference images for Warhammer 40K units"
    )
    parser.add_argument("--faction", help="Only scrape this faction")
    parser.add_argument("--unit", help="Only scrape this unit slug")
    parser.add_argument(
        "--num", type=int, default=30, help="Max candidates per unit (default: 30)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be scraped without downloading"
    )
    args = parser.parse_args()

    # Read coverage
    if not COVERAGE_JSON.exists():
        print("ERROR: coverage.json not found. Run generate_coverage.py first:")
        print("  python scripts/generate_coverage.py")
        sys.exit(1)

    with open(COVERAGE_JSON) as f:
        coverage = json.load(f)

    # Filter to units with gaps
    units = [u for u in coverage["units"] if u["gap"] > 0]

    if args.faction:
        units = [u for u in units if u["faction"] == args.faction]
    if args.unit:
        units = [u for u in units if u["slug"] == args.unit]

    if not units:
        print("All units are at target coverage! Nothing to scrape.")
        return

    print(f"\n{'='*60}")
    print(f"  REFERENCE IMAGE SCRAPER")
    print(f"{'='*60}")
    print(f"  Units to scrape: {len(units)}")
    print(f"  Candidates per unit: {args.num}")
    print(f"  Output: {CANDIDATES_DIR}")
    print(f"{'='*60}\n")

    if args.dry_run:
        for u in units:
            queries = build_search_queries(u["name"], u["factionDisplay"], u.get("factionAliases", []))
            print(f"  {u['factionDisplay']} / {u['name']} (need {u['gap']} more)")
            for q in queries:
                print(f"    -> \"{q}\"")
        print(f"\n  Total: {len(units)} units, ~{len(units) * 3} search queries")
        print("  (dry run, nothing downloaded)\n")
        return

    # Verify icrawler is available
    _get_crawlers()

    total_stats = {"downloaded": 0, "accepted": 0, "filtered": 0, "duplicates": 0}

    for i, u in enumerate(units, 1):
        print(f"\n[{i}/{len(units)}] {u['factionDisplay']} / {u['name']} (have {u['accepted']}, need {u['gap']})")

        stats = scrape_unit(
            faction=u["faction"],
            unit_slug=u["slug"],
            unit_name=u["name"],
            faction_display=u["factionDisplay"],
            faction_aliases=u.get("factionAliases", []),
            faction_dir=u.get("factionDir", u["faction"]),
            num_candidates=args.num,
            existing_accepted=u["accepted"],
        )

        for k in total_stats:
            total_stats[k] += stats.get(k, 0)

        print(
            f"    Result: {stats['accepted']} accepted, "
            f"{stats['filtered']} filtered, {stats.get('duplicates', 0)} dupes"
        )

    print(f"\n{'='*60}")
    print(f"  SCRAPING COMPLETE")
    print(f"{'='*60}")
    print(f"  Downloaded:  {total_stats['downloaded']}")
    print(f"  Accepted:    {total_stats['accepted']}")
    print(f"  Filtered:    {total_stats['filtered']}")
    print(f"  Duplicates:  {total_stats['duplicates']}")
    print(f"\n  Next step: review candidates with the Review UI")
    print(f"  Run: python scripts/generate_coverage.py  (to refresh coverage)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
