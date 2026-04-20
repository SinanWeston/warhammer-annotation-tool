"""Freeze the Phase C 200-image evaluation set.

Samples 200 annotated images from backend/training_data_annotations/
stratified by bbox density (single / sparse / medium / crowded), then
by source within each bucket. Deterministic via a fixed seed so re-runs
produce the same list. Once committed, the resulting manifest must
never overlap with training data — every future model change is scored
against this set. See STRATEGY.md §3.1 step 1 and Phase C in the status
table.

Usage:
    yolo_env/bin/python scripts/phaseC/freeze_eval_set.py

Outputs:
    data/scene_benchmark/eval_200.json  (the frozen manifest)
    data/scene_benchmark/README.md       (no-touch warning + summary)
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

SEED = 42
ANN_DIR = Path("backend/training_data_annotations")
OUT_DIR = Path("data/scene_benchmark")
MANIFEST_PATH = OUT_DIR / "eval_200.json"
README_PATH = OUT_DIR / "README.md"

# Density buckets, in priority order. Counts chosen so crowded (the
# Dakka-Dakka tier where product quality is judged) is over-represented
# vs its corpus share — only 78 crowded images exist and 40 is ~half.
BUCKET_TARGETS = {
    "single": 60,    # 1 bbox  — eBay / single-mini product shot tier
    "sparse": 50,    # 2-3 bboxes — typical hobby / painter shots
    "medium": 50,    # 4-9 bboxes — small skirmish
    "crowded": 40,   # 10+ bboxes — full tabletop, the stress tier
}
assert sum(BUCKET_TARGETS.values()) == 200


def bucket_for(n_boxes: int) -> str | None:
    if n_boxes == 0:
        return None  # skip annotator-flagged "no minis here" entries
    if n_boxes == 1:
        return "single"
    if n_boxes <= 3:
        return "sparse"
    if n_boxes <= 9:
        return "medium"
    return "crowded"


def load_candidates() -> list[dict]:
    """Read every annotation JSON and return a flat list with the
    fields needed for sampling. Drops 0-box entries and entries with
    missing source (handful from pre-v2 migrations)."""
    rows = []
    for path in sorted(ANN_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except Exception as e:
            print(f"  skip {path.name}: {e}")
            continue
        n = len(data.get("annotations") or [])
        bucket = bucket_for(n)
        if bucket is None:
            continue
        src = data.get("source")
        if not src:
            continue
        rows.append({
            "imageId": data["imageId"],
            "imagePath": data.get("imagePath"),
            "faction": data.get("faction"),
            "source": src,
            "bucket": bucket,
            "n_boxes": n,
            "width": data.get("width"),
            "height": data.get("height"),
        })
    return rows


def stratified_sample(candidates: list[dict]) -> list[dict]:
    """For each density bucket, sample BUCKET_TARGETS[bucket] images,
    trying to keep source proportions balanced within the bucket. If a
    bucket has fewer candidates than its target, take all of them (and
    surface the shortfall in the summary)."""
    rng = random.Random(SEED)
    by_bucket: dict[str, list[dict]] = defaultdict(list)
    for r in candidates:
        by_bucket[r["bucket"]].append(r)

    picked: list[dict] = []
    shortfalls: dict[str, int] = {}

    for bucket, target in BUCKET_TARGETS.items():
        pool = by_bucket[bucket]
        if len(pool) <= target:
            picked.extend(pool)
            if len(pool) < target:
                shortfalls[bucket] = target - len(pool)
            continue
        # Proportional allocation per source, rounded down, plus
        # remainder sampled at random to hit the target exactly.
        by_src: dict[str, list[dict]] = defaultdict(list)
        for r in pool:
            by_src[r["source"]].append(r)
        total = len(pool)
        alloc: dict[str, int] = {}
        for src, items in by_src.items():
            alloc[src] = (len(items) * target) // total
        remainder = target - sum(alloc.values())
        # Distribute remainder across sources with spare capacity.
        spare_srcs = [s for s, items in by_src.items() if alloc[s] < len(items)]
        rng.shuffle(spare_srcs)
        for s in spare_srcs[:remainder]:
            alloc[s] += 1

        for src, items in by_src.items():
            rng.shuffle(items)
            picked.extend(items[: alloc[src]])

    if shortfalls:
        for b, n in shortfalls.items():
            print(f"  shortfall: {b} bucket is {n} short of target")

    return picked


def summarise(picked: list[dict]) -> str:
    by_bucket = Counter(r["bucket"] for r in picked)
    by_source = Counter(r["source"] for r in picked)
    by_faction = Counter(r["faction"] for r in picked)
    by_bucket_source: dict[str, Counter] = defaultdict(Counter)
    for r in picked:
        by_bucket_source[r["bucket"]][r["source"]] += 1

    lines = [f"Total: {len(picked)}  (seed={SEED})", "", "By bucket:"]
    for b in BUCKET_TARGETS:
        lines.append(f"  {b:<8} {by_bucket.get(b, 0):>3}  (target {BUCKET_TARGETS[b]})")
    lines.append("")
    lines.append("By source:")
    for s, c in by_source.most_common():
        lines.append(f"  {s:<12} {c:>3}")
    lines.append("")
    lines.append("Bucket × source:")
    for b in BUCKET_TARGETS:
        parts = ", ".join(f"{s}={c}" for s, c in by_bucket_source[b].most_common())
        lines.append(f"  {b:<8} {parts}")
    lines.append("")
    lines.append(f"Factions covered: {len(by_faction)}")
    top = ", ".join(f"{f}={c}" for f, c in by_faction.most_common(5))
    lines.append(f"Top 5: {top}")
    return "\n".join(lines)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    candidates = load_candidates()
    print(f"Loaded {len(candidates)} usable annotations")
    picked = stratified_sample(candidates)
    # Stable output order: by bucket (in BUCKET_TARGETS order), then imageId.
    bucket_order = {b: i for i, b in enumerate(BUCKET_TARGETS)}
    picked.sort(key=lambda r: (bucket_order[r["bucket"]], r["imageId"]))

    manifest = {
        "version": 1,
        "seed": SEED,
        "bucket_targets": BUCKET_TARGETS,
        "frozen_at": "2026-04-20",
        "source_annotation_dir": str(ANN_DIR),
        "n": len(picked),
        "images": picked,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=False))
    print(f"\nWrote {MANIFEST_PATH}")

    summary = summarise(picked)
    print()
    print(summary)

    README_PATH.write_text(
        "# Phase C — Frozen scene benchmark\n\n"
        "**Do not train on these images.** Every model evaluation "
        "(detection mAP, faction top-1, unit top-3) is scored against "
        "this set. If you retrain and these image IDs end up in the "
        "training split, every downstream number is meaningless.\n\n"
        "The manifest (`eval_200.json`) is the source of truth — pin "
        "against its `imageId` list, not filesystem globs.\n\n"
        "See `STRATEGY.md` §3.1 step 1 and the Phase C row in the "
        "Status table for context.\n\n"
        "## Generated summary\n\n```\n" + summary + "\n```\n\n"
        "## Regenerating\n\nRerun `yolo_env/bin/python "
        "scripts/phaseC/freeze_eval_set.py`. Output is deterministic "
        "(seed=42) — re-running will not change the list unless the "
        "underlying annotation corpus gains or loses images in the "
        "sampled buckets. If that happens intentionally (e.g., new "
        "crowded images annotated), bump the `version` field and "
        "publish a migration note.\n"
    )
    print(f"\nWrote {README_PATH}")


if __name__ == "__main__":
    main()
