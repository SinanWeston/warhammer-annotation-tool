#!/usr/bin/env python3
"""
Phase 2 — Tier 2 faction classifier via DINOv2 gallery k-NN.

Given a DINOv2 query embedding, find the K nearest gallery entries by
cosine similarity, weight-vote each entry's faction by its sim score,
return the top faction. Reuses the same gallery embeddings that Tier 3
searches, so there's no extra model load and no model-crop-distribution
mismatch (YOLO was trained on full scenes, not crops — feeding a crop
into YOLO gave us near-zero confidence regardless of the true class).

This module is imported by eval_scoped_retrieval.py; not usually run
directly. CLI is provided for debugging.

Usage as a module:
    from classify_faction_knn import classify_faction_knn
    result = classify_faction_knn(
        query_embedding,            # (D,) np.ndarray, L2-normalised
        gallery_embeddings,         # (N, D) np.ndarray
        gallery_factions,           # (N,) str array
        k=5,
    )

Usage as a CLI:
    yolo_env/bin/python3 scripts/phase3/classify_faction_knn.py <query.jpg>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE3 = REPO_ROOT / "scripts" / "phase3"
DEFAULT_EMBEDDINGS = PHASE3 / "gallery_embeddings.npz"


def classify_faction_knn(
    query_embedding,
    gallery_embeddings,
    gallery_factions,
    k: int = 5,
) -> dict:
    """
    Return:
      {
        "faction": <top faction slug>,
        "confidence": <0-1, sum of top faction's weights / sum of all weights>,
        "k_neighbors_used": k,
        "all_scores": {<faction>: <summed_weight>, ...},
        "top_k_sims": [(faction, sim), ...]
      }
    """
    import numpy as np

    sims = query_embedding @ gallery_embeddings.T  # (N,)
    # Top-K by similarity.
    top_k_idx = np.argsort(-sims)[: min(k, len(sims))]
    top_k_sims = [(str(gallery_factions[i]), float(sims[i])) for i in top_k_idx]

    # Weighted-vote: faction score = sum of cosine similarities among its top-K hits.
    votes: dict[str, float] = defaultdict(float)
    for faction, sim in top_k_sims:
        votes[faction] += max(0.0, sim)

    if not votes:
        return {
            "faction": None,
            "confidence": 0.0,
            "k_neighbors_used": 0,
            "all_scores": {},
            "top_k_sims": [],
        }

    top_faction, top_score = max(votes.items(), key=lambda kv: kv[1])
    total = sum(votes.values())
    confidence = top_score / total if total > 0 else 0.0
    return {
        "faction": top_faction,
        "confidence": confidence,
        "k_neighbors_used": len(top_k_sims),
        "all_scores": dict(votes),
        "top_k_sims": top_k_sims,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", help="Path to a crop")
    parser.add_argument("--embeddings", default=str(DEFAULT_EMBEDDINGS))
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    try:
        import numpy as np
        import torch
        from PIL import Image
        from transformers import AutoImageProcessor, AutoModel
    except ImportError as e:
        sys.exit(f"Missing dep: {e}. Run from yolo_env.")

    g = np.load(args.embeddings, allow_pickle=True)
    gallery_emb = g["embeddings"]
    gallery_factions = [str(x) for x in g["factions"]]
    model_id = str(g["model_id"])

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    processor = AutoImageProcessor.from_pretrained(model_id)
    model = AutoModel.from_pretrained(model_id).to(device).eval()

    img = Image.open(args.image).convert("RGB")
    with torch.no_grad():
        inp = processor(images=img, return_tensors="pt").to(device)
        out = model(**inp)
        emb = out.pooler_output if getattr(out, "pooler_output", None) is not None else out.last_hidden_state[:, 0]
        emb = torch.nn.functional.normalize(emb, p=2, dim=-1).cpu().numpy()[0]

    result = classify_faction_knn(emb, gallery_emb, gallery_factions, k=args.k)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
