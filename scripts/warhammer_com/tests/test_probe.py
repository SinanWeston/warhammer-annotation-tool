#!/usr/bin/env python3
"""
End-to-end probe test for the warhammer.com scraper.

Live network test — requires bootstrap_waf.py to have run first so the browser
profile has WAF cookies. Scrapes 2 known-good URLs and asserts the pipeline
produces the expected file layout + manifest rows.

Run:
    yolo_env/bin/python3 -m pytest scripts/warhammer_com/tests/test_probe.py -v

Skip when network unavailable:
    SKIP_LIVE=1 yolo_env/bin/python3 -m pytest ...
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT))
sys.path.insert(0, str(PARENT.parent))

import pytest  # noqa: E402

SKIP_LIVE = os.environ.get("SKIP_LIVE", "0") == "1"
pytestmark = pytest.mark.skipif(SKIP_LIVE, reason="SKIP_LIVE=1 set")


@pytest.fixture(scope="module")
def scrape_results(tmp_path_factory):
    """Run the probe once and share results across assertions."""
    import gw_shop_scrape  # noqa: PLC0415
    from gw_shop_constants import IMAGES_ROOT, PROBE_URLS  # noqa: PLC0415

    stats = gw_shop_scrape.run(
        only_urls=list(PROBE_URLS),
        headless=True,
    )
    return {"stats": stats, "images_root": IMAGES_ROOT, "probe_urls": list(PROBE_URLS)}


def test_probe_products_scraped(scrape_results):
    stats = scrape_results["stats"]
    assert stats.products_scraped >= 2, f"expected ≥2 scraped, got {stats.summary()}"


def test_probe_custodian_dreadnought_dir_exists(scrape_results):
    root = scrape_results["images_root"]
    d = root / "adeptus_custodes" / "custodes_custodian_dreadnought"
    assert d.exists(), f"expected {d} to exist"
    jpgs = list(d.glob("*.jpg"))
    assert len(jpgs) >= 5, f"expected ≥5 images, got {len(jpgs)}"


def test_probe_kroot_combat_patrol_constituents(scrape_results):
    root = scrape_results["images_root"]
    group_dir = root / "tau_empire" / "tau_combat_patrol_kroot"
    assert group_dir.exists(), f"expected {group_dir} to exist (box group shots)"

    # Expect at least one of the constituent unit dirs to exist
    candidates = [
        root / "tau_empire" / "kroot_rampagers",
        root / "tau_empire" / "kroot_lone_spear",
        root / "tau_empire" / "kroot_rider",
    ]
    existing = [c for c in candidates if c.exists()]
    assert existing, f"expected at least one of {candidates} to exist"


def test_probe_no_sprue_files(scrape_results):
    root = scrape_results["images_root"]
    sprues = list(root.rglob("*Sprue*.jpg"))
    assert not sprues, f"sprue files leaked through: {sprues[:5]}"


def test_probe_manifest_rows_match_disk(scrape_results):
    """Every saved image should have exactly one row in scrape_log.csv."""
    from scraper_utils import SCRAPE_LOG  # noqa: PLC0415
    root = scrape_results["images_root"]

    disk_files = set(p.name for p in root.rglob("*.jpg"))
    assert disk_files, "no images on disk — probe didn't save anything"

    manifest_filenames: set[str] = set()
    if SCRAPE_LOG.exists():
        with SCRAPE_LOG.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("source_platform") == "warhammer_shop":
                    manifest_filenames.add(Path(row["filename"]).name)

    leaks = disk_files - manifest_filenames
    assert not leaks, f"{len(leaks)} images on disk have no manifest row: {list(leaks)[:5]}"


def test_probe_resumability_no_new_downloads(scrape_results):
    """Running the probe again should download zero new files (dedup + skip works)."""
    import gw_shop_scrape  # noqa: PLC0415

    stats2 = gw_shop_scrape.run(
        only_urls=scrape_results["probe_urls"],
        headless=True,
    )
    # products re-fetched (no scraped_at skip since we pass only_urls), but
    # every image should dedup on MD5.
    assert stats2.images_saved == 0, (
        f"resumable dedup broken — re-run saved {stats2.images_saved} images:\n"
        f"{stats2.summary()}"
    )
