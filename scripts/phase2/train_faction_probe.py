"""Train the production Tier 2 faction probe and save the artifact.

Trains `photoanalyzer.classify.FactionProbe` (the benched recipe) on the
current FiftyOne gallery embeddings and writes `models/tier2_faction_probe.joblib`
(gitignored — retrain after any gallery change; this script IS the provenance).

  fiftyone_env/bin/python scripts/phase2/train_faction_probe.py
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from photoanalyzer.classify import FactionProbe  # noqa: E402
from photoanalyzer.taxonomy import V1_FACTIONS  # noqa: E402

OUT = Path("models/tier2_faction_probe.joblib")


def main() -> None:
    import fiftyone as fo
    from fiftyone import ViewField as F

    ds = fo.load_dataset("wh40k_pile")
    gal = ds.match((F("pool") == "gallery") & (F("embedding") != None))  # noqa: E711
    facs, embs = gal.values(["weak_faction", "embedding"])
    X = np.stack([np.asarray(e, np.float32) for e in embs])
    y = [str(f) for f in facs]
    counts = collections.Counter(y)
    print(f"training on {len(y)} gallery crops, {len(counts)} factions")
    for f in V1_FACTIONS:
        print(f"  {f:14} {counts.get(f, 0):5}")

    probe = FactionProbe().fit(X, y)
    missing = [f for f in V1_FACTIONS if f not in probe.classes]
    if missing:
        raise SystemExit(f"v1 factions missing from gallery: {missing} — "
                         "the v1-restricted production path would crash. Fix the "
                         "gallery first.")
    probe.save(OUT)
    print(f"saved {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
