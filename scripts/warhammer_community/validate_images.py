#!/usr/bin/env python3
"""
Post-scrape validation for Warhammer Community images.

Two-stage automated pipeline:

  Stage 1 — CLIP zero-shot classification
    Each image is scored against text prompts:
      "a painted Warhammer miniature on display"
      "a close-up of a painted Warhammer miniature"
      "a paint pot or hobby supply"
      "a diagram, chart, or infographic"
      "artwork or illustration"
      "a photograph of a person"
      "a gaming table or battlefield"
      "a book or product box"
      "a screenshot of a website or app"
    Images where "painted miniature" (either prompt) is the top class AND
    score exceeds a threshold are kept. Others are quarantined.

  Stage 2 — DINOv2 cross-validation against the GW shop gallery
    Each CLIP-approved image is embedded with DINOv2 and matched against
    the pre-computed GW shop gallery embeddings (scripts/phase3/gallery_embeddings.npz).
    If the nearest match's faction matches the article's faction tag →
    high confidence. If mismatch → flagged for human review.

Output:
  state/validation.csv — per-image scores: clip_top_class, clip_score,
                          dino_match_faction, dino_match_unit, dino_cosine,
                          verdict (clean/quarantine/review)
  Images with verdict=quarantine are moved to images/_non_miniature/
  Images with verdict=review stay in place but are listed for human triage.

Usage:
    yolo_env/bin/python3 scripts/warhammer_community/validate_images.py              # dry-run
    yolo_env/bin/python3 scripts/warhammer_community/validate_images.py --apply      # move
    yolo_env/bin/python3 scripts/warhammer_community/validate_images.py --stage clip # CLIP only
    yolo_env/bin/python3 scripts/warhammer_community/validate_images.py --stage dino # DINOv2 only
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# ─── Config ─────────────────────────────────────────────────────────────────

IMAGES_ROOT = HERE / "images"
STATE_DIR = HERE / "state"
VALIDATION_CSV = STATE_DIR / "validation.csv"
QUARANTINE_DIR = IMAGES_ROOT / "_non_miniature"

GALLERY_EMBEDDINGS = REPO_ROOT / "scripts" / "phase3" / "gallery_embeddings.npz"

# CLIP
CLIP_MODEL = "ViT-B-32"
CLIP_PRETRAINED = "openai"
CLIP_MINIATURE_THRESHOLD = 0.24  # calibrate on first run; ~0.24 typical for openai ViT-B-32

CLIP_PROMPTS = {
    "painted_miniature": [
        "a painted Warhammer miniature figurine on display",
        "a close-up photograph of a painted tabletop gaming miniature",
    ],
    "paint_supply": [
        "a paint pot or hobby painting supply",
        "bottles of acrylic paint and paintbrushes",
    ],
    "diagram": [
        "a diagram, chart, or infographic",
        "a rules reference card or datasheet",
    ],
    "artwork": [
        "fantasy or science fiction artwork and illustration",
        "a digital painting or concept art",
    ],
    "person": [
        "a photograph of a person or people",
        "a portrait photo of someone at an event",
    ],
    "table": [
        "a gaming table with terrain and miniatures from far away",
        "a wide shot of a wargaming battlefield",
    ],
    "product": [
        "a product box or packaging",
        "a book cover or rulebook",
    ],
    "screenshot": [
        "a screenshot of a website, video game, or app",
    ],
}

# ─── Data structures ────────────────────────────────────────────────────────

@dataclass
class ImageValidation:
    path: Path
    faction: str
    article_slug: str
    # CLIP
    clip_top_class: str
    clip_score: float
    clip_is_miniature: bool
    # DINOv2
    dino_match_faction: str
    dino_match_unit: str
    dino_cosine: float
    dino_faction_matches: bool
    # Final
    verdict: str  # "clean" | "quarantine" | "review"


# ─── CLIP Stage ─────────────────────────────────────────────────────────────

class CLIPClassifier:
    def __init__(self, device: str = "cpu"):
        import open_clip
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            CLIP_MODEL, pretrained=CLIP_PRETRAINED, device=device,
        )
        self.tokenizer = open_clip.get_tokenizer(CLIP_MODEL)
        self.device = device

        # Pre-encode all text prompts → one embedding per class (average of variants)
        self.class_names: list[str] = []
        self.text_features: torch.Tensor | None = None
        self._encode_prompts()

    def _encode_prompts(self) -> None:
        all_embeddings: list[torch.Tensor] = []
        for cls_name, prompts in CLIP_PROMPTS.items():
            self.class_names.append(cls_name)
            tokens = self.tokenizer(prompts).to(self.device)
            with torch.no_grad():
                feats = self.model.encode_text(tokens)
                feats = feats / feats.norm(dim=-1, keepdim=True)
                avg = feats.mean(dim=0)
                avg = avg / avg.norm()
            all_embeddings.append(avg)
        self.text_features = torch.stack(all_embeddings)

    def classify(self, img_path: Path) -> tuple[str, float]:
        """Return (top_class_name, score) for the image."""
        img = Image.open(img_path).convert("RGB")
        img_tensor = self.preprocess(img).unsqueeze(0).to(self.device)
        with torch.no_grad():
            img_feat = self.model.encode_image(img_tensor)
            img_feat = img_feat / img_feat.norm(dim=-1, keepdim=True)
            sims = (img_feat @ self.text_features.T).squeeze(0)
        probs = sims.softmax(dim=0).cpu().numpy()
        top_idx = int(probs.argmax())
        return self.class_names[top_idx], float(probs[top_idx])

    def is_miniature(self, img_path: Path) -> tuple[bool, str, float]:
        """Return (is_mini, top_class, score)."""
        cls, score = self.classify(img_path)
        is_mini = cls == "painted_miniature" and score >= CLIP_MINIATURE_THRESHOLD
        return is_mini, cls, score


# ─── DINOv2 Stage ───────────────────────────────────────────────────────────

class DINOv2Validator:
    def __init__(self, device: str = "cpu"):
        from transformers import AutoImageProcessor, AutoModel
        model_id = "facebook/dinov2-base"
        self.processor = AutoImageProcessor.from_pretrained(model_id)
        self.model = AutoModel.from_pretrained(model_id).to(device)
        self.model.eval()
        self.device = device

        # Load pre-computed gallery embeddings
        data = np.load(str(GALLERY_EMBEDDINGS), allow_pickle=True)
        self.gallery_embs = data["embeddings"]  # (N, 768) L2-normalized
        self.gallery_factions = data["factions"]
        self.gallery_units = data["units"]
        print(f"  Gallery loaded: {self.gallery_embs.shape[0]} images, "
              f"{len(set(self.gallery_factions))} factions", flush=True)

    def embed(self, img_path: Path) -> np.ndarray:
        img = Image.open(img_path).convert("RGB")
        inputs = self.processor(images=img, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = self.model(**inputs)
        cls_token = outputs.last_hidden_state[:, 0].cpu().numpy().squeeze()
        cls_token = cls_token / (np.linalg.norm(cls_token) + 1e-8)
        return cls_token

    def match(self, img_path: Path) -> tuple[str, str, float]:
        """Return (faction, unit_slug, cosine_similarity) of nearest gallery image."""
        emb = self.embed(img_path)
        sims = self.gallery_embs @ emb
        top_idx = int(sims.argmax())
        return (
            str(self.gallery_factions[top_idx]),
            str(self.gallery_units[top_idx]),
            float(sims[top_idx]),
        )


# ─── Image iterator ─────────────────────────────────────────────────────────

def _iter_images() -> list[tuple[Path, str, str]]:
    """Yield (path, faction, article_slug) for all downloaded images."""
    out: list[tuple[Path, str, str]] = []
    for faction_dir in sorted(IMAGES_ROOT.iterdir()):
        if not faction_dir.is_dir() or faction_dir.name.startswith("_"):
            continue
        faction = faction_dir.name
        for article_dir in sorted(faction_dir.iterdir()):
            if not article_dir.is_dir():
                continue
            slug = article_dir.name
            for img in sorted(article_dir.glob("*.jpg")):
                out.append((img, faction, slug))
    return out


# ─── Main pipeline ──────────────────────────────────────────────────────────

def run(
    stage: str = "both",
    apply_changes: bool = False,
    batch_size: int = 50,
) -> None:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}", flush=True)

    images = _iter_images()
    print(f"Images to validate: {len(images)}", flush=True)
    if not images:
        print("No images found. Run the scraper first.")
        return

    results: list[ImageValidation] = []

    # ── Stage 1: CLIP ──
    if stage in ("both", "clip"):
        print("\n=== Stage 1: CLIP zero-shot classification ===", flush=True)
        clip = CLIPClassifier(device=device)
        for i, (path, faction, slug) in enumerate(images):
            is_mini, cls, score = clip.is_miniature(path)
            results.append(ImageValidation(
                path=path, faction=faction, article_slug=slug,
                clip_top_class=cls, clip_score=score, clip_is_miniature=is_mini,
                dino_match_faction="", dino_match_unit="", dino_cosine=0.0,
                dino_faction_matches=False,
                verdict="",
            ))
            if (i + 1) % batch_size == 0:
                n_mini = sum(1 for r in results if r.clip_is_miniature)
                print(f"  {i+1}/{len(images)}  miniatures so far: {n_mini}", flush=True)

        n_mini = sum(1 for r in results if r.clip_is_miniature)
        n_other = len(results) - n_mini
        print(f"  CLIP done: {n_mini} miniatures, {n_other} non-miniatures", flush=True)

        # Class distribution
        from collections import Counter
        cls_dist = Counter(r.clip_top_class for r in results)
        print("  Class distribution:")
        for c, n in cls_dist.most_common():
            print(f"    {c:25s}  {n:5d}")
    else:
        # Load prior CLIP results from CSV
        if VALIDATION_CSV.exists():
            for row in csv.DictReader(VALIDATION_CSV.open()):
                path = Path(row["path"])
                if path.exists():
                    results.append(ImageValidation(
                        path=path,
                        faction=row["faction"],
                        article_slug=row["article_slug"],
                        clip_top_class=row["clip_top_class"],
                        clip_score=float(row["clip_score"]),
                        clip_is_miniature=row["clip_is_miniature"] == "True",
                        dino_match_faction="", dino_match_unit="", dino_cosine=0.0,
                        dino_faction_matches=False,
                        verdict="",
                    ))

    # ── Stage 2: DINOv2 cross-validation (PRIMARY filter — runs on ALL images) ──
    if stage in ("both", "dino"):
        if not GALLERY_EMBEDDINGS.exists():
            print(f"\n⚠ Gallery embeddings not found at {GALLERY_EMBEDDINGS}")
            print("  Run scripts/phase3/embed_gallery.py first.")
            print("  Skipping DINOv2 stage.")
        else:
            # When running dino-only without prior CLIP, build results from disk
            if not results:
                for path, faction, slug in images:
                    results.append(ImageValidation(
                        path=path, faction=faction, article_slug=slug,
                        clip_top_class="", clip_score=0.0, clip_is_miniature=False,
                        dino_match_faction="", dino_match_unit="", dino_cosine=0.0,
                        dino_faction_matches=False, verdict="",
                    ))

            print(f"\n=== Stage 2: DINOv2 cross-validation ({len(results)} images) ===",
                  flush=True)
            dino = DINOv2Validator(device=device)
            for i, r in enumerate(results):
                match_faction, match_unit, cosine = dino.match(r.path)
                r.dino_match_faction = match_faction
                r.dino_match_unit = match_unit
                r.dino_cosine = cosine
                r.dino_faction_matches = (
                    r.faction != "unknown" and r.faction == match_faction
                )
                if (i + 1) % batch_size == 0:
                    n_keep = sum(1 for x in results[:i+1] if x.dino_cosine >= 0.35)
                    print(f"  {i+1}/{len(results)}  miniatures (cosine≥0.35): {n_keep}",
                          flush=True)

            n_match = sum(1 for r in results if r.dino_faction_matches)
            n_unknown = sum(1 for r in results if r.faction == "unknown")
            n_mismatch = sum(1 for r in results if r.faction != "unknown" and not r.dino_faction_matches and r.dino_cosine > 0)
            print(f"  DINOv2 done: {n_match} faction-matched, {n_unknown} unknown-faction, "
                  f"{n_mismatch} mismatched", flush=True)

            # Cosine distribution
            scores = [r.dino_cosine for r in results]
            print(f"  Cosine: min={min(scores):.3f} max={max(scores):.3f} mean={sum(scores)/len(scores):.3f}")
            for thresh in (0.25, 0.30, 0.35, 0.40, 0.45, 0.50):
                n = sum(1 for s in scores if s >= thresh)
                print(f"    ≥{thresh:.2f}: {n:5d} ({100*n/len(scores):.0f}%)")

    # ── Assign verdicts ──
    # Primary signal: DINOv2 cosine to nearest gallery image.
    # If the image is visually close to ANY GW shop miniature, it's a miniature.
    # CLIP top-class is secondary / tiebreaker.
    DINO_KEEP_THRESHOLD = 0.71   # cosine ≥ 0.71 → confident miniature (user-calibrated)
    DINO_REVIEW_THRESHOLD = 0.50 # cosine 0.50-0.71 → uncertain, human review
    # Below 0.50 → quarantine (junk)

    for r in results:
        if r.dino_cosine >= DINO_KEEP_THRESHOLD:
            r.verdict = "clean"
        elif r.dino_cosine >= DINO_REVIEW_THRESHOLD:
            r.verdict = "review"
        elif r.dino_cosine > 0.0:
            r.verdict = "quarantine"
        elif r.clip_is_miniature:
            # No DINOv2 data but CLIP says miniature → keep cautiously
            r.verdict = "review"
        else:
            r.verdict = "quarantine"

    # ── Write audit CSV ──
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with VALIDATION_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "path", "faction", "article_slug",
            "clip_top_class", "clip_score", "clip_is_miniature",
            "dino_match_faction", "dino_match_unit", "dino_cosine", "dino_faction_matches",
            "verdict",
        ])
        for r in sorted(results, key=lambda x: (x.verdict, str(x.path))):
            w.writerow([
                str(r.path), r.faction, r.article_slug,
                r.clip_top_class, f"{r.clip_score:.4f}", r.clip_is_miniature,
                r.dino_match_faction, r.dino_match_unit, f"{r.dino_cosine:.4f}",
                r.dino_faction_matches, r.verdict,
            ])

    # Summary
    from collections import Counter
    verdicts = Counter(r.verdict for r in results)
    print(f"\n=== Validation summary ===")
    for v in ("clean", "review", "quarantine"):
        print(f"  {v:12s}  {verdicts.get(v, 0):5d}")
    print(f"  total       {len(results):5d}")
    print(f"\nAudit written to {VALIDATION_CSV}")

    # ── Apply: move quarantined images ──
    if apply_changes:
        quarantine = [r for r in results if r.verdict == "quarantine"]
        print(f"\n=== Moving {len(quarantine)} non-miniature images to {QUARANTINE_DIR} ===",
              flush=True)
        moved = 0
        for r in quarantine:
            try:
                rel = r.path.relative_to(IMAGES_ROOT)
            except ValueError:
                continue
            dst = QUARANTINE_DIR / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(r.path), str(dst))
            moved += 1
        print(f"  Moved {moved} files")

        # Clean empty dirs
        for d in sorted(IMAGES_ROOT.rglob("*"), reverse=True):
            if d.is_dir() and not d.name.startswith("_") and d != IMAGES_ROOT:
                try:
                    d.rmdir()
                except OSError:
                    pass
    else:
        print("\n(dry-run — no files moved. Re-run with --apply to quarantine.)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate Warhammer Community images via CLIP + DINOv2")
    ap.add_argument("--apply", action="store_true",
                    help="Move non-miniature images to quarantine (default: dry-run)")
    ap.add_argument("--stage", choices=["both", "clip", "dino"], default="both",
                    help="Run only one stage (default: both)")
    args = ap.parse_args(argv)
    run(stage=args.stage, apply_changes=args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
