# Annotation Toolchain — Improvement Plan

> Scope: Everything that improves training data quality, annotation throughput, and dataset health.
> All file references are relative to `frontend/src/` unless otherwise noted.

---

## Do This First — Zero Code Required

### Trigger batch inference
```bash
curl -X POST http://localhost:3001/api/active-learning/start-batch
```
This generates `confidence_scores.json` and makes the "Prioritize by confidence" toggle actually work.
Until this runs, every annotation session serves images in alphabetical order regardless of what the toggle says.
Watch the live progress bar in QualityDashboard. Run it again after every ~200 new annotations.

---

## Priority 1 — Workflow Gaps (Highest Impact)

### 1.1 Review & re-edit previously annotated images

**Problem:** Once an image is saved, there's no way to get back to it short of manually knowing its ID.
The quality dashboard shows outliers (TINY / HUGE / CROWDED) but clicking them does nothing — you can't
navigate to that image to fix it. This means bad annotations accumulate permanently.

**What to build:**
- "Edit" button on each outlier row in QualityDashboard that calls `onEditImage(imageId)` — a new prop
- In AnnotationInterface, add `loadSpecificImage(imageId)` alongside `loadNextImage()` — hits a new or
  existing endpoint like `GET /api/annotate/image/:imageId` instead of `/api/annotate/next`
- Visually distinguish "editing existing" vs "annotating new" mode with a banner: "Editing previously
  annotated image — Save to update"

**Backend:** Check if `GET /api/annotate/image/:imageId` already exists or needs adding. The save
endpoint should already handle overwriting existing annotations (it writes JSON by imageId).

---

### 1.2 Skip / flag images as unannotatable

**Problem:** Some images are genuinely useless — blurry, wrong subject, bad crop, watermarked. Right now
`K` skips the image for the session but it comes back next time. There's no way to permanently remove it
from the annotation queue.

**What to build:**
- A "Flag as unusable" button (or keyboard shortcut, e.g. `X`) distinct from Skip
- Writes a sentinel file `training_data_annotations/{imageId}.skip.json` (or a `skipped: true` field) so
  the backend's "next unannotated" query excludes it permanently
- Show flagged count per faction in QualityDashboard

**Backend:** Update `getNextImage()` in `annotationService.ts` to also exclude images with skip markers.

---

### 1.3 Faster validation panel keyboard navigation

**Problem:** The AI prediction validation panel (Accept / Redraw / Wrong per prediction) requires mouse
clicks. For a session with 10+ predictions per image, this is a major throughput bottleneck.

**What to build:** Keyboard shortcuts for the active/highlighted prediction:
- `A` — Accept highlighted prediction
- `W` — Mark as Wrong
- `R` — Mark for Redraw
- `Tab` / `Shift+Tab` — cycle through predictions (already partially implied by `highlightedId`)
- `Enter` — Accept all remaining predictions and save

Keyboard shortcuts should be clearly shown in a small legend near the validation panel.
Guard against conflicts with existing shortcuts (S=save, K=skip, Del=delete, +/-=zoom).

---

### 1.4 Bulk "Accept All" and "Reject All" for AI predictions

**Problem:** When AI predictions are clearly all good (or all bad), accepting/rejecting them one at a time
is wasteful.

**What to build:**
- "Accept All" button that marks every prediction as accepted in one click
- "Reject All" button
- "Accept High Confidence" button that auto-accepts predictions above a threshold (e.g. >80% confidence)
  and leaves the rest for manual review — the most useful of the three for real workflows

These already align with how the prediction metadata is structured.

---

## Priority 2 — Data Health

### 2.1 Raise or remove the per-faction 110-image cap for struggling factions

**File:** `backend/src/services/annotationService.ts`  
**Problem:** The 110-image cap exists for balance, but Death Guard (3.4% mAP) and Ad Mech (25.6%) need
far more examples to reach parity. The cap is actively limiting recovery.

**What to build:** Make the cap configurable per faction rather than a single global constant.

```typescript
const FACTION_LIMITS: Record<string, number> = {
  death_guard: 300,
  adeptus_mechanicus: 200,
  tau: 150,
  default: 110,
};

const limit = FACTION_LIMITS[faction] ?? FACTION_LIMITS.default;
```

Expose this as a backend config or environment variable so it can be adjusted without a redeploy.
Show the effective cap per faction in QualityDashboard's faction progress cards.

---

### 2.2 Image deduplication in the training pool

**Problem:** 18,088 images gathered from the internet will contain near-duplicates — same image resized,
slightly cropped, different compression. Training on duplicates causes overfitting; annotating them wastes
time.

**What to build:** A one-time Python script (add to `scripts/`) that runs perceptual hashing (pHash) across
the image pool and writes a blocklist of duplicate image IDs. The backend then excludes blocklisted images
from annotation queues.

```python
# scripts/deduplicate_images.py
import imagehash
from PIL import Image
import json, os

THRESHOLD = 8  # hamming distance — tune to taste
hashes = {}
duplicates = []

for faction_dir in os.scandir('backend/training_data'):
    for src_dir in os.scandir(faction_dir):
        for img_file in os.scandir(src_dir):
            h = imagehash.phash(Image.open(img_file.path))
            for existing_id, existing_h in hashes.items():
                if h - existing_h < THRESHOLD:
                    duplicates.append(img_file.name)
                    break
            else:
                hashes[img_file.name] = h

with open('backend/duplicate_images.json', 'w') as f:
    json.dump(duplicates, f)
```

**Dependencies:** `pip install imagehash Pillow`  
**Note:** Run this once on the full pool, then periodically as new images are added.

---

### 2.3 Annotation consistency audit view

**Problem:** The quality dashboard shows box size statistics per faction but not whether boxes are being
drawn consistently. A Death Guard model might have boxes drawn at the base by one annotator and at the
torso by another — this confuses training even if individual annotations look fine.

**What to build:** In QualityDashboard, add a "Sample Grid" view per faction — shows a random 9-image
grid of annotated images with their bboxes overlaid (using the same base64 + canvas approach as
ResultsPage). This lets you visually spot inconsistent box placement in 30 seconds.

**Implementation:** New `GET /api/annotate/sample/:faction?count=9` endpoint that returns 9 random
annotated images with their annotations. New `AnnotationSampleGrid` component in the dashboard.

---

## Priority 3 — Throughput & Efficiency

### 3.1 Pre-load next image in background

**Problem:** After saving an image, there's a visible loading gap while the next image fetches and
decodes. At scale this adds up.

**What to build:** While the user is annotating image N, fetch image N+1 in the background and hold it
in state. On save, instantly display the preloaded image.

```tsx
const [nextImageBuffer, setNextImageBuffer] = useState<PreloadedImage | null>(null);

// After loading current image, kick off prefetch
useEffect(() => {
  if (currentImage) prefetchNextImage();
}, [currentImage?.id]);
```

This is particularly impactful with large base64 image payloads — the decode is CPU-heavy and takes
100-300ms on a normal laptop.

---

### 3.2 Annotation session stats

**Problem:** No feedback on annotation velocity during a session. It's easy to lose track of time or
productivity.

**What to build:** A small persistent stats bar during annotation sessions showing:
- Images annotated this session
- Session duration
- Avg time per image (rolling)
- Total for today

This is motivational (gamification), but also practically useful for estimating how long it will take
to reach annotation targets.

---

### 3.3 Target-setting and progress toward training milestones

**Problem:** QualityDashboard shows current state but not what you're working toward. There's no way to
see "Death Guard needs 80 more annotations before the next training run."

**What to build:** Add a "Training Target" concept — a configurable annotation count per faction that
represents "enough for the next training run." Show progress bars with a target marker.

```tsx
const TRAINING_TARGETS: Record<string, number> = {
  death_guard: 200,
  adeptus_mechanicus: 150,
  // ...
};
```

Show: `[██████░░░░] 64 / 200 — 136 needed` per faction. Makes prioritisation obvious at a glance.

---

### 3.4 Annotation export improvements

**Problem:** The current YOLO export likely exports everything or by faction, but there's no way to
export a "balanced" dataset — e.g. cap each faction at the same number so no faction dominates training.

**What to build:** Export options in QualityDashboard:
- "Export All" (current behaviour)
- "Export Balanced" — takes min(count, global_cap) per faction, so no one faction dominates
- "Export since last training run" — exports only annotations added after a stored timestamp

These don't change the annotation workflow at all, just give you smarter training inputs from the same
data.

---

## Priority 4 — Data Augmentation Pipeline

### 4.1 Offline augmentation script

**Problem:** You have 964 annotated images. With augmentation you effectively have 4,000–8,000. This is
a significant multiplier for free, especially for underrepresented factions.

**What to build:** A Python script that takes annotated images + their YOLO label files and generates
augmented variants. Critically, bboxes must be transformed alongside the image.

```python
# scripts/augment_dataset.py
import albumentations as A

transform = A.Compose([
    A.HorizontalFlip(p=0.5),
    A.RandomBrightnessContrast(brightness_limit=0.2, contrast_limit=0.2, p=0.5),
    A.HueSaturationValue(hue_shift_limit=10, sat_shift_limit=20, p=0.3),
    A.GaussianBlur(blur_limit=(3, 5), p=0.2),
    A.ImageCompression(quality_lower=70, quality_upper=100, p=0.3),
], bbox_params=A.BboxParams(format='yolo', label_fields=['class_labels']))
```

**Recommended augmentations for miniatures:**
- Horizontal flip (safe — no asymmetric faction markings on most models)
- Brightness/contrast (mimics different lighting conditions — very high value)
- Hue shift (mimics different paint schemes within a faction)
- Slight blur (mimics motion/focus issues in photos)
- JPEG compression noise (mimics phone camera quality variance)

**Avoid:** Rotation beyond ±15°, heavy crop, or anything that makes models unrecognisable.

**Dependencies:** `pip install albumentations`  
**Target:** 4x augmentation ratio for all factions; 8x for Death Guard and Ad Mech specifically.

---

## Summary Prioritisation

| # | Item | Impact | Effort |
|---|------|--------|--------|
| 0 | Trigger batch inference (no code) | Very High | Zero |
| 1.1 | Edit previously annotated images | High — fixes bad data | Medium |
| 1.2 | Flag images as unusable | High — cleans queue | Low |
| 1.3 | Keyboard nav for validation panel | High — throughput | Low |
| 1.4 | Bulk Accept/Reject AI predictions | High — throughput | Low |
| 2.1 | Per-faction annotation caps | High — unblocks Death Guard | Very Low |
| 2.2 | Image deduplication script | Medium — data health | Low (Python script) |
| 2.3 | Annotation consistency sample grid | Medium — quality audit | Medium |
| 3.1 | Preload next image | Medium — UX smoothness | Low |
| 3.2 | Session stats bar | Low — motivation | Very Low |
| 3.3 | Training targets + progress | Medium — focus | Low |
| 3.4 | Balanced export option | High — training quality | Low |
| 4.1 | Augmentation script | Very High — data multiplier | Medium (Python) |

---

## Recommended Order of Attack

1. **Trigger batch inference** — right now, before anything else
2. **Raise Death Guard + Ad Mech caps** (2.1) — 10 minute change, immediate impact
3. **Keyboard shortcuts for validation panel** (1.3) + **Bulk Accept** (1.4) — throughput
4. **Flag as unusable** (1.2) — keeps queue clean going forward
5. **Edit previously annotated images** (1.1) — lets you fix outliers the dashboard is already showing you
6. **Augmentation script** (4.1) — biggest dataset multiplier for free
7. **Deduplication script** (2.2) — data hygiene
8. **Balanced export** (3.4) — smarter training runs
9. **Training targets** (3.3) + **Consistency grid** (2.3) — longer-term tooling
