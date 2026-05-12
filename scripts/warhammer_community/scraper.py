#!/usr/bin/env python3
"""
Warhammer Community blog scraper — discovers 40K painting/hobby articles via
sitemap, extracts article body images, labels by faction (from topic tags) and
unit (best-effort from title), downloads to images/{faction}/{slug}/.

Much simpler than the GW shop scraper: plain requests + BeautifulSoup, no
Playwright, no WAF. robots.txt explicitly allows crawling.

Pipeline:
  1. Fetch sitemap.xml → extract all /en-gb/articles/ URLs
  2. For each: fetch HTML → extract topic tags → filter to 40K + painting
  3. Extract article body images (hash-based filenames on CDN)
  4. Download to images/{faction}/{article_slug_or_unit}/
  5. Log to scrape_log.csv (source_platform = "warhammer_community")

Usage:
    yolo_env/bin/python3 scripts/warhammer_community/scraper.py
    yolo_env/bin/python3 scripts/warhammer_community/scraper.py --limit 20
    yolo_env/bin/python3 scripts/warhammer_community/scraper.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scraper_utils import (  # noqa: E402
    BASE_DIR,
    USER_AGENTS,
    init_csv,
    load_known_hashes,
    log_image,
    now_iso,
    quality_check_bytes,
    save_hash,
)

# ─── Config ─────────────────────────────────────────────────────────────────

SITEMAP_URL = "https://www.warhammer-community.com/sitemap.xml"
CDN_HOST = "assets.warhammer-community.com"
SOURCE_PLATFORM = "warhammer_community"

IMAGES_ROOT = HERE / "images"
STATE_DIR = HERE / "state"
ARTICLES_JSONL = STATE_DIR / "articles.jsonl"

# Topic slugs that indicate 40K content
TOPIC_40K = {"warhammer-40000", "warhammer-40,000"}

# Topic slugs that indicate painting/hobby content worth scraping
TOPIC_PAINTING = {
    "painting", "building-and-painting", "golden-demon", "showcase",
    "hobby", "tutorial", "how-to-paint", "starting-army",
    "miniature-of-the-month", "army-showcase", "community-spotlight",
}

# Faction topic slugs → repo faction names
FACTION_TOPIC_MAP: dict[str, str] = {
    "space-marines": "space_marines",
    "dark-angels": "dark_angels",
    "blood-angels": "blood_angels",
    "space-wolves": "space_wolves",
    "black-templars": "black_templars",
    "grey-knights": "grey_knights",
    "deathwatch": "deathwatch",
    "ultramarines": "space_marines",
    "imperial-fists": "space_marines",
    "iron-hands": "space_marines",
    "salamanders": "space_marines",
    "raven-guard": "space_marines",
    "white-scars": "space_marines",
    "adepta-sororitas": "adepta_sororitas",
    "adeptus-custodes": "adeptus_custodes",
    "adeptus-mechanicus": "adeptus_mechanicus",
    "astra-militarum": "astra_militarum",
    "imperial-knights": "imperial_knights",
    "imperial-agents": "imperial_agents",
    "chaos-space-marines": "chaos_space_marines",
    "death-guard": "death_guard",
    "thousand-sons": "thousand_sons",
    "world-eaters": "world_eaters",
    "emperors-children": "emperors_children",
    "chaos-daemons": "chaos_daemons",
    "chaos-knights": "chaos_knights",
    "aeldari": "aeldari",
    "drukhari": "drukhari",
    "harlequins": "harlequins",
    "ynnari": "ynnari",
    "tyranids": "tyranids",
    "genestealer-cults": "genestealer_cults",
    "necrons": "necrons",
    "orks": "orks",
    "leagues-of-votann": "leagues_of_votann",
    "tau-empire": "tau_empire",
    "t-au-empire": "tau_empire",
    "kroot": "tau_empire",
}

# Hash-based filenames are article body content; descriptive ones are site chrome
BODY_IMAGE_RE = re.compile(r"^[a-z0-9]{10,24}(-\d+)?\.(?:jpg|png|webp)$", re.IGNORECASE)

# ─── HTTP session ───────────────────────────────────────────────────────────

def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = random.choice(USER_AGENTS)
    return s


def _rand_delay(lo: float = 1.0, hi: float = 3.0) -> None:
    time.sleep(random.uniform(lo, hi))


# ─── Discovery ──────────────────────────────────────────────────────────────

def discover_articles(session: requests.Session) -> list[str]:
    """Fetch sitemap.xml, return all /en-gb/articles/ URLs."""
    print("Fetching sitemap.xml…", flush=True)
    r = session.get(SITEMAP_URL, timeout=30)
    r.raise_for_status()
    urls = re.findall(
        r"https://www\.warhammer-community\.com/en-gb/articles/[^<\s]+", r.text
    )
    # Dedupe, strip trailing whitespace
    urls = list(dict.fromkeys(u.strip().rstrip("/") for u in urls))
    print(f"  {len(urls)} article URLs in sitemap", flush=True)
    return urls


# ─── Per-article parsing ────────────────────────────────────────────────────

@dataclass
class ArticleMeta:
    url: str
    article_id: str
    slug: str
    title: str
    topics: list[str]           # raw topic slugs from /topics/{slug}
    is_40k: bool
    is_painting: bool
    faction: str                # best-guess repo faction slug, or 'unknown'
    unit_hint: str              # best-effort unit name from title, or ''
    image_urls: list[str] = field(default_factory=list)


def _extract_article_id_and_slug(url: str) -> tuple[str, str]:
    """'/en-gb/articles/08WNtm8e/starting-a-dark-angels-army...' → ('08WNtm8e', 'starting-a-dark-angels-army...')"""
    parts = urlparse(url).path.strip("/").split("/")
    # ['en-gb', 'articles', ID, SLUG]
    if len(parts) >= 4:
        return parts[2], parts[3]
    return parts[-1] if parts else "", ""


def _parse_topics(soup: BeautifulSoup) -> list[str]:
    """Extract topic slugs from /en-gb/topics/{slug} links."""
    topics: list[str] = []
    for a in soup.find_all("a", href=re.compile(r"/en-gb/topics/")):
        href = a.get("href", "")
        m = re.search(r"/topics/([^/]+)", href)
        if m:
            topics.append(m.group(1).lower())
    return list(dict.fromkeys(topics))  # dedupe, preserve order


def _infer_faction(topics: list[str]) -> str:
    """First matching faction topic slug wins."""
    for t in topics:
        if t in FACTION_TOPIC_MAP:
            return FACTION_TOPIC_MAP[t]
    return "unknown"


def _infer_unit_from_title(title: str) -> str:
    """
    Best-effort unit extraction from article title. Works for:
      "How to Paint Intercessors" → "intercessors"
      "Painting a Blightlord Terminator" → "blightlord_terminator"
    Falls back to '' for generic titles like "Starting a Dark Angels Army".
    """
    title_lower = title.lower()
    # "how to paint X" / "painting X"
    for pattern in (r"how to paint (.+?)(?:\s*[-–—]|$)", r"painting (?:a |an )?(.+?)(?:\s*[-–—]|$)"):
        m = re.search(pattern, title_lower)
        if m:
            raw = m.group(1).strip()
            slug = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
            if slug and len(slug) > 2:
                return slug
    return ""


def _extract_body_images(soup: BeautifulSoup, html: str) -> list[str]:
    """
    Extract article body image URLs. Strategy:
    1. Find all image URLs on the assets CDN
    2. Keep only hash-based filenames (article content)
    3. Discard descriptive filenames (site chrome: explore-more, icons, logos)
    """
    # Gather from <img> src/data-src + inline JSON/RSC payloads
    urls: set[str] = set()

    for tag in soup.find_all(["img", "source"]):
        for attr in ("src", "data-src", "srcset", "data-srcset"):
            val = tag.get(attr, "")
            if CDN_HOST in val:
                urls.add(val.split()[0].split(",")[0])

    # Also extract from inline JSON (RSC payloads embed image URLs as strings)
    for m in re.finditer(
        rf'"(https://{re.escape(CDN_HOST)}/[^"]+\.(?:jpg|png|webp))"', html
    ):
        urls.add(m.group(1))

    # Filter to body content (hash filenames)
    body_imgs: list[str] = []
    for u in sorted(urls):
        fname = u.split("/")[-1].split("?")[0]
        if BODY_IMAGE_RE.match(fname):
            body_imgs.append(u)
    return body_imgs


def parse_article(url: str, session: requests.Session) -> ArticleMeta | None:
    """Fetch and parse one article. Returns None on HTTP error."""
    try:
        r = session.get(url, timeout=20)
        if r.status_code != 200:
            return None
    except requests.RequestException:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    article_id, slug = _extract_article_id_and_slug(url)

    title_tag = soup.find("title")
    title = title_tag.string.split(" - ")[0].strip() if title_tag else slug

    topics = _parse_topics(soup)
    is_40k = any(t in TOPIC_40K for t in topics) or any(t in FACTION_TOPIC_MAP for t in topics)
    is_painting = any(t in TOPIC_PAINTING for t in topics)
    faction = _infer_faction(topics)
    unit_hint = _infer_unit_from_title(title)
    image_urls = _extract_body_images(soup, r.text)

    return ArticleMeta(
        url=url,
        article_id=article_id,
        slug=slug,
        title=title,
        topics=topics,
        is_40k=is_40k,
        is_painting=is_painting,
        faction=faction,
        unit_hint=unit_hint,
        image_urls=image_urls,
    )


# ─── Image download ─────────────────────────────────────────────────────────

def _download_and_save(
    img_url: str,
    meta: ArticleMeta,
    session: requests.Session,
    known_hashes: set[str],
) -> str:
    """Download one image, quality-check, save. Returns status token."""
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        r = session.get(img_url, headers=headers, timeout=30)
        if r.status_code != 200:
            return "failed"
    except requests.RequestException:
        return "failed"

    checked = quality_check_bytes(r.content, known_hashes)
    if checked is None:
        return "dedup"
    jpg_bytes, w, h, md5 = checked

    # Determine output path
    faction = meta.faction
    unit = meta.unit_hint or meta.slug
    out_dir = IMAGES_ROOT / faction / unit
    out_dir.mkdir(parents=True, exist_ok=True)

    fname = img_url.split("/")[-1].split("?")[0]
    if not fname.endswith(".jpg"):
        fname = fname.rsplit(".", 1)[0] + ".jpg"
    out_path = out_dir / fname
    out_path.write_bytes(jpg_bytes)

    save_hash(md5)
    known_hashes.add(md5)

    try:
        rel = str(out_path.relative_to(BASE_DIR))
    except ValueError:
        rel = str(out_path)
    log_image({
        "filename": rel,
        "unit_name": meta.unit_hint or meta.title,
        "faction": faction,
        "image_type": "community_article",
        "source_url": img_url,
        "page_url": meta.url,
        "source_platform": SOURCE_PLATFORM,
        "width_px": w,
        "height_px": h,
        "file_hash": md5,
        "search_query": "",
        "timestamp": now_iso(),
    })
    return "saved"


# ─── Main orchestrator ──────────────────────────────────────────────────────

def _load_processed() -> set[str]:
    """Article URLs already scraped (from articles.jsonl)."""
    if not ARTICLES_JSONL.exists():
        return set()
    out: set[str] = set()
    for line in ARTICLES_JSONL.read_text().splitlines():
        if not line.strip():
            continue
        try:
            out.add(json.loads(line)["url"])
        except (json.JSONDecodeError, KeyError):
            pass
    return out


def _append_article_row(meta: ArticleMeta, images_saved: int) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "url": meta.url,
        "article_id": meta.article_id,
        "slug": meta.slug,
        "title": meta.title,
        "topics": meta.topics,
        "is_40k": meta.is_40k,
        "is_painting": meta.is_painting,
        "faction": meta.faction,
        "unit_hint": meta.unit_hint,
        "n_images_found": len(meta.image_urls),
        "images_saved": images_saved,
        "scraped_at": now_iso(),
    }
    with ARTICLES_JSONL.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def run(
    limit: int | None = None,
    dry_run: bool = False,
    require_painting_tag: bool = False,
) -> dict:
    IMAGES_ROOT.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    init_csv()
    known_hashes = load_known_hashes()
    session = _session()

    # 1. Discover
    all_urls = discover_articles(session)
    already = _load_processed()
    print(f"Already processed: {len(already)}", flush=True)

    # 2. Quick-filter by URL keywords (saves HTTP calls)
    candidates = [u for u in all_urls if u not in already]
    print(f"Candidates to check: {len(candidates)}", flush=True)
    if limit:
        candidates = candidates[:limit * 5]  # over-fetch since many won't be 40K

    # 3. Fetch + parse + filter
    stats = {"checked": 0, "is_40k": 0, "scraped": 0, "images_saved": 0,
             "images_deduped": 0, "images_failed": 0}
    scraped = 0

    for i, url in enumerate(candidates):
        if limit and scraped >= limit:
            break
        stats["checked"] += 1

        meta = parse_article(url, session)
        if meta is None:
            continue

        if not meta.is_40k:
            continue
        stats["is_40k"] += 1

        if require_painting_tag and not meta.is_painting:
            continue

        if not meta.image_urls:
            continue

        if dry_run:
            print(f"  [DRY] {meta.title[:60]:60s}  faction={meta.faction:20s}  "
                  f"imgs={len(meta.image_urls)}  unit={meta.unit_hint}", flush=True)
            scraped += 1
            _rand_delay(0.3, 0.8)
            continue

        # Download images
        saved = 0
        for img_url in meta.image_urls:
            result = _download_and_save(img_url, meta, session, known_hashes)
            if result == "saved":
                saved += 1
                stats["images_saved"] += 1
            elif result == "dedup":
                stats["images_deduped"] += 1
            else:
                stats["images_failed"] += 1

        _append_article_row(meta, saved)
        stats["scraped"] += 1
        scraped += 1
        print(f"  [{scraped:4d}] {meta.title[:50]:50s}  "
              f"faction={meta.faction:18s}  saved={saved}/{len(meta.image_urls)}",
              flush=True)
        _rand_delay(1.0, 2.5)

    print(f"\n=== done ===", flush=True)
    for k, v in stats.items():
        print(f"  {k}: {v}", flush=True)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scrape Warhammer Community 40K articles")
    ap.add_argument("--limit", type=int, default=None,
                    help="Max articles to scrape (default: no limit)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse articles but don't download images")
    ap.add_argument("--painting-only", action="store_true",
                    help="Only scrape articles with painting/hobby topic tags")
    args = ap.parse_args(argv)
    run(limit=args.limit, dry_run=args.dry_run, require_painting_tag=args.painting_only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
