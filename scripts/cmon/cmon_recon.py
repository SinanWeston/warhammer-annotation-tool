#!/usr/bin/env python3
"""
CMON recon — open one or more URLs in a persistent, user-assisted Playwright
session and dump raw artefacts so we can design the rest of the pipeline
against real DOM / real API responses.

First run: the browser window pops up on coolminiornot.com's homepage. The
user solves the Cloudflare challenge manually. The `cf_clearance` cookie is
persisted in the profile and reused on every subsequent navigation.

For each target URL, writes to scripts/cmon/recon/{slug}/:
  html.html              rendered DOM
  img_urls.json          all img/source URLs visible on the page
  links.json             all <a href> values
  title.txt              H1 text (or <title> fallback)
  captured_requests.json api/graphql/search network traffic captured during load
  url.txt                final URL after redirects

Usage:
    fiftyone_env/bin/python3 scripts/cmon/cmon_recon.py
        (defaults: homepage + a placeholder WH40K listing URL)

    fiftyone_env/bin/python3 scripts/cmon/cmon_recon.py \\
        https://www.coolminiornot.com/ \\
        https://www.coolminiornot.com/browse/figure?game=Warhammer+40K

    fiftyone_env/bin/python3 scripts/cmon/cmon_recon.py --scroll 10 <url>
        (scroll to bottom up to 10 times before capturing — for lazy-loading
        galleries)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cmon_browser import BASE, CmonBrowser, rand_delay  # noqa: E402

RECON_DIR = HERE / "recon"


DEFAULT_TARGETS = [
    BASE + "/",
    # Placeholder — CMON's actual browse path is unknown until recon;
    # user will override via CLI after first-pass discovery.
    BASE + "/browse",
]


def slugify_url(url: str) -> str:
    p = urlparse(url)
    raw = (p.path.strip("/") or "root") + ("?" + p.query if p.query else "")
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw).strip("_").lower()
    return slug[:80] or "root"


def dump_target(browser: CmonBrowser, url: str, scroll: int, outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"\n▶ {url}", flush=True)
    browser.clear_captured_requests()
    html = browser.goto(url, wait_ms=3000, wait_until="networkidle")
    if scroll:
        rounds = browser.scroll_to_bottom(max_rounds=scroll, pause_ms=1200)
        print(f"  scrolled {rounds} round(s)", flush=True)
        html = browser.current_content()

    (outdir / "url.txt").write_text(browser.current_url() + "\n")
    (outdir / "html.html").write_text(html or "")
    (outdir / "title.txt").write_text((browser.eval_title() or "") + "\n")

    img_urls = browser.eval_img_urls()
    (outdir / "img_urls.json").write_text(json.dumps(img_urls, indent=2))

    links = browser.harvest_links()
    (outdir / "links.json").write_text(json.dumps(links, indent=2))

    captured = browser.captured_requests()
    (outdir / "captured_requests.json").write_text(json.dumps(captured, indent=2))

    print(f"  html={len(html or '')}B imgs={len(img_urls)} "
          f"links={len(links)} captured={len(captured)}", flush=True)
    print(f"  → {outdir}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="*", default=DEFAULT_TARGETS,
                    help="URLs to recon (default: homepage + /browse)")
    ap.add_argument("--scroll", type=int, default=0,
                    help="Scroll to bottom N times before capture (for lazy lists)")
    ap.add_argument("--headless", action="store_true",
                    help="Run headless (won't work on first run — need visible "
                         "window to solve CF challenge)")
    args = ap.parse_args()

    RECON_DIR.mkdir(parents=True, exist_ok=True)

    with CmonBrowser(headless=args.headless, capture_requests=True) as b:
        for url in args.urls:
            slug = slugify_url(url)
            dump_target(b, url, scroll=args.scroll, outdir=RECON_DIR / slug)
            rand_delay(2.0, 4.0)

    print(f"\nDone. Artefacts under {RECON_DIR}", flush=True)


if __name__ == "__main__":
    main()
