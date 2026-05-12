"""Phase F1 pseudo-labeller — multi-detector ensemble for class-agnostic
miniature detection on Warhammer 40K photos.

Each sub-module is a `Detector` subclass (see photoanalyzer.detect.base)
or a helper used by the voting orchestrator. Keep the module boundaries
clean so we can swap individual detectors without touching the rest.

  sam3            — SAM 3 (Meta, Nov 2025). Used offline only; outputs
                    are our pseudo-boxes. Primary quality driver.
  dinox           — DINO-X (IDEA Research, Apache-2.0). Best text-prompt
                    open-vocab detector with Apache licensing.
  owlv2_visual    — OWLv2 in image_guided_detection mode with ~30 gold
                    exemplar crops. Complements text-prompted passes.
  sam2_refine     — SAM 2 mask refinement. For every candidate box,
                    prompt SAM 2 with the box, recompute tight bbox from
                    the mask. Drops false positives whose refined IoU
                    with the original is too low.
  voting          — Orchestrator. Run all detectors, refine, NMS with
                    supporter tracking, split into auto_accept/review.
"""
