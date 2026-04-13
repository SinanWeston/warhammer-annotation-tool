#!/usr/bin/env python3
"""
Flickr Tag-Search Scraper for Battle Scanner Training Data

Searches Flickr by faction-specific tags using the REST API, downloads images
sorted by interestingness, and appends to the shared scrape_log.csv.

Credentials (from .env or environment):
    FLICKR_API_KEY
    FLICKR_API_SECRET

Usage:
    python scripts/flickr_collector.py --faction necrons --limit 100 --dry-run
    python scripts/flickr_collector.py --faction necrons --limit 100
    python scripts/flickr_collector.py --all --limit 100
    python scripts/flickr_collector.py --list-factions
    python scripts/flickr_collector.py --faction necrons --tags "necrons warhammer" "necron miniature"
"""

import argparse
import csv
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from scraper_utils import (
    OUTPUT_DIR, SCRAPE_LOG,
    init_csv, load_known_hashes, log_image,
    now_iso, quality_check_bytes, rand_delay, save_hash,
)

# ─── Faction Tag Map ──────────────────────────────────────────────────────────

FACTION_TAG_MAP = {
    "space_marines":       ["space marines 40k", "astartes miniature warhammer"],
    "necrons":             ["necrons 40k", "necron miniature warhammer"],
    "orks":                ["orks warhammer 40k", "ork boyz miniature"],
    "tyranids":            ["tyranids 40k", "tyranid miniature warhammer"],
    "tau_empire":          ["tau empire 40k", "tau miniature warhammer"],
    "aeldari":             ["aeldari 40k", "eldar miniature warhammer"],
    "astra_militarum":     ["astra militarum 40k", "imperial guard miniature"],
    "adepta_sororitas":    ["sisters of battle 40k", "adepta sororitas miniature"],
    "adeptus_mechanicus":  ["adeptus mechanicus 40k", "admech miniature warhammer"],
    "adeptus_custodes":    ["adeptus custodes 40k", "custodes miniature warhammer"],
    "chaos_space_marines": ["chaos space marines 40k", "chaos marines miniature"],
    "death_guard":         ["death guard 40k", "nurgle marines miniature"],
    "thousand_sons":       ["thousand sons 40k", "tzeentch marines miniature"],
    "world_eaters":        ["world eaters 40k", "khorne berzerkers miniature"],
    "emperors_children":   ["emperors children 40k", "slaanesh marines miniature"],
    "genestealer_cults":   ["genestealer cult 40k", "genestealer miniature warhammer"],
    "imperial_knights":    ["imperial knights 40k", "knight miniature warhammer"],
    "chaos_knights":       ["chaos knights 40k", "war dog miniature warhammer"],
    "leagues_of_votann":   ["leagues of votann 40k", "votann miniature warhammer"],
    "drukhari":            ["drukhari 40k", "dark eldar miniature warhammer"],
}

MAX_PAGES = 10
API_DELAY = 1.0   # seconds between API requests (3600/hour limit → very safe)


# ─── Env / Credentials ───────────────────────────────────────────────────────

def load_env():
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass


def make_flickr():
    try:
        import flickrapi
    except ImportError:
        print("ERROR: flickrapi is not installed. Run: pip install flickrapi")
        sys.exit(1)

    api_key = os.environ.get("FLICKR_API_KEY", "")
    api_secret = os.environ.get("FLICKR_API_SECRET", "")
    if not api_key or not api_secret:
        print("ERROR: FLICKR_API_KEY and FLICKR_API_SECRET must be set.")
        sys.exit(1)

    return flickrapi.FlickrAPI(api_key, api_secret, format="parsed-json")


# ─── Resumability ─────────────────────────────────────────────────────────────

def load_scraped_flickr_ids() -> set:
    ids = set()
    if not SCRAPE_LOG.exists():
        return ids
    with open(SCRAPE_LOG, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("source_platform") == "flickr":
                url = row.get("page_url", "")
                # page_url format: https://www.flickr.com/photos/{owner}/{photo_id}/
                parts = url.rstrip("/").split("/")
                if parts:
                    ids.add(parts[-1])
    return ids


# ─── Download ─────────────────────────────────────────────────────────────────

def get_photo_url(flickr, photo: dict) -> str | None:
    """Return the best available direct URL for a Flickr photo."""
    # url_l = large (1024px), url_o = original
    url = photo.get("url_l") or photo.get("url_o")
    if url:
        return url

    # Fall back to getSizes API call
    try:
        time.sleep(API_DELAY)
        sizes = flickr.photos.getSizes(photo_id=photo["id"])
        size_list = sizes.get("sizes", {}).get("size", [])
        if not size_list:
            return None
        # Sort by area descending, pick largest
        def area(s):
            try:
                return int(s.get("width", 0)) * int(s.get("height", 0))
            except (ValueError, TypeError):
                return 0
        best = max(size_list, key=area)
        return best.get("source")
    except Exception:
        return None


def download_image(url: str, known_hashes: set) -> tuple[bytes, int, int, str] | None:
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "BattleScanner/1.0"})
        if resp.status_code != 200:
            return None
    except requests.RequestException:
        return None
    return quality_check_bytes(resp.content, known_hashes)


# ─── Main Scraping Logic ──────────────────────────────────────────────────────

def scrape_faction(
    flickr,
    faction_slug: str,
    tags: list[str],
    limit: int,
    known_hashes: set,
    scraped_ids: set,
    dry_run: bool = False,
) -> int:
    out_dir = OUTPUT_DIR / faction_slug / "flickr"

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    saved = 0
    print(f"\n  {faction_slug}  tags={tags}")

    if dry_run:
        print(f"  [DRY RUN] Would search Flickr for: {tags}")
        return 0

    for tag_query in tags:
        if saved >= limit:
            break

        print(f"  Searching Flickr: \"{tag_query}\"")

        for page in range(1, MAX_PAGES + 1):
            if saved >= limit:
                break

            try:
                time.sleep(API_DELAY)
                result = flickr.photos.search(
                    tags=tag_query,
                    extras="url_l,url_o",
                    sort="interestingness-desc",
                    per_page=100,
                    page=page,
                    safe_search=1,
                )
            except Exception as e:
                print(f"    Flickr API error: {e}")
                break

            photos = result.get("photos", {})
            photo_list = photos.get("photo", [])

            if not photo_list:
                break

            total_pages = photos.get("pages", 1)
            if page == 1:
                total = photos.get("total", "?")
                print(f"    {total} total results, {total_pages} pages")

            for idx, photo in enumerate(photo_list):
                if saved >= limit:
                    break

                photo_id = photo["id"]
                if photo_id in scraped_ids:
                    continue

                img_url = get_photo_url(flickr, photo)
                if not img_url:
                    continue

                result_dl = download_image(img_url, known_hashes)
                time.sleep(API_DELAY)

                if result_dl is None:
                    continue

                jpg_data, w, h, fhash = result_dl
                known_hashes.add(fhash)
                save_hash(fhash)
                scraped_ids.add(photo_id)

                owner = photo.get("owner", "unknown")
                page_url = f"https://www.flickr.com/photos/{owner}/{photo_id}/"
                fname = f"{faction_slug}_flickr_{photo_id}_{saved:03d}.jpg"
                (out_dir / fname).write_bytes(jpg_data)
                saved += 1

                log_image({
                    "filename": fname,
                    "unit_name": "",
                    "faction": faction_slug,
                    "image_type": "faction_scene",
                    "source_url": img_url,
                    "page_url": page_url,
                    "source_platform": "flickr",
                    "width_px": w,
                    "height_px": h,
                    "file_hash": fhash,
                    "search_query": tag_query,
                    "timestamp": now_iso(),
                })

            if page >= total_pages:
                break

    print(f"  Done: {saved} new images for {faction_slug}")
    return saved


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scrape Flickr for Warhammer 40K miniature images by faction"
    )
    parser.add_argument("--faction", metavar="SLUG", help="Faction slug (e.g. necrons)")
    parser.add_argument("--all", action="store_true", help="Scrape all factions in FACTION_TAG_MAP")
    parser.add_argument("--limit", type=int, default=100, help="Max images per faction (default: 100)")
    parser.add_argument("--tags", nargs="+", metavar="TAG", help="Override tags for --faction")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list-factions", action="store_true")
    args = parser.parse_args()

    if args.list_factions:
        print("\nFaction → Tags:")
        for faction, tags in FACTION_TAG_MAP.items():
            print(f"  {faction:30s} {tags}")
        return

    if not args.all and not args.faction:
        parser.print_help()
        sys.exit(1)

    load_env()

    if args.all:
        targets = list(FACTION_TAG_MAP.items())
    else:
        if args.faction not in FACTION_TAG_MAP and not args.tags:
            print(f"Unknown faction '{args.faction}'. Use --list-factions or provide --tags.")
            sys.exit(1)
        tags = args.tags or FACTION_TAG_MAP[args.faction]
        targets = [(args.faction, tags)]

    init_csv()
    known_hashes = load_known_hashes()
    scraped_ids = load_scraped_flickr_ids()
    flickr = make_flickr()

    print("=" * 60)
    print("Flickr Collector")
    print(f"Factions: {len(targets)}")
    print(f"Limit per faction: {args.limit}")
    print(f"Dry run: {args.dry_run}")
    print(f"Known hashes: {len(known_hashes)}")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 60)

    grand_total = 0
    try:
        for faction_slug, tags in targets:
            n = scrape_faction(
                flickr=flickr,
                faction_slug=faction_slug,
                tags=tags,
                limit=args.limit,
                known_hashes=known_hashes,
                scraped_ids=scraped_ids,
                dry_run=args.dry_run,
            )
            grand_total += n
    except KeyboardInterrupt:
        print("\n\nInterrupted. Progress is saved — safe to resume.")

    print(f"\n{'='*60}")
    print(f"DONE. Total new images: {grand_total}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Log: {SCRAPE_LOG}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
