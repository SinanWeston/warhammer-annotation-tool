# Labeling Guide — Battle Scanner

**Status:** v1 draft, 2026-06-04. Governs the 50-image gold set and all
pseudo-label QA. Edit freely — this is meant to be argued with, then frozen.

The point of this document (Battle Scanner Plan §3): make "annotation quality" a
*measurable number* instead of a vibe, and prevent label drift over months. Every
SAM 3 pseudo-label run and model eval is scored against a gold set labeled by
**these exact rules**. When a rule is ambiguous, fix the rule here first, then label.

---

## 1. What is a "miniature" box?

**One box per physical model**, i.e. **one box per base.** A box is the tightest
axis-aligned rectangle around the whole physical miniature **including its integral
base**, as far as the model is visible.

- **Axis-aligned boxes only — never rotate.** Boxes must be upright rectangles
  (`[x, y, w, h]`). CVAT lets you rotate a box, but don't: RF-DETR/YOLO and the import
  pipeline expect axis-aligned boxes, and a rotated one loses its angle (or breaks) on
  import. For a diagonal model, accept the empty corners — an upright box with some
  background beats a tilted one.
- **Base included.** Rationale: the base is the most reliably-visible, consistently-
  shaped part in cluttered/occluded scenes — a stable anchor for the detector, and
  the natural unit of counting ("how many bases on the table"). Retrieval crops can
  be tightened to model-only at crop time; the *label* includes the base.
- **One base = one model.** A multi-sculpt single-base swarm (e.g. a Ripper Swarm
  base with three rippers, a Nurglings base) counts as **one model** = one box.
- **Vehicles, monsters, bikes, cavalry** — same rule, one box around the whole hull/
  creature including any integral base or flight stem.
- **Protrusions (spears, lances, banners, guns, tails, wings)** are part of the model
  — include them. The box is the tightest rectangle that still contains *every* part.
  A diagonal spear leaves empty corners in the box — that's **normal and correct**, not
  a reason to crop it off.
  - **Box inflation is fine.** A raised weapon enlarging the box ~1.5–2× (≈half the box
    empty) is normal and expected — detectors handle elongated boxes routinely (think a
    person holding a pole, or a giraffe). Don't trim a solid weapon to reduce empty space.
  - **Only reconsider** a truly extreme case: a hair-thin element (wispy banner pole,
    antenna) that blows the box up to ~3–4×+ and is almost all air. Even then, default to
    including it — trim only if the protrusion is both negligibly thin and enormously long.
  - **Consistency wins:** apply the same call to every weapon across all 50 images.

## 2. Occlusion rule

**Operational rule (a human can't eyeball "30%"):** label it if you can
**confidently tell it's a separate model** *and* place a box around its visible
part. **Skip** only true slivers where you'd be guessing whether it's even a
distinct model. When torn, label it. (Rough mental anchor: ~⅓ visible, but the
judgement above is what governs — not a percentage.)

The box covers only the **visible** extent of an occluded model — do not hallucinate
the hidden part.

**A thin occluder crossing a model does NOT split it.** A sword, banner, gun barrel or
rail passing in front of a model leaves two visible fragments — it's still **one model =
one box** spanning the full visible extent (top fragment through bottom fragment). Never
draw a separate box per fragment; that fabricates extra models and corrupts the count.
The box will overlap the occluding model — that's fine.

**Cut off by the image edge (truncation):** same rule — if a clear, substantial part
of the model is in-frame, box the **visible part, clipped to the image border** (don't
extend past the edge or imagine the hidden part). Skip models reduced to a thin edge sliver.

**Focus / quality floor:** box only models in **reasonable focus** that you can
delineate. **Skip** heavily blurred or out-of-focus background models where the box
would be a guess — including them only makes the eval noisy and unfair (a human can
barely see them, so penalising the model for missing them is meaningless). Apply the
same threshold across all 50 images; **consistency beats catching every faint figure.**

## 3. Faction + unit naming

- **Always from the taxonomy module** (`photoanalyzer.taxonomy`) — canonical faction
  and unit slugs. **No freetext, no folder names.** (Folder-faction labels in the
  corpus are *weak* and noisy: `imperial_guard` vs `astra_militarum`, `eldar` vs
  `aeldari`, loyalist chapters split from `space_marines` — never copy those.)
- **v1 factions only** (locked 2026-06-04): `space_marines`, `necrons`, `tyranids`,
  `death_guard`. Anything outside v1 → `faction = "out_of_scope"` (still box it for
  the detector; don't unit-label it).
- **Set the label *before* drawing.** CVAT reuses the last-used label for every new
  box, so pick the correct faction in the toolbar first — otherwise new boxes silently
  inherit the previous label (e.g. a whole Krieg squad ends up tagged `death_guard`).
- **Faction is required on every box; unit is best-effort.** Always set faction (or
  `unknown`). Set the unit slug **only when you're confident** — labeling a specific
  unit for every model in a 30-model table photo is slow and often impossible, and a
  guessed unit silently corrupts the eval. Confident unit → label it; unsure → leave
  unit `unknown`. This keeps the 50-image gold set achievable in one sitting.

## 4. Unknown / ambiguous (this is a feature, not a failure)

The product must say "I don't recognise this" rather than guess — so the labels must
too.

- **Can box it but can't name the unit** → `faction` if known, `unit = "unknown"`.
- **Can't even tell the faction** → `faction = "unknown"`, `unit = "unknown"`.
- **Kitbash / proxy / 3rd-party model** → label faction by intent if obvious, else
  `unknown`; tag the sample `kitbash`.
- **Never assign a confident unit label to a model you're guessing on.** A wrong
  confident label is worse than an honest `unknown` — it silently corrupts the eval.

## 5. Unit grouping (army-list aggregation layer, NOT the box layer)

Boxes are always per-model. **Grouping happens downstream**, not during boxing:
- N boxes of the same unit type → one army-list entry with `count = N`.
- Use in-game unit-coherency intuition (clustered, same sculpts) only as a tiebreak;
  when models of the same type are clearly separate squads, that's a list-level call
  the aggregation step makes, not the labeler.

## 6. What is NOT a miniature (do not box)

Terrain / scenery, ruins, dice, templates, range rulers, tokens, objective markers,
empty movement trays (box the models *on* the tray, not the tray), painting handles,
sprues, the photographer's hand. If in doubt: is it a *playable model*? If no, skip.

## 7. Gold set composition (the 50 images)

Stratify the 50 across:
- **Factions:** roughly even across the 4 v1 factions (Death Guard will lean on
  detection/scene shots — it has no isolation crops in the corpus).
- **Difficulty:** a deliberate spread of single-model / sparse / medium / crowded
  scenes. Over-sample **crowded** scenes — that's where counting and occlusion
  actually get judged.
- **Realism:** include some real tabletop phone photos once shot (the realistic eval
  matters most — Plan §4.5). Studio/listing shots alone will flatter the numbers.

**Too dense/blurry to enumerate → exclude it, don't partially label.** If a scene has
so many models (or such a blurred back field) that you can't box *every* resolvable
model consistently, drop it from the gold set and swap in a cleaner crowded scene.
Partially labelling it poisons the eval: a detector that correctly finds a model you
skipped gets scored as a false positive. Crowded scenes are wanted — but only ones you
can fully enumerate (e.g. a 10–20 model patrol, every model resolvable), not a 50-model
blurred army pile.

Keep the gold set **frozen forever** once labeled. It is the reference every run is
measured against; changing it silently breaks comparability across time.
