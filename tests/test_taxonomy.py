"""Tests for photoanalyzer.taxonomy — the single source of truth for factions
and unit slugs. Read from scripts/data/units.json."""

from __future__ import annotations

import pytest

from photoanalyzer import taxonomy as t


def test_slugify_matches_existing_convention():
    """Must match scripts/phase1/extract_gt_crops.py:123 so labels.csv stays
    compatible."""
    assert t.slugify("Captain") == "captain"
    assert t.slugify("Captain in Gravis Armour") == "captain_in_gravis_armour"
    assert t.slugify("T'au Commander") == "tau_commander"
    assert t.slugify("Lion'el Johnson") == "lionel_johnson"


def test_factions_returns_20_canonical_factions():
    fs = t.factions()
    assert len(fs) == 20
    # Spot-check known canonical slugs
    for f in ["space_marines", "orks", "necrons", "aeldari", "adepta_sororitas",
              "astra_militarum", "chaos_space_marines"]:
        assert f in fs


def test_is_valid_faction():
    assert t.is_valid_faction("space_marines")
    assert t.is_valid_faction("orks")
    assert not t.is_valid_faction("blood_angels")  # alias, not canonical
    assert not t.is_valid_faction("notafaction")


def test_resolve_faction_passthrough_for_canonical():
    assert t.resolve_faction("space_marines") == "space_marines"
    assert t.resolve_faction("orks") == "orks"


def test_resolve_faction_chapter_aliases():
    """Space Marine chapters collapse to `space_marines`."""
    for chapter in ["blood_angels", "dark_angels", "space_wolves", "black_templars",
                    "ultramarines", "crimson_fists"]:
        assert t.resolve_faction(chapter) == "space_marines", chapter


def test_resolve_faction_renames():
    """Historical renames / short forms."""
    assert t.resolve_faction("imperial_guard") == "astra_militarum"
    assert t.resolve_faction("eldar") == "aeldari"
    assert t.resolve_faction("dark_eldar") == "drukhari"
    assert t.resolve_faction("custodes") == "adeptus_custodes"
    assert t.resolve_faction("tau") == "tau_empire"


def test_resolve_faction_unknown_returns_none():
    assert t.resolve_faction("notafaction") is None


def test_units_by_faction_has_units_per_faction():
    by_f = t.units_by_faction()
    # Every canonical faction has at least one unit
    for f in t.factions():
        assert len(by_f[f]) > 0, f"faction {f} has no units"
    # Space marines has >100 units (it's the largest)
    assert len(by_f["space_marines"]) > 100


def test_find_unit_with_faction_scope():
    """A slug like 'captain' exists in multiple factions; faction-scoped
    lookup must return the right one."""
    u = t.find_unit("captain", faction="space_marines")
    assert u is not None
    assert u.faction == "space_marines"
    assert u.name == "Captain"


def test_find_unit_with_alias_faction():
    """Faction aliases must work in find_unit too."""
    u = t.find_unit("captain", faction="blood_angels")
    assert u is not None
    assert u.faction == "space_marines"


def test_find_unit_unknown():
    assert t.find_unit("not_a_unit", faction="space_marines") is None
    assert t.find_unit("captain", faction="notafaction") is None


def test_is_valid_unit():
    assert t.is_valid_unit("captain", faction="space_marines")
    assert t.is_valid_unit("captain", faction="blood_angels")  # alias resolves
    assert not t.is_valid_unit("not_a_unit", faction="space_marines")
    # Unscoped: True if slug exists in ANY faction
    assert t.is_valid_unit("captain")


def test_all_slugs_for_faction():
    slugs = t.all_slugs_for_faction("space_marines")
    assert "captain" in slugs
    assert "intercessors" in slugs or "intercessor_squad" in slugs
    # Alias
    slugs_bl = t.all_slugs_for_faction("blood_angels")
    assert slugs_bl == slugs  # blood_angels alias → same slug set


def test_unit_dataclass_immutable():
    """Unit is frozen dataclass — immutable."""
    u = t.find_unit("captain", faction="space_marines")
    assert u is not None
    with pytest.raises(Exception):  # FrozenInstanceError
        u.slug = "x"  # type: ignore[misc]


def test_iter_units_all():
    units = list(t.iter_units())
    # Sanity: >500 units across 20 factions
    assert len(units) > 500
    # Every unit has the four required fields populated
    for u in units[:50]:
        assert u.faction
        assert u.slug
        assert u.name


def test_iter_units_filtered_with_aliases():
    """Iterate space_marines, passing alias `blood_angels`."""
    units = list(t.iter_units(factions_filter=["blood_angels"]))
    assert len(units) > 100
    assert all(u.faction == "space_marines" for u in units)
