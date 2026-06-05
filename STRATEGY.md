# Strategy — Warhammer 40K Miniature Recognition

**Status**: Direction adopted 2026-04-13. Living document — update the status section at the bottom as phases ship.
**Scope**: Architectural direction for the CV pipeline. Supersedes the end-to-end-YOLO assumption baked into earlier planning (SPEC.md §6.4).

This is the guiding star. Every modelling decision, every annotation effort, every backend endpoint should be checked against it. When a tradeoff arises, default to what this document says; if it's wrong, update it deliberately.

---

## 1. The goal, decomposed

From a user photograph of a painted army, the system must answer three questions:

1. **How many miniatures are present?** — a counting / detection problem.
2. **Which factions are represented, and in what proportion?** — a coarse classification problem (~20 classes).
3. **Which specific units are present?** — a fine-grained classification problem (~900 classes, long tail, open-set).

These are three problems with three different optimal architectures. Treating them as one — as the current end-to-end YOLO11x does — is the core mistake that this strategy corrects.

| Sub-goal | Nature | Hard part | Data required per class |
|---|---|---|---|
| Count | Class-agnostic detection | Occlusion in crowded scenes | 0 (foundation models suffice) |
| Faction (~20 classes) | Coarse classification | Broad visual cues are strong | 30–100 examples |
| Unit (~900 classes) | Fine-grained classification | Within-faction units look near-identical | 5–10 examples *if embedding-based*, hundreds if softmax-trained |

## 2. Why the current architecture has a ceiling

Evidence points to a mid-40% mAP50 plateau even with significantly more annotations. The reasons are structural, not data-volume-bound.

- **Class imbalance compounds.** 900 units, long-tailed. Popular chapters dominate batches; rare units can't be discriminated with a handful of examples under softmax loss.
- **Detection and classification losses fight.** Box regression wants appearance invariance; classification wants class-specific memorization. With thin per-class data, the classification branch overfits to specific paint schemes in the training set.
- **Paint variance is the unsolved problem.** Two Intercessor models painted Ultramarine and Blood Angel are more visually different to a CNN than an Intercessor and an Assault Intercessor painted the same way. This is the opposite of what the model should learn.
- **Open-set is a failure mode for softmax.** New Games Workshop releases arrive monthly. Softmax must assign a class; it cannot say "I don't recognize this". Retrieval with a confidence threshold can.

Every TCG card scanner that scaled past ~1K classes hit this wall and pivoted away from monolithic classification heads. Ximilar (15+ TCGs, 97%+ accuracy commercial) explicitly abandoned CNN classifiers in favour of embedding retrieval. That pattern — `YOLO + CLIP` / `detector + embedding retrieval against a catalog` — is the published blueprint we will adopt.

The benchmark closest to our regime is iNaturalist-2021 (10K fine-grained species, thin per-class data):

- Full softmax training: ~60–65% top-1 with heroic effort.
- DINOv2 frozen features + linear probe: **81.1%**.
- DINOv2 V-measure: **0.908** (vs 0.719 CLIP, 0.708 ResNet-18).

We will not out-engineer that 20+ point gap with more YOLO epochs.

## 3. Target architecture

Three tiers, decoupled, each replaceable independently. Add Tier 4 as a premium / fallback layer.

```
Photo
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ Tier 1  —  Class-agnostic detection                 │
│ Cloud: fine-tuned RF-DETR-Medium (DINOv2 backbone)  │
│ Edge:  RF-DETR-Nano for on-device mobile inference  │
│ Bootstrap: Grounded-SAM-2 pseudo-labels on ~17k     │
│ scraped images + 1.5k gold. See §3.1.               │
│ Output: bounding boxes, single class ("miniature"). │
└─────────────────────────────────────────────────────┘
  │
  ▼ per crop
┌─────────────────────────────────────────────────────┐
│ Tier 2  —  Faction classifier (20 classes)          │
│ DINOv3-L linear probe OR current YOLO as            │
│ classifier-only. Existing 1,500 annotations train   │
│ this. Output: faction + confidence.                 │
└─────────────────────────────────────────────────────┘
  │
  ▼ scoped to chosen faction
┌─────────────────────────────────────────────────────┐
│ Tier 3  —  Unit retrieval (within-faction k-NN)     │
│ Embed crop with frozen DINOv3-L (or SigLIP 2).      │
│ Cosine similarity against reference gallery.        │
│ Gallery: 5–10 canonical photos × ~60 units per      │
│ faction = ~500 images searched. k-NN is trivial.    │
│ Output: top-3 unit candidates with confidences.     │
└─────────────────────────────────────────────────────┘
  │
  ▼ if top-1 confidence < threshold
┌─────────────────────────────────────────────────────┐
│ Tier 4  —  VLM disambiguation (opt-in)              │
│ Claude / Gemini: "which of these three is this?"    │
│ Zero-shot, strong on fine visual comparison.        │
└─────────────────────────────────────────────────────┘
```

### 3.1 Tier 1 implementation: pseudo-label bootstrap

The original framing ("Zero training. Foundation models suffice.") held up at the Phase 1 prototype scale (6 queries, OWLv2 at 83% recall) but does *not* hold up at product scale. April 2026 research (Roboflow's RF-DETR training notes, VLM detection survey arXiv 2504.09480) documents that open-vocabulary detectors deliver only **55–70% correct boxes on dense tabletop scenes** — the Dakka-Dakka tier where the consumer product will be judged. The fix is not to abandon zero-shot but to **repurpose it as an auto-labeler** and train a small, fast, class-agnostic detector on the result. This is the same recipe Roboflow uses to pre-train RF-DETR itself.

Concrete pipeline for building the Tier 1 detector:

1. **Freeze a 200-image eval set** stratified by bbox density (single / sparse / medium / crowded), never trained on. (→ Phase C.)
2. **Auto-label the ~30.6k clean detection-pool images** (34.7k pool minus the junk filter → `data/phaseF/autolabel_images.txt`) with **SAM 3 detection + optional SAM 2 mask refinement**. The original multi-detector ensemble (SAM 3 + Grounding DINO + OWLv2 + agreement voting) was **dropped 2026-04-25** — Phase C bench showed SAM 3 beating the alternatives 3× and the weaker votes only hurt precision (DINO/OWLv2 code removed 2026-06-05). Class-agnostic NMS @ IoU 0.5, SAHI for images > 1200 px long edge; prompt/threshold locked in `HANDOFF.md` §5.1. (~16–30 GPU-hours on a T4.) Implementation: `scripts/phaseF/autolabel_ensemble.py`, modules under `src/photoanalyzer/detect/ensemble/`. Then bucket output via `scripts/phaseF/triage_pseudolabels.py` (zero-box → review).
3. **Train RF-DETR-Medium v1** on the union of 1,500 gold annotations (oversampled 5–10×) + ~15,600 auto-accept pseudo-labels. Expected mAP@50 on the frozen eval: 0.70–0.78.
4. **Self-relabel at confidence 0.3.** Compare v1 predictions to the original pseudo-labels; images where they disagree — plus the ensemble's single-supporter review tier — become the active-learning pool (~1,000–3,000 images, ~5–12 human-hours in the desktop annotator).
5. **Train RF-DETR-Medium v2** (cloud, quality-max) and **RF-DETR-Nano** (edge, mobile) on the cleaned union. Target mAP@50 on the frozen eval: **0.82–0.88**. Both are Apache-2.0; no knowledge-distillation loss, "poor man's distillation" via shared dataset.

License stack is deliberately all-Apache-2.0 **for the shipped inference path**. The offline pseudo-labeller may use gated models so long as their outputs are used only to train the Apache-2.0 shipping stack:

| Component | License | Role | Why chosen |
|---|---|---|---|
| SAM 3 | SAM License (Meta) | Offline pseudo-labeller (primary) | Corrected 2026-04-24: the current SAM 3 license permits commercial use, has no competing-foundation-models clause, and does not force share-alike on outputs. Used offline only; the shipped detector is RF-DETR-Medium. More than doubles OWLv2 / DINO-X on SA-Co exhaustive detection (arXiv 2511.16719). |
| ~~Grounding DINO base~~ | Apache-2.0 | **DROPPED 2026-04-25** | Was an ensemble member; Phase C bench showed it only hurt precision vs SAM 3 alone. Code removed 2026-06-05. |
| ~~OWLv2 image-guided~~ | Apache-2.0 | **DROPPED 2026-04-25** | Was the visual-prompt ensemble member. Removed with Grounding DINO. |
| SAM 2 hiera-large | Apache-2.0 | Mask refinement | Ungated on HF; tightens every candidate box to the silhouette via mask-to-bbox, filters false positives whose refined IoU with the candidate < 0.3. |
| RF-DETR-Medium (cloud) | Apache-2.0 | **Shipped detector** | DINOv2 backbone, peer-reviewed at ICLR 2026, explicitly designed for 1k–20k custom datasets |
| RF-DETR-Nano (edge) | Apache-2.0 | Shipped edge detector | Same model family, ships to iPhone via CoreML. ~5 mAP below YOLO26-n but YOLO26-n is AGPL-3.0 which constrains closed-source commercial distribution |

**~~Ensemble logic (agreement voting)~~ — REMOVED 2026-04-25.** The pipeline is a
single detector (SAM 3), so there is no cross-detector voting. Review routing is now
done per-image on the SAM 3 output by `scripts/phaseF/triage_pseudolabels.py`
(zero-box → review = "junk OR a hard miss"; has-boxes → a prioritised F3 queue by
low-confidence / count-outlier / weird-geometry). The Grounding DINO + OWLv2 detector
code was deleted 2026-06-05 (recover from git history if an A/B is ever wanted).

### Why this wins over the current pipeline

| Property | YOLO end-to-end (current) | Three-tier architecture (target) |
|---|---|---|
| Add a new unit (release month) | Full retrain, new annotated data | Add 5–10 photos to gallery. Ship same day. |
| Scale 900 → 2,000 classes | Accuracy degrades | Linear cost, no architecture change |
| "I don't recognize this" | Softmax forces a class | Cosine threshold returns "unknown" |
| Paint variance | Hurts within-class cohesion | DINOv3 pretrained on 1.7B images, variation-robust |
| Uncertainty to user | Single label | Top-K with scores, fits "did you mean?" UI |
| Independent iteration | One big model to retrain | Swap any tier without touching others |

## 4. What to keep, what to stop

### Keep

- **Annotation tooling (desktop + mobile).** Output shifts from "train a detector" to "crop + unit label for the gallery". All 1,500 annotations stay useful.
- **YOLO11x weights.** Redeploy as a 20-class faction classifier. Run 2's 39.9% mAP50 is probably >80% on faction-only evaluation.
- **Active learning pipeline.** Re-target: prioritise crops for **gallery enrollment**, not training set.
- **~~Grounding DINO / OWLv2~~ — DROPPED.** Were considered as ensemble auto-labellers; Phase C bench killed them (SAM 3 alone won 3×). Code removed 2026-06-05. The auto-labeller is **SAM 3** (§3.1 Step 2).
- **18K scraped image pool.** Fodder for later DINOv3 domain adaptation to close the studio-photo-vs-painted-tabletop gap.
- **Backend + API contracts.** No API change required for Tier 1+3 internals; the `/api/detect` endpoint stays, its innards get swapped.
- **Consumer v2 UI.** Already supports top-K grouping, uncertainty section, inline edits — fits retrieval-style output better than softmax classification.

### Stop

- Training YOLO11x with a 900-class head.
- Expecting mAP50 gains past ~60% from more annotations alone.
- Treating unit identification as a classification problem. It is a retrieval problem.
- Optimising one number (mAP50) that conflates detection and classification performance.

## 5. Force multipliers

### 5.1 Synthetic data from 3D models

Games Workshop does not publish STL files, but the fan community does: **~4,000 free 3D models on Cults3D**, thousands more on CGTrader, active Sketchfab collections. Coverage is sufficient for every unit the consumer app will realistically see.

Domain randomization playbook (Tremblay 2018, NVIDIA DOPE, now standard):

- Random paint schemes applied per-part (torso, shoulderpads, weapon, base)
- Random lighting (soft box, hard spot, outdoor)
- Random backgrounds (game mats, grass, rubble, plain)
- Random poses (rotate in small ranges to match kit posability)
- Random distractors (other miniatures, dice, rulers)

Mix ~80% synthetic + 20% real painted. This is the only credible path to covering the long tail (Forgeworld units, ten-year-old sculpts nobody photographs).

Tooling: **BlenderProc** is the production-grade procedural rendering pipeline; NVIDIA Omniverse Replicator is the heavyweight alternative.

### 5.2 Community data flywheel

The consumer app is the flywheel. Every confirmed detection becomes a new gallery photo, tagged and labelled by the user. Three months in, the gallery is larger and more in-the-wild than anything we could scrape.

Seed the gallery from free, permissive sources:

- **Games Workshop product pages** — canonical studio photos, one per kit.
- **Lexicanum** — fan wiki, 35 image subcategories, cleanest labelled corpus.
- **Wahapedia** — canonical unit taxonomy + point values (non-image data anchor).

## 6. Research backing (why to trust this)

- **Class-agnostic detection is tractable with the right split-of-work.** Foundation models (Grounded-SAM-2, SAM 3, T-Rex2, OWLv2) hit **50–70% zero-shot recall on painted miniatures** — strong enough to auto-label 17k scraped images in a weekend, too weak (55–70% correct boxes on dense Dakka-Dakka scenes, per arXiv 2504.09480) to ship as the inference-time detector. The validated 2026 pattern is: auto-label with foundation → fine-tune a small specialised detector (RF-DETR, DINOv2 backbone, Apache-2.0, ICLR 2026). Roboflow uses the same recipe to pre-train RF-DETR itself on Objects365 + SAM 2 pseudo-labels.
- **Fine-grained retrieval is solved.** DINOv3 (Meta, 2025; 7B-param ViT, 1.7B training images) extends DINOv2's lead. On the 10K-class species benchmark: DINOv2 70%, CLIP 15%, ResNet ~13%.
- **Production analog.** TCG card scanners (Ximilar, Dragon Shield, Delver Lens, Pokellector) all converged on embedding retrieval, hitting 95%+ on thousands of classes. `YOLO + CLIP` is the published blueprint.
- **Warhammer CV is greenfield.** Two tiny Roboflow datasets (97, 35 images). No published academic work. No Games Workshop-official scanner. We are ahead of anything public; the question is direction, not competition.

See [STRATEGY_SOURCES.md](docs/STRATEGY_SOURCES.md) for the full reading list and links.

## 7. Implementation roadmap

Each phase ends with a measurable outcome. Do not proceed to the next phase without it.

### Phase 0 · Baseline reality-check (1–2 days)

- Evaluate current YOLO11x on a held-out set *scored three ways*: detection mAP50, **faction top-1**, **unit top-1**.
- The last two numbers are the honest baseline we'll compete against.

**Exit criteria**: three numbers published in `docs/benchmarks/`.

### Phase 1 · Prototype Tier 1 + Tier 3, no training (1–2 weeks)

- Scrape Games Workshop product pages → seed gallery (~500 units × 1 canonical photo each).
- Wire **T-Rex2** or **OWLv2** in visual-prompt mode as Tier 1. Feed 20 example miniature crops from existing annotations.
- **DINOv3-Base** frozen embeddings for Tier 3. Cosine k-NN.
- Skip Tier 2. Evaluate unit accuracy directly against a held-out set of annotated crops.

**Exit criteria**: unit top-5 accuracy comparable to or better than current YOLO unit top-1.

### Phase 2 · Add Tier 2 and expand gallery (2 weeks)

- Repurpose YOLO11x as faction-only classifier (single softmax on frozen features) OR DINOv3 linear probe.
- Expand gallery to 5 photos per unit — mix Games Workshop studio + Lexicanum + annotated crops.
- Scope Tier 3 k-NN by Tier 2 output.

**Exit criteria**: faction top-1 ≥ 90%; unit top-3 accuracy ≥ 70% within-faction.

### Phase 3 · Synthetic data pilot (4 weeks)

- Pick 20 popular units. Grab STLs from Cults3D. Render 100 variants each via BlenderProc with paint-scheme randomization.
- Mix into the gallery. Measure accuracy lift on those units vs unchanged control units.
- If lift ≥ 10%, scale to 200 units.

**Exit criteria**: measured accuracy lift on pilot units, go/no-go decision on full scale-out.

### Phase 4 · Consumer feedback loop + VLM tier (ongoing)

- Ship Tier 1–3 in the consumer app with a "did you mean?" top-3 UI.
- Every user confirmation → gallery add (after dedup + quality filter).
- Tier 4 (VLM verification) opt-in, shown only when Tier 3 top-1 confidence < 0.6.

**Exit criteria**: sustained growth in gallery size + rising consumer top-1 acceptance rate.

### Phase 5 · DINOv3 domain adaptation (defer until user data exists)

- Contrastive pretraining on the 18K scraped image pool + accumulated consumer uploads.
- Only worthwhile once there is measurable user-facing pain from the studio-vs-painted domain gap.

## 8. Metrics that actually matter

The product is a reference gallery, not a model. Track what a gallery-centric product should track.

- **Gallery coverage**: units present / total published units (Wahapedia canonical list).
- **Gallery freshness**: median age since last photo added per unit.
- **Gallery depth**: median photos per unit.
- **Consumer top-1 accuracy**: fraction of scans where user accepts first suggestion unchanged.
- **Consumer top-3 accuracy**: fraction where user's chosen unit appears in top-3.
- **"I don't recognize this" recall**: on genuinely unknown crops (new sculpts not yet in gallery), does the system correctly return low confidence?
- **Time-to-enrol a new unit**: from Games Workshop announcement to gallery presence.

These have very different incentives from minimising a detection loss — they reward curation, freshness, and calibration.

## 9. Honest tradeoffs

- **Latency.** Retrieval adds ~50–200ms per crop (embed + k-NN over ~500 references scoped by faction). Negligible for photo-upload UX; unsuitable for 30fps live video (not a current goal).
- **Ongoing curation.** Building a database, not training a model. Plan for gallery audits, a deprecation workflow for bad images, and a Wahapedia-sync job.
- **Model size.** T-Rex2 / OWLv2 / DINOv3 weights are GB-scale. Inference stays on the backend; the PWA uploads and receives JSON. No change to current deployment model.
- **VLM cost.** Tier 4 adds ~$0.01–0.05 per scan. Budget as a premium feature or rate-limit free users.
- **Paint variance is still hard.** DINOv3 helps, synthetic paint augmentation helps more, crowdsourced gallery photos of real painted minis help most. Plan for all three in sequence.

## 10. Reframing: the product is a reference gallery

Internalize this. The model is commodity — swap DINOv3 for whatever comes next every 18 months. What compounds in value is the curated, taxonomised, community-grown database of canonical photos per unit. Every competitor would have to rebuild that from scratch.

Think of this project less as *"training a YOLO"* and more as *"building Lexicanum's image arm with a CV interface on top."* The modelling choices follow from that framing.

---

## Status (living)

Update this section as phases complete. Date every entry.

| Phase | Status | Notes | Last update |
|---|---|---|---|
| 0 · Baseline reality-check | ✅ Complete | Detection 66.0% / faction-top-1 64% / mAP50 54.7% on val split. [Full report](docs/benchmarks/2026-04-13-phase0-baseline.md) | 2026-04-13 |
| 1 · Prototype Tier 1+3 | ✅ Complete | OWLv2 detection recall 83.3% (+17pp); DINOv2 retrieval unit top-5 83.3%, top-1 66.7%, MRR 0.72 on 6 queries. Both exit criteria met. [Full report](docs/benchmarks/2026-04-13-phase1-prototype.md) | 2026-04-13 |
| 2 · Tier 2 + gallery expand | ✅ Complete (unscoped path) | Unscoped top-3 = 84.6% (passes 70% bar). Tier 2 KNN-vote + confidence-gating swept 0.3→0.7; best gated top-3 = 76.9%, still below unscoped. Production ships unscoped; Tier 2 deferred to a future linear-probe experiment. [Full report](docs/benchmarks/2026-04-14-phase2-scoped.md) | 2026-04-14 |
| 3a · Gallery expansion from existing corpus | 🟠 Partial pass | Breadth met (23 factions, 51 queries — 3.9× Phase 2); unit top-3 regressed to 74.5% (Wilson LB 61.1%) because 78% of gallery units have depth=1. Tier 2 KNN-vote flatlined at 54.9%, confirming Phase 2.5's dead-end verdict. [Full report](docs/benchmarks/2026-04-15-phase3a-corpus-expansion.md) | 2026-04-15 |
| 3a.1 · Depth-focused labelling | ☐ Not started | Lift the 109 singleton gallery units to ≥ 3 crops each from the already-annotated corpus. Cheapest path to clearing the 80% top-3 bar. | — |
| 3b · Synthetic data pilot | ☐ Not started | BlenderProc on 20 units from Cults3D. Runs only after 3a.1 exposes which units the corpus can't cover. | — |
| 4 · Consumer feedback loop | ☐ Not started | Ship + VLM fallback | — |
| 5 · DINOv3 domain adaptation | ☐ Deferred | After Phase 4 shows domain-gap pain | — |
| A · Library foundation (refactor) | ✅ Complete | `src/photoanalyzer/` package scaffolded (taxonomy + label schema v2 + scene-eval skeleton + 53 tests green). Legacy `scripts/phase{1,3}/labels.csv` unified into `data/labels.csv` (3748 rows, 92.2% labelled, v2 schema). See [plan](../.claude/plans/okay-this-shows-there-joyful-lark.md). | 2026-04-17 |
| B · Labelling infrastructure + depth push | ☐ Not started | Weak supervision + CMON crop extraction + active-learning queue + keyboard-first batch UI. Subsumes phase 3a.1. | — |
| C · Frozen scene benchmark | 🟡 In progress | 200-image frozen eval set stratified by bbox density (60 single / 50 sparse / 50 medium / 40 crowded). Never trained on. See §3.1 step 1 and `data/scene_benchmark/eval_200.json`. | 2026-04-20 |
| D · Model improvements to ≥95% top-3 | ☐ Not started | D1 linear probe Tier 2, D2 class balancing, D3 multi-view grouping, D4 backbone ablation. Tier 3 / retrieval sub-phases. Gated on Phase C scoreboard. Tier 1 detector work split out into Phase F. | — |
| E · Consumer app shipping | ☐ Not started | FastAPI server + PWA wire-up + top-3 confirmation UX. | — |
| F · Tier 1 detector bootstrap | 🟡 In progress | **SAM 3 + SAM 2** (ensemble dropped 2026-04-25) → RF-DETR-Medium cloud + RF-DETR-Nano edge. Sub-phases per §3.1 steps 2–5. Scored against **gold_v2** (count-MAE × density + per-faction recall via `score_gold.py`), NOT the legacy eval_200. | 2026-06-05 |
| F1 · Auto-label 34.7k scraped images | 🟡 Pipeline + measuring infra ready | Ensemble simplified to **SAM 3 + SAM 2** after Phase C bench (3× alternatives). **2026-06-05:** gold expanded to 89/283 (all v1 factions ≥40); built the trusted-GT eval harness (`eval/gold.py` count-MAE×density + per-faction recall + box-convention diagnostic), box reconciliation (`eval/boxconv.py`), CLI `scripts/phaseF/score_gold.py`, and a detection-pool junk filter (1,463 `lowq` tagged). Score against **gold_v2** (trusted), not eval_200 (legacy GT). SAM 3 prompt/threshold + base-pad decisions locked — see HANDOFF §5.1. Blocks on GPU run (Colab). | 2026-06-05 |
| F2 · Train RF-DETR v1 | ☐ Not started | 1.5k gold (5–10× oversampled) + ~15.6k pseudo. Expected mAP@50 0.70–0.78 on frozen eval. Blocks on F1. | — |
| F3 · Self-relabel + human review | ☐ Not started | RF-DETR v1 at conf 0.3; disagreement set (~500–1.5k images) goes into the desktop annotator. ~5–12 human-hours. Blocks on F2. | — |
| F4 · Train RF-DETR v2 + Nano | ☐ Not started | Cloud quality-max + edge mobile variant, same cleaned dataset. Target mAP@50 0.82–0.88. Blocks on F3. | — |

### Phase 0 headline findings

The baseline split confirmed the strategic thesis:

- **Detection is the strong link** (66% recall, 76% precision @ IoU 0.5). Keep it.
- **Classification is the weak link** (64% top-1 on matched), and **highly bimodal per class** — some classes are near-solved (tyranids 100%, adeptus_mechanicus 89%) while others are effectively hallucinated (death_guard 2.4% class precision, chaos_space_marines 5.3%). Retrieval-based classification should move the bottom more than the top.
- **The "39.9% mAP50" number in SPEC.md was actually mAP50-95.** Real mAP50 on the same val split is 54.7%. The stricter mAP50-95 is 39.1%. SPEC.md corrected alongside this phase.
- **Unit-level KPIs are N/A.** Not a model failure — a corpus limitation. Annotations are faction-only, so top-1 / top-3 unit accuracy literally cannot be measured against current ground truth. Tier 3 retrieval evaluates against the reference gallery instead and does not require unit annotations.

### Phase 3a headline findings

On 51 queries (3.9× Phase 2) against a 274-crop, 23-faction gallery drawn from the full annotation corpus:

- **Breadth target met, accuracy target missed.** All 14 previously-uncovered factions now have gallery + query coverage. Unscoped top-3 = 74.5% (Wilson 61.1–84.5%) — regressed from Phase 2's 84.6% on 13 queries, but the 61.1% lower bound is *tighter* than Phase 2's 57.8%. The headline is more honest, not worse.
- **Depth=1 is the single biggest failure mode.** 109 of 139 gallery units (78%) have only one reference crop. Every named retrieval failure (rank > 5) is a singleton unit. Retrieval cannot generalise off a lone exemplar when paint schemes vary.
- **Tier 2 KNN-vote flatlined at 54.9%** (vs Phase 2's 53.8%) despite 3.4× more gallery data. Confirms Phase 2.5's conclusion: the problem is not volume, it's that DINOv2 embeddings don't cluster linearly by faction under majority vote. Linear probe remains the cheapest next experiment if Tier 2 is revisited.
- **Phase 0's crisis classes recovered.** CSM 100%, death_guard 100%, genestealer_cult 50% unscoped top-3. The retrieval architecture *does* rescue the YOLO-bad classes — the residual problem is gallery depth, not embedding discrimination. This is the Phase 1 hypothesis holding at larger scale.
- **Scoped_oracle dropped 100% → 92.2%.** Within-faction discrimination is still strong at the larger scale; the 5.9 pp ceiling gap is the cost of adding the long tail.
- **Strategic decision.** Treat Phase 3a as a partial pass: ship what we have, then run Phase 3a.1 (depth-focused labelling — bring every query unit to ≥ 3 crops from the already-annotated corpus) before considering synthetic data (Phase 3b). The lever is known; only labelling hours are required.

### Phase 2 headline findings

On 13 queries against an 80-image gallery (labels hand-curated + normalised from 93 Sinan labels):

- **Unscoped retrieval top-3 = 84.6% (CI 57.8–95.7%)** — passes the Phase 2 exit bar at point estimate; Wilson lower bound is below 70%, so the *direction* is confirmed but tighter measurement is needed. Unscoped MRR climbed from Phase 1's 0.72 → 0.84.
- **Tier 2 KNN-vote = 53.8% faction top-1** — far below the 90% exit bar. When Tier 2 is right (7/13), scoped retrieval is perfect (100%). When it's wrong (6/13), scoped retrieval is 0% by construction. `scoped_actual` flatlines at exactly the Tier 2 accuracy.
- **Confidence gating does not rescue scoping.** Swept gate thresholds 0.3–0.7; the best (0.6–0.7) still under-performs unscoped by 7.7 pp on top-3 (76.9% vs 84.6%). Tier 2's confidence signal is too noisy — confidently-wrong predictions still regress results.
- **Scoped oracle = 100% across top-1/3/5**. Within-faction discrimination is fully solved at this gallery size. The cross-faction confusions Phase 1 flagged (aberrants vs deathshroud_terminators) resolved *purely by gallery depth*.
- **Strategic decision.** Ship unscoped retrieval as the production Tier 3. Tier 2 as drawn in §3 is deferred — not cancelled. When attempted again, the viable paths are (a) linear probe on DINOv2 embeddings with gallery faction labels, or (b) a crops-specific YOLO retrain. KNN-vote is a dead end.
- **Gallery depth keeps paying off.** Biggest single lift between Phase 1 and Phase 2 came from 2× crops per unit (+18 pp top-5). This directly predicts Phase 3's synthetic-data expansion will continue to move the needle.

### Phase 1 headline findings

The retrieval prototype hit both exit criteria on a 24-image gallery + 6 query eval:

- **OWLv2 detection recall 83.3% (+17.3 pp over YOLO)** with zero training. Precision 0.6% at score threshold 0.1 — tuning, not fundamental.
- **DINOv2-base retrieval top-5 83.3%, top-1 66.7%, MRR 0.722.** DINOv3 was gated on HuggingFace and was not used — the fallback is already above the bar.
- **Retrieval inverted the difficulty pattern.** The YOLO-problem block (CSM, DG, GSC; Phase 0 faction top-1 7–14%) produced 4/4 top-5 and 3/4 top-1. The YOLO-easy block (tyranids 100%, SM 100% in Phase 0) lost its only query — a termagants crop that had just one gallery example. **Gallery depth matters more than breadth** at this scale.
- **"Unknown" threshold 0.812** — sim@FPR=10%. Correct matches land at 0.81–0.94 similarity; the one total failure bottoms at 0.62. The threshold is clean and usable for Phase 4's "I don't recognise this" calibration.
- **Sample size caveat**: 6 queries is small. Wilson 95% CIs are wide (~±30 pp). Phase 2 should rerun with ≥30 queries once the gallery expands.

All of this aligns with — and strengthens — the three-tier architecture in §3. No direction change is warranted; Phase 2 proceeds as planned.

## Source list

Full links in [docs/STRATEGY_SOURCES.md](docs/STRATEGY_SOURCES.md).
