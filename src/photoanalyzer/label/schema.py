"""labels.csv v2 schema and roundtrip I/O.

The label record is the canonical unit of training-data provenance. Every
crop we train on, evaluate on, or serve from the retrieval gallery ultimately
comes from a row in labels.csv.

v2 schema (2026-04-17):

    crop_path     relative path from repo root, e.g. "data/crops/cmon/475293/00.jpg"
    source        provenance: gw_shop | cmon | dakka | reddit | wh_community
                              | annotation | synthetic | user_photo
    source_ref    URL or "{source}:{id}" — lets us trace back to origin
    instance_id   groups crops of the same physical mini (e.g. "cmon:475293")
                  — optional but critical for multi-view augmentation
    view_idx      0-indexed view number within an instance (empty if single-view)
    faction       canonical faction slug (see photoanalyzer.taxonomy.FACTIONS)
    unit_slug     canonical unit slug within that faction (empty = unlabelled)
    suggested_by  "human" | "weak_regex" | "llm:{model}" | "yolo_detect" | ""
    confidence    float 0–1 from whatever produced the label (empty if human)
    labeller      user id or agent id who confirmed (empty if auto-accepted)
    split         "" (uncommitted) | "gallery" | "query" | "benchmark"
    created_at    ISO8601 UTC, e.g. "2026-04-17T14:23:05Z"
    notes         free-text — painter name, caveats, LLM reasoning, etc.

The schema is versioned intentionally. Migrations live in
`scripts/migrate_labels.py`; read_labels_csv tolerates v1 (no v2 columns) by
best-effort inference.
"""

from __future__ import annotations

import csv
import datetime as _dt
import os
import time
from dataclasses import asdict, dataclass, field, fields


class _CrossProcessMkdirLock:
    """Advisory cross-process lock using atomic `mkdir` as the primitive.

    Why this and not `filelock`? The Node backend uses `proper-lockfile`,
    which creates a DIRECTORY at the lockfile path (atomic `mkdir` is the
    underlying primitive). `filelock` creates a FILE and uses `fcntl.flock`
    — the two mechanisms don't interop (each sees the other's lockfile as
    the wrong kind of inode and errors out). To get real Python↔Node
    serialisation on a shared sidecar path we use the same primitive both
    sides of the fence. Zero extra deps.

    Stale-lock handling is minimal: if a process crashes holding the lock,
    the directory persists until manually cleaned. The Node side's
    proper-lockfile heartbeats the lockfile's mtime and treats anything
    older than its `stale` config (default 10s) as abandoned, so it
    auto-recovers. Python here doesn't heartbeat — writes are sub-second,
    so the blast radius of a stale Python lock is limited to a short
    user-visible pause before Node's stale detector kicks in.
    """

    def __init__(self, path, *, timeout: float = 30.0, poll: float = 0.05):
        self.path = str(path)
        self.timeout = timeout
        self.poll = poll
        self._held = False

    def __enter__(self):
        start = time.monotonic()
        while True:
            try:
                os.mkdir(self.path)
                self._held = True
                return self
            except FileExistsError:
                if time.monotonic() - start > self.timeout:
                    raise TimeoutError(f"Could not acquire lock {self.path} within {self.timeout}s")
                time.sleep(self.poll)

    def __exit__(self, *_):
        if self._held:
            try:
                os.rmdir(self.path)
            except FileNotFoundError:
                pass
            self._held = False
        return False
from pathlib import Path
from typing import Iterable, Iterator


# ── schema constants ───────────────────────────────────────────────────────
SCHEMA_VERSION = 2

V2_COLUMNS: tuple[str, ...] = (
    "crop_path",
    "source",
    "source_ref",
    "instance_id",
    "view_idx",
    "faction",
    "unit_slug",
    "suggested_by",
    "confidence",
    "labeller",
    "split",
    "created_at",
    "notes",
)

VALID_SOURCES: frozenset[str] = frozenset({
    "gw_shop", "cmon", "dakka", "reddit", "wh_community",
    "annotation", "synthetic", "user_photo",
})

VALID_SPLITS: frozenset[str] = frozenset({
    "", "gallery", "query", "benchmark",
})

# Sentinel slugs — values we write into `unit_slug` to mark a crop as
# definitively NOT usable for training. Anything matching `__*__` is a sentinel
# by convention; the set below enumerates what the labeller UI actually emits.
#
# Why sentinel slugs at all? We want to keep the row in labels.csv (for the
# audit trail: "YOLO fired on this region, human rejected it — negative example
# for future detector training") but exclude the row from the retrieval gallery
# and the faction classifier. Stuffing the reason into unit_slug lets us do
# both without adding a new column.
#
# If you're writing a gallery/training consumer, USE `is_trainable(record)` —
# don't roll your own `unit_slug != ""` check, because the sentinels will pass.
SENTINEL_SLUGS: frozenset[str] = frozenset({
    "__bad_crop__",       # detector false positive — crop doesn't contain a mini
    "__unknown__",        # labeller saw the crop but couldn't identify the unit
    "__ambiguous__",      # multiple valid answers (e.g. overlapping minis)
})


def is_sentinel(slug: str) -> bool:
    """True if `slug` is a retired / non-trainable label sentinel."""
    if not slug:
        return False
    if slug in SENTINEL_SLUGS:
        return True
    # Defensive: any `__foo__` pattern is treated as a sentinel even if we
    # haven't explicitly listed it. Future-proofs against new sentinel kinds.
    return slug.startswith("__") and slug.endswith("__") and len(slug) >= 4


def _utc_now_iso() -> str:
    """ISO8601 UTC 'Z' format, seconds precision."""
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── LabelRecord ────────────────────────────────────────────────────────────
@dataclass
class LabelRecord:
    crop_path: str
    source: str
    source_ref: str = ""
    instance_id: str = ""
    view_idx: int | None = None
    faction: str = ""
    unit_slug: str = ""
    suggested_by: str = ""
    confidence: float | None = None
    labeller: str = ""
    split: str = ""
    created_at: str = field(default_factory=_utc_now_iso)
    notes: str = ""

    # ── invariants ──
    def validate(self, *, strict: bool = False) -> list[str]:
        """Return list of validation errors (empty if valid).

        If strict=True, also requires a non-empty faction and a known source."""
        errs: list[str] = []
        if not self.crop_path:
            errs.append("crop_path is empty")
        if self.source and self.source not in VALID_SOURCES:
            errs.append(f"unknown source {self.source!r}")
        if self.split and self.split not in VALID_SPLITS:
            errs.append(f"invalid split {self.split!r}")
        if self.view_idx is not None and self.view_idx < 0:
            errs.append(f"view_idx must be >= 0, got {self.view_idx}")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            errs.append(f"confidence must be in [0,1], got {self.confidence}")
        if strict:
            if not self.faction:
                errs.append("strict: faction is required")
            if self.source not in VALID_SOURCES:
                errs.append(f"strict: source {self.source!r} not in VALID_SOURCES")
        return errs

    # ── CSV roundtrip ──
    def to_csv_row(self) -> dict[str, str]:
        """Serialize to a v2-schema dict suitable for csv.DictWriter."""
        return {
            "crop_path": self.crop_path,
            "source": self.source,
            "source_ref": self.source_ref,
            "instance_id": self.instance_id,
            "view_idx": "" if self.view_idx is None else str(self.view_idx),
            "faction": self.faction,
            "unit_slug": self.unit_slug,
            "suggested_by": self.suggested_by,
            "confidence": "" if self.confidence is None else f"{self.confidence:.4f}",
            "labeller": self.labeller,
            "split": self.split,
            "created_at": self.created_at,
            "notes": self.notes,
        }

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> "LabelRecord":
        """Parse a row tolerantly.

        Accepts both v2 (all columns) and v1 (crop_path, faction, unit_slug,
        notes, source, split). Missing v2 fields default to sensible values.
        """
        def _f(s: str | None) -> float | None:
            if s is None or s == "":
                return None
            try:
                return float(s)
            except ValueError:
                return None

        def _i(s: str | None) -> int | None:
            if s is None or s == "":
                return None
            try:
                return int(s)
            except ValueError:
                return None

        return cls(
            crop_path=(row.get("crop_path") or "").strip(),
            source=(row.get("source") or "").strip(),
            source_ref=(row.get("source_ref") or "").strip(),
            instance_id=(row.get("instance_id") or "").strip(),
            view_idx=_i(row.get("view_idx")),
            faction=(row.get("faction") or "").strip(),
            unit_slug=(row.get("unit_slug") or "").strip(),
            suggested_by=(row.get("suggested_by") or "").strip(),
            confidence=_f(row.get("confidence")),
            labeller=(row.get("labeller") or "").strip(),
            split=(row.get("split") or "").strip(),
            created_at=(row.get("created_at") or "").strip() or _utc_now_iso(),
            notes=(row.get("notes") or "").strip(),
        )

    @classmethod
    def from_v1_row(cls, row: dict[str, str], *, default_source: str = "") -> "LabelRecord":
        """Legacy v1 row: {crop_path, faction, unit_slug, notes, source, split}.

        Explicit migration entry point. If the v1 file lacks `source`, the
        caller must supply `default_source` — source is required in v2.
        """
        return cls(
            crop_path=(row.get("crop_path") or "").strip(),
            source=((row.get("source") or "").strip() or default_source),
            faction=(row.get("faction") or "").strip(),
            unit_slug=(row.get("unit_slug") or "").strip(),
            notes=(row.get("notes") or "").strip(),
            split=(row.get("split") or "").strip(),
        )

    # ── training-data guards ──
    def is_sentinel(self) -> bool:
        """True if this row's `unit_slug` is a retired sentinel (bad crop /
        unknown / ambiguous). Such rows must not be used for training."""
        return is_sentinel(self.unit_slug)

    def is_trainable(self, *, require_split: bool = False) -> bool:
        """True iff this row should be fed to a training/gallery pipeline.
        Requires: a non-empty unit_slug that is NOT a sentinel, and a non-empty
        faction. When `require_split=True`, also requires a non-empty split."""
        if not self.unit_slug:
            return False
        if self.is_sentinel():
            return False
        if not self.faction:
            return False
        if require_split and not self.split:
            return False
        return True


def is_trainable(record: LabelRecord, *, require_split: bool = False) -> bool:
    """Module-level alias so callers can `from ...schema import is_trainable`
    without needing to touch the record first."""
    return record.is_trainable(require_split=require_split)


def filter_trainable(
    records: Iterable[LabelRecord],
    *,
    require_split: bool = False,
) -> Iterator[LabelRecord]:
    """Yield only the subset of `records` that are trainable (no sentinels,
    faction set, unit slug set). The single canonical filter — every gallery
    / training pipeline should use this rather than rolling its own check."""
    for r in records:
        if r.is_trainable(require_split=require_split):
            yield r


# ── file I/O ───────────────────────────────────────────────────────────────
def read_labels_csv(path: str | os.PathLike) -> Iterator[LabelRecord]:
    """Stream LabelRecord rows from a CSV. Tolerates v1 and v2 files.

    Returns a generator; opens the file on first iteration. The caller is
    responsible for consuming it before the file handle is garbage-collected
    (wrap in list(...) if needed)."""
    p = Path(path)
    with p.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield LabelRecord.from_csv_row(row)


def write_labels_csv(
    path: str | os.PathLike,
    records: Iterable[LabelRecord],
    *,
    append: bool = False,
) -> int:
    """Write records to `path` using the v2 column order.

    append=False: atomic write via `.tmp` + rename; overwrites any existing file.
    append=True : appends rows in place without a header rewrite (requires the
                  file already exists with v2 header; we do not create it).

    Returns the number of records written.

    Cross-process lock: every call acquires `<path>.lock` (a directory,
    using atomic `mkdir` as the primitive) for the duration of the write.
    Interop-compatible with the Node backend's `proper-lockfile`, which
    uses the same primitive on the same sidecar path — a Python writer
    blocks a concurrent Node save and vice versa.
    """
    p = Path(path)
    with _CrossProcessMkdirLock(str(p) + ".lock", timeout=30):
        if append:
            if not p.exists():
                raise FileNotFoundError(
                    f"append=True but {p} does not exist. Create it first with append=False."
                )
            n = 0
            with p.open("a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(V2_COLUMNS))
                for rec in records:
                    writer.writerow(rec.to_csv_row())
                    n += 1
            return n

        # Atomic write: .tmp then rename
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        n = 0
        with tmp.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(V2_COLUMNS))
            writer.writeheader()
            for rec in records:
                writer.writerow(rec.to_csv_row())
                n += 1
        tmp.replace(p)
        return n


