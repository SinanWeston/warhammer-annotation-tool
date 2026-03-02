# Project Status

**Last Updated**: February 15, 2026
**Version**: 7.0 (Quality Dashboard + Active Learning)
**Status**: Active Learning Phase - Dashboard live, confidence-based prioritization ready

---

## Recent Changes (Factual Log)

### February 15, 2026 - Quality Dashboard + Active Learning Pipeline

**Goal**: Add visibility into annotation quality and prioritize annotation order using model confidence

**Achievements**:

1. **Quality Dashboard (new view)**
   - Nav bar with Annotation/Dashboard toggle in App.tsx
   - Boxes per image distribution (min/max/avg/median + bar chart)
   - Box sizes by faction table (color-coded for struggling factions)
   - Annotation speed chart (annotations per day)
   - Outlier detection: tiny boxes (<1% area), huge boxes (>90% area), crowded images (20+ boxes)
   - Stats cached in memory with 60s TTL, invalidated on annotation save

2. **Active Learning Pipeline**
   - `batchYoloInference.py` — loads YOLO model once, processes image list, outputs JSON lines
   - `activeLearningService.ts` — manages confidence scores, spawns batch Python process, writes scores atomically
   - "Start Batch Inference" UI in dashboard with faction filter, limit input, and progress bar
   - `GET /api/annotate/next?prioritize=true` — serves lowest-confidence images first
   - "Prioritize by confidence" toggle in annotation interface with confidence badge

3. **New Files Created**
   - `backend/src/services/dashboardStatsService.ts` — stats computation + caching
   - `backend/src/services/activeLearningService.ts` — confidence scoring + prioritization
   - `backend/src/services/batchYoloInference.py` — batch YOLO inference script
   - `frontend/src/components/QualityDashboard.tsx` — dashboard UI (5 card sections)
   - `frontend/src/types/dashboard.ts` — TypeScript interfaces

4. **Modified Files**
   - `backend/src/index.ts` — 3 new endpoints (dashboard stats, batch start, AL status), prioritize query param
   - `backend/src/services/annotationService.ts` — cache invalidation callback, prioritize param on getNextImage
   - `frontend/src/App.tsx` — state-based navigation with nav buttons
   - `frontend/src/components/AnnotationInterface.tsx` — prioritize toggle + confidence badge

**New API Endpoints**:
- `GET /api/dashboard/stats` — annotation quality statistics
- `POST /api/active-learning/start-batch` — start background batch inference
- `GET /api/active-learning/status` — batch progress + total scored images

---

### February 8, 2026 - First YOLO Model Trained!

**Goal**: Train a YOLO model to detect Warhammer 40K miniatures using annotated dataset

**Achievements**:

1. **Dataset Export Fixed**
   - Fixed 46 annotation files with wrong paths (`/home/sinan/photoanalyzer/` → `/home/sinan/Active/Projects/photoanalyzer/`)
   - Removed 2 annotations with out-of-bounds bboxes
   - Successfully exported 280 images to YOLO format (206 train, 74 val)

2. **YOLOv8n Model Trained (First Iteration)**
   - Model: YOLOv8 nano (3M parameters)
   - Training: 30 epochs, 416px, CPU
   - Training time: ~15 minutes

   **Results**:
   | Metric | Value |
   |--------|-------|
   | **mAP50** | **63.2%** |
   | mAP50-95 | 49.3% |
   | Precision | 59.5% |
   | Recall | 55.7% |

   **Per-Faction Performance**:
   | Faction | mAP50 |
   |---------|-------|
   | Custodes | 97.0% |
   | Grey Knights | 95.8% |
   | Imperial Guard | 83.8% |
   | Eldar | 77.9% |
   | Chaos Space Marines | 75.1% |
   | Genestealer Cult | 46.7% |
   | Adeptus Mechanicus | 25.6% |
   | Death Guard | 3.4% |

3. **Training Infrastructure Created**
   - Python virtual environment: `yolo_env/`
   - Training script: `train_yolo.py`
   - Google Colab notebook: `train_yolo_colab.ipynb`
   - Maximum training script: `train_yolo_max.py`
   - YOLO11x training script: `train_yolo11.py`

**Model Location**: `runs/warhammer_detector/weights/best.pt`

**Next Steps**:
- Train with larger model (YOLO11x) on Google Colab for better accuracy
- Use trained model for semi-supervised learning on remaining 17k images

---

### February 7, 2026 - Annotation Simplification Complete

**Goal**: Simplify annotation workflow for faster iteration

**Changes Made**:

1. **Simplified to Model-Only Bboxes**
   - Removed base bbox mode entirely
   - BboxAnnotator now only draws model boxes
   - Simplified YOLO export (standard detection format, not pose)

2. **Limited to 60 Images Per Faction**
   - Added `perFactionLimit = 60` in annotationService.ts
   - Ensures focused annotation for initial training round
   - Total target: 480 images (8 factions × 60)

3. **Fixed Multiple Bugs**
   - Progress bar not updating after save (added `fetchProgress()` call)
   - Faction not advancing after completion (fixed counting logic)
   - Zoom/pan issues (switched to CSS transform approach)
   - Canvas size issues (expanded to near-fullscreen)

4. **Annotation Results**
   - Total annotated: 492 images
   - With boxes: 220 images
   - Skipped (empty): 272 images
   - Factions complete: 8 (60 each)

**Files Modified**:
- `frontend/src/components/BboxAnnotator.tsx` - Removed base mode, CSS zoom
- `frontend/src/components/AnnotationInterface.tsx` - Fixed progress, layout
- `backend/src/services/annotationService.ts` - 60/faction limit, simplified export

---

### December 27, 2025 - All Improvements Complete ✅

**Goal**: Transform annotation tool from MVP to production-ready system

**Completion Status**: 100% (10/10 tasks complete)

**Key Features Implemented**:
- Zoom & Pan (mouse wheel + drag)
- Undo/Redo (Ctrl+Z, Ctrl+Y)
- Auto-constrain base bboxes
- Real-time validation
- Quality issues modal
- YOLO export with validation
- Comprehensive test suites

---

## Current State

### ✅ Annotation System (Complete)

- 18,088 total images collected
- 707 images annotated (with model-assisted workflow)
- 8 factions, 110 per-faction limit
- Model-only bboxes (simplified from hierarchical)
- YOLO format export working
- AI-assisted annotation (predict + accept/reject/redraw)

### ✅ First YOLO Model (Complete)

- YOLOv8n trained on 280 images
- 63.2% mAP50 overall
- Best factions: Custodes (97%), Grey Knights (96%)
- Needs improvement: Death Guard (3.4%), Adeptus Mechanicus (25.6%)

### ✅ Quality Dashboard (Complete)

- Boxes per image stats + distribution chart
- Box sizes by faction table
- Annotation speed timeline
- Outlier detection (tiny/huge/crowded)
- Cached stats with 60s TTL

### ✅ Active Learning Pipeline (Complete)

- Batch YOLO inference (loads model once, processes in bulk)
- Confidence scores persisted to `confidence_scores.json`
- Lowest-confidence-first annotation ordering
- Dashboard controls with progress bar
- Prioritize toggle in annotation interface

---

## Quick Start Commands

```bash
# Start development servers
npm run dev

# Activate YOLO environment
source yolo_env/bin/activate

# Train model locally (CPU)
python3 train_yolo.py

# Export annotations to YOLO
curl -X POST http://localhost:3001/api/annotate/export

# Test trained model
python3 -c "from ultralytics import YOLO; m = YOLO('runs/warhammer_detector/weights/best.pt'); m.val(data='backend/yolo_dataset/data.yaml')"
```

---

## Project Files

### Training
- `train_yolo.py` - Basic CPU training (YOLOv8n)
- `train_yolo_max.py` - Maximum settings (YOLOv8s)
- `train_yolo11.py` - Best model (YOLO11x)
- `train_yolo_colab.ipynb` - Google Colab notebook
- `yolo_env/` - Python virtual environment

### Models
- `runs/warhammer_detector/weights/best.pt` - First trained model (63.2% mAP50)

### Data
- `backend/yolo_dataset/` - Exported YOLO format dataset
- `backend/training_data/` - 18,088 source images
- `backend/training_data_annotations/` - 492 annotation JSON files

---

## Performance Summary

### First Model (YOLOv8n)
- Training: 30 epochs, 15 min on CPU
- mAP50: 63.2%
- Inference: 34ms per image

### Expected (YOLO11x on GPU)
- Training: 100 epochs, ~2 hours on T4 GPU
- Target mAP50: 75-85%
- Better accuracy on difficult factions

---

## Next Milestones

1. **Run batch inference on all unannotated images** — Score ~17k images with confidence levels via Dashboard
2. **Annotate high-value images** — Use active learning to focus on images the model struggles with (Death Guard, AdMech)
3. **Train YOLO11x on Colab** — Larger model on expanded dataset for higher accuracy
4. **Iterate** — Re-score, re-annotate worst performers, retrain (active learning loop)

## Future Improvements

- **Per-faction confidence breakdowns** in dashboard (which factions have lowest avg confidence?)
- **Auto-suggest struggling factions** when starting batch inference
- **Annotation time tracking** (time per image, not just per day)
- **Export confidence-weighted sampling** (oversample low-confidence factions in training split)
- **Model comparison dashboard** (compare mAP across training iterations)
- **Keyboard shortcut for prioritize toggle** in annotation view

---

**Quality dashboard and active learning pipeline are live! Focus annotation effort where it matters most.**
