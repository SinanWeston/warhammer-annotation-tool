"""Canonical 40K taxonomy — factions, unit slugs, aliases.

Single source of truth: `scripts/data/units.json`. Every other module in
`photoanalyzer/` must import faction + unit vocabulary from here; do not
hardcode strings elsewhere.

Slug convention (matches scripts/phase1/extract_gt_crops.py):
    slug(name) = name.lower().replace("'", "").replace(" ", "_")

Aliases map historical / chapter-level / abbreviated faction strings to the
20 canonical faction slugs defined by units.json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
UNITS_JSON_PATH = REPO_ROOT / "scripts" / "data" / "units.json"
CHARACTERS_JSON_PATH = REPO_ROOT / "scripts" / "data" / "characters.json"

# ── v1 product scope ───────────────────────────────────────────────────────
# The four factions the v1 scanner recognises (locked 2026-06-04). The
# production Tier 2 probe restricts its predictions to this set — measured at
# +0.30 faction top-1 over 20-way argmax on real crops
# (docs/benchmarks/2026-06-09-review-experiments.md).
V1_FACTIONS: tuple[str, ...] = (
    "space_marines", "necrons", "tyranids", "death_guard",
)


# ── faction aliases ────────────────────────────────────────────────────────
# Map non-canonical strings → canonical faction slug.
# Keep narrow: only add aliases that actually appear in our data corpora.
FACTION_ALIASES: dict[str, str] = {
    # Space Marine chapters (all collapsed to space_marines for classifier)
    "blood_angels": "space_marines",
    "dark_angels": "space_marines",
    "space_wolves": "space_marines",
    "black_templars": "space_marines",
    "ultramarines": "space_marines",
    "crimson_fists": "space_marines",
    "imperial_fists": "space_marines",
    "salamanders": "space_marines",
    "iron_hands": "space_marines",
    "raven_guard": "space_marines",
    "white_scars": "space_marines",
    "chapter_marines": "space_marines",
    "primaris": "space_marines",
    # Codex-level aliases treated as space_marines for coarse classifier
    "deathwatch": "space_marines",
    "grey_knights": "space_marines",
    # NOTE: death_guard / thousand_sons / world_eaters / emperors_children
    # are now top-level factions in units.json (see scripts/split_chaos_subfactions.py,
    # 2026-04-19). They used to alias to chaos_space_marines; now they
    # stand on their own and match the deployed YOLO model's class list.
    # Historical / short / alt forms
    "imperial_guard": "astra_militarum",
    "eldar": "aeldari",
    "craftworlds": "aeldari",
    "dark_eldar": "drukhari",
    "custodes": "adeptus_custodes",
    "mechanicus": "adeptus_mechanicus",
    "sororitas": "adepta_sororitas",
    "sisters_of_battle": "adepta_sororitas",
    "genestealer_cult": "genestealer_cults",
    "tau": "tau_empire",
    "votann": "leagues_of_votann",
}


# ── loader ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Unit:
    """A canonical 40K unit within a faction."""
    faction: str       # canonical faction slug
    slug: str          # slugified unit name, primary key
    name: str          # human-readable name from units.json
    category: str      # e.g. "character", "troops", "elites" (free-text in units.json)


@dataclass(frozen=True)
class NamedCharacter:
    """A canonical named 40K character (primarch, HQ special, etc).
    Source: scripts/data/characters.json. May or may not also exist in
    units.json — the character catalog is authoritative for IDs here.
    """
    slug: str
    faction: str
    display_name: str
    aliases: tuple[str, ...]   # match phrases for weak-sup, first is canonical
    chapter: str = ""          # optional sub-faction / chapter tag
    era: str = "40k"           # "40k" | "heresy"


def slugify(name: str) -> str:
    """Deterministic name → slug.

    Matches scripts/phase1/extract_gt_crops.py:123 semantics but also strips
    Unicode curly/smart quotes (U+2018 / U+2019) that Wahapedia uses in
    names like "Lion El'jonson" — without this, the curly-apostrophe variant
    produces a different slug than the straight-apostrophe one.
    """
    return (
        name.lower()
        .replace("\u2018", "")  # ‘ LEFT SINGLE QUOTATION MARK
        .replace("\u2019", "")  # ’ RIGHT SINGLE QUOTATION MARK (Wahapedia default)
        .replace("'", "")       # ' APOSTROPHE
        .replace(" ", "_")
    )


@lru_cache(maxsize=1)
def _load_units_json() -> dict:
    if not UNITS_JSON_PATH.exists():
        raise FileNotFoundError(
            f"units.json not found at {UNITS_JSON_PATH}. "
            "photoanalyzer.taxonomy is the only module allowed to read it."
        )
    with open(UNITS_JSON_PATH) as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _build_index() -> tuple[
    tuple[str, ...],                    # FACTIONS tuple
    dict[str, tuple[Unit, ...]],        # UNITS_BY_FACTION
    dict[str, Unit],                    # SLUG_TO_UNIT (global, for quick lookup)
]:
    data = _load_units_json()
    factions_obj = data.get("factions") or {}

    factions: list[str] = []
    by_faction: dict[str, list[Unit]] = {}
    slug_to_unit: dict[str, Unit] = {}

    for faction_slug, body in factions_obj.items():
        factions.append(faction_slug)
        unit_list: list[Unit] = []
        for u in body.get("units") or []:
            name = u.get("name") or ""
            if not name:
                continue
            slug = slugify(name)
            unit = Unit(
                faction=faction_slug,
                slug=slug,
                name=name,
                category=u.get("category") or "",
            )
            unit_list.append(unit)
            # First definition wins for globally-ambiguous slugs (e.g. "captain"
            # is in multiple factions). The canonical source-of-truth is the
            # per-faction map; this global dict is a convenience for quick
            # checks and should never be the authority for resolving a slug's
            # faction — pass `faction=` explicitly in lookup helpers below.
            slug_to_unit.setdefault(slug, unit)
        by_faction[faction_slug] = unit_list

    return (
        tuple(factions),
        {f: tuple(us) for f, us in by_faction.items()},
        slug_to_unit,
    )


# Public module constants computed lazily on first access.
def _get():
    return _build_index()


@lru_cache(maxsize=1)
def factions() -> tuple[str, ...]:
    """Canonical 20 faction slugs, in units.json order."""
    return _get()[0]


@lru_cache(maxsize=1)
def units_by_faction() -> dict[str, tuple[Unit, ...]]:
    return _get()[1]


@lru_cache(maxsize=1)
def slug_to_unit() -> dict[str, Unit]:
    """Convenience global slug → first-matching Unit. Not for resolving
    faction ownership — use `find_unit(slug, faction=)` for that."""
    return _get()[2]


# ── public API ─────────────────────────────────────────────────────────────
def is_valid_faction(faction: str) -> bool:
    """True if `faction` is a canonical faction slug."""
    return faction in factions()


def resolve_faction(faction: str) -> str | None:
    """Return the canonical faction slug for `faction`, resolving aliases.
    Returns None if `faction` is unknown and not aliased."""
    if faction in factions():
        return faction
    return FACTION_ALIASES.get(faction)


def is_valid_unit(slug: str, *, faction: str | None = None) -> bool:
    """True if `slug` is a known unit. If `faction` is provided, checks within
    that faction (after resolving aliases)."""
    if faction is not None:
        f = resolve_faction(faction)
        if f is None:
            return False
        return any(u.slug == slug for u in units_by_faction().get(f, ()))
    return slug in slug_to_unit()


def find_unit(slug: str, *, faction: str | None = None) -> Unit | None:
    """Resolve a slug to a Unit. If `faction` is given, scoped to that faction
    (with alias resolution). Otherwise returns the first global match."""
    if faction is not None:
        f = resolve_faction(faction)
        if f is None:
            return None
        for u in units_by_faction().get(f, ()):
            if u.slug == slug:
                return u
        return None
    return slug_to_unit().get(slug)


def faction_of(slug: str) -> str | None:
    """Return the (first) canonical faction a unit slug belongs to.

    WARNING: ambiguous for slugs shared across factions (e.g. 'captain'). Use
    only when a label record already carries faction — this is a convenience
    for checking membership, not for resolving ambiguous cases.
    """
    u = slug_to_unit().get(slug)
    return u.faction if u else None


def all_slugs_for_faction(faction: str) -> tuple[str, ...]:
    """All valid unit slugs for `faction` (after alias resolution). Empty tuple
    if faction is unknown."""
    f = resolve_faction(faction)
    if f is None:
        return ()
    return tuple(u.slug for u in units_by_faction().get(f, ()))


def iter_units(factions_filter: Iterable[str] | None = None) -> Iterable[Unit]:
    """Iterate all units (optionally restricted to given factions, aliases OK)."""
    if factions_filter is None:
        for fs in units_by_faction().values():
            yield from fs
        return
    wanted = set()
    for f in factions_filter:
        resolved = resolve_faction(f)
        if resolved is not None:
            wanted.add(resolved)
    for f, fs in units_by_faction().items():
        if f in wanted:
            yield from fs


# ── named characters ───────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _load_characters_json() -> list[dict]:
    if not CHARACTERS_JSON_PATH.exists():
        return []
    with open(CHARACTERS_JSON_PATH) as f:
        data = json.load(f)
    return data.get("characters") or []


@lru_cache(maxsize=1)
def characters() -> tuple[NamedCharacter, ...]:
    """Return all named characters from characters.json, sorted so longer
    primary aliases come first (so pattern matching in weak-sup picks the
    most-specific entry when multiple could match, e.g. 'Lion El'Jonson'
    beats a bare 'Lion')."""
    out: list[NamedCharacter] = []
    seen_slugs: set[str] = set()
    for entry in _load_characters_json():
        slug = entry.get("slug")
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        faction = resolve_faction(entry.get("faction", "")) or entry.get("faction", "")
        aliases = tuple(entry.get("aliases") or ())
        if not aliases:
            aliases = (entry.get("display_name", slug.replace("_", " ")),)
        out.append(NamedCharacter(
            slug=slug,
            faction=faction,
            display_name=entry.get("display_name", ""),
            aliases=aliases,
            chapter=entry.get("chapter", ""),
            era=entry.get("era", "40k"),
        ))
    out.sort(key=lambda c: -len(c.aliases[0]))
    return tuple(out)


def find_character(slug: str) -> NamedCharacter | None:
    for c in characters():
        if c.slug == slug:
            return c
    return None


def characters_by_faction(faction: str) -> tuple[NamedCharacter, ...]:
    """All named characters for a given canonical (or aliased) faction."""
    f = resolve_faction(faction)
    if f is None:
        return ()
    return tuple(c for c in characters() if c.faction == f)
