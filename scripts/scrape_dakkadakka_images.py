"""
DakkaDakka Gallery Scraper for Warhammer 40K Training Data

Scrapes painted miniature images from DakkaDakka's gallery for all 30 factions.
Downloads full-resolution images into backend/training_data/{faction}/dakkadakka/.

Usage:
    python3 scrape_dakkadakka_images.py                    # Scrape all factions needing images
    python3 scrape_dakkadakka_images.py --faction blood_angels --limit 300
    python3 scrape_dakkadakka_images.py --list              # Show faction config
    python3 scrape_dakkadakka_images.py --dry-run            # Preview without downloading

Dependencies:
    pip install requests   (already installed)
"""

import os
import sys
import time
import hashlib
import argparse
import re
import requests
from pathlib import Path
from urllib.parse import urlparse, quote, unquote

# ── Faction → DakkaDakka search config ────────────────────────────────────────
# search_terms: quoted phrases searched via dq= parameter
# min_paintjob: minimum paintjob rating (0-10) to filter quality

FACTION_CONFIG = {
    # -- Factions with existing dakkadakka images (top up) --
    "adeptus_mechanicus": {
        "search_terms": ['"adeptus mechanicus"', '"admech"', '"skitarii"', '"mechanicum"'],
        "display_name": "Adeptus Mechanicus",
    },
    "chaos_space_marines": {
        "search_terms": ['"chaos space marines"', '"chaos marines"', '"heretic astartes"', '"black legion"'],
        "display_name": "Chaos Space Marines",
    },
    "custodes": {
        "search_terms": ['"custodes"', '"adeptus custodes"', '"custodian guard"'],
        "display_name": "Adeptus Custodes",
    },
    "death_guard": {
        "search_terms": ['"death guard"', '"plague marines"', '"poxwalkers"', '"mortarion"'],
        "display_name": "Death Guard",
    },
    "eldar": {
        "search_terms": ['"craftworld"', '"aeldari"', '"eldar"', '"aspect warriors"'],
        "display_name": "Aeldari / Craftworlds",
    },
    "genestealer_cult": {
        "search_terms": ['"genestealer cult"', '"genestealer"', '"brood brothers"'],
        "display_name": "Genestealer Cults",
    },
    "grey_knights": {
        "search_terms": ['"grey knights"', '"grey knight"', '"nemesis"'],
        "display_name": "Grey Knights",
    },
    "imperial_guard": {
        "search_terms": ['"astra militarum"', '"imperial guard"', '"cadian"', '"leman russ"'],
        "display_name": "Astra Militarum",
    },
    "necrons": {
        "search_terms": ['"necrons"', '"necron"', '"dynasty"', '"canoptek"'],
        "display_name": "Necrons",
    },
    "orks": {
        "search_terms": ['"orks" 40k', '"ork" warhammer', '"boyz"', '"waaagh"'],
        "display_name": "Orks",
    },
    "space_marines": {
        "search_terms": ['"space marines"', '"primaris"', '"ultramarines"', '"intercessors"'],
        "display_name": "Space Marines",
    },
    "thousand_sons": {
        "search_terms": ['"thousand sons"', '"rubric marines"', '"magnus"', '"tzeentch marines"'],
        "display_name": "Thousand Sons",
    },
    "tyranids": {
        "search_terms": ['"tyranids"', '"tyranid"', '"hive fleet"', '"carnifex"', '"hormagaunt"'],
        "display_name": "Tyranids",
    },
    # -- Factions that need images (empty or mostly empty) --
    "adepta_sororitas": {
        "search_terms": ['"sisters of battle"', '"adepta sororitas"', '"battle sisters"', '"repentia"'],
        "display_name": "Adepta Sororitas",
    },
    "black_templars": {
        "search_terms": ['"black templars"', '"black templar"', '"emperor\'s champion"'],
        "display_name": "Black Templars",
    },
    "blood_angels": {
        "search_terms": ['"blood angels"', '"blood angel"', '"sanguinary"', '"death company"'],
        "display_name": "Blood Angels",
    },
    "chaos_daemons": {
        "search_terms": ['"chaos daemons"', '"daemons of chaos"', '"bloodletters"', '"plaguebearers"', '"daemonettes"'],
        "display_name": "Chaos Daemons",
    },
    "chaos_knights": {
        "search_terms": ['"chaos knight"', '"chaos knights"', '"war dog"', '"abominant"'],
        "display_name": "Chaos Knights",
    },
    "dark_angels": {
        "search_terms": ['"dark angels"', '"dark angel"', '"deathwing"', '"ravenwing"'],
        "display_name": "Dark Angels",
    },
    "deathwatch": {
        "search_terms": ['"deathwatch"', '"kill team" deathwatch'],
        "display_name": "Deathwatch",
    },
    "drukhari": {
        "search_terms": ['"drukhari"', '"dark eldar"', '"kabalite"', '"wych"'],
        "display_name": "Drukhari",
    },
    "emperors_children": {
        "search_terms": ['"emperor\'s children"', '"emperors children"', '"noise marines"', '"fulgrim"'],
        "display_name": "Emperor's Children",
    },
    "harlequins": {
        "search_terms": ['"harlequins"', '"harlequin" 40k', '"troupe" harlequin', '"solitaire" 40k'],
        "display_name": "Harlequins",
    },
    "imperial_agents": {
        "search_terms": ['"inquisitor" 40k', '"imperial assassin"', '"sisters of silence"', '"imperial agents"'],
        "display_name": "Imperial Agents",
    },
    "imperial_knights": {
        "search_terms": ['"imperial knight"', '"imperial knights"', '"knight castellan"', '"knight errant"'],
        "display_name": "Imperial Knights",
    },
    "leagues_of_votann": {
        "search_terms": ['"leagues of votann"', '"votann"', '"squats" 40k'],
        "display_name": "Leagues of Votann",
    },
    "space_wolves": {
        "search_terms": ['"space wolves"', '"space wolf"', '"thunderwolf"', '"fenrisian"'],
        "display_name": "Space Wolves",
    },
    "tau_empire": {
        "search_terms": ['"tau empire"', '"tau" 40k', '"crisis suit"', '"broadside" tau', '"fire warriors"'],
        "display_name": "T'au Empire",
    },
    "world_eaters": {
        "search_terms": ['"world eaters"', '"khorne berzerker"', '"angron"', '"world eater"'],
        "display_name": "World Eaters",
    },
    "ynnari": {
        "search_terms": ['"ynnari"', '"yncarne"', '"visarch"', '"yvraine"'],
        "display_name": "Ynnari",
    },
}

# DakkaDakka config
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
DAKKA_SEARCH = "https://www.dakkadakka.com/core/gallery-search.jsp"
DAKKA_IMAGES = "https://images.dakkadakka.com"
REQUEST_DELAY = 1.5  # seconds between page requests
DOWNLOAD_DELAY = 0.3  # seconds between image downloads

# Image settings
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MIN_IMAGE_SIZE = 20_000  # 20KB
RESULTS_PER_PAGE = 90  # max DakkaDakka allows


def search_dakkadakka(query: str, min_paintjob: int = 5, max_pages: int = 10) -> list[dict]:
    """Search DakkaDakka gallery and return image URLs."""
    urls = []
    seen = set()

    for page in range(max_pages):
        start = page * RESULTS_PER_PAGE

        params = {
            "dq": query,
            "sort1": "1",       # Best paintjobs first
            "sort2": "0",
            "skip": str(RESULTS_PER_PAGE),
            "p": "1",
            "ll": "3",
            "auction": "0",
            "unapproved": "0",
            "coolnesslow": "0",
            "coolnesshigh": "10",
            "paintjoblow": str(min_paintjob),
            "paintjobhigh": "10",
            "start": str(start),
        }

        try:
            resp = requests.get(DAKKA_SEARCH, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
            if resp.status_code != 200:
                print(f"    HTTP {resp.status_code} for query '{query}' page {page+1}")
                break

            html = resp.text

            # Extract image URLs: https://images.dakkadakka.com/gallery/YYYY/M/D/ID_mb-TITLE.ext
            img_pattern = re.compile(r'https://images\.dakkadakka\.com/gallery/\d{4}/\d{1,2}/\d{1,2}/(\d+)_mb-[^"\'>\s]+\.(?:jpg|jpeg|png|gif|JPG|JPEG|PNG)', re.IGNORECASE)
            matches = img_pattern.findall(html)

            if not matches:
                break

            # Re-extract full URLs
            full_matches = re.findall(r'https://images\.dakkadakka\.com/gallery/\d{4}/\d{1,2}/\d{1,2}/\d+_mb-[^"\'>\s]+\.(?:jpg|jpeg|png|gif|JPG|JPEG|PNG)', html, re.IGNORECASE)

            new_count = 0
            for thumb_url in full_matches:
                # Convert _mb- thumbnail to full-size (replace _mb- with -)
                full_url = thumb_url.replace("_mb-", "-")
                img_id = re.search(r'/(\d+)-', full_url)
                if img_id:
                    img_id = img_id.group(1)
                else:
                    img_id = hashlib.md5(full_url.encode()).hexdigest()[:10]

                if full_url not in seen:
                    seen.add(full_url)
                    urls.append({
                        "url": full_url,
                        "thumb_url": thumb_url,
                        "id": img_id,
                    })
                    new_count += 1

            if new_count == 0:
                break

            time.sleep(REQUEST_DELAY)

        except requests.RequestException as e:
            print(f"    Error: {e}")
            break

    return urls


def download_image(url: str, save_path: Path) -> bool:
    """Download a single image. Returns True on success."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30, stream=True)
        if resp.status_code != 200:
            # Try medium size fallback
            fallback = url.replace("/-", "/_md-", 1)
            # Actually construct fallback properly
            parts = url.rsplit("/", 1)
            if len(parts) == 2:
                filename = parts[1]
                # Original: ID-Title.ext → try ID_md-Title.ext
                fallback_name = filename.replace("-", "_md-", 1)
                fallback_url = parts[0] + "/" + fallback_name
                resp = requests.get(fallback_url, headers={"User-Agent": USER_AGENT}, timeout=30, stream=True)
                if resp.status_code != 200:
                    return False

        content_type = resp.headers.get("content-type", "")
        if "image" not in content_type and "octet-stream" not in content_type:
            return False

        data = resp.content
        if len(data) < MIN_IMAGE_SIZE:
            return False

        save_path.write_bytes(data)
        return True

    except Exception:
        return False


def scrape_faction(faction: str, config: dict, output_dir: Path, limit: int = 200, min_paintjob: int = 5, dry_run: bool = False) -> int:
    """Scrape images for a single faction. Returns number of images downloaded."""
    print(f"\n{'='*60}")
    print(f"  {config['display_name']} ({faction})")
    print(f"{'='*60}")

    dakka_dir = output_dir / faction / "dakkadakka"
    dakka_dir.mkdir(parents=True, exist_ok=True)

    # Check existing images
    existing = set(f.name for f in dakka_dir.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS)
    print(f"  Existing DakkaDakka images: {len(existing)}")

    if len(existing) >= limit:
        print(f"  Already have {len(existing)} images (limit: {limit}), skipping")
        return 0

    needed = limit - len(existing)
    print(f"  Need {needed} more images")

    # Collect URLs from all search terms
    all_urls = []
    seen_urls = set()

    for term in config["search_terms"]:
        max_pages = max(3, (needed * 2) // RESULTS_PER_PAGE + 1)
        print(f"  Searching for {term}...", end="", flush=True)
        results = search_dakkadakka(term, min_paintjob=min_paintjob, max_pages=max_pages)

        new = 0
        for r in results:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                all_urls.append(r)
                new += 1

        print(f" {new} new URLs")

        if len(all_urls) >= needed * 2:
            break

        time.sleep(REQUEST_DELAY)

    print(f"\n  Total unique URLs found: {len(all_urls)}")

    if dry_run:
        print(f"  [DRY RUN] Would download up to {needed} images")
        for u in all_urls[:10]:
            print(f"    {u['url'][:90]}")
        return 0

    # Download
    downloaded = 0
    failed = 0
    for entry in all_urls:
        if downloaded >= needed:
            break

        url = entry["url"]
        parsed = urlparse(url)
        ext = Path(parsed.path).suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            ext = ".jpg"

        filename = f"dakka_{entry['id']}{ext}"

        if filename in existing:
            continue

        save_path = dakka_dir / filename

        success = download_image(url, save_path)
        if success:
            downloaded += 1
            if downloaded % 25 == 0:
                print(f"    Downloaded {downloaded}/{needed}...")
        else:
            save_path.unlink(missing_ok=True)
            failed += 1

        time.sleep(DOWNLOAD_DELAY)

    print(f"  Downloaded: {downloaded} images ({failed} failed)")
    return downloaded


def main():
    parser = argparse.ArgumentParser(description="Scrape Warhammer 40K miniature images from DakkaDakka")
    parser.add_argument("--faction", type=str, default=None, help="Specific faction to scrape")
    parser.add_argument("--limit", type=int, default=200, help="Target images per faction (default: 200)")
    parser.add_argument("--min-paintjob", type=int, default=5, help="Minimum paintjob rating 0-10 (default: 5)")
    parser.add_argument("--list", action="store_true", help="List all faction configs")
    parser.add_argument("--dry-run", action="store_true", help="Preview without downloading")
    parser.add_argument("--all", action="store_true", help="Scrape ALL factions")
    parser.add_argument("--empty-only", action="store_true", help="Only scrape factions with zero dakkadakka images (default)")
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    training_data = project_root / "backend" / "training_data"

    if args.list:
        print("DakkaDakka Faction configurations:")
        print(f"{'Faction':<25} {'Display Name':<30} {'Search Terms'}")
        print("-" * 100)
        for faction, config in sorted(FACTION_CONFIG.items()):
            terms = ", ".join(config["search_terms"][:2])
            print(f"{faction:<25} {config['display_name']:<30} {terms}")
        return

    # Determine which factions to scrape
    if args.faction:
        if args.faction not in FACTION_CONFIG:
            print(f"ERROR: Unknown faction '{args.faction}'")
            print(f"Available: {', '.join(sorted(FACTION_CONFIG.keys()))}")
            sys.exit(1)
        factions_to_scrape = {args.faction: FACTION_CONFIG[args.faction]}
    elif args.all:
        factions_to_scrape = FACTION_CONFIG
    else:
        # Default: only factions with zero dakkadakka images
        factions_to_scrape = {}
        for faction, config in FACTION_CONFIG.items():
            dakka_dir = training_data / faction / "dakkadakka"
            img_count = 0
            if dakka_dir.exists():
                img_count = sum(1 for f in dakka_dir.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS)
            if img_count == 0:
                factions_to_scrape[faction] = config

    if not factions_to_scrape:
        print("All factions already have DakkaDakka images! Use --faction or --all to force scrape.")
        return

    print(f"Will scrape {len(factions_to_scrape)} factions from DakkaDakka, target {args.limit} images each")
    print(f"Min paintjob rating: {args.min_paintjob}/10")
    print(f"Factions: {', '.join(sorted(factions_to_scrape.keys()))}")

    total_downloaded = 0
    for faction, config in sorted(factions_to_scrape.items()):
        count = scrape_faction(faction, config, training_data, limit=args.limit, min_paintjob=args.min_paintjob, dry_run=args.dry_run)
        total_downloaded += count

    print(f"\n{'='*60}")
    print(f"DONE — Downloaded {total_downloaded} total images across {len(factions_to_scrape)} factions")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
