#!/usr/bin/env python3
"""
Unified CLI for the warhammer.com scraper.

Subcommands:
    bootstrap   — headed browser, solve AWS WAF CAPTCHA once (persists cookies)
    discover    — enumerate 40K product URLs into state/products.jsonl
    scrape      — walk products.jsonl, download images, append manifest rows
    test-probe  — quick validation: scrape 2 known URLs and assert pipeline health
    status      — print counts of products / images / manifest rows

Usage:
    yolo_env/bin/python3 scripts/warhammer_com/gw_shop_cli.py bootstrap
    yolo_env/bin/python3 scripts/warhammer_com/gw_shop_cli.py discover
    yolo_env/bin/python3 scripts/warhammer_com/gw_shop_cli.py scrape --limit 10
    yolo_env/bin/python3 scripts/warhammer_com/gw_shop_cli.py test-probe
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from gw_shop_constants import (  # noqa: E402
    IMAGES_ROOT,
    PROBE_URLS,
    PRODUCTS_JSONL,
)


def cmd_bootstrap(_args) -> int:
    import bootstrap_waf  # noqa: PLC0415
    return bootstrap_waf.main()


def cmd_discover(args) -> int:
    import gw_shop_discover  # noqa: PLC0415
    return gw_shop_discover.main(
        [
            "--strategy", args.strategy,
            *(["--limit", str(args.limit)] if args.limit else []),
            *(["--max-pages", str(args.max_pages)] if args.max_pages else []),
            *(["--headed"] if args.headed else []),
        ]
    )


def cmd_scrape(args) -> int:
    import gw_shop_scrape  # noqa: PLC0415
    argv = []
    if args.limit:
        argv += ["--limit", str(args.limit)]
    if args.factions:
        argv += ["--factions", args.factions]
    if args.headed:
        argv += ["--headed"]
    return gw_shop_scrape.main(argv)


def cmd_test_probe(args) -> int:
    """
    Scrape two known-good recon URLs + one Space Marines kit, print a summary.
    Full pytest assertions live in tests/test_probe.py.
    """
    import gw_shop_scrape  # noqa: PLC0415
    probe_urls = list(PROBE_URLS)
    if args.plus_space_marines:
        probe_urls.append(
            "https://www.warhammer.com/en-GB/shop/space-marines-primaris-intercessors-2020"
        )
    print(f"Probe URLs ({len(probe_urls)}):")
    for u in probe_urls:
        print(f"  · {u}")
    stats = gw_shop_scrape.run(
        only_urls=probe_urls,
        headless=not args.headed,
    )
    print("\n── Probe summary ──")
    print(stats.summary())

    # Quick on-disk sanity check
    n_images = sum(1 for _ in IMAGES_ROOT.rglob("*.jpg")) if IMAGES_ROOT.exists() else 0
    print(f"\nImages on disk under {IMAGES_ROOT}: {n_images}")
    return 0 if stats.products_scraped > 0 else 1


def cmd_status(_args) -> int:
    n_products = 0
    n_scraped = 0
    if PRODUCTS_JSONL.exists():
        with PRODUCTS_JSONL.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                n_products += 1
                if row.get("scraped_at"):
                    n_scraped += 1

    n_images = sum(1 for _ in IMAGES_ROOT.rglob("*.jpg")) if IMAGES_ROOT.exists() else 0
    n_faction_dirs = (
        len([d for d in IMAGES_ROOT.iterdir() if d.is_dir()])
        if IMAGES_ROOT.exists() else 0
    )
    n_unit_dirs = (
        sum(1 for d in IMAGES_ROOT.rglob("*") if d.is_dir() and d.parent != IMAGES_ROOT)
        if IMAGES_ROOT.exists() else 0
    )
    print(f"products.jsonl:    {n_products} total, {n_scraped} scraped")
    print(f"images on disk:    {n_images}")
    print(f"faction folders:   {n_faction_dirs}")
    print(f"unit folders:      {n_unit_dirs}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="warhammer.com 40K scraper — unified CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("bootstrap", help="Open headed browser; solve WAF once")

    p_discover = sub.add_parser("discover", help="Enumerate 40K product URLs")
    p_discover.add_argument("--strategy", choices=["listing", "crawl"], default="crawl")
    p_discover.add_argument("--limit", type=int, default=None)
    p_discover.add_argument("--max-pages", type=int, default=None)
    p_discover.add_argument("--headed", action="store_true")

    p_scrape = sub.add_parser("scrape", help="Download images for unprocessed products")
    p_scrape.add_argument("--limit", type=int, default=None)
    p_scrape.add_argument("--factions", type=str, default="")
    p_scrape.add_argument("--headed", action="store_true")

    p_probe = sub.add_parser("test-probe", help="Run the 2-3 URL verification probe")
    p_probe.add_argument("--plus-space-marines", action="store_true",
                         help="Also test a Space Marines kit (requires a valid URL)")
    p_probe.add_argument("--headed", action="store_true")

    sub.add_parser("status", help="Show counts of discovered / scraped / saved")

    args = ap.parse_args(argv)

    dispatch = {
        "bootstrap": cmd_bootstrap,
        "discover": cmd_discover,
        "scrape": cmd_scrape,
        "test-probe": cmd_test_probe,
        "status": cmd_status,
    }
    return dispatch[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
