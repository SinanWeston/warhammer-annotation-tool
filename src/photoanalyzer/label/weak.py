"""Weak supervision: rule-based labelling from titles + detector cross-check.

Signals, in order of precedence:
1. **Named character match** — title contains a canonical character name from
   units.json (where category == "character"). Unambiguous → emits BOTH faction
   and unit_slug with high confidence.
2. **Chapter / sub-faction keyword** — e.g. "Crimson Fists", "Death Guard",
   "Ultramarines" → emits faction (rollup to the canonical 20). Unit_slug
   stays empty unless other rules fire.
3. **Faction keyword** — e.g. "ork", "tau", "sisters of battle" → emits faction.
4. **Unit keyword** (faction-scoped) — e.g. "intercessors", "boyz",
   "terminators". Only emits unit_slug *if* a faction was already determined
   (by a prior rule) and the slug is unique within that faction.
5. **Detector cross-check** — if YOLO predicted a faction (preserved in the
   `detector_faction=X` hint in notes), we cross-reference:
     - detector agrees with title → bump confidence
     - detector disagrees → emit `flag="title_detector_conflict"` (the human
       review pass should see this first)
     - detector says something, title says nothing → use detector as weak prior

No rule ever overrides a non-empty existing label. Runs are idempotent on
`data/labels.csv`: crops already labelled (`unit_slug != ""`) are skipped.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .. import taxonomy
from ..taxonomy import slugify


# ── title cleanup ──────────────────────────────────────────────────────────
# Titles often end with " by <artist>" — strip that before matching so artist
# names don't accidentally hit character rules ("by Dante" → "Dante").
_BY_ARTIST_RE = re.compile(r"\s+by\s+[\w'.\-& ]+$", re.IGNORECASE)


def normalise_title(title: str) -> str:
    t = (title or "").strip()
    t = _BY_ARTIST_RE.sub("", t)
    # collapse whitespace
    t = re.sub(r"\s+", " ", t)
    return t


# ── rule result shape ──────────────────────────────────────────────────────
@dataclass
class WeakLabel:
    faction: str = ""
    unit_slug: str = ""
    confidence: float = 0.0       # 0..1
    source: str = ""              # "char_table" | "chapter_kw" | "faction_kw" | "unit_kw"
    rule: str = ""                # which rule fired (for debugging)
    flag: str = ""                # "" | "title_detector_conflict" | "ambiguous_slug"

    def to_dict(self) -> dict:
        return {
            "faction": self.faction,
            "unit_slug": self.unit_slug,
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "rule": self.rule,
            "flag": self.flag,
        }


# ── rule data ──────────────────────────────────────────────────────────────
# Chapter / sub-faction keywords that imply a canonical faction. Order matters
# only in ambiguity resolution — if multiple match, the earlier one wins.
_CHAPTER_RULES: list[tuple[str, str, str]] = [
    # (keyword regex, canonical faction, chapter tag)
    # Horus Heresy is an era / IP — default to space_marines (loyalist art is
    # more common in HH commissions). This must fire BEFORE the `horus`
    # character match; the classifier pre-strips "horus heresy" → "heresy"
    # before character matching runs.
    (r"\bhorus heresy\b|\bhh\b(?=\s)|\bage of darkness\b", "space_marines", "horus_heresy"),
    (r"\bcthonian\b",            "chaos_space_marines", "sons_of_horus"),
    (r"\bsons of horus\b",       "chaos_space_marines", "sons_of_horus"),
    (r"\bdeath guard\b",         "chaos_space_marines", "death_guard"),
    (r"\bthousand sons\b",       "chaos_space_marines", "thousand_sons"),
    (r"\bworld eaters\b",        "chaos_space_marines", "world_eaters"),
    (r"\bemperor['’]s children\b", "chaos_space_marines", "emperors_children"),
    (r"\balpha legion\b",        "chaos_space_marines", "alpha_legion"),
    (r"\bnight lords?\b",        "chaos_space_marines", "night_lords"),
    (r"\bword bearers?\b",       "chaos_space_marines", "word_bearers"),
    (r"\biron warriors?\b",      "chaos_space_marines", "iron_warriors"),
    (r"\bblack legion\b",        "chaos_space_marines", "black_legion"),
    (r"\bcrimson fists?\b",      "space_marines", "crimson_fists"),
    (r"\bblood angels?\b",       "space_marines", "blood_angels"),
    (r"\bdark angels?\b",        "space_marines", "dark_angels"),
    (r"\bspace wolves\b|\bwolves chapter\b", "space_marines", "space_wolves"),
    (r"\bultramarines?\b",       "space_marines", "ultramarines"),
    (r"\bimperial fists?\b",     "space_marines", "imperial_fists"),
    (r"\bsalamanders?\b",        "space_marines", "salamanders"),
    (r"\biron hands?\b",         "space_marines", "iron_hands"),
    (r"\braven guard\b",         "space_marines", "raven_guard"),
    (r"\bwhite scars?\b",        "space_marines", "white_scars"),
    (r"\bblack templars?\b",     "space_marines", "black_templars"),
    (r"\bgrey knights?\b",       "space_marines", "grey_knights"),
    (r"\bdeathwatch\b",          "space_marines", "deathwatch"),
    (r"\bdeath korps\b|\bkrieg\b", "astra_militarum", "death_korps_of_krieg"),
    (r"\bcadian\b",              "astra_militarum", "cadian"),
    (r"\bcatachan\b",            "astra_militarum", "catachan"),
    (r"\b(craftworld|iyanden|ulthwe|saim[- ]hann|biel[- ]tan|alaitoc)\b", "aeldari", ""),
    (r"\b(nurgle|plague|pestilence)\b", "chaos_space_marines", "nurgle"),
    (r"\bkhorne\b|\bberserker?s?\b", "chaos_space_marines", "world_eaters"),
    (r"\btzeentch\b|\brubric\b|\btsons\b", "chaos_space_marines", "thousand_sons"),
    (r"\bslaanesh\b|\bnoise marines?\b", "chaos_space_marines", "emperors_children"),
]

# Broad faction keywords — fire only if no chapter rule hit. Match whole-word.
# Order matters: more specific rules first (e.g. GSC before Tyranids).
_FACTION_RULES: list[tuple[str, str]] = [
    (r"\bdark eldar\b|\bdrukhari\b",                  "drukhari"),
    (r"\bharlequins?\b|\btroupes?\b",                 "harlequins"),
    (r"\bynnari\b",                                   "ynnari"),
    (r"\bgenestealer cults?\b|\bgsc\b|\bgenestealer cult\b|\bpatriarch\b|\bmagus\b|\bprimus\b|\bneophyte\b|\bacolyte\b|\baberrants?\b|\bkelermorph\b", "genestealer_cults"),
    (r"\b(aeldari|eldar)\b",                          "aeldari"),
    (r"\b(t['’]?au|tau empire|tau |kroot)\b",         "tau_empire"),
    (r"\bnecrons?\b",                                 "necrons"),
    (r"\btyranids?\b|\btyranid\b|\bgaunts?\b|\bhormagaunts?\b|\bgants?\b", "tyranids"),
    (r"\borks?\b|\bboyz\b|\bwaaagh\b|\bgoff\b|\bmeganob\b|\bmek\b", "orks"),
    (r"\bleagues of votann\b|\bvotann\b",             "leagues_of_votann"),
    (r"\bchaos daemons?\b|\bdaemons?\b|\bbloodletters?\b|\bplaguebearers?\b|\bdaemonettes?\b|\bhorrors? of tzeentch\b", "chaos_daemons"),
    (r"\bchaos knights?\b",                           "chaos_knights"),
    (r"\bimperial knights?\b|\bknight (paladin|errant|warden|gallant|crusader|lancer)\b", "imperial_knights"),
    (r"\badepta sororitas\b|\bsisters of battle\b|\bbattle sisters?\b", "adepta_sororitas"),
    (r"\badeptus mechanicus\b|\badmech\b|\bmechanicus\b|\bskitarii\b", "adeptus_mechanicus"),
    (r"\b(adeptus custodes|custodes|custodian guard)\b", "adeptus_custodes"),
    (r"\b(astra militarum|imperial guard|guardsmen?)\b", "astra_militarum"),
    (r"\b(chaos space marines?|chaos marines?|csm|legionnaires|legionaries|heretic astartes)\b", "chaos_space_marines"),
    (r"\b(space marines?|adeptus astartes|primaris|astartes)\b", "space_marines"),
    (r"\bimperial agents?\b|\binquisition\b|\binquisitor\b", "imperial_agents"),
]

# Unit-keyword rules — emit unit_slug *if* a faction was determined, and the
# slug is unambiguously owned by that faction. Each entry gives a regex + the
# canonical slug; we still validate ownership via units.json.
# Slugs here match units.json. Specific variants first so e.g. "heavy
# intercessor" beats the bare "intercessor" rule. The engine additionally
# requires that the emitted slug is valid within the already-determined
# faction (see classify_title), so cross-faction collisions can't escape.
# Generic role names — these are faction-ambiguous even though units.json
# may define them under exactly one faction. "Captain" exists as a word
# across many 40K factions in practice; "captain_in_gravis_armour" is
# specific enough to keep. Keep this list short — only block words that
# are commonly used AS NAMES across factions.
_GENERIC_ROLE_WORDS: frozenset[str] = frozenset({
    "captain", "chaplain", "librarian", "apothecary", "lieutenant",
    "champion", "ancient", "lord", "priest", "sergeant", "hero",
    "master", "scout", "commander", "assault_sergeant", "veteran_sergeant",
})


# Hand-curated ALIASES — how people actually write unit names in CMON titles
# vs. the official units.json slug. Each entry: (regex, canonical_slug). At
# load time we look up the slug's faction via units.json. Keeps a single
# source of truth (units.json) while accepting colloquial spellings.
_UNIT_ALIAS_RULES: list[tuple[str, str]] = [
    (r"\bfire warriors?\b",               "strike_team"),
    (r"\bcrisis suits?\b",                "crisis_battlesuits"),
    (r"\bburna boyz\b",                   "burna_boyz"),
    (r"\bmegadread\b|\bmeka[- ]?dread\b", "meka_dread"),
    (r"\bk?horne (ber)?serkers?\b|\bbe?r?serkers?\b|\bbeserks?\b|\bbezerkers?\b",
     "khorne_berserkers"),
    (r"\bintercessors?\b",                "intercessor_squad"),
    (r"\bterminators?\b",                 "terminator_squad"),
    # Shared slugs — canonical "home" faction wins. Lictor exists under both
    # Tyranids AND Genestealer Cults in 10e (GSC can ally Tyranids units), but
    # if someone just says "Lictor" in a title they mean the Tyranids one;
    # GSC users almost always disambiguate with "Aberrant" / "Purestrain" /
    # a GSC-specific keyword.
    (r"\blictors?\b",                     "lictor"),
    (r"\btanks?\s+of\s+the\s+imperium\b", ""),  # placeholder, no unit match
]




# ── auto-derived unique-unit rules (sourced from units.json) ───────────────
# For every slug that appears in exactly one faction in units.json AND whose
# name isn't a generic role, auto-generate a regex → (faction, slug) rule.
# Replaces the previously hand-written _UNIQUE_UNIT_RULES with a single
# source of truth: adding a unit to units.json makes weak-sup see it.
from collections import defaultdict
from functools import lru_cache as _lru_cache


@_lru_cache(maxsize=1)
def _auto_derived_unique_unit_rules() -> list[tuple[re.Pattern, str, str]]:
    """Return compiled (pattern, faction, slug) triples for every unit in
    units.json that is:
        1. Unique to one faction (slug appears only under that faction)
        2. Not a generic role (name not in _GENERIC_ROLE_WORDS)
    The regex is derived from the unit NAME (underscores→spaces),
    whole-word bounded, case-insensitive.
    """
    slug_to_factions: dict[str, set[str]] = defaultdict(set)
    slug_to_name: dict[str, str] = {}
    for unit in taxonomy.iter_units():
        slug_to_factions[unit.slug].add(unit.faction)
        slug_to_name.setdefault(unit.slug, unit.name or unit.slug)

    triples: list[tuple[re.Pattern, str, str]] = []
    for slug, factions_for_slug in slug_to_factions.items():
        if len(factions_for_slug) != 1:
            continue  # shared slug, ambiguous — skip
        name = slug_to_name[slug]
        normalised_name = name.lower().strip()
        # Generic-role filter: single-word names in the stop list
        if " " not in normalised_name and normalised_name.replace("-", "_") in _GENERIC_ROLE_WORDS:
            continue
        # Name-based regex: whole-word, tolerant of apostrophes and optional 's'.
        # Use the NAME (not slug) so "Scarab Occult Terminators" matches human phrasing.
        pattern_src = re.escape(normalised_name)
        # Let singular/plural be interchangeable at the end (e.g. Skitarii Ranger(s))
        if pattern_src.endswith("s"):
            pattern_src = pattern_src[:-1] + r"s?"
        else:
            pattern_src = pattern_src + r"s?"
        pat = re.compile(r"\b" + pattern_src + r"\b", re.IGNORECASE)
        faction = next(iter(factions_for_slug))
        triples.append((pat, faction, slug))
    # Sort longest-name first so specific names beat shorter ones
    triples.sort(key=lambda t: -len(t[0].pattern))
    return triples


@_lru_cache(maxsize=None)
def _auto_unit_rules_for_faction(faction: str) -> list[tuple[re.Pattern, str]]:
    """Auto-derive (regex, slug) rules for units WITHIN a faction. Used when
    step 3 established a faction and we now want to slot a unit_slug."""
    out: list[tuple[re.Pattern, str]] = []
    for unit in taxonomy.units_by_faction().get(faction, ()):
        name = (unit.name or "").lower().strip()
        if not name:
            continue
        pattern_src = re.escape(name)
        if pattern_src.endswith("s"):
            pattern_src = pattern_src[:-1] + r"s?"
        else:
            pattern_src = pattern_src + r"s?"
        pat = re.compile(r"\b" + pattern_src + r"\b", re.IGNORECASE)
        out.append((pat, unit.slug))
    # Longer names first so "Assault Intercessor Squad" beats "Intercessor Squad"
    out.sort(key=lambda t: -len(t[0].pattern))
    return out


@_lru_cache(maxsize=1)
def _compiled_alias_rules() -> list[tuple[re.Pattern, str, str]]:
    """Compile the hand-curated _UNIT_ALIAS_RULES. Each alias regex maps to
    a canonical slug; we look up the slug's faction from units.json."""
    out: list[tuple[re.Pattern, str, str]] = []
    # Build a slug→faction map (first match wins for the tiny 15-case ambiguity set)
    slug_to_first_faction: dict[str, str] = {}
    for unit in taxonomy.iter_units():
        slug_to_first_faction.setdefault(unit.slug, unit.faction)
    for regex_src, slug in _UNIT_ALIAS_RULES:
        faction = slug_to_first_faction.get(slug, "")
        if not faction:
            continue  # slug not in units.json (e.g. aliases to renamed slugs)
        out.append((re.compile(regex_src, re.IGNORECASE), faction, slug))
    # Put aliases BEFORE auto-derived so they override on overlap
    return out


# ── character table ────────────────────────────────────────────────────────
# Loaded from scripts/data/characters.json via photoanalyzer.taxonomy. Every
# character add is a one-line JSON edit — no Python changes needed to extend.


@_lru_cache(maxsize=1)
def character_table() -> list[tuple[list[re.Pattern], taxonomy.NamedCharacter]]:
    """Return the compiled character match table, ordered longest-alias-first
    so specific names beat generic ones (e.g. 'Lion El'Jonson' before 'Lion').
    """
    out: list[tuple[list[re.Pattern], taxonomy.NamedCharacter]] = []
    for character in taxonomy.characters():
        pats = [
            re.compile(r"\b" + re.escape(a) + r"\b", re.IGNORECASE)
            for a in character.aliases
        ]
        out.append((pats, character))
    # taxonomy.characters() already sorts longest-alias-first; re-ensure in
    # case the upstream sort ever changes.
    out.sort(key=lambda x: -len(x[1].aliases[0]))
    return out


# ── title classifier ───────────────────────────────────────────────────────
def classify_title(title: str) -> WeakLabel | None:
    """Run the weak-sup rule cascade over `title`. Returns None if nothing fired."""
    if not title:
        return None
    t = normalise_title(title)
    tl = t.lower()

    # Step 0: disambiguate contexts where a character alias is part of an IP
    # title (e.g. "Horus Heresy" — the era, not the primarch). Strip those
    # phrases before running the character table; let chapter rules catch
    # them instead.
    tl_chars = re.sub(r"\bhorus heresy\b", "heresy", tl)
    tl_chars = re.sub(r"\bage of darkness\b", "", tl_chars)

    # Step 1: named character (most specific). Chapter rules may still fire
    # AFTER a character match if we did NOT match; otherwise the character's
    # faction/slug is authoritative.
    for patterns, entry in character_table():
        for pat in patterns:
            if pat.search(tl_chars):
                return WeakLabel(
                    faction=entry.faction, unit_slug=entry.slug,
                    confidence=0.90, source="char_table",
                    rule=f"char:{entry.slug}",
                )

    # Step 2: chapter / sub-faction (emits faction, not unit)
    chapter_faction = ""
    chapter_tag = ""
    for kw, fac, tag in _CHAPTER_RULES:
        if re.search(kw, tl):
            chapter_faction, chapter_tag = fac, tag
            break

    # Step 3: bare faction keyword
    plain_faction = ""
    if not chapter_faction:
        for kw, fac in _FACTION_RULES:
            if re.search(kw, tl):
                plain_faction = fac
                break

    faction = chapter_faction or plain_faction

    # Step 3b: unique-unit fallback. If no faction keyword hit, try the
    # auto-derived unique-unit rules (every slug in units.json that lives in
    # exactly one faction and isn't a generic role word). Emits faction AND
    # unit_slug when a match fires.
    #
    # Alias rules (colloquial phrasings → canonical slug) run FIRST so
    # "fire warriors" maps to strike_team before the name-based match tries.
    if not faction:
        for pat, fac, slug in _compiled_alias_rules():
            if pat.search(tl):
                return WeakLabel(
                    faction=fac, unit_slug=slug,
                    confidence=0.80, source="unit_alias",
                    rule=f"alias:{slug}",
                )
        for pat, fac, slug in _auto_derived_unique_unit_rules():
            if pat.search(tl):
                return WeakLabel(
                    faction=fac, unit_slug=slug,
                    confidence=0.78, source="auto_unique_unit",
                    rule=f"auto:{slug}",
                )
        return None  # title gave us nothing

    # Step 4: unit-keyword rules — within the determined faction, check if
    # any unit name from units.json appears in the title. Auto-derived from
    # units.json (no hand-curated list here).
    for pat, slug in _auto_unit_rules_for_faction(faction):
        if pat.search(tl):
            note = f"chapter:{chapter_tag}" if chapter_tag else ""
            return WeakLabel(
                faction=faction, unit_slug=slug,
                confidence=0.80, source="unit_kw",
                rule=f"unit:{slug}|{note}".rstrip("|"),
            )
    # Alias rules (colloquial vernacular) as a secondary pass — only match if
    # the alias's slug is in the determined faction.
    for pat, alias_fac, slug in _compiled_alias_rules():
        if alias_fac == faction and pat.search(tl):
            return WeakLabel(
                faction=faction, unit_slug=slug,
                confidence=0.80, source="unit_alias",
                rule=f"alias:{slug}",
            )

    # Faction only (no unit-keyword hit). Confidence depends on chapter vs. bare
    return WeakLabel(
        faction=faction, unit_slug="",
        confidence=0.75 if chapter_faction else 0.65,
        source="chapter_kw" if chapter_faction else "faction_kw",
        rule=f"faction:{chapter_tag or faction}",
    )


# ── detector cross-check ───────────────────────────────────────────────────
_DETECTOR_FACTION_RE = re.compile(r"detector_faction=([a-z0-9_]+)", re.IGNORECASE)
_DETECTOR_CONF_RE = re.compile(r"detector_conf=([\d.]+)", re.IGNORECASE)


def parse_detector_signal(notes: str) -> tuple[str, float]:
    """Return (detector_faction, detector_confidence) extracted from notes.
    Returns ('', 0.0) if not present."""
    f_match = _DETECTOR_FACTION_RE.search(notes or "")
    c_match = _DETECTOR_CONF_RE.search(notes or "")
    det_faction = (f_match.group(1) if f_match else "").strip()
    try:
        det_conf = float(c_match.group(1)) if c_match else 0.0
    except ValueError:
        det_conf = 0.0
    if det_faction:
        # Canonicalise via taxonomy (the detector may emit chapter-level classes)
        resolved = taxonomy.resolve_faction(det_faction)
        if resolved:
            det_faction = resolved
    return det_faction, det_conf


def combine_with_detector(
    title_label: WeakLabel | None,
    detector_faction: str,
    detector_conf: float,
) -> WeakLabel | None:
    """Cross-check title weak-sup with detector's faction prediction.

    Policy:
    - title disagrees with confident detector → flag conflict, keep title's
      weak label but lower confidence and set flag (human should review).
    - title agrees with detector → bump confidence.
    - title empty, detector confident → emit detector-only faction with
      medium confidence.
    - detector absent / unconfident → pass title label through unchanged.

    "Title says" is the stronger signal in general (scene-level, painter-written);
    detector is a disagreement flagger and a fallback when titles are empty.
    """
    # Thresholds — tightened after the 100-entry test revealed a 52% conflict
    # rate. The detector is significantly noisier at the per-crop level than
    # Phase-0 scene-level metrics suggested; marginal (<0.6) predictions are
    # effectively coin flips and their disagreements are not signal.
    DET_AGREE_TRUST = 0.4     # bump title confidence only when this firm
    DET_CONFLICT_TRUST = 0.6  # flag conflict only when detector is confident
    DET_FALLBACK_TRUST = 0.5  # detector-only fallback threshold (unchanged)

    if title_label is not None:
        if not detector_faction:
            return title_label
        if detector_faction == title_label.faction and detector_conf >= DET_AGREE_TRUST:
            out = WeakLabel(**{**title_label.to_dict(), "flag": ""})
            out.confidence = min(0.95, title_label.confidence + 0.05)
            out.rule = title_label.rule + "+detector_agree"
            return out
        if (detector_faction != title_label.faction
                and detector_conf >= DET_CONFLICT_TRUST):
            # Title still wins — do NOT lower title confidence (detector too
            # noisy to justify that). Only raise the flag so human review can
            # look at this case.
            out = WeakLabel(**title_label.to_dict())
            out.rule = title_label.rule + f"+detector_disagree({detector_faction}@{detector_conf:.2f})"
            out.flag = "title_detector_conflict"
            return out
        # Detector weak or agreement-weak: pass title through unchanged.
        return title_label

    # No title label. Fall back to detector when confident.
    if detector_faction and detector_conf >= DET_FALLBACK_TRUST:
        return WeakLabel(
            faction=detector_faction,
            unit_slug="",
            confidence=min(0.65, detector_conf),
            source="detector_only",
            rule=f"detector:{detector_faction}",
        )
    return None


# ── WeakLabel → patch dict for label row ───────────────────────────────────
def to_row_patch(label: WeakLabel, labeller: str = "weak_sup") -> dict:
    """Convert a WeakLabel into the row-field patch for data/labels.csv."""
    return {
        "faction": label.faction,
        "unit_slug": label.unit_slug,
        "suggested_by": f"weak_regex:{label.source}",
        "confidence": f"{label.confidence:.4f}" if label.confidence else "",
        "labeller": labeller if label.flag else "",  # leave blank when conflicted
        "notes_append": f"weak:{label.rule}" + (f"; flag:{label.flag}" if label.flag else ""),
    }
