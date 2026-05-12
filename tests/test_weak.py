"""Tests for photoanalyzer.label.weak — title-based weak supervision."""

from __future__ import annotations

import pytest

from photoanalyzer.label.weak import (
    WeakLabel,
    classify_title,
    combine_with_detector,
    normalise_title,
    parse_detector_signal,
)


# ── title normalisation ────────────────────────────────────────────────────
def test_normalise_strips_by_artist():
    assert normalise_title("1st company captain of the Crimson fists by Yellow one") \
        == "1st company captain of the Crimson fists"
    assert normalise_title("Magnus the Red by DEN of IMAGINATION") == "Magnus the Red"


def test_normalise_passes_through():
    assert normalise_title("Orks Waaagh Volmax BurnaBoyzBattlewagon") \
        == "Orks Waaagh Volmax BurnaBoyzBattlewagon"


# ── named characters ───────────────────────────────────────────────────────
def test_magnus_unambiguous():
    w = classify_title("Magnus the Red")
    assert w is not None
    assert w.faction == "chaos_space_marines"
    assert w.unit_slug == "magnus_the_red"
    assert w.source == "char_table"
    assert w.confidence >= 0.85


def test_magnus_with_artist_suffix():
    w = classify_title("Magnus the Red by DEN of IMAGINATION")
    assert w is not None
    assert w.unit_slug == "magnus_the_red"


def test_dante_blood_angels():
    w = classify_title("Dante")
    assert w is not None
    assert w.faction == "space_marines"
    assert "dante" in w.unit_slug


def test_guilliman_nickname():
    w = classify_title("Bobby G in terminator armour")
    assert w is not None
    assert w.faction == "space_marines"
    assert w.unit_slug == "roboute_guilliman"


def test_artist_name_not_matched_as_character():
    # If the title is just "Painting by Dante" we should NOT match Dante the
    # character — the ` by artist` suffix gets stripped before matching.
    w = classify_title("Captain by Dante")
    # "Captain" is a unit kw; no faction implied (captain exists in many
    # factions) — with no faction signal, the rule doesn't fire.
    assert w is None or w.unit_slug != "commander_dante"


# ── chapter rules ──────────────────────────────────────────────────────────
def test_crimson_fists_rollup():
    w = classify_title("1st company captain of the Crimson fists")
    assert w is not None
    assert w.faction == "space_marines"
    # Chapter rule fires; unit-kw for "captain" is too ambiguous to slot
    # uniquely → no unit_slug yet. Confidence is chapter-level.
    assert w.source in ("chapter_kw", "unit_kw")


def test_death_guard_rollup():
    w = classify_title("Death Guard plague marines")
    assert w is not None
    assert w.faction == "chaos_space_marines"
    assert w.unit_slug == "plague_marines"


def test_ultramarines_rollup():
    w = classify_title("Ultramarines Intercessor Squad")
    assert w is not None
    assert w.faction == "space_marines"
    # units.json slug is `intercessor_squad` (not `intercessors`)
    assert w.unit_slug == "intercessor_squad"


# ── faction rules ──────────────────────────────────────────────────────────
def test_orks_keyword():
    w = classify_title("Ork Megadread")
    assert w is not None
    assert w.faction == "orks"


def test_dark_eldar_before_eldar():
    w = classify_title("Dark eldar archon - Kruellagh the Vile")
    assert w is not None
    assert w.faction == "drukhari"


def test_tau_empire():
    w = classify_title("T'au fire warriors")
    assert w is not None
    assert w.faction == "tau_empire"
    # units.json 10e calls them `strike_team` (Fire Warriors is common parlance)
    assert w.unit_slug == "strike_team"


def test_genestealer_cults_before_tyranids():
    w = classify_title("Genestealer Cults patriarch")
    assert w is not None
    assert w.faction == "genestealer_cults"


def test_necrons_keyword():
    w = classify_title("Necron Warriors and a Monolith")
    assert w is not None
    assert w.faction == "necrons"


# ── unique-unit inference (title has no faction word, but unit implies one) ──
def test_unique_unit_lictor_implies_tyranids():
    w = classify_title("The Ultimate Lictor!")
    assert w is not None
    assert w.faction == "tyranids"
    assert w.unit_slug == "lictor"
    # Lictor is shared with GSC post-Wahapedia migration, so auto-derive skips
    # it. We route "Lictor" via an explicit alias rule → source="unit_alias".
    assert w.source == "unit_alias"


def test_unique_unit_warboss_implies_orks():
    w = classify_title("Grand Warboss diorama")
    assert w is not None
    assert w.faction == "orks"
    assert w.unit_slug == "warboss"


def test_unique_unit_lord_of_contagion():
    w = classify_title("Lord of contagion")
    assert w is not None
    assert w.faction == "chaos_space_marines"
    assert w.unit_slug == "lord_of_contagion"


def test_unique_unit_canoness():
    w = classify_title("Canoness Eruita with Retinue")
    assert w is not None
    assert w.faction == "adepta_sororitas"


def test_unique_unit_kroot_implies_tau():
    w = classify_title("Kroot hunters")
    assert w is not None
    assert w.faction == "tau_empire"


def test_mephiston_added():
    w = classify_title("Mephiston Lord Of Death")
    assert w is not None
    assert w.faction == "space_marines"
    assert w.unit_slug == "mephiston"


def test_typhus_added():
    w = classify_title("Typhus Herald of Nurgle")
    assert w is not None
    assert w.faction == "chaos_space_marines"
    assert w.unit_slug == "typhus"


def test_da_red_gobbo_added():
    w = classify_title("Da Red Gobbo")
    assert w is not None
    assert w.faction == "orks"
    assert w.unit_slug == "da_red_gobbo"


# ── ambiguous / empty ──────────────────────────────────────────────────────
def test_empty_title_returns_none():
    assert classify_title("") is None
    assert classify_title(None) is None


def test_cryptic_title_returns_none():
    # Nothing matches — category 5 of the plan's taxonomy
    assert classify_title("Yellow one") is None
    assert classify_title("My first mini") is None
    assert classify_title("Test paint 1") is None


# ── detector signal parser ─────────────────────────────────────────────────
def test_parse_detector_signal_present():
    notes = "detector_conf=0.650; detector_faction=orks; title: 'Orks Waaagh'; multi-box"
    f, c = parse_detector_signal(notes)
    assert f == "orks"
    assert c == pytest.approx(0.65)


def test_parse_detector_canonicalises_alias():
    notes = "detector_faction=blood_angels; detector_conf=0.8"
    f, c = parse_detector_signal(notes)
    assert f == "space_marines"   # alias resolved
    assert c == pytest.approx(0.8)


def test_parse_detector_absent():
    assert parse_detector_signal("title: something") == ("", 0.0)
    assert parse_detector_signal("") == ("", 0.0)


# ── detector cross-check ───────────────────────────────────────────────────
def test_combine_agreement_bumps_confidence():
    title = classify_title("Ork warboss")
    combined = combine_with_detector(title, "orks", 0.8)
    assert combined is not None
    assert combined.faction == "orks"
    assert combined.confidence > title.confidence
    assert "detector_agree" in combined.rule


def test_combine_confident_disagreement_flags_but_does_not_lower():
    """Post-100-entry-test: the detector is too noisy at the crop level to
    justify lowering confidence. Conflict flag still fires for human review."""
    title = classify_title("Orks Waaagh Volmax")
    combined = combine_with_detector(title, "space_marines", 0.8)  # above 0.6
    assert combined is not None
    assert combined.faction == "orks"   # title wins
    assert combined.flag == "title_detector_conflict"
    assert combined.confidence == title.confidence   # unchanged


def test_combine_marginal_disagreement_does_not_flag():
    """Detector <0.6 is treated as noise; no flag."""
    title = classify_title("Orks Waaagh Volmax")
    combined = combine_with_detector(title, "space_marines", 0.5)  # below 0.6
    assert combined is not None
    assert combined.flag == ""
    assert combined.faction == "orks"


def test_combine_no_title_uses_detector():
    combined = combine_with_detector(None, "orks", 0.7)
    assert combined is not None
    assert combined.faction == "orks"
    assert combined.source == "detector_only"


def test_combine_no_title_no_detector_returns_none():
    assert combine_with_detector(None, "", 0.0) is None
    assert combine_with_detector(None, "orks", 0.2) is None


def test_combine_weak_detector_passes_title_through():
    title = classify_title("Necron warriors")
    combined = combine_with_detector(title, "space_marines", 0.2)  # below threshold
    assert combined is title  # no-op


# ── end-to-end sample ──────────────────────────────────────────────────────
@pytest.mark.parametrize("title, expected_faction", [
    ("Fulgrim", "chaos_space_marines"),
    ("Lion'el Johnson, Primarch of the D.A.", "space_marines"),
    ("Leviathan Space Marines.", "space_marines"),
    ("Krieg Command Diorama", "astra_militarum"),
    ("Cthonian Beserks", "chaos_space_marines"),  # World Eaters
    ("Dark eldar countess hellion - Satryx", "drukhari"),
    ("Horus Heresy Chaplain", "space_marines"),
    ("Alpha Legion Traitor Champion", "chaos_space_marines"),
])
def test_batch_of_real_cmon_titles(title, expected_faction):
    w = classify_title(title)
    assert w is not None, f"No match for {title!r}"
    assert w.faction == expected_faction, (
        f"{title!r}: expected {expected_faction}, got {w.faction} via {w.rule}"
    )
