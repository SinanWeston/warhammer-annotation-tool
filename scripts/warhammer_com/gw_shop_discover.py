#!/usr/bin/env python3
"""
Stage 1 — Product URL discovery for the warhammer.com 40K shop.

Strategy: navigate the category landing page with a WAF-authorized browser,
scroll to trigger lazy-loading, harvest all product anchor hrefs, filter to
individual product URLs (single-segment under /en-GB/shop/), dedupe against
prior runs, and write to state/products.jsonl.

Fallback strategy: seed with known-good URLs + BFS over each product's
context.relatedProducts. Called automatically if the primary yields too few.

Usage:
    fiftyone_env/bin/python3 scripts/warhammer_com/gw_shop_discover.py
    fiftyone_env/bin/python3 scripts/warhammer_com/gw_shop_discover.py --strategy crawl
    fiftyone_env/bin/python3 scripts/warhammer_com/gw_shop_discover.py --limit 20
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from gw_shop_constants import (  # noqa: E402
    BASE,
    LANDING_40K,
    PRODUCTS_JSONL,
    PROFILE_DIR,
    SEED_URLS,
    STATE_DIR,
)
from wh_browser import WhBrowser, rand_delay  # noqa: E402


# Top-level category slugs — anything at /en-GB/shop/{slug} whose slug is in
# this set is a category, not a product.
CATEGORY_SLUGS: frozenset[str] = frozenset({
    "warhammer-40000",
    "age-of-sigmar",
    "horus-heresy",
    "the-horus-heresy",
    "necromunda",
    "kill-team",
    "warcry",
    "middle-earth",
    "lord-of-the-rings",
    "blood-bowl",
    "the-old-world",
    "warmaster",
    "adeptus-titanicus",
    "legions-imperialis",
    "paints",
    "painting-and-modelling",
    "modelling",
    "accessories",
    "books",
    "bundles",
    "gift-vouchers",
    "gw-virtual-gift-voucher",
    "webstore-exclusives",
    "warhammer-plus",
    "black-library",
    "black-library-novels",
    "new-releases",
    "last-chance-to-buy",
    "made-to-order",
    "cart",
    "expert-kits",
    "starter-sets",
    "big-box-games",
    "white-dwarf",
    "white-dwarf-12-month-sub-eng",
})

# Non-40K product slug patterns — reject any slug containing these tokens
# (user requested 40K-only corpus).
NON_40K_TOKENS: tuple[str, ...] = (
    "age-of-sigmar", "aos-", "-aos-", "sigmar",
    "blood-bowl", "warhammer-underworlds", "warhammer-quest",
    "adeptus-titanicus", "legions-imperialis", "horus-heresy",
    "necromunda", "kill-team-",  # kill-team-hivestorm etc. are mixed but listed under 40k separately
    "warcry", "old-world", "warmaster", "middle-earth", "lotr-",
    "white-dwarf", "black-library",
    "mto-", "gift-voucher", "subscription",
    "paint-set", "paint-bundle", "paintbrush",
    "modelling-tool", "hobby-tool", "plastic-glue",
)

PRODUCT_URL_RE = re.compile(
    r"^(?:https?://[^/]+)?/en-GB/shop/(?P<slug>[a-z0-9][a-z0-9-]*)/?$",
    re.IGNORECASE,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_product_url(href: str) -> str | None:
    """
    Returns the canonical product URL if `href` looks like a 40K product link,
    else None.

    Rules:
      - single-segment slug under /en-GB/shop/
      - slug is not a known category
      - ignores locale variants other than en-GB to keep things consistent
    """
    if not href:
        return None
    full = urljoin(BASE, href)
    parsed = urlparse(full)
    if parsed.netloc and parsed.netloc != "www.warhammer.com":
        return None

    m = PRODUCT_URL_RE.match(full)
    if not m:
        return None

    slug = m.group("slug").lower()
    if slug in CATEGORY_SLUGS:
        return None
    # Drop obvious non-product pages
    if slug.startswith(("help-", "faq", "terms", "privacy", "cookie", "login",
                        "store-locator", "account")):
        return None
    # Drop non-40K product slugs
    if any(tok in slug for tok in NON_40K_TOKENS):
        return None

    return f"{BASE}/en-GB/shop/{slug}"


def _load_existing(path: Path) -> dict[str, dict]:
    """Read products.jsonl (if it exists) into a dict keyed by url."""
    if not path.exists():
        return {}
    rows: dict[str, dict] = {}
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = row.get("url")
            if url:
                rows[url] = row
    return rows


def _write_rows(path: Path, rows: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        for url in sorted(rows.keys()):
            f.write(json.dumps(rows[url], ensure_ascii=False) + "\n")
    tmp.replace(path)


def _new_row(url: str) -> dict:
    slug = url.rsplit("/", 1)[-1]
    return {
        "url": url,
        "url_slug": slug,
        "discovered_at": _now_iso(),
        "scraped_at": None,
        "product_id": None,
        "master_sku": None,
        "name": None,
        "product_type": None,
        "images_saved": None,
        "images_skipped": None,
        "error": None,
    }


# ─── Strategies ─────────────────────────────────────────────────────────────

def discover_via_listing(browser: WhBrowser, limit: int | None = None) -> set[str]:
    """Navigate the 40K landing page, scroll to load all tiles, harvest product URLs."""
    print(f"  Navigating {LANDING_40K} …", flush=True)
    html = browser.goto(LANDING_40K, wait_ms=4000)
    if not html:
        print("  ⚠ listing page returned empty HTML", flush=True)
        return set()

    rounds = browser.scroll_to_bottom(max_rounds=40, pause_ms=1500)
    print(f"  scrolled {rounds} rounds", flush=True)

    hrefs = browser.harvest_links()
    print(f"  {len(hrefs)} raw <a href> values harvested", flush=True)

    found: set[str] = set()
    for h in hrefs:
        norm = _normalise_product_url(h)
        if norm:
            found.add(norm)
            if limit and len(found) >= limit:
                break
    print(f"  {len(found)} unique product URLs after filtering", flush=True)
    return found


WARMUP_URL = f"{BASE}/en-GB/shop/legio-custodes-custodian-dreadnought-2026"


def _warmup_waf(browser: WhBrowser) -> bool:
    """
    Navigate to a known-good product page first so the WAF token gets
    minted/refreshed before we touch category pages (which are more
    aggressively WAF-gated). Returns True on success.
    """
    print(f"  warmup: {WARMUP_URL}", flush=True)
    html = browser.goto(
        WARMUP_URL, wait_ms=3000, timeout=30000,
        wait_until="domcontentloaded", solve_challenge_interactive=False,
    )
    ok = len(html) > 500_000  # real product pages are ~1MB
    print(f"  warmup: {'OK' if ok else 'FAILED'} ({len(html)} bytes)", flush=True)
    return ok


def discover_via_related_crawl(
    browser: WhBrowser,
    seed_urls: list[str],
    max_products: int = 5000,
    max_pages: int | None = None,
    on_new_product: "callable | None" = None,
) -> set[str]:
    """
    BFS from seed URLs, harvesting product links on each page. Seeds can be
    product URLs OR faction-category URLs — we only care about what `<a href>`s
    render on each page after hydration.

    Category pages are never added to `found` (filter via _normalise_product_url,
    which rejects known-category slugs). Product pages get both (a) added to
    `found` and (b) traversed for their own outbound product links.
    """
    # Seeds that happen to be products go into `found` immediately.
    found: set[str] = set()
    for s in seed_urls:
        norm = _normalise_product_url(s)
        if norm:
            found.add(norm)

    queue: list[str] = list(seed_urls)
    seen: set[str] = set()
    pages_visited = 0

    while queue and len(found) < max_products:
        if max_pages is not None and pages_visited >= max_pages:
            break
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        pages_visited += 1

        html = browser.goto(
            url, wait_ms=2500, timeout=30000,
            wait_until="domcontentloaded", solve_challenge_interactive=False,
        )
        if not html or len(html) < 20_000:
            # WAF-blocked. Try re-warming via a product page, then one retry.
            print(f"       WAF-short ({len(html)} bytes) — re-warming", flush=True)
            _warmup_waf(browser)
            html = browser.goto(
                url, wait_ms=2500, timeout=30000,
                wait_until="domcontentloaded", solve_challenge_interactive=False,
            )
            if not html or len(html) < 20_000:
                print(f"       still WAF-short after retry — skipping", flush=True)
                continue

        # Let lazy-loaded tiles settle before harvesting.
        browser.scroll_to_bottom(max_rounds=8, pause_ms=800)

        new_this_page = 0
        for href in browser.harvest_links():
            norm = _normalise_product_url(href)
            if norm and norm not in found:
                found.add(norm)
                queue.append(norm)
                new_this_page += 1
                if on_new_product:
                    on_new_product(norm)

        print(f"  [{pages_visited:4d}] {url[-70:]:70s}  +{new_this_page:3d} → total {len(found)}",
              flush=True)
        rand_delay(2.0, 4.0)

    return found


# ─── Main orchestrator ──────────────────────────────────────────────────────

def run(
    strategy: str = "crawl",
    limit: int | None = None,
    headless: bool = True,
    max_pages: int | None = None,
) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    existing = _load_existing(PRODUCTS_JSONL)
    print(f"Existing products on disk: {len(existing)}")

    # Incremental-save callback: every new product URL is appended to disk
    # immediately so Ctrl-C / timeout / crash can't throw away hours of BFS.
    def _persist_incremental(url: str) -> None:
        if url not in existing:
            existing[url] = _new_row(url)
            # Cheap path: append one line rather than rewriting the file every time.
            PRODUCTS_JSONL.parent.mkdir(parents=True, exist_ok=True)
            with PRODUCTS_JSONL.open("a") as f:
                f.write(json.dumps(existing[url], ensure_ascii=False) + "\n")

    with WhBrowser(headless=headless, capture_requests=False, profile_dir=PROFILE_DIR) as b:
        # Always warm up WAF with a known-good product page before crawling.
        _warmup_waf(b)
        if strategy == "listing":
            found = discover_via_listing(b, limit=limit)
            if len(found) < 50:
                print(f"  only {len(found)} products found — falling back to crawl",
                      flush=True)
                seeds = list(SEED_URLS) + list(found) + list(existing.keys())
                extra = discover_via_related_crawl(
                    b, seeds, max_products=limit or 5000, max_pages=max_pages,
                    on_new_product=_persist_incremental,
                )
                found |= extra
        else:  # "crawl"
            seeds = list(SEED_URLS) + list(existing.keys())
            found = discover_via_related_crawl(
                b, seeds, max_products=limit or 5000, max_pages=max_pages,
                on_new_product=_persist_incremental,
            )

    # Merge and persist
    added = 0
    for url in found:
        if url not in existing:
            existing[url] = _new_row(url)
            added += 1

    _write_rows(PRODUCTS_JSONL, existing)
    print(f"\n✓ {added} new products added (total on disk: {len(existing)})")
    print(f"  Wrote {PRODUCTS_JSONL}")
    return added


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Discover 40K product URLs on warhammer.com")
    ap.add_argument("--strategy", choices=["listing", "crawl"], default="crawl",
                    help="'crawl' seeds with known faction URLs + BFS (recommended). "
                         "'listing' tries the WAF-sensitive 40K landing first.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap total product URLs found (default: no cap)")
    ap.add_argument("--max-pages", type=int, default=None,
                    help="Cap total pages visited (default: no cap)")
    ap.add_argument("--headed", action="store_true",
                    help="Run browser in headed mode (useful for debugging)")
    args = ap.parse_args(argv)

    n = run(strategy=args.strategy, limit=args.limit, headless=not args.headed,
            max_pages=args.max_pages)
    return 0 if n >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
