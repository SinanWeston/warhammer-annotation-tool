# Warhammer 40K Miniature Recogniser — Project Overview

**Last updated**: April 2026
**Status**: Active development — annotation in progress, first model trained
**Architectural direction**: See [STRATEGY.md](STRATEGY.md) — pivoting from end-to-end YOLO to a three-tier detection + retrieval pipeline

---

## What Is This?

A pipeline for training a computer vision model to identify and count Warhammer 40K miniatures by faction from a photograph. You point a camera at an army and the app tells you which armies are on the table and how many models each has.

The project has four parts: two annotation tools (desktop and mobile), a consumer-facing scanner app, and a shared backend.

---

## Components

### 1. Desktop Annotator (`frontend/`)
A browser-based tool for drawing bounding boxes on miniature images. This is the main annotation workhorse for bulk work at a desk.

- **Tech**: React 18 + TypeScript + Vite, running on `localhost:5173`
- **What it does**: Loads images one at a time from the training dataset, lets you draw bboxes around miniatures, saves annotations as JSON
- **AI assistance**: Can query the trained YOLO model to pre-suggest bboxes — you accept, reject, or redraw each one
- **Active learning**: Prioritises images the model is least confident about, so annotation effort goes where it's needed most
- **Quality dashboard**: Shows stats per faction (boxes/image, sizes, outliers), annotation speed, and progress

### 2. Mobile Annotator PWA (`annotator-mobile/`)
An offline-first touch annotation app for annotating on iPhone/iPad away from a desk.

- **Tech**: React 18 + TypeScript + Vite PWA (service worker), deployed to Netlify
- **Live URL**: https://40k-annotator.netlify.app
- **What it does**: Import a zip batch of images → annotate with drag-to-draw bboxes on a touch canvas → export annotations as JSON → import on PC
- **Offline-first**: Everything stored in IndexedDB; works with no internet connection
- **Sync workflow**: Phone exports `annotations-[timestamp].json` → saved to pCloud → PC runs `npm run sync:mobile` to import into the backend
- **AI predictions**: Batch can include YOLO predictions; you accept/reject each prediction card
- **One army per image**: Faction selector applies to all bboxes in the image (each photo shows one army)

### 3. Consumer Scanner (`consumer/`) — v2.0
The end-user app. Upload army photos and get unit identifications, points calculations, and army list tools.

- **Tech**: React 18 + TypeScript + Vite, Zustand, React Router v6 (hash), jsPDF — running on `localhost:5174`
- **Desktop-first**: Four-tab layout — Scan, Results, Army Builder, History
- **Scan tab**: Multi-photo upload with drag-drop, optional per-image cropping, faction hint dropdown, mock scan returning realistic 12-detection results (real AI integration is a single function swap)
- **Results tab**: Split view — canvas with interactive bbox overlay (hover/click syncs with unit list), inline editing of unit names/points, grouping by faction/role/flat, uncertain detections section for low-confidence results
- **Army Builder tab**: Editable army list with +/- counts, 180-unit searchable database, points progress bar, composition suggestions filtered by playstyle, PDF/text export, shareable URL encoding
- **History tab**: Past scans and saved armies stored in IndexedDB, click to reload any past result

### 4. Backend (`backend/`)
Shared Express API serving all three frontends.

- **Tech**: Node.js + Express + TypeScript, running on `localhost:3001`
- **Key responsibilities**:
  - Serves images to annotators (110 per faction, ordered by confidence)
  - Saves and validates annotation JSON files
  - Exports annotations to YOLOv8 format for training
  - Runs batch YOLO inference for active learning scoring
  - Packages image batches as zips for mobile download
  - Receives and imports mobile annotations (`POST /api/mobile/sync`)
  - Runs YOLO inference for the consumer scanner (`POST /api/detect`)

---

## Dataset

### Legacy training_data (~12,000 images)

The original scraped dataset. Images are faction-level (no unit labels), mixed quality — some wrong editions, some kitbashed. Used for the first trained model.

| Faction | Images | Annotated |
|---------|--------|-----------|
| Space Marines | 2,800 | 100 |
| Chaos Space Marines | 2,000 | 124 |
| Adepta Sororitas | 400 | 67 |
| Adeptus Mechanicus | 400 | 60 |
| Chaos Daemons | 400 | 50 |
| Chaos Knights | 400 | 51 |
| Adeptus Custodes | 400 | 84 |
| Aeldari (Eldar) | 400 | 64 |
| Genestealer Cults | 400 | 40 |
| Harlequins | 400 | 14 |
| Imperial Agents | 400 | 0 |
| Astra Militarum | 400 | 34 |
| Imperial Knights | 400 | 35 |
| Leagues of Votann | 400 | 0 |
| Necrons | 400 | 15 |
| Orks | 400 | 40 |
| T'au Empire | 400 | 11 |
| Tyranids | 400 | 60 |
| Ynnari | 400 | 26 |
| Drukhari | 399 | 20 |
| **Total** | **~11,999** | **895** |

### New training_data_v2 (in progress — clean seed dataset)

Being scraped now. Unit-level images of 10th edition painted models only, sourced from eBay (Playwright) and DakkaDakka (high paintjob rating). Target: 10+ images per unit across all 20 factions.

| Stat | Value |
|------|-------|
| Factions | 20 |
| Unit database | ~900 units across all factions |
| Sources | eBay listings, DakkaDakka gallery (paintjob≥4) |
| Structure | `training_data_v2/{faction}/isolation/{unit}/` |
| Combat patrols | `training_data_v2/{faction}/combat_patrol/` |
| Metadata | `training_data_v2/metadata/scrape_log.csv` |

### All 20 Factions

**Imperium:** Space Marines, Adepta Sororitas, Adeptus Mechanicus, Adeptus Custodes, Astra Militarum, Imperial Knights, Imperial Agents

**Chaos:** Chaos Space Marines, Chaos Daemons, Chaos Knights

**Aeldari:** Aeldari, Harlequins, Ynnari, Drukhari

**Xenos:** Necrons, Orks, T'au Empire, Tyranids, Genestealer Cults, Leagues of Votann

---

## Trained Model

A YOLO11x model trained on Google Colab is integrated for AI-assisted annotation and consumer detection.

- **Location**: `runs/yolo11x_run2_best.pt`
- **Trained on**: ~1,549 annotated images, 15 factions
- **Performance**: 54.7% mAP50 / 39.1% mAP50-95 on the 119-image val split. Detection recall 66%, faction top-1 on matched 64%. ([full Phase 0 baseline](docs/benchmarks/2026-04-13-phase0-baseline.md))
- **Note**: Lower mAP50 vs earlier model due to wider faction coverage and mixed-quality training images. Retraining planned using the clean training_data_v2 dataset once sufficient images are collected (target: 2,000 annotated → 80% mAP50).

---

## Data Storage

```
backend/
  training_data/              # ~18,600 source images
    {faction}/
      reddit/                 # scraped from Reddit
      dakkadakka/             # scraped from DakkaDakka forum
  training_data_annotations/  # one JSON per annotated image
  yolo_dataset/               # last YOLO export (train/val split)
    images/train|val/
    labels/train|val/
    data.yaml
    classes.txt
  confidence_scores.json      # per-image YOLO confidence (active learning)
```

---

## Running the Project

```bash
# Install all dependencies
npm install

# Start desktop annotator + backend
npm run dev

# Start mobile annotator (accessible on LAN for phone)
npm run dev:backend &
npm run dev:annotator-mobile

# Start consumer app
npm run dev:consumer
```

Individual ports:
- Desktop annotator: `localhost:5173`
- Backend API: `localhost:3001`
- Consumer scanner: `localhost:5174`
- Mobile annotator (LAN): `<your-ip>:5175`

---

## Annotation Workflow

### Desktop
1. `npm run dev` → open `localhost:5173`
2. Click "Start Annotating"
3. Optionally click "Get AI Suggestions" for model-predicted boxes
4. Accept/reject/redraw predictions, draw any missed miniatures
5. "Save & Next" — repeats for next image

### Mobile (away from home)
1. PC: export a zip batch via backend API or desktop annotator
2. Save zip to pCloud root
3. Phone: open https://40k-annotator.netlify.app, import zip
4. Annotate offline (drag to draw bboxes, pick faction per image)
5. Phone: "Export to File" → save JSON to pCloud
6. PC: `npm run sync:mobile` → imports annotations into backend

---

## Export & Training

```bash
# Validate annotations
curl -X POST http://localhost:3001/api/annotate/validate-export

# Export to YOLO format
curl -X POST http://localhost:3001/api/annotate/export

# Validate exported dataset
python3 scripts/validate_yolo_dataset.py backend/yolo_dataset

# Train (Google Colab recommended)
# See train_yolo_colab.ipynb
```

---

## Tech Stack Summary

| Layer | Tech |
|-------|------|
| Frontend (all 3 apps) | React 18, TypeScript, Tailwind CSS, Vite |
| Mobile PWA | vite-plugin-pwa, IndexedDB (idb), Netlify |
| Backend | Node.js, Express, TypeScript |
| Image processing | Sharp |
| ML model | YOLO11 (Ultralytics), trained on Google Colab |
| Offline storage | IndexedDB (~1GB limit on iOS Safari) |
| File sync | pCloud (cloud storage mounted at ~/pCloudDrive) |
| Hosting | Netlify (mobile annotator) |
