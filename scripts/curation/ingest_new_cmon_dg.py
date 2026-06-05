"""Ingest newly-scraped CMON Death Guard images into the gallery (depth top-up).

Run after `scripts/cmon/cmon_scrape.py single` pulls more entries. Scans
`entries_single.jsonl` for Death Guard entries (keyword match on title/desc),
and for each DG image on disk that isn't already in `wh40k_pile`:
  - embeds it with frozen dinov2-large (CLS token, L2-normalized — the pile recipe)
  - adds a FiftyOne sample (source=cmon, faction_v1=death_guard, weak_unit from
    title, pool=gallery, provenance from the entry).

DG-only by design: the other newly-scraped factions stay on disk for a future
full ingest; here we just deepen the DG gallery. Idempotent (skips filepaths
already present).

  fiftyone_env/bin/python scripts/curation/ingest_new_cmon_dg.py [--run single] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# shared DG detection + unit mapping (kept in sync with seed_dg_gallery.py)
DG_KEYWORDS = [
    "death guard", "death-guard", "deathguard", "nurgle", "plague marine",
    "poxwalker", "mortarion", "typhus", "deathshroud", "blightlord", "bloat drone",
    "plaguebearer", "foul blight", "biologus", "plague", "rotbone", "myphitic",
    "malignant",
]
UNIT_MAP = [
    ("mortarion", "daemon_primarch_mortarion"), ("typhus", "death_guard_typhus"),
    ("deathshroud", "deathshroud_bodyguard"), ("poxwalker", "csmdg_poxwalkers"),
    ("blight-hauler", "myphitic_blight_hauler"), ("blighthauler", "myphitic_blight_hauler"),
    ("blight hauler", "myphitic_blight_hauler"), ("biologus", "biologus_putrifier"),
    ("bloat drone", "bloat_drone"), ("blightlord", "death_guard_blight_lord_terminators"),
    ("plaguebearer", "plaguebearers"), ("foul blight", "death_guard_foul_blight_spawn"),
]
MODEL = "facebook/dinov2-large"


def _unit(title: str) -> str:
    t = title.lower()
    for kw, slug in UNIT_MAP:
        if kw in t:
            return slug
    return "plague_marines"


def _embed(paths: list[Path]):
    import torch
    from PIL import Image
    from transformers import AutoImageProcessor, AutoModel

    proc = AutoImageProcessor.from_pretrained(MODEL)
    model = AutoModel.from_pretrained(MODEL).eval()
    vecs = []
    with torch.no_grad():
        for i in range(0, len(paths), 16):
            imgs = [Image.open(p).convert("RGB") for p in paths[i:i + 16]]
            pix = proc(images=imgs, return_tensors="pt")["pixel_values"]
            cls = model(pixel_values=pix).last_hidden_state[:, 0]
            cls = torch.nn.functional.normalize(cls, dim=1)
            vecs.extend(cls.to(torch.float16).numpy())
            print(f"  embedded {min(i + 16, len(paths))}/{len(paths)}")
    return vecs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="single")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import fiftyone as fo
    from fiftyone import ViewField as F

    entries_file = Path(f"scripts/cmon/data/entries_{args.run}.jsonl")
    img_root = Path(f"scripts/cmon/images/{args.run}")

    # DG entries → unit + url
    dg = {}
    for line in entries_file.read_text().splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        text = (r.get("title", "") + " " + r.get("description", "") + " "
                + " ".join(r.get("tags", []))).lower()
        if any(k in text for k in DG_KEYWORDS):
            dg[str(r["id"])] = {"unit": _unit(r.get("title", "")), "url": r.get("url", "")}
    print(f"DG entries in {entries_file.name}: {len(dg)}")

    ds = fo.load_dataset("wh40k_pile")
    have = set(ds.values("filepath"))

    new = []  # (abs_path, unit, url)
    for eid, meta in dg.items():
        d = img_root / eid
        if not d.is_dir():
            continue
        for img in sorted(d.glob("*.jpg")):
            ap_ = str(img.resolve())
            if ap_ in have:
                continue
            new.append((ap_, meta["unit"], meta["url"]))
    print(f"new DG images to ingest: {len(new)}")
    if not new or args.dry_run:
        print("(dry-run or nothing new)")
        return

    vecs = _embed([Path(p) for p, _, _ in new])
    samples = []
    for (path, unit, url), v in zip(new, vecs):
        samples.append(fo.Sample(
            filepath=path, source="cmon", corpus="cmon",
            weak_faction="death_guard", faction_v1="death_guard",
            weak_unit=unit, pool="gallery",
            source_url=url, label_source="cmon_title", label_confidence=0.5,
            embedding=v,
        ))
    ds.add_samples(samples)
    gal = ds.match(F("pool") == "gallery")
    ds.save_view("gallery", gal, overwrite=True)
    dgg = gal.match(F("faction_v1") == "death_guard")
    print(f"added {len(samples)} → DG gallery now {dgg.count()} crops / "
          f"{len(set(dgg.values('weak_unit')))} units")


if __name__ == "__main__":
    main()
