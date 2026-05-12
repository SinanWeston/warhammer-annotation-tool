#!/usr/bin/env python3
"""
Configuration constants for the warhammer.com scraper.

Single source for:
  - URL bases and path prefixes
  - File system layout (images output, state)
  - Skip tokens (sprue / paint / book filtering)
  - FACTION_PREFIX_MAP for filename → repo-faction-slug attribution
  - SEED_URLS for discovery fallback + test-probe targets
"""

from __future__ import annotations

from pathlib import Path

# ─── Site + endpoints ───────────────────────────────────────────────────────

BASE = "https://www.warhammer.com"
LANDING_40K = f"{BASE}/en-GB/shop/warhammer-40000"

INDEX_NAME = "prod-lazarus-product-en-gb"
RECOMMEND_ENDPOINT = f"{BASE}/api/recommend/products/alternative"

IMAGE_PREFIX = "/app/resources/catalog/product/"
IMAGE_920x950 = IMAGE_PREFIX + "920x950/"
IMAGE_360_PREFIX = IMAGE_PREFIX + "threeSixty/"

# GW's CDN honours arbitrary width; w=2000 yields ≥1200px quality shots.
MAX_WIDTH_QS = "?fm=webp&w=2000"

# ─── Filesystem layout ──────────────────────────────────────────────────────

HERE = Path(__file__).resolve().parent
IMAGES_ROOT = HERE / "images"
STATE_DIR = HERE / "state"
PRODUCTS_JSONL = STATE_DIR / "products.jsonl"
UNPARSEABLE_LOG = STATE_DIR / "unparseable.txt"
PROFILE_DIR = HERE / "recon" / ".browser_profile"

SOURCE_PLATFORM = "warhammer_shop"

# ─── Content filters ────────────────────────────────────────────────────────

# Substrings that, when present in the camel-split filename name,
# mean "not a whole-miniature photo": sprues, paint bundles, books, cards.
SKIP_TOKENS: tuple[str, ...] = (
    "Sprue",
    "SprueSet",
    "InDev",
    "PaintSet",
    "PaintBundle",
    "Card",
    "Datasheets",
    "Book",
    "Rulebook",
    "Codex",
)

BOX_PRODUCT_NAME_PREFIXES: tuple[str, ...] = (
    "Combat Patrol",
    "Battleforce",
    "Start Collecting",
    "Boarding Patrol",
    "Boarding Action",
    "Army Set",
    "Spearhead",
    "Vanguard",
)

# ─── Faction prefix map ─────────────────────────────────────────────────────
# Keyed on longest-matching lowercase prefix of camel_to_snake(filename_name).
# Sentinel `None` means "strip this prefix and look up the remainder."

FACTION_PREFIX_MAP: dict[str, str | None] = {
    # Adeptus Custodes (incl. Horus Heresy Legio Custodes)
    "custodes": "adeptus_custodes",
    "legio_custodes": "adeptus_custodes",
    "aquilon": "adeptus_custodes",
    # Space Marines + chapter folders that exist in repo
    "sm": "space_marines",
    "space_marines": "space_marines",
    "ultramarines": "space_marines",
    "blood_angels": "blood_angels",
    "dark_angels": "dark_angels",
    "space_wolves": "space_marines",
    "black_templars": "black_templars",
    "grey_knights": "grey_knights",
    "deathwatch": "deathwatch",
    # Astra Militarum
    "am": "astra_militarum",
    "astra_militarum": "astra_militarum",
    "cadian": "astra_militarum",
    "catachan": "astra_militarum",
    "krieg": "astra_militarum",
    # Adepta Sororitas
    "as": "adepta_sororitas",
    "sororitas": "adepta_sororitas",
    "sisters": "adepta_sororitas",
    # Adeptus Mechanicus
    "admech": "adeptus_mechanicus",
    "adeptus_mechanicus": "adeptus_mechanicus",
    "skitarii": "adeptus_mechanicus",
    # T'au + Kroot + allies
    "tau": "tau_empire",
    "kroot": "tau_empire",
    "com": "tau_empire",        # ComShadowsun
    "shas": "tau_empire",
    "ethereal": "tau_empire",
    # Chaos Space Marines (chapter folders where they exist)
    "csm": "chaos_space_marines",
    "chaos_space_marines": "chaos_space_marines",
    "thousand_sons": "thousand_sons",
    "death_guard": "death_guard",
    "world_eaters": "chaos_space_marines",
    "emperors_children": "chaos_space_marines",
    "black_legion": "chaos_space_marines",
    # Tyranids + GSC
    "tyr": "tyranids",
    "tyranids": "tyranids",
    "termagants": "tyranids",
    "hormagaunts": "tyranids",
    "gsc": "genestealer_cult",
    "genestealer": "genestealer_cult",
    # Xenos
    "necrons": "necrons",
    "necron": "necrons",
    "orks": "orks",
    "ork": "orks",
    "aeldari": "aeldari",
    "eldar": "aeldari",
    "drukhari": "drukhari",
    "harlequins": "harlequins",
    "ynnari": "ynnari",
    "votann": "leagues_of_votann",
    # Knights
    "imperial_knights": "imperial_knights",
    "chaos_knights": "chaos_knights",
    # Imperial Agents
    "imperial_agents": "imperial_agents",
    # Kill Team sentinel — recurse into remainder
    "kt": None,
    # Generic TAU prefix on box codes
    "tau_combat_patrol": "tau_empire",
    # Combat Patrol sentinel — fall through to slug-based inference
    "combat_patrol": None,
}

# ─── URL seeds ──────────────────────────────────────────────────────────────
# Fallback discovery seeds; also the test-probe targets.

SEED_URLS: tuple[str, ...] = (
    # 40K faction category landing pages (user-facing URLs).
    # Some of these may 404 if GW reorganises slugs — discover() tolerates that
    # via `if not html: continue`.
    f"{BASE}/en-GB/shop/warhammer-40000",
    # Imperium
    f"{BASE}/en-GB/shop/warhammer-40000/space-marines",
    f"{BASE}/en-GB/shop/warhammer-40000/blood-angels",
    f"{BASE}/en-GB/shop/warhammer-40000/dark-angels",
    f"{BASE}/en-GB/shop/warhammer-40000/space-wolves",
    f"{BASE}/en-GB/shop/warhammer-40000/black-templars",
    f"{BASE}/en-GB/shop/warhammer-40000/deathwatch",
    f"{BASE}/en-GB/shop/warhammer-40000/grey-knights",
    f"{BASE}/en-GB/shop/warhammer-40000/adepta-sororitas",
    f"{BASE}/en-GB/shop/warhammer-40000/adeptus-custodes",
    f"{BASE}/en-GB/shop/warhammer-40000/adeptus-mechanicus",
    f"{BASE}/en-GB/shop/warhammer-40000/astra-militarum",
    f"{BASE}/en-GB/shop/warhammer-40000/imperial-knights",
    f"{BASE}/en-GB/shop/warhammer-40000/imperial-agents",
    # Chaos
    f"{BASE}/en-GB/shop/warhammer-40000/chaos-space-marines",
    f"{BASE}/en-GB/shop/warhammer-40000/death-guard",
    f"{BASE}/en-GB/shop/warhammer-40000/thousand-sons",
    f"{BASE}/en-GB/shop/warhammer-40000/world-eaters",
    f"{BASE}/en-GB/shop/warhammer-40000/emperors-children",
    f"{BASE}/en-GB/shop/warhammer-40000/chaos-daemons",
    f"{BASE}/en-GB/shop/warhammer-40000/chaos-knights",
    # Xenos
    f"{BASE}/en-GB/shop/warhammer-40000/aeldari",
    f"{BASE}/en-GB/shop/warhammer-40000/drukhari",
    f"{BASE}/en-GB/shop/warhammer-40000/harlequins",
    f"{BASE}/en-GB/shop/warhammer-40000/ynnari",
    f"{BASE}/en-GB/shop/warhammer-40000/tyranids",
    f"{BASE}/en-GB/shop/warhammer-40000/genestealer-cults",
    f"{BASE}/en-GB/shop/warhammer-40000/necrons",
    f"{BASE}/en-GB/shop/warhammer-40000/orks",
    f"{BASE}/en-GB/shop/warhammer-40000/leagues-of-votann",
    f"{BASE}/en-GB/shop/warhammer-40000/tau-empire",
    # Cross-faction / bundles
    f"{BASE}/en-GB/shop/warhammer-40000/combat-patrol",
    f"{BASE}/en-GB/shop/warhammer-40000/battleforce",
    f"{BASE}/en-GB/shop/warhammer-40000/start-collecting",
    f"{BASE}/en-GB/shop/warhammer-40000/terrain",
)

# Known-good product URLs for test-probe + regex / extractor sanity.
PROBE_URLS: tuple[str, ...] = (
    f"{BASE}/en-GB/shop/legio-custodes-custodian-dreadnought-2026",
    f"{BASE}/en-GB/shop/combat-patrol-kroot-2026",
)
