# Benchmark — 2026-06-04 · Auto-label baseline (Tier 1 detection)

**What:** First class-agnostic detection baseline for the data-centric rebuild, scored
against the frozen `gold_v1` set (35 images, 124 hand-labeled boxes).

**Method:** Grounding-DINO-tiny (`IDEA-Research/grounding-dino-tiny`), single text prompt
`"miniature."`, box threshold 0.3, on CPU. Class-agnostic: every gold box (any faction,
incl. `out_of_scope`) is a detection target. Greedy IoU≥0.5 matching.
Repro: `fiftyone_env/bin/python scripts/curation/eval_autolabel_gold.py`.

**Results:**
| metric | value |
|---|---|
| precision | 0.681 |
| recall | **0.516** |
| F1 | 0.587 |
| count MAE / image | 1.77 (bias −0.86, under-counts) |
| TP / FP / FN | 64 / 30 / 60 |

**Read:** A cheap, untuned zero-shot text-prompt detector finds ~half the models on these
(often dense) scenes — squarely in the ~50–70% band the strategy predicted for open-vocab
detectors on dense tabletop. **Well below the Plan D2 exit bar (recall ≥ 0.90.)** Under-counts
in crowds (negative bias). This is the floor.

**Next:** SAM 3 promptable-concept segmentation on Colab (GPU) with tuned prompts + image
exemplars (`scripts/phaseF/autolabel_colab.ipynb`), then distill RF-DETR (Autodistill) and
re-score against this same gold set. Caveats on this baseline: smallest GDINO variant, one
naive prompt, no exemplars, untuned threshold — lots of easy headroom before SAM 3 even.
