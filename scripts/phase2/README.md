# Phase 2 — Tier 2 faction classifier + gallery expansion

Follow-up to Phase 1 per [../../STRATEGY.md](../../STRATEGY.md) §7.2. Phase 1 passed on 6 queries; Phase 2 proves the approach at scale with **scoped retrieval** and a bigger, deeper gallery.

## Exit criteria (from STRATEGY.md)

- **Faction top-1 ≥ 90%** on ≥ 30 queries.
- **Unit top-3 ≥ 70%** on ≥ 30 queries, measured *within-faction* (Tier 3 scoped by Tier 2's faction pick).

## The three changes from Phase 1

1. **Gallery depth.** Phase 1's 24-image gallery had most units at 1-2 examples. The one hard failure (termagants rank 12) was a thin-gallery case. Target for Phase 2: ≥ 3 images per unit that appears in any query set.
2. **Tier 2 faction classifier.** Insert YOLO11x Run 2 as a faction-only classifier before Tier 3. Tier 3 retrieval then searches only within the predicted faction's gallery slice. This should cleanly fix the Phase 1 aberrants-vs-deathshroud_terminators cross-faction confusion.
3. **≥ 30 queries.** Phase 1's 6 queries had ±30 pp CIs on every headline number. Phase 2 eval set is big enough that a 10 pp effect is detectable.

## What to reuse from Phase 1

All of it. `scripts/phase1/labels.csv` is the seed. The `warhammer-analyzer` labelling tool points at `scripts/phase2/crops/` after you update `LABELLING_CROPS_DIR` + `LABELLING_LABELS_CSV`.

## Workflow (for you to execute)

```bash
# 1. Extract ~80 more crops from the val set, biased toward depth-per-unit
yolo_env/bin/python3 scripts/phase2/extract_more_crops.py
#    Produces scripts/phase2/crops/{faction}/*.jpg + scripts/phase2/labels.csv
#    (seeded with Phase 1 labels + new unlabelled rows)

# 2. Switch the labeller to point at phase2
#    In warhammer-analyzer/.env add:
#      LABELLING_CROPS_DIR=../scripts/phase2/crops
#      LABELLING_LABELS_CSV=../scripts/phase2/labels.csv
#      LABELLING_CHEATSHEET=../scripts/phase2/unit_slugs_cheatsheet.md
#    Or export before starting:
#      cd warhammer-analyzer
#      LABELLING_CROPS_DIR=../scripts/phase2/crops \
#      LABELLING_LABELS_CSV=../scripts/phase2/labels.csv \
#      LABELLING_CHEATSHEET=../scripts/phase2/unit_slugs_cheatsheet.md \
#      node backend/src/index.js

# 3. Hand-label the new rows at http://localhost:3003/label
#    ~30 min with AI assistance.

# 4. Split + build + embed
yolo_env/bin/python3 scripts/phase2/auto_split.py
yolo_env/bin/python3 scripts/phase2/build_gallery.py
yolo_env/bin/python3 scripts/phase2/embed_gallery.py

# 5. Evaluate (scoped + unscoped, side-by-side)
yolo_env/bin/python3 scripts/phase2/eval_scoped_retrieval.py

# 6. Generate the report
yolo_env/bin/python3 scripts/phase2/generate_report.py
#    Writes docs/benchmarks/YYYY-MM-DD-phase2-scoped.md
```

## Files in this directory

```
extract_more_crops.py      # adds new crops, seeds labels.csv from Phase 1
auto_split.py              # fork of phase1 auto_split targeting phase2/
build_gallery.py           # fork of phase1 build_gallery targeting phase2/
embed_gallery.py           # fork of phase1 embed_gallery targeting phase2/
classify_faction_knn.py    # Tier 2 — KNN-vote on gallery embeddings
classify_faction_yolo.py   # (DEPRECATED for crops — see file for why)
eval_scoped_retrieval.py   # Tier 2 + Tier 3 pipeline eval
generate_report.py         # Phase 2 markdown report with Tier 2 metrics
```

## Target extraction mix (what `extract_more_crops.py` pulls)

Goal: bring every unit that survived Phase 1 to ≥ 3 gallery examples, then add breadth.

| Faction | Phase 1 units | Target units | New crops wanted |
|---|---|---|---|
| chaos_space_marines | 5 (chaos_bikers, chaos_lord, legionaries ×2, rubric_marines ×0, plague_marines ×0) | 5 | +10 |
| death_guard | 3 (plague_marines ×5, lord_of_contagion ×1, deathshroud_terminators ×1) | 4 | +10 |
| thousand_sons | 1 (rubric_marines ×2) | 1 | +3 |
| genestealer_cult | 4 (aberrants ×2, neophyte_hybrids ×3, achilles_ridgerunner ×1, genestealers ×1) | 5 | +15 |
| space_marines | 2 (captain ×1, sanguinary_guard ×1) | 4 | +15 |
| tyranids | 4 (termagants ×2, genestealers ×1, ripper_swarms ×1, tyranid_warriors ×1) | 5 | +20 |
| necrons | 0 | 3 | +10 |
| eldar | 0 | 3 | +10 |
| **total** | 19 | ~30 | **~80** |

Plus whatever Phase 1 already labelled — that gets pulled in by `extract_more_crops.py` so the user doesn't re-label anything.

## What "scoped retrieval" means, concretely

Before (Phase 1): embed query, cosine-sim against ALL gallery items, take top-K.

After (Phase 2):
```
crop
  │
  ▼
DINOv2 embedding (same as Tier 3)
  │
  ├──► Tier 2: top-K gallery neighbours, weighted faction vote → predicted faction
  │
  ▼
Tier 3: cosine sim restricted to gallery[faction == predicted], top-K
```

**Why KNN-vote, not YOLO, for Tier 2.** We initially planned to use the trained YOLO11x Run 2 as the faction classifier. Empirically, YOLO was trained on full tabletop photographs with scene context; on tight single-miniature crops its confidence collapses (0.01–0.17 on test crops, often wrong class). KNN-voting on the same embeddings Tier 3 uses has no distribution mismatch, no extra model load, and every query produces a faction prediction and a unit ranking from one inference. If Tier 2 gets the faction wrong, Tier 3 searches the wrong slice — the eval reports that failure mode explicitly.

The *best* reporting splits it three ways:

- `unscoped`: Phase 1-style eval, for direct comparison
- `scoped_oracle`: Tier 3 scoped by the *true* faction (upper bound)
- `scoped_actual`: Tier 3 scoped by Tier 2's prediction (real-world result)

The `eval_scoped_retrieval.py` script emits all three.

## Not doing in Phase 2

- GW product-page scraping (was Phase 2 in STRATEGY.md; deferred because hand-labelling existing val crops is fast and in-domain, per Phase 1 findings)
- DINOv3 upgrade (DINOv2-base passed Phase 1; HF gate step still pending on user side)
- Linear probe on DINOv2 (alternative to YOLO for Tier 2 — might revisit if YOLO faction accuracy caps below 90%)
- Synthetic data via BlenderProc (Phase 3)
