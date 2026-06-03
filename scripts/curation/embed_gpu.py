"""Embed the downsized image bundle on a GPU (Battle Scanner Plan D1).

Canonical embedding logic — runs on Colab (`!python embed_gpu.py ...`) or any GPU
box. The Colab notebook (embed_colab.ipynb) inlines this same logic for drag-drop use.

Defaults to DINOv2-large (open, no HF gating) — for a dedup/curation pass the
backbone barely matters. Swap --model to a DINOv3 checkpoint for the Tier 3
retrieval gallery later (that one needs a HF token / gated access).

Input:  a bundle dir with images/{idx:06d}.jpg + manifest.csv (idx,filepath,status)
Output: embeddings.npz  (idx:int32[N], embeddings:float16[N,D], model:str, filepaths:str[N])

Usage:
  python embed_gpu.py --bundle ./wh40k_embed_bundle --out embeddings.npz --batch 64
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from transformers import AutoImageProcessor, AutoModel


class BundleDataset(Dataset):
    def __init__(self, img_dir: Path, rows, processor):
        self.img_dir = img_dir
        self.rows = rows  # list of (idx, filepath)
        self.processor = processor

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        idx, filepath = self.rows[i]
        im = Image.open(self.img_dir / f"{idx:06d}.jpg").convert("RGB")
        pix = self.processor(images=im, return_tensors="pt")["pixel_values"][0]
        return idx, filepath, pix


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True, help="dir with images/ + manifest.csv")
    ap.add_argument("--out", default="embeddings.npz")
    ap.add_argument("--model", default="facebook/dinov2-large")
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    bundle = Path(args.bundle)
    img_dir = bundle / "images"
    rows = []
    with open(bundle / "manifest.csv") as f:
        for r in csv.DictReader(f):
            if r["status"] == "ok":
                rows.append((int(r["idx"]), r["filepath"]))
    print(f"{len(rows)} ok images to embed with {args.model}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    processor = AutoImageProcessor.from_pretrained(args.model)
    model = AutoModel.from_pretrained(args.model).to(device).eval()

    ds = BundleDataset(img_dir, rows, processor)
    dl = DataLoader(ds, batch_size=args.batch, num_workers=args.workers, collate_fn=_collate)

    idxs, fps, embs = [], [], []
    done = 0
    with torch.no_grad():
        for batch_idx, batch_fp, pix in dl:
            pix = pix.to(device)
            out = model(pixel_values=pix)
            cls = out.last_hidden_state[:, 0]  # CLS token
            cls = torch.nn.functional.normalize(cls, dim=1)
            embs.append(cls.cpu().to(torch.float16).numpy())
            idxs.extend(batch_idx)
            fps.extend(batch_fp)
            done += len(batch_idx)
            if done % 2560 == 0:
                print(f"  {done}/{len(rows)}")

    embeddings = np.concatenate(embs, axis=0)
    np.savez_compressed(
        args.out,
        idx=np.array(idxs, dtype=np.int32),
        embeddings=embeddings,
        filepaths=np.array(fps),
        model=args.model,
    )
    print(f"saved {embeddings.shape} -> {args.out}")


def _collate(batch):
    idxs = [b[0] for b in batch]
    fps = [b[1] for b in batch]
    pix = torch.stack([b[2] for b in batch])
    return idxs, fps, pix


if __name__ == "__main__":
    main()
