# Annotation guide — Phase F detector bootstrap

**What you're doing:** reviewing auto-generated bounding boxes on
painted-mini photos so we can fine-tune a detector that actually ships.
Every box you confirm, correct, or delete becomes a training example.
Getting ~500 right is worth more than getting 5,000 half-right.

**Target:** an RF-DETR detector at mAP@50 ≥ 0.82 on the frozen 200-image
eval set. Current pseudo-labels sit at roughly 0.55 quality; your review
is what closes that gap.

---

## 1. Priority — what to spend time on

Work in this order when the queue gives you a choice:

1. **Crowded scenes (4+ minis).** This is the user-facing distribution.
   Someone photographing their painted army has 10–50 models on a
   table. DETR-family detectors specifically underperform on crowds vs
   single-object regimes ([Lin et al. 2020, DETR for Crowd Pedestrian
   Detection](https://arxiv.org/abs/2012.06785);
   [CrowdHuman](https://arxiv.org/abs/1805.00123)), so crowd-labelled
   data is the scarce resource that moves the target metric.
   **Highest value.**
2. **Medium scenes (2–3 minis).** Typical hobby shots, painter-blog
   photos, small skirmish games.
3. **Single-mini shots.** Clean silhouettes anchor the detector's "what
   is a miniature" concept, so don't ignore them — but we already have
   GW studio + eBay product listings in volume. 10–15 seconds each,
   not minutes.
4. **Edge cases** — unusual angles, dioramas, non-standard bases,
   experimental paint schemes. Do them last; they're rare in the
   test distribution but enrich the training set.

**Target mix across the whole labelled set: ~60–70% crowd scenes
(4+ minis), ~25% singles, rest medium.** This is an informed
extrapolation from the CrowdHuman gap evidence; no paper pins an
exact ratio for DETR, so revisit after the Phase F2 eval.

When you see a queue of pseudo-labels, **don't work through them in
order** — skim-scroll for crowd shots first. Keyboard `N` advances;
`P` goes back if you skim past something.

---

## 2. How to draw a good bbox

**One box per distinct miniature.** Never boxes around parts (weapons,
heads, shoulder pads) — the detector has to learn "mini = whole
figure including base," not "mini = shoulder pad."

### Tight, not loose

Hug the silhouette. Include:
- ✅ The **base** (the round / oval slotted disc). The base is part of
  the mini and the detector needs it to learn scale and orientation.
- ✅ Any weapons, banners, or wings the mini is holding or mounted on.
- ✅ The **flying stand** for jet-pack / bike / flying minis. It's a
  structural part of the model.
- ✅ Vehicle + crew as **one** box when the crew model is glued to the
  vehicle (Ork warbosses on bikes, Tau commanders in battlesuits).

Exclude:
- ❌ Terrain the mini is standing on (rocks, ruins, grass mat) that's
  not on the base itself.
- ❌ Adjacent bases of other minis. If two bases are touching, each
  mini gets its own tight box — even if their boxes overlap slightly.
- ❌ Shadows. A long cast shadow is not part of the mini.

**Tightness target: visually tight, not pixel-tight.** Hug the
silhouette as a human would expect. A few pixels of slack around
fiddly parts (bayonets, antennae, banner tips) is fine; 10+ pixels of
consistent padding is not. The GIoU+L1 loss DETR uses tolerates a few
pixels of slop (a CVPR-W 2022 study found 66% of COCO annotations
fail a ±2 px consistency test, yet detectors still hit their
reported mAPs). Prioritise **annotating more images** over
pixel-perfection on fewer. Roboflow's RF-DETR labelling guide
explicitly says "tight around the object" without specifying a pixel
tolerance; PASCAL VOC's rule is "all visible pixels except where the
box would have to be excessively large to include a few extras."

### Formation rules

- **Squad in close formation** (e.g. 10 Intercessors shoulder-to-shoulder
  on a movement tray) → **separate boxes for each mini.** Even if their
  bases touch and their boxes overlap significantly due to posed arms
  and weapons. DETR's one-to-one Hungarian matching actively *prefers*
  overlapping distinct boxes over merged ones — merging 10 minis into
  one box means 9 queries get unmatched and the model is trained to
  produce low-IoU enclosing boxes (the opposite of what we want).
  This is also the COCO convention:
  [iscrowd=0 boxes overlap freely](https://cocodataset.org/#format-data),
  and the [COCO-Crowd curation effort](https://sites.google.com/view/coco-crowd/home)
  exists specifically because COCO under-represents overlap.
- **Single model glued together** (rider + bike, Tau battlesuit) → **one
  box** around the full unit. These are one physical model in the kit.
- **Model + weapon platform carried by model** (Space Marine with
  missile launcher) → **one box.** The launcher is part of the mini.
- **Squad leader carrying a banner that extends above the squad** →
  include the full banner in the leader's box. Banner tip counts.
- **Chariots / bike squads / cavalry** — each rider+mount+chariot is
  ONE model, one box.

### Partially occluded minis

- **<50% occluded** (one mini peeking from behind another) → draw a
  tight box around the **visible portion only**. Don't guess the
  hidden silhouette.
- **>50% occluded** → skip it. Better no label than a guessed one.
- **Only the base is visible** (mini is a back-rank model behind a
  front rank) → skip. The detector would learn "mini = disc-shaped
  base" which is wrong.
- **Rear-rank ceiling on massive crowds:** when 20+ rear-rank minis
  are visible only as partial shoulders/heads behind a front rank,
  stop drawing on them and move on. You can't build a reliable label
  from 50%-guessed silhouettes, and the front rank is doing the
  training work anyway.

---

## 3. Resolution & quality triage

Before you draw anything, decide if the image is worth annotating:

| Long edge | What to do |
|---|---|
| **≥ 1600 px** | Full annotation. Zoom in (`+` / scroll-wheel) to get tight boxes on small minis. |
| **800–1600 px** | Full annotation. Bboxes don't need to be pixel-perfect; within ~3 px is fine. |
| **400–800 px** | Annotate if individual minis are clearly resolvable; otherwise skip. |
| **< 400 px** | Skip. The detector can't learn from 20×40-pixel miniatures. |

**Focus / blur check.** If the front-rank minis are out of focus, skip
unless the image is otherwise unique. Motion-blurred miniatures teach
the detector to fire on blur artefacts.

**Lighting check.** Deep shadow photos (backlit, underexposed) → skip
unless crowd value is high. Wash-out / overexposed → skip.

**Diorama vs tabletop.** Both are fine to annotate. Painted terrain is
not a mini; don't box it.

---

## 4. What to SKIP entirely

Flag these with the Skip (`X`) keybind — they get a `.skip.json`
sidecar and permanently leave the queue:

- **Sprues** — unpainted plastic parts still on the frame.
- **Primer-only WIPs** — grey / black / zenithal prime, no colour. The
  detector will later be used on fully painted armies; primed minis are
  a different distribution and confuse the signal.
- **Box art / rulebook illustrations** — not actual minis, they're
  drawings or CGI renders. Easy to spot: studio background, perfect
  lighting, fantastical pose, explosion-and-smoke backdrop.
- **Product packaging photos** (GW box with the box-art illustration
  on its front) — the illustration is not a real mini. SKIP the whole
  photo unless it also contains a real assembled mini.
- **Mini + packaging in one frame** — if the photo shows BOTH a real
  assembled mini and the box it came in, box **only the real mini**.
  Do not draw a box around the illustration on the packaging.
- **In-store shelf photos** with stacks of product boxes — SKIP. Those
  are shelves, not minis.
- **Duplicates / near-duplicates** — if you just annotated the same
  photo from a different angle or crop, skip the duplicate.
- **Memes / jokes / non-mini content** — someone's cat next to a
  Dreadnought is a skip.
- **Screenshots** from Total War / Dawn of War / tabletop simulator —
  digital models, wrong distribution.

---

## 5. Reviewing pseudo-labels (Phase F1-specific)

You're in the **Pseudo-labelled** queue. Each image was auto-labelled
by Grounding DINO; your job is to **correct, not re-label from
scratch**.

### Typical correction patterns

1. **Confirm & move on** (~60% of single-model shots, ~40% of crowds).
   Boxes look right → press `S` to save, `N` for next.

2. **Part-of-model duplicates on single-model shots** — common failure.
   You'll see a tight box around the whole mini AND a smaller box
   around its weapon or helmet. Delete the smaller box (click-select,
   `Delete`). Keep the whole-model box.

3. **Boxes that wrap multiple minis as one** — common in dense crowds.
   Delete the wrapper, draw individual boxes for each mini inside.

4. **Missed minis** — empty areas where a mini clearly exists but has
   no box. Draw in.

5. **Shifted/loose boxes** — right mini, wrong bounds. Drag the
   corners to tighten.

### When to redraw from scratch vs fix existing

If **>50% of the boxes on an image are wrong**, select all (`Ctrl+A`),
`Delete`, and redraw from scratch — it's faster than individual fixes.

If **<50% are wrong**, fix individually.

### Classification note

Tier 1 (what we're training) is **class-agnostic** — just "is there a
mini here?" So the `classLabel` on each bbox doesn't matter for F2
training. Leave it as the image's default faction. You can ignore
unit_slug entirely for this pass.

### Saving

Saving (`S`) clears the `pseudoLabelled` flag → the image leaves the
Pseudo queue. Don't save if you want to come back to the image later;
use `K` (Skip for now) instead to park it.

---

## 6. Rhythm & sustainability

Aim for **20–40 images per focused hour**. Pseudo-labels with only
minor fixes: 30 seconds each. Full redraws on a 30-mini crowd shot:
2–3 minutes.

**Breaks matter.** Eye fatigue causes sloppy boxes, which train a
sloppy detector. 50 minutes on, 10 minutes off.

**Audit yourself.** Every ~50 images, scroll back through the last 10
you saved. If two or more look wrong with fresh eyes, you were in the
fatigue zone — take a longer break.

---

## 7. Red flags — tell the team

If you notice any of these patterns, flag them in chat — they usually
mean a prompt / threshold needs adjustment upstream, not that you
should correct them one at a time:

- **>30% of single-model shots have part-of-model duplicates.** Prompt
  or SAHI threshold is wrong.
- **Most boxes are at the minimum score threshold (0.25).** Need to
  bump threshold up.
- **Systematic mis-detection of a specific faction** (e.g. Tyranids
  always under-detected because organic shapes). Prompt may need to
  be faction-aware.
- **Multiple source images look identical** — scraper may have
  deduplicated badly.

---

## 8. Reference — keyboard shortcuts

| Key | Action |
|---|---|
| `S` | Save annotation (clears pseudo flag) |
| `K` | Skip for now (stays in queue, comes back later) |
| `X` | Flag image as unusable (`.skip.json`) |
| `N` / `P` | Next / Previous |
| `B` | Back to last image |
| `Delete` | Delete selected bbox |
| `+` / `-` | Zoom in / out |
| `Ctrl+Z` / `Ctrl+Shift+Z` | Undo / Redo |
| `Ctrl+A` | Select all bboxes (for mass-delete) |

---

Last updated: 2026-04-21 (Phase F1 active). Update this file when the
detector changes, when a failure mode is added, or when the workflow
evolves.
