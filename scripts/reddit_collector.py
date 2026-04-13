#!/usr/bin/env python3
"""
Reddit Faction Subreddit Scraper for Battle Scanner Training Data

Scrapes image posts from faction-specific and multi-faction subreddits using PRAW.
Handles direct image links, Imgur singles, Imgur albums, and Reddit galleries.

Credentials (from .env or environment):
    REDDIT_CLIENT_ID
    REDDIT_CLIENT_SECRET
    REDDIT_USER_AGENT

Usage:
    python scripts/reddit_collector.py --subreddit Necrons --limit 50 --dry-run
    python scripts/reddit_collector.py --subreddit Necrons --limit 200
    python scripts/reddit_collector.py --all --limit 200
    python scripts/reddit_collector.py --list-subreddits
"""

import argparse
import csv
import html
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from scraper_utils import (
    OUTPUT_DIR, SCRAPE_LOG,
    compute_md5, init_csv, load_known_hashes, log_image,
    now_iso, quality_check_bytes, rand_delay, save_hash,
)

# ─── Subreddit → Faction Mapping ─────────────────────────────────────────────

SUBREDDIT_MAP = {
    "Necrons":              "necrons",
    "Tyranids":             "tyranids",
    "Orks":                 "orks",
    "Tau40K":               "tau_empire",
    "AdeptusMechanicus":    "adeptus_mechanicus",
    "spacemarines":         "space_marines",
    "sistersofbattle":      "adepta_sororitas",
    "thousandsons":         "chaos_space_marines",
    "genestealercult":      "genestealer_cults",
    "ImperialKnights":      "imperial_knights",
    "deathguard40k":        "chaos_space_marines",
    "BlackTemplars":        "space_marines",
    # Multi-faction
    "Warhammer40k":         "multi_faction",
    "minipainting":         "multi_faction",
    "Warhammer":            "multi_faction",
}

DIRECT_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

IMAGE_DELAY = 1.0   # seconds between image downloads


# ─── Env / Credentials ───────────────────────────────────────────────────────

def load_env():
    """Load .env file from project root if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass


def make_reddit():
    """Return an authenticated praw.Reddit instance."""
    import os
    try:
        import praw
    except ImportError:
        print("ERROR: praw is not installed. Run: pip install praw")
        sys.exit(1)

    client_id = os.environ.get("REDDIT_CLIENT_ID", "")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
    user_agent = os.environ.get("REDDIT_USER_AGENT", "BattleScanner/1.0")

    if not client_id or not client_secret:
        print("ERROR: REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set.")
        print("       Add them to your .env file or environment variables.")
        sys.exit(1)

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )


# ─── Resumability ─────────────────────────────────────────────────────────────

def load_scraped_reddit_ids() -> set:
    """Return set of post IDs already scraped from Reddit."""
    ids = set()
    if not SCRAPE_LOG.exists():
        return ids
    with open(SCRAPE_LOG, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("source_platform") == "reddit":
                url = row.get("page_url", "")
                m = re.search(r"/comments/([a-z0-9]+)/", url)
                if m:
                    ids.add(m.group(1))
    return ids


# ─── URL Type Detection & Image Resolution ───────────────────────────────────

def detect_url_type(url: str) -> str:
    """
    Returns one of: 'direct', 'imgur_direct', 'imgur_single', 'other'
    """
    if not url:
        return "other"
    low = url.lower()
    p = Path(url.split("?")[0])

    # Direct image URL (i.redd.it or any URL with image extension)
    if "i.redd.it" in low:
        return "direct"
    if p.suffix.lower() in DIRECT_EXTS and "imgur.com" not in low:
        return "direct"

    # Imgur direct (i.imgur.com/ID.ext)
    if "i.imgur.com" in low and p.suffix.lower() in DIRECT_EXTS:
        return "imgur_direct"

    # Imgur single page (imgur.com/ID — no /a/ album)
    if "imgur.com" in low and "/a/" not in low and "/gallery/" not in low:
        return "imgur_single"

    return "other"


def resolve_image_urls(submission) -> list[str]:
    """
    Return a list of direct image URLs from a PRAW submission.
    Handles galleries, Imgur, and plain image links.
    """
    urls = []

    # Reddit gallery
    if getattr(submission, "is_gallery", False):
        media = getattr(submission, "media_metadata", {}) or {}
        for item in media.values():
            try:
                # p[-1] = largest preview, use html.unescape for encoded URLs
                p_list = item.get("p", [])
                if p_list:
                    raw = p_list[-1].get("u", "")
                    if raw:
                        urls.append(html.unescape(raw))
            except (KeyError, TypeError, IndexError):
                continue
        return urls

    url = getattr(submission, "url", "") or ""
    kind = detect_url_type(url)

    if kind == "direct":
        urls.append(url)

    elif kind == "imgur_direct":
        urls.append(url)

    elif kind == "imgur_single":
        # Follow redirect to get the direct URL
        try:
            resp = requests.head(url, timeout=10, allow_redirects=True)
            final = resp.url
            if detect_url_type(final) in ("direct", "imgur_direct"):
                urls.append(final)
            else:
                # Append .jpg as fallback for imgur page IDs
                img_id = url.rstrip("/").split("/")[-1]
                urls.append(f"https://i.imgur.com/{img_id}.jpg")
        except requests.RequestException:
            pass

    return urls


# ─── Download ────────────────────────────────────────────────────────────────

def download_image(url: str, known_hashes: set, referer: str = "https://www.reddit.com/") -> tuple[bytes, int, int, str] | None:
    """Download and quality-check one image. Returns (jpg_bytes, w, h, hash) or None."""
    headers = {
        "User-Agent": "BattleScanner/1.0",
        "Referer": referer,
    }
    try:
        resp = requests.get(url, timeout=20, headers=headers)
        if resp.status_code != 200:
            return None
    except requests.RequestException:
        return None

    return quality_check_bytes(resp.content, known_hashes)


# ─── Main Scraping Logic ──────────────────────────────────────────────────────

def scrape_subreddit(
    reddit,
    subreddit_name: str,
    faction_slug: str,
    limit: int,
    sort: str,
    time_filter: str,
    known_hashes: set,
    scraped_ids: set,
    dry_run: bool = False,
) -> int:
    """Scrape one subreddit. Returns number of images saved."""
    if faction_slug == "multi_faction":
        out_dir = OUTPUT_DIR / "multi_faction" / "reddit"
    else:
        out_dir = OUTPUT_DIR / faction_slug / "reddit"

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    saved = 0

    print(f"\n  r/{subreddit_name} → {faction_slug}  (sort={sort}, time={time_filter})")

    if dry_run:
        print(f"  [DRY RUN] Would scrape r/{subreddit_name} for up to {limit} images")
        return 0

    try:
        sub = reddit.subreddit(subreddit_name)
        if sort == "top":
            posts = sub.top(time_filter=time_filter, limit=None)
        elif sort == "new":
            posts = sub.new(limit=None)
        else:
            posts = sub.hot(limit=None)
    except Exception as e:
        print(f"  ERROR accessing r/{subreddit_name}: {e}")
        return 0

    post_count = 0
    for submission in posts:
        if saved >= limit:
            break

        post_id = submission.id
        if post_id in scraped_ids:
            continue

        # Skip text/link posts that have no image
        if submission.is_self:
            continue

        image_urls = resolve_image_urls(submission)
        if not image_urls:
            continue

        post_count += 1
        page_url = f"https://www.reddit.com/comments/{post_id}/"

        for img_idx, img_url in enumerate(image_urls):
            if saved >= limit:
                break

            result = download_image(img_url, known_hashes)
            time.sleep(IMAGE_DELAY)

            if result is None:
                continue

            jpg_data, w, h, fhash = result
            known_hashes.add(fhash)
            save_hash(fhash)
            scraped_ids.add(post_id)

            fname = f"{faction_slug}_reddit_{post_id}_{img_idx:02d}.jpg"
            (out_dir / fname).write_bytes(jpg_data)
            saved += 1

            log_image({
                "filename": fname,
                "unit_name": "",
                "faction": faction_slug,
                "image_type": "multi_faction" if faction_slug == "multi_faction" else "faction_scene",
                "source_url": img_url,
                "page_url": page_url,
                "source_platform": "reddit",
                "width_px": w,
                "height_px": h,
                "file_hash": fhash,
                "search_query": f"r/{subreddit_name}",
                "timestamp": now_iso(),
            })

            if saved % 10 == 0:
                print(f"    {saved}/{limit} images saved...")

    print(f"  Done: {saved} new images from r/{subreddit_name} ({post_count} posts processed)")
    return saved


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scrape Reddit faction subreddits for Warhammer 40K images"
    )
    parser.add_argument("--subreddit", metavar="NAME", help="Single subreddit name (e.g. Necrons)")
    parser.add_argument("--faction", metavar="SLUG", help="Override faction slug for --subreddit")
    parser.add_argument("--all", action="store_true", help="Scrape all subreddits in SUBREDDIT_MAP")
    parser.add_argument("--limit", type=int, default=200, help="Max images per subreddit (default: 200)")
    parser.add_argument("--sort", choices=["top", "new", "hot"], default="top")
    parser.add_argument("--time-filter", choices=["week", "month", "year", "all"], default="year")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list-subreddits", action="store_true")
    args = parser.parse_args()

    if args.list_subreddits:
        print("\nSubreddit → Faction mapping:")
        for sub, faction in SUBREDDIT_MAP.items():
            print(f"  r/{sub:30s} → {faction}")
        return

    if not args.all and not args.subreddit:
        parser.print_help()
        sys.exit(1)

    load_env()

    if args.all:
        targets = list(SUBREDDIT_MAP.items())
    else:
        faction = args.faction or SUBREDDIT_MAP.get(args.subreddit)
        if not faction:
            print(f"Unknown subreddit '{args.subreddit}'. Use --list-subreddits to see options.")
            sys.exit(1)
        targets = [(args.subreddit, faction)]

    init_csv()
    known_hashes = load_known_hashes()
    scraped_ids = load_scraped_reddit_ids()

    reddit = make_reddit()

    print("=" * 60)
    print("Reddit Collector")
    print(f"Subreddits: {len(targets)}")
    print(f"Limit per subreddit: {args.limit}")
    print(f"Sort: {args.sort} | Time: {args.time_filter}")
    print(f"Dry run: {args.dry_run}")
    print(f"Known hashes: {len(known_hashes)}")
    print(f"Already-scraped post IDs: {len(scraped_ids)}")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 60)

    grand_total = 0
    try:
        for subreddit_name, faction_slug in targets:
            n = scrape_subreddit(
                reddit=reddit,
                subreddit_name=subreddit_name,
                faction_slug=faction_slug,
                limit=args.limit,
                sort=args.sort,
                time_filter=args.time_filter,
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
