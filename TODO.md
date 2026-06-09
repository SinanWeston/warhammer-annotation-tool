# TODO — Battle Scanner

Live project to-do for the **data-centric rebuild** (detect → faction → retrieve →
optional VLM). Supersedes the pre-rebuild "app audit" TODO. Authoritative state:
`HANDOFF.md`; rationale: `STRATEGY.md`; execution plan: `BATTLE_SCANNER_PLAN.md`.

Legend: ✅ done · 🔄 in-flight · ⬜ todo · ⚠️ decision/blocker

---

## ✅ Foundation (done)
- ✅ Curate the pile — 66.4k images (60.9k DINOv2-embedded; warhammer_community +
  roboflow still un-embedded), deduped, role-split (gallery /
  detection / holdout), provenance-stamped, v1 factions locked (SM / Necrons /
  Tyranids / Death Guard)
- ✅ **Gold eval set** — `data/gold/gold_v2.json`, 89 imgs / 283 boxes, every v1
  faction ≥40. The trusted measuring stick.
- ✅ **Tier 1 measuring infra** — `eval/gold.py` (count-MAE × density + per-faction
  recall), `eval/boxconv.py` (box-convention reconciliation), `eval/triage.py`
  (post-SAM3 bucketing), `scripts/phaseF/score_gold.py`. 157 tests.
- ✅ **Junk filter** — `lowq` (1,463) + `junk_clip` (1,772) → 30.6k clean SAM 3 input
  (`data/phaseF/autolabel_images.txt`).
- ✅ Dataset hunt (no shortcut dataset exists — see `docs/research/`), Tier 2 probe +
  gallery audit (`docs/benchmarks/2026-06-05-tier2-probe-gallery-audit.md`).

## 🔄 Now
- 🔄 Label the **gold density round** (`wh40k_gold_v6`, 26 crowded scenes) → `pull v6`
  + `merge` so the crowded bucket (currently 5 imgs) can support the count metric.
- ⬜ **Add SM gold images** (currently only **7 images** / 55 boxes — too thin to judge
  the weakest faction; target ≥25 imgs) — fold into the v6 CVAT round or a v7.
- ⚠️ **GATE (2026-06-09 review):** do NOT run the SAM 3 prompt/threshold sweep until
  v6 is merged — its selection criterion is *crowded-bucket recall*, currently
  measured on 5 images (i.e. selecting hyperparameters on noise).
- ⚠️ Confirm the **SAM 3 license** is accepted on huggingface.co/facebook/sam3 (and
  read the actual license text — commercial-use terms are unverified, see STRATEGY §3.1).

## ⬜ Tier 1 — class-agnostic detector (active build)
1. ⬜ **SAM 3 prompt-validation sweep** — prompt {`miniature`/`painted miniature`/
   `miniature figurine`} × threshold {0.30/0.40/0.50} on the gold images → score with
   `score_gold.py` → pick the config maxing **crowded-bucket recall** s.t. precision ≥
   baseline. (Decisions locked in `HANDOFF.md` §5.1.)
2. ⬜ Apply locked SAM 3 changes: drop `"painted"`, switch `post_process_object_detection`
   → `post_process_instance_segmentation` (may retire SAM 2 refinement).
3. ⬜ Box-convention check — if recall@0.3 ≫ recall@0.5, re-run with `--base-pad 0.10`.
4. ⬜ **Full ~30.6k auto-label run** on Colab (`bash scripts/phaseF/sync.sh`), resumable.
5. ⬜ Triage output (`triage_pseudolabels.py`): zero-box → review, prioritized F3 queue.
6. ⬜ **F2** — train RF-DETR-Medium v1 (gold oversampled + pseudo-labels); target
   mAP@50 0.70–0.78 vs gold_v2.
7. ⬜ **F3** — self-relabel @ conf 0.3, disagreement set → annotator review.
8. ⬜ **F4** — RF-DETR-Medium v2 (cloud) + RF-DETR-Nano (edge); target mAP@50 0.82–0.88.

## ⬜ Tier 2 — faction classifier (~20 classes)
- 🔄 DINOv2 linear probe **prototyped** (v1 faction top-1 0.68 on gold crops; beats
  KNN-vote +12pp). Tyranids 0.91, Necrons 0.70, **SM 0.47** (weak link), DG untestable.
- ⬜ **Calibrate a confidence threshold** for the "unknown" path — out_of_scope crops are
  confidently misclassified (empirically required, not optional).
- ⬜ Diversify the SM gallery (it's all `dup`-tagged near-dups — likely why SM is low).
- ⬜ Exit bar: faction top-1 ≥ 90% (or rely on top-3 + Tier 3 to discriminate).

## ⬜ Tier 3 — unit retrieval (~900 classes, open-set)
- ✅ Gallery **depth** solved 4/4 (SM/Necrons/Tyranids median 30 crops/unit, ~0
  singletons; DG seeded 0→189 crops / 29 units from on-disk gw_shop+CMON on
  2026-06-06 — no scrape needed after all).
- ⚠️ Depth ≠ retrieval: the 2026-06-06 numbers were **leave-one-out self-retrieval**
  (dup-inflated). The honest gold-domain bench
  (`docs/benchmarks/2026-06-09-tier3-gold-domain-retrieval.md`): scoped top-3
  **0.52 overall** — SM 0.20 / Tyranids 0.24 / Necrons 0.46 / **DG 0.93**. Only the
  curated DG gallery passes the bar.
- ⬜ **Replicate the DG gallery recipe for SM/Tyranids/Necrons** (product-labeled
  gw_shop/CMON crops, curated) + `weak_unit` label QA — the highest-leverage Tier 3
  work; a 73-point gap (DG 0.93 vs SM 0.20) says gallery quality, not embedding
  power, is the bottleneck.
- ⬜ DINOv3-L (or SigLIP 2) frozen embeddings + cosine k-NN scoped by Tier 2 faction.
- ⬜ Calibrate the "I don't recognise this" threshold (~0.81 from Phase 1).
- ⬜ Exit bar: unit top-3 ≥ 80% within-faction **measured on the gold-domain bench,
  not LOO** (currently 0.52 overall, 1/4 factions pass).

## ⬜ Tier 4 — VLM disambiguation (opt-in)
- ⬜ Claude/Gemini "which of these 3?" fallback when Tier 3 top-1 confidence < 0.6.

## ⬜ Data acquisition & quality
- ⬜ Wave 1 depth engine — query-by-taxonomy scraper (⚠️ needs SerpApi/CSE or Reddit key).
- ⬜ Waves 2–4 (realism / marketplace / negatives) — see `BATTLE_SCANNER_IMAGE_SOURCING.md`.
- ⬜ Synthetic pilot (BlenderProc) — prefer commercial STL studios over GW-IP Cults3D.
- ⬜ (Deferred per decision) DINOv2 linear-probe upgrade for the semantic junk filter.

## ⬜ Product / shipping
- ⬜ FastAPI persistent inference server (replaces per-call subprocess).
- ⬜ Wire consumer PWA to real inference (UI built on mock data; clean swap point).
- ⬜ Army-list aggregation — boxes → unit counts → Wahapedia points → export/share.
- ⬜ Phone packaging — RF-DETR-Nano → CoreML on-device.
- ⬜ Consumer feedback loop — confirmed detections → gallery (the data flywheel).

## ⚠️ Cross-cutting decisions
- ⚠️ **GW IP** — the binding legal constraint for a *commercial* product (lower-risk for
  offline training; ship only Apache-2.0 weights).
- ⚠️ Sourcing-key signup (SerpApi/CSE/Reddit) — gates Wave 1+, needed by Tier 3.
- ⬜ Deferred: DINOv3 domain adaptation (after real user data exists).

---

## v0 desktop-annotator backlog (maintenance only)

The annotator (`backend/` + `frontend/` + mobile PWA) is the **v0 surface** used for
hand-labelling, not the rebuild target. Still-valid hardening items from the old audit:

- ⬜ **Atomic annotation saves** — write `{path}.tmp` then `fs.rename()` (annotations are
  irreplaceable human work). ~15 min.
- ⬜ **`schemaVersion` on annotations** — future-proof the JSON format. ~20 min.
- ⬜ **YOLO export test coverage** — `remapExportLabel`, coord normalization, keypoint
  gen, train/val split. (Export is still used; the `/export` skill drives it.)
- ⬜ Git-track `training_data_annotations/` (or another backup) — months of human labour.
- ⬜ Frontend vitest infra — `jsdom`/`vitest 0.34` ESM/CJS conflict blocks component tests.
- ⬜ `BASE_OUTSIDE_MODEL` validation — 5 skipped tests in `annotationService.validation.test.ts`.

---

## Scraper suite — setup & run checklist (when acquisition resumes)

### One-time setup
- [ ] Reddit "script" app → client ID + secret; add `REDDIT_CLIENT_ID/SECRET/USER_AGENT`
      to `.env`.
- [ ] SerpApi or Google CSE key (the Wave 1 depth-engine gate).

### Dry-run first (always)
- [ ] `python scripts/reddit_collector.py --subreddit Necrons --limit 10 --dry-run`
- [ ] `python scripts/youtube_collector.py --all-channels --limit 3 --frame-limit 5 --dry-run`

### Collection (run supervised, rate-limited — not an unattended blast)
- [ ] Reddit faction subs · YouTube battle reports · marketplace (eBay/dakka via existing
      `scripts/scrape_*.py`).

### Post-collection quality passes
- [ ] CLIP score → dedup (`scripts/curation/quality_scan.py` + `deduplicate.py`); ingest
      to FiftyOne with provenance; re-pool.
