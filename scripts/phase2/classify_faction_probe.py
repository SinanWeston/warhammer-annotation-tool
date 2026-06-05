"""Tier 2 faction classifier — DINOv2 linear probe, tested on the GOLD crops.

STRATEGY names the linear probe as the cheapest next Tier 2 experiment (KNN-vote
flatlined ~55%). This runs it honestly:

  TRAIN  on the full gallery's frozen DINOv2-large embeddings (weak_faction
         labels). Dups are kept — `build_pools.py` deliberately retains them, and
         the global `dup` tag in fact nukes the entire SM + Necron gallery, so
         excluding it would silently drop two v1 factions.
  TEST   on crops cut from the hand-labeled gold set (`gold_v2.json`) and embedded
         fresh with the SAME recipe (dinov2-large, CLS token, L2-normalized). The
         gold crops are fully separate from the gallery → no train/test leakage,
         and real hand labels → no weak-label noise on the eval side.

This is the trustworthy faction number; a gallery-internal split is leakage-prone
(near-dups) and is intentionally not used.

  fiftyone_env/bin/python scripts/phase2/classify_faction_probe.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

MODEL = "facebook/dinov2-large"
GOLD = "data/gold/gold_v2.json"
V1 = ("space_marines", "necrons", "tyranids", "death_guard")


def embed_crops(crops) -> np.ndarray:
    """Embed PIL crops with dinov2-large CLS token, L2-normalized (matches embed_gpu.py)."""
    import torch
    from transformers import AutoImageProcessor, AutoModel

    proc = AutoImageProcessor.from_pretrained(MODEL)
    model = AutoModel.from_pretrained(MODEL).eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(crops), 16):
            batch = crops[i:i + 16]
            pix = proc(images=batch, return_tensors="pt")["pixel_values"]
            cls = model(pixel_values=pix).last_hidden_state[:, 0]
            cls = torch.nn.functional.normalize(cls, dim=1)
            out.append(cls.to(torch.float16).numpy())
            print(f"  embedded {min(i + 16, len(crops))}/{len(crops)}")
    return np.concatenate(out, 0)


def main() -> None:
    import fiftyone as fo
    from fiftyone import ViewField as F
    from PIL import Image
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    # ── train: full gallery embeddings ──────────────────────────────────────
    ds = fo.load_dataset("wh40k_pile")
    gal = ds.match((F("pool") == "gallery") & (F("embedding") != None))  # noqa: E711
    facs, embs = gal.values(["weak_faction", "embedding"])
    Xtr = np.stack([np.asarray(e, np.float32) for e in embs])
    ytr = np.asarray([str(f) for f in facs])
    print(f"train: {len(ytr)} gallery crops, {len(set(ytr))} factions")
    scaler = StandardScaler().fit(Xtr)
    clf = LogisticRegression(max_iter=3000, C=1.0).fit(scaler.transform(Xtr), ytr)
    classes = clf.classes_

    # ── test: gold crops, embedded fresh ────────────────────────────────────
    gold = json.loads(Path(GOLD).read_text())
    crops, truth = [], []
    for im in gold["images"]:
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
            truth.append(b["label"])
    print(f"test: {len(crops)} gold crops")
    Xte = embed_crops(crops)
    yte = np.asarray(truth)

    proba = clf.predict_proba(scaler.transform(Xte.astype(np.float32)))
    order = np.argsort(-proba, axis=1)
    pred1 = classes[order[:, 0]]

    # score only on classes the probe can actually predict (gallery factions).
    # out_of_scope / unknown have no gallery class; DG has 0 gallery crops.
    trainable = set(classes)
    print(f"\n=== Tier 2 probe on GOLD crops (train=gallery, test=hand-labeled) ===")
    for fac in V1:
        m = yte == fac
        n = int(m.sum())
        if not n:
            continue
        if fac not in trainable:
            print(f"  {fac:14} n={n:3}  — NO gallery training data (untestable)")
            continue
        t1 = float(np.mean(pred1[m] == fac))
        t3 = float(np.mean([yte[i] in classes[order[i, :3]]
                            for i in range(len(yte)) if m[i]]))
        print(f"  {fac:14} n={n:3}  top-1 {t1:.3f}  top-3 {t3:.3f}")

    # overall on the 3 trainable v1 factions
    mask = np.array([t in trainable and t in V1 for t in yte])
    if mask.any():
        t1 = float(np.mean(pred1[mask] == yte[mask]))
        print(f"\n  v1 (trainable factions) overall top-1: {t1:.3f}  (n={int(mask.sum())})")

    # what does out_of_scope get predicted as? (calibration sanity)
    oos = yte == "out_of_scope"
    if oos.any():
        import collections
        c = collections.Counter(pred1[oos])
        print(f"\n  out_of_scope crops (n={int(oos.sum())}) predicted as:",
              dict(c.most_common(5)))
        print("  → these SHOULD be rejected by a confidence threshold (Tier 2 'unknown' path)")


if __name__ == "__main__":
    main()
