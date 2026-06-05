#!/usr/bin/env python3
"""
CMON discover — walk /browse/raw/{page} for a given run and append every tile
to scripts/cmon/data/discover_{run}.jsonl.

Reads filter values from scripts/cmon/targeting.json. Resume-safe: stores
{last_page_done, total_tiles, seen_ids[]} in scripts/cmon/state/discover_{run}.json
and only continues from there.

Usage:
    fiftyone_env/bin/python3 scripts/cmon/cmon_discover.py single
    fiftyone_env/bin/python3 scripts/cmon/cmon_discover.py single --max-pages 200
    fiftyone_env/bin/python3 scripts/cmon/cmon_discover.py single --dry-run  (no writes)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cmon_browser import BASE, CmonBrowser, rand_delay  # noqa: E402
from cmon_parse import parse_tiles  # noqa: E402


TARGETING = json.load(open(HERE / "targeting.json"))
DATA_DIR = HERE / "data"
STATE_DIR = HERE / "state"
LOG_DIR = HERE / "logs"
DATA_DIR.mkdir(exist_ok=True)
STATE_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)


def run_spec(run_name: str) -> dict:
    for r in TARGETING["runs"]:
        if r["name"] == run_name:
            return r
    raise SystemExit(f"run '{run_name}' not in targeting.json (available: "
                     f"{[r['name'] for r in TARGETING['runs']]})")


def build_listing_url(run: dict, page: int) -> str:
    """
    All pages come from /browse/raw/{page}?{filters}, fetched as XHR from
    the /browse page's JS context. Top-level navigation to /browse/raw/*
    returns 403 — the endpoint requires X-Requested-With + a /browse
    Referer, which the browser supplies automatically when called via
    page.evaluate(fetch()).
    """
    params = dict(TARGETING["fixed_filters"])
    tid = run.get("type_id")
    if tid is not None:
        params["type_id"] = tid
    qs = urlencode(params, doseq=True)
    return f"{BASE}{TARGETING['listing_raw_path']}/{page}?{qs}"


def load_state(run_name: str) -> dict:
    p = STATE_DIR / f"discover_{run_name}.json"
    if p.exists():
        return json.load(open(p))
    return {"last_page_done": 0, "total_tiles": 0, "seen_ids": []}


def save_state(run_name: str, state: dict):
    p = STATE_DIR / f"discover_{run_name}.json"
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", help="Run name from targeting.json (e.g. 'single')")
    ap.add_argument("--max-pages", type=int, default=5000,
                    help="Safety cap on pages to walk (default 5000)")
    ap.add_argument("--stop-after-empty", type=int, default=2,
                    help="Stop after N consecutive empty/dup pages (default 2)")
    ap.add_argument("--delay-lo", type=float, default=2.0)
    ap.add_argument("--delay-hi", type=float, default=5.0)
    ap.add_argument("--dry-run", action="store_true", help="Don't write discover jsonl")
    args = ap.parse_args()

    run = run_spec(args.run)
    print(f"▶ discover run={args.run} type_id={run['type_id']} "
          f"({run['label']})", flush=True)

    state = load_state(args.run)
    seen_ids = set(state["seen_ids"])
    start_page = state["last_page_done"] + 1
    print(f"  resuming from page {start_page}; already have {len(seen_ids)} tiles",
          flush=True)

    jsonl_path = DATA_DIR / f"discover_{args.run}.jsonl"
    jsonl_fp = None
    if not args.dry_run:
        jsonl_fp = open(jsonl_path, "a", buffering=1)  # line-buffered

    empty_streak = 0
    added = 0
    with CmonBrowser(headless=False) as b:
        b.warm_session()
        page = start_page
        while page <= args.max_pages:
            url = build_listing_url(run, page)
            html = b.fetch_xhr_text(url) or ""
            tiles = parse_tiles(html)
            new_tiles = [t for t in tiles if t.id not in seen_ids]

            print(f"  page={page:4} got={len(tiles):3} new={len(new_tiles):3} "
                  f"total_seen={len(seen_ids) + len(new_tiles)}", flush=True)

            if not tiles:
                empty_streak += 1
                print(f"    (empty — streak={empty_streak}/{args.stop_after_empty})",
                      flush=True)
                if empty_streak >= args.stop_after_empty:
                    print("  halting: consecutive empty pages", flush=True)
                    break
            elif not new_tiles:
                empty_streak += 1
                print(f"    (no new ids — streak={empty_streak}/{args.stop_after_empty})",
                      flush=True)
                if empty_streak >= args.stop_after_empty:
                    print("  halting: pages producing duplicates only", flush=True)
                    break
            else:
                empty_streak = 0
                for t in new_tiles:
                    seen_ids.add(t.id)
                    rec = t.to_jsonable()
                    rec["type_id"] = run["type_id"]
                    rec["run"] = args.run
                    rec["page"] = page
                    if jsonl_fp:
                        jsonl_fp.write(json.dumps(rec) + "\n")
                added += len(new_tiles)

            state["last_page_done"] = page
            state["total_tiles"] = len(seen_ids)
            state["seen_ids"] = sorted(seen_ids)
            if not args.dry_run:
                save_state(args.run, state)

            page += 1
            rand_delay(args.delay_lo, args.delay_hi)

    if jsonl_fp:
        jsonl_fp.close()
    print(f"\nDone. {added} new tiles written to {jsonl_path}", flush=True)
    print(f"     {len(seen_ids)} total tiles discovered across all runs.", flush=True)


if __name__ == "__main__":
    main()
