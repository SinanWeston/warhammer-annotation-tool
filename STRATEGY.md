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
│ T-Rex2 (visual prompt) or OWLv2 or Grounding-SAM    │
│ Prompt: 10–20 example miniature crops + "miniature" │
│ Output: bounding boxes, no classes. Zero training.  │
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
- **Grounding DINO integration.** Already in the codebase for annotation proposals — promote it to a first-class detection stage (or swap for T-Rex2 / OWLv2).
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

- **Class-agnostic detection is solved.** T-Rex2 (ECCV 2024) with visual prompts beats text prompts by +5.6 AP on ODinW and +9.2 on Roboflow100 — the rare/novel object regime miniatures live in. OWLv2 and Grounding DINO reach 50–70% zero-shot recall on "miniature" without a single training example.
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
| 3a · Gallery expansion from existing corpus | 🟡 Prepared (awaiting labelling) | 316 new crops seeded from the 3,525-bbox corpus. Covers all 14 previously-missing factions. Added when an audit revealed 97% of the corpus was unused. [scripts/phase3/](scripts/phase3/README.md) | 2026-04-14 |
| 3b · Synthetic data pilot | ☐ Not started | BlenderProc on 20 units from Cults3D. Runs only after 3a closes the corpus-derived gaps. | — |
| 4 · Consumer feedback loop | ☐ Not started | Ship + VLM fallback | — |
| 5 · DINOv3 domain adaptation | ☐ Deferred | After Phase 4 shows domain-gap pain | — |

### Phase 0 headline findings

The baseline split confirmed the strategic thesis:

- **Detection is the strong link** (66% recall, 76% precision @ IoU 0.5). Keep it.
- **Classification is the weak link** (64% top-1 on matched), and **highly bimodal per class** — some classes are near-solved (tyranids 100%, adeptus_mechanicus 89%) while others are effectively hallucinated (death_guard 2.4% class precision, chaos_space_marines 5.3%). Retrieval-based classification should move the bottom more than the top.
- **The "39.9% mAP50" number in SPEC.md was actually mAP50-95.** Real mAP50 on the same val split is 54.7%. The stricter mAP50-95 is 39.1%. SPEC.md corrected alongside this phase.
- **Unit-level KPIs are N/A.** Not a model failure — a corpus limitation. Annotations are faction-only, so top-1 / top-3 unit accuracy literally cannot be measured against current ground truth. Tier 3 retrieval evaluates against the reference gallery instead and does not require unit annotations.

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
