"""Embed the two Tier 2/3 eval crop sets once and cache to npz.

Every probe/retrieval experiment re-embeds the same crops (~8 CPU-min a run).
This caches both sets in one pass:

  queries  : the 102 gold-domain unit-labeled crops (labels.csv source=annotation,
             regenerated from annotation JSONs — see eval_gold_domain_retrieval)
  gold     : the 283 gold_v2 box crops incl. out_of_scope (the Tier 2 test set,
             cropping per classify_faction_probe.py)

Cache: data/embeddings/eval_crops_cache.npz. Invalidate by deleting the file
(crops are regenerated deterministically from labels.csv + annotation JSONs +
gold_v2.json — if those change, delete the cache).

  fiftyone_env/bin/python scripts/phase2/embed_eval_crops.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "phase3"))
from eval_gold_domain_retrieval import embed_crops, load_queries  # noqa: E402

OUT = Path("data/embeddings/eval_crops_cache.npz")
GOLD = Path("data/gold/gold_v2.json")


def gold_crops():
    """gold_v2 box crops + labels (same recipe as classify_faction_probe.py)."""
    from PIL import Image

    crops, labels = [], []
    for im in json.loads(GOLD.read_text())["images"]:
        try:
            img = Image.open(im["filepath"]).convert("RGB")
        except Exception:
            continue
        W, H = img.size
        for b in im["boxes"]:
            x, y, w, h = b["bbox_xywh_norm"]
            px, py, pw, ph = x * W, y * H, w * W, h * H
            if pw < 8 or ph < 8:
                continue
            crops.append(img.crop((px, py, px + pw, py + ph)))
            labels.append(b["label"])
    return crops, labels


def main() -> None:
    if OUT.exists():
        print(f"{OUT} already exists — delete it to re-embed")
        return

    queries = load_queries()
    q_imgs = [q.pop("_crop") for q in queries]
    g_imgs, g_labels = gold_crops()
    print(f"embedding {len(q_imgs)} query crops + {len(g_imgs)} gold crops")

    E = embed_crops(q_imgs + g_imgs).astype(np.float16)
    nq = len(q_imgs)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUT,
        q_emb=E[:nq],
        q_faction=np.array([q["faction"] for q in queries]),
        q_unit=np.array([q["unit_slug"] for q in queries]),
        q_crop_path=np.array([q["crop_path"] for q in queries]),
        g_emb=E[nq:],
        g_label=np.array(g_labels),
        model="facebook/dinov2-large",
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
