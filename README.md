# Warhammer 40K Dataset Annotation Tool

A web-based tool for manually annotating bounding boxes on Warhammer 40K miniature images to create training datasets for YOLO object detection models.

## Overview

This tool helps you create high-quality training data for custom YOLO models by providing an intuitive interface to:
- Draw model bounding boxes around miniatures
- Use AI-assisted annotation (model pre-suggests boxes, you accept/reject/redraw)
- Track annotation progress across 18,000+ images
- Monitor annotation quality via a dedicated dashboard
- Prioritize annotation order using active learning (lowest model confidence first)
- Export to YOLO format for training

## Features

### Model-Assisted Annotation
- **AI Predictions**: Click "Get AI Suggestions" to have the trained YOLO model detect miniatures
- **Validation Workflow**: Accept correct boxes, reject false positives, redraw wrong ones
- **Training Feedback**: Rejected/redrawn predictions stored for hard negative mining
- **Accept All**: Bulk-accept when all predictions look good

### Quality Dashboard
- **Boxes Per Image**: Distribution chart with min/max/avg/median stats
- **Box Sizes by Faction**: Table with color-coding for struggling factions
- **Annotation Speed**: Daily annotation throughput chart
- **Outlier Detection**: Flags tiny boxes (<1% area), huge boxes (>90% area), crowded images (20+ boxes)
- **Cached Stats**: 60-second TTL, auto-invalidated on annotation save

### Active Learning
- **Batch Inference**: Score unannotated images by model confidence (loads YOLO model once)
- **Confidence Prioritization**: Serve lowest-confidence images first for maximum annotation value
- **Faction Filtering**: Focus batch inference on struggling factions (Death Guard, AdMech, etc.)
- **Progress Tracking**: Real-time progress bar while batch inference runs
- **Toggle in UI**: "Prioritize by confidence" checkbox with confidence badge per image

### Quality Validation
- **Real-time Validation**: Checks annotations before saving (out of bounds, too small, overlaps)
- **Quality Issues Modal**: Visual feedback with helpful tips for fixing errors
- **Pre-Export Validation**: Validates entire dataset before YOLO export
- **Error Prevention**: Blocks saves when critical errors detected
- **Python Validator**: Standalone script for validating exported YOLO datasets

### Progress Tracking
- Real-time progress by faction
- Total annotation count and percentage complete
- Per-faction statistics and progress bars

### Workflow Optimized for Speed
- **Zoom & Pan**: Mouse wheel zoom, click-and-drag panning for precise annotation
- **Undo/Redo**: Full undo/redo support with Ctrl+Z/Ctrl+Y/Ctrl+Shift+Z
- **Keyboard shortcuts** for common actions
- Auto-save and automatic next image loading
- Skip images without miniatures
- Resume annotation from where you left off

## Quick Start

### Prerequisites
- Node.js v18+
- npm 9+
- 18,088 images in `backend/training_data/{faction}/{source}/`

### Installation

```bash
# Install dependencies
npm install

# Start both frontend and backend
npm run dev
```

The app will be available at `http://localhost:5173`

### Usage

1. **Navigate to the app** - Open `http://localhost:5173` in your browser
2. **Click "Start Annotating"** - Loads the first unannotated image
3. **Get AI suggestions** - Click "Get AI Suggestions" to have the model pre-detect miniatures
4. **Validate predictions** - Accept correct boxes, reject false positives, redraw wrong ones
5. **Draw additional boxes** - Manually draw any miniatures the AI missed
6. **Save and continue** - Click "Save & Next" to save annotations and load the next image
7. **Use Dashboard** - Click "Dashboard" nav button to view quality stats and run active learning
8. **Enable prioritization** - Toggle "Prioritize by confidence" to annotate high-value images first

### Keyboard Shortcuts

- **Delete / Backspace**: Remove selected model box
- **B**: Remove base box from selected model
- **Ctrl+Z**: Undo last action
- **Ctrl+Y** or **Ctrl+Shift+Z**: Redo last undone action
- **Mouse Wheel**: Zoom in/out
- **Click + Drag** (on canvas): Pan around zoomed image
- **Click box**: Select a box (turns green)
- **Draw**: Click and drag in canvas to create boxes

## Export to YOLO

After annotating, export to YOLOv8-pose format:

```bash
# Validate before export (recommended)
curl -X POST http://localhost:3001/api/annotate/validate-export

# Export to YOLO format
curl -X POST http://localhost:3001/api/annotate/export \
  -H "Content-Type: application/json" \
  -d '{"outputDir": "backend/yolo_dataset", "trainSplit": 0.8}'

# Validate exported dataset (Python)
python3 scripts/validate_yolo_dataset.py backend/yolo_dataset
```

## Training a YOLO Model

See `TRAIN_CUSTOM_YOLO.md` for detailed training instructions.

### Quick Training Setup

Use the automated setup script to prepare your training environment:

```bash
# Setup training environment (virtual env, dependencies, GPU check, pretrained weights)
python3 scripts/setup_training_env.py

# Or specify custom dataset path
python3 scripts/setup_training_env.py --dataset-path backend/yolo_dataset
```

After setup completes, follow the displayed instructions to start training.

## Tech Stack

- **Frontend**: React 18, TypeScript, Tailwind CSS, Vite
- **Backend**: Node.js, Express, TypeScript
- **Image Processing**: Sharp
- **Dataset**: 18,088 Warhammer 40K miniature images

## API Endpoints

### Annotation
- `GET /api/annotate/images` - Get all images with annotation status
- `GET /api/annotate/next` - Get next unannotated image (`?prioritize=true` for confidence-based ordering)
- `GET /api/annotate/image/:imageId` - Get image data as base64
- `POST /api/annotate/save` - Save annotation (with validation)
- `GET /api/annotate/progress` - Get annotation progress stats
- `GET /api/annotate/predict/:imageId` - Get AI predictions for an image
- `POST /api/annotate/validate-export` - Validate all annotations before export
- `POST /api/annotate/export` - Export to YOLO format (with pre-export validation)

### Dashboard
- `GET /api/dashboard/stats` - Get annotation quality statistics (cached 60s)

### Active Learning
- `POST /api/active-learning/start-batch` - Start background batch inference (`{ factions?, limit? }`)
- `GET /api/active-learning/status` - Get batch progress and total scored images

## Development

```bash
# Install dependencies
npm install

# Start development servers (frontend + backend)
npm run dev

# Build for production
npm run build
```

## Testing

### Backend Tests (TypeScript/Jest)

```bash
# Install dependencies
cd backend && npm install

# Run all tests
npm test

# Run validation tests specifically
npm test -- annotationService.validation.test.ts

# Run with coverage
npm test -- --coverage
```

**Test Coverage**: 28 test cases covering validation logic (bbox out of bounds, too small, base outside model, duplicates, IoU calculation)

### Python Tests (pytest)

```bash
# Install pytest
pip install pytest pytest-cov

# Run all Python tests
cd scripts
pytest test_validate_yolo_dataset.py -v

# Run with coverage
pytest test_validate_yolo_dataset.py -v --cov=validate_yolo_dataset --cov-report=html
```

**Test Coverage**: 25+ test cases for YOLO dataset validator

See `TESTING.md` for comprehensive testing documentation.

## Documentation

- **README.md** - This file (quick start guide)
- **STATUS.md** - Project status, changelog, and current state
- **IMPROVEMENTS.md** - Completed enhancements (correctness, throughput, training pipeline)
- **TESTING.md** - Testing guide (unit tests, coverage, CI/CD setup)
- **CLAUDE.md** - Developer guidance for Claude Code
- **TRAIN_CUSTOM_YOLO.md** - Guide for training YOLO models after annotation

## License

MIT
