# Phase 1 — retrieval pipeline MVP

Prototype of the three-tier architecture laid out in [../../STRATEGY.md](../../STRATEGY.md):

- **Tier 1** — class-agnostic detection via OWLv2 (`google/owlv2-base-patch16-ensemble`)
- **Tier 3** — frozen-embedding unit retrieval via DINOv3 (`facebook/dinov3-vitb16-pretrain-lvd1689m`), k-NN against a reference gallery built from hand-labelled val crops
- No training, no backend wiring, no consumer changes — the point is to answer "does this architecture work?" on our actual data

Plan of record: [~/.claude/plans/eventual-sniffing-diffie.md](../../../../.claude/plans/eventual-sniffing-diffie.md)

## Outputs

Everything below lives under `scripts/phase1/`:

```
crops/{faction}/*.jpg             GT crops from the YOLO val set, pre-mix
labels.csv                         40 rows; unit_slug filled by hand
unit_slugs_cheatsheet.md           valid slugs per faction (from scripts/data/units.json)
crops_index.jsonl                  metadata sidecar for crops/
gallery/{faction}/{unit}/*.jpg     labelled gallery (from build_gallery.py)
queries/{faction}/{unit}/*.jpg     held-out queries
gallery_embeddings.npz             DINOv3 embeddings of gallery
results/retrieval_summary.json     top-1/3/5, MRR, per-query ranks
results/detection_summary.json     OWLv2 vs YOLO detection recall/precision
```

## Reproduction

**One-time setup** (Sinan, ~5 min):

```bash
# Only needed if using gated DINOv3. DINOv2-base fallback kicks in automatically otherwise.
yolo_env/bin/pip install --quiet huggingface-hub[cli]
yolo_env/bin/huggingface-cli login   # paste an HF token that has accepted the DINOv3 licence
```

**Pipeline:**

```bash
# 1. Extract ground-truth crops from the val set (target mix: 15 CSM, 10 DG, 8 GSC, 5 tyr, 2 SM)
yolo_env/bin/python3 scripts/phase1/extract_gt_crops.py

# 2. HAND-LABEL   open scripts/phase1/labels.csv, fill the unit_slug column for all 40 rows
#    Reference scripts/phase1/unit_slugs_cheatsheet.md for valid slugs per faction.
#    ~20 minutes. When in doubt, use a broader slug rather than guessing a variant.

# 3. Split into gallery + query (auto rule: each unit with ≥2 crops → 1 query + rest gallery)
yolo_env/bin/python3 scripts/phase1/auto_split.py

# 4. Materialise gallery/ and queries/ directories
yolo_env/bin/python3 scripts/phase1/build_gallery.py

# 5. Embed gallery with DINOv3 (falls back to DINOv2-base if gate is closed)
yolo_env/bin/python3 scripts/phase1/embed_gallery.py

# 6. Evaluate retrieval
yolo_env/bin/python3 scripts/phase1/eval_retrieval.py

# 7. Evaluate OWLv2 detection on full val set (compare vs Phase 0 YOLO)
yolo_env/bin/python3 scripts/phase1/eval_detection.py
```

## Status

- [x] Day 1 — scaffolding (scripts, crops, seeded labels.csv, cheatsheet)
- [ ] **Hand-labelling** (Sinan, ~20 min)
- [ ] Day 1 — gallery build + embed
- [ ] Day 2 — retrieval eval
- [ ] Day 2 — detection eval
- [ ] Day 3 — report + STRATEGY.md update

## Exit criteria (from the plan)

- Unit top-5 ≥ 50% on the 10-query eval set
- OWLv2 detection recall ≥ 66% (YOLO Phase 0 baseline)
- Failure modes named if either bar is missed (domain gap vs embedding vs detection)

## Anti-patterns to avoid while iterating

- Don't write into `reference_gallery/` — Phase 1 artefacts stay quarantined.
- Don't add new metrics without a reason — mirror Phase 0's schema so numbers compare.
- Don't wire this into the backend yet — that's Phase 2.
- Don't scrape GW — also Phase 2.
- Don't pull in FAISS — numpy cosine sim is fine at N<300.
