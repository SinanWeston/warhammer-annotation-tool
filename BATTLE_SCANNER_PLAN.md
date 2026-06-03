# Battle Scanner — Build Plan v1

**Goal (locked):** From a single photo of a tabletop of painted Warhammer 40K miniatures, report how many models are present, which faction(s) they belong to, and the specific unit each model is — then assemble a structured army list with per-unit counts and points totals that can be exported or shared. Must hold up under real conditions: varied paint schemes, clustered/occluding models, and an open, growing set of ~900+ units — recognising what it knows with calibrated confidence and flagging what it doesn't, rather than guessing. End form factor: a phone app.

---

## 0. The one idea that drives the whole plan

**What the best do (data-centric AI).** In 2026 the models are commodities. RF-DETR, DINOv3, and SAM 3 are open, SOTA, and frozen/off-the-shelf. The differentiator between a working CV product and a dead one is *data quality, curation, and evaluation* — not novel modelling. Serious teams spend ~80% of effort on the dataset and the eval harness and ~20% plugging into foundation models. Nobody trains a backbone anymore for a problem like this.

**How we apply it.** You already converged on the correct architecture (detect → faction → retrieve → optional VLM). So there is no research risk left to retire — every phase below is "get the right data into the right frozen model and measure it honestly." This is also the direct correction to v0: you built infrastructure and trained from scratch; the new default is *survey → plug into frozen foundation models → curate data → measure.*

---

## 1. The stack (decide once, then stop touching it)

| Layer | Tool | Why | License / cost |
|---|---|---|---|
| **Dataset hub / curation / QA / eval** | **FiftyOne (Voxel51)** | The tool serious CV teams use to explore, dedup, find label errors, slice metrics, and evaluate. Integrates SAM 3, CVAT, and embeddings natively. This is your home base. | OSS, free |
| **Auto-labeling (Tier 1)** | **SAM 3** + **Autodistill** | SAM 3 does promptable concept segmentation: prompt "miniature" → masks + boxes for every instance. Autodistill orchestrates base→target distillation as a library. | OSS, free (compute only) |
| **Annotation / review UI** | **Roboflow** (managed) or **CVAT** (self-host) | Roboflow = Label Assist + Auto Label + RF-DETR training + deploy SDK in one place (fastest for solo). CVAT = free/self-hosted with SAM integration. | Roboflow: free tier→paid; CVAT: OSS |
| **Detector (Tier 1)** | **RF-DETR** (Medium=cloud, Nano=edge) | Apache-2.0, DINOv2 backbone, NMS-free → cleaner counts and fewer false positives in dense scenes; generalises across domains better than YOLO. | OSS, Apache-2.0 |
| └ edge fallback | **YOLO26-n** | NMS-free, edge-optimised, faster CPU; use only if RF-DETR-Nano won't hit your on-device latency budget. | OSS |
| **Embeddings (Tier 2/3)** | **DINOv3** (ViT-L cloud, ConvNeXt/ViT-S edge) | Frozen backbone, commercial license, SOTA fine-grained classification and k-NN retrieval. Optionally ensemble with **SigLIP 2**. | Commercial-OK |
| **Vector index** | **FAISS** | Fast cosine k-NN over the reference gallery, indexed per faction. | OSS |
| **Disambiguator (Tier 4)** | **Claude / Gemini** (VLM) | Verifier on a 3-candidate shortlist, not a primary classifier. Fires only on low-confidence cases. | API, pay-per-call |
| **Experiment tracking** | **Weights & Biases** | Track every training run, dataset version, and eval. | Free tier |
| **Data versioning** | FiftyOne datasets + **DVC** (or Roboflow versions) | Reproducible dataset snapshots tied to results. | OSS / free |
| **Compute** | **Colab Pro / cloud GPU** | You already use Colab; keep it. | low |
| **Points / rules data** | catalog source (swappable) | Needed for the army-list layer. **IP/licensing caveat — see §8.** | TBD |

**Hard rules**
- **Kill the bespoke annotator apps** (desktop + mobile + Express backend). They rebuild solved infrastructure. *Keep* the taxonomy module, the image assets, and the consumer UI (reused at the very end).
- **Never hardcode faction/unit strings** — keep importing from the taxonomy module. (You already do this; preserve it.)
- One spine, named above. CVAT/Lightly/SigLIP2 are listed as *alternatives*, not additions — don't run five tools where two will do.

---

## 2. Lock v1 scope: narrow, end-to-end, then widen

**What the best do.** Ship a vertical slice first. Prove the entire pipeline on a small set, get a real number on real inputs, then scale breadth. Breadth is a labeling/data-collection problem you scale *after* the loop works, not a thing you solve up front.

**How we apply it.** v1 supports **3–5 factions**, chosen by (a) visual separability, (b) data availability in your corpus, (c) popularity. A reasonable starting set (edit freely): **Space Marines + Necrons + Tyranids** (and maybe Death Guard for a "hard, samey" faction to stress retrieval). Get count + faction + unit + army-list working on these. **Do not touch the ~900-unit long tail until the loop is proven** on the narrow set.

**Exit criteria:** an end-to-end demo on the narrow faction set that hits target metrics on a *frozen, realistic* eval set.

---

## 3. Write the labeling guideline + gold set (half a day, saves months)

**What the best do.** Every serious labeling operation starts with a written guideline, edge-case rules, and a small gold-standard set — *even with one labeler.* This is what makes "annotation quality" a measurable number instead of a vibe, and it's what prevents label drift over months (your unwritten v0 risk).

**How we apply it.** Produce `LABELING_GUIDE.md` defining precisely:
- **What a "miniature" box/mask is** — one box per physical model; base included or not (pick one, document it); model-only vs model+base.
- **Occlusion rule** — label partially-hidden models down to what % visible? (e.g., ≥30%).
- **Unit grouping** — N models of the same unit → one army-list entry; how to decide unit boundaries.
- **Naming** — always from the taxonomy module; no freetext.
- **Unknown/ambiguous** — explicit handling so it's labeled consistently.

Then hand-label a **50-image gold set** spanning your factions and difficulty levels. Keep it forever as the QA reference that every pseudo-labeling and model run is measured against.

---

## 4. Phase D1 — Curate the image pile (FiftyOne-led)

"We have a shitload of images" means the first job is turning a *pile* into a *designed dataset.*

**What the best do.** Dedup, filter junk, and *select what to label by diversity/uncertainty* (embedding-based) — never random. Scraped corpora are full of near-duplicates; random labeling burns hours re-labeling the same model.

**How we apply it.**
1. Ingest **all** images into a FiftyOne dataset; tag by source (eBay/Reddit/DakkaDakka/CMON/GW) and folder-faction as **weak labels**.
2. Compute DINOv3 (or CLIP) embeddings → visualise with UMAP → **remove near-duplicates** and **junk** (boxes, sprues, terrain-only, blurry, non-miniature).
3. Use FiftyOne **uniqueness/representativeness** (or Lightly) to pick a **diverse labeling pool**, not a random sample.
4. **Split by role, not just train/val:**
   - **Detection pool** — cluttered, multi-mini, realistic scenes → Tier 1 training.
   - **Gallery pool** — clean single-mini shots → Tier 3 reference crops.
   - **Eval / holdout** — frozen, as phone-/tabletop-like as possible; **never trained on.**
5. **Close the train/serve gap now.** Your corpus is studio/marketing/listing shots; deployment is cluttered phone photos from above in household lighting. Start collecting **50–100 real tabletop photos** for the eval set immediately — you model and paint 40K, so shoot your own table from realistic angles. This is the highest-signal data you can produce and it costs you an afternoon.

**Exit:** a clean, deduped, role-split FiftyOne dataset with weak faction tags + a frozen realistic eval set.

---

## 5. Phase D2 — Tier 1 detector: auto-label → distill → active-learn

Here "assume no good annotations" is an *advantage*: you barely hand-label anything.

**What the best do.** Bootstrap labels with a foundation model, human-review a sample, distill into a fast specialist, then close the loop with active learning. (Autodistill pattern; SAM 3 collapses the labeling step to a single prompt.)

**How we apply it.**
1. **Auto-label with SAM 3** on the detection pool. Concept prompts: `"miniature"`, `"tabletop wargame figure"`, `"warhammer model"`; add a few **image exemplars** (positive/negative boxes) to recover missed/rare cases. Single `miniature` class → high-quality pseudo-labels (boxes + masks).
2. **QA in FiftyOne.** Review a stratified ~200-image sample, fix systematic errors (merging touching models, base-only boxes), and **measure pseudo-label precision/recall vs the gold set.** Adjust prompt/exemplars; re-run. Don't proceed until pseudo-label quality is high.
3. **Distill into RF-DETR-Medium** (via Autodistill or Roboflow training). NMS-free → cleaner counts in dense scenes; transformer backbone → fewer ghost detections than YOLO.
4. **Active-learning loop.** Run RF-DETR over more of the corpus; in FiftyOne surface **low-confidence / crowded / high-disagreement** scenes; hand-correct **only those** (this is where your small budget of real labeling hours goes); retrain. Repeat until detection recall plateaus on the frozen eval.
5. **Occlusion/clustering** (the genuinely hard part): deliberately include dense overlapping scenes, lean on SAM 3's instance separation + RF-DETR's low false-positive rate, and **evaluate count error specifically on crowded scenes** (not just overall mAP).

Illustrative distill snippet (Autodistill; SAM 3 base, RF-DETR target):
```python
from autodistill.detection import CaptionOntology
# base model = SAM 3 / Grounded-SAM with the "miniature" concept
base_model.label(input_folder="./detection_pool", output_folder="./tier1_dataset")
# then train RF-DETR on ./tier1_dataset (Roboflow or rfdetr package)
```

**Exit:** detection recall ≥ ~0.90 on the frozen eval; count error within ±1 on typical scenes.

---

## 6. Phase D3 — Tier 2/3: faction + unit (the core — retrieval)

**Design refinement worth making explicit:** fold faction into retrieval instead of running a separate hard classifier. The retrieved unit *implies* its faction; faction is best used as a *prior that scopes the retrieval index*, not as an independent decision.

**What the best do.** For open-set, fine-grained, long-tail recognition: **frozen embeddings + k-NN against a reference gallery**, with unknown-rejection by distance/margin. Never a 900-way softmax (that's the v0 dead-end). DINOv3 k-NN on frozen features is SOTA fine-grained — this is precisely the published precedent (TCG scanners, iNaturalist) you cited.

**How we apply it.**
1. **Crops.** Auto-crop every detected mini (Tier 1) across the gallery pool; assign faction from weak labels + a light **DINOv3 linear-probe faction classifier** (used only as a scoping prior); confirm a sample in FiftyOne.
2. **Gallery depth is THE lever** — this is what killed v0 (78% of units had 1 crop → top-3 regressed to 74.5%). Set a **hard floor of ≥3–5 reference crops per supported unit**, spanning paint schemes and angles. Source from corpus crops + GW official multi-angle photos. **No unit ships with a single crop.**
3. **Embed** the gallery with frozen **DINOv3 (ViT-L)**; build a **FAISS** index **per faction**. Optionally ensemble with **SigLIP 2** (average or rank-fuse the two similarity scores).
4. **Retrieve.** Query crop → faction prior scopes the index → cosine k-NN → **top-3 units + confidence.** Faction = faction of the top results.
5. **Open-set rejection + calibration.** Threshold on top-1 distance **and** the top1–top2 margin → return **"unknown"** when below threshold. Calibrate thresholds on the eval set with a reliability diagram. *This is the mechanism that lets it honestly say "I don't recognise this"* — a hard requirement of the goal.
6. **Paint invariance** (the crux of the domain):
   - **Short-term:** multiple gallery crops across schemes + test-time augmentation.
   - **Long-term (deferred until real data exists):** metric-learn / lightly fine-tune the embeddings using **same-unit-different-paint positive pairs**. **Design your labels now to capture unit identity** so you can build those pairs later without re-labeling.

Illustrative retrieval core:
```python
# frozen DINOv3 embedding -> per-faction FAISS index
q = dinov3_embed(crop)                 # L2-normalised vector
D, I = faction_index[faction].search(q, k=3)
top1, margin = D[0], D[0] - D[1]
unit = "unknown" if (top1 < TAU or margin < DELTA) else gallery_labels[I[0]]
```

**Exit:** top-3 unit accuracy ≥ ~0.90 on supported units; calibrated unknown-rejection working on out-of-set inputs.

---

## 7. Phase D4 — Tier 4 VLM disambiguation (cheap, high-leverage)

**What the best do.** Use a VLM as a **verifier on a shortlist**, not a primary classifier. VLMs are weak at open-set 900-way recognition but strong at *"is this A, B, or C — or none — and why?"*

**How we apply it.** When top-1 retrieval confidence < threshold, send the crop + the **top-3 candidate reference images + names** to Claude/Gemini with a structured "pick one or none, with reasoning" prompt → calibrated decision. Fires only on hard cases → cost-controlled. **Log every VLM call** as future training/eval data (these are exactly your hardest, most valuable examples).

**Exit:** measurable accuracy lift on the low-confidence slice; cost per scan within budget.

---

## 8. Phase D5 — Aggregation → army list + points (reuse your existing UI)

- Detections → units → group models into unit entries → counts.
- **Points** require a catalog source, and GW points change with rules updates. **IP/licensing caveat:** community datasets (BattleScribe-/Wahapedia-style) carry their own licensing terms, and the points/rules data itself is GW IP. Keep this layer **swappable** and resolve sourcing before any public launch (see also the broader IP question from the last review — training data + recognising GW's trademarked IP in a commercial app).
- Output: structured list + PDF/text/shareable URL — **you already built this.** Swap the mock scanner for the real pipeline (your "single function swap"). This is the one place v0 effort pays off directly.

---

## 9. Evaluation & QA (the discipline that makes everything else real)

**What the best do.** A frozen golden eval set on *real* inputs; **slice-based** metrics; the **end-to-end product metric**, not just per-tier scores; confidence calibration; tracked label quality.

**How we apply it.**
- **The only metric that matters: end-to-end.** Given a tabletop photo, score the *final army list* — count error, faction accuracy, unit top-1/top-3, list-level F1. Optimise this, not isolated tier numbers. (A great detector + great retriever can still produce a bad list.)
- **Slice everything in FiftyOne:** per-faction, per-difficulty (single vs clustered), per-lighting, per-paint-quality. Find the failing slices and **label into them** (active learning, targeted).
- **Keep v0's rigor, fix its scale.** Wilson CIs and dated reports were genuinely good. But 119-/200-image splits gave noise-dominated swings (the 74.5 vs 84.6 wobble was partly sampling). Aim for **≥500 eval images**, more where cheap.
- **Version taxonomy + eval set together** so benchmarks stay comparable across time (v0 mistake: the 2026-04-19 Chaos sub-faction split silently broke comparability).

---

## 10. MLOps / reproducibility (lightweight, solo-appropriate)

- **W&B** for every run. **FiftyOne datasets + DVC** for data versions tied to results. **Colab/cloud GPU** for training. A minimal **model registry** (versioned weights + a manifest of which dataset/eval produced them). One reproducible "rebuild everything from scratch" script so a resume is `git clone` + one command, not archaeology.

---

## 11. Deployment (do **not** optimise edge prematurely)

- **v1 = cloud inference.** RF-DETR-Medium + DINOv3 + FAISS server-side + VLM API. The phone app just calls the API — reuse the consumer app, mock → real.
- **Edge later.** RF-DETR-Nano / YOLO26-n + quantised DINOv3-ConvNeXt embeddings; export ONNX → CoreML/TFLite. Only once real usage justifies on-device latency/privacy work. Premature edge optimisation was a v0-style trap (building for constraints you don't have yet).

---

## 12. Start here — first sprint (this week)

1. **Stand up FiftyOne**; ingest the entire image pile; compute embeddings; dedup + junk-filter.
2. **Write `LABELING_GUIDE.md`** + hand-label the **50-image gold set.**
3. **Lock the v1 faction set** (3–5).
4. **Shoot/collect 50–100 real tabletop photos** → frozen realistic eval set.
5. **SAM 3 prompt experiments** for "miniature" on a few hundred images; eyeball quality and tune prompts/exemplars.

Everything after that follows the phase order: D2 (detector) → D3 (retrieval + gallery depth) → D4 (VLM) → D5 (army list) → scale breadth beyond the v1 factions.

---

### The meta-point

The whole plan substitutes **survey + plug into frozen foundation models + curate data + measure** for **build infrastructure + train from scratch.** Same architecture you already designed — but the effort now goes where it actually moves the metric: gallery depth, realistic eval data, calibration, and honest end-to-end measurement. The hard part was never the engineering. It was pointing the engineering at the right thing.
