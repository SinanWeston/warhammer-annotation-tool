# 2026-06-06 · Tier 3 retrieval — Death Guard gallery validated

After seeding the Death Guard gallery from already-on-disk data (0 → 189 crops /
29 units; gw_shop studio + CMON painted — see `seed_dg_gallery.py`), this validates
that it actually retrieves. Method: leave-one-out over the gallery, cosine k-NN on
frozen DINOv2-large embeddings, scoped per faction (Tier 2 picks faction → Tier 3
retrieves within it). Repro: `scripts/phase3/eval_gallery_retrieval.py`.

## Result — DG is now the BEST-retrieving v1 faction

| Faction | gallery units | scoped top-1 | scoped top-3 | ≥0.80 bar |
|---|---|---|---|---|
| **Death Guard** (built today) | 29 | 0.763 | **0.887** | ✅ |
| Necrons | 59 | 0.792 | 0.847 | ✅ |
| Tyranids | 53 | 0.759 | 0.827 | ✅ |
| Space Marines | 125 | 0.614 | **0.697** | ⚠️ |

Death Guard — the project's headline gap that morning — clears the 80% Tier 3 exit
bar at **88.7% scoped top-3**, ahead of the three established factions. Built
entirely by ingesting data already on disk (no scraping). DG retrieval is solved at
this depth.

DG unscoped (query vs the full 19.6k gallery): top-1 0.661 / top-3 0.729, faction
top-1 = 0.763. The scoped→unscoped drop is cross-faction confusion (DG vs other
Chaos), which is exactly what Tier 2 faction-scoping removes — motivating the scoped
production path.

DG failure modes: the generic `plague_marines` catch-all and `dg_combat_patrol`
(multi-model box shots). Named characters (Typhus, Deathshroud, Mortarion) retrieve
cleanly.

## The real Tier 3 weak link: Space Marines (0.697, below bar)

SM is now the worst v1 faction — 125 units of visually-similar power-armoured
marines, compounded by the SM gallery being 100% `dup`-tagged (homogeneous source;
also surfaced in the 2026-06-05 Tier 2 probe, SM faction top-1 0.47). SM gallery
**diversity** is the next Tier 3 lever, not DG.

## Implications
- Death Guard is no longer a blocker — gallery seeded + validated.
- A supervised CMON top-up for DG is **not** needed at current depth (89% top-3).
- Next Tier 3 work is SM gallery diversification, then wiring the full
  detect→Tier2→Tier3 path on real photos.
