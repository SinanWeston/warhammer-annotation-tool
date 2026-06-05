"""Ingest the already-scraped-but-un-ingested GW-shop product shots.

~4.4k GW-shop images are on disk (scripts/warhammer_com/images/{faction}/{unit}/)
but only ~3k are in wh40k_pile — ~1.4k canonical per-unit product photos were
scraped and never ingested. This adds them: faction + unit come straight from the
directory path, embed with frozen dinov2-large (CLS, L2-norm — the pile recipe),
and (because they carry a weak_unit) they land in the gallery per the build_pools
rule. faction_v1 is set only for the four v1 factions; others get weak_faction only.

Idempotent (skips basenames already in the pile). CPU embedding — slow but offline.

  fiftyone_env/bin/python scripts/curation/ingest_gw_shop_backlog.py [--dry-run]
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

IMG_ROOT = Path("scripts/warhammer_com/images")
MODEL = "facebook/dinov2-large"
V1 = {"space_marines", "necrons", "tyranids", "death_guard"}


def _embed(paths, batch=16):
    import torch
    from PIL import Image
    from transformers import AutoImageProcessor, AutoModel

    proc = AutoImageProcessor.from_pretrained(MODEL)
    model = AutoModel.from_pretrained(MODEL).eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(paths), batch):
            imgs = []
            for p in paths[i:i + batch]:
                try:
                    imgs.append(Image.open(p).convert("RGB"))
                except Exception:
                    imgs.append(Image.new("RGB", (224, 224)))
            pix = proc(images=imgs, return_tensors="pt")["pixel_values"]
            cls = model(pixel_values=pix).last_hidden_state[:, 0]
            cls = torch.nn.functional.normalize(cls, dim=1)
            out.extend(cls.to(torch.float16).numpy())
            if (i // batch) % 10 == 0:
                print(f"  embedded {min(i + batch, len(paths))}/{len(paths)}", flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import collections

    import fiftyone as fo
    from fiftyone import ViewField as F

    ds = fo.load_dataset("wh40k_pile")
    have = {os.path.basename(p) for p in ds.values("filepath")}

    todo = []  # (path, faction, unit)
    for f in IMG_ROOT.glob("*/*/*.jpg"):
        if f.name in have:
            continue
        parts = f.parts
        faction, unit = parts[-3], parts[-2]
        todo.append((str(f.resolve()), faction, unit))
    by_fac = collections.Counter(t[1] for t in todo)
    print(f"un-ingested gw_shop images: {len(todo)}")
    print("by faction:", dict(by_fac.most_common()))
    if not todo or args.dry_run:
        print("(dry-run or nothing to do)")
        return

    vecs = _embed([t[0] for t in todo])
    samples = []
    for (path, faction, unit), v in zip(todo, vecs):
        samples.append(fo.Sample(
            filepath=path, source="gw_shop", corpus="gw_shop",
            weak_faction=faction,
            faction_v1=(faction if faction in V1 else None),
            weak_unit=unit, pool="gallery",
            label_source="gw_shop_path", label_confidence=0.6,
            embedding=v,
        ))
    ds.add_samples(samples)
    gal = ds.match(F("pool") == "gallery")
    ds.save_view("gallery", gal, overwrite=True)
    print(f"\nadded {len(samples)} gw_shop crops → gallery; gallery now {gal.count()}")
    for fac in sorted(V1):
        fg = gal.match(F("weak_faction") == fac)
        print(f"  {fac}: {fg.count()} gallery crops / "
              f"{len(set(fg.values('weak_unit')))} units")


if __name__ == "__main__":
    main()
