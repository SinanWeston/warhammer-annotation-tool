# Phase 2 — scoped retrieval (Tier 1 + Tier 2 + Tier 3)

**Date**: 2026-04-14
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

## Tier 3 retrieval — variants side-by-side

| Variant | Unit top-1 | Unit top-3 | Unit top-5 | MRR |
|---|---|---|---|---|
| unscoped (no Tier 2) | 76.9% (49.7%–91.8%) | **84.6% (57.8%–95.7%)** ✓ | 92.3% (66.7%–98.6%) | 0.840 |
| scoped_actual (always scope) | 53.8% (29.1%–76.8%) | 53.8% (29.1%–76.8%) | 53.8% (29.1%–76.8%) | 0.538 |
| scoped_gated @ conf ≥ 0.5 | 61.5% (35.5%–82.3%) | 69.2% (42.4%–87.3%) | 76.9% (49.7%–91.8%) | 0.686 |
| scoped_oracle (upper bound) | 100.0% (77.2%–100.0%) | 100.0% (77.2%–100.0%) | 100.0% (77.2%–100.0%) | 1.000 |

### Gate threshold sweep

| Threshold | Top-1 | Top-3 | Top-5 | MRR | Queries scoped |
|---|---|---|---|---|---|
| t = 0.3 | 53.8% | 53.8% | 61.5% | 0.558 | 12/13 |
| t = 0.4 | 61.5% | 61.5% | 69.2% | 0.635 | 11/13 |
| t = 0.5 | 61.5% | 69.2% | 76.9% | 0.686 | 8/13 |
| t = 0.6 | 69.2% | 76.9% | 84.6% | 0.763 | 7/13 |
| t = 0.7 | 69.2% | 76.9% | 84.6% | 0.763 | 4/13 |

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

## Headline findings

**Phase 2's retrieval hypothesis is confirmed. Its Tier 2 scoping approach is falsified — even with confidence gating.**

1. **Unscoped retrieval top-3 = 84.6%** (Wilson 57.8–95.7% on 13 queries) — clears the 70% Phase 2 exit bar at point estimate. MRR climbed from Phase 1's 0.72 to 0.84. A bigger, deeper gallery alone lifted every metric by 8–18 pp vs Phase 1.

2. **KNN-vote Tier 2 = 53.8% faction top-1.** Far below the 90% exit bar. When it's right (7/13), scoped retrieval is perfect (100% top-3). When it's wrong (6/13), scoped retrieval is 0% by construction — the correct unit is excluded from the search slice. `scoped_actual` flatlines at exactly the Tier 2 accuracy.

3. **Confidence gating doesn't rescue scoping.** Swept gate thresholds 0.3–0.7; the best (0.6–0.7) hits top-3 = 76.9%, still below unscoped's 84.6%. Tier 2's confidence signal isn't reliable enough — confidently-wrong predictions still drag scoped numbers down. Gating recovers some damage but never wins.

4. **Scoped oracle = 100%.** Within-faction discrimination is fully solved at this gallery size. The cross-faction confusions Phase 1 flagged (aberrants vs deathshroud_terminators) resolved purely by gallery depth — no architectural change needed.

5. **Thousand Sons is the canonical failure mode.** Both TS queries got classified as `chaos_space_marines` by Tier 2; crops look visually very similar in armour/silhouette. Unscoped retrieval nailed both (matching across factions by embedding only).

## What this means for STRATEGY.md

- **Ship unscoped retrieval as the production path.** No Tier 2 needed for the MVP. k-NN over 79 items is sub-millisecond; scoping is a latency optimisation, not a correctness pass.
- **Tier 2 as KNN-vote is a dead end** at this gallery size. Confidence gating confirmed.
- **If Tier 2 scoping is ever re-attempted**, the viable paths are: (a) linear probe on DINOv2 embeddings with gallery faction labels (~30 LOC, likely 80%+ faction top-1), (b) a dedicated YOLO retrained specifically on crops (not scene-context full images — Phase 0/2 showed the crop-vs-scene distribution mismatch breaks YOLO).
- **Gallery depth is the highest-leverage investment.** Biggest single lift between Phase 1 and Phase 2 came from 2× crops per unit. This predicts Phase 3's synthetic-data expansion will continue to move the needle.

## Caveats

- **13 queries is still small.** Wilson 95% CIs on headline numbers are ±20 pp. Treat direction as strong; treat exact percentages as soft.
- **Unit top-3 unscoped Wilson lower bound is 57.8%** — below the 70% threshold. On this sample the *point estimate* passes; the *confidence interval* straddles it. A 30-query rerun (hand-label more crops) would pin it down.
- **Detection precision was not re-measured.** OWLv2 at score threshold 0.1 stays at 0.6%. Threshold tuning remains a separate follow-up.

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