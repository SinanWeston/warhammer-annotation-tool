#!/usr/bin/env python3
"""
Pure parsers for warhammer.com product scraper.

No IO. No browser. Deterministic. Unit-testable.

Public interface:
  parse_image_filename(url)           → ImageMeta | None
  camel_to_snake(name)                → str
  match_faction_prefix(snake, mapping)→ str | None
  infer_faction(raw_name, url_slug)   → str           # 'unknown' when nothing matches
  extract_product_payload(next_data)  → ProductPayload
  is_box_product(product_type, name)  → bool
  classify_image_type(meta, is_box, master_sku)  → str
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gw_shop_constants import (  # noqa: E402
    BOX_PRODUCT_NAME_PREFIXES,
    FACTION_PREFIX_MAP,
    IMAGE_360_PREFIX,
    IMAGE_920x950,
    SKIP_TOKENS,
)


# ─── Dataclasses ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ImageMeta:
    """Parsed product-image filename."""
    sku: str
    name: str          # raw PascalCase, e.g. "CustodesCustodianDreadnought"
    idx: str           # variant/index token: "1", "01", "ALT", "Live", "Lead", "New", "3New", or ""
    basename: str      # full filename ("99123043006_CustodesCustodianDreadnought1.jpg")
    is_three_sixty: bool

    @property
    def unit_slug(self) -> str:
        return camel_to_snake(self.name)


@dataclass(frozen=True)
class ProductPayload:
    """What we care about from a product page's NEXT_DATA."""
    product_id: str
    name: str
    url_slug: str
    master_sku: str
    product_type_name: str
    image_urls: list[str]


# ─── Regexes ────────────────────────────────────────────────────────────────

# Matches "/app/resources/catalog/product/920x950/{sku}_{stem}.jpg" (± query)
FILENAME_RE = re.compile(
    r"^(?P<sku>\d{10,12})_(?P<stem>[A-Za-z][A-Za-z0-9]*)\.jpg$"
)

# Trailing variant markers on the stem: pure digits, named tokens, or digit+letters.
# Ordered so specific literals win over the \d+[A-Za-z]* fallback.
TAIL_RE = re.compile(r"(?P<idx>ALT|Live|Lead|New|\d+[A-Za-z]*)$")


# ─── Filename parsing ───────────────────────────────────────────────────────

def parse_image_filename(url_or_path: str) -> ImageMeta | None:
    """
    Extract (sku, name, idx) from a product image URL or path.

    Returns None when the URL is not a /app/resources/catalog/product/... image,
    or when the filename does not match the expected SKU_NAME.jpg grammar.
    """
    parsed = urlparse(url_or_path)
    path = parsed.path or url_or_path  # accept bare paths too

    if IMAGE_920x950 not in path and IMAGE_360_PREFIX not in path:
        return None

    is_three_sixty = IMAGE_360_PREFIX in path
    # Product's 360° turntable uses a nested dir: threeSixty/{sku}_{name}{x}/01-01.jpg
    # Those frames are out-of-scope per the plan, but flag them so the caller can drop.
    basename = path.rsplit("/", 1)[-1]

    m = FILENAME_RE.match(basename)
    if not m:
        return None

    sku = m.group("sku")
    stem = m.group("stem")

    tail = TAIL_RE.search(stem)
    if tail:
        idx = tail.group("idx")
        name = stem[: tail.start()]
    else:
        idx = ""
        name = stem

    if not name:
        return None

    return ImageMeta(
        sku=sku,
        name=name,
        idx=idx,
        basename=basename,
        is_three_sixty=is_three_sixty,
    )


def has_skip_token(name: str) -> bool:
    """Returns True if the PascalCase name contains a skip token (sprue, book, paint…)."""
    return any(tok in name for tok in SKIP_TOKENS)


# ─── Case transforms ────────────────────────────────────────────────────────

_CAMEL_SPLIT_1 = re.compile(r"([A-Z]+)([A-Z][a-z])")   # "TAUCombat" → "TAU_Combat"
_CAMEL_SPLIT_2 = re.compile(r"([a-z0-9])([A-Z])")      # "CombatPatrol" → "Combat_Patrol"


def camel_to_snake(s: str) -> str:
    """
    Convert PascalCase / acronymed PascalCase to snake_case.

    Examples:
      CustodesCustodianDreadnought → custodes_custodian_dreadnought
      TAUCombatPatrolKroot         → tau_combat_patrol_kroot
      KTFarstalkerKinband          → kt_farstalker_kinband
      ENGIntoDarkSprue             → eng_into_dark_sprue
    """
    if not s:
        return ""
    s = _CAMEL_SPLIT_1.sub(r"\1_\2", s)
    s = _CAMEL_SPLIT_2.sub(r"\1_\2", s)
    return s.lower()


# ─── Faction attribution ────────────────────────────────────────────────────

def match_faction_prefix(
    snake_name: str,
    mapping: dict[str, str | None] = FACTION_PREFIX_MAP,
) -> str | None:
    """
    Longest-prefix match against FACTION_PREFIX_MAP. Recurses when mapping yields None
    (sentinel for "strip this prefix and look at the remainder").

    Returns the faction slug (e.g. 'adeptus_custodes') or None if nothing matches.
    """
    # Sort keys longest-first so "legio_custodes" beats "custodes" etc.
    for key in sorted(mapping.keys(), key=len, reverse=True):
        if snake_name == key or snake_name.startswith(key + "_"):
            value = mapping[key]
            if value is None:
                # Sentinel: strip and recurse on the remainder.
                remainder = snake_name[len(key):].lstrip("_")
                if not remainder:
                    return None
                return match_faction_prefix(remainder, mapping)
            return value
    return None


def infer_faction(raw_name: str, url_slug: str | None = None) -> str:
    """
    Best-effort faction attribution cascade:

      1. Match filename prefix (strongest signal).
      2. If that fails, try URL slug tokens (e.g. 'combat-patrol-kroot-2026' contains 'kroot').
      3. Return 'unknown' as the triage bucket.
    """
    # 1) Filename prefix
    snake = camel_to_snake(raw_name)
    faction = match_faction_prefix(snake)
    if faction:
        return faction

    # 2) URL slug fallback
    if url_slug:
        slug_tokens = url_slug.lower().replace("-", "_")
        faction = match_faction_prefix(slug_tokens)
        if faction:
            return faction
        # Also try each slug token independently (catches 'combat-patrol-KROOT-2026' →
        # the 'kroot' token alone resolves cleanly).
        for tok in url_slug.lower().split("-"):
            faction = match_faction_prefix(tok)
            if faction:
                return faction

    return "unknown"


# ─── NEXT_DATA extraction ───────────────────────────────────────────────────

class SchemaError(Exception):
    """Raised when window.__NEXT_DATA__ doesn't match the expected shape."""


def extract_product_payload(next_data: dict, url_slug: str = "") -> ProductPayload:
    """
    Drill into window.__NEXT_DATA__ and return a ProductPayload.

    Schema (verified on recon artefacts):
      props.pageProps.context.productInformation.inStore.product
        .id
        .productType.name
        .masterData.current
          .name
          .masterVariant
            .sku
            .images: [{url, label}, ...]
    """
    try:
        product = (
            next_data["props"]["pageProps"]["context"]
            ["productInformation"]["inStore"]["product"]
        )
    except (KeyError, TypeError) as e:
        raise SchemaError(
            "NEXT_DATA missing props.pageProps.context.productInformation.inStore.product"
        ) from e

    product_id = product.get("id", "")
    product_type_name = (product.get("productType") or {}).get("name", "")

    current = (product.get("masterData") or {}).get("current") or {}
    name = current.get("name", "")
    master_variant = current.get("masterVariant") or {}
    master_sku = master_variant.get("sku", "")
    images_raw = master_variant.get("images") or []

    image_urls = []
    for img in images_raw:
        if isinstance(img, dict):
            u = img.get("url", "")
        else:
            u = str(img)
        if u:
            image_urls.append(u)

    if not image_urls:
        # Don't raise — some products genuinely have no images (book listings, etc.)
        pass

    return ProductPayload(
        product_id=product_id,
        name=name,
        url_slug=url_slug,
        master_sku=master_sku,
        product_type_name=product_type_name,
        image_urls=image_urls,
    )


# ─── Product-type classification ────────────────────────────────────────────

def extract_master_sku_suffix(master_sku: str) -> str:
    """
    commercetools / GW store master SKUs like 'P-245382-99123043006'.

    Return the trailing numeric part (matches filename SKUs), or `master_sku`
    unchanged when the format is atypical.
    """
    if not master_sku:
        return ""
    if "-" in master_sku:
        tail = master_sku.rsplit("-", 1)[-1]
        if tail.isdigit():
            return tail
    return master_sku


def is_box_product(product_type_name: str, display_name: str) -> bool:
    """True for multi-unit bundle products (Combat Patrol, Battleforce, etc.)."""
    if product_type_name and product_type_name.lower() in (
        "combatpatrol", "battleforce", "startingset", "armyset"
    ):
        return True
    return any(display_name.startswith(p) for p in BOX_PRODUCT_NAME_PREFIXES)


def classify_image_type(
    meta: ImageMeta,
    is_box: bool,
    master_sku: str,
    box_name: str = "",
) -> str:
    """
    Returns one of:
      studio_hero             - single-unit product, first image
      studio_alt              - single-unit product, alt angles
      studio_group            - box product, filename SKU == box SKU AND filename name == box name
      studio_box_constituent  - box product, per-unit shot: either
                                 (a) filename SKU differs from box SKU (from a separate kit), OR
                                 (b) SKU matches but filename name differs from box name
                                     (GW often embeds per-unit shots under the box's own SKU)
    """
    if is_box:
        master_sku_numeric = extract_master_sku_suffix(master_sku)
        same_sku = meta.sku == master_sku_numeric
        if same_sku and box_name:
            box_slug = camel_to_snake(box_name.replace(":", "").replace(" ", ""))
            file_slug = camel_to_snake(meta.name)
            if file_slug == box_slug:
                return "studio_group"
            return "studio_box_constituent"
        if same_sku:
            # Fallback when caller didn't pass box_name — default to group
            return "studio_group"
        return "studio_box_constituent"

    # Single-unit product: image 1 is hero, others are alt.
    if meta.idx == "1":
        return "studio_hero"
    return "studio_alt"


def constituent_unit_name(meta: ImageMeta, box_payload: ProductPayload) -> str:
    """
    For box-product images, decide which display name to use.

    If the image's filename SKU ≠ the box's master SKU (true constituent),
    derive the unit name from the filename (camel-split, title-cased).

    Special case: some boxes carry internal unit variants that share the box's SKU
    but have a different camel-split name than the box itself. Detect that and still
    prefer the filename-derived name (e.g. "KrootRider5" inside box sku 99120113100,
    box name "Combat Patrol: Kroot" → unit name "Kroot Rider").
    """
    box_slug = camel_to_snake(box_payload.name.replace(":", "").replace(" ", ""))
    file_slug = camel_to_snake(meta.name)
    master_sku_numeric = extract_master_sku_suffix(box_payload.master_sku)
    if meta.sku != master_sku_numeric or file_slug != box_slug:
        return _pretty_from_camel(meta.name)
    return box_payload.name


def _pretty_from_camel(pascal: str) -> str:
    """PascalCase → 'Title Cased Words'. Acronyms (ALL-CAPS runs) are kept uppercase."""
    snake = camel_to_snake(pascal)
    return " ".join(tok.upper() if tok in {"tau", "kt", "am", "as", "csm", "sm", "gsc"}
                    else tok.capitalize()
                    for tok in snake.split("_"))
