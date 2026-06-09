# 2026-06-09 · Tier 3 retrieval — gold-domain queries (the honest number)

The 2026-06-06 Tier 3 numbers were **leave-one-out over the gallery itself** —
catalog-style crops retrieved against a catalog that deliberately retains
near-duplicates. That measures gallery self-consistency, not the deployment task.
This bench measures the deployment task: real-scene crops → current gallery.
Repro: `scripts/phase3/eval_gold_domain_retrieval.py`; raw JSON alongside this file.

## Method
- **Queries:** the 102 `source=annotation` v1 rows of `data/labels.csv` — crops cut
  from the hand-annotated scene corpus (tabletop/forum photos, same domain as gold)
  with **human unit labels**. The original crop JPEGs were deleted in the 2026-06-05
  cleanup, so crops are regenerated from the annotation JSONs (box index from the
  crop filename, 5% pad — the deleted `extract_gt_crops.py` recipe).
- **Gallery:** the current FiftyOne `pool=gallery` (19,765 embedded crops,
  `weak_unit` labels), i.e. exactly what production Tier 3 would search.
- **Scoring:** scoped cosine k-NN (GT faction given — the production path),
  DINOv2-large CLS, L2-normalized, same recipe as the gallery embeddings. Top-3 over
  *distinct* units. Only queries whose unit exists in their faction's gallery are
  scored (79/102 covered; 23 uncovered — gallery depth gaps, listed in the JSON).
- **Leakage screen:** 0/79 queries had max gallery cosine ≥ 0.97 — the result is not
  near-dup inflated.

## Result — the LOO bench overstated 3 of 4 factions by 25–60 points

| Faction | n | gold-domain top-1 | **gold-domain top-3** | LOO top-3 (06-06) | ≥0.80 bar |
|---|---|---|---|---|---|
| death_guard | 29 | 0.724 | **0.931** | 0.887 | ✅ |
| necrons | 11 | 0.364 | **0.455** | 0.847 | ❌ |
| tyranids | 29 | 0.069 | **0.241** | 0.827 | ❌ |
| space_marines | 10 | 0.200 | **0.200** | 0.697 | ❌ |
| **v1 overall** | **79** | **0.367** | **0.519** | — | ❌ |

## Reading — the architecture works; three galleries don't
**Death Guard is the control group.** Its gallery is the only *curated* one (built
2026-06-06 from gw_shop product pages + CMON, unit labels from product names) — and
it retrieves real tabletop crops at 93%, *above* its own LOO score. Frozen DINOv2
embeddings are sufficient when the gallery is clean. The central architectural bet
survives its first deployment-domain test.

The other three galleries are isolation-corpus crops with **unverified `weak_unit`
folder-name labels** (the long-standing "gallery label QA" TODO) and heavy
homogeneity (SM 100% dup-tagged). Their LOO scores were self-retrieval among
near-identical catalog twins; against real crops they collapse. Failure is
concentrated: termagants alone are 13 of 29 tyranid misses (tiny swarm models),
immortals 5 of the necron misses.

## Caveats
- n is thin for SM (10) and necrons (11) — wide CIs; the *direction* is unambiguous
  (tyranids n=29 at 0.241), the exact numbers aren't.
- Crop regeneration assumes annotation-JSON box order is unchanged since labels.csv
  was written (2026-04-18; some JSONs touched 2026-04-19). DG's 0.93 argues the
  crops are largely correct — scrambled indices would have hurt it too.
- Queries come from the legacy annotation corpus; their *unit* labels were assigned
  by hand in Phase 1 and are trusted here.

## Implications
1. **This bench, not LOO, is the Tier 3 exit-bar measurement** (bar: top-3 ≥ 0.80
   within-faction). Current honest standing: 1/4 factions pass.
2. **Re-prioritize: gallery label QA + curation beats gallery depth.** DG (189
   curated crops) beats SM (2,914 weak-labeled crops) by 73 points. Replicating the
   DG recipe (product-page-labeled gw_shop/CMON crops) for SM/Tyranids/Necrons is
   the highest-leverage Tier 3 work — before any backbone upgrade.
3. The 23 uncovered queries list real gallery depth gaps (tyranid_warriors,
   DG characters, SM named characters).
