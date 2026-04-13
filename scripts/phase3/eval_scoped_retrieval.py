#!/usr/bin/env python3
"""
Phase 2 — scoped retrieval eval.

Three-tier pipeline all derived from a single DINOv2 embedding per query:

  Tier 2 (faction)  = classify_faction_knn — top-K gallery neighbours
                       vote on faction
  Tier 3 scoped     = cosine-sim retrieval restricted to gallery items
                       whose faction matches Tier 2's prediction

We report three retrieval variants to make the lift auditable:

  unscoped        — Phase 1-style; search the full gallery
  scoped_actual   — scope by Tier 2's prediction (production path)
  scoped_oracle   — scope by the TRUE faction (upper bound if Tier 2
                     were perfect)

Note: we intentionally do NOT use YOLO11x as Tier 2 — it was trained
on full tabletop images and returns near-zero confidence on single-
miniature crops (empirically confirmed at phase2 scaffolding time).
KNN on the gallery re-uses infrastructure we already have and operates
in the same embedding space as Tier 3, with no distribution mismatch.

Usage:
    yolo_env/bin/python3 scripts/phase3/eval_scoped_retrieval.py
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE3 = REPO_ROOT / "scripts" / "phase3"
QUERIES_DIR = PHASE3 / "queries"
EMBEDDINGS_PATH = PHASE3 / "gallery_embeddings.npz"
RESULTS_DIR = PHASE3 / "results"

sys.path.insert(0, str(PHASE3))
from classify_faction_knn import classify_faction_knn  # noqa: E402


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--device", default=None)
    p.add_argument("--k", type=int, default=5, help="Top-K for retrieval output")
    p.add_argument("--tier2-k", type=int, default=5, help="K neighbours for Tier 2 faction voting")
    p.add_argument(
        "--gate-threshold",
        type=float,
        default=0.5,
        help="Tier 2 confidence threshold for the scoped_gated variant. Below this, "
             "fall back to unscoped retrieval. Default 0.5.",
    )
    p.add_argument(
        "--sweep-gates",
        action="store_true",
        help="Also evaluate a sweep of gate thresholds (0.3 / 0.4 / 0.5 / 0.6 / 0.7) "
             "for quick comparison.",
    )
    return p.parse_args()


def walk_queries() -> list[tuple[str, str, str, Path]]:
    if not QUERIES_DIR.exists():
        sys.exit(f"Queries directory not found at {QUERIES_DIR}. Run build_gallery.py first.")
    out = []
    for fac_dir in sorted(p for p in QUERIES_DIR.iterdir() if p.is_dir()):
        for unit_dir in sorted(p for p in fac_dir.iterdir() if p.is_dir()):
            for img in sorted(unit_dir.iterdir()):
                if img.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                    out.append((fac_dir.name, unit_dir.name, str(img.relative_to(REPO_ROOT)), img))
    return out


def rank_units(sims, gallery_factions, gallery_units, mask):
    """Return sorted list of ((faction, unit), max-sim) for rows where mask is True."""
    best: dict[tuple[str, str], float] = {}
    for i, (f, u, s) in enumerate(zip(gallery_factions, gallery_units, sims)):
        if not mask[i]:
            continue
        key = (str(f), str(u))
        if s > best.get(key, -1):
            best[key] = float(s)
    return sorted(best.items(), key=lambda kv: -kv[1])


def find_rank(ranked, true_key):
    for r, (k, _) in enumerate(ranked, 1):
        if k == true_key:
            return r
    return None


def agg(per_query_ranks, n):
    t1 = sum(1 for r in per_query_ranks if r == 1)
    t3 = sum(1 for r in per_query_ranks if r is not None and r <= 3)
    t5 = sum(1 for r in per_query_ranks if r is not None and r <= 5)
    rr_sum = sum(1 / r for r in per_query_ranks if r is not None)
    return {
        "top1": t1 / n if n else 0,
        "top3": t3 / n if n else 0,
        "top5": t5 / n if n else 0,
        "mrr": rr_sum / n if n else 0,
        "counts": {"top1": t1, "top3": t3, "top5": t5, "total": n},
    }


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
    g = np.load(EMBEDDINGS_PATH, allow_pickle=True)
    gallery_emb = g["embeddings"]
    gallery_factions = np.array([str(x) for x in g["factions"]])
    gallery_units = np.array([str(x) for x in g["units"]])
    model_id = str(g["model_id"])

    device = args.device or ("cuda:0" if torch.cuda.is_available() else "cpu")
    processor = AutoImageProcessor.from_pretrained(model_id)
    embedder = AutoModel.from_pretrained(model_id).to(device).eval()

    print(f"Device: {device}")
    print(f"Gallery: {gallery_emb.shape[0]} images, model={model_id}")

    queries = walk_queries()
    if not queries:
        sys.exit(f"No query images under {QUERIES_DIR}")
    print(f"Queries: {len(queries)}")

    # Embed queries.
    q_embeds = []
    with torch.no_grad():
        for i in range(0, len(queries), args.batch):
            batch = queries[i : i + args.batch]
            imgs = [Image.open(e[3]).convert("RGB") for e in batch]
            inp = processor(images=imgs, return_tensors="pt").to(device)
            out = embedder(**inp)
            emb = out.pooler_output if getattr(out, "pooler_output", None) is not None else out.last_hidden_state[:, 0]
            emb = torch.nn.functional.normalize(emb, p=2, dim=-1)
            q_embeds.append(emb.cpu().numpy())
    query_emb = np.concatenate(q_embeds, axis=0).astype(np.float32)

    # Pre-compute full sims matrix: (Q, N).
    all_sims = query_emb @ gallery_emb.T

    all_mask = np.ones(len(gallery_emb), dtype=bool)

    per_query = []
    tier2_correct = 0
    unscoped_ranks = []
    scoped_actual_ranks = []
    scoped_oracle_ranks = []
    scoped_gated_ranks = []
    # Sweep storage: { threshold: [rank_per_query] }
    sweep_ranks = {t: [] for t in (0.3, 0.4, 0.5, 0.6, 0.7)} if args.sweep_gates else {}

    for qi, (q_faction, q_unit, q_rel, _) in enumerate(queries):
        sims = all_sims[qi]
        true_key = (q_faction, q_unit)

        # Tier 2 via KNN faction vote.
        tier2 = classify_faction_knn(
            query_emb[qi], gallery_emb, gallery_factions, k=args.tier2_k
        )
        predicted_faction = tier2["faction"]
        tier2_conf = tier2["confidence"]
        tier2_is_right = predicted_faction == q_faction
        tier2_correct += int(tier2_is_right)

        # Rank under the three masks — we need all of them for the gated
        # variant (which conditionally uses scoped vs unscoped).
        u_ranked = rank_units(sims, gallery_factions, gallery_units, all_mask)
        u_rank = find_rank(u_ranked, true_key)
        unscoped_ranks.append(u_rank)

        actual_mask = gallery_factions == predicted_faction if predicted_faction else all_mask
        a_ranked = rank_units(sims, gallery_factions, gallery_units, actual_mask)
        a_rank = find_rank(a_ranked, true_key)
        scoped_actual_ranks.append(a_rank)

        oracle_mask = gallery_factions == q_faction
        o_ranked = rank_units(sims, gallery_factions, gallery_units, oracle_mask)
        o_rank = find_rank(o_ranked, true_key)
        scoped_oracle_ranks.append(o_rank)

        # Gated: use scoped only when Tier 2 is confident enough.
        gated_rank = a_rank if tier2_conf >= args.gate_threshold else u_rank
        gated_used_scoped = tier2_conf >= args.gate_threshold
        scoped_gated_ranks.append(gated_rank)

        for t, bucket in sweep_ranks.items():
            bucket.append(a_rank if tier2_conf >= t else u_rank)

        per_query.append({
            "query_path": q_rel,
            "true_faction": q_faction,
            "true_unit": q_unit,
            "tier2_pred": predicted_faction,
            "tier2_conf": round(tier2_conf, 3),
            "tier2_correct": tier2_is_right,
            "tier2_all_scores": {k: round(v, 3) for k, v in tier2["all_scores"].items()},
            "unscoped_rank": u_rank,
            "scoped_actual_rank": a_rank,
            "scoped_oracle_rank": o_rank,
            "scoped_gated_rank": gated_rank,
            "scoped_gated_used_scoping": gated_used_scoped,
            "unscoped_top5": [{"unit": u, "faction": f, "sim": round(s, 3)} for (f, u), s in u_ranked[:args.k]],
            "scoped_actual_top5": [{"unit": u, "faction": f, "sim": round(s, 3)} for (f, u), s in a_ranked[:args.k]],
        })

    n = len(queries)
    summary = {
        "model_id": model_id,
        "tier2_method": "knn_vote",
        "tier2_k": args.tier2_k,
        "gate_threshold": args.gate_threshold,
        "metrics": {
            "num_queries": n,
            "tier2_faction_top1": tier2_correct / n if n else 0,
            "unscoped": agg(unscoped_ranks, n),
            "scoped_actual": agg(scoped_actual_ranks, n),
            "scoped_gated": agg(scoped_gated_ranks, n),
            "scoped_oracle": agg(scoped_oracle_ranks, n),
        },
        "per_query": per_query,
    }
    if sweep_ranks:
        summary["metrics"]["gate_sweep"] = {
            f"threshold_{t}": agg(ranks, n) for t, ranks in sweep_ranks.items()
        }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "retrieval_summary.json"
    out_path.write_text(json.dumps(summary, indent=2))

    def fmt(v):
        return f"top1={v['top1']:.1%} top3={v['top3']:.1%} top5={v['top5']:.1%} MRR={v['mrr']:.3f}"

    m = summary["metrics"]
    n_gated_scoped = sum(1 for q in per_query if q["scoped_gated_used_scoping"])
    print()
    print(f"=== Phase 2 scoped retrieval ({n} queries) ===")
    print(f"Tier 2 (KNN-vote, k={args.tier2_k}) faction top-1: {m['tier2_faction_top1']:.1%}")
    print(f"unscoped        : {fmt(m['unscoped'])}")
    print(f"scoped_actual   : {fmt(m['scoped_actual'])}   ← always-scope")
    print(f"scoped_gated    : {fmt(m['scoped_gated'])}   ← gated @ conf ≥ {args.gate_threshold} "
          f"({n_gated_scoped}/{n} queries took the scoped branch)")
    print(f"scoped_oracle   : {fmt(m['scoped_oracle'])}   ← upper bound")
    if sweep_ranks:
        print()
        print("Gate threshold sweep:")
        for t, ranks in sweep_ranks.items():
            a = agg(ranks, n)
            n_scoped = sum(1 for q in per_query if q["tier2_conf"] >= t)
            print(f"  t={t:.1f}  {fmt(a)}  ({n_scoped}/{n} queries scoped)")
    print(f"\nFull results: {out_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
