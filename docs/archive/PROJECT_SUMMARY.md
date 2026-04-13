# Photoanalyzer — Comprehensive Project Summary

> **Generated**: 2026-03-01
> **Project Version**: 7.0 (Quality Dashboard + Active Learning)
> **Status**: Active Development

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Monorepo Structure](#2-monorepo-structure)
3. [Workspace: Frontend (Desktop Annotator)](#3-workspace-frontend-desktop-annotator)
4. [Workspace: Backend (Express API)](#4-workspace-backend-express-api)
5. [Workspace: Consumer (Battle Scanner PWA)](#5-workspace-consumer-battle-scanner-pwa)
6. [Workspace: Annotator Mobile (Offline PWA)](#6-workspace-annotator-mobile-offline-pwa)
7. [Data Layout & File Paths](#7-data-layout--file-paths)
8. [API Reference](#8-api-reference)
9. [Data Types & Interfaces](#9-data-types--interfaces)
10. [Configuration Files](#10-configuration-files)
11. [Environment Variables](#11-environment-variables)
12. [Key Workflows & Data Flows](#12-key-workflows--data-flows)
13. [YOLO Export Format](#13-yolo-export-format)
14. [Testing](#14-testing)
15. [Current State & Model Performance](#15-current-state--model-performance)
16. [Dependencies](#16-dependencies)
17. [Known Issues & Architecture Decisions](#17-known-issues--architecture-decisions)

---

## 1. Project Overview

**Photoanalyzer** is a monorepo toolchain for building a Warhammer 40K miniature detection and classification model using YOLO. It consists of four applications:

| App | Purpose | Port |
|---|---|---|
| **frontend** | Desktop web annotator — draw bboxes, manage dataset | 5173 |
| **backend** | Express API — serves all three frontends, stores annotations, runs YOLO | 3001 |
| **consumer** | Consumer-facing PWA — scan your army, get faction counts | 5174 |
| **annotator-mobile** | Offline-first iOS/iPad PWA — touch annotation for field use | 5175 |

**Core Mission**: Create a high-quality YOLO training dataset of Warhammer 40K miniatures across many factions, train an accurate model, and expose it via a consumer scanning app.

**Annotation Count** (as of 2026-02-15): 707 images annotated
**Image Pool**: ~18,088 images in `backend/training_data/`
**Trained Model**: `runs/yolo11_colab_best.pt` (YOLOv8n, trained on 280 images)

---

## 2. Monorepo Structure

```
photoanalyzer/
├── package.json                   # Root — npm workspaces
├── .env / .env.example            # Environment variables (backend)
├── README.md
├── CLAUDE.md
├── STATUS.md
├── IMPROVEMENTS.md
├── TESTING.md
├── CONSUMER_APP_PLAN.md
│
├── frontend/                      # Desktop annotation UI
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── src/
│       ├── App.tsx
│       ├── components/
│       ├── types.ts
│       ├── types/dashboard.ts
│       └── theme/factionThemes.ts
│
├── backend/                       # Express API server
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── index.ts               # Server entry point
│       ├── types.ts
│       ├── services/
│       │   ├── annotationService.ts
│       │   ├── dashboardStatsService.ts
│       │   ├── activeLearningService.ts
│       │   └── yoloInferenceService.ts
│       ├── middleware/
│       │   ├── requestId.ts
│       │   └── errorHandler.ts
│       └── utils/logger.ts
│
├── consumer/                      # Battle Scanner PWA
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── src/
│       ├── App.tsx
│       ├── pages/
│       │   ├── ScanPage.tsx
│       │   └── ResultsPage.tsx
│       ├── components/
│       └── types/detection.ts
│
├── annotator-mobile/              # Offline iOS PWA annotator
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── src/
│       ├── App.tsx
│       ├── pages/
│       │   ├── HomePage.tsx
│       │   └── AnnotatePage.tsx
│       ├── components/
│       ├── lib/
│       │   ├── db.ts
│       │   ├── zip.ts
│       │   ├── sync.ts
│       │   └── id.ts
│       └── types.ts
│
├── scripts/                       # Python utility scripts
├── runs/                          # Trained YOLO model weights
│   └── yolo11_colab_best.pt
├── yolo_env/                      # Python virtual environment
├── backend/training_data/         # Source images (18,088)
├── backend/training_data_annotations/  # JSON annotation files
├── backend/yolo_dataset/          # Exported YOLO-format dataset
└── backend/confidence_scores.json # Per-image YOLO confidence scores
```

### Root `package.json` Workspaces

```json
{
  "workspaces": ["frontend", "backend", "consumer", "annotator-mobile"],
  "scripts": {
    "dev": "concurrently (all 4 apps)",
    "build": "build all in order",
    "test": "test all workspaces"
  }
}
```

---

## 3. Workspace: Frontend (Desktop Annotator)

**Path**: `frontend/`
**Port**: 5173
**Purpose**: Desktop browser app for drawing bounding boxes on miniature images to build the YOLO training dataset.

### Source Files

| File | Purpose |
|---|---|
| `src/App.tsx` | Root component. State-based view router: `annotation` vs `dashboard`. Fetches progress, handles view transitions. |
| `src/components/AnnotationInterface.tsx` | Full annotation workflow. Loads images, tracks progress, controls navigation between images. |
| `src/components/BboxAnnotator.tsx` | Canvas-based bbox drawing engine. Handles zoom, pan, draw, select, resize, undo/redo. |
| `src/components/QualityDashboard.tsx` | Quality statistics view. Shows metrics, charts, outlier detection, active learning controls. |
| `src/components/QualityIssuesModal.tsx` | Modal showing real-time validation issues (errors + warnings) before save. |
| `src/types.ts` | Core annotation types: `BboxAnnotation`, `Bbox`, etc. |
| `src/types/dashboard.ts` | Dashboard types: `DashboardStats`, `ActiveLearningStatus`, etc. |
| `src/theme/factionThemes.ts` | Per-faction color themes for UI elements. |

### Key Features

- **Model-only bboxes**: Single tier of bounding boxes per miniature (simplified from an earlier base+model hierarchy)
- **AI-assisted annotation**: "Get AI Suggestions" button hits YOLO inference endpoint, overlays predicted boxes
- **Undo / Redo**: Full undo stack with Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z (Command pattern)
- **Zoom & Pan**: Mouse wheel zoom, click-drag pan; all coordinates transform through a central utility
- **Two-tier validation**: Errors block save; warnings display but allow save
- **Active learning toggle**: "Prioritize by confidence" — serves lowest-confidence images first
- **Faction filtering**: Focus annotation session on a specific faction
- **Progress tracking**: Per-faction progress bar showing annotated / total

### Architecture Patterns

**Command Pattern (Undo/Redo)**
Each bbox operation (add, delete, move, resize) is encapsulated as a command object with `execute()` and `undo()` methods. Commands push onto a stack; undo pops them.

**Centralized Coordinate Transforms**
A single utility function converts between canvas-space and image-space coordinates, accounting for zoom level and pan offset. This is the single source of truth — no ad-hoc coordinate math anywhere else.

**Bbox Auto-Constraint**
When bboxes are drawn or dragged, they are automatically clamped to stay within the image bounds. Out-of-bounds errors are prevented rather than just detected.

### `vite.config.ts`

```ts
server: {
  proxy: {
    '/api': 'http://localhost:3001'
  }
}
```

---

## 4. Workspace: Backend (Express API)

**Path**: `backend/`
**Port**: 3001
**Purpose**: Central API server. Handles all annotation CRUD, validation, YOLO export, image serving, active learning inference, and mobile sync.

### Source Files

| File | Purpose |
|---|---|
| `src/index.ts` | Express app entry. Registers all routes and middleware. |
| `src/types.ts` | Backend types: `DetectedModel`, `AnalysisResult`, `BboxAnalysisConfig`, `ValidationError`, etc. |
| `src/services/annotationService.ts` | Core annotation logic: listing images, save/load JSON, bbox validation, YOLO export. |
| `src/services/dashboardStatsService.ts` | Aggregate quality statistics with 60s TTL cache. |
| `src/services/activeLearningService.ts` | Batch YOLO inference pipeline via Python subprocess. |
| `src/services/yoloInferenceService.ts` | Single-image YOLO inference for AI annotation suggestions. |
| `src/middleware/requestId.ts` | Injects `X-Request-ID` header for log tracing. |
| `src/middleware/errorHandler.ts` | Global error handler + 404 handler. |
| `src/utils/logger.ts` | Winston logger with daily rotating file output. |

### AnnotationService — Detail

**Image Listing**
- Reads from `backend/training_data/{faction}/{source}/`
- Per-faction limit: **110 images** (caps dataset to manageable size)
- Filters out already-annotated images for "next" queries

**Annotation Save**
- Validates bbox array (see Validation Logic below)
- Writes JSON to `backend/training_data_annotations/{imageId}.json`
- Triggers cache invalidation callback on DashboardStatsService

**Annotation Load**
- Reads existing JSON if present, returns empty array otherwise
- Returns image as base64-encoded data URI

**Bbox Validation Logic**

| Error Code | Condition | Severity |
|---|---|---|
| `BBOX_OUT_OF_BOUNDS` | Any corner outside image dimensions | Error — blocks save |
| `BBOX_TOO_SMALL` | Width or height < 5px | Error — blocks save |
| `DUPLICATE_BOX` | IoU > 0.9 with another box | Error — blocks save |
| Large box warning | Box covers > 90% of image | Warning — informs |
| Tiny box warning | Box area < 1% of image | Warning — informs |
| Crowded warning | > 20 boxes in image | Warning — informs |

**YOLO Export**
- Writes to `backend/yolo_dataset/`
- Coordinates normalized to [0, 1] range
- See [YOLO Export Format](#13-yolo-export-format) section

### DashboardStatsService — Detail

- Reads all annotation JSONs concurrently (max 50 at a time via `p-limit`)
- Computes:
  - Boxes per image (min, max, avg, median + histogram)
  - Box sizes per faction (for struggling-faction detection)
  - Annotation speed (daily annotations chart)
  - Outliers: tiny (<1%), huge (>90%), crowded (20+ boxes)
- **60-second TTL cache** — invalidated immediately on any save

### ActiveLearningService — Detail

- Spawns a Python subprocess: loads YOLO model once, runs batch inference over all unannotated images
- Output: JSON-lines format for streaming progress
- Scores each image by **max detection confidence** (lower = harder = annotate first)
- Writes scores atomically: temp file → `fsync` → rename to `confidence_scores.json`
- Fallback: if no scores file exists, default alphabetical ordering is used

### YoloInferenceService — Detail

- Spawns a Python subprocess per request (single image)
- Runs YOLO model with `conf=0.25` threshold
- Returns array of predicted boxes with confidence scores
- Typical inference time: ~34ms per image

### Middleware

**Request ID** (`src/middleware/requestId.ts`)
Injects `X-Request-ID` UUID header on every request. Appears in all log lines for tracing.

**Error Handler** (`src/middleware/errorHandler.ts`)
- Catches all unhandled errors, returns structured JSON
- 404 handler for unknown routes

### Logger (`src/utils/logger.ts`)

- Winston with daily rotating file
- Log files in `backend/logs/`
- Includes request ID in every line

---

## 5. Workspace: Consumer (Battle Scanner PWA)

**Path**: `consumer/`
**Port**: 5174
**Purpose**: Consumer-facing PWA for scanning Warhammer 40K armies and getting faction identification and counts.

### Source Files

| File | Purpose |
|---|---|
| `src/App.tsx` | State router: `scan` → `results` pages. |
| `src/pages/ScanPage.tsx` | Camera capture + photo upload. Submits image to `/api/detect`. |
| `src/pages/ResultsPage.tsx` | Detection results with bbox overlay canvas + faction cards. |
| `src/components/Header.tsx` | "BATTLE SCANNER" gothic-styled header. |
| `src/components/CameraCapture.tsx` | `getUserMedia` camera with front/rear switching. |
| `src/components/PhotoUpload.tsx` | Drag-and-drop / file picker with preview. |
| `src/components/ScanAnimation.tsx` | Loading overlay with orbiting animation effect. |
| `src/components/ArmySummary.tsx` | Total miniature count + faction badges. |
| `src/components/ResultsCard.tsx` | Per-faction expandable card with confidence bars. |
| `src/types/detection.ts` | `Detection`, `DetectionResult`, `FactionSummary` types. |

### Detection Flow

```
User → Camera/Upload → POST /api/detect (multipart blob)
     ← DetectionResult { detections[], factionSummary[], inferenceTime }
        → Canvas bbox overlay
        → Faction cards with counts + confidence bars
```

### Key Features

- Camera access with front/rear toggle
- Drag-and-drop or file picker upload
- Loading animation while backend processes
- Bounding box overlay drawn on canvas
- Faction grouping with color coding (matches training factions)
- Per-detection confidence scores
- PWA: installable, offline caching via service worker

### PWA Configuration (`vite.config.ts`)

- `vite-plugin-pwa` enabled
- Manifest: name, icons, theme color, display standalone
- Service worker: caches fonts, CSS, JS assets
- Works offline after first visit

---

## 6. Workspace: Annotator Mobile (Offline PWA)

**Path**: `annotator-mobile/`
**Port**: 5175 (with `--host` flag so LAN devices can connect)
**Purpose**: Touch-first offline-capable PWA for annotating on an iOS/iPad device. Import a batch of images via zip, annotate fully offline, sync back over WiFi when done.

### Source Files

| File | Purpose |
|---|---|
| `src/pages/HomePage.tsx` | Stats display, zip import button, sync controls, storage management (clear synced). |
| `src/pages/AnnotatePage.tsx` | Main annotation loop: load next image → draw → save → next. |
| `src/components/TouchCanvas.tsx` | Canvas with native touch event handlers: draw bboxes, pinch-zoom, pan. |
| `src/components/BottomToolbar.tsx` | Faction selector dropdown, Undo / Skip / Save buttons. |
| `src/components/PredictionCards.tsx` | Strip of AI prediction cards — tap to accept or reject. |
| `src/components/SyncStatus.tsx` | Online/offline indicator + count of pending-sync annotations. |

### Library Files (`src/lib/`)

**`db.ts` — IndexedDB Layer**
Uses the `idb` wrapper. Two stores:
- `images` — stores image blobs with metadata (faction, source, annotated flag)
- `annotations` — stores `MobileAnnotation` objects with sync status

Key functions:
```ts
saveImage(image: StoredImage): Promise<void>
getNextUnannotated(): Promise<StoredImage | null>
saveAnnotation(ann: MobileAnnotation): Promise<void>
getPendingSync(): Promise<MobileAnnotation[]>
markSynced(imageId: string): Promise<void>
getStats(): Promise<{ total, annotated, pendingSync }>
```

**`zip.ts` — Zip Import**
Uses `JSZip`. Extracts:
- Image files → blobs → `saveImage()`
- `manifest.json` → `BatchManifest` (faction/source metadata per image)
- `predictions.json` → prediction boxes per image

```ts
importZip(file: File, onProgress: (n: number) => void): Promise<void>
```

**`sync.ts` — WiFi Sync**
Sends pending annotations to backend in batches of 25.
```ts
syncAnnotations(onProgress: (sent, total) => void): Promise<SyncResult>
```

**`id.ts` — Safe UUID Generator**
```ts
// crypto.randomUUID() requires HTTPS — broken on http://192.168.x.x
// Fallback uses crypto.getRandomValues() which works on HTTP too
function generateId(): string
```

### Data Types (`src/types.ts`)

```ts
interface MobileBbox {
  id: string;
  x: number; y: number;
  width: number; height: number;
  label: string;           // faction label
  isPrediction: boolean;   // came from AI or user-drawn?
}

interface MobileAnnotation {
  imageId: string;
  bboxes: MobileBbox[];
  synced: boolean;
  skipped: boolean;
  timestamp: number;
}

interface StoredImage {
  id: string;
  blob: Blob;
  faction: string;
  source: string;
  annotated: boolean;
  width: number;          // resized width (max 1200px)
  height: number;
}

interface PredictionBox {
  x: number; y: number;
  width: number; height: number;
  confidence: number;
  label: string;
}

interface BatchManifest {
  images: Array<{
    id: string;
    faction: string;
    source: string;
    originalWidth: number;
    originalHeight: number;
    resizedWidth: number;
    resizedHeight: number;
  }>;
}
```

### Offline Workflow

```
Desktop Backend
    ↓ POST /api/mobile/export-batch
    ↓ → zip (images resized ≤1200px + manifest.json + predictions.json)
    ↓
iPad (annotator-mobile)
    → importZip() → IndexedDB
    → Annotate offline (draw bboxes, confirm/skip)
    → Auto-save drafts to IndexedDB
    ↓ (connect WiFi)
    → syncAnnotations() → POST /api/mobile/sync (batches of 25)
    ↓
Backend
    → Scale bbox coords back to original dimensions
    → Save as regular annotation JSON
    → Return { synced, skipped, failed }
```

### Critical iOS Safari Decisions

| Issue | Solution |
|---|---|
| `crypto.randomUUID()` fails on HTTP | Use `crypto.getRandomValues()` fallback in `id.ts` |
| Buttons over canvas don't receive taps | Move all buttons **outside** the canvas container |
| `setPointerCapture` + `preventDefault()` breaks `pointerup` | Use **native touch events** (`touchstart`, `touchmove`, `touchend`) with `{ passive: false }` |
| Page scrolls during bbox draw | `touch-action: none` on canvas element |

---

## 7. Data Layout & File Paths

### Training Images

```
backend/training_data/
  {faction}/
    {source}/
      image001.jpg
      image002.jpg
      ...
```

- ~18,088 total images
- Per-faction limit: 110 images served for annotation
- Factions: Space Marines, Blood Angels, Dark Angels, Death Guard, Custodes, Grey Knights, Adeptus Mechanicus, Necrons, Tyranids, Orks, Eldar, Dark Eldar, Tau, Sisters of Battle, and more

### Annotation JSONs

```
backend/training_data_annotations/
  {imageId}.json
```

Each file:
```json
{
  "imageId": "faction_source_filename",
  "imagePath": "relative/path/to/image.jpg",
  "imageWidth": 1920,
  "imageHeight": 1080,
  "bboxes": [
    {
      "id": "uuid",
      "x": 120, "y": 80,
      "width": 200, "height": 350,
      "label": "space_marines"
    }
  ],
  "annotatedAt": "2026-01-15T10:30:00Z"
}
```

### YOLO Dataset Export

```
backend/yolo_dataset/
  data.yaml
  images/
    train/
    val/
  labels/
    train/
    val/
```

### Confidence Scores

```
backend/confidence_scores.json
```
```json
{
  "imageId1": 0.34,
  "imageId2": 0.87,
  ...
}
```

Lower score = lower model confidence = higher annotation priority in active learning.

### Python Environment

```
yolo_env/          # Python virtualenv
  bin/python3
  lib/site-packages/
    ultralytics/   # YOLO
    ...
```

### Trained Model

```
runs/yolo11_colab_best.pt    # YOLOv8n weights, trained on 280 images
```

---

## 8. API Reference

### Annotation Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/annotate/images` | List all images with annotation status and faction |
| `GET` | `/api/annotate/next` | Get next unannotated image. Query: `?prioritize=true`, `?faction=X` |
| `GET` | `/api/annotate/image/:imageId` | Get image as base64 + existing annotation |
| `POST` | `/api/annotate/save` | Save annotation. Body: `{ imageId, bboxes[] }`. Returns `{ ok, errors[], warnings[] }` |
| `GET` | `/api/annotate/progress` | Annotation progress stats per faction |
| `GET` | `/api/annotate/predict/:imageId` | Run YOLO inference; return predicted boxes |
| `POST` | `/api/annotate/validate-export` | Validate all annotations before export |
| `POST` | `/api/annotate/export` | Export YOLO-format dataset to disk |

### Dashboard Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/dashboard/stats` | Aggregate quality stats (cached 60s) |

### Active Learning Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/active-learning/start-batch` | Start background batch inference on all unannotated images |
| `GET` | `/api/active-learning/status` | Batch progress: `{ running, processed, total, scored }` |

### Mobile Sync Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/mobile/export-batch` | Export zip: images (≤1200px) + manifest.json + predictions.json |
| `POST` | `/api/mobile/sync` | Receive mobile annotations, scale coords, save. Body: `{ annotations[] }` |
| `GET` | `/api/mobile/status` | Return annotated imageId set + progress stats |

### Consumer Detection Endpoint

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/detect` | Run YOLO detection on uploaded image. Multipart form, field: `image`. Returns `DetectionResult`. |

---

## 9. Data Types & Interfaces

### Frontend Types (`frontend/src/types.ts`)

```ts
interface Bbox {
  id: string;
  x: number;         // left edge, image-space pixels
  y: number;         // top edge, image-space pixels
  width: number;
  height: number;
  label: string;     // faction label
}

interface BboxAnnotation {
  imageId: string;
  imagePath: string;
  imageWidth: number;
  imageHeight: number;
  bboxes: Bbox[];
  annotatedAt: string;  // ISO timestamp
}
```

### Dashboard Types (`frontend/src/types/dashboard.ts`)

```ts
interface DashboardStats {
  totalImages: number;
  annotatedImages: number;
  totalBboxes: number;
  bboxesPerImage: {
    min: number; max: number; avg: number; median: number;
    histogram: Array<{ range: string; count: number }>;
  };
  bboxSizesByFaction: Record<string, { avg: number; min: number; max: number }>;
  annotationSpeed: Array<{ date: string; count: number }>;
  outliers: {
    tiny: string[];      // imageIds with <1% area boxes
    huge: string[];      // imageIds with >90% area boxes
    crowded: string[];   // imageIds with 20+ boxes
  };
}

interface ActiveLearningStatus {
  running: boolean;
  processed: number;
  total: number;
  scored: number;
}
```

### Backend Types (`backend/src/types.ts`)

```ts
interface DetectedModel {
  id: string;
  bbox: { x: number; y: number; width: number; height: number };
  confidence: number;
  label: string;
}

interface AnalysisResult {
  imageId: string;
  detections: DetectedModel[];
  inferenceTime: number;
}

interface ValidationError {
  code: 'BBOX_OUT_OF_BOUNDS' | 'BBOX_TOO_SMALL' | 'DUPLICATE_BOX';
  bboxId: string;
  message: string;
  severity: 'error' | 'warning';
}
```

### Consumer Types (`consumer/src/types/detection.ts`)

```ts
interface Detection {
  id: string;
  bbox: { x: number; y: number; width: number; height: number };
  confidence: number;
  label: string;        // faction
  displayName: string;  // human-readable
}

interface FactionSummary {
  faction: string;
  displayName: string;
  count: number;
  avgConfidence: number;
  color: string;         // CSS color for faction theme
}

interface DetectionResult {
  detections: Detection[];
  factionSummary: FactionSummary[];
  inferenceTime: number;
  imageWidth: number;
  imageHeight: number;
}
```

---

## 10. Configuration Files

### TypeScript Configs

All workspaces share similar tsconfig settings with slight variations:

| Setting | frontend | backend | consumer | annotator-mobile |
|---|---|---|---|---|
| `target` | ES2020 | ES2022 | ES2020 | ES2020 |
| `module` | — | CommonJS | — | — |
| `moduleResolution` | bundler | Node | bundler | bundler |
| `jsx` | react-jsx | — | react-jsx | react-jsx |
| `outDir` | — | `dist/` | — | — |
| `noEmit` | true | false | true | true |
| `strict` | true | true | true | true |

### Vite Configs

**frontend/vite.config.ts**
```ts
plugins: [react()]
server.proxy: { '/api': 'http://localhost:3001' }
```

**consumer/vite.config.ts**
```ts
plugins: [react(), VitePWA({ ... })]
server.proxy: { '/api': 'http://localhost:3001' }
// PWA: manifest, service worker, caches fonts + assets
```

**annotator-mobile/vite.config.ts**
```ts
plugins: [react(), VitePWA({ ... })]
server: { host: true }   // enables LAN access (--host)
server.proxy: { '/api': 'http://localhost:3001' }
```

### Tailwind Config (all workspaces share same theme)

```js
theme.extend = {
  fontFamily: {
    gothic: ['Cinzel', 'serif'],      // heading font
    grim:   ['Orbitron', 'monospace'] // label font
  },
  colors: {
    gothic: {
      darker: '#0a0a0a',
      dark:   '#2a3d52',
      medium: '#3d4a63',
      light:  '#5a6b82'
    }
  },
  boxShadow: {
    'glow-red':    '0 0 20px rgba(255,0,0,0.4)',
    'glow-purple': '0 0 20px rgba(128,0,255,0.4)',
    'glow-blue':   '0 0 20px rgba(0,100,255,0.4)',
    'glow-cyan':   '0 0 20px rgba(0,200,255,0.4)',
    'glow-amber':  '0 0 20px rgba(255,180,0,0.4)',
    'glow-green':  '0 0 20px rgba(0,200,100,0.4)'
  },
  animation: {
    'pulse-glow':   'pulse-glow 2s ease-in-out infinite',
    'fade-in-down': 'fade-in-down 0.3s ease-out',
    'glow-pulse':   'glow-pulse 3s ease-in-out infinite'
  }
}
```

---

## 11. Environment Variables

Full list from `.env.example`:

```env
# API Keys
OPENROUTER_API_KEY=        # Claude Vision API (via OpenRouter)
ROBOFLOW_API_KEY=          # Optional Roboflow YOLO endpoint

# Server
PORT=3001

# YOLO Model Paths
BBOX_MODEL=runs/yolo11_colab_best.pt
CLASSIFIER_MODEL=
TRIANGULATION_MODEL=

# YOLO Thresholds
BBOX_IOU_THRESHOLD=0.5
TRIANGULATION_THRESHOLD=0.3
TRIANGULATION_MARGIN=0.05

# Clump Separation (dense miniature groups)
ENABLE_CLUMP_SEPARATION=false
CLUMP_MIN_OVERLAP=0.3
CLUMP_MAX_MERGE_AREA=0.5

# Analysis Mode
USE_BBOX=true              # Default recommended mode
USE_TWO_TIER=false         # Legacy two-stage cascade

# Classification Accuracy Options
ENABLE_CLIP=false          # Visual pre-filtering with CLIP service
ENABLE_CLIP_ONLY=false     # CLIP-only classification (bypass LLMs)
ENABLE_CLIP_DISAGREEMENT=false   # Cross-validate LLM with CLIP
ENABLE_FEW_SHOT=false      # Example-based learning
```

---

## 12. Key Workflows & Data Flows

### Workflow 1: Desktop Annotation

```
1. User opens frontend (localhost:5173)
2. Clicks "Start Annotating"
3. Frontend → GET /api/annotate/next[?prioritize=true][?faction=X]
4. Backend returns imageId + base64 image
5. User views image on canvas, draws model bboxes
   - Scroll wheel → zoom
   - Click-drag on empty area → pan
   - Click-drag on image → draw new bbox
   - Click existing bbox → select (resize handles appear)
   - Ctrl+Z → undo last operation
6. Optional: Click "Get AI Suggestions"
   → GET /api/annotate/predict/:imageId
   → Backend spawns Python → YOLO inference → returns boxes
   → User accepts/rejects/adjusts predictions
7. User clicks "Save & Next"
   → POST /api/annotate/save { imageId, bboxes[] }
   → Backend validates (errors block, warnings inform)
   → If OK: saves JSON, invalidates dashboard cache
   → Frontend loads next image
```

### Workflow 2: Quality Dashboard

```
1. User clicks "Quality Dashboard" tab in frontend
2. Frontend → GET /api/dashboard/stats
3. Backend (if cache miss):
   - Reads all annotation JSONs concurrently (p-limit 50)
   - Computes aggregate stats
   - Caches for 60 seconds
4. Frontend renders:
   - Boxes-per-image histogram
   - Per-faction size chart
   - Daily annotation speed chart
   - Outlier image lists (tiny/huge/crowded)
5. Any save in AnnotationInterface invalidates the cache instantly
```

### Workflow 3: Active Learning

```
1. User clicks "Start Batch Inference" in Quality Dashboard
2. Frontend → POST /api/active-learning/start-batch
3. Backend spawns Python process:
   - Loads YOLO model once
   - Iterates all unannotated images
   - For each: run inference → score = max(detection confidences)
   - Output JSON-lines to stdout for progress streaming
   - Write scores atomically to confidence_scores.json
4. Frontend polls GET /api/active-learning/status
   - Shows progress bar (processed / total)
5. User enables "Prioritize by confidence" toggle in AnnotationInterface
6. Frontend → GET /api/annotate/next?prioritize=true
7. Backend reads confidence_scores.json → serves lowest-confidence image
8. User annotates the hardest images first → fastest model improvement
```

### Workflow 4: Mobile Annotation

```
Desktop:
1. User clicks "Export Batch for Mobile"
2. POST /api/mobile/export-batch
3. Backend:
   - Selects unannotated images
   - Resizes each to max 1200px (preserving aspect ratio, via Sharp)
   - Packs: images + manifest.json + predictions.json → zip stream
4. Browser downloads zip file

iPad (annotator-mobile at http://[desktop-ip]:5175):
5. User opens app in Safari
6. Taps "Import Batch" → selects zip from Files
7. importZip() extracts → stores images + predictions in IndexedDB
8. User annotates:
   - TouchCanvas: finger draw → bbox
   - Pinch → zoom
   - Two-finger drag → pan
   - PredictionCards strip: tap to accept a prediction
   - BottomToolbar: choose faction, Undo/Skip/Save
9. Annotations auto-saved to IndexedDB as drafts
10. When done / back on WiFi:
11. Taps "Sync Now" on HomePage
12. syncAnnotations() sends annotations in batches of 25 to backend
13. Backend scales bbox coords from resized→original dimensions
14. Backend saves as regular annotation JSON files
15. Returns { synced: N, skipped: M, failed: 0 }
```

### Workflow 5: Consumer Detection

```
1. User opens consumer app (localhost:5174)
2. Takes photo via camera or uploads image file
3. ScanPage shows loading animation
4. POST /api/detect (multipart/form-data, field: "image")
5. Backend runs YOLO inference
6. Returns DetectionResult:
   {
     detections: [{ bbox, confidence, label, displayName }],
     factionSummary: [{ faction, count, avgConfidence, color }],
     inferenceTime: 340
   }
7. ResultsPage:
   - Draws image on canvas
   - Overlays colored bboxes for each detection
   - Shows ArmySummary (total count + faction chips)
   - Shows per-faction ResultsCards (expandable, confidence bars)
```

---

## 13. YOLO Export Format

### File Structure

```
yolo_dataset/
  data.yaml
  images/train/*.jpg
  images/val/*.jpg
  labels/train/*.txt
  labels/val/*.txt
```

### `data.yaml`

```yaml
train: images/train
val: images/val
nc: 30          # number of faction classes
names:
  - space_marines
  - blood_angels
  - death_guard
  # ... all factions
```

### Label Format (bbox only — no base)

```
# class x_center y_center width height
0 0.523 0.410 0.187 0.324
```

All coordinates normalized to [0, 1] relative to image dimensions.

### Label Format (bbox + base keypoints)

```
# class x_center y_center width height kp1x kp1y kp1v kp2x kp2y kp2v kp3x kp3y kp3v kp4x kp4y kp4v
0 0.523 0.410 0.187 0.324 0.430 0.650 2 0.616 0.650 2 0.616 0.734 2 0.430 0.734 2
```

17 values per detection: 5 bbox + (4 keypoints × 3 values each)
Keypoint visibility: `2` = visible, `1` = occluded, `0` = not labeled

---

## 14. Testing

### Backend Unit Tests

**File**: `backend/src/services/__tests__/annotationService.validation.test.ts`
**Runner**: Vitest
**Count**: 28 test cases

Coverage:
- Bbox validation: out of bounds (all 4 edges), too small (width, height), exact boundary conditions
- Base-outside-model constraint
- Duplicate detection (IoU > 0.9)
- IoU calculation correctness
- Edge cases: empty bbox array, single bbox, adjacent non-overlapping bboxes

Run:
```bash
cd backend && npm test
```

### Python Dataset Validation Tests

**File**: `scripts/test_validate_yolo_dataset.py`
**Runner**: pytest
**Count**: 25+ test cases

Coverage:
- Directory structure validation
- `data.yaml` format and class list
- Label file format (correct column counts)
- Coordinate range (all values in [0, 1])
- Keypoint format and visibility flags
- Overlap detection between labels

Run:
```bash
cd scripts && pytest test_validate_yolo_dataset.py -v
```

### Frontend Tests

**Runner**: Vitest + Testing Library
**Location**: `frontend/src/**/__tests__/`

Run:
```bash
cd frontend && npm test
```

---

## 15. Current State & Model Performance

### Annotation Progress (2026-02-15)

- **Total annotated**: 707 images
- **Training split**: ~280 used for first model training (Colab)
- **Current model**: YOLOv8n, `runs/yolo11_colab_best.pt`

### Model Performance by Faction

| Faction | mAP50 | Notes |
|---|---|---|
| Custodes | 97% | Excellent — distinctive gold armor |
| Grey Knights | 96% | Excellent — distinctive silver/teal |
| Necrons | ~70% | Good |
| Space Marines | ~65% | Good — many variants dilute accuracy |
| Tyranids | ~60% | Moderate |
| Eldar | ~55% | Moderate |
| Tau | ~50% | Moderate |
| Adeptus Mechanicus | 25.6% | Poor — needs more annotation |
| Death Guard | 3.4% | Very poor — heavily underrepresented |

**Overall mAP50**: 63.2%

### What Needs Work

1. **Death Guard** — Critically underrepresented; prioritize in active learning
2. **Adeptus Mechanicus** — Second worst; needs focused annotation session
3. **Image diversity** — More varied lighting/backgrounds would help generalization

### Active Learning Status

- Batch inference: Operational
- Confidence scores: Generated and stored
- Prioritization: Ready (toggle in UI)

---

## 16. Dependencies

### Root

```json
{
  "devDependencies": {
    "concurrently": "^8.x"
  }
}
```

### Frontend

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "axios": "^1.x",
    "uuid": "^9.x"
  },
  "devDependencies": {
    "typescript": "^5.2.2",
    "vite": "^4.5.0",
    "@vitejs/plugin-react": "^4.x",
    "tailwindcss": "^3.3.5",
    "vitest": "^0.34.x",
    "@testing-library/react": "^14.x",
    "eslint": "^8.x"
  }
}
```

### Backend

```json
{
  "dependencies": {
    "express": "^4.x",
    "cors": "^2.x",
    "axios": "^1.x",
    "sharp": "^0.32.x",
    "archiver": "^6.x",
    "winston": "^3.x",
    "winston-daily-rotate-file": "^4.x",
    "zod": "^3.x",
    "p-limit": "^4.x",
    "uuid": "^9.x"
  },
  "devDependencies": {
    "typescript": "^5.2.2",
    "ts-node": "^10.x",
    "nodemon": "^3.x",
    "vitest": "^0.34.x"
  }
}
```

### Consumer

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "axios": "^1.x"
  },
  "devDependencies": {
    "typescript": "^5.2.2",
    "vite": "^4.5.0",
    "@vitejs/plugin-react": "^4.x",
    "vite-plugin-pwa": "^0.16.x",
    "tailwindcss": "^3.3.5"
  }
}
```

### Annotator Mobile

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "idb": "^7.x",
    "jszip": "^3.x"
  },
  "devDependencies": {
    "typescript": "^5.2.2",
    "vite": "^4.5.0",
    "@vitejs/plugin-react": "^4.x",
    "vite-plugin-pwa": "^0.16.x",
    "tailwindcss": "^3.3.5"
  }
}
```

---

## 17. Known Issues & Architecture Decisions

### iOS Safari Quirks (all in `annotator-mobile`)

| Problem | Symptom | Fix |
|---|---|---|
| `crypto.randomUUID()` needs HTTPS | Silent failures on `http://192.168.x.x` | Use `crypto.getRandomValues()` fallback — see `src/lib/id.ts` |
| Buttons over canvas block touch | Tapping Save/Undo does nothing | Buttons placed **outside** canvas DOM container |
| Pointer events break on iOS | `pointerup` never fires after `setPointerCapture` + `preventDefault()` | Replaced with native `touchstart/touchmove/touchend` + `{ passive: false }` |
| Page scrolls while drawing | Canvas draw interrupted by scroll gesture | `touch-action: none` on canvas element |

### Backend Architecture Decisions

| Decision | Rationale |
|---|---|
| Per-faction 110-image limit | Keeps dataset balanced and manageable; prevents dominant factions from skewing training |
| 60s TTL cache for dashboard | Stats computation is expensive (50 concurrent reads); cache prevents overload |
| Atomic confidence score writes | Prevents partial reads of scores file during write; temp file → rename |
| Spawn Python subprocess per inference | Isolates YOLO environment from Node.js; Python process manages GPU memory |
| Batch mode loads model once | Amortizes model load cost (~2s) across many images in active learning |
| Errors block save, warnings inform | Dataset quality is critical; better to force fix than silently accumulate bad data |

### Frontend Architecture Decisions

| Decision | Rationale |
|---|---|
| Command pattern for undo | Clean separation; easy to add new undoable operations; no state diffing needed |
| Single coordinate transform function | Eliminated bugs from ad-hoc zoom/pan math scattered across components |
| Model-only bboxes (no base tier) | Simplified from base+model hierarchy; cleaner training signal for YOLO |
| Real-time validation on save | Faster feedback than pre-save validation; users fix issues immediately |

### Known Backend Issues

- Pre-existing TypeScript errors in test files and legacy modules — `index.ts` itself compiles clean
- YOLO Python subprocess stderr sometimes appears in logs when no GPU is available (CUDA warning noise)

---

*End of PROJECT_SUMMARY.md*
