"""Tests for photoanalyzer.label.schema — LabelRecord dataclass + CSV roundtrip."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import pytest

from photoanalyzer.label.schema import (
    SENTINEL_SLUGS,
    V2_COLUMNS,
    VALID_SOURCES,
    VALID_SPLITS,
    LabelRecord,
    filter_trainable,
    is_sentinel,
    is_trainable,
    read_labels_csv,
    write_labels_csv,
)


def test_v2_columns_fixed_order():
    """Column order must be stable — readers may index by position."""
    assert V2_COLUMNS[0] == "crop_path"
    assert V2_COLUMNS[-1] == "notes"
    assert len(V2_COLUMNS) == 13


def test_valid_sources_include_all_scraper_sources():
    for s in ("gw_shop", "cmon", "dakka", "reddit", "wh_community"):
        assert s in VALID_SOURCES


def test_label_record_defaults():
    r = LabelRecord(crop_path="x.jpg", source="cmon")
    assert r.unit_slug == ""
    assert r.faction == ""
    assert r.view_idx is None
    assert r.confidence is None
    assert r.split == ""
    assert r.created_at  # auto-set


def test_validate_ok():
    r = LabelRecord(
        crop_path="data/crops/cmon/1/00.jpg", source="cmon",
        faction="space_marines", unit_slug="captain",
    )
    assert r.validate() == []


def test_validate_catches_bad_source():
    r = LabelRecord(crop_path="x.jpg", source="notasource")
    errs = r.validate()
    assert any("source" in e for e in errs)


def test_validate_catches_bad_split():
    r = LabelRecord(crop_path="x.jpg", source="cmon", split="train")  # not in VALID_SPLITS
    errs = r.validate()
    assert any("split" in e for e in errs)


def test_validate_catches_negative_view_idx():
    r = LabelRecord(crop_path="x.jpg", source="cmon", view_idx=-1)
    errs = r.validate()
    assert any("view_idx" in e for e in errs)


def test_validate_catches_out_of_range_confidence():
    r = LabelRecord(crop_path="x.jpg", source="cmon", confidence=1.2)
    errs = r.validate()
    assert any("confidence" in e for e in errs)


def test_validate_strict_requires_faction_and_source():
    r = LabelRecord(crop_path="x.jpg", source="")  # empty source
    errs = r.validate(strict=True)
    assert any("faction" in e for e in errs)
    assert any("source" in e for e in errs)


def test_to_csv_row_has_all_v2_columns():
    r = LabelRecord(
        crop_path="x.jpg", source="cmon", faction="space_marines",
        unit_slug="captain", view_idx=3, confidence=0.87,
    )
    row = r.to_csv_row()
    assert set(row.keys()) == set(V2_COLUMNS)
    assert row["view_idx"] == "3"
    assert row["confidence"] == "0.8700"


def test_from_csv_row_v2_roundtrip():
    original = LabelRecord(
        crop_path="data/crops/cmon/1/00.jpg",
        source="cmon",
        source_ref="cmon:1",
        instance_id="cmon:1",
        view_idx=0,
        faction="space_marines",
        unit_slug="captain",
        suggested_by="llm:claude-sonnet-4-5",
        confidence=0.87,
        labeller="sinan",
        split="gallery",
        notes="painter: Yellow one",
    )
    row = original.to_csv_row()
    parsed = LabelRecord.from_csv_row(row)
    # Ignore created_at drift (auto-set in from_csv_row if empty — here present)
    assert parsed.crop_path == original.crop_path
    assert parsed.source == original.source
    assert parsed.instance_id == original.instance_id
    assert parsed.view_idx == original.view_idx
    assert parsed.faction == original.faction
    assert parsed.unit_slug == original.unit_slug
    assert parsed.confidence == pytest.approx(0.87)
    assert parsed.split == original.split


def test_from_v1_row_supplies_default_source():
    """Legacy labels.csv at scripts/phase3/ has `source` column; phase1 may not."""
    v1_row = {
        "crop_path": "scripts/phase3/crops/adepta_sororitas/x__00.jpg",
        "faction": "adepta_sororitas",
        "unit_slug": "battle_sisters",
        "notes": "",
        "split": "gallery",
    }
    r = LabelRecord.from_v1_row(v1_row, default_source="annotation")
    assert r.source == "annotation"
    assert r.unit_slug == "battle_sisters"
    assert r.split == "gallery"


def test_from_v1_row_preserves_existing_source():
    v1_row = {
        "crop_path": "x.jpg", "faction": "space_marines", "unit_slug": "captain",
        "notes": "", "source": "post_export", "split": "",
    }
    # post_export is NOT in VALID_SOURCES but we migrate it verbatim; the
    # migration script re-maps values. Validate catches it downstream.
    r = LabelRecord.from_v1_row(v1_row, default_source="annotation")
    assert r.source == "post_export"


def test_write_then_read_roundtrip():
    recs = [
        LabelRecord(crop_path="a.jpg", source="cmon", faction="orks",
                    unit_slug="boyz", split="gallery"),
        LabelRecord(crop_path="b.jpg", source="gw_shop", faction="space_marines",
                    unit_slug="captain", split="query", confidence=0.93),
        LabelRecord(crop_path="c.jpg", source="annotation", faction="necrons"),
    ]
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "labels.csv"
        n = write_labels_csv(p, recs)
        assert n == 3
        loaded = list(read_labels_csv(p))
        assert len(loaded) == 3
        assert loaded[0].crop_path == "a.jpg"
        assert loaded[1].confidence == pytest.approx(0.93)
        assert loaded[2].unit_slug == ""  # unlabelled


def test_write_atomic_leaves_no_tmp_on_success():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "labels.csv"
        write_labels_csv(p, [LabelRecord(crop_path="x.jpg", source="cmon")])
        assert p.exists()
        assert not p.with_suffix(".csv.tmp").exists()


def test_append_requires_existing_file():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "labels.csv"
        with pytest.raises(FileNotFoundError):
            write_labels_csv(p, [LabelRecord(crop_path="x.jpg", source="cmon")],
                             append=True)


def test_append_extends_existing_file():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "labels.csv"
        write_labels_csv(p, [LabelRecord(crop_path="a.jpg", source="cmon")])
        write_labels_csv(p, [LabelRecord(crop_path="b.jpg", source="cmon")],
                         append=True)
        loaded = list(read_labels_csv(p))
        assert [r.crop_path for r in loaded] == ["a.jpg", "b.jpg"]


def test_tolerates_v1_csv():
    """A CSV with only v1 columns (crop_path, faction, unit_slug, notes,
    source, split) loads cleanly."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "labels_v1.csv"
        with p.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["crop_path", "faction", "unit_slug",
                                              "notes", "source", "split"])
            w.writeheader()
            w.writerow({"crop_path": "legacy.jpg", "faction": "orks",
                        "unit_slug": "boyz", "notes": "", "source": "post_export",
                        "split": "gallery"})
        records = list(read_labels_csv(p))
        assert len(records) == 1
        assert records[0].crop_path == "legacy.jpg"
        assert records[0].unit_slug == "boyz"
        assert records[0].view_idx is None
        assert records[0].confidence is None


# ── sentinel guards — critical data-integrity tests ───────────────────────
def test_sentinel_slugs_includes_known_statuses():
    assert "__bad_crop__" in SENTINEL_SLUGS
    assert "__unknown__" in SENTINEL_SLUGS
    assert "__ambiguous__" in SENTINEL_SLUGS


@pytest.mark.parametrize("slug", [
    "__bad_crop__", "__unknown__", "__ambiguous__",
    # Defensive: any __foo__ pattern counts, even if not explicitly enumerated
    "__new_future_sentinel__",
])
def test_is_sentinel_true_for_sentinels(slug):
    assert is_sentinel(slug) is True


@pytest.mark.parametrize("slug", [
    "", "captain", "intercessor_squad", "plague_marines",
    # Half-matches don't count: only `__foo__` is a sentinel
    "__half", "half__", "_captain_", "captain__", "_captain", "__",
])
def test_is_sentinel_false_for_real_slugs(slug):
    assert is_sentinel(slug) is False


def test_is_trainable_requires_faction_and_non_sentinel_slug():
    # All good
    r = LabelRecord(crop_path="x.jpg", source="cmon",
                    faction="orks", unit_slug="boyz")
    assert r.is_trainable() is True
    assert is_trainable(r) is True


def test_is_trainable_false_for_empty_slug():
    r = LabelRecord(crop_path="x.jpg", source="cmon", faction="orks", unit_slug="")
    assert r.is_trainable() is False


def test_is_trainable_false_for_empty_faction():
    r = LabelRecord(crop_path="x.jpg", source="cmon", faction="", unit_slug="boyz")
    assert r.is_trainable() is False


def test_is_trainable_false_for_sentinel_slug():
    # THE critical case: a bad crop MUST NOT leak into training
    r = LabelRecord(crop_path="x.jpg", source="cmon",
                    faction="orks", unit_slug="__bad_crop__")
    assert r.is_trainable() is False
    assert r.is_sentinel() is True


def test_is_trainable_respects_require_split():
    r = LabelRecord(crop_path="x.jpg", source="cmon",
                    faction="orks", unit_slug="boyz", split="")
    assert r.is_trainable(require_split=False) is True
    assert r.is_trainable(require_split=True) is False
    r.split = "gallery"
    assert r.is_trainable(require_split=True) is True


def test_filter_trainable_removes_sentinels_and_empty_rows():
    rows = [
        LabelRecord(crop_path="a.jpg", source="cmon",
                    faction="orks", unit_slug="boyz"),                 # pass
        LabelRecord(crop_path="b.jpg", source="cmon",
                    faction="orks", unit_slug="__bad_crop__"),         # skip (sentinel)
        LabelRecord(crop_path="c.jpg", source="cmon",
                    faction="orks", unit_slug=""),                     # skip (no slug)
        LabelRecord(crop_path="d.jpg", source="cmon",
                    faction="", unit_slug="rubric_marines"),            # skip (no faction)
        LabelRecord(crop_path="e.jpg", source="cmon",
                    faction="chaos_space_marines", unit_slug="__unknown__"),  # skip (sentinel)
        LabelRecord(crop_path="f.jpg", source="cmon",
                    faction="tyranids", unit_slug="lictor"),           # pass
    ]
    trainable = list(filter_trainable(rows))
    assert [r.crop_path for r in trainable] == ["a.jpg", "f.jpg"]
