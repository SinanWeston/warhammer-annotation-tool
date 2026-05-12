#!/usr/bin/env python3
"""
Stage 0 recon spike — dump raw artefacts from three sample warhammer.com pages
so the rest of the pipeline can be designed against real DOM / real API
responses rather than guesses.

Targets:
  1. Shop / 40K landing           (to discover faction URL structure)
  2. Single-unit product          (to discover image carousel + metadata)
  3. Combat Patrol product        (to decide per-unit vs group-shot policy)

For each page, saves into scripts/warhammer_com/recon/:
  {slug}_html.html                rendered DOM after hydration
  {slug}_next_data.json           window.__NEXT_DATA__ (if present)
  {slug}_window_keys.json         interesting window globals
  {slug}_imgs.json                list of img/source URLs
  {slug}_breadcrumb.json          extracted breadcrumb text
  {slug}_title.txt                H1 text
  {slug}_carousel_imgs.json       img URLs AFTER clicking carousel "next" fully
  {slug}_algolia.json             captured algolia network requests/responses

Plus a consolidated summary.md with quick findings.

Usage:
    yolo_env/bin/python3 scripts/warhammer_com/recon.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from wh_browser import WhBrowser, rand_delay  # noqa: E402

RECON_DIR = HERE / "recon"

TARGETS = [
    {
        "slug": "00_shop_40k_landing",
        "url": "https://www.warhammer.com/en-GB/shop/warhammer-40000",
        "note": "Entry point — should surface faction categories.",
        "click_carousel": False,
    },
    {
        "slug": "01_single_unit_custodian_dreadnought",
        "url": "https://www.warhammer.com/en-GB/shop/legio-custodes-custodian-dreadnought-2026",
        "note": "User-provided exemplar of a single-unit product page.",
        "click_carousel": True,
    },
    {
        "slug": "02_combat_patrol_kroot",
        "url": "https://www.warhammer.com/en-GB/shop/combat-patrol-kroot-2026",
        "note": "User-provided exemplar of a combat patrol; check contents list structure.",
        "click_carousel": True,
    },
]


def dump(path: Path, data) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        text = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    else:
        text = str(data) if data is not None else ""
    path.write_text(text)
    return len(text)


def probe(browser: WhBrowser, target: dict) -> dict:
    slug = target["slug"]
    print(f"\n── {slug} ──")
    print(f"   {target['url']}")
    browser.clear_captured_requests()

    html = browser.goto(target["url"], wait_ms=3000)
    if not html:
        print("   ⚠ empty HTML — navigation failed")
        return {"slug": slug, "status": "empty", "url": target["url"]}

    title = browser.eval_title()
    imgs_pre = browser.eval_img_urls()
    next_data = browser.eval_next_data()
    win_keys = browser.eval_window_keys()
    breadcrumb = browser.eval_breadcrumb()
    algolia = browser.captured_requests()

    # Try carousel click-through to reveal lazily-injected slides.
    carousel_clicks = 0
    imgs_post = imgs_pre
    if target.get("click_carousel"):
        carousel_clicks = browser.click_carousel_next(max_clicks=20)
        imgs_post = browser.eval_img_urls()

    # Sanitise sizes/summaries for the return dict (full payloads go to disk).
    res = {
        "slug": slug,
        "url": target["url"],
        "status": "ok",
        "title": title,
        "html_bytes": len(html),
        "img_count_pre": len(imgs_pre),
        "img_count_post": len(imgs_post),
        "carousel_clicks": carousel_clicks,
        "window_keys": win_keys,
        "breadcrumb": breadcrumb,
        "next_data_present": next_data is not None,
        "algolia_events": len(algolia),
    }

    # Persist everything to disk.
    dump(RECON_DIR / f"{slug}_html.html", html)
    dump(RECON_DIR / f"{slug}_title.txt", title)
    dump(RECON_DIR / f"{slug}_imgs.json", imgs_pre)
    if imgs_post != imgs_pre:
        dump(RECON_DIR / f"{slug}_carousel_imgs.json", imgs_post)
    dump(RECON_DIR / f"{slug}_window_keys.json", win_keys)
    dump(RECON_DIR / f"{slug}_breadcrumb.json", breadcrumb)
    if next_data is not None:
        dump(RECON_DIR / f"{slug}_next_data.json", next_data)
    if algolia:
        dump(RECON_DIR / f"{slug}_algolia.json", algolia)

    print(f"   status={res['status']}  title={title[:60]!r}")
    print(f"   html={res['html_bytes']} bytes  imgs={res['img_count_pre']} → {res['img_count_post']} "
          f"(carousel {carousel_clicks} clicks)")
    print(f"   window globals matching regex: {win_keys}")
    print(f"   breadcrumb: {' > '.join(breadcrumb) if breadcrumb else '<none>'}")
    print(f"   algolia events captured: {res['algolia_events']}")
    return res


def warhammer_image_hosts(urls: list[str]) -> dict[str, int]:
    tally: dict[str, int] = {}
    for u in urls:
        try:
            host = urlparse(u).netloc
        except Exception:
            continue
        tally[host] = tally.get(host, 0) + 1
    return dict(sorted(tally.items(), key=lambda kv: -kv[1]))


def summarise(results: list[dict]):
    lines = ["# Stage 0 recon — warhammer.com\n"]
    for r in results:
        lines.append(f"\n## {r['slug']}\n")
        lines.append(f"- URL: {r['url']}")
        lines.append(f"- Status: {r['status']}")
        if r["status"] != "ok":
            continue
        lines.append(f"- Title: `{r['title']}`")
        lines.append(f"- Rendered HTML: {r['html_bytes']:,} bytes")
        lines.append(f"- Image URLs discovered: {r['img_count_pre']} "
                     f"(post-carousel: {r['img_count_post']}, clicks: {r['carousel_clicks']})")
        lines.append(f"- Breadcrumb: {' > '.join(r['breadcrumb']) if r['breadcrumb'] else '—'}")
        lines.append(f"- Window globals (regex filter): {r['window_keys']}")
        lines.append(f"- `window.__NEXT_DATA__` present: {r['next_data_present']}")
        lines.append(f"- Captured Algolia-like network events: {r['algolia_events']}")
        # Host tally
        imgs = json.loads((RECON_DIR / f"{r['slug']}_imgs.json").read_text())
        tally = warhammer_image_hosts(imgs)
        lines.append(f"- Image host tally: {tally}")
    (RECON_DIR / "SUMMARY.md").write_text("\n".join(lines))


def main():
    RECON_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Recon output dir: {RECON_DIR}")
    results = []
    with WhBrowser(headless=False, capture_requests=True) as browser:
        for i, target in enumerate(TARGETS):
            try:
                results.append(probe(browser, target))
            except Exception as e:
                print(f"   ! probe crashed: {e}")
                results.append({"slug": target["slug"], "status": f"crash: {e}",
                                "url": target["url"]})
            if i < len(TARGETS) - 1:
                rand_delay(3.0, 6.0)

    summarise(results)
    print(f"\nSummary: {RECON_DIR / 'SUMMARY.md'}")
    print("Inspect the artefacts, then move on to Stage 1a (algolia_probe).")


if __name__ == "__main__":
    main()
