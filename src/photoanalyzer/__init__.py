"""photoanalyzer — Warhammer 40K miniature recognition pipeline.

Modules:
- taxonomy: canonical factions + unit slugs (wraps scripts/data/units.json)
- detect: class-agnostic detection (YOLO, OWLv2)
- classify: faction classification (KNN, linear probe)
- retrieve: unit retrieval gallery (DINOv2, SigLIP embeddings)
- label: weak supervision + LLM-assisted labelling + active-learning queue
- scrape: pluggable Source abstraction (GW shop, CMON, Dakka, Reddit, etc.)
- eval: per-crop + scene-level benchmarks
- pipeline: end-to-end orchestration
- server: FastAPI inference server (loaded lazily to keep import cheap)
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
