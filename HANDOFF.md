# Handoff — Battle Scanner (read this first)

**Updated:** 2026-06-04, end of session. For the next Claude instance picking up the work.

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
Project was mothballed, now in active data-centric rebuild. Step 1 (**curate the pile**) is
done: 61,215 images in a FiftyOne dataset `wh40k_pile`, deduped, role-split into
gallery/detection/holdout pools, provenance-stamped (~49% with real source URLs). v1
factions locked: **space_marines, necrons, tyranids, death_guard**. Gallery depth (v0's
killer) solved for 3/4 (every SM/Necron/Tyranid unit ≥5 crops; Death Guard has 0 — open).
**Gold eval set is frozen**: 35 hand-labeled images, 124 boxes → `data/gold/gold_v1.json`.
Wave 0 sourcing done (provenance + 314 CC-BY Roboflow images). Currently measuring a
first auto-label baseline (Grounding-DINO vs gold).

---

## 2. How to resume (environment)
- **No `yolo_env`** (mothballed). The new env is **`fiftyone_env/`** (gitignored).
  Has: fiftyone 1.16, fiftyone-brain, umap, roboflow, torch (CPU), transformers, timm.
- **No local GPU** → all GPU work (embeddings, SAM 3) goes to **Colab**.
- Launch the data browser: `fiftyone_env/bin/fiftyone app launch wh40k_pile` → localhost:5151
- The dataset lives in FiftyOne's MongoDB (NOT git). The curation scripts rebuild it.

## 3. The dataset `wh40k_pile` (FiftyOne)
- **61,215 samples**. Fields: `weak_faction`, `source`, `weak_unit`, `corpus` (td1/td2/roboflow),
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
`acquire_roboflow.py` → `backfill_provenance.py` → `gold_to_cvat.py` (push/pull) →
`eval_autolabel_gold.py`. Each has a docstring; run with `fiftyone_env/bin/python`.

## 5. Done / in-flight / next
- ✅ Curate (ingest, dedup, pools, provenance), v1 factions, gold set, Wave 0 sourcing.
- 🔄 Auto-label baseline (Grounding-DINO vs gold) — see §7 for result / `eval_autolabel_gold.py`.
- ⬜ **SAM 3 auto-label → distill RF-DETR** (Plan D2) — Colab; reuse `scripts/phaseF/autolabel_colab.ipynb`.
- ⬜ Wave 1 depth engine (needs SerpApi/CSE/Reddit keys — query-by-taxonomy over v1 factions).
- ⬜ Tier 2/3 faction+unit retrieval (Plan D3) — gallery already built for 3/4 factions.

## 6. OPEN DECISIONS (need the user)
1. **Death Guard gallery = 0 crops.** Keep DG (scrape GW official, needs user at keyboard
   for the Cloudflare WAF) OR swap DG for Orks/Astra Militarum (have corpus depth).
2. **Gold set = 35, below the 50 target.** Reseed ~16 more, or grow later. User declined
   shooting real tabletop photos (only owns unpainted tyranids) → eval leans on scraped
   data and will read optimistic vs real phone photos.
3. **Detection pool junk filter** — ~30% of the random gold pick was meme/terrain/blur;
   the detection pool needs a junk pass (start from the `low_unique` tag).

## 7. Credentials & gotchas
- `.env` (gitignored) has: `ROBOFLOW_API_KEY` (works), `CVAT_USERNAME`/`CVAT_PASSWORD` (works).
  **Missing** (block Wave 1+): SerpApi / Google CSE / Reddit (PRAW) / Apify. See SETUP_CHECKLIST.
- **CVAT gold tasks** (app.cvat.ai): `wh40k_gold_v1` (task 2307405, labeled), `wh40k_gold_extra`
  (task 2307548, skipped/empty). Annotation runs `gold_v1`, `gold_v1_extra` on the dataset.
- **Gotchas:** (a) no local GPU → Colab for SAM 3 / heavy embed; (b) CVAT API needs a real
  username+password — GitHub-OAuth signup has none until set in CVAT settings; (c) FiftyOne
  reads CVAT creds at import → set `FIFTYONE_CVAT_*` env vars BEFORE `import fiftyone`;
  (d) `transformers 5.x` changed the detection box format — check Grounding-DINO post-process
  if `eval_autolabel_gold.py` looks off; (e) `backend/training_data` has 13k symlinks into
  `scripts/warhammer_com` — follow them (rglob does, `find -type f` doesn't).

## 8. Working style notes (from this session)
- The user is the 40K domain expert — defer to their faction/model calls.
- Be honest about what can't run unattended (GPU/credentials/ToS) — don't fake it.
- Don't mass-scrape third-party sites unsupervised; the user owns the legal posture.
- Commit scripts as you go; the FiftyOne dataset state is NOT in git (back up via exports
  like `data/gold/gold_v1.json`).
