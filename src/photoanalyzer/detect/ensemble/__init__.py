"""Phase F1 pseudo-labeller — class-agnostic miniature detection on 40K photos.

The pipeline is **SAM 3 detection + optional SAM 2 refinement** (locked
2026-04-25; the original SAM 3 + Grounding DINO + OWLv2 ensemble was dropped
after Phase C bench showed the extra detectors only hurt precision). The
`ensemble` package name and `voting` module are retained for the existing call
sites — there is no longer any multi-detector voting.

  sam3         — SAM 3 (Meta). Offline pseudo-box generator. Primary detector.
  sam2_refine  — SAM 2 mask refinement: box-prompt SAM 2, recompute a tight
                 bbox from the mask, drop FPs whose refined IoU is too low.
  voting       — Single-detector runner: SAM 3 → (optional) SAM 2 refine →
                 IoU-cluster SAHI tile-seam duplicates. No voting.
"""
