"""CLIP zero-shot semantic junk scan over the detection pool (Tier 1 prep, layer 2).

The cheap `quality_scan.py` catches *technically* broken images (blur/tiny/strip,
~4%). The bigger problem is *semantic* junk — memes, screenshots, terrain-only
shots, dice piles, rulebook pages — that are in focus and well-proportioned but
contain no miniature to detect. Auto-labeling them wastes the SAM 3 run and feeds
RF-DETR false positives.

This runs CLIP (ViT-B/32) zero-shot against a small prompt set and stores the
top-1 class + confidence in `semantic_zs`. Junk classes are deliberately
*unambiguous* non-miniature content; unpainted / primed / sprue models are NOT
flagged (they're valid detection targets — see the SAM 3 prompt research). It is
a **review** signal, not auto-deletion: tag, eyeball, tune the threshold.

Usage:
  fiftyone_env/bin/python scripts/curation/semantic_junk_scan.py [--sample N]   # classify
  fiftyone_env/bin/python scripts/curation/semantic_junk_scan.py --tag [--conf 0.0]
"""
from __future__ import annotations

import argparse

# Zero-shot prompt set. Top-1 over these → keep vs junk by membership below.
KEEP = [
    "a photo of painted tabletop miniatures",
    "a single miniature figurine model",
    "an army of wargaming models on a table",
]
JUNK = [
    "an internet meme with large caption text",
    "a screenshot of text or a website",
    "empty tabletop terrain and scenery with no miniatures",
    "a pile of dice and gaming tokens",
    "a page of printed rules text",
    "a cartoon or comic illustration",
]
CLASSES = KEEP + JUNK
JUNK_SET = set(JUNK)
FIELD = "semantic_zs"


def classify(sample_n: int | None, batch_size: int) -> None:
    import fiftyone as fo
    import fiftyone.zoo as foz
    from fiftyone import ViewField as F

    ds = fo.load_dataset("wh40k_pile")
    view = ds.match(F("pool") == "detection")
    # resumable: only samples without a prediction yet
    todo = view.match(F(FIELD) == None)  # noqa: E711 - FiftyOne needs == None
    if sample_n:
        todo = todo.limit(sample_n)
    print(f"detection pool {view.count()}; classifying {todo.count()} "
          f"(batch {batch_size})")
    if todo.count() == 0:
        print("nothing to do")
        return
    model = foz.load_zoo_model("clip-vit-base32-torch", classes=CLASSES)
    todo.apply_model(model, label_field=FIELD, batch_size=batch_size)
    print("done")
    _summary(ds, view)


def _summary(ds, view) -> None:
    from fiftyone import ViewField as F

    scored = view.match(F(FIELD) != None)  # noqa: E711
    n = scored.count()
    if not n:
        return
    counts = scored.count_values(f"{FIELD}.label")
    junk_n = sum(v for k, v in counts.items() if k in JUNK_SET)
    print(f"\nscored {n}; predicted JUNK {junk_n} ({100*junk_n/n:.1f}%)")
    for k in sorted(counts, key=lambda x: -counts[x]):
        tag = "JUNK" if k in JUNK_SET else "keep"
        print(f"  [{tag}] {counts[k]:5}  {k}")


def tag(conf: float) -> None:
    import fiftyone as fo
    from fiftyone import ViewField as F

    ds = fo.load_dataset("wh40k_pile")
    if ds.match_tags("junk_clip").count():
        ds.match_tags("junk_clip").untag_samples("junk_clip")
    junk = ds.match(
        F(f"{FIELD}.label").is_in(list(JUNK_SET)) & (F(f"{FIELD}.confidence") >= conf)
    )
    junk.tag_samples("junk_clip")
    print(f"tagged {junk.count()} images junk_clip (conf >= {conf})")
    # intersection with the cheap lowq filter (chained match = AND)
    both = ds.match_tags("junk_clip").match_tags("lowq")
    print(f"  also flagged lowq (overlap): {both.count()}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=None,
                    help="classify only first N (validation run)")
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--tag", action="store_true")
    ap.add_argument("--conf", type=float, default=0.0,
                    help="min confidence to tag as junk")
    args = ap.parse_args()
    if args.tag:
        tag(args.conf)
    else:
        classify(args.sample, args.batch_size)


if __name__ == "__main__":
    main()
