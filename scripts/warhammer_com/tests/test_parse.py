#!/usr/bin/env python3
"""
Unit tests for gw_shop_parse.py.

Run: yolo_env/bin/python3 -m pytest scripts/warhammer_com/tests/test_parse.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT))

import pytest  # noqa: E402

from gw_shop_parse import (  # noqa: E402
    camel_to_snake,
    classify_image_type,
    extract_master_sku_suffix,
    extract_product_payload,
    has_skip_token,
    infer_faction,
    is_box_product,
    match_faction_prefix,
    parse_image_filename,
)


def test_extract_master_sku_suffix_composite():
    assert extract_master_sku_suffix("P-245382-99123043006") == "99123043006"


def test_extract_master_sku_suffix_bare_numeric():
    assert extract_master_sku_suffix("99123043006") == "99123043006"


def test_extract_master_sku_suffix_empty():
    assert extract_master_sku_suffix("") == ""


def test_classify_image_type_box_group_composite_sku():
    # master_sku is composite ("P-240927-99120113100"); filename sku matches the suffix
    meta = parse_image_filename("/app/resources/catalog/product/920x950/99120113100_TAUCombatPatrolKroot1.jpg")
    assert classify_image_type(meta, is_box=True, master_sku="P-240927-99120113100") == "studio_group"


def test_classify_image_type_box_constituent_composite_sku():
    meta = parse_image_filename("/app/resources/catalog/product/920x950/99120113088_KrootRampagers1.jpg")
    assert classify_image_type(meta, is_box=True, master_sku="P-240927-99120113100") == "studio_box_constituent"


# ─── parse_image_filename ───────────────────────────────────────────────────

PARSE_CASES = [
    # (input, expected sku, expected name, expected idx)
    ("99123043006_CustodesCustodianDreadnought1.jpg", "99123043006", "CustodesCustodianDreadnought", "1"),
    ("99123043006_CustodesCustodianDreadnoughtALT.jpg", "99123043006", "CustodesCustodianDreadnought", "ALT"),
    ("99120113088_KrootRampagers1.jpg", "99120113088", "KrootRampagers", "1"),
    ("99120113092_KrootLoneSpear2.jpg", "99120113092", "KrootLoneSpear", "2"),
    ("99070113005_TauDarkstriderLead.jpg", "99070113005", "TauDarkstrider", "Lead"),
    ("99070113003_EtherealLive.jpg", "99070113003", "Ethereal", "Live"),
    ("99560108191_AquilonTerminatorsFirepikes01.jpg", "99560108191", "AquilonTerminatorsFirepikes", "01"),
    ("99550108194_CustodesShieldCaptain01.jpg", "99550108194", "CustodesShieldCaptain", "01"),
    ("99120113100_ENGIntoDarkSprue4.jpg", "99120113100", "ENGIntoDarkSprue", "4"),
    ("99120113100_TAUCombatPatrolKroot1.jpg", "99120113100", "TAUCombatPatrolKroot", "1"),
    ("60010199070_KTHivestorm3New.jpg", "60010199070", "KTHivestorm", "3New"),
]


@pytest.mark.parametrize("basename,sku,name,idx", PARSE_CASES)
def test_parse_image_filename_basic(basename, sku, name, idx):
    url = "/app/resources/catalog/product/920x950/" + basename
    meta = parse_image_filename(url)
    assert meta is not None
    assert meta.sku == sku
    assert meta.name == name
    assert meta.idx == idx


def test_parse_image_filename_accepts_bare_path():
    meta = parse_image_filename("/app/resources/catalog/product/920x950/99123043006_CustodesCustodianDreadnought1.jpg")
    assert meta is not None
    assert meta.sku == "99123043006"


def test_parse_image_filename_accepts_full_url():
    full = "https://www.warhammer.com/app/resources/catalog/product/920x950/99123043006_CustodesCustodianDreadnought1.jpg?fm=webp&w=800"
    meta = parse_image_filename(full)
    assert meta is not None
    assert meta.basename == "99123043006_CustodesCustodianDreadnought1.jpg"


def test_parse_image_filename_three_sixty_flag():
    url = "/app/resources/catalog/product/threeSixty/99120113100_TAUCombatPatrolKroot2026OTT1360/01-01.jpg"
    meta = parse_image_filename(url)
    # The nested sku+stem/01-01.jpg doesn't match FILENAME_RE, returns None.
    # That's acceptable — 360° frames are filtered anyway.
    assert meta is None or meta.is_three_sixty


def test_parse_image_filename_rejects_contentful_art():
    url = "/ur4mtvpiojcu/5IhHBFsfqjvItuUoZENZ0S/8577cc27226e029316e5844b2547ea1b/Aeronautica_Imperialis-_Landscape_Art_-_6.jpg"
    assert parse_image_filename(url) is None


def test_parse_image_filename_rejects_non_product_hosts():
    url = "https://cookie-cdn.cookiepro.com/logos/static/powered_by_logo.svg"
    assert parse_image_filename(url) is None


# ─── camel_to_snake ─────────────────────────────────────────────────────────

CAMEL_CASES = [
    ("CustodesCustodianDreadnought", "custodes_custodian_dreadnought"),
    ("TAUCombatPatrolKroot",         "tau_combat_patrol_kroot"),
    ("KTFarstalkerKinband",          "kt_farstalker_kinband"),
    ("AquilonTerminatorsFirepikes",  "aquilon_terminators_firepikes"),
    ("ENGIntoDarkSprue",             "eng_into_dark_sprue"),
    ("ComShadowsun",                 "com_shadowsun"),
    ("Kroot",                        "kroot"),
    ("",                             ""),
]


@pytest.mark.parametrize("pascal,snake", CAMEL_CASES)
def test_camel_to_snake(pascal, snake):
    assert camel_to_snake(pascal) == snake


# ─── faction inference ──────────────────────────────────────────────────────

def test_match_faction_prefix_longest_wins():
    # "legio_custodes" is longer than "custodes" — should win
    assert match_faction_prefix("legio_custodes_custodian_dreadnought") == "adeptus_custodes"


def test_match_faction_prefix_exact():
    assert match_faction_prefix("custodes") == "adeptus_custodes"


def test_match_faction_prefix_startswith():
    assert match_faction_prefix("custodes_shield_captain") == "adeptus_custodes"


def test_match_faction_prefix_no_false_positive_partial():
    # "taurus" should NOT match "tau" (boundary check requires a full-token match)
    assert match_faction_prefix("taurus") is None


def test_match_faction_prefix_kt_sentinel_recurses():
    # "kt_farstalker_kinband" → kt is sentinel None → recurses on "farstalker_kinband"
    # → no match → returns None (correctly; Kill Team is cross-faction)
    assert match_faction_prefix("kt_farstalker_kinband") is None


def test_match_faction_prefix_combat_patrol_recurses():
    # combat_patrol → sentinel → recurses on remainder
    assert match_faction_prefix("combat_patrol_kroot") == "tau_empire"


INFER_CASES = [
    # (raw_name, url_slug, expected faction)
    ("CustodesCustodianDreadnought", "legio-custodes-custodian-dreadnought-2026", "adeptus_custodes"),
    ("KrootRampagers", "combat-patrol-kroot-2026", "tau_empire"),
    ("TAUCombatPatrolKroot", "combat-patrol-kroot-2026", "tau_empire"),
    ("ENGIntoDarkSprue", "combat-patrol-kroot-2026", "tau_empire"),  # filename unknown → slug fallback
    ("", "legio-custodes-custodian-dreadnought-2026", "adeptus_custodes"),  # slug fallback only
    ("", "", "unknown"),  # nothing to go on
]


@pytest.mark.parametrize("raw,slug,expected", INFER_CASES)
def test_infer_faction(raw, slug, expected):
    assert infer_faction(raw, slug) == expected


# ─── SKIP_TOKENS ────────────────────────────────────────────────────────────

def test_has_skip_token_sprue():
    assert has_skip_token("ENGIntoDarkSprue")
    assert has_skip_token("SomeUnitSprueSet")


def test_has_skip_token_false_on_unit():
    assert not has_skip_token("CustodesCustodianDreadnought")
    assert not has_skip_token("KrootRampagers")


# ─── is_box_product / classify_image_type ──────────────────────────────────

def test_is_box_product_by_name_prefix():
    assert is_box_product("", "Combat Patrol: Kroot")
    assert is_box_product("", "Battleforce: Space Marines")
    assert is_box_product("", "Start Collecting Necrons")


def test_is_box_product_by_product_type():
    assert is_box_product("combatPatrol", "Some Custom Name")


def test_is_box_product_single_unit():
    assert not is_box_product("miniatureKit", "Custodian Dreadnought")


def test_classify_image_type_single_unit_hero():
    meta = parse_image_filename("/app/resources/catalog/product/920x950/99123043006_CustodesCustodianDreadnought1.jpg")
    assert classify_image_type(meta, is_box=False, master_sku="99123043006") == "studio_hero"


def test_classify_image_type_single_unit_alt():
    meta = parse_image_filename("/app/resources/catalog/product/920x950/99123043006_CustodesCustodianDreadnought3.jpg")
    assert classify_image_type(meta, is_box=False, master_sku="99123043006") == "studio_alt"


def test_classify_image_type_box_group():
    meta = parse_image_filename("/app/resources/catalog/product/920x950/99120113100_TAUCombatPatrolKroot1.jpg")
    assert classify_image_type(meta, is_box=True, master_sku="99120113100") == "studio_group"


def test_classify_image_type_box_constituent_different_sku():
    # Constituent from the combat patrol, originally from a separate kit
    meta = parse_image_filename("/app/resources/catalog/product/920x950/99120113088_KrootRampagers1.jpg")
    assert classify_image_type(meta, is_box=True, master_sku="99120113100") == "studio_box_constituent"


def test_classify_image_type_box_constituent_same_sku_different_name():
    # Per-unit shot embedded under the box's SKU (e.g. Kroot Rider images
    # filed under the Combat Patrol SKU)
    meta = parse_image_filename("/app/resources/catalog/product/920x950/99120113100_KrootLoneSpear5.jpg")
    assert classify_image_type(
        meta, is_box=True,
        master_sku="P-240927-99120113100",
        box_name="Combat Patrol: Kroot",
    ) == "studio_box_constituent"


def test_classify_image_type_box_group_same_sku_matching_name():
    # Genuine box hero shot: SKU and name both match the box
    meta = parse_image_filename("/app/resources/catalog/product/920x950/99120113100_TAUCombatPatrolKroot1.jpg")
    assert classify_image_type(
        meta, is_box=True,
        master_sku="P-240927-99120113100",
        box_name="TAU Combat Patrol Kroot",
    ) == "studio_group"


# ─── extract_product_payload (integration against recon artefacts) ──────────

def _load_recon(relpath: str) -> dict:
    path = HERE.parent / "recon" / relpath
    return json.loads(path.read_text())


def test_extract_payload_custodian_dreadnought():
    nd = _load_recon("01_single_unit_custodian_dreadnought_next_data.json")
    p = extract_product_payload(nd, url_slug="legio-custodes-custodian-dreadnought-2026")
    assert p.name == "Custodian Dreadnought"
    assert p.product_type_name in ("miniatureKit", "")
    assert len(p.image_urls) == 8
    # Every URL is a product catalog path
    assert all("/app/resources/catalog/product/" in u for u in p.image_urls)


def test_extract_payload_combat_patrol_kroot():
    nd = _load_recon("02_combat_patrol_kroot_next_data.json")
    p = extract_product_payload(nd, url_slug="combat-patrol-kroot-2026")
    assert p.name == "Combat Patrol: Kroot"
    assert len(p.image_urls) >= 20
    # Heuristic: should be a box
    assert is_box_product(p.product_type_name, p.name)
    # At least one constituent with a non-box SKU
    metas = [parse_image_filename(u) for u in p.image_urls]
    metas = [m for m in metas if m is not None]
    assert any(m.sku != p.master_sku for m in metas)
