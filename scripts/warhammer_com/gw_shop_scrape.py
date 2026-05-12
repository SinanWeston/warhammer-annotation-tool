#!/usr/bin/env python3
"""
Stage 2 — Per-product scraper for the warhammer.com 40K shop.

For each unprocessed row in state/products.jsonl:
  1. Navigate to the product URL (WAF handled by wh_browser).
  2. Extract window.__NEXT_DATA__ → ProductPayload (name, sku, images, product_type).
  3. For each image URL:
       - Skip 360° frames, sprues, paint sets, books.
       - Parse filename (SKU + PascalCase unit name + idx).
       - Infer faction (filename prefix → URL slug fallback).
       - Download at max resolution via browser.fetch_bytes() (reuses cookies).
       - Quality-check + dedup via scraper_utils.quality_check_bytes.
       - Save to scripts/warhammer_com/images/{faction}/{unit_slug}/{basename}
       - Append one row to training_data_v2/metadata/scrape_log.csv.
  4. Update the products.jsonl row with scraped_at + counts.

Usage:
    yolo_env/bin/python3 scripts/warhammer_com/gw_shop_scrape.py
    yolo_env/bin/python3 scripts/warhammer_com/gw_shop_scrape.py --limit 5
    yolo_env/bin/python3 scripts/warhammer_com/gw_shop_scrape.py --factions tau_empire,space_marines
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from gw_shop_constants import (  # noqa: E402
    BASE,
    IMAGES_ROOT,
    MAX_WIDTH_QS,
    PRODUCTS_JSONL,
    PROFILE_DIR,
    SOURCE_PLATFORM,
    STATE_DIR,
    UNPARSEABLE_LOG,
)
from gw_shop_parse import (  # noqa: E402
    ImageMeta,
    ProductPayload,
    SchemaError,
    _pretty_from_camel,
    camel_to_snake,
    classify_image_type,
    constituent_unit_name,
    extract_product_payload,
    has_skip_token,
    infer_faction,
    is_box_product,
    parse_image_filename,
)
from scraper_utils import (  # noqa: E402
    BASE_DIR,
    USER_AGENTS,
    init_csv,
    load_known_hashes,
    log_image,
    now_iso,
    quality_check_bytes,
    rand_delay,
    save_hash,
)
from wh_browser import WhBrowser  # noqa: E402


def _download_image(url: str, session: requests.Session, timeout: float = 30.0) -> bytes | None:
    """
    Plain HTTP download of a /app/resources/catalog/product/... image. Requires
    no WAF cookies (verified via curl). Uses a rotating User-Agent.
    """
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        resp = session.get(url, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return None
        return resp.content
    except requests.RequestException as e:
        print(f"     ✖ requests error: {type(e).__name__}: {str(e)[:80]}", flush=True)
        return None


# ─── Stats ──────────────────────────────────────────────────────────────────

@dataclass
class ScrapeStats:
    products_seen: int = 0
    products_scraped: int = 0
    products_skipped: int = 0
    products_errored: int = 0
    images_saved: int = 0
    images_deduped: int = 0
    images_skipped_type: int = 0
    images_unparseable: int = 0
    images_failed: int = 0

    def summary(self) -> str:
        return (
            f"products: seen={self.products_seen} scraped={self.products_scraped} "
            f"skipped={self.products_skipped} errored={self.products_errored}\n"
            f"images:   saved={self.images_saved} deduped={self.images_deduped} "
            f"skipped_type={self.images_skipped_type} "
            f"unparseable={self.images_unparseable} failed={self.images_failed}"
        )


# ─── JSONL helpers ──────────────────────────────────────────────────────────

def _load_rows(path: Path) -> dict[str, dict]:
    """Load products.jsonl into a url→row dict."""
    rows: dict[str, dict] = {}
    if not path.exists():
        return rows
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("url"):
                rows[row["url"]] = row
    return rows


def _write_rows(path: Path, rows: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        for url in sorted(rows.keys()):
            f.write(json.dumps(rows[url], ensure_ascii=False) + "\n")
    tmp.replace(path)


def _log_unparseable(url: str, reason: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with UNPARSEABLE_LOG.open("a") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()}\t{reason}\t{url}\n")


# ─── Core scrape logic ──────────────────────────────────────────────────────

def _should_skip_product_type(product_type: str) -> bool:
    """Non-miniature product types to skip entirely."""
    pt = (product_type or "").lower()
    return pt in {
        "paintbundle", "paint", "paints",
        "book", "rulebook", "codex",
        "cards", "datasheetcards",
        "hobbytool", "modellingtool",
        "glue", "basingmaterial",
        "giftvoucher",
        "digitalcontent",
    }


class ShopScraper:
    def __init__(self, browser: WhBrowser, known_hashes: set[str], workers: int = 6):
        self.browser = browser
        self.known_hashes = known_hashes
        self.stats = ScrapeStats()
        self.http = requests.Session()
        # Lock serialises access to shared state that isn't GIL-atomic:
        # duplicates.txt append, scrape_log.csv append, stats increments, and
        # the known-hashes check-then-add critical section.
        self._lock = threading.Lock()
        self._workers = workers

    def _payload_from_row(self, row: dict) -> ProductPayload | None:
        """
        If a row was pre-populated by algolia_discover (has `images` list +
        name + master_sku + product_type), build a ProductPayload directly
        without loading the product page. Returns None if row lacks the
        required fields — in that case the caller should fall back to the
        browser-based path.
        """
        imgs = row.get("images")
        if not imgs or not isinstance(imgs, list):
            return None
        if not row.get("name") or not row.get("master_sku"):
            return None
        return ProductPayload(
            product_id=row.get("product_id", ""),
            name=row["name"],
            url_slug=row.get("url_slug", ""),
            master_sku=row["master_sku"],
            product_type_name=row.get("product_type", ""),
            image_urls=list(imgs),
        )

    def scrape_product(self, row: dict) -> dict:
        """
        Download images for one product. When the row was pre-populated by
        algolia_discover, we skip browser navigation entirely — fast path.
        Otherwise we fall back to the original browser-driven NEXT_DATA path.

        Returns the updated row (in place; caller persists).
        """
        url = row["url"]
        slug = row.get("url_slug") or url.rsplit("/", 1)[-1]
        # Prefer Algolia-sourced faction when present; _process_one_image
        # falls back to filename inference only when this is 'unknown'.
        faction_hint = row.get("faction_hint") or "unknown"
        self.stats.products_seen += 1
        print(f"── {slug}", flush=True)

        # Fast path: Algolia-enriched row
        payload = self._payload_from_row(row)
        if payload is None:
            # Slow path: load page, parse NEXT_DATA
            html = self.browser.goto(url, wait_ms=2500) if self.browser else ""
            if not html:
                row["scraped_at"] = now_iso()
                row["error"] = "empty html / navigation failed"
                self.stats.products_errored += 1
                return row
            next_data = self.browser.eval_next_data()
            if not next_data:
                row["scraped_at"] = now_iso()
                row["error"] = "no __NEXT_DATA__ on page"
                self.stats.products_errored += 1
                return row
            try:
                payload = extract_product_payload(next_data, url_slug=slug)
            except SchemaError as e:
                row["scraped_at"] = now_iso()
                row["error"] = f"schema: {e}"
                self.stats.products_errored += 1
                return row
            row["product_id"] = payload.product_id
            row["master_sku"] = payload.master_sku
            row["name"] = payload.name
            row["product_type"] = payload.product_type_name

        if _should_skip_product_type(payload.product_type_name):
            row["scraped_at"] = now_iso()
            row["error"] = f"skipped product_type={payload.product_type_name}"
            self.stats.products_skipped += 1
            print(f"   · skipped (product_type={payload.product_type_name})")
            return row

        is_box = is_box_product(payload.product_type_name, payload.name)

        # Parallel image download + quality-check within a single product.
        # Thread-safe: _process_one_image uses self._lock for shared writes.
        if self._workers > 1 and len(payload.image_urls) > 1:
            with ThreadPoolExecutor(max_workers=self._workers) as ex:
                results = list(ex.map(
                    lambda raw: self._process_one_image(
                        raw, payload, is_box, page_url=url, faction_hint=faction_hint,
                    ),
                    payload.image_urls,
                ))
        else:
            results = [
                self._process_one_image(
                    raw, payload, is_box, page_url=url, faction_hint=faction_hint,
                )
                for raw in payload.image_urls
            ]
        saved = sum(1 for r in results if r == "saved")
        skipped = len(results) - saved

        row["scraped_at"] = now_iso()
        row["images_saved"] = saved
        row["images_skipped"] = skipped
        row["error"] = None
        self.stats.products_scraped += 1
        print(
            f"   {payload.name}  sku={payload.master_sku}  imgs={len(payload.image_urls)}  "
            f"saved={saved} skipped={skipped}",
            flush=True,
        )
        return row

    def _process_one_image(
        self,
        raw_url: str,
        payload: ProductPayload,
        is_box: bool,
        page_url: str,
        faction_hint: str = "unknown",
    ) -> str:
        """
        Download + save one image. Returns a short status token:
          'saved' | 'unparseable' | 'skip_type' | 'skip_3sixty' | 'dedup' | 'failed'
        """
        # Parse + filter
        meta = parse_image_filename(raw_url)
        if meta is None:
            self.stats.images_unparseable += 1
            _log_unparseable(raw_url, "no-match")
            return "unparseable"

        if meta.is_three_sixty:
            self.stats.images_skipped_type += 1
            return "skip_3sixty"

        if has_skip_token(meta.name):
            self.stats.images_skipped_type += 1
            return "skip_type"

        # Faction + unit.
        # Prefer Algolia-sourced faction_hint (authoritative when present);
        # fall back to filename+slug heuristic only when it's 'unknown'.
        if faction_hint and faction_hint != "unknown":
            faction = faction_hint
        else:
            faction = infer_faction(meta.name, payload.url_slug)
        unit_slug = camel_to_snake(meta.name)
        if not unit_slug:
            self.stats.images_unparseable += 1
            _log_unparseable(raw_url, "empty-unit-slug")
            return "unparseable"

        # Unit name display
        if is_box:
            unit_name = constituent_unit_name(meta, payload)
        else:
            unit_name = payload.name or _pretty_from_camel(meta.name)

        image_type = classify_image_type(meta, is_box, payload.master_sku, box_name=payload.name)

        # Build full download URL
        # raw_url is relative like "/app/resources/catalog/product/920x950/{basename}"
        # or absolute like "https://www.warhammer.com/app/...".
        if raw_url.startswith("/"):
            full_url = f"{BASE}{raw_url}{MAX_WIDTH_QS}"
        elif raw_url.startswith("http"):
            full_url = raw_url + (MAX_WIDTH_QS if "?" not in raw_url else "")
        else:
            full_url = f"{BASE}/{raw_url}{MAX_WIDTH_QS}"

        body = _download_image(full_url, self.http)
        if not body:
            with self._lock:
                self.stats.images_failed += 1
            print(f"     ✖ download failed: {meta.basename}", flush=True)
            return "failed"

        # Quality-check + dedup + normalise.
        # Critical section: hash check + add + save_hash + log_image must be
        # atomic so concurrent workers don't both persist the same image.
        with self._lock:
            checked = quality_check_bytes(body, self.known_hashes)
            if checked is None:
                self.stats.images_deduped += 1
                return "dedup"
            jpg_bytes, w, h, md5 = checked

            out_dir = IMAGES_ROOT / faction / unit_slug
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / meta.basename
            out_path.write_bytes(jpg_bytes)

            save_hash(md5)
            self.known_hashes.add(md5)

            try:
                rel_filename = str(out_path.relative_to(BASE_DIR))
            except ValueError:
                rel_filename = str(out_path)
            log_image({
                "filename": rel_filename,
                "unit_name": unit_name,
                "faction": faction,
                "image_type": image_type,
                "source_url": full_url,
                "page_url": page_url,
                "source_platform": SOURCE_PLATFORM,
                "width_px": w,
                "height_px": h,
                "file_hash": md5,
                "search_query": "",
                "timestamp": now_iso(),
            })
            self.stats.images_saved += 1
        return "saved"


# ─── CLI runner ─────────────────────────────────────────────────────────────

def run(
    from_jsonl: Path = PRODUCTS_JSONL,
    limit: int | None = None,
    factions_only: set[str] | None = None,
    headless: bool = True,
    only_urls: list[str] | None = None,
) -> ScrapeStats:
    """
    Walk products.jsonl and scrape unprocessed products.

    Fast path: when every target row has pre-populated `images` (from
    algolia_discover), we skip the browser entirely — pure requests downloads.
    Slow path: legacy per-page NEXT_DATA extraction via Playwright.

    only_urls: if non-empty, scrape only these URLs (used by test-probe).
    """
    IMAGES_ROOT.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    init_csv()
    known_hashes = load_known_hashes()
    print(f"Known image hashes loaded: {len(known_hashes)}")

    rows = _load_rows(from_jsonl)
    print(f"Products on disk: {len(rows)}")

    if only_urls:
        for u in only_urls:
            if u not in rows:
                rows[u] = {
                    "url": u,
                    "url_slug": u.rsplit("/", 1)[-1],
                    "discovered_at": now_iso(),
                    "scraped_at": None,
                }
        targets = [rows[u] for u in only_urls]
    else:
        targets = [r for r in rows.values() if not r.get("scraped_at")]
        if factions_only:
            targets = [r for r in targets if r.get("faction_hint") in factions_only]
        if limit:
            targets = targets[:limit]

    print(f"Targets to scrape this run: {len(targets)}")

    # Decide fast vs slow path: browser only needed if any target lacks images.
    need_browser = any(not (r.get("images") and r.get("name")) for r in targets)

    browser_ctx: WhBrowser | None = None
    try:
        if need_browser:
            browser_ctx = WhBrowser(
                headless=headless, capture_requests=False, profile_dir=PROFILE_DIR,
            )
            scraper = ShopScraper(browser_ctx, known_hashes)
        else:
            print("  fast path: all targets have pre-populated images (no browser needed)")
            scraper = ShopScraper(None, known_hashes)  # type: ignore[arg-type]

        for i, row in enumerate(targets):
            updated = scraper.scrape_product(row)
            rows[updated["url"]] = updated
            # Persist after every product — Ctrl-C safe.
            _write_rows(from_jsonl, rows)
            # Inter-product delay only on slow (browser) path; fast path is
            # bounded by download throughput already.
            if need_browser and i < len(targets) - 1:
                rand_delay(3.0, 6.0)
    finally:
        if browser_ctx is not None:
            browser_ctx.close()

    print("\n" + scraper.stats.summary())
    return scraper.stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scrape 40K product pages on warhammer.com")
    ap.add_argument("--limit", type=int, default=None,
                    help="Stop after N products this run")
    ap.add_argument("--factions", type=str, default="",
                    help="Comma-separated faction slugs to restrict (best-effort post-scrape)")
    ap.add_argument("--headed", action="store_true",
                    help="Run browser in headed mode (useful for debugging)")
    args = ap.parse_args(argv)

    factions = {f.strip() for f in args.factions.split(",") if f.strip()} or None
    run(limit=args.limit, factions_only=factions, headless=not args.headed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
