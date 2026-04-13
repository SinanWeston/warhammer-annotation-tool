#!/usr/bin/env python3
"""
eBay Image Scraper for Battle Scanner Training Data

Uses Playwright (real Chromium browser) to bypass eBay's bot detection,
then downloads images via requests for speed.

Usage:
    python scrape_ebay.py --faction space_marines --unit "Terminator Squad" --limit 5 --dry-run
    python scrape_ebay.py --faction necrons --limit 15
    python scrape_ebay.py --all --limit 15
    python scrape_ebay.py --all --combat-patrol-only
    python scrape_ebay.py --list-factions
    python scrape_ebay.py --list-units space_marines
"""

import argparse
import csv
import hashlib
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import quote_plus

import requests
from PIL import Image

# ─── Configuration ───────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
UNITS_JSON = BASE_DIR / "scripts" / "data" / "units.json"
OUTPUT_DIR = BASE_DIR / "training_data_v2"
METADATA_DIR = OUTPUT_DIR / "metadata"
SCRAPE_LOG = METADATA_DIR / "scrape_log.csv"
DUPLICATES_FILE = METADATA_DIR / "duplicates.txt"

EBAY_SEARCH_URL = "https://www.ebay.com/sch/i.html"
EBAY_ITEM_BASE = "https://www.ebay.com/itm/"

MIN_WIDTH = 400
MIN_HEIGHT = 400
MIN_FILE_SIZE = 15 * 1024       # 15 KB
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
MAX_ASPECT_RATIO = 5.0
MIN_IMAGES_PER_LISTING = 2
JPEG_QUALITY = 92

SEARCH_DELAY = (5.0, 10.0)   # (min, max) seconds between search queries
LISTING_DELAY = (3.0, 6.0)   # (min, max) seconds between listing page loads
IMAGE_DELAY = 0.3              # seconds between image downloads (no bot detection on CDN)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[''']", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def compute_md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def load_known_hashes() -> set:
    hashes = set()
    if DUPLICATES_FILE.exists():
        with open(DUPLICATES_FILE) as f:
            for line in f:
                h = line.strip()
                if h:
                    hashes.add(h)
    return hashes


def save_hash(file_hash: str):
    with open(DUPLICATES_FILE, "a") as f:
        f.write(file_hash + "\n")


def load_scraped_listings() -> set:
    scraped = set()
    if SCRAPE_LOG.exists():
        with open(SCRAPE_LOG, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                match = re.search(r"/itm/(\d+)", row.get("page_url", ""))
                if match:
                    scraped.add(match.group(1))
    return scraped


def init_csv():
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SCRAPE_LOG.exists():
        with open(SCRAPE_LOG, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "filename", "unit_name", "faction", "image_type",
                "source_url", "page_url", "source_platform",
                "width_px", "height_px", "file_hash",
                "search_query", "timestamp"
            ])


def log_image(row: dict):
    with open(SCRAPE_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            row["filename"], row["unit_name"], row["faction"],
            row["image_type"], row["source_url"], row["page_url"],
            row["source_platform"], row["width_px"], row["height_px"],
            row["file_hash"], row["search_query"], row["timestamp"]
        ])


def rand_delay(delay_range: tuple):
    time.sleep(random.uniform(*delay_range))


# ─── Browser Manager ────────────────────────────────────────────────────────

class EbayBrowser:
    """Manages a Playwright Chromium browser for eBay scraping."""

    def __init__(self, headless: bool = False):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        self._page = self._context.new_page()
        # Visit eBay homepage first to establish cookies
        print("  Initialising browser session...")
        self._page.goto("https://www.ebay.com/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        print("  Browser ready.")

    def get_page_content(self, url: str, wait_ms: int = 3000) -> str:
        """Navigate to URL and return page HTML after JS renders."""
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._page.wait_for_timeout(wait_ms)
            return self._page.content()
        except Exception as e:
            print(f"    Browser error: {e}")
            return ""

    def close(self):
        try:
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass


# ─── eBay Search & Extraction ───────────────────────────────────────────────

def search_ebay(browser: EbayBrowser, query: str, max_listings: int = 20) -> list[dict]:
    """Search eBay via browser. Returns list of {"url": str, "listing_id": str}."""
    params = {"_nkw": query, "LH_BIN": "1", "_sop": "12"}
    url = f"{EBAY_SEARCH_URL}?{'&'.join(f'{k}={quote_plus(str(v))}' for k, v in params.items())}"

    content = browser.get_page_content(url)
    if not content or "Pardon Our Interruption" in content:
        print("    eBay challenge page — waiting 30s and retrying...")
        time.sleep(30)
        content = browser.get_page_content(url)
        if not content or "Pardon Our Interruption" in content:
            print("    Still blocked, skipping this search.")
            return []

    seen_ids = set()
    listings = []
    for match in re.finditer(r'/itm/(\d{10,})', content):
        lid = match.group(1)
        if lid not in seen_ids:
            seen_ids.add(lid)
            listings.append({"url": f"{EBAY_ITEM_BASE}{lid}", "listing_id": lid})
            if len(listings) >= max_listings:
                break
    return listings


def extract_listing_images(browser: EbayBrowser, listing_url: str) -> list[str]:
    """Extract high-res image URLs from an eBay listing page via browser."""
    content = browser.get_page_content(listing_url, wait_ms=2000)
    if not content:
        return []

    image_urls = set()
    # Extract ebayimg URLs with clean regex (hash chars + size suffix)
    for match in re.finditer(
        r'(https?://i\.ebayimg\.com/images/g/[A-Za-z0-9~_-]+/s-l\d+\.\w+)', content
    ):
        url = match.group(1)
        url = re.sub(r'/s-l\d+\.', '/s-l1600.', url)
        image_urls.add(url)

    # Filter out tiny thumbnails
    return [u for u in image_urls if "/s-l64." not in u and "/s-l96." not in u and "/s-l140." not in u]


# ─── Image Download (plain requests — eBay CDN doesn't block) ───────────────

def download_image(image_url: str, known_hashes: set) -> tuple[bytes, int, int, str] | None:
    """Download and validate an image. Returns (jpg_bytes, w, h, hash) or None."""
    try:
        resp = requests.get(image_url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        if resp.status_code != 200:
            return None
    except requests.RequestException:
        return None

    data = resp.content
    if len(data) < MIN_FILE_SIZE or len(data) > MAX_FILE_SIZE:
        return None

    file_hash = compute_md5(data)
    if file_hash in known_hashes:
        return None

    try:
        img = Image.open(BytesIO(data))
        img.verify()
        img = Image.open(BytesIO(data))
        w, h = img.size
    except Exception:
        return None

    if w < MIN_WIDTH or h < MIN_HEIGHT:
        return None
    if max(w, h) / max(min(w, h), 1) > MAX_ASPECT_RATIO:
        return None

    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    jpg_data = buf.getvalue()

    file_hash = compute_md5(jpg_data)
    if file_hash in known_hashes:
        return None

    return (jpg_data, w, h, file_hash)


# ─── Main Scraping Logic ────────────────────────────────────────────────────

def scrape_unit(
    browser: EbayBrowser,
    faction_slug: str,
    faction_name: str,
    unit_name: str,
    search_templates: list[str],
    image_type: str,
    limit: int,
    known_hashes: set,
    scraped_listings: set,
    dry_run: bool = False,
) -> int:
    unit_slug = slugify(unit_name)
    out_dir = (
        OUTPUT_DIR / faction_slug / "combat_patrol"
        if image_type == "combat_patrol"
        else OUTPUT_DIR / faction_slug / "isolation" / unit_slug
    )

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    existing = len(list(out_dir.glob("*.jpg"))) if out_dir.exists() else 0
    if existing >= limit:
        print(f"  Already have {existing}/{limit} images, skipping")
        return 0

    remaining = limit - existing
    saved = 0

    queries = [t.replace("{unit}", unit_name).replace("{faction}", faction_name) for t in search_templates]

    for query in queries:
        if saved >= remaining:
            break

        print(f"  Searching: \"{query}\"")

        if dry_run:
            print(f"    [DRY RUN] Would search eBay")
            rand_delay(SEARCH_DELAY)
            continue

        listings = search_ebay(browser, query, max_listings=20)
        print(f"    Found {len(listings)} listings")
        rand_delay(SEARCH_DELAY)

        for listing in listings:
            if saved >= remaining:
                break

            lid = listing["listing_id"]
            if lid in scraped_listings:
                continue

            print(f"    Listing {lid}...")
            images = extract_listing_images(browser, listing["url"])
            rand_delay(LISTING_DELAY)

            if len(images) < MIN_IMAGES_PER_LISTING:
                print(f"      Only {len(images)} images, skipping")
                continue

            listing_saved = 0
            for idx, img_url in enumerate(images):
                if saved >= remaining:
                    break

                result = download_image(img_url, known_hashes)
                if result is None:
                    continue

                jpg_data, w, h, fhash = result
                known_hashes.add(fhash)
                save_hash(fhash)

                fname = f"{faction_slug}_{unit_slug}_ebay_{lid}_{idx:02d}.jpg"
                (out_dir / fname).write_bytes(jpg_data)
                saved += 1
                listing_saved += 1

                log_image({
                    "filename": fname, "unit_name": unit_name,
                    "faction": faction_slug, "image_type": image_type,
                    "source_url": img_url, "page_url": listing["url"],
                    "source_platform": "ebay", "width_px": w, "height_px": h,
                    "file_hash": fhash, "search_query": query,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                time.sleep(IMAGE_DELAY)

            scraped_listings.add(lid)
            print(f"      Saved {listing_saved} images")

    total = existing + saved
    print(f"  Total: {total}/{limit} images for {unit_name}")
    return saved


def count_existing_isolation(faction_slug: str) -> int:
    """Count isolation images already on disk for a faction."""
    iso_dir = OUTPUT_DIR / faction_slug / "isolation"
    if not iso_dir.exists():
        return 0
    return sum(1 for f in iso_dir.rglob("*.jpg"))


def scrape_faction(
    browser: EbayBrowser,
    faction_slug: str,
    faction_data: dict,
    search_templates: dict,
    limit: int,
    known_hashes: set,
    scraped_listings: set,
    dry_run: bool = False,
    unit_filter: str | None = None,
    combat_patrol_only: bool = False,
    isolation_only: bool = False,
    faction_limit: int | None = None,
) -> int:
    faction_name = faction_data["name"]
    total_saved = 0

    # Track faction-level cap
    faction_existing = count_existing_isolation(faction_slug) if faction_limit else 0
    faction_remaining = (faction_limit - faction_existing) if faction_limit else None
    if faction_remaining is not None and faction_remaining <= 0:
        print(f"  Already have {faction_existing}/{faction_limit} isolation images, skipping faction")
        return 0

    # 1. Combat Patrol group shots
    if not isolation_only:
        cp = faction_data.get("combat_patrol", {})
        if cp:
            print(f"\n  --- Combat Patrol: {cp.get('box_name', faction_name)} ---")
            n = scrape_unit(
                browser, faction_slug, faction_name,
                f"Combat Patrol {faction_name}",
                search_templates.get("combat_patrol", []),
                "combat_patrol", limit=20,
                known_hashes=known_hashes,
                scraped_listings=scraped_listings,
                dry_run=dry_run,
            )
            total_saved += n

    if combat_patrol_only:
        return total_saved

    # 2. Unit isolation shots
    iso_templates = search_templates.get("isolation", [])
    for unit in faction_data.get("units", []):
        name = unit["name"]
        if unit_filter and slugify(unit_filter) != slugify(name):
            continue

        # Stop if faction cap reached
        if faction_remaining is not None:
            faction_remaining -= 0  # recalc from disk each unit for accuracy
            current = count_existing_isolation(faction_slug)
            if current >= faction_limit:
                print(f"  Faction limit {faction_limit} reached ({current} images), stopping")
                break
            per_unit_cap = min(limit, faction_limit - current)
        else:
            per_unit_cap = limit

        print(f"\n  --- {name} ({unit.get('category', '?')}) ---")
        n = scrape_unit(
            browser, faction_slug, faction_name,
            name, iso_templates, "isolation",
            limit=per_unit_cap,
            known_hashes=known_hashes,
            scraped_listings=scraped_listings,
            dry_run=dry_run,
        )
        total_saved += n

    return total_saved


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape eBay for Warhammer 40K miniature images")
    parser.add_argument("--faction", type=str, help="Faction slug (e.g. space_marines)")
    parser.add_argument("--unit", type=str, help="Specific unit name")
    parser.add_argument("--all", action="store_true", help="Scrape all factions")
    parser.add_argument("--combat-patrol-only", action="store_true", help="Only Combat Patrol shots")
    parser.add_argument("--isolation-only", action="store_true", help="Only isolation unit shots (skip combat patrol)")
    parser.add_argument("--limit", type=int, default=15, help="Max images per unit (default: 15)")
    parser.add_argument("--faction-limit", type=int, default=None, help="Max total isolation images per faction")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be scraped")
    parser.add_argument("--headless", action="store_true", help="Run browser headless (may get blocked)")
    parser.add_argument("--list-factions", action="store_true")
    parser.add_argument("--list-units", type=str, metavar="FACTION")
    args = parser.parse_args()

    with open(UNITS_JSON) as f:
        db = json.load(f)
    factions = db["factions"]
    search_templates = db["search_templates"]

    if args.list_factions:
        for slug, data in factions.items():
            print(f"  {slug:30s} {data['name']:30s} ({len(data.get('units', []))} units)")
        return

    if args.list_units:
        faction = factions.get(args.list_units)
        if not faction:
            print(f"Unknown faction. Available: {', '.join(factions.keys())}")
            sys.exit(1)
        print(f"\n{faction['name']} — {len(faction['units'])} units:\n")
        for u in faction["units"]:
            print(f"  [{u.get('category', '?'):12s}] {u['name']}")
        print(f"\nCombat Patrol: {', '.join(faction['combat_patrol']['contents'])}")
        return

    if not args.all and not args.faction:
        parser.print_help()
        sys.exit(1)

    target_factions = list(factions.keys()) if args.all else [args.faction]
    if not args.all and args.faction not in factions:
        print(f"Unknown faction. Available: {', '.join(factions.keys())}")
        sys.exit(1)

    init_csv()
    known_hashes = load_known_hashes()
    scraped_listings = load_scraped_listings()

    print("=" * 60)
    print("eBay Miniature Scraper (Playwright)")
    print(f"Factions: {len(target_factions)}")
    print(f"Limit per unit: {args.limit}")
    print(f"Dry run: {args.dry_run}")
    print(f"Known hashes: {len(known_hashes)}")
    print(f"Scraped listings: {len(scraped_listings)}")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 60)

    browser = EbayBrowser(headless=args.headless)
    grand_total = 0

    try:
        for faction_slug in target_factions:
            faction_data = factions[faction_slug]
            print(f"\n{'='*60}")
            print(f"FACTION: {faction_data['name']} ({len(faction_data.get('units', []))} units)")
            print(f"{'='*60}")

            n = scrape_faction(
                browser, faction_slug, faction_data, search_templates,
                limit=args.limit,
                known_hashes=known_hashes,
                scraped_listings=scraped_listings,
                dry_run=args.dry_run,
                unit_filter=args.unit,
                combat_patrol_only=args.combat_patrol_only,
                isolation_only=args.isolation_only,
                faction_limit=args.faction_limit,
            )
            grand_total += n
            print(f"\n  Faction total: {n} new images")
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Progress is saved — safe to resume.")
    finally:
        browser.close()

    print(f"\n{'='*60}")
    print(f"DONE. Total new images: {grand_total}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Log: {SCRAPE_LOG}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
