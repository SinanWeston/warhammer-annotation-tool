#!/usr/bin/env python3
"""
CMON scrape — for each tile in discover_{run}.jsonl, fetch the entry detail
page, download all hi-res `/o/` images into scripts/cmon/images/{run}/{id}/
and append a full metadata record to scripts/cmon/data/entries_{run}.jsonl.

Resume-safe: skips any entry whose image directory already has a manifest.json.

Usage:
    fiftyone_env/bin/python3 scripts/cmon/cmon_scrape.py single
    fiftyone_env/bin/python3 scripts/cmon/cmon_scrape.py single --limit 20
    fiftyone_env/bin/python3 scripts/cmon/cmon_scrape.py single --min-score 7
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cmon_browser import BASE, CmonBrowser, rand_delay  # noqa: E402
from cmon_parse import parse_entry_detail  # noqa: E402


TARGETING = json.load(open(HERE / "targeting.json"))
DATA_DIR = HERE / "data"
IMAGES_DIR = HERE / "images"
LOG_DIR = HERE / "logs"
IMAGES_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)


def read_discover(run_name: str) -> list[dict]:
    p = DATA_DIR / f"discover_{run_name}.jsonl"
    if not p.exists():
        raise SystemExit(f"no discover file at {p}. Run cmon_discover.py first.")
    rows = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def image_ext_from_url(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if path.endswith(ext):
            return ext
    return ".jpg"


def _existing_manifest(entry_id: str) -> Path | None:
    """Return the path to an existing manifest for this entry under any run
    directory, so we don't re-scrape an entry that has already been captured
    under a different run (e.g. 'single' → 'all'). None if not scraped yet."""
    for p in IMAGES_DIR.glob(f"*/{entry_id}/manifest.json"):
        return p
    return None


def scrape_one(b: CmonBrowser, tile: dict, run_name: str,
               min_score: float, max_score: float) -> dict | None:
    entry_id = tile["id"]
    out_dir = IMAGES_DIR / run_name / entry_id
    manifest_path = out_dir / "manifest.json"
    if manifest_path.exists():
        return None  # already done
    prior = _existing_manifest(entry_id)
    if prior is not None:
        # Already captured under a different run — don't duplicate.
        return None

    url = f"{BASE}/{entry_id}"
    html = b.fetch_html(url)
    if not html:
        print(f"  {entry_id} FAIL fetch_text returned empty", flush=True)
        return None

    d = parse_entry_detail(html, entry_id, url)

    # Belt-and-braces score gate (filter URL should already enforce this, but
    # verify — CMON has been known to leak out-of-range entries on the edge).
    if d.score is not None and not (min_score <= d.score <= max_score):
        print(f"  {entry_id} SKIP score={d.score} outside [{min_score},{max_score}]",
              flush=True)
        return None

    if not d.image_urls:
        print(f"  {entry_id} SKIP no hi-res images on detail page", flush=True)
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    local_paths = []
    for idx, img_url in enumerate(d.image_urls):
        ext = image_ext_from_url(img_url)
        fname = f"{idx:02d}{ext}"
        out_path = out_dir / fname
        if out_path.exists() and out_path.stat().st_size > 0:
            local_paths.append(str(out_path.relative_to(HERE)))
            continue
        data = b.fetch_xhr_bytes(img_url)
        if not data:
            print(f"  {entry_id} img[{idx}] FAIL {img_url[:80]}", flush=True)
            continue
        out_path.write_bytes(data)
        local_paths.append(str(out_path.relative_to(HERE)))

    if not local_paths:
        print(f"  {entry_id} SKIP all images failed to download", flush=True)
        return None

    record = {
        **d.to_jsonable(),
        "tile_title": tile.get("title", ""),
        "tile_artist": tile.get("artist", ""),
        "type_id": tile.get("type_id"),
        "run": run_name,
        "local_paths": local_paths,
        "scraped_at": int(time.time()),
    }
    manifest_path.write_text(json.dumps(record, indent=2))
    print(f"  {entry_id} OK score={d.score} imgs={len(local_paths)} "
          f"title={d.title[:50]!r}", flush=True)
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", help="Run name from targeting.json (e.g. 'single')")
    ap.add_argument("--limit", type=int, default=0,
                    help="Process at most N entries this invocation (0 = all)")
    ap.add_argument("--min-score", type=float,
                    default=float(TARGETING["fixed_filters"]["regaverageMin"]))
    ap.add_argument("--max-score", type=float,
                    default=float(TARGETING["fixed_filters"]["regaverageMax"]))
    ap.add_argument("--delay-lo", type=float, default=2.0)
    ap.add_argument("--delay-hi", type=float, default=5.0)
    args = ap.parse_args()

    tiles = read_discover(args.run)
    print(f"▶ scrape run={args.run}; {len(tiles)} tiles in discover jsonl", flush=True)

    entries_path = DATA_DIR / f"entries_{args.run}.jsonl"
    entries_fp = open(entries_path, "a", buffering=1)

    processed = 0
    ok = 0
    try:
        with CmonBrowser(headless=False) as b:
            b.warm_session()
            for i, tile in enumerate(tiles):
                if args.limit and processed >= args.limit:
                    print(f"  reached --limit {args.limit}", flush=True)
                    break
                rec = scrape_one(b, tile, args.run, args.min_score, args.max_score)
                processed += 1
                if rec:
                    entries_fp.write(json.dumps(rec) + "\n")
                    ok += 1
                rand_delay(args.delay_lo, args.delay_hi)
    finally:
        entries_fp.close()

    print(f"\nDone. processed={processed} ok={ok} entries_file={entries_path}",
          flush=True)


if __name__ == "__main__":
    main()
