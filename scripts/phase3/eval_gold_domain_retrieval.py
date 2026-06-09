"""Tier 3 retrieval eval — GOLD-DOMAIN queries vs the current gallery.

The 2026-06-06 numbers (`eval_gallery_retrieval.py`) are leave-one-out over the
gallery itself: catalog-style queries against a catalog that deliberately retains
near-duplicates. That measures gallery self-consistency, not the deployment task.

This script measures the deployment task: queries are hand-unit-labeled crops cut
from real scene photos (the `source=annotation` rows of `data/labels.csv` — the
human annotation corpus, i.e. the same domain as the gold set), retrieved against
the current FiftyOne gallery (`pool=gallery`) by cosine k-NN on frozen
DINOv2-large embeddings, scoped to the query's true faction (the production path:
Tier 2 picks the faction, Tier 3 retrieves within it).

Honesty mechanics:
- Queries are embedded fresh with the SAME recipe as the gallery (dinov2-large,
  CLS token, L2-normalized — see embed_gpu.py / classify_faction_probe.py).
- Only queries whose unit_slug exists in their faction's gallery are scored
  (coverage is reported — a missing gallery unit is a depth problem, not a
  retrieval problem).
- Near-dup suspects (max cosine vs gallery >= --dup-thresh, default 0.97) are
  reported and the headline is recomputed without them.

  fiftyone_env/bin/python scripts/phase3/eval_gold_domain_retrieval.py
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import math
from pathlib import Path

import numpy as np

V1 = ("space_marines", "necrons", "tyranids", "death_guard")
LABELS_CSV = "data/labels.csv"
OUT_JSON = "docs/benchmarks/2026-06-09-tier3-gold-domain-retrieval.json"


def embed_crops(crops) -> np.ndarray:
    """dinov2-large CLS token, L2-normalized — matches embed_gpu.py exactly."""
    import torch
    from transformers import AutoImageProcessor, AutoModel

    proc = AutoImageProcessor.from_pretrained("facebook/dinov2-large")
    model = AutoModel.from_pretrained("facebook/dinov2-large").eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(crops), 16):
            pix = proc(images=crops[i:i + 16], return_tensors="pt")["pixel_values"]
            cls = model(pixel_values=pix).last_hidden_state[:, 0]
            cls = torch.nn.functional.normalize(cls, dim=1)
            out.append(cls.to(torch.float16).numpy())
            print(f"  embedded {min(i + 16, len(crops))}/{len(crops)}")
    return np.concatenate(out, 0)


def wilson_lb(k: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - margin) / denom


def load_queries() -> list[dict]:
    """labels.csv annotation-source rows. The original crop JPEGs under
    scripts/phase1/crops/ were deleted in the 2026-06-05 cleanup, so each crop
    is regenerated from its annotation JSON: crop_path encodes
    {imageid}__{box_idx}, the JSON's `annotations` array holds pixel-space
    modelBbox in extraction order, padding 5% of max(w,h) per the deleted
    extract_gt_crops.py behaviour (documented in label/extract.py:pad_bbox)."""
    from PIL import Image

    ann_dir = Path("backend/training_data_annotations")
    rows, skipped = [], collections.Counter()
    with open(LABELS_CSV) as f:
        for r in csv.DictReader(f):
            if r["faction"] not in V1 or r["source"] != "annotation":
                continue
            if not r["unit_slug"] or r["unit_slug"] == "unknown":
                continue
            stem = Path(r["crop_path"]).stem          # {imageid}__{NN}
            imageid, _, box_idx = stem.rpartition("__")
            hits = list(ann_dir.glob(f"*{imageid}.json"))
            if len(hits) != 1:
                skipped["no_unique_annotation_json"] += 1
                continue
            ann = json.loads(hits[0].read_text())
            boxes = ann.get("annotations", [])
            bi = int(box_idx)
            if bi >= len(boxes):
                skipped["box_idx_out_of_range"] += 1
                continue
            img_path = Path(ann["imagePath"])
            if not img_path.exists():
                skipped["scene_image_missing"] += 1
                continue
            b = boxes[bi]["modelBbox"]
            img = Image.open(img_path).convert("RGB")
            pad = max(b["width"], b["height"]) * 0.05
            x0 = max(0, int(round(b["x"] - pad)))
            y0 = max(0, int(round(b["y"] - pad)))
            x1 = min(img.width, int(round(b["x"] + b["width"] + pad)))
            y1 = min(img.height, int(round(b["y"] + b["height"] + pad)))
            if x1 - x0 < 8 or y1 - y0 < 8:
                skipped["degenerate_box"] += 1
                continue
            r["_crop"] = img.crop((x0, y0, x1, y1))
            rows.append(r)
    if skipped:
        print(f"query rows skipped: {dict(skipped)}")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dup-thresh", type=float, default=0.97)
    args = ap.parse_args()

    import fiftyone as fo
    from fiftyone import ViewField as F
    from PIL import Image

    # ── gallery: current pool, precomputed DINOv2-large embeddings ───────────
    ds = fo.load_dataset("wh40k_pile")
    gal = ds.match((F("pool") == "gallery") & (F("embedding") != None))  # noqa: E711
    gfac, gunit, gemb = gal.values(["weak_faction", "weak_unit", "embedding"])
    G = np.stack([np.asarray(e, np.float32) for e in gemb])
    G /= np.linalg.norm(G, axis=1, keepdims=True) + 1e-9
    gfac = np.array([str(x) for x in gfac])
    gunit = np.array([str(x) for x in gunit])
    print(f"gallery: {len(gfac)} embedded crops")

    # ── queries: hand-labeled scene crops from labels.csv ────────────────────
    queries = load_queries()
    print(f"queries: {len(queries)} annotation-source v1 crops "
          f"(by faction: {dict(collections.Counter(q['faction'] for q in queries))})")
    imgs = [q.pop("_crop") for q in queries]
    Q = embed_crops(imgs).astype(np.float32)
    Q /= np.linalg.norm(Q, axis=1, keepdims=True) + 1e-9

    # ── scoped retrieval ─────────────────────────────────────────────────────
    results = []
    for q, qe in zip(queries, Q):
        fac, unit = q["faction"], q["unit_slug"]
        gi = np.where(gfac == fac)[0]
        covered = unit in set(gunit[gi])
        sims = G[gi] @ qe
        order = gi[np.argsort(-sims)]
        top_units = list(dict.fromkeys(gunit[order]))[:3]  # top-3 distinct units
        results.append({
            "crop_path": q["crop_path"], "faction": fac, "unit": unit,
            "covered": covered,
            "max_sim": float(sims.max()) if len(sims) else 0.0,
            "top1": covered and top_units[0] == unit,
            "top3": covered and unit in top_units,
            "retrieved": top_units,
        })

    # ── report ───────────────────────────────────────────────────────────────
    def table(rows, title):
        print(f"\n=== {title} ===")
        print(f"  {'faction':16} {'n':>4} {'top-1':>7} {'top-3':>7} {'wilsonLB3':>10}")
        agg = {"n": 0, "t1": 0, "t3": 0}
        out = {}
        for fac in V1:
            fr = [r for r in rows if r["faction"] == fac]
            n = len(fr)
            if not n:
                continue
            t1 = sum(r["top1"] for r in fr)
            t3 = sum(r["top3"] for r in fr)
            agg["n"] += n; agg["t1"] += t1; agg["t3"] += t3
            out[fac] = {"n": n, "top1": t1 / n, "top3": t3 / n,
                        "wilson_lb_top3": wilson_lb(t3, n)}
            print(f"  {fac:16} {n:>4} {t1 / n:>7.3f} {t3 / n:>7.3f} "
                  f"{wilson_lb(t3, n):>10.3f}")
        if agg["n"]:
            out["v1_overall"] = {"n": agg["n"], "top1": agg["t1"] / agg["n"],
                                 "top3": agg["t3"] / agg["n"],
                                 "wilson_lb_top3": wilson_lb(agg["t3"], agg["n"])}
            print(f"  {'v1 overall':16} {agg['n']:>4} {agg['t1'] / agg['n']:>7.3f} "
                  f"{agg['t3'] / agg['n']:>7.3f} "
                  f"{wilson_lb(agg['t3'], agg['n']):>10.3f}")
        return out

    covered = [r for r in results if r["covered"]]
    uncov = [r for r in results if not r["covered"]]
    print(f"\ncoverage: {len(covered)}/{len(results)} queries have their unit in "
          f"the faction gallery ({len(uncov)} uncovered)")
    if uncov:
        miss = collections.Counter((r["faction"], r["unit"]) for r in uncov)
        print("  uncovered units:", dict(miss.most_common(12)))

    scored = table(covered, "scoped retrieval, covered queries")

    suspects = [r for r in covered if r["max_sim"] >= args.dup_thresh]
    print(f"\nnear-dup suspects (max cosine >= {args.dup_thresh}): "
          f"{len(suspects)}/{len(covered)}")
    clean = table([r for r in covered if r["max_sim"] < args.dup_thresh],
                  f"scoped retrieval, suspects excluded")

    fails = collections.Counter(
        (r["faction"], r["unit"]) for r in covered if not r["top3"])
    if fails:
        print("\nworst units (top-3 misses):", dict(fails.most_common(10)))

    Path(OUT_JSON).write_text(json.dumps({
        "date": "2026-06-09",
        "method": "scoped cosine k-NN, DINOv2-large CLS, gold-domain queries "
                  "(labels.csv source=annotation) vs current FiftyOne gallery",
        "n_queries": len(results), "n_covered": len(covered),
        "n_dup_suspects": len(suspects), "dup_thresh": args.dup_thresh,
        "covered": scored, "suspects_excluded": clean,
        "uncovered_units": [f"{f}/{u}" for (f, u), _ in
                            collections.Counter((r["faction"], r["unit"])
                                                for r in uncov).most_common()],
        "worst_units": [f"{f}/{u}:{c}" for (f, u), c in fails.most_common()],
    }, indent=2) + "\n")
    print(f"\nwrote {OUT_JSON}")


if __name__ == "__main__":
    main()
