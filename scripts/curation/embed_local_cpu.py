"""Embed the un-embedded pile samples locally on CPU and attach to FiftyOne.

For small batches (e.g. the 5,155 warhammer_community + 314 roboflow samples)
a Colab round-trip is overkill — dinov2-large on a 12-core CPU does ~1-2
img/s, so a few thousand images is an hour, not a session. Matches the
canonical recipe exactly: 384px downsize (the bundle recipe), dinov2-large
CLS token, L2-normalized, float16.

ATTACH-ONLY: this does NOT run the brain near-dup/uniqueness pass that
load_embeddings.py runs — re-tagging `dup` over the whole pile is a deliberate
curation decision, not a side effect. Run that separately when re-pooling.

Resumable: only samples with `embedding == None` are selected.

  fiftyone_env/bin/python scripts/curation/embed_local_cpu.py [--limit N] [--npz out.npz]
"""
from __future__ import annotations

import argparse

import numpy as np


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="wh40k_pile")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--npz", default="", help="optional side-dump of the new embeddings")
    args = ap.parse_args()

    import fiftyone as fo
    import torch
    from PIL import Image, ImageOps
    from transformers import AutoImageProcessor, AutoModel

    Image.MAX_IMAGE_PIXELS = None
    torch.set_num_threads(max(1, (torch.get_num_threads() or 4) - 2))

    ds = fo.load_dataset(args.name)
    todo = ds.match({"embedding": None})
    n_todo = todo.count()
    print(f"{n_todo} samples without embedding")
    if not n_todo:
        return

    proc = AutoImageProcessor.from_pretrained("facebook/dinov2-large")
    model = AutoModel.from_pretrained("facebook/dinov2-large").eval()

    done = failed = 0
    dump_fps, dump_vecs = [], []
    batch_samples, batch_imgs = [], []

    def flush():
        nonlocal done, batch_samples, batch_imgs
        if not batch_imgs:
            return
        pix = proc(images=batch_imgs, return_tensors="pt")["pixel_values"]
        with torch.no_grad():
            cls = model(pixel_values=pix).last_hidden_state[:, 0]
            cls = torch.nn.functional.normalize(cls, dim=1)
        vecs = cls.to(torch.float16).numpy()
        for s, v in zip(batch_samples, vecs):
            s["embedding"] = v
            s.save()
            if args.npz:
                dump_fps.append(s.filepath)
                dump_vecs.append(v)
        done += len(batch_samples)
        if done % 80 < args.batch:
            print(f"  {done}/{n_todo} embedded ({failed} failed)", flush=True)
        batch_samples, batch_imgs = [], []

    for s in todo.iter_samples(progress=False):
        if args.limit and done + len(batch_imgs) >= args.limit:
            break
        try:
            with Image.open(s.filepath) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((384, 384), Image.BILINEAR)  # bundle recipe
                batch_imgs.append(im.copy())
            batch_samples.append(s)
        except Exception as e:
            failed += 1
            print(f"  FAIL {s.filepath}: {type(e).__name__}", flush=True)
            continue
        if len(batch_imgs) >= args.batch:
            flush()
    flush()

    print(f"done: {done} embedded, {failed} unreadable")
    if args.npz and dump_vecs:
        np.savez_compressed(args.npz, filepaths=np.array(dump_fps),
                            embeddings=np.stack(dump_vecs),
                            model="facebook/dinov2-large")
        print(f"side-dump -> {args.npz}")


if __name__ == "__main__":
    main()
