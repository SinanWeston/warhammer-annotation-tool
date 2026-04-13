# Phase 2 — scoped retrieval (Tier 1 + Tier 2 + Tier 3)

**Date**: 2026-04-13
**Phase**: 2 (Tier 2 faction classifier + scoped Tier 3)
**Retrieval model**: `facebook/dinov2-base`
**Tier 2 classifier**: KNN-vote on DINOv2 gallery embeddings (k=5)
**Queries**: 13

## Exit criteria

- **Faction top-1 ≥ 90%** (Tier 2 accuracy on the query crops)
- **Unit top-3 ≥ 70%** within-faction (Tier 3 scoped by Tier 2)

- Tier 2 faction top-1: **53.8%** (Wilson lower bound 29.1%) — ❌ MISS
- Scoped unit top-3: **53.8%** (Wilson lower bound 29.1%) — ❌ MISS

## Tier 2 — faction classifier

| Metric | Value |
|---|---|
| Faction top-1 | 53.8% (29.1%–76.8%) |

## Tier 3 retrieval — three variants side-by-side

| Variant | Unit top-1 | Unit top-3 | Unit top-5 | MRR |
|---|---|---|---|---|
| unscoped (Phase 1-style) | 76.9% (49.7%–91.8%) | 84.6% (57.8%–95.7%) | 92.3% (66.7%–98.6%) | 0.840 |
| scoped_actual (production) | 53.8% (29.1%–76.8%) | 53.8% (29.1%–76.8%) | 53.8% (29.1%–76.8%) | 0.538 |
| scoped_oracle (upper bound) | 100.0% (77.2%–100.0%) | 100.0% (77.2%–100.0%) | 100.0% (77.2%–100.0%) | 1.000 |

## Delta vs Phase 1

| Metric | Phase 1 (6q) | Phase 2 unscoped | Phase 2 scoped_actual |
|---|---|---|---|
| Unit top-1 | 66.7% | 76.9% | 53.8% |
| Unit top-3 | 66.7% | 84.6% | 53.8% |
| Unit top-5 | 83.3% | 92.3% | 53.8% |
| MRR | 0.722 | 0.840 | 0.538 |

## Tier 2 ⇒ Tier 3 cascade

| Tier 2 verdict | queries | Tier 3 top-3 |
|---|---|---|
| Tier 2 correct | 7 | 7/7 = 100% |
| Tier 2 wrong | 6 | 0/6 = 0% |

## Per-faction breakdown (scoped_actual)

| Faction | Queries | Top-1 | Top-3 | Top-5 | Tier 2 correct |
|---|---|---|---|---|---|
| chaos_space_marines | 1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) |
| death_guard | 1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) |
| drukhari | 1 | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| eldar | 1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) |
| genestealer_cult | 2 | 1/2 (50%) | 1/2 (50%) | 1/2 (50%) | 1/2 (50%) |
| necrons | 2 | 1/2 (50%) | 1/2 (50%) | 1/2 (50%) | 1/2 (50%) |
| thousand_sons | 2 | 0/2 (0%) | 0/2 (0%) | 0/2 (0%) | 0/2 (0%) |
| tyranids | 3 | 2/3 (67%) | 2/3 (67%) | 2/3 (67%) | 2/3 (67%) |

## Named failure examples

**`scripts/phase2/queries/thousand_sons/exalted_sorcerer/1218019_8fb9b9be817c__00.jpg`** — true `thousand_sons/exalted_sorcerer`, Tier 2 → `chaos_space_marines` (42%), scoped rank: >5
  1. chaos_space_marines/chaos_lord — sim 0.750
  2. chaos_space_marines/dark_angels_company_champion — sim 0.671
  3. chaos_space_marines/legionaries — sim 0.583

**`scripts/phase2/queries/thousand_sons/rubric_marines/13164_2ebfe221cced__01.jpg`** — true `thousand_sons/rubric_marines`, Tier 2 → `chaos_space_marines` (41%), scoped rank: >5
  1. chaos_space_marines/legionaries — sim 1.000
  2. chaos_space_marines/chaos_terminator_squad — sim 0.736
  3. chaos_space_marines/chaos_lord — sim 0.704

**`scripts/phase2/queries/tyranids/tyranid_warriors/122lero_82096eaba983__04.jpg`** — true `tyranids/tyranid_warriors`, Tier 2 → `thousand_sons` (20%), scoped rank: >5
  1. thousand_sons/rubric_marines — sim 0.658
  2. thousand_sons/ahriman — sim 0.569
  3. thousand_sons/exalted_sorcerer — sim 0.504

## Detection (unchanged from Phase 1; re-run only if Tier 1 is swapped)

- OWLv2 detection recall @ IoU 0.5: **83.3%** (vs YOLO baseline 83.3%)
- OWLv2 detection precision @ IoU 0.5: **0.6%** (score threshold 0.1; tune for precision in a follow-up)

## Reproduction

```bash
yolo_env/bin/python3 scripts/phase2/extract_more_crops.py
# fill remaining unit_slug rows via warhammer-analyzer labeller
yolo_env/bin/python3 scripts/phase2/auto_split.py
yolo_env/bin/python3 scripts/phase2/build_gallery.py
yolo_env/bin/python3 scripts/phase2/embed_gallery.py
yolo_env/bin/python3 scripts/phase2/eval_scoped_retrieval.py
yolo_env/bin/python3 scripts/phase2/generate_report.py
```

See [../../STRATEGY.md](../../STRATEGY.md) §7.2 for the phase spec.