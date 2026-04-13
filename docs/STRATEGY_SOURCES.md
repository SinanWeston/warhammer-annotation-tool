# Strategy — Research Sources

Companion to [../STRATEGY.md](../STRATEGY.md). Full bibliography and working links for every claim in the strategy document.

## Foundation vision models

- [DINOv2 — Meta, 2023](https://arxiv.org/abs/2304.07193) — self-supervised ViT, frozen features beat supervised ResNets on fine-grained benchmarks.
- [DINOv2 with Registers — 2024](https://arxiv.org/abs/2309.16588) — fixes artifact tokens; small gains on dense tasks.
- [DINOv3 — Meta, 2025](https://ai.meta.com/blog/dinov3-self-supervised-vision-model/) — 7B-param ViT, 1.7B training images.
- [SigLIP 2 — Google, 2025](https://arxiv.org/abs/2502.14786) — current open-weights SOTA for CLIP-style retrieval.

## Open-vocabulary / prompt-driven detection

- [T-Rex2 — IDEA Research, ECCV 2024](https://arxiv.org/abs/2403.14610) · [GitHub](https://github.com/IDEA-Research/T-Rex) — text + visual prompt synergy; +5.6 AP over text on ODinW, +9.2 on Roboflow100.
- [OWLv2 — Google, 2023](https://arxiv.org/abs/2306.09683) — image-conditioned detection; strong zero-shot AP on LVIS.
- [Grounding DINO — IDEA, 2023](https://arxiv.org/abs/2303.05499) — already integrated in this codebase via `scripts/grounding_dino_propose.py`.
- [Grounded-SAM — 2024](https://arxiv.org/abs/2401.14159) — Grounding DINO feeds SAM for mask-level segmentation.
- [YOLO-World — 2024](https://arxiv.org/abs/2401.17270) — real-time open-vocabulary, weaker than Grounding DINO but fast.

## Counting in crowded scenes

- [CountGD — Oxford VGG, 2024](https://arxiv.org/abs/2407.04619) — open-world counting from text + examples; SOTA on FSC-147.
- [P2PNet — 2021](https://arxiv.org/abs/2107.12746) — point-based detection, beats bboxes on dense scenes.
- [SAM 2 — Meta, 2024](https://arxiv.org/abs/2408.00714) — class-agnostic segmentation, suits mask-then-classify pipelines.

## Synthetic data and domain randomization

- [Training Deep Networks with Synthetic Data — Tremblay / NVIDIA, 2018](https://arxiv.org/abs/1804.06516) — the foundational domain randomization paper.
- [BlenderProc — 2023](https://arxiv.org/abs/2303.13404) — the production-grade procedural rendering pipeline to use.

## Production analogs (retrieval at scale)

- [A deep learning pipeline for product recognition — Tonioni et al., 2018](https://arxiv.org/abs/1810.01733) — closest architectural analog: class-agnostic detection + embedding retrieval against catalog.
- [Ximilar — Pokémon card image search engine](https://www.ximilar.com/blog/pokemon-card-image-search-engine/) — why they abandoned CNN classifiers at scale.
- [Ximilar — Visual AI for collectibles](https://www.ximilar.com/services/visual-ai-for-collectibles/)
- [YOLO + CLIP retrieval pattern — Akshay Ballal](https://www.akshaymakes.com/blogs/clip-yolo) — practical writeup of the pattern we're adopting.
- [Detecting 100,000 classes on a single machine — Google](https://research.google.com/pubs/archive/40814.pdf) — retrieval-based scaling argument.
- [Voxel51 — best embedding models for image classification](https://voxel51.com/blog/finding-the-best-embedding-model-for-image-classification) — current benchmarks across embedding models.

## VLM fine-grained failure cases

- ["Eyes Wide Shut" — Tong et al., 2024](https://arxiv.org/abs/2401.06209) — systematic study of VLM failures on fine visual details. Informs why VLMs are a Tier 4 fallback, not a primary classifier.

## Warhammer-specific assets

### Existing public CV work (thin)

- [Roboflow: Warhammer 40K miniature dataset (97 images)](https://universe.roboflow.com/davide-puopolo-9xomj/warhammer-40.000-miniature)
- [Roboflow: Warhammer 40K minins (35 images)](https://universe.roboflow.com/jonas-krger/warhammer-40k-minins)

### Reference corpora (for seeding the gallery)

- [Lexicanum — fan wiki, Category:Images](https://wh40k.lexicanum.com/wiki/Main_Page) — cleanest labelled miniature photos.
- [Wahapedia](https://wahapedia.ru/wh40k10ed/) — canonical unit taxonomy + point values. Scrapeable.
- Games Workshop product pages on `warhammer.com` — one canonical studio photo per kit.

### 3D models (for synthetic rendering)

- [Cults3D — 3,900+ free Warhammer 40K STL models](https://cults3d.com/en/tags/warhammer_40k)
- [CGTrader — 3,700+ Warhammer 40K 3D models](https://www.cgtrader.com/3d-print-models/warhammer-40k)
- [Sketchfab — CountCurls Warhammer 40K collection](https://sketchfab.com/CountCurls/collections/warhammer-40k-models-4c7f6de97c14407bb884fcaea9bdc4a6)
- [STLFinder — Warhammer 40K aggregator](https://www.stlfinder.com/3dmodels/warhammer-40k-3d-models/)

### Adjacent tabletop dataset

- [TO-Scene — tabletop scenes, 60K instances, 52 classes](https://arxiv.org/abs/2203.09440) — useful for domain-adaptation pretraining if we pivot there.
