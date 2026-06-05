#!/usr/bin/env python3
"""Apply weak supervision to data/labels.csv and report coverage.

For every row whose `unit_slug` is empty, run:
  1. Title classifier (regex + character table)   → (faction, unit_slug)
  2. Cross-check with detector faction (from notes) → flag conflicts
  3. Pre-populate label fields with `suggested_by=weak_regex:{source}`

The row is NOT marked as human-confirmed (`labeller` stays empty). Humans
still pass through the label UI to confirm or correct.

Flags:
    --dry-run        Don't write; just print stats
    --source cmon    Only apply to rows matching this source (default: all)
    --overwrite      Apply even to rows that already have a suggested_by value
                     (lets us rerun after tweaking rules). Rows with trusted
                     provenance (`human`, `human_redraw`, `scraped`,
                     `annotation`) or any non-empty `labeller` are ALWAYS
                     skipped — the guard runs regardless of --overwrite.

Usage:
    fiftyone_env/bin/python3 scripts/apply_weak_sup.py --source cmon --dry-run
    fiftyone_env/bin/python3 scripts/apply_weak_sup.py --source cmon
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "src"))

from photoanalyzer.label.schema import (  # noqa: E402
    LabelRecord, read_labels_csv, write_labels_csv,
)
from photoanalyzer.label.weak import (  # noqa: E402
    classify_title, combine_with_detector, parse_detector_signal,
)


_TITLE_IN_NOTES_RE = re.compile(r"title:\s*'([^']*)'")


def extract_title_from_notes(notes: str) -> str:
    """Pull the `title: '...'` clause out of the notes field written by
    extract_cmon_crops.py. Returns empty string if absent."""
    m = _TITLE_IN_NOTES_RE.search(notes or "")
    return m.group(1) if m else ""


#: Provenance tags that identify rows we will NEVER let weak-sup rewrite,
#: even under --overwrite. `human` / `human_redraw` = user confirmed the
#: label via the UI. `scraped` = pulled from a canonical GW shop page.
#: `annotation` = carried over from the desktop annotator's human corpus.
#: Losing the provenance tag on any of these would silently pollute a
#: future provenance filter.
TRUSTED_PROVENANCE = frozenset({"human", "human_redraw", "scraped", "annotation"})


def apply_to_rows(
    rows: list[LabelRecord],
    *,
    source_filter: str | None,
    overwrite: bool,
) -> tuple[list[LabelRecord], Counter]:
    stats: Counter = Counter()
    out: list[LabelRecord] = []
    for row in rows:
        out.append(row)  # we mutate in-place; the list returned is same order
        if source_filter and row.source != source_filter:
            stats["skipped_wrong_source"] += 1
            continue
        # Trusted-provenance guard: runs BEFORE the --overwrite short-circuits
        # below. Without this, `--overwrite` would rewrite `suggested_by` at
        # line ~98 and clear `labeller` at line ~103, wiping the human/scraped/
        # annotation provenance tag. The label values themselves (faction,
        # unit_slug) are already protected by the `if not row.faction:` /
        # `if not row.unit_slug:` guards further down, but the provenance
        # signal is not — this guard is the belt to those suspenders.
        if row.suggested_by in TRUSTED_PROVENANCE or row.labeller:
            stats["skipped_trusted_provenance"] += 1
            continue
        if row.unit_slug and not overwrite:
            stats["skipped_already_labelled"] += 1
            continue
        if row.suggested_by and not overwrite:
            stats["skipped_already_suggested"] += 1
            continue

        title = extract_title_from_notes(row.notes)
        det_faction, det_conf = parse_detector_signal(row.notes)

        title_label = classify_title(title) if title else None
        combined = combine_with_detector(title_label, det_faction, det_conf)

        if combined is None:
            stats["no_signal"] += 1
            continue

        # Apply to row. Don't overwrite pre-existing non-empty faction/unit.
        if not row.faction:
            row.faction = combined.faction
        if not row.unit_slug:
            row.unit_slug = combined.unit_slug
        row.suggested_by = f"weak_regex:{combined.source}"
        row.confidence = combined.confidence
        if combined.flag:
            # Append conflict flag to notes so the UI can surface it.
            row.notes = (row.notes + f"; flag:{combined.flag}").strip("; ")
        row.labeller = ""  # still unconfirmed

        # Tally by outcome
        stats["applied"] += 1
        stats[f"source={combined.source}"] += 1
        if combined.flag == "title_detector_conflict":
            stats["conflicts"] += 1
        if combined.unit_slug:
            stats["applied_with_unit"] += 1
        else:
            stats["applied_faction_only"] += 1

    return out, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", type=Path,
                    default=REPO / "data" / "labels.csv")
    ap.add_argument("--source", default="cmon",
                    help="Only apply to rows with this source (default: cmon)")
    ap.add_argument("--all-sources", action="store_true",
                    help="Apply to all sources, not just --source")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--overwrite", action="store_true",
                    help="Re-suggest rows that already had weak-sup or LLM labels")
    ap.add_argument("--report-title-misses", type=int, default=20,
                    help="Print N sample titles where weak-sup found nothing")
    args = ap.parse_args()

    source_filter = None if args.all_sources else args.source
    print(f"▶ apply weak-sup: source={source_filter or 'all'}  "
          f"overwrite={args.overwrite}  dry_run={args.dry_run}",
          flush=True)

    rows = list(read_labels_csv(args.labels))
    print(f"  loaded {len(rows)} rows")
    before_labelled = sum(1 for r in rows if r.unit_slug)
    print(f"  already labelled (unit_slug != ''): {before_labelled}")

    # Keep a record of miss-titles BEFORE applying (so we can print samples)
    title_misses: list[str] = []
    for r in rows:
        if source_filter and r.source != source_filter:
            continue
        if r.unit_slug:
            continue
        title = extract_title_from_notes(r.notes)
        if title and classify_title(title) is None:
            title_misses.append(title)

    updated, stats = apply_to_rows(rows,
                                   source_filter=source_filter,
                                   overwrite=args.overwrite)

    print("\n=== stats ===")
    for k in sorted(stats):
        print(f"  {k:32s} {stats[k]}")

    after_labelled = sum(1 for r in updated if r.unit_slug)
    after_suggested = sum(1 for r in updated if r.suggested_by)
    print(f"\n  labelled rows after: {after_labelled} (was {before_labelled})")
    print(f"  suggested rows after: {after_suggested}")

    if title_misses:
        sample = title_misses[: args.report_title_misses]
        print(f"\n=== sample titles that matched NO rule ({len(title_misses)} total) ===")
        for t in sample:
            print(f"  {t!r}")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return

    n = write_labels_csv(args.labels, updated)
    print(f"\n✅ wrote {n} rows to {args.labels}")


if __name__ == "__main__":
    main()
