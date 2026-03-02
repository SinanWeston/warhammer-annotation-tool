"""
Warhammer 40K Faction Image Scraper

Scrapes miniature images from Reddit (public JSON API, no auth needed) for factions
that are missing training data. Downloads images into the correct directory structure.

Usage:
    python3 scrape_faction_images.py                    # Scrape all empty factions
    python3 scrape_faction_images.py --faction blood_angels --limit 300
    python3 scrape_faction_images.py --list              # Show faction config
    python3 scrape_faction_images.py --dry-run            # Preview without downloading

Dependencies:
    pip install requests   (already installed)
"""

import os
import sys
import json
import time
import hashlib
import argparse
import requests
from pathlib import Path
from urllib.parse import urlparse

# ── Faction → Reddit search config ──────────────────────────────────────────
# Each faction maps to subreddits + search terms that yield painted miniature photos.
# Multiple subreddits are searched. Terms are combined with the subreddit search.

FACTION_CONFIG = {
    "adepta_sororitas": {
        "subreddits": ["sistersofbattle", "Warhammer40k", "minipainting"],
        "search_terms": ["sisters of battle painted", "adepta sororitas army", "sisters of battle miniatures"],
        "display_name": "Adepta Sororitas / Sisters of Battle",
    },
    "black_templars": {
        "subreddits": ["BlackTemplars", "Warhammer40k", "minipainting"],
        "search_terms": ["black templars painted", "black templars army", "black templars miniatures"],
        "display_name": "Black Templars",
    },
    "blood_angels": {
        "subreddits": ["BloodAngels", "Warhammer40k", "minipainting"],
        "search_terms": ["blood angels painted", "blood angels army", "blood angels miniatures"],
        "display_name": "Blood Angels",
    },
    "chaos_daemons": {
        "subreddits": ["Chaos40k", "Warhammer40k", "minipainting"],
        "search_terms": ["chaos daemons painted", "daemons of chaos army", "chaos daemons miniatures"],
        "display_name": "Chaos Daemons",
    },
    "chaos_knights": {
        "subreddits": ["ChaosKnights", "Warhammer40k", "minipainting"],
        "search_terms": ["chaos knights painted", "war dog", "chaos knight army miniature"],
        "display_name": "Chaos Knights",
    },
    "dark_angels": {
        "subreddits": ["DarkAngels40k", "Warhammer40k", "minipainting"],
        "search_terms": ["dark angels painted", "dark angels army", "dark angels miniatures", "deathwing painted"],
        "display_name": "Dark Angels",
    },
    "deathwatch": {
        "subreddits": ["deathwatch40k", "Warhammer40k", "minipainting"],
        "search_terms": ["deathwatch painted", "deathwatch army", "deathwatch kill team miniatures"],
        "display_name": "Deathwatch",
    },
    "drukhari": {
        "subreddits": ["Drukhari", "Warhammer40k", "minipainting"],
        "search_terms": ["drukhari painted", "dark eldar army", "drukhari miniatures", "kabalite warriors"],
        "display_name": "Drukhari / Dark Eldar",
    },
    "emperors_children": {
        "subreddits": ["EmperorsChildren", "Chaos40k", "Warhammer40k"],
        "search_terms": ["emperors children painted", "emperor's children army", "emperors children noise marines"],
        "display_name": "Emperor's Children",
    },
    "harlequins": {
        "subreddits": ["Harlequins40K", "Warhammer40k", "minipainting"],
        "search_terms": ["harlequins painted", "harlequin troupe painted", "harlequins army miniatures"],
        "display_name": "Harlequins",
    },
    "imperial_agents": {
        "subreddits": ["Warhammer40k", "minipainting", "Inquisimunda"],
        "search_terms": ["inquisitor painted miniature", "imperial agents 40k", "assassin painted 40k", "sisters of silence painted"],
        "display_name": "Imperial Agents",
    },
    "imperial_knights": {
        "subreddits": ["ImperialKnights", "Warhammer40k", "minipainting"],
        "search_terms": ["imperial knight painted", "knight castellan painted", "imperial knights army"],
        "display_name": "Imperial Knights",
    },
    "leagues_of_votann": {
        "subreddits": ["LeaguesofVotann", "Warhammer40k", "minipainting"],
        "search_terms": ["leagues of votann painted", "votann army", "squats 40k painted"],
        "display_name": "Leagues of Votann",
    },
    "space_wolves": {
        "subreddits": ["SpaceWolves", "Warhammer40k", "minipainting"],
        "search_terms": ["space wolves painted", "space wolves army", "thunderwolf cavalry painted"],
        "display_name": "Space Wolves",
    },
    "tau_empire": {
        "subreddits": ["Tau40K", "Warhammer40k", "minipainting"],
        "search_terms": ["tau empire painted", "tau army 40k", "crisis suit painted", "tau miniatures"],
        "display_name": "T'au Empire",
    },
    "world_eaters": {
        "subreddits": ["WorldEaters40k", "Chaos40k", "Warhammer40k"],
        "search_terms": ["world eaters painted", "angron painted", "world eaters army", "khorne berzerkers painted"],
        "display_name": "World Eaters",
    },
    "ynnari": {
        "subreddits": ["Eldar", "Warhammer40k", "minipainting"],
        "search_terms": ["ynnari painted", "yncarne painted", "ynnari army", "visarch painted"],
        "display_name": "Ynnari",
    },
}

# Reddit API config
USER_AGENT = "WH40K-Training-Data-Collector/1.0"
REDDIT_BASE = "https://www.reddit.com"
REQUEST_DELAY = 2.0  # seconds between requests (be nice to Reddit)

# Valid image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# Minimum image size in bytes (skip tiny thumbnails)
MIN_IMAGE_SIZE = 20_000  # 20KB


def get_image_urls_from_reddit(subreddit: str, query: str, limit: int = 100, sort: str = "relevance", time_filter: str = "all") -> list[dict]:
    """Search a subreddit and extract image URLs from posts."""
    urls = []
    after = None
    fetched = 0
    max_pages = (limit // 25) + 2

    for page in range(max_pages):
        if fetched >= limit:
            break

        params = {
            "q": query,
            "restrict_sr": "on",
            "sort": sort,
            "t": time_filter,
            "limit": 25,
            "type": "link",
        }
        if after:
            params["after"] = after

        url = f"{REDDIT_BASE}/r/{subreddit}/search.json"

        try:
            resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=15)
            if resp.status_code == 429:
                print(f"    Rate limited, waiting 60s...")
                time.sleep(60)
                continue
            if resp.status_code != 200:
                print(f"    HTTP {resp.status_code} for r/{subreddit} search '{query}'")
                break

            data = resp.json()
            posts = data.get("data", {}).get("children", [])
            after = data.get("data", {}).get("after")

            if not posts:
                break

            for post in posts:
                post_data = post.get("data", {})

                # Skip videos, text posts, NSFW
                if post_data.get("is_video"):
                    continue
                if post_data.get("over_18"):
                    continue

                # Direct image link
                post_url = post_data.get("url", "")
                if any(post_url.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
                    urls.append({
                        "url": post_url,
                        "title": post_data.get("title", ""),
                        "post_id": post_data.get("id", ""),
                        "score": post_data.get("score", 0),
                    })
                    fetched += 1
                    continue

                # Reddit gallery
                if "gallery" in post_url or post_data.get("is_gallery"):
                    media_metadata = post_data.get("media_metadata") or {}
                    for media_id, media_info in media_metadata.items():
                        if media_info.get("status") == "valid" and media_info.get("m", "").startswith("image/"):
                            ext = media_info["m"].split("/")[-1]
                            if ext == "jpeg":
                                ext = "jpg"
                            gallery_url = f"https://i.redd.it/{media_id}.{ext}"
                            urls.append({
                                "url": gallery_url,
                                "title": post_data.get("title", ""),
                                "post_id": post_data.get("id", ""),
                                "score": post_data.get("score", 0),
                            })
                            fetched += 1

                # i.redd.it preview
                preview = post_data.get("preview", {})
                if preview:
                    images = preview.get("images", [])
                    if images:
                        source_url = images[0].get("source", {}).get("url", "").replace("&amp;", "&")
                        if source_url:
                            urls.append({
                                "url": source_url,
                                "title": post_data.get("title", ""),
                                "post_id": post_data.get("id", ""),
                                "score": post_data.get("score", 0),
                            })
                            fetched += 1

            if not after:
                break

            time.sleep(REQUEST_DELAY)

        except requests.RequestException as e:
            print(f"    Error fetching r/{subreddit}: {e}")
            break

    return urls


def download_image(url: str, save_path: Path) -> bool:
    """Download a single image. Returns True on success."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30, stream=True)
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


def scrape_faction(faction: str, config: dict, output_dir: Path, limit: int = 200, dry_run: bool = False) -> int:
    """Scrape images for a single faction. Returns number of images downloaded."""
    print(f"\n{'='*60}")
    print(f"  {config['display_name']} ({faction})")
    print(f"{'='*60}")

    reddit_dir = output_dir / faction / "reddit"
    reddit_dir.mkdir(parents=True, exist_ok=True)

    # Check existing images
    existing = set(f.name for f in reddit_dir.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS)
    print(f"  Existing images: {len(existing)}")

    if len(existing) >= limit:
        print(f"  Already have {len(existing)} images (limit: {limit}), skipping")
        return 0

    needed = limit - len(existing)
    print(f"  Need {needed} more images")

    # Collect URLs from all subreddits and search terms
    all_urls = []
    seen_urls = set()

    for subreddit in config["subreddits"]:
        for term in config["search_terms"]:
            print(f"  Searching r/{subreddit} for '{term}'...", end="", flush=True)
            results = get_image_urls_from_reddit(subreddit, term, limit=100)

            new = 0
            for r in results:
                if r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    all_urls.append(r)
                    new += 1

            print(f" {new} new URLs")
            time.sleep(REQUEST_DELAY)

            if len(all_urls) >= needed * 2:  # Collect 2x to account for failures
                break
        if len(all_urls) >= needed * 2:
            break

    # Sort by score (higher quality posts first)
    all_urls.sort(key=lambda x: -x["score"])

    print(f"\n  Total unique URLs found: {len(all_urls)}")

    if dry_run:
        print(f"  [DRY RUN] Would download up to {needed} images")
        for u in all_urls[:10]:
            print(f"    {u['score']:>5}pts  {u['url'][:80]}")
        return 0

    # Download
    downloaded = 0
    for i, entry in enumerate(all_urls):
        if downloaded >= needed:
            break

        url = entry["url"]
        parsed = urlparse(url)
        ext = Path(parsed.path).suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            ext = ".jpg"

        # Generate filename from URL hash + post ID
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        post_id = entry.get("post_id", "unknown")
        filename = f"{post_id}_{url_hash}{ext}"

        if filename in existing:
            continue

        save_path = reddit_dir / filename

        success = download_image(url, save_path)
        if success:
            downloaded += 1
            if downloaded % 25 == 0:
                print(f"    Downloaded {downloaded}/{needed}...")
        else:
            save_path.unlink(missing_ok=True)

        time.sleep(0.5)  # Small delay between downloads

    print(f"  Downloaded: {downloaded} images")
    return downloaded


def main():
    parser = argparse.ArgumentParser(description="Scrape Warhammer 40K miniature images from Reddit")
    parser.add_argument("--faction", type=str, default=None, help="Specific faction to scrape")
    parser.add_argument("--limit", type=int, default=200, help="Target images per faction (default: 200)")
    parser.add_argument("--list", action="store_true", help="List all faction configs")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded without downloading")
    parser.add_argument("--all", action="store_true", help="Scrape ALL factions (including ones with images)")
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    training_data = project_root / "backend" / "training_data"

    if args.list:
        print("Faction configurations:")
        print(f"{'Faction':<25} {'Display Name':<35} {'Subreddits'}")
        print("-" * 90)
        for faction, config in sorted(FACTION_CONFIG.items()):
            subs = ", ".join(f"r/{s}" for s in config["subreddits"][:3])
            print(f"{faction:<25} {config['display_name']:<35} {subs}")
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
        # Default: only scrape factions with zero images
        factions_to_scrape = {}
        for faction, config in FACTION_CONFIG.items():
            faction_dir = training_data / faction
            img_count = 0
            for source in ["reddit", "dakkadakka"]:
                src_dir = faction_dir / source
                if src_dir.exists():
                    img_count += sum(1 for f in src_dir.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS)
            if img_count == 0:
                factions_to_scrape[faction] = config

    if not factions_to_scrape:
        print("All factions already have images! Use --faction or --all to force scrape.")
        return

    print(f"Will scrape {len(factions_to_scrape)} factions, target {args.limit} images each")
    print(f"Factions: {', '.join(sorted(factions_to_scrape.keys()))}")

    total_downloaded = 0
    for faction, config in sorted(factions_to_scrape.items()):
        count = scrape_faction(faction, config, training_data, limit=args.limit, dry_run=args.dry_run)
        total_downloaded += count

    print(f"\n{'='*60}")
    print(f"DONE — Downloaded {total_downloaded} total images across {len(factions_to_scrape)} factions")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
