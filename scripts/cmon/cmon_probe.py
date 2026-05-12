#!/usr/bin/env python3
"""
Tiny probe — fetch three candidate listing endpoints for the 'single' run
and print response length + tile count so we can see what CMON is actually
serving. Writes full bodies to scripts/cmon/recon/probe_{slug}.html for
inspection.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlencode

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cmon_browser import BASE, CmonBrowser  # noqa: E402
from cmon_parse import parse_tiles  # noqa: E402


TARGETING = json.load(open(HERE / "targeting.json"))
RUN = next(r for r in TARGETING["runs"] if r["name"] == "single")
FILTERS = dict(TARGETING["fixed_filters"])
FILTERS["type_id"] = RUN["type_id"]
QS = urlencode(FILTERS, doseq=True)

URLS = [
    ("browse",       f"{BASE}/browse?{QS}",        "html"),
    ("browse_raw_1", f"{BASE}/browse/raw/1?{QS}",  "xhr"),
    ("browse_raw_2", f"{BASE}/browse/raw/2?{QS}",  "xhr"),
]

OUT = HERE / "recon"
OUT.mkdir(exist_ok=True)


def main():
    with CmonBrowser(headless=False) as b:
        b.warm_session()
        for slug, url, mode in URLS:
            if mode == "xhr":
                body = b.fetch_xhr_text(url) or ""
                title = "(xhr)"
                final_url = url
            else:
                body = b.fetch_html(url) or ""
                title = b.eval_title() or ""
                final_url = b.current_url() or ""
            tiles = parse_tiles(body)
            head = (body[:200] or "").replace("\n", " ")
            fpath = OUT / f"probe_{slug}.html"
            fpath.write_text(body)
            print(f"  {slug:14} [{mode}] {len(body):>8}B  tiles={len(tiles):>3}",
                  flush=True)
            print(f"                 title={title[:80]!r}", flush=True)
            print(f"                 url  ={final_url[:120]}", flush=True)
            print(f"                 head ={head[:160]!r}", flush=True)


if __name__ == "__main__":
    main()
