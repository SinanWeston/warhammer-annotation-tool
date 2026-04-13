#!/usr/bin/env python3
"""
Phase 1 — embed every gallery image with DINOv3 (or DINOv2 fallback) and
save the index as a numpy .npz.

Output arrays:
    embeddings  (N, 768)  float32, L2-normalised
    paths       (N,)      str — relative crop paths
    factions    (N,)      str
    units       (N,)      str  (unit_slug)

If DINOv3 is gated on HuggingFace (403), falls back to `facebook/dinov2-base`
automatically and records the actual model used in the output .npz under
the key `model_id`.

Usage:
    yolo_env/bin/python3 scripts/phase1/embed_gallery.py
    yolo_env/bin/python3 scripts/phase1/embed_gallery.py --model facebook/dinov2-base
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE1 = REPO_ROOT / "scripts" / "phase1"
GALLERY_DIR = PHASE1 / "gallery"
OUT_PATH = PHASE1 / "gallery_embeddings.npz"

DEFAULT_MODEL = "facebook/dinov3-vitb16-pretrain-lvd1689m"
FALLBACK_MODEL = "facebook/dinov2-base"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"HuggingFace model id. Default: {DEFAULT_MODEL}. Fallback: {FALLBACK_MODEL}.")
    p.add_argument("--batch", type=int, default=8, help="Embedding batch size")
    p.add_argument("--device", default=None, help="Explicit device (e.g. 'cuda:0'). Auto-detect if unset.")
    p.add_argument("--out", default=str(OUT_PATH))
    return p.parse_args()


def walk_gallery() -> list[tuple[str, str, str, Path]]:
    """Yield (faction, unit, rel_path, abs_path) for every gallery image."""
    if not GALLERY_DIR.exists():
        sys.exit(f"Gallery directory not found at {GALLERY_DIR}. Run build_gallery.py first.")
    out = []
    for faction_dir in sorted(p for p in GALLERY_DIR.iterdir() if p.is_dir()):
        faction = faction_dir.name
        for unit_dir in sorted(p for p in faction_dir.iterdir() if p.is_dir()):
            unit = unit_dir.name
            for img in sorted(unit_dir.iterdir()):
                if img.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                    out.append((faction, unit, str(img.relative_to(REPO_ROOT)), img))
    return out


def load_model(model_id: str, device: str):
    """Load HF model + processor. Returns (model, processor, actual_model_id)."""
    from transformers import AutoImageProcessor, AutoModel
    try:
        processor = AutoImageProcessor.from_pretrained(model_id)
        model = AutoModel.from_pretrained(model_id).to(device).eval()
        return model, processor, model_id
    except Exception as e:
        msg = str(e)
        if "403" in msg or "gated" in msg.lower() or "access" in msg.lower():
            print(f"⚠ {model_id} appears gated: {e}")
            print(f"  Falling back to {FALLBACK_MODEL}.")
            processor = AutoImageProcessor.from_pretrained(FALLBACK_MODEL)
            model = AutoModel.from_pretrained(FALLBACK_MODEL).to(device).eval()
            return model, processor, FALLBACK_MODEL
        raise


def main():
    args = parse_args()

    try:
        import numpy as np
        import torch
        from PIL import Image
    except ImportError as e:
        sys.exit(f"Missing dependency: {e}. Run from yolo_env.")

    device = args.device or ("cuda:0" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    entries = walk_gallery()
    if not entries:
        sys.exit(f"No gallery images found under {GALLERY_DIR}.")
    print(f"Embedding {len(entries)} gallery images...")

    model, processor, actual_model = load_model(args.model, device)
    print(f"Model: {actual_model}")

    factions, units, paths = [], [], []
    all_embeds = []

    with torch.no_grad():
        for i in range(0, len(entries), args.batch):
            batch = entries[i : i + args.batch]
            imgs = [Image.open(e[3]).convert("RGB") for e in batch]
            inputs = processor(images=imgs, return_tensors="pt").to(device)
            outputs = model(**inputs)
            # Prefer pooler_output, fall back to CLS of last_hidden_state.
            if getattr(outputs, "pooler_output", None) is not None:
                embed = outputs.pooler_output
            else:
                embed = outputs.last_hidden_state[:, 0]
            embed = torch.nn.functional.normalize(embed, p=2, dim=-1)
            all_embeds.append(embed.cpu().numpy())
            for faction, unit, rel, _ in batch:
                factions.append(faction)
                units.append(unit)
                paths.append(rel)
            print(f"  {min(i + args.batch, len(entries))}/{len(entries)}")

    embeddings = np.concatenate(all_embeds, axis=0).astype(np.float32)

    out_path = Path(args.out)
    np.savez(
        out_path,
        embeddings=embeddings,
        paths=np.array(paths),
        factions=np.array(factions),
        units=np.array(units),
        model_id=np.array(actual_model),
    )
    print(f"\nWrote {out_path.relative_to(REPO_ROOT)}")
    print(f"  shape={embeddings.shape}  dtype={embeddings.dtype}")


if __name__ == "__main__":
    main()
