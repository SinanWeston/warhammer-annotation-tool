"""
Faction Label Audit Tool

Uses the trained YOLO model to flag images that are likely in the wrong faction folder.
Runs inference on each image and compares the predicted faction against the folder label.

Usage:
    python3 audit_faction_labels.py [--faction FACTION] [--limit N] [--confidence 0.3]

Examples:
    # Audit all factions (100 images each)
    python3 audit_faction_labels.py

    # Audit just imperial_guard
    python3 audit_faction_labels.py --faction imperial_guard

    # Audit with higher confidence threshold
    python3 audit_faction_labels.py --faction imperial_guard --confidence 0.4 --limit 500
"""

import sys
import os
import json
import argparse
from pathlib import Path
from collections import defaultdict

def main():
    parser = argparse.ArgumentParser(description="Audit faction folder labels using YOLO model")
    parser.add_argument("--faction", type=str, default=None, help="Specific faction to audit (default: all)")
    parser.add_argument("--limit", type=int, default=200, help="Max images per faction (default: 200)")
    parser.add_argument("--confidence", type=float, default=0.25, help="Min confidence threshold (default: 0.25)")
    parser.add_argument("--output", type=str, default=None, help="Output JSON report path")
    args = parser.parse_args()

    # Paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    training_data = project_root / "backend" / "training_data"
    model_path = project_root / "runs" / "yolo11_colab_best.pt"

    if not model_path.exists():
        print(f"ERROR: Model not found at {model_path}")
        sys.exit(1)

    print(f"Loading YOLO model from {model_path}...")
    from ultralytics import YOLO
    model = YOLO(str(model_path))

    # Get class names from model
    class_names = model.names  # {0: 'adeptus_mechanicus', 1: 'chaos_space_marines', ...}
    print(f"Model classes: {list(class_names.values())}")
    print()

    # Determine which factions to audit
    # Non-canonical dirs: old sub-type artifacts + non-faction data source dirs
    skip_dirs = {"hormagaunts", "tyranid_ripper_swarm", "reddit", "dakkadakka"}
    if args.faction:
        factions = [args.faction]
    else:
        factions = sorted([
            d for d in os.listdir(training_data)
            if (training_data / d).is_dir() and d not in skip_dirs
        ])

    # Results
    all_mismatches = []
    faction_stats = {}

    for faction in factions:
        faction_dir = training_data / faction
        if not faction_dir.is_dir():
            print(f"WARNING: {faction_dir} not found, skipping")
            continue

        # Collect image paths
        images = []
        for source in ["reddit", "dakkadakka"]:
            src_dir = faction_dir / source
            if not src_dir.exists():
                continue
            for f in sorted(src_dir.iterdir()):
                if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
                    images.append(f)
                    if len(images) >= args.limit:
                        break
            if len(images) >= args.limit:
                break

        if not images:
            print(f"{faction}: no images found")
            continue

        print(f"Auditing {faction}: {len(images)} images...", end="", flush=True)

        mismatches = []
        no_detection = 0
        correct = 0
        predicted_factions = defaultdict(int)

        for img_path in images:
            try:
                results = model.predict(str(img_path), conf=args.confidence, verbose=False)

                # Get all predictions
                preds = []
                for r in results:
                    for box in r.boxes:
                        cls_id = int(box.cls[0])
                        conf = float(box.conf[0])
                        cls_name = class_names[cls_id]
                        preds.append({"class": cls_name, "confidence": conf})

                if not preds:
                    no_detection += 1
                    continue

                # Majority vote: which faction appears most?
                faction_votes = defaultdict(float)
                for p in preds:
                    faction_votes[p["class"]] += p["confidence"]

                top_faction = max(faction_votes, key=faction_votes.get)
                top_score = faction_votes[top_faction]
                predicted_factions[top_faction] += 1

                if top_faction == faction:
                    correct += 1
                else:
                    mismatches.append({
                        "image": str(img_path),
                        "filename": img_path.name,
                        "expected": faction,
                        "predicted": top_faction,
                        "confidence_sum": round(top_score, 3),
                        "num_detections": len(preds),
                        "all_predictions": [
                            f"{p['class']} ({p['confidence']:.0%})" for p in
                            sorted(preds, key=lambda x: -x["confidence"])[:5]
                        ]
                    })

            except Exception as e:
                print(f"\n  ERROR on {img_path.name}: {e}")

        total_with_detections = correct + len(mismatches)
        mismatch_rate = len(mismatches) / total_with_detections * 100 if total_with_detections > 0 else 0

        print(f" {correct} correct, {len(mismatches)} mismatches ({mismatch_rate:.1f}%), {no_detection} no detections")

        if mismatches:
            # Show top predicted factions for mismatches
            mismatch_targets = defaultdict(int)
            for m in mismatches:
                mismatch_targets[m["predicted"]] += 1
            top_wrong = sorted(mismatch_targets.items(), key=lambda x: -x[1])[:3]
            print(f"  Most common wrong predictions: {', '.join(f'{f}={c}' for f,c in top_wrong)}")

        faction_stats[faction] = {
            "total_audited": len(images),
            "correct": correct,
            "mismatches": len(mismatches),
            "no_detection": no_detection,
            "mismatch_rate": round(mismatch_rate, 1)
        }
        all_mismatches.extend(mismatches)

    # Summary
    print()
    print("=" * 70)
    print("AUDIT SUMMARY")
    print("=" * 70)
    total_correct = sum(s["correct"] for s in faction_stats.values())
    total_mismatches = sum(s["mismatches"] for s in faction_stats.values())
    total_audited = sum(s["total_audited"] for s in faction_stats.values())
    total_detected = total_correct + total_mismatches

    print(f"Total images audited: {total_audited}")
    print(f"Total with detections: {total_detected}")
    print(f"Correct: {total_correct}")
    print(f"Mismatches: {total_mismatches} ({total_mismatches/total_detected*100:.1f}% of detected)" if total_detected > 0 else "")
    print()

    # Per-faction breakdown
    print(f"{'Faction':<25} {'Audited':>8} {'Correct':>8} {'Wrong':>8} {'Rate':>8}")
    print("-" * 60)
    for faction in sorted(faction_stats, key=lambda f: -faction_stats[f]["mismatch_rate"]):
        s = faction_stats[faction]
        print(f"{faction:<25} {s['total_audited']:>8} {s['correct']:>8} {s['mismatches']:>8} {s['mismatch_rate']:>7.1f}%")

    # Save report
    output_path = args.output or str(project_root / "scripts" / "audit_report.json")
    report = {
        "summary": {
            "total_audited": total_audited,
            "total_correct": total_correct,
            "total_mismatches": total_mismatches,
            "confidence_threshold": args.confidence
        },
        "per_faction": faction_stats,
        "mismatches": all_mismatches
    }

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nFull report saved to: {output_path}")

    if total_mismatches > 0:
        print(f"\nTo review mismatched images, check the report JSON.")
        print(f"Each entry has: filename, expected faction, predicted faction, confidence.")

if __name__ == "__main__":
    main()
