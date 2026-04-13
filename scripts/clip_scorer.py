#!/usr/bin/env python3
"""
CLIP Quality Filter for Battle Scanner Training Data

Scores all images in training_data_v2/ using OpenCLIP (ViT-B-32/openai) and
moves low-scoring images to training_data_v2/rejected/low_clip_score/.

Score formula:
    score = cosine_sim(img_emb, positive_emb)
            - 0.3 * max(cosine_sim(img_emb, neg_emb) for neg_emb in negatives)

Default threshold: 0.18  (tune with --dry-run first)

Prerequisites:
    pip install open-clip-torch

Usage:
    python scripts/clip_scorer.py --faction necrons --dry-run
    python scripts/clip_scorer.py --faction necrons --score-only
    python scripts/clip_scorer.py --faction necrons
    python scripts/clip_scorer.py --dry-run           # all factions
    python scripts/clip_scorer.py                     # score + reject all
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scraper_utils import OUTPUT_DIR, METADATA_DIR

CLIP_SCORES_FILE = METADATA_DIR / "clip_scores.json"
REJECTED_DIR = OUTPUT_DIR / "rejected" / "low_clip_score"

POSITIVE_PROMPT = "a photo of painted Warhammer 40K miniatures on a gaming table"
NEGATIVE_PROMPTS = [
    "a screenshot from a video game",
    "digital art illustration fantasy",
]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
BATCH_SIZE = 32


# ─── CLIP Setup ───────────────────────────────────────────────────────────────

def load_clip_model(device: str = "cpu"):
    try:
        import open_clip
    except ImportError:
        print("ERROR: open-clip-torch is not installed. Run: pip install open-clip-torch")
        sys.exit(1)

    import torch
    print("Loading CLIP model (ViT-B-32/openai) — first run downloads ~350 MB...")
    model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
    tokenizer = open_clip.get_tokenizer("ViT-B-32")
    model.eval()
    model = model.to(device)
    return model, preprocess, tokenizer, device


def encode_texts(model, tokenizer, texts: list[str], device: str):
    import torch
    with torch.no_grad():
        tokens = tokenizer(texts).to(device)
        embs = model.encode_text(tokens)
        embs = embs / embs.norm(dim=-1, keepdim=True)
    return embs.cpu()


def encode_images_batch(model, preprocess, paths: list[Path], device: str):
    import torch
    from PIL import Image

    tensors = []
    valid = []
    for p in paths:
        try:
            img = Image.open(p).convert("RGB")
            tensors.append(preprocess(img))
            valid.append(p)
        except Exception:
            continue

    if not tensors:
        return [], valid

    batch = torch.stack(tensors).to(device)
    with torch.no_grad():
        embs = model.encode_image(batch)
        embs = embs / embs.norm(dim=-1, keepdim=True)
    return embs.cpu(), valid


def compute_score(img_emb, pos_emb, neg_embs) -> float:
    import torch
    pos_sim = float((img_emb @ pos_emb.T).squeeze())
    neg_sims = [float((img_emb @ n.T).squeeze()) for n in neg_embs]
    return pos_sim - 0.3 * max(neg_sims)


# ─── File Discovery ───────────────────────────────────────────────────────────

def find_images(faction: str | None = None) -> list[Path]:
    """Return all image paths under OUTPUT_DIR, excluding rejected/ and metadata/."""
    base = OUTPUT_DIR
    paths = []
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in IMAGE_EXTS:
            continue
        rel = p.relative_to(base)
        parts = rel.parts
        if parts[0] in ("rejected", "metadata"):
            continue
        if faction and parts[0] != faction:
            continue
        paths.append(p)
    return paths


def load_scores() -> dict:
    if CLIP_SCORES_FILE.exists():
        with open(CLIP_SCORES_FILE) as f:
            return json.load(f)
    return {}


def save_scores(scores: dict):
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CLIP_SCORES_FILE, "w") as f:
        json.dump(scores, f, indent=2)


# ─── Scoring Pass ─────────────────────────────────────────────────────────────

def score_images(
    faction: str | None,
    batch_size: int,
    dry_run: bool = False,
) -> dict:
    """Compute CLIP scores for all unscored images. Returns updated scores dict."""
    import torch
    device = "cuda" if _has_cuda() else "cpu"
    model, preprocess, tokenizer, device = load_clip_model(device)

    pos_emb = encode_texts(model, tokenizer, [POSITIVE_PROMPT], device)
    neg_embs = [encode_texts(model, tokenizer, [t], device) for t in NEGATIVE_PROMPTS]

    scores = load_scores()
    all_paths = find_images(faction)

    to_score = [p for p in all_paths if str(p.relative_to(OUTPUT_DIR)) not in scores]
    print(f"  {len(to_score)} images to score (already scored: {len(scores)})")

    if dry_run:
        print("  [DRY RUN] Would score images, not writing anything")
        return scores

    for i in range(0, len(to_score), batch_size):
        batch = to_score[i : i + batch_size]
        embs, valid_paths = encode_images_batch(model, preprocess, batch, device)
        if not valid_paths:
            continue
        for emb, path in zip(embs, valid_paths):
            rel = str(path.relative_to(OUTPUT_DIR))
            scores[rel] = round(compute_score(emb.unsqueeze(0), pos_emb, neg_embs), 4)

        # Save incrementally
        save_scores(scores)
        pct = min(i + batch_size, len(to_score))
        print(f"  Scored {pct}/{len(to_score)}", end="\r")

    print(f"\n  Scoring complete. {len(scores)} total entries in index.")
    return scores


def _has_cuda() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


# ─── Rejection Pass ───────────────────────────────────────────────────────────

def reject_low_scores(scores: dict, threshold: float, dry_run: bool = False) -> int:
    """Move images below threshold to rejected/low_clip_score/. Returns count moved."""
    moved = 0
    for rel, score in scores.items():
        if score >= threshold:
            continue
        src = OUTPUT_DIR / rel
        if not src.exists():
            continue
        dst = REJECTED_DIR / rel
        if dry_run:
            print(f"  [DRY RUN] Would reject (score={score:.3f}): {rel}")
            moved += 1
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            moved += 1

    return moved


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Score and filter images using CLIP quality scoring"
    )
    parser.add_argument("--threshold", type=float, default=0.18,
                        help="CLIP score threshold for rejection (default: 0.18)")
    parser.add_argument("--faction", metavar="SLUG", help="Limit to one faction directory")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be scored/rejected without making changes")
    parser.add_argument("--score-only", action="store_true",
                        help="Update clip_scores.json but don't move any files")
    parser.add_argument("--reject-only", action="store_true",
                        help="Apply existing scores without re-scoring")
    args = parser.parse_args()

    print("=" * 60)
    print("CLIP Scorer")
    print(f"Threshold: {args.threshold}")
    print(f"Faction: {args.faction or 'all'}")
    print(f"Dry run: {args.dry_run}")
    print(f"Score only: {args.score_only}")
    print(f"Reject only: {args.reject_only}")
    print("=" * 60)

    if args.reject_only:
        scores = load_scores()
        print(f"Loaded {len(scores)} existing scores.")
    else:
        scores = score_images(
            faction=args.faction,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )

    if args.score_only or args.dry_run:
        # Print summary stats
        if scores:
            below = sum(1 for s in scores.values() if s < args.threshold)
            above = len(scores) - below
            print(f"\nScore distribution (threshold={args.threshold}):")
            print(f"  Pass:   {above}")
            print(f"  Reject: {below}")
        return

    moved = reject_low_scores(scores, threshold=args.threshold, dry_run=args.dry_run)

    print(f"\n{'='*60}")
    print(f"DONE. Rejected: {moved} images (score < {args.threshold})")
    print(f"Rejected images moved to: {REJECTED_DIR}")
    print(f"Scores index: {CLIP_SCORES_FILE}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
