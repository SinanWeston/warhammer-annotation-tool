# Handoff — Battle Scanner (read this first)

**Updated:** 2026-06-08. For the next Claude instance picking up the work after a `/clear`.

---

## ⚡ CATCH-UP (30-second version — read this, then §0)

**Where we are:** the *foundation is done and validated*. The pipeline is detect →
faction → retrieve → VLM; v1 = SM / Necrons / Tyranids / Death Guard. Env is
**`fiftyone_env`** (no GPU locally → all heavy work on Colab). The dataset lives in
FiftyOne's MongoDB (`wh40k_pile`, **66,370 images**), NOT git — rebuilt via
`scripts/curation/*`.

**Done & validated:**
- **Gold eval set** `data/gold/gold_v2.json` — 89 imgs / 283 boxes, every v1 faction ≥40. The trusted measuring stick.
- **Tier 1 measuring infra** — `eval/gold.py` (count-MAE × density + per-faction recall), `eval/boxconv.py`, `eval/triage.py`, `scripts/phaseF/score_gold.py`. 157 tests green.
- **Junk filter** → `data/phaseF/autolabel_images.txt` = ~30.4k clean SAM 3 input.
- **Death Guard gallery: 0 → 189 crops / 29 units** (88.7% scoped Tier-3 top-3 — `docs/benchmarks/2026-06-06-dg-gallery-retrieval.md`). Built by *ingesting* gw_shop+CMON already on disk — no scraping. DG depth is no longer a blocker. ⚠️ **Caveat (2026-06-09 review):** that 88.7% is *leave-one-out over the gallery itself* (catalog self-retrieval, dup-inflated) — see the gold-domain re-eval `docs/benchmarks/2026-06-09-tier3-gold-domain-retrieval.md` for the deployment-domain number.
- **Tier 2 faction probe** prototyped (DINOv2 linear probe, 0.68 v1 top-1; SM weak at 0.47).
- **Codebase cleanup** (2026-06-05/06): removed dead Grounding-DINO/OWLv2 ensemble + the DINO-proposal feature, `yolo_env`→`fiftyone_env` everywhere, reconciled STRATEGY/CLAUDE/README, deleted dead scripts + `warhammer-analyzer/`. `TODO.md` is now the live roadmap.
- **New source online:** `warhammer_community` (robots-allowed HTTP) — +5,155 detection images, all factions, **un-embedded**.

**The single most important next step:** the **SAM 3 Tier 1 run on Colab** — prompt/threshold sweep (decisions locked in §5.1) → auto-label the ~30.4k → triage → train RF-DETR. Everything's prepped; it needs a GPU session.

**Other live threads:** (a) the un-embedded images (warhammer_community + roboflow) are being embedded **locally on CPU** (`scripts/curation/embed_local_cpu.py`, attach-only, resumable — re-run it if interrupted; check `ds.match({"embedding": None}).count()`); (b) finish labeling **v6** density round (`wh40k_gold_v6` in CVAT) → `pull v6` + `merge` — **the SAM 3 sweep is gated on this** (its selection criterion, crowded-bucket recall, currently rests on 5 images); also queue **v7** = the SM gold fill (candidates ready: `data/gold/gold_v7_sm_candidates.json`, tag via `select_gold_v7_sm.py --apply` → `gold_to_cvat.py push v7`); (c) **Tier 3 reality check (2026-06-09):** gold-domain bench = real-scene scoped top-3 **0.52 overall** — SM 0.20 / Tyranids 0.24 / Necrons 0.46 / **DG 0.93**. DG's *curated* gallery works; the three weak-labeled isolation galleries don't. Replicate the DG gallery recipe for SM/Tyranids/Necrons + `weak_unit` label QA — not depth, not backbone (paint-invariance AUC is 0.835 on trusted labels); (d) **Tier 2 is the pipeline chokepoint (2026-06-09):** compounded Tier2→Tier3 on real crops = **0.089** with the 20-way probe, **0.228 v1-restricted** (`docs/benchmarks/2026-06-09-review-experiments.md`). The production probe is now `photoanalyzer.classify.FactionProbe` — **v1-restricted by default** (via `taxonomy.V1_FACTIONS`; SM faction 0.39→0.94), artifact at `models/tier2_faction_probe.joblib` (retrain: `scripts/phase2/train_faction_probe.py`). Tier 2 tuning is now EXHAUSTED on current data (2026-06-10, `docs/benchmarks/2026-06-10-tier2-dg-routing-unknown-threshold.md`): class weighting doesn't move DG routing (domain problem — fix is real-photo DG crops from the SAM 3 run), and no open-set signal separates non-v1 minis (AUC ~0.65, need ~0.9 — gate mechanism built into FactionProbe, operating point deferred to post-gallery-curation). Both remaining Tier 2 levers are blocked on data, not modelling; (e) ⚠️ **run `scripts/curation/fix_gold_pool_contamination.py`** — 7 gold_v2 DG images are sitting in the gallery pool (seed_dg_gallery swept them in; script now guarded), then re-run the two retrieval benches. Holdout is also 21% exact-twinned with the gallery — dedup before ever using it as a test set.

**Gotchas that bite:** check disk before scraping (ingestion ≠ acquisition — burned 3× today); browser scrapers (CMON/eBay) die unattended; an image isn't usable until embedded (Colab); `fiftyone_env` is CPU-only.

---

## 0. Read these, in order
1. **`BATTLE_SCANNER_PLAN.md`** — the bible (data-centric rebuild: survey → frozen
   foundation models → curate → measure). Supersedes STRATEGY.md for execution order.
2. **`BATTLE_SCANNER_IMAGE_SOURCING.md`** — the image acquisition plan (waves, provenance schema).
3. **`LABELING_GUIDE.md`** — the battle-tested annotation rulebook.
4. **`SETUP_CHECKLIST.md`** — what credentials/decisions are still needed from the user.
5. Your auto-loaded memory files (goal, battle-scanner-plan, v0-lessons,
   annotations-untrusted, v1-scope, data_sources_roadmap) — `v1-scope` is the live state.

**The goal:** photo of a tabletop → count + faction + unit per model → army list w/ points.
Phone app. Architecture: detect → faction → retrieve → optional VLM. v1 = 4 factions.

---

## 1. Current state (one paragraph)
Active data-centric rebuild. The pile (`wh40k_pile` in FiftyOne MongoDB) is **66,370
images** across 8 sources, deduped, role-split into gallery/detection/holdout pools,
provenance-stamped. v1 factions locked: **space_marines, necrons, tyranids, death_guard**.
**Gallery depth solved 3/4 by the LOO bench** — DG/Necrons/Tyranids clear the 0.80
top-3 bar; **Space Marines fails it (0.697)** with a 100%-dup gallery. (And note the
LOO bench is self-retrieval — the gold-domain eval is the honest number.) **Gold eval set**
`data/gold/gold_v2.json` — 89 imgs / 283 boxes, every v1 faction ≥40 (`gold_v1.json`
35/124 frozen as baseline). **Tier 1 measuring infra built** (eval harness, box
reconciliation, triage, junk filter → 30.4k clean SAM 3 input). **Tier 2** faction probe
prototyped. **Codebase cleaned** of the pre-pivot leftovers (Grounding-DINO/ensemble,
yolo_env, DINO-proposal feature, dead scripts, warhammer-analyzer). Newest source
`warhammer_community` added (+5,155 detection imgs, un-embedded). Next build step: the
**SAM 3 Tier 1 detector run on Colab** → distill RF-DETR, scored vs gold_v2.

---

## 2. How to resume (environment)
- **No `yolo_env`** (mothballed). The new env is **`fiftyone_env/`** (gitignored).
  Has: fiftyone 1.16, fiftyone-brain, umap, roboflow, torch (CPU), transformers, timm.
- **No local GPU** → all GPU work (embeddings, SAM 3) goes to **Colab**.
- Launch the data browser: `fiftyone_env/bin/fiftyone app launch wh40k_pile` → localhost:5151
- The dataset lives in FiftyOne's MongoDB (NOT git). The curation scripts rebuild it.

## 3. The dataset `wh40k_pile` (FiftyOne)
- **66,370 samples** (60,901 embedded; the un-embedded 5,469 = warhammer_community 5,155 + roboflow 314). Fields: `weak_faction`, `source`, `weak_unit`, `corpus` (td1/td2/roboflow),
  `pool`, `faction_v1`, `embedding` (DINOv2-large), provenance (`source_url`, `source_platform`,
  `caption_title`, `scrape_date`, `file_hash`, `license_status`, `product_safe`, `realism_tier`,
  `finish_state`, `label_source`, `label_confidence`), `ground_truth` (gold boxes).
- **Pools** (`pool` field + saved views): gallery 19,576 · detection 34,537 · holdout 1,000 ·
  excluded 5,788 (near-dups).
- **Saved views**: `clean`, `gallery`, `detection`, `holdout`, `v1`, `gold`.
- **Tags**: `dup` (16,512 near-dups), `low_unique` (junk-seed), `gold` (35), `gold_skipped` (16), `roboflow`.

## 4. Scripts (all in `scripts/curation/`, committed)
`ingest_fiftyone.py` → `prepare_embed_bundle.py` → `embed_colab.ipynb`/`embed_gpu.py` →
`load_embeddings.py` → `set_v1_factions.py` → `build_pools.py` → `provenance.py` →
`acquire_roboflow.py` → `backfill_provenance.py` → `gold_to_cvat.py` (push/pull).
Each has a docstring; run with `fiftyone_env/bin/python`.

## 5. Done / in-flight / next
- ✅ Curate (ingest, dedup, pools, provenance), v1 factions, Wave 0 sourcing.
- ✅ **Gold set expanded to 89/283, all factions ≥40** (CVAT rounds v2–v5; tooling:
  `gold_to_cvat.py` profiles + `merge_gold_v2.py`).
- ✅ **Tier 1 measuring infra (2026-06-05):**
  - `src/photoanalyzer/eval/gold.py` — score detector vs gold_v2: **count-MAE × density
    bucket** (headline), per-faction recall (DG/Necron/Tyranid auto-flagged wide-CI),
    recall@IoU sweep (box-convention diagnostic). 20 tests in `tests/test_gold_eval.py`.
  - `src/photoanalyzer/eval/boxconv.py` — reconcile mask-tight SAM boxes → model+base
    gold convention (bottom-pad ~0.10) + a diagnostic that detects base-clipping.
  - CLI: `scripts/phaseF/score_gold.py --preds data/pseudo_labels/boxes`.
  - `scripts/curation/quality_scan.py` — cheap junk filter; tagged **1,463 `lowq`**
    (blur/tiny/strip).
  - `scripts/curation/semantic_junk_scan.py` — CLIP zero-shot semantic junk; tagged
    **1,772 `junk_clip`** (meme/terrain/screenshot/text/illustration/dice, 5.1%). NOTE:
    ViT-B/32 zero-shot has poor *recall* — ~50% junk hides in low-confidence keeps. We
    deliberately keep only the high-precision flags (see decided strategy below); a
    DINOv2 linear probe is the upgrade path if deeper filtering is ever wanted.
  - `scripts/phaseF/clean_detection_list.py` → **`data/phaseF/autolabel_images.txt`**:
    the SAM 3 input = detection pool − (`excluded ∪ lowq ∪ low_unique ∪ junk_clip`) =
    **30,638 images** (88.1% of pool). This is what the Colab auto-label run consumes.
  - `src/photoanalyzer/eval/triage.py` + `scripts/phaseF/triage_pseudolabels.py` —
    **post-SAM 3** bucketing: zero-box → REVIEW (not drop: "junk OR hard miss", the
    misses are AL gold), has-boxes → prioritized F3 queue (low_conf > count_outlier >
    geom_outlier). 8 tests.
- ⬜ **Tier 1 detector run (next):** SAM 3 on Colab → distill RF-DETR (Plan D2/§3.1) →
  `score_gold.py` vs gold_v2. **Apply the §5.1 SAM 3 changes below before the full run.**
- ⬜ Wave 1 depth engine (needs SerpApi/CSE/Reddit keys — query-by-taxonomy over v1 factions).
- ⬜ Tier 2/3 faction+unit retrieval (Plan D3) — gallery already built for 3/4 factions.

### 5.1 Tier 1 decisions locked 2026-06-05 (read before the SAM 3 run)
From a literature pass (SAM 3 paper arXiv 2511.16719 + HF docs) and the gold-set analysis:
- **Prompt-validate SAM 3 on ~150 stratified images before the 34.7k run.** Grid:
  prompt ∈ {`miniature`, `painted miniature` (current), `miniature figurine`} × threshold
  ∈ {0.30, 0.40, 0.50}. Current default 0.25 is *half* the paper's 0.5 operating point.
- **Drop `"painted"`** — it acts as an attribute filter that suppresses unpainted/primed
  models. Prefer the bare object-noun `"miniature"`.
- **Switch `post_process_object_detection` → `post_process_instance_segmentation`** in
  `src/photoanalyzer/detect/ensemble/sam3.py` — SAM 3 emits masks+boxes natively, likely
  retiring the separate SAM 2 refinement step (~halves GPU time). Bench `sam3` vs
  `sam3_refined` to confirm before dropping SAM 2.
- **Box convention:** gold = model+**base**, SAM = mask-tight (clips base). Run
  `score_gold.py` first WITHOUT padding; if the recall@IoU sweep shows a base-clip gap
  (recall@0.3 ≫ recall@0.5), re-run with `--base-pad 0.10`. Adapt the *prediction*, never
  the frozen gold. Padding heuristic validated at ~8–12% in the literature.
- **Decision rule for the prompt sweep:** maximize **recall@0.5 on the *crowded* bucket**
  s.t. precision ≥ baseline — under-detection in crowds (two models → one box) is the
  error RF-DETR inherits and can't recover; excess FPs get cleaned in the F3 review pass.
- **⚠ Gold density gap:** the crowded bucket has only **5 images** (gold is 64% single-
  model — faction top-ups leaned on single-army listings). Count-MAE on the crowded slice
  is underpowered until ~10–15 more **crowded** images (11+ models, fully enumerable) are
  labeled — pull from reddit/dakkadakka battle scenes (mixed-army is fine for a *count*
  metric; opponents = out_of_scope). A "gold density round" is the cheapest next labeling.
- **Exemplars** (image prompts) are SAM 3's biggest upside (78.1 vs 56.4 AP in-paper) but
  the cross-image HF API is uncertain — validate before relying on it.

## 6. OPEN DECISIONS (status 2026-06-05)
1. **Death Guard — DECIDED: proceed on current depth.** DG gallery depth feeds Tier 3
   *retrieval*, orthogonal to the class-agnostic Tier 1 detector. The ≥40 gold boxes give
   a provisional (wide-CI) per-faction recall read. **GW scrape queued for *before* Tier 3**
   (Cloudflare WAF → needs user at keyboard). DG holdout pool is now EXHAUSTED — any more
   DG (gallery or eval) requires that scrape.
2. **Gold set — DONE.** 89/283, every v1 faction ≥40 (`gold_v2.json`). Residual gap is
   *density* not faction: crowded bucket = 5 imgs (see §5.1). User declined shooting real
   tabletop photos (owns only unpainted tyranids) → eval leans on scraped data, reads
   optimistic vs real phone photos.
3. **Detection pool junk filter — DECIDED & DONE.** Strategy: commit only the cheap
   *high-precision* junk (1,463 `lowq` + 1,772 `junk_clip` + legacy `low_unique`) → a
   30,638-image clean SAM 3 input (`autolabel_images.txt`). Do NOT chase the borderline
   junk with a heavier classifier — instead **bucket on the SAM 3 output**: zero-box →
   review (junk OR hard miss → AL gold), and run a prioritized F3 review (low-conf boxes,
   count outliers, weird geometry, a 0-box sample). Tooling = `triage_pseudolabels.py`.
   (DINOv2 linear probe remains the upgrade if a cleaner pre-filter is ever wanted —
   CLIP zero-shot recall is only ~50% in the borderline.)
4. **Sourcing keys (user, 5 min):** sign up for SerpApi or Google CSE so Wave 1 is ready
   at Tier 3. Nothing today gates on it.

## 7. Credentials & gotchas
- `.env` (gitignored) has: `ROBOFLOW_API_KEY` (works), `CVAT_USERNAME`/`CVAT_PASSWORD` (works).
  **Missing** (block Wave 1+): SerpApi / Google CSE / Reddit (PRAW) / Apify. See SETUP_CHECKLIST.
- **CVAT gold tasks** (app.cvat.ai, **free tier caps at 3 tasks**): v1/v2/v3 deleted after
  pull+merge (all labels frozen in `gold_v2.json`); live tasks `wh40k_gold_v4` (2310058) +
  `wh40k_gold_v5` (2310139) are pulled+merged and now disposable. Delete pulled tasks to
  free slots. Profile-based `gold_to_cvat.py push|pull {v1..v5}` + `merge_gold_v2.py`.
- **Gotchas:** (a) no local GPU → Colab for SAM 3 / heavy embed; (b) CVAT API needs a real
  username+password — GitHub-OAuth signup has none until set in CVAT settings; (c) FiftyOne
  reads CVAT creds at import → set `FIFTYONE_CVAT_*` env vars BEFORE `import fiftyone`;
  (d) `backend/training_data` has 13k symlinks into `scripts/warhammer_com` — follow them
  (rglob does, `find -type f` doesn't).

## 8. Working style notes (from this session)
- The user is the 40K domain expert — defer to their faction/model calls.
- Be honest about what can't run unattended (GPU/credentials/ToS) — don't fake it.
- Don't mass-scrape third-party sites unsupervised; the user owns the legal posture.
- Commit scripts as you go; the FiftyOne dataset state is NOT in git (back up via exports
  like `data/gold/gold_v1.json`).
