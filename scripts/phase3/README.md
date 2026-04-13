# Phase 3a — Gallery expansion from existing annotation corpus

Grows the retrieval gallery beyond Phase 2 by extracting crops from the **full** annotation corpus (`backend/training_data_annotations/`, 899 images / 3,525 bboxes) instead of just the val split. Covers 14 factions that had zero Phase 2 coverage.

See [../../STRATEGY.md](../../STRATEGY.md) §7 for phase context. Phase 3a was not in the original STRATEGY.md roadmap — it was added when a fresh data audit revealed 97% of the corpus was unused. Phase 3b (synthetic data, the original "Phase 3") runs only if 3a's gallery expansion can't close remaining coverage gaps.

## What's already done

```
scripts/phase3/crops/{faction}/*.jpg    400 crops on disk
scripts/phase3/labels.csv               407 rows (91 pre-labelled from Phase 2, 316 empty)
scripts/phase3/crops_index.jsonl        metadata + post-export flag per crop
scripts/phase3/unit_slugs_cheatsheet.md 24-faction slug reference
```

**Distribution**: every Phase 2 faction + all 14 uncovered ones. Biased toward post-YOLO-export images (never seen by the current YOLO model) for the new factions, so they function as a pristine eval set.

## Exit criteria

- Gallery ≥ 300 crops across ≥ 18 factions, ≥ 3 depth per query unit
- Eval ≥ 30 queries (up from Phase 2's 13)
- Unscoped unit top-3 ≥ 80% **with Wilson lower bound ≥ 70%** (tight CIs at last)
- Per-faction top-3 breakdown across the 14 previously-uncovered factions

## Workflow (for you)

### 1. Re-point the labeller at phase3

```bash
pkill -f "node backend/src/index.js"; pkill -f "node server.js"
cd warhammer-analyzer
LABELLING_CROPS_DIR=../scripts/phase3/crops \
LABELLING_LABELS_CSV=../scripts/phase3/labels.csv \
LABELLING_CHEATSHEET=../scripts/phase3/unit_slugs_cheatsheet.md \
node backend/src/index.js &
node server.js &
```

Open http://localhost:3003/label. Your 91 Phase 2 labels are already marked labelled and carried over. You'll land on the first of **316 unlabelled** crops.

### 2. Label (budget ~3–4 hours for the Big scope)

Same rules as before:
- **Broader over specific** when unsure (`intercessors` > `heavy_intercessors`)
- Aim for **2–4 crops per unit** within each faction (so auto_split produces queries)
- For crops you can't ID → right-click → "Search image with Google Lens" → read → type

You don't need to label all 316 — anywhere from 150 upward gets us to the Phase 3a exit criteria. Stop whenever the coverage feels right or you run out of patience.

### 3. Run the pipeline

```bash
yolo_env/bin/python3 scripts/phase3/auto_split.py
yolo_env/bin/python3 scripts/phase3/build_gallery.py
yolo_env/bin/python3 scripts/phase3/embed_gallery.py
yolo_env/bin/python3 scripts/phase3/eval_scoped_retrieval.py
yolo_env/bin/python3 scripts/phase3/generate_report.py
```

Produces `docs/benchmarks/YYYY-MM-DD-phase3a-corpus-expansion.md`.

## Files

Forked from phase2/ with `scripts/phase3/` paths; `classify_faction_knn.py` stays for symmetry even though unscoped retrieval is the production path.

```
extract_from_corpus.py        (NEW) walks full annotation corpus
auto_split.py                 fork of phase2
build_gallery.py              fork of phase2
embed_gallery.py              fork of phase2
eval_scoped_retrieval.py      fork of phase2
generate_report.py            fork of phase2
classify_faction_knn.py       fork of phase2 (Tier 2 — dormant, present for future linear-probe work)
unit_slugs_cheatsheet.md      24-faction slug reference
```

## Why not synthetic data first?

Was the original STRATEGY.md Phase 3. Deferred because the annotation audit showed we had 3,525 already-labelled bboxes and were using 80. Synthetic data makes sense for the **long tail** (Forgeworld, discontinued sculpts, rare characters). For faction-level breadth, the existing corpus is cheaper, lower-risk, and in-domain.

Phase 3b (synthetic) will run after 3a gives us concrete data on which units/factions STILL have gaps.
