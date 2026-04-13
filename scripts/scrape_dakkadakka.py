#!/usr/bin/env python3
"""
DakkaDakka Gallery Scraper for Battle Scanner Training Data

Server-rendered HTML — no Playwright needed. Uses requests + BeautifulSoup.
Sorts by paintjob rating (sort1=pr) to get highest-quality images first.

Shares the same output directory and metadata CSV as scrape_ebay.py.

Usage:
    python scrape_dakkadakka.py --faction space_marines --unit "Intercessor Squad" --limit 15 --dry-run
    python scrape_dakkadakka.py --faction necrons --limit 15
    python scrape_dakkadakka.py --all --limit 15
    python scrape_dakkadakka.py --list-factions
    python scrape_dakkadakka.py --list-units space_marines
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
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image

# ─── Configuration ───────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
UNITS_JSON = BASE_DIR / "scripts" / "data" / "units.json"
OUTPUT_DIR = BASE_DIR / "training_data_v2"
METADATA_DIR = OUTPUT_DIR / "metadata"
SCRAPE_LOG = METADATA_DIR / "scrape_log.csv"
DUPLICATES_FILE = METADATA_DIR / "duplicates.txt"

DAKKA_BASE = "https://www.dakkadakka.com"
DAKKA_SEARCH = "https://www.dakkadakka.com/core/gallery-search.jsp"

RESULTS_PER_PAGE = 30
MAX_PAGES = 10          # Max pages to scrape per query (300 images max per query)

MIN_WIDTH = 400
MIN_HEIGHT = 400
MIN_FILE_SIZE = 15 * 1024       # 15 KB
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
MAX_ASPECT_RATIO = 5.0
JPEG_QUALITY = 92

SEARCH_DELAY = (3.0, 6.0)   # (min, max) seconds between search page fetches
DETAIL_DELAY = 1.0           # seconds between detail page fetches
IMAGE_DELAY = 0.5            # seconds between image downloads

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]


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


def load_scraped_dakka_ids() -> set:
    """Load image IDs already scraped from DakkaDakka (from scrape_log.csv)."""
    ids = set()
    if SCRAPE_LOG.exists():
        with open(SCRAPE_LOG, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("source_platform") == "dakkadakka":
                    src = row.get("source_url", "")
                    m = re.search(r"/(\d+)_(?:mb|th|tb)-", src)
                    if m:
                        ids.add(m.group(1))
    return ids


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


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "DNT": "1",
    })
    return session


# ─── DakkaDakka Fetch & Parse ────────────────────────────────────────────────

def fetch_search_page(session: requests.Session, query: str, start: int = 0, min_paintjob: int = 4) -> BeautifulSoup | None:
    """Fetch one page of DakkaDakka gallery search results.

    Uses dq= (the actual form field name), sort1=1 (paintjob best-to-worst),
    and paintjoblow filter to get only well-painted models.
    """
    params = {
        "dq": query,
        "sort1": "1",       # Paintjob rating (best to worst)
        "start": str(start),
        "skip": str(RESULTS_PER_PAGE),
    }
    if min_paintjob > 0:
        params["paintjoblow"] = str(min_paintjob)
    url = DAKKA_SEARCH + "?" + "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items())

    for attempt in range(3):
        try:
            resp = session.get(url, timeout=20)
            if resp.status_code == 200:
                return BeautifulSoup(resp.text, "html.parser")
            elif resp.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"    Rate limited. Waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"    HTTP {resp.status_code} for search page")
                return None
        except requests.RequestException as e:
            print(f"    Request error (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(5)

    return None


def parse_image_entries(soup: BeautifulSoup) -> list[dict]:
    """Extract image info from a DakkaDakka gallery search results page."""
    entries = []

    for td in soup.find_all("td", class_="row1"):
        img_tag = td.find("img")
        link_tag = td.find("a", href=re.compile(r"^/gallery/\d+"))
        if not img_tag or not link_tag:
            continue

        img_src = img_tag.get("src", "")
        if not img_src or "dakkadakka.com" not in img_src:
            continue

        # Extract image ID from URL (e.g. .../1234137_mb-title.png)
        id_match = re.search(r"/(\d+)_(?:mb|th|tb)-", img_src)
        if not id_match:
            continue
        image_id = id_match.group(1)

        detail_href = link_tag.get("href", "")
        detail_url = urljoin(DAKKA_BASE, detail_href)

        entries.append({
            "image_id": image_id,
            "thumbnail_url": img_src,
            "detail_url": detail_url,
        })

    return entries


def get_total_results(soup: BeautifulSoup) -> int:
    """Parse total result count from search page."""
    text = soup.get_text()
    m = re.search(r"([\d,]+)\s+images?\s+found", text)
    if m:
        return int(m.group(1).replace(",", ""))
    return 0


def get_fullsize_url(session: requests.Session, detail_url: str) -> str | None:
    """
    Visit the DakkaDakka gallery detail page and return the full-size image URL.
    The _mb- thumbnails are only 320px wide; full-size is 900px+ and necessary
    for training data quality.
    """
    try:
        resp = session.get(detail_url, timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        # The first dakkadakka image on the detail page without _th- or _mb- is the full-size
        for img in soup.find_all("img", src=re.compile(r"images\.dakkadakka\.com")):
            src = img.get("src", "")
            if "_th-" not in src and "_mb-" not in src and "_tb-" not in src:
                return src
        # Fallback: take the largest img URL we can find
        for img in soup.find_all("img", src=re.compile(r"images\.dakkadakka\.com")):
            src = img.get("src", "")
            if "_mb-" in src:
                return src
        return None
    except requests.RequestException:
        return None


# ─── Image Download ────────────────────────────────────────────────────────

def download_image(image_url: str, session: requests.Session, known_hashes: set) -> tuple[bytes, int, int, str] | None:
    """Download and validate an image. Returns (jpg_bytes, w, h, hash) or None."""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": "https://www.dakkadakka.com/",
    }
    try:
        resp = requests.get(image_url, timeout=20, headers=headers)
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


# ─── Main Scraping Logic ─────────────────────────────────────────────────────

def scrape_unit(
    session: requests.Session,
    faction_slug: str,
    faction_name: str,
    unit_name: str,
    search_queries: list[str],
    image_type: str,
    limit: int,
    known_hashes: set,
    scraped_ids: set,
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

    # Count existing DakkaDakka images specifically (don't double-count eBay)
    existing_dakka = len(list(out_dir.glob(f"*_dakka_*.jpg"))) if out_dir.exists() else 0
    if existing_dakka >= limit:
        print(f"  Already have {existing_dakka}/{limit} DakkaDakka images, skipping")
        return 0

    remaining = limit - existing_dakka
    saved = 0

    for query in search_queries:
        if saved >= remaining:
            break

        print(f"  Searching DakkaDakka: \"{query}\"")

        if dry_run:
            print(f"    [DRY RUN] Would search DakkaDakka")
            rand_delay(SEARCH_DELAY)
            continue

        # Try with paintjob>=4 filter first; fall back to unfiltered for rare units
        for min_pj in [4, 0]:
            if saved >= remaining:
                break

            if min_pj == 0:
                print(f"    Retrying without paintjob filter (rare unit)")

            query_saved_before = saved

            # Paginate through results
            for page in range(MAX_PAGES):
                if saved >= remaining:
                    break

                start = page * RESULTS_PER_PAGE
                soup = fetch_search_page(session, query, start, min_paintjob=min_pj)
                if not soup:
                    break

                if page == 0:
                    total = get_total_results(soup)
                    label = f" (paintjob≥{min_pj})" if min_pj else ""
                    print(f"    {total:,} total results{label}")

                entries = parse_image_entries(soup)
                if not entries:
                    break

                print(f"    Page {page+1}: {len(entries)} entries")
                rand_delay(SEARCH_DELAY)

                for entry in entries:
                    if saved >= remaining:
                        break

                    image_id = entry["image_id"]
                    if image_id in scraped_ids:
                        continue

                    img_url = get_fullsize_url(session, entry["detail_url"])
                    time.sleep(DETAIL_DELAY)
                    if img_url is None:
                        continue

                    result = download_image(img_url, session, known_hashes)
                    time.sleep(IMAGE_DELAY)

                    if result is None:
                        continue

                    jpg_data, w, h, fhash = result
                    known_hashes.add(fhash)
                    save_hash(fhash)
                    scraped_ids.add(image_id)

                    # Counter to make filenames unique per unit
                    idx = existing_dakka + saved
                    fname = f"{faction_slug}_{unit_slug}_dakka_{image_id}_{idx:03d}.jpg"
                    (out_dir / fname).write_bytes(jpg_data)
                    saved += 1

                    log_image({
                        "filename": fname, "unit_name": unit_name,
                        "faction": faction_slug, "image_type": image_type,
                        "source_url": img_url, "page_url": entry["detail_url"],
                        "source_platform": "dakkadakka", "width_px": w, "height_px": h,
                        "file_hash": fhash, "search_query": query,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

                # If fewer results than a full page, no point fetching next page
                if len(entries) < RESULTS_PER_PAGE:
                    break

            # If we got enough from the filtered pass, skip the unfiltered pass
            if saved - query_saved_before >= remaining // 2:
                break

    total_dakka = existing_dakka + saved
    print(f"  Total DakkaDakka: {total_dakka}/{limit} images for {unit_name}")
    return saved


def build_dakka_queries(unit_name: str, faction_name: str) -> list[str]:
    """Build 2-3 DakkaDakka search queries for a unit."""
    # DakkaDakka searches within the Warhammer 40K tag, so keep queries tight
    queries = [
        unit_name,
        f"{unit_name} {faction_name}",
    ]
    # Deduplicate while preserving order
    seen = set()
    result = []
    for q in queries:
        if q.lower() not in seen:
            seen.add(q.lower())
            result.append(q)
    return result


def scrape_faction(
    session: requests.Session,
    faction_slug: str,
    faction_data: dict,
    limit: int,
    known_hashes: set,
    scraped_ids: set,
    dry_run: bool = False,
    unit_filter: str | None = None,
    combat_patrol_only: bool = False,
) -> int:
    faction_name = faction_data["name"]
    total_saved = 0

    # 1. Combat Patrol group shots (skip when filtering to a specific unit)
    cp = faction_data.get("combat_patrol", {})
    if cp and not unit_filter:
        print(f"\n  --- Combat Patrol: {cp.get('box_name', faction_name)} ---")
        cp_queries = [
            f"Combat Patrol {faction_name}",
            f"{cp.get('box_name', 'Combat Patrol ' + faction_name)}",
        ]
        n = scrape_unit(
            session, faction_slug, faction_name,
            f"Combat Patrol {faction_name}",
            cp_queries,
            "combat_patrol", limit=20,
            known_hashes=known_hashes,
            scraped_ids=scraped_ids,
            dry_run=dry_run,
        )
        total_saved += n

    if combat_patrol_only:
        return total_saved

    # 2. Unit isolation shots
    for unit in faction_data.get("units", []):
        name = unit["name"]
        if unit_filter and slugify(unit_filter) != slugify(name):
            continue

        print(f"\n  --- {name} ({unit.get('category', '?')}) ---")
        queries = build_dakka_queries(name, faction_name)
        n = scrape_unit(
            session, faction_slug, faction_name,
            name, queries, "isolation",
            limit=limit,
            known_hashes=known_hashes,
            scraped_ids=scraped_ids,
            dry_run=dry_run,
        )
        total_saved += n

    return total_saved


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape DakkaDakka for Warhammer 40K miniature images")
    parser.add_argument("--faction", type=str, help="Faction slug (e.g. space_marines)")
    parser.add_argument("--unit", type=str, help="Specific unit name")
    parser.add_argument("--all", action="store_true", help="Scrape all factions")
    parser.add_argument("--combat-patrol-only", action="store_true", help="Only Combat Patrol shots")
    parser.add_argument("--limit", type=int, default=15, help="Max DakkaDakka images per unit (default: 15)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be scraped")
    parser.add_argument("--list-factions", action="store_true")
    parser.add_argument("--list-units", type=str, metavar="FACTION")
    args = parser.parse_args()

    with open(UNITS_JSON) as f:
        db = json.load(f)
    factions = db["factions"]

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
    scraped_ids = load_scraped_dakka_ids()

    print("=" * 60)
    print("DakkaDakka Gallery Scraper")
    print(f"Factions: {len(target_factions)}")
    print(f"Limit per unit: {args.limit}")
    print(f"Dry run: {args.dry_run}")
    print(f"Known hashes: {len(known_hashes)}")
    print(f"Already-scraped DakkaDakka IDs: {len(scraped_ids)}")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 60)

    session = make_session()
    grand_total = 0

    try:
        for faction_slug in target_factions:
            faction_data = factions[faction_slug]
            print(f"\n{'='*60}")
            print(f"FACTION: {faction_data['name']} ({len(faction_data.get('units', []))} units)")
            print(f"{'='*60}")

            n = scrape_faction(
                session, faction_slug, faction_data,
                limit=args.limit,
                known_hashes=known_hashes,
                scraped_ids=scraped_ids,
                dry_run=args.dry_run,
                unit_filter=args.unit,
                combat_patrol_only=args.combat_patrol_only,
            )
            grand_total += n
            print(f"\n  Faction total: {n} new images")

            # Rotate user agent between factions
            session = make_session()

    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Progress is saved — safe to resume.")
    finally:
        session.close()

    print(f"\n{'='*60}")
    print(f"DONE. Total new images: {grand_total}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Log: {SCRAPE_LOG}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
