# Phase F1 — handoff context for future Claude sessions

This file is for an agent picking up Phase F1 work mid-stream. It
documents *why* the pipeline looks the way it does, *what was tried
and rejected*, and *the gotchas you'd otherwise rediscover painfully*.
The user-facing operations manual is `scripts/phaseF/README.md`.

If you only have time to read one section: **§ Architecture (current)**.

---

## Architecture (current — locked 2026-04-25)

**SAM 3 + SAM 2 mask refinement.** Single-detector pipeline.

- **SAM 3** (`facebook/sam3`, gated) drives detection. Text prompt:
  `"painted miniature"`. Confidence threshold 0.25.
- **SAM 2** (`facebook/sam2-hiera-large`, ungated) refines each box: prompt
  with the box, take SAM 2's best-scoring mask, recompute the tight
  enclosing bbox. Drop candidates whose refined IoU with the original
  box < **0.10** (loosened from 0.30 after refinement was filtering out
  almost everything on the 10-image smoke; see `§ Rejected paths`).
- The voting orchestrator (`voting.py`) still exists and works for
  multi-detector configurations, but the production path runs a
  degenerate "ensemble" with one detector. This is intentional: the code
  surface stays available for re-introducing detectors if needed, while
  the default config is dead simple.

Code location: `src/photoanalyzer/detect/ensemble/`.

The bench script (`scripts/phaseF/bench_ensemble.py`) measures two
detectors side-by-side as a regression check:

- `sam3` — SAM 3 raw boxes
- `sam3_refined` — SAM 3 → SAM 2 refinement (the production path)

If `sam3_refined` ever drops below `sam3` by more than a few mAP points,
something's wrong with refinement and we should investigate before
production runs.

---

## Why this architecture (not the original ensemble)

The plan written 2026-04-24 (`/home/sinan/.claude/plans/i-want-the-best-noble-blum.md`)
specified a 3-detector ensemble with agreement voting:

```
SAM 3  ┐
DINO-X ─► SAM 2 refine ─► IoU clustering ─► auto_accept (≥2 agree) / review (1)
OWLv2  ┘
```

Phase C bench results on 48 images (2026-04-25) demolished the case
for the ensemble:

| Detector | mAP@50 | Recall@0.5 | Precision@0.5 | Time/img |
|---|---|---|---|---|
| **SAM 3** | **0.322** | 0.535 | 0.262 | ~10s |
| OWLv2 visual | 0.142 | 0.632 | 0.012 | ~58s |
| DINO-X (Grounding DINO) | 0.107 | 0.368 | 0.287 | ~2.5s |
| ensemble_auto / full | broken (SAM 2 box-format bug) | | | |

Three things became clear:
1. **SAM 3 is the elephant.** 3× the next-best detector. The cv-researcher's
   prediction (SAM 3 doubles OWLv2/DINO-X on SA-Co) held up.
2. **OWLv2 visual at 1.2% precision is essentially noise.** Agreement
   with noise isn't a useful signal. Voting with weak detectors *hurts*
   precision more than it boosts recall.
3. **Ensemble cost is ~6× SAM 3 alone.** For a 17k production run that's
   the difference between ~50 GPU-hours and ~300 GPU-hours.

The decision: drop DINO-X and OWLv2 from production. Keep SAM 2 mask
refinement (it's the only ensemble component that pulled its weight
on its own merits — it tightens boxes and filters terrain false
positives). Keep the OWLv2 / DINO-X code paths so they're available
if a future need surfaces.

---

## Rejected paths (with reasons, so you don't redo them)

1. **DINO-X via DeepDataSpace API.** STRATEGY.md aspires to DINO-X (Apache-2.0,
   ~4 AP better than Grounding DINO base). DINO-X weights aren't on
   HuggingFace as of 2026-04. DeepDataSpace's API requires a paid key.
   The `DinoXDetector` class supports a `backend="dinox_api"` flag for
   when this changes; until then, `backend="grounding_dino_base"` is
   the default.

2. **3-detector ensemble.** See above. Don't put it back without new evidence.

3. **OWLv2 visual-prompt at threshold 0.90.** Produces 50× more false
   positives than true positives. The HF transformers issue #39710
   documents that OWLv2's default query-embedding selection is suboptimal;
   fixing it would require post-processing the model's last-layer
   embeddings rather than using `image_guided_detection`. Not worth
   the engineering for a detector that's already 2× worse than SAM 3.

4. **SAM 2 refinement IoU 0.30.** Empirically too aggressive — on the
   10-image smoke run, every box got dropped, leaving 0/55 predictions.
   Lowered to 0.10. Watch this number; if precision tanks on a future
   bench, re-tighten.

5. **Embedding the HF token in the notebook.** Sandbox blocks this for
   credential-leakage reasons (notebooks get re-uploaded indefinitely).
   Use Colab Secrets instead — the notebook's cell 6 reads from
   `userdata.get('HUGGINGFACE_HUB_TOKEN')`.

6. **Using `parts[-4:]` to reconstruct relative image paths.** The
   image path layout is `backend/training_data/<faction>/<source>/<file>`,
   which is **5 path components**, not 4. Use `parts[-5:]` or — better —
   the explicit `faction` + `source` fields in the eval manifest.
   See `_resolve_image_path` in `bench_ensemble.py`.

---

## Known gotchas

### Coord-space round-trips (twice burned)

The Colab bundler downscales images to a 1333 px long-edge cap. The
annotator and bench scripts run on full-resolution originals. If pseudo
boxes are emitted in 1333-space but consumed in 2592-space, every box
lands squashed in the top-left corner.

The fix is layered:

1. **`prepare_colab_bundle.py`** writes `data/pseudo_labels/original_dims.json`
   mapping each bundled image's relative path to its pre-downscale
   `(orig_w, orig_h)`.
2. **`autolabel_ensemble.py`** reads that manifest at runtime and
   rescales boxes from processed dims back to original dims before
   writing pseudo JSONs.
3. **`import_pseudo_to_annotator.py`** rescales again on import as a
   safety net, comparing the recorded width/height in the pseudo JSON
   to the actual image file dims and rebuilding boxes if they differ.

If you ever see boxes squashed in the top-left of an image, check this
chain. The original 2026-04-24 bug was: bundler didn't emit the
manifest, autolabel had no way to know images were downscaled, coords
came back wrong. Fix has held since.

### Phase C image-path resolution on Colab

`eval_200.json` records absolute paths like
`/home/sinan/Active/Projects/photoanalyzer/backend/training_data/...`.
On Colab the absolute prefix is different. `bench_ensemble.py`'s
`_resolve_image_path` falls back to `Path("backend/training_data") /
faction / source / filename` using the manifest's faction/source fields.
Don't break that fallback.

### CMON image symlinks

Some images live as symlinks under `backend/training_data/_unknown/cmon/`
pointing to the real files in `scripts/cmon/images/`. When the bundler
or bench scripts handle these, **do not `.resolve()` the path** —
that follows the symlink out of `backend/training_data/`. Use
`.absolute()` instead. The bug was hit on 2026-04-25 in
`prepare_colab_bundle.py:_load_phase_c_paths`; fix is in place.

### transformers 5.0 API changes

The current Colab env installs `transformers==5.0.0` (we pin
`>= 4.49`). Two breaking changes from 4.x:

- `Owlv2ImageProcessor` and `GroundingDinoImageProcessor` default to
  fast-processor classes which can produce slightly different outputs.
  Cosmetic warning in stdout; no action needed.
- `Sam2Processor.__call__(input_boxes=...)` requires **3 levels of
  list nesting**: `[[[x0,y0,x1,y1], [x0,y0,x1,y1], ...]]`. Python
  tuples (`(x0,y0,x1,y1)`) don't count as a level any more. The
  `sam2_refine.py` code converts xyxy tuples to lists of floats explicitly.
  If you see `Input boxes must be a nested list with 3 levels`, that's
  this. Don't substitute tuples back in.

### Notebook subprocess `PYTHONPATH`

Cell 13 runs `!python scripts/phaseF/bench_ensemble.py`. The notebook
kernel's `sys.path.insert` does **not** propagate to the subprocess.
The cell prepends `PYTHONPATH=/content/photoanalyzer/src` to the shell
command so the subprocess can `import photoanalyzer`. Don't drop that
prefix.

### Drive caching

Drive web UI sometimes serves stale notebooks for 30–60s after upload.
`sync.sh push` deletes stale `f1_outputs.tar` first so cell 11's
"restore prior outputs" logic doesn't fire on a Phase C bench run. If
the user opens the notebook too fast they may get the old version.
Tell them to hard-refresh (Ctrl-Shift-R) the Drive tab if cell 13
prints anything from the old notebook.

---

## File map

User-facing entry points:
- `scripts/phaseF/sync.sh` — Drive sync helper. Subcommands `full`,
  `push`, `pull`, `roundtrip`, `status`.
- `scripts/phaseF/README.md` — operations manual.
- `scripts/phaseF/autolabel_colab.ipynb` — the notebook that runs on
  Colab (cell 6 = HF token, cell 11 = restore outputs unless bench mode,
  cell 13 = run bench OR autolabel, cell 15 = save outputs).
- `scripts/phaseF/prepare_colab_bundle.py` — builds the tarball. Two
  modes: `--phase-c [--phase-c-limit N]` (bench bundle) vs `--sample N`
  / no-flag (autolabel bundle).
- `scripts/phaseF/build_exemplar_set.py` — generates `data/exemplars/`
  for OWLv2 (currently unused in production, kept available).
- `scripts/phaseF/bench_ensemble.py` — Phase C scorer. `--detectors`
  flag accepts: `sam3`, `sam3_refined`, `dinox`, `owlv2_visual`,
  `ensemble_auto`, `ensemble_full`, `grounding_dino_baseline`.
- `scripts/phaseF/autolabel_ensemble.py` — production runner.
- `scripts/phaseF/import_pseudo_to_annotator.py` — converts pseudo
  JSONs into the annotator's schema with safety-net coord rescaling.

Library code:
- `src/photoanalyzer/detect/base.py` — `Detector` ABC + `Detection`
  dataclass.
- `src/photoanalyzer/detect/sahi.py` — shared SAHI tiling + post-process
  (lifted out of `autolabel.py` so all detectors can use it).
- `src/photoanalyzer/detect/ensemble/sam3.py` — SAM 3 wrapper.
- `src/photoanalyzer/detect/ensemble/sam2_refine.py` — SAM 2 refinement.
- `src/photoanalyzer/detect/ensemble/voting.py` — multi-detector
  orchestrator (currently runs degenerate with just SAM 3).
- `src/photoanalyzer/detect/ensemble/dinox.py` — Grounding DINO wrapper
  (kept for fallback / experimentation).
- `src/photoanalyzer/detect/ensemble/owlv2_visual.py` — OWLv2
  image-guided wrapper (kept for fallback / experimentation).

Strategy / planning docs:
- `STRATEGY.md` §3.1 — architectural rationale, license stack table.
- `docs/STRATEGY_SOURCES.md` — bibliography incl. SAM 3 paper, DINO-X,
  Vision-Language Detection survey.
- `/home/sinan/.claude/plans/i-want-the-best-noble-blum.md` — original
  plan for the now-simplified ensemble.

---

## Active state at handoff

- **SAM 3 access**: the user (HF account `Ezek1al`) has Meta's gate
  approval for `facebook/sam3`. Token persists in `.env` and Colab
  Secrets.
- **rclone**: configured under remote name `gdrive`, root of MyDrive.
  OAuth in `~/.config/rclone/rclone.conf`. Don't mess with it.
- **First successful Phase C bench**: 48 images (2026-04-25), SAM 3
  alone hit 0.322 mAP@50. 10-image follow-up was noisy (0.004) — the
  small sample isn't trustworthy. 50-image runs are the standard.
- **Production 17k run**: not yet executed. Architecture is ready, just
  needs `sync.sh push` with an autolabel bundle and a longer-running
  Colab session (or rented GPU).

---

## How a future agent should pick up

1. Read `scripts/phaseF/README.md` for the operational picture.
2. Read this file for the *why* and the *don't-do-X-because-Y* context.
3. Run `bash scripts/phaseF/sync.sh status` to see what's currently on
   Drive — that tells you whether a run is staged or in flight.
4. If the user says "the bench numbers look weird", read the most recent
   `docs/benchmarks/*.md` and compare per-bucket recall against
   the 2026-04-25 baseline (0.535 recall@0.5 on 48 images for SAM 3
   alone). Drift below that probably means an integration regression,
   not a model issue.
5. If the user wants to add a new detector, copy the pattern from
   `sam3.py` (subclass `Detector`, lazy-load weights, support SAHI),
   add a `build_detector()` branch in `bench_ensemble.py`, and run a
   bench before flipping it into the default pipeline.
