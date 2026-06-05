#!/usr/bin/env python3
"""
Algolia-native product discovery for warhammer.com.

The warhammer.com frontend loads its product catalogue from an Algolia search
index (`prod-lazarus-product-en-gb`, app id `M5ZIQZNQ2H`). Each hit contains:
  - slug, name, sku, productType
  - images: full list of /app/resources/catalog/product/... URLs
  - GameSystemsRoot.lvl2: authoritative "Game > Armies > Faction" path

So we skip browser navigation entirely for discovery. One-time headed WAF bootstrap
captures the Algolia API key (see capture-creds tool) — after that, discovery is
pure HTTPS calls to Algolia. No WAF rotation risk for this step.

Output: enriched rows in `state/products.jsonl` — each row already carries the
full image list + faction, so the scrape step can skip browser too (plain
`requests` image downloads, ~3600 40K miniatures in ~30 minutes).

Usage:
    fiftyone_env/bin/python3 scripts/warhammer_com/algolia_discover.py
    fiftyone_env/bin/python3 scripts/warhammer_com/algolia_discover.py --limit 100
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from gw_shop_constants import (  # noqa: E402
    BASE,
    INDEX_NAME,
    PRODUCTS_JSONL,
    STATE_DIR,
)

CREDS_FILE = STATE_DIR / "algolia_creds.json"
HITS_PER_PAGE = 500  # Algolia default cap per page; 500 is safe under all tiers

FACTION_LVL2_PREFIX = "Warhammer 40,000 > "

# lvl2 paths are "Warhammer 40,000 > <parent> > <child>". We want <child> only
# when <parent> is an army-taxonomy category, not a unit-type or
# start-here/gameplay-rules taxonomy.
FACTION_PARENTS: tuple[str, ...] = (
    "Armies of the Imperium",
    "Armies of Chaos",
    "Xenos Armies",
    "Space Marines",  # chapters (Blood Angels, Dark Angels, etc.) live under here
)

# Map GW's display names to the repo's existing faction folder conventions.
FACTION_DISPLAY_ALIASES: dict[str, str] = {
    "t_au_empire": "tau_empire",
    "emperor_s_children": "emperors_children",
    "genestealer_cults": "genestealer_cults",
}


def _load_creds() -> dict:
    if not CREDS_FILE.exists():
        raise SystemExit(
            f"Missing {CREDS_FILE}. Run the capture-creds step first (one-time):\n"
            f"  (documented in wh_browser / bootstrap_waf flow)"
        )
    return json.loads(CREDS_FILE.read_text())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(s: str) -> str:
    s = s.lower().strip()
    # Drop apostrophes before splitting on non-alnum, so "T'au Empire" →
    # "tau_empire" (not "t_au_empire") and "Emperor's Children" →
    # "emperors_children".
    for apos in ("'", "\u2019", "\u2018", "`"):
        s = s.replace(apos, "")
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def faction_from_game_systems_root(gsr: dict | None) -> str:
    """
    Extract a repo-style faction slug from Algolia's hierarchical categories.

    `GameSystemsRoot.lvl2` is a list of strings like:
      "Warhammer 40,000 > Armies of the Imperium > Adeptus Custodes"
      "Warhammer 40,000 > Unit Type > Infantry"              ← NOT a faction
      "Warhammer 40,000 > Space Marines > Unit Type"         ← child is a type, not a chapter
      "Warhammer 40,000 > Space Marines > Blood Angels"       ← chapter-specific
      "Warhammer 40,000 > Space Marines > Dark Angels"        ← (multi-chapter generic kit)
      "Warhammer 40,000 > Space Marines > Iron Hands"         ← (same — means cross-chapter)

    Rule:
      - Only honour lvl2 entries whose parent is an army-taxonomy category
        (FACTION_PARENTS).
      - Reject `child == "Unit Type"` and self-referential `child == parent`.
      - For Space-Marines parent: if exactly one chapter-child remains, use it.
        If multiple (→ universal SM kit), return "space_marines" umbrella.
      - For "Armies of *" parents: use the first valid child (alphabetical).
    """
    if not gsr:
        return "unknown"

    valid: list[tuple[str, str]] = []  # (parent, child)
    for path in gsr.get("lvl2") or []:
        if not isinstance(path, str) or not path.startswith(FACTION_LVL2_PREFIX):
            continue
        parts = [p.strip() for p in path.split(" > ")]
        if len(parts) < 3:
            continue
        parent, child = parts[1], parts[2]
        if parent not in FACTION_PARENTS:
            continue
        if child in {"Unit Type", parent}:       # type leaf or self-ref
            continue
        valid.append((parent, child))

    if not valid:
        return "unknown"

    by_parent: dict[str, set[str]] = {}
    for p, c in valid:
        by_parent.setdefault(p, set()).add(c)

    # Space-Marines branch: chapter-specific if exactly one child, else generic.
    if "Space Marines" in by_parent:
        children = by_parent["Space Marines"]
        if len(children) == 1:
            slug = _slugify(next(iter(children)))
            return FACTION_DISPLAY_ALIASES.get(slug, slug)
        # Universal SM kit — available to all chapters. Default to space_marines.
        return "space_marines"

    # Armies-of-* branch: prefer deterministic first child (alphabetical).
    for parent in ("Armies of the Imperium", "Armies of Chaos", "Xenos Armies"):
        if parent in by_parent:
            child = sorted(by_parent[parent])[0]
            slug = _slugify(child)
            return FACTION_DISPLAY_ALIASES.get(slug, slug)

    return "unknown"


def is_40k(hit: dict) -> bool:
    gsr = hit.get("GameSystemsRoot") or {}
    lvl0 = gsr.get("lvl0") or []
    if isinstance(lvl0, list):
        return any("Warhammer 40,000" in s for s in lvl0)
    return False


def query_algolia_page(creds: dict, page: int, facet_filter_40k: bool = True) -> dict:
    """
    Hit Algolia search API for one page.

    When facet_filter_40k=True, server-side filters to hits where
    GameSystemsRoot.lvl0 contains "Warhammer 40,000" — gives us only 40K
    products and proper pagination.
    """
    from urllib.parse import urlencode, quote

    url = (
        f"https://{creds['app_id'].lower()}-dsn.algolia.net/1/indexes/"
        f"{INDEX_NAME}/query"
    )
    # Algolia params are a URL-encoded query string passed as the "params" field
    # of the POST body.
    p = {
        "hitsPerPage": str(HITS_PER_PAGE),
        "page": str(page),
    }
    if facet_filter_40k:
        # JSON-encoded nested array: [["GameSystemsRoot.lvl0:Warhammer 40,000"]]
        # Inner [] = AND, outer [] around inner = OR. Single filter → both.
        p["facetFilters"] = json.dumps([["GameSystemsRoot.lvl0:Warhammer 40,000"]])
    params = urlencode(p, quote_via=quote)

    headers = {
        "x-algolia-api-key": creds["api_key"],
        "x-algolia-application-id": creds["app_id"],
        "content-type": "application/json",
    }
    body = {"params": params}
    resp = requests.post(url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _enriched_row(hit: dict) -> dict:
    slug = hit.get("slug", "")
    return {
        "url": f"{BASE}/en-GB/shop/{slug}" if slug else "",
        "url_slug": slug,
        "product_id": hit.get("id", ""),
        "master_sku": hit.get("sku", ""),
        "name": hit.get("name", ""),
        "product_type": hit.get("productType", ""),
        "images": list(hit.get("images") or []),
        "faction_hint": faction_from_game_systems_root(hit.get("GameSystemsRoot")),
        "game_systems_lvl0": (hit.get("GameSystemsRoot") or {}).get("lvl0", []),
        "game_systems_lvl2": (hit.get("GameSystemsRoot") or {}).get("lvl2", []),
        "is_available": hit.get("isAvailable", False),
        "is_pre_order": hit.get("isPreOrder", False),
        "is_webstore_exclusive": hit.get("isWebstoreExclusive", False),
        "is_last_chance": hit.get("isLastChanceToBuy", False),
        "discovered_at": _now_iso(),
        "scraped_at": None,
        "images_saved": None,
        "images_skipped": None,
        "error": None,
    }


def _load_existing() -> dict[str, dict]:
    if not PRODUCTS_JSONL.exists():
        return {}
    rows: dict[str, dict] = {}
    with PRODUCTS_JSONL.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("url"):
                rows[r["url"]] = r
    return rows


def _write_rows(rows: dict[str, dict]) -> None:
    PRODUCTS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    tmp = PRODUCTS_JSONL.with_suffix(PRODUCTS_JSONL.suffix + ".tmp")
    with tmp.open("w") as f:
        for url in sorted(rows.keys()):
            f.write(json.dumps(rows[url], ensure_ascii=False) + "\n")
    tmp.replace(PRODUCTS_JSONL)


def discover(limit: int | None = None) -> int:
    """
    Paginate the Algolia index, filter to 40K hits, upsert into products.jsonl.
    Returns count of newly-added products.
    """
    creds = _load_creds()
    existing = _load_existing()
    print(f"Existing products on disk: {len(existing)}")

    added = 0
    updated = 0
    page = 0
    total_hits = None
    total_40k_seen = 0

    while True:
        print(f"  querying page {page}…", flush=True)
        data = query_algolia_page(creds, page)
        hits = data.get("hits") or []
        if total_hits is None:
            total_hits = data.get("nbHits", 0)
            print(f"  index reports nbHits={total_hits}, nbPages={data.get('nbPages', '?')}")
        if not hits:
            break

        for hit in hits:
            if not is_40k(hit):
                continue
            total_40k_seen += 1
            row = _enriched_row(hit)
            if not row["url"]:
                continue
            if row["url"] in existing:
                # Keep any prior scraped_at / counts; update all Algolia-sourced fields.
                prior = existing[row["url"]]
                for k, v in row.items():
                    if k in ("scraped_at", "images_saved", "images_skipped", "error"):
                        continue
                    prior[k] = v
                updated += 1
            else:
                existing[row["url"]] = row
                added += 1
                if limit and added >= limit:
                    break

        if limit and added >= limit:
            break
        page += 1
        nb_pages = data.get("nbPages", 0)
        if page >= nb_pages:
            break

    _write_rows(existing)
    print(f"\n✓ {added} new + {updated} refreshed = {added + updated} products")
    print(f"  40K hits scanned: {total_40k_seen}  (total index: {total_hits})")
    print(f"  wrote {PRODUCTS_JSONL}")
    return added


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Algolia-based 40K product discovery")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap total new products added (default: no cap)")
    args = ap.parse_args(argv)
    n = discover(limit=args.limit)
    return 0 if n >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
