#!/usr/bin/env python3
"""
Phase 1 — evaluate unit-level retrieval.

For every crop in scripts/phase1/queries/, embed with the same model
that produced gallery_embeddings.npz, run cosine similarity against the
gallery, aggregate per-unit via max-similarity (one value per unit =
best-matching gallery image for that unit), and report top-K metrics.

Per-query output:
    {
        "query_path": "...",
        "true_faction": "...",
        "true_unit": "...",
        "ranked_units": [ { "unit": ..., "faction": ..., "sim": ... }, ... ],  // top-5
        "is_top1": bool,
        "is_top3": bool,
        "is_top5": bool,
        "reciprocal_rank": float,   // 0 if true unit not in ranking
    }

Summary:
    top-1, top-3, top-5 accuracy
    MRR (mean reciprocal rank over queries; unranked queries count as 0)
    Faction top-1 (faction of top-1 unit matches true faction)
    "Unknown" calibration — sim value at false-positive-rate 10%

Usage:
    yolo_env/bin/python3 scripts/phase1/eval_retrieval.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE1 = REPO_ROOT / "scripts" / "phase1"
QUERIES_DIR = PHASE1 / "queries"
EMBEDDINGS_PATH = PHASE1 / "gallery_embeddings.npz"
LABELS_CSV = PHASE1 / "labels.csv"
RESULTS_DIR = PHASE1 / "results"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--device", default=None)
    p.add_argument("--k", type=int, default=5, help="Top-K to return per query (also used for top-K metrics)")
    return p.parse_args()


def walk_queries() -> list[tuple[str, str, str, Path]]:
    """Yield (faction, unit, rel_path, abs_path) for every query image."""
    if not QUERIES_DIR.exists():
        sys.exit(f"Queries directory not found at {QUERIES_DIR}. Run build_gallery.py first.")
    out = []
    for faction_dir in sorted(p for p in QUERIES_DIR.iterdir() if p.is_dir()):
        faction = faction_dir.name
        for unit_dir in sorted(p for p in faction_dir.iterdir() if p.is_dir()):
            unit = unit_dir.name
            for img in sorted(unit_dir.iterdir()):
                if img.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                    out.append((faction, unit, str(img.relative_to(REPO_ROOT)), img))
    return out


def main():
    args = parse_args()

    try:
        import numpy as np
        import torch
        from PIL import Image
        from transformers import AutoImageProcessor, AutoModel
    except ImportError as e:
        sys.exit(f"Missing dependency: {e}. Run from yolo_env.")

    if not EMBEDDINGS_PATH.exists():
        sys.exit(f"Gallery embeddings not found at {EMBEDDINGS_PATH}. Run embed_gallery.py first.")
    gallery_npz = np.load(EMBEDDINGS_PATH, allow_pickle=True)
    gallery_emb = gallery_npz["embeddings"]        # (N, D)
    gallery_paths = gallery_npz["paths"]
    gallery_factions = gallery_npz["factions"]
    gallery_units = gallery_npz["units"]
    model_id = str(gallery_npz["model_id"])

    # Build per-(faction, unit) max-sim aggregation map: each gallery entry is indexed
    # by its (faction, unit) tuple, and we group indices for max-reduction per query.
    by_unit: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, (f, u) in enumerate(zip(gallery_factions, gallery_units)):
        by_unit[(str(f), str(u))].append(i)

    device = args.device or ("cuda:0" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    print(f"Gallery: {gallery_emb.shape[0]} images, {len(by_unit)} unique units, model={model_id}")

    processor = AutoImageProcessor.from_pretrained(model_id)
    model = AutoModel.from_pretrained(model_id).to(device).eval()

    queries = walk_queries()
    if not queries:
        sys.exit(f"No query images found under {QUERIES_DIR}.")
    print(f"Queries: {len(queries)}")

    # Embed queries.
    q_embeds = []
    with torch.no_grad():
        for i in range(0, len(queries), args.batch):
            batch = queries[i : i + args.batch]
            imgs = [Image.open(e[3]).convert("RGB") for e in batch]
            inputs = processor(images=imgs, return_tensors="pt").to(device)
            outputs = model(**inputs)
            embed = outputs.pooler_output if getattr(outputs, "pooler_output", None) is not None else outputs.last_hidden_state[:, 0]
            embed = torch.nn.functional.normalize(embed, p=2, dim=-1)
            q_embeds.append(embed.cpu().numpy())
    query_emb = np.concatenate(q_embeds, axis=0).astype(np.float32)  # (Q, D)

    # Cosine sim is a dot product because both sides are L2-normalised.
    sims = query_emb @ gallery_emb.T  # (Q, N)

    per_query = []
    top1 = top3 = top5 = 0
    faction_top1 = 0
    rr_sum = 0.0
    impostor_sims: list[float] = []  # for "unknown" calibration
    true_positive_sims: list[float] = []

    for qi, (q_faction, q_unit, q_rel, _) in enumerate(queries):
        # Max-sim per gallery unit.
        unit_scores: list[tuple[float, str, str]] = []
        for (f, u), indices in by_unit.items():
            s = float(sims[qi, indices].max())
            unit_scores.append((s, f, u))
        unit_scores.sort(key=lambda x: -x[0])

        ranked = [{"unit": u, "faction": f, "sim": s} for (s, f, u) in unit_scores[: args.k]]
        # Rank of the true unit in the full unit list.
        rank = None
        for r, (_, f, u) in enumerate(unit_scores):
            if (f, u) == (q_faction, q_unit):
                rank = r + 1
                break

        is_top1 = (rank == 1)
        is_top3 = (rank is not None and rank <= 3)
        is_top5 = (rank is not None and rank <= 5)
        rr = (1.0 / rank) if rank else 0.0

        top1 += int(is_top1)
        top3 += int(is_top3)
        top5 += int(is_top5)
        rr_sum += rr
        if ranked[0]["faction"] == q_faction:
            faction_top1 += 1

        # Calibration: impostor_sims = top-1 sim when wrong; true-positive_sims = sim of correct unit.
        if is_top1:
            true_positive_sims.append(ranked[0]["sim"])
        else:
            impostor_sims.append(ranked[0]["sim"])

        per_query.append({
            "query_path": q_rel,
            "true_faction": q_faction,
            "true_unit": q_unit,
            "ranked_units": ranked,
            "is_top1": is_top1,
            "is_top3": is_top3,
            "is_top5": is_top5,
            "reciprocal_rank": rr,
            "true_rank": rank,
        })

    n = len(queries)
    # "Unknown" threshold: sim value at which 10% of impostors would be (mis)accepted.
    if impostor_sims:
        impostor_sims_sorted = sorted(impostor_sims, reverse=True)
        idx_10pct = max(0, int(len(impostor_sims_sorted) * 0.1) - 1)
        sim_at_fpr10 = impostor_sims_sorted[idx_10pct]
    else:
        sim_at_fpr10 = None

    summary = {
        "model_id": model_id,
        "num_queries": n,
        "num_gallery_images": int(gallery_emb.shape[0]),
        "num_gallery_units": len(by_unit),
        "metrics": {
            "top1": top1 / n if n else 0.0,
            "top3": top3 / n if n else 0.0,
            "top5": top5 / n if n else 0.0,
            "mrr": rr_sum / n if n else 0.0,
            "faction_top1": faction_top1 / n if n else 0.0,
            "unknown_threshold_sim_at_fpr10pct": sim_at_fpr10,
        },
        "per_query": per_query,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "retrieval_summary.json"
    out_path.write_text(json.dumps(summary, indent=2))

    print()
    print("=== Retrieval summary ===")
    print(f"Queries: {n}  |  Gallery units: {len(by_unit)}  |  Model: {model_id}")
    print(f"Top-1:   {top1}/{n} = {top1 / n:.1%}")
    print(f"Top-3:   {top3}/{n} = {top3 / n:.1%}")
    print(f"Top-5:   {top5}/{n} = {top5 / n:.1%}")
    print(f"MRR:     {rr_sum / n:.3f}")
    print(f"Faction top-1 (via retrieval): {faction_top1 / n:.1%}")
    if sim_at_fpr10 is not None:
        print(f"'Unknown' threshold (sim@FPR=10%): {sim_at_fpr10:.3f}")
    print(f"\nFull results: {out_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
