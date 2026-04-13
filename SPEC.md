# Technical Specification — Warhammer 40K Miniature Recogniser

**Document version**: 1.0
**Last updated**: March 2026
**Author**: Sinan
**Status**: Active development — annotation in progress, second model trained

---

## 1. Overview

A computer vision pipeline for identifying and counting Warhammer 40K miniatures by faction from a photograph. The system has three phases: **annotate** training images with bounding boxes, **train** a YOLO object detection model, and **detect** miniatures in new photos via a consumer app.

The project is a TypeScript/Node.js monorepo containing four workspaces: a desktop annotation tool, a mobile annotation PWA, a consumer scanner PWA, and a shared Express backend. A custom-trained YOLO11 model provides AI-assisted annotation and real-time detection.

---

## 2. Background & Motivation

Warhammer 40K tabletop games involve armies of painted miniatures from 30+ factions. Currently there is no automated way to identify which factions are on the table or how many models each player has fielded. Tournament organisers, casual players, and content creators would benefit from a "point your camera and get a faction breakdown" tool.

No off-the-shelf model exists for this domain. The miniatures are hand-painted, vary wildly in paint scheme, and are often photographed in cluttered battlefield settings. A custom object detection model trained on purpose-built annotations is required.

The project was started to solve this from scratch: scrape reference images, build annotation tooling, train iteratively, and ship a consumer PWA.

---

## 3. Goals & Non-Goals

### Goals

- Annotate 12,000+ images across 24 model classes with high-quality bounding boxes
- Train a YOLO model achieving >75% mAP50 across all 24 classes
- Ship a mobile-friendly consumer app that returns faction counts from a photo in <5 seconds
- Provide offline-capable annotation tooling so work can happen anywhere (phone, tablet, desktop)
- Use active learning to focus annotation effort where the model is weakest

### Non-Goals

- Real-time video detection (single-image inference only)
- Individual unit identification (faction-level classification, not "Intercessor vs Hellblaster")
- Point-cost calculation or army list validation
- Cloud-hosted inference (runs locally on the developer's machine for now)
- Multi-user collaboration or authentication (single-user annotation pipeline)

---

## 4. Stakeholders

| Role | Who | Responsibility |
|------|-----|----------------|
| Developer / annotator | Sinan | Everything: annotation, training, frontend, backend, deployment |
| End users | Warhammer 40K players | Use consumer scanner to identify armies |
| Hosting | Netlify | Mobile annotator PWA hosting |

---

## 5. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                       MONOREPO                              │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   frontend/   │  │   consumer/   │  │ annotator-mobile/ │
│  │   Desktop     │  │   Battle     │  │   Mobile PWA     │  │
│  │   Annotator   │  │   Scanner    │  │   (Offline)      │  │
│  │   :5173       │  │   :5174      │  │   :5175          │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │             │
│         └────────┬────────┘                    │             │
│                  │                             │             │
│         ┌────────▼─────────┐          ┌───────▼──────────┐  │
│         │    backend/       │          │   IndexedDB      │  │
│         │    Express API    │◄─sync────│   (on device)    │  │
│         │    :3001          │          └──────────────────┘  │
│         └────────┬─────────┘                                │
│                  │                                          │
│         ┌────────▼─────────┐                                │
│         │  training_data/   │   ~18,600 images              │
│         │  annotations/     │   JSON per image              │
│         │  yolo_dataset/    │   YOLO export                 │
│         │  confidence_scores│   Active learning             │
│         └──────────────────┘                                │
│                                                             │
│         ┌──────────────────┐                                │
│         │  YOLO11 Model    │   .pt file in runs/            │
│         │  (Python/ONNX)   │   Spawned from Node.js         │
│         └──────────────────┘                                │
└─────────────────────────────────────────────────────────────┘

        ┌──────────────────┐
        │   Google Colab    │   Training environment
        │   (GPU)           │   Produces .pt model files
        └──────────────────┘
```

### Component Interaction Summary

1. **Desktop Annotator** ↔ Backend: REST API over localhost. Loads images as base64, saves annotations as JSON, requests AI predictions.
2. **Consumer Scanner** → Backend: Uploads photo via multipart POST, receives detection results with bboxes and faction summaries.
3. **Mobile Annotator** → Backend (batch export): Downloads zip of resized images + manifest. Works offline. Syncs completed annotations back via chunked POST.
4. **Backend** → YOLO Model: Spawns Python subprocess for inference (single-image or batch). Python loads Ultralytics YOLO, runs prediction, returns JSON via stdout.
5. **Backend** → Filesystem: All data is file-based (images on disk, annotations as JSON files, YOLO dataset as directory structure).

---

## 6. Detailed Design

### 6.1 Desktop Annotator (`frontend/`)

**Tech**: React 18, TypeScript, Vite, Tailwind CSS, Axios

**Key modules**:

| File | Purpose |
|------|---------|
| `App.tsx` | Shell with Annotation/Dashboard navigation |
| `AnnotationInterface.tsx` | Main annotation UI: image loading, progress, AI workflow |
| `BboxAnnotator.tsx` | HTML5 Canvas — bbox drawing with zoom, pan, undo/redo |
| `QualityDashboard.tsx` | Stats dashboard with active learning controls |
| `QualityIssuesModal.tsx` | Validation error/warning display |
| `types.ts` | `BboxAnnotation` interface |
| `types/dashboard.ts` | Dashboard & active learning types |

**Annotation data model** (`BboxAnnotation`):

```typescript
interface BboxAnnotation {
  id: string
  x: number; y: number; width: number; height: number  // model bbox (pixels)
  classLabel: string                                     // faction name
  baseBbox?: { x; y; width; height }                     // optional base bbox
  confidence?: number                                    // AI confidence (0–1)
  isPrediction?: boolean                                 // AI-generated, pending validation
  isAccepted?: boolean                                   // user accepted prediction
  validationAction?: 'accepted' | 'rejected' | 'redrawn'
  originalPrediction?: boolean
}
```

**Architectural patterns**:

- **Command pattern** for undo/redo: `AddModelBoxCommand`, `DeleteModelBoxCommand`, `AddBaseBoxCommand`, `DeleteBaseBoxCommand`. Each implements `execute()` and `undo()`. No full-state snapshots — operations are reversible.
- **Centralised coordinate transforms**: `screenToImage()` and `imageToScreen()` are the single source of truth for zoom/pan calculations. All mouse/touch handlers route through these.
- **Two-tier validation**: Errors block save (bbox out of bounds, base outside model). Warnings inform but allow save (duplicates, tiny boxes).

### 6.2 Mobile Annotator PWA (`annotator-mobile/`)

**Tech**: React 18, TypeScript, Vite, Tailwind CSS, vite-plugin-pwa, idb (IndexedDB wrapper), JSZip

**Deployed to**: https://40k-annotator.netlify.app

**Key modules**:

| File | Purpose |
|------|---------|
| `pages/HomePage.tsx` | Stats dashboard, zip import, sync, storage management |
| `pages/AnnotatePage.tsx` | Annotation loop: load → draw → confirm → save & next |
| `components/TouchCanvas.tsx` | Canvas with native touch draw, pinch-zoom, pan |
| `components/BottomToolbar.tsx` | Faction chips, undo/skip/save, progress bar |
| `components/PredictionCards.tsx` | AI prediction accept/reject cards |
| `lib/db.ts` | IndexedDB operations (images store + annotations store) |
| `lib/zip.ts` | Zip extraction (images + manifest + predictions) |
| `lib/sync.ts` | Chunked POST to backend (batches of 25) |
| `lib/id.ts` | Safe UUID generator (crypto.getRandomValues fallback) |

**Offline architecture**:

```
Import zip → IndexedDB ──► Annotate offline ──► Export JSON ──► Sync to backend
                │                                                    │
                ▼                                                    ▼
          images store                                    POST /api/mobile/sync
         annotations store                                (batches of 25)
```

- Images stored as Blobs in IndexedDB (~1GB limit on iOS Safari)
- Batches limited to 500–1000 images to stay within storage limits
- `terminated()` callback handles iOS Safari background DB eviction
- Coordinates stored in resized dimensions (max 1200px); backend scales back to original on sync

**Mobile-specific constraints** (hard-won lessons):

| Issue | Solution |
|-------|----------|
| `crypto.randomUUID()` HTTPS-only | `generateId()` uses `crypto.getRandomValues()` fallback |
| Buttons over `touch-action: none` canvas don't receive clicks on iOS | Interactive buttons placed outside canvas container |
| `setPointerCapture` + `preventDefault` breaks `pointerup` on iOS | Native touch events with `{ passive: false }` |
| IndexedDB ~1GB on iOS Safari | Batch imports capped at 500–1000 |
| Pull-to-refresh conflicts with canvas | `overscroll-behavior: none` on body |
| iPhone notch/home indicator | `env(safe-area-inset-bottom)` on bottom toolbar |
| Touch target size | Minimum 44px height (Apple HIG) |

### 6.3 Consumer Scanner PWA (`consumer/`)

**Tech**: React 18, TypeScript, Vite, Tailwind CSS, vite-plugin-pwa, idb, Axios

**Key modules**:

| File | Purpose |
|------|---------|
| `ScanPage.tsx` | Camera capture + photo upload entry point |
| `ResultsPage.tsx` | Detection results with bbox overlay on canvas |
| `CameraCapture.tsx` | getUserMedia camera with front/rear switching |
| `PhotoUpload.tsx` | Drag-and-drop / file picker with preview |
| `ScanAnimation.tsx` | Loading overlay during inference |
| `ArmySummary.tsx` | Total count + faction badges |
| `ResultsCard.tsx` | Per-faction expandable card with confidence bars |

**Detection data model**:

```typescript
interface DetectionResult {
  imageWidth: number; imageHeight: number
  detections: Array<{
    faction: string
    confidence: number
    bbox: { x; y; width; height }
  }>
  summary: Array<{
    faction: string; count: number
    avgConfidence: number; color: string
  }>
  totalDetected: number
  inferenceTimeMs: number
}
```

**User flow**: Capture/upload photo → `POST /api/detect` (multipart) → receive `DetectionResult` → render bbox overlay + faction summary cards.

### 6.4 Backend (`backend/`)

**Tech**: Node.js, Express 4, TypeScript, Sharp, Multer, Archiver, Winston, Zod, onnxruntime-node

**Runtime**: tsx watch (development), tsc + node (production)

#### Services

| Service | File | Purpose |
|---------|------|---------|
| Annotation | `annotationService.ts` | CRUD for annotations, validation, YOLO export, progress tracking, image flagging |
| Dashboard Stats | `dashboardStatsService.ts` | Quality metrics with 60s in-memory cache, invalidated on save |
| Active Learning | `activeLearningService.ts` | Confidence scoring, batch Python inference, prioritised ordering |
| YOLO Inference | `yoloInferenceService.ts` | Single-image inference, consumer detection + summarisation |

#### Backend data model (`ImageAnnotation`):

```typescript
interface ImageAnnotation {
  imageId: string
  imagePath: string
  faction: string
  source: 'reddit' | 'dakkadakka'
  width: number; height: number
  annotations: Array<{
    id: string
    modelBbox: { x; y; width; height }   // pixels
    baseBbox?: { x; y; width; height }    // optional
    classLabel: string
    confidence?: number
    validationAction?: 'accepted' | 'rejected' | 'redrawn'
    originalPrediction?: boolean
  }>
  rejectedPredictions?: Array<{ id; modelBbox; classLabel; confidence }>
  redrawnPredictions?: Array<{ id; modelBbox; classLabel; confidence }>
  annotatedAt: string
  annotatedBy: string
}
```

#### API Endpoints

**Annotation endpoints**:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/annotate/images` | List all images with annotation status |
| GET | `/api/annotate/next` | Next unannotated image (supports `?prioritize=true&faction=X`) |
| GET | `/api/annotate/image/:imageId` | Image as base64 + dimensions + existing annotation |
| POST | `/api/annotate/save` | Save annotation (validates first, blocks on errors) |
| GET | `/api/annotate/progress` | Annotation progress stats by faction |
| POST | `/api/annotate/flag` | Flag image as unusable (permanent skip) |
| GET | `/api/annotate/flagged-count` | Count of flagged images |
| GET | `/api/annotate/sample/:faction` | Random annotated samples for consistency audit |
| POST | `/api/annotate/validate-export` | Validate entire dataset pre-export |
| POST | `/api/annotate/export` | Export to YOLOv8-pose format (validates first) |

**Mobile endpoints**:

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/mobile/export-batch` | Zip of resized images + manifest + optional predictions |
| POST | `/api/mobile/sync` | Receive mobile annotations (scales coords back to original) |
| GET | `/api/mobile/status` | Annotated IDs + progress for dedup |

**Inference endpoints**:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/annotate/predict/:imageId` | AI predictions for annotation assistance |
| POST | `/api/detect` | Consumer detection (multipart image upload, 20MB limit) |

**Dashboard & active learning**:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/dashboard/stats` | Annotation quality statistics |
| POST | `/api/active-learning/start-batch` | Start background batch inference |
| GET | `/api/active-learning/status` | Batch progress + total scored |

**Other**:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Health check + model availability |
| POST | `/api/consumer/feedback` | Save consumer detection feedback |

#### Middleware

- **CORS**: Open (all origins, development mode)
- **Request ID**: UUID attached to every request for log correlation
- **Body parsers**: JSON (100KB default, 10MB for mobile sync)
- **Error handler**: Centralised with structured error responses
- **Multer**: Multipart uploads to `/tmp/battlescanner-uploads/` (20MB limit)

---

## 7. Data Flow

### 7.1 Annotation Flow (Desktop)

```
User clicks "Start Annotating"
    │
    ▼
GET /api/annotate/next ──► Backend scans training_data/, cross-references
    │                       annotations/, returns next unannotated image
    ▼                       (optionally prioritised by confidence score)
GET /api/annotate/image/:id
    │
    ▼
Backend reads image from disk, encodes base64,
gets dimensions via Sharp, returns with any existing annotation
    │
    ▼
User draws model bboxes ──► (optionally) GET /api/annotate/predict/:id
    │                        for AI-suggested boxes
    ▼
User draws base bboxes (auto-constrained inside model bbox)
    │
    ▼
POST /api/annotate/save ──► Backend validates (errors block, warnings pass)
    │                        ──► Writes JSON to training_data_annotations/
    ▼                        ──► Invalidates dashboard cache
Next image loads automatically
```

### 7.2 Annotation Flow (Mobile)

```
PC: POST /api/mobile/export-batch
    │
    ▼
Backend resizes images to max 1200px via Sharp,
packages into zip with manifest.json + predictions.json
    │
    ▼
Zip saved to pCloud ──► Phone downloads from pCloud
    │
    ▼
Phone: importZip() ──► Extracts to IndexedDB (images + annotations stores)
    │
    ▼
Annotate offline (touch draw, faction select, accept/reject AI predictions)
    │
    ▼
Phone: "Export to File" ──► JSON saved to pCloud
    │
    ▼
PC: npm run sync:mobile ──► Reads JSON, calls POST /api/mobile/sync
    │
    ▼
Backend: scales coords from 1200px back to original dimensions,
converts mobile format to ImageAnnotation, saves
```

### 7.3 Consumer Detection Flow

```
User captures/uploads photo
    │
    ▼
POST /api/detect (multipart, max 20MB)
    │
    ▼
Backend saves to /tmp, spawns Python:
  YOLO model predicts boxes ──► Returns JSON via stdout
    │
    ▼
Backend groups detections by faction, maps class aliases
to canonical names, attaches faction colours
    │
    ▼
Returns DetectionResult: bboxes + faction summaries + timing
    │
    ▼
Consumer app renders bbox overlay on canvas + summary cards
    │
    ▼
Uploaded file cleaned up from /tmp
```

### 7.4 Training Flow

```
POST /api/annotate/validate-export
    │
    ▼
Validates all annotations (bbox bounds, sizes, duplicates)
    │
    ▼
POST /api/annotate/export
    │  Body: { trainSplit: 0.8, balanced: false }
    ▼
Converts annotations to YOLO format:
  - Model bbox → class x_center y_center width height (normalised 0–1)
  - Base bbox → 4 keypoints (TL, TR, BR, BL) with visibility flags
  - Missing base → 5 values only (no keypoints)
    │
    ▼
Writes to yolo_dataset/:
  images/train/  images/val/
  labels/train/  labels/val/
  data.yaml      classes.txt
    │
    ▼
Upload to Google Colab ──► Train YOLO11 ──► Download best.pt
    │
    ▼
Place best.pt in runs/ ──► Available for inference
```

---

## 8. Data Storage

All storage is file-system based. No database.

```
backend/
├── training_data/                    # ~18,600 source images
│   └── {faction}/
│       ├── reddit/                   # Scraped from r/Warhammer40k etc.
│       └── dakkadakka/               # Scraped from DakkaDakka forum
├── training_data_annotations/        # One JSON file per annotated image
│   └── {imageId}.json                # ImageAnnotation format
├── yolo_dataset/                     # Last YOLO export
│   ├── images/
│   │   ├── train/
│   │   └── val/
│   ├── labels/
│   │   ├── train/
│   │   └── val/
│   ├── data.yaml
│   └── classes.txt
├── confidence_scores.json            # Per-image YOLO confidence (active learning)
├── consumer_feedback/                # Consumer detection feedback files
│   └── feedback-{timestamp}.json
└── logs/
    ├── all.log
    └── error.log

runs/
├── yolo11_colab_best.pt              # First model (8 classes, 63.2% mAP50)
└── yolo11x_run2_best.pt             # Second model (15 classes, 54.7% mAP50 / 39.1% mAP50-95)

yolo_env/                             # Python venv with ultralytics
└── bin/python3

annotator-mobile/
└── (browser IndexedDB)               # Offline image + annotation storage
    ├── images store                   # StoredImage { imageId, faction, blob, width, height, predictions? }
    └── annotations store             # MobileAnnotation { imageId, bboxes, completed, syncedAt, ... }
```

### Dataset Statistics (March 2026)

| Metric | Value |
|--------|-------|
| Total images | ~18,600 |
| Factions | 24 model classes (30 image directories) |
| Sources | Reddit, DakkaDakka |
| Annotated | ~1,500 / 12,000 target (12.6%) |
| Images shown per faction (capped) | 400 |
| Fully annotated factions (110+) | 12 |
| In-progress factions | 3 |
| Not started | 15 |

### YOLO Export Format (YOLOv8-Pose)

```
# Model with base (17 values):
# class x_center y_center width height kp_tl_x kp_tl_y vis kp_tr_x kp_tr_y vis kp_br_x kp_br_y vis kp_bl_x kp_bl_y vis
0 0.500 0.500 0.300 0.200 0.400 0.400 1 0.600 0.400 1 0.600 0.600 1 0.400 0.600 1

# Model without base (5 values):
0 0.500 0.500 0.300 0.200
```

All coordinates normalised to 0–1. Keypoints represent the four corners of the base bbox with binary visibility flags.

---

## 9. Dependencies

### Runtime Dependencies

**Backend** (Node.js):

| Package | Version | Purpose |
|---------|---------|---------|
| express | ^4.18.2 | HTTP server |
| cors | ^2.8.5 | Cross-origin requests |
| sharp | ^0.34.4 | Image resizing, metadata extraction |
| multer | ^1.4.5-lts.1 | Multipart file uploads |
| archiver | ^7.0.1 | Zip streaming for mobile batches |
| winston | ^3.18.3 | Structured logging |
| zod | ^3.22.4 | Schema validation |
| dotenv | ^16.3.1 | Environment variables |
| uuid | ^13.0.0 | Unique identifiers |
| axios | ^1.13.2 | HTTP client |
| onnxruntime-node | ^1.23.2 | ONNX model inference (optional) |
| p-limit | ^7.2.0 | Concurrency limiting |

**Frontend / Consumer / Mobile** (Browser):

| Package | Version | Purpose |
|---------|---------|---------|
| react | ^18.2.0 | UI framework |
| react-dom | ^18.2.0 | DOM rendering |
| axios | ^1.6.0 | HTTP client (frontend, consumer) |
| idb | ^8.0.0 | IndexedDB wrapper (mobile, consumer) |
| jszip | ^3.10.1 | Zip extraction (mobile) |
| uuid | ^9.0.0 | Unique identifiers (frontend) |

### Development Dependencies

| Package | Purpose |
|---------|---------|
| typescript ^5.2.2 | Type checking |
| vite ^4.5.0 | Build tool + dev server |
| @vitejs/plugin-react ^4.1.1 | React support for Vite |
| tailwindcss ^3.3.5 | Utility CSS |
| vitest | Test runner |
| tsx ^4.1.1 | TypeScript execution (backend dev) |
| concurrently ^8.2.0 | Run multiple processes |
| vite-plugin-pwa ^0.17.4 | PWA support (mobile + consumer) |
| eslint + plugins | Linting (frontend) |
| @testing-library/react | Component testing (frontend) |

### External Dependencies

| Dependency | Purpose |
|------------|---------|
| Python 3.12 | YOLO inference runtime |
| Ultralytics (YOLO) | Object detection framework |
| Google Colab | GPU training environment |
| pCloud | File sync between PC and mobile |
| Netlify | Mobile annotator PWA hosting |

---

## 10. Security & Privacy Considerations

### Current State (Development / Single-User)

- **No authentication**: All API endpoints are open. Acceptable for localhost-only development.
- **No HTTPS locally**: Mobile annotator accessed over LAN HTTP. Mitigated by `crypto.getRandomValues()` fallback for UUID generation.
- **CORS wide open**: `cors()` with no restrictions. All three frontends run on different ports on localhost.
- **File uploads**: Multer restricts to 20MB, files stored in `/tmp/` and cleaned up after inference.
- **No injection risk**: No SQL database. File paths are constructed from scanned directory entries, not user input. Image IDs come from filesystem traversal.
- **API keys**: Not required for current functionality. `.env` file exists for future use (e.g., if Claude Vision API is re-enabled).

### Future Considerations (If Deployed Publicly)

- Add authentication (API keys or OAuth) to all endpoints
- Restrict CORS to specific origins
- Enable HTTPS (required for PWA service workers on production domains)
- Rate-limit the `/api/detect` endpoint
- Validate and sanitise all file uploads (currently trusts Multer extension check)
- Move uploaded files to a sandboxed directory
- Add request size limits per-endpoint

### Data Privacy

- Training images are scraped from public forums (Reddit, DakkaDakka)
- No personally identifiable information is collected or stored
- Consumer photos are processed transiently and deleted after inference
- Consumer feedback is stored locally on the server filesystem

---

## 11. Performance & Scalability

### Current Performance

| Operation | Typical Time | Notes |
|-----------|-------------|-------|
| Load next image (base64) | 100–500ms | Sharp metadata + fs read + base64 encode |
| Save annotation | <50ms | JSON write to disk |
| YOLO single-image inference | 2–5s | Python cold start dominates; model load ~2s |
| YOLO batch inference | ~1s/image | Model loaded once, amortised |
| Mobile batch export (500 images) | 30–60s | Sharp resize + zip compression |
| Mobile sync (25 annotations) | <1s | JSON processing + Sharp metadata |
| Consumer detection | 3–6s | Upload + inference + response |
| Dashboard stats | <1s | Cached with 60s TTL |

### Bottlenecks

1. **Python cold start**: Each single-image inference spawns a new Python process and loads the YOLO model (~2s overhead). Batch inference avoids this by loading once.
2. **Base64 image encoding**: Sending full images as base64 in JSON responses is bandwidth-heavy. Acceptable for localhost.
3. **Image list scanning**: `getImageList()` walks the filesystem on every call. Works at ~18K images but would not scale to millions.
4. **No caching of image metadata**: Sharp metadata is re-read on every request. Dashboard stats have a 60s cache but individual image requests don't.

### Scalability Path (If Needed)

- Replace Python subprocess with persistent Python inference server (Flask/FastAPI) or ONNX.js
- Serve images via static file serving instead of base64-in-JSON
- Add SQLite or similar for image metadata instead of filesystem scanning
- Move to cloud inference (Lambda, Cloud Run) for consumer detection
- CDN for consumer app static assets

---

## 12. Testing Strategy

### Unit Tests

**Backend (TypeScript — Vitest)**:
- `annotationService.validation.test.ts`: 28 test cases
  - Bbox out-of-bounds (4 tests)
  - Bbox too small (2 tests)
  - Base outside model (6 tests)
  - Duplicate boxes / IoU (9 tests)
  - Complex scenarios (5 tests)
  - Edge cases (2 tests)

**Python (pytest)**:
- `test_validate_yolo_dataset.py`: 25+ test cases
  - Directory structure validation
  - data.yaml validation
  - Label format (5 vs 17 values)
  - Coordinate range validation
  - Keypoint validation
  - Overlap detection

### Running Tests

```bash
# Backend TypeScript tests
cd backend && npm test

# Python dataset validator tests
cd scripts && pytest test_validate_yolo_dataset.py -v

# With coverage
cd backend && npm test -- --coverage
cd scripts && pytest test_validate_yolo_dataset.py -v --cov=validate_yolo_dataset
```

### Manual Testing Checklist

1. Start dev servers: `npm run dev`
2. Open desktop annotator at `localhost:5173`
3. Draw bboxes, test zoom/pan (mouse wheel, click-drag)
4. Test undo/redo (Ctrl+Z, Ctrl+Y)
5. Save & verify annotation written to `training_data_annotations/`
6. Test AI suggestions (Get AI Suggestions button)
7. Test flagging an image
8. Check Quality Dashboard stats
9. Test mobile annotator on phone (LAN access)
10. Test consumer scanner with photo upload

### Test Coverage Goals

| Area | Target | Achieved |
|------|--------|----------|
| Validation logic | 90% | Yes |
| Export logic | 85% | Yes |
| UI components | Manual only | N/A |
| Mobile PWA | Manual only | N/A |
| Consumer app | Manual only | N/A |

---

## 13. Deployment & Infrastructure

### Development Environment

| Component | Details |
|-----------|---------|
| Machine | Linux (Ubuntu), Node v18.19.1, Python 3.12.3 |
| Package manager | npm 9.2.0 with workspaces |
| TypeScript | v5.2.2, strict mode |
| Dev server | Vite (HMR) + tsx watch (backend) |
| Model training | Google Colab (free tier GPU) |

### Production Deployments

| App | Platform | URL |
|-----|----------|-----|
| Mobile annotator | Netlify | https://40k-annotator.netlify.app |
| Desktop annotator | localhost only | http://localhost:5173 |
| Consumer scanner | localhost only | http://localhost:5174 |
| Backend API | localhost only | http://localhost:3001 |

### Build Process

```bash
# Build all workspaces
npm run build

# Individual builds
npm run build:frontend    # tsc + vite build → frontend/dist/
npm run build:backend     # tsc → backend/dist/
npm run build:consumer    # tsc + vite build → consumer/dist/
npm run build:annotator-mobile  # tsc + vite build → annotator-mobile/dist/
```

### File Sync (pCloud)

pCloud is mounted at `~/pCloudDrive/` and `~/Local Pcloud Box Linux/`. Used for:
- Transferring zip batches from PC to phone
- Transferring annotation JSON exports from phone to PC
- Automated sync — changes propagate automatically

### Logging

Winston logger writes to:
- `backend/logs/all.log` — all log levels
- `backend/logs/error.log` — errors only
- Console — colourised output in development

Each request gets a UUID for log correlation.

---

## 14. Trained Models

### Model 1: YOLOv8n (First Iteration)

| Metric | Value |
|--------|-------|
| Architecture | YOLOv8 nano (3M params) |
| Training data | 280 images (206 train, 74 val), 8 factions |
| Training | 30 epochs, 416px, CPU, ~15 min |
| mAP50 | 63.2% |
| mAP50-95 | 49.3% |
| Location | `runs/yolo11_colab_best.pt` |

Best factions: Custodes (97%), Grey Knights (96%). Worst: Death Guard (3.4%).

### Model 2: YOLO11x (Second Iteration)

| Metric | Value |
|--------|-------|
| Architecture | YOLO11 extra-large |
| Training data | 593 images, 15 factions |
| Training | Google Colab GPU |
| mAP50 | 54.7% |
| mAP50-95 | 39.1% |
| Detection recall @ IoU 0.5 | 66.0% |
| Faction top-1 on matched | 63.8% |
| Location | `runs/yolo11x_run2_best.pt` |

Lower mAP50 than model 1 because the class count nearly doubled (8 → 15) while per-class training samples remained limited. Performance expected to improve as more annotations are completed.

### Faction Classes (24 Model Classes)

`blood_angels`, `dark_angels`, `space_wolves`, `black_templars`, `deathwatch`, and `grey_knights` are collapsed into `space_marines` at YOLO export time. Their images remain in separate training data directories and annotations are stored with the original faction label; the merge is applied in `annotationService.ts → remapExportLabel()` and is fully reversible.

**Imperium** (7): space_marines *(covers Blood Angels, Dark Angels, Space Wolves, Black Templars, Deathwatch, Grey Knights)*, adeptus_mechanicus, astra_militarum, adeptus_custodes, adepta_sororitas, imperial_knights, imperial_agents

**Chaos** (7): chaos_space_marines, death_guard, thousand_sons, world_eaters, emperors_children, chaos_daemons, chaos_knights

**Xenos** (10): orks, craftworld_aeldari, drukhari, harlequins, ynnari, tau_empire, tyranids, genestealer_cults, necrons, leagues_of_votann

Model class aliases in `yoloInferenceService.ts → MODEL_CLASS_ALIASES` handle naming differences and chapter marine remapping (e.g., `grey_knights` → `space_marines`, `eldar` → `craftworld_aeldari`, `custodes` → `adeptus_custodes`).

---

## 15. Timeline & Milestones

| Date | Milestone | Status |
|------|-----------|--------|
| Late 2025 | Image scraping complete (~18,600 images from Reddit + DakkaDakka) | Done |
| Jan 2026 | Desktop annotation tool built and functional | Done |
| Feb 8, 2026 | First YOLO model trained (8 factions, 63.2% mAP50) | Done |
| Feb 15, 2026 | Quality dashboard + active learning pipeline | Done |
| Feb 2026 | Mobile annotator PWA (offline-first) | Done |
| Feb 2026 | Consumer scanner PWA (Battle Scanner) | Done |
| Feb 2026 | Second model trained (15 factions, YOLO11x) | Done |
| Mar 2026 | ~1,500 annotations complete (12.6% of target) | In progress |
| TBD | 6,000 annotations (50% target) → retrain model | Planned |
| TBD | 12,000 annotations (100% target) → final model | Planned |
| TBD | Achieve >75% mAP50 across all 30 factions | Planned |
| TBD | Public deployment of consumer scanner | Planned |

---

## 16. Open Questions & Future Work

### Open Questions

1. **Hosting strategy for consumer app**: Keep self-hosted or deploy to Netlify/Vercel with a cloud inference backend?
2. **Model architecture**: Continue with YOLO11x or try YOLOv9/v10 for better small-object detection?
3. **Base bbox value**: Is the hierarchical model+base annotation scheme paying off in model accuracy, or should we simplify to model-only?
4. ~~**Faction granularity**~~ — **Resolved**: Blood Angels, Dark Angels, Space Wolves, Black Templars, Deathwatch, and Grey Knights are collapsed into `space_marines`. The merge is export-only and reversible if per-chapter accuracy becomes a future goal.

### Future Work

- **Persistent Python inference server**: Replace subprocess spawning with a long-running FastAPI/Flask server to eliminate cold-start overhead
- **ONNX.js inference**: Run YOLO inference entirely in Node.js via onnxruntime-node, eliminating Python dependency
- **Image augmentation**: Add augmentation during YOLO export (flips, rotations, colour jitter) to increase effective dataset size
- **Multi-image army accumulation**: Consumer app can scan multiple photos and accumulate detections across a full army
- **Cloud deployment**: Move inference to serverless (AWS Lambda, GCP Cloud Run) for public consumer access
- **Authentication**: API keys for consumer endpoint, rate limiting
- **Annotation review mode**: Second-pass review workflow for quality assurance
- **Model versioning**: Track model performance per version and auto-select best model for inference

---

## Appendix A: Development Quick Reference

```bash
# Start everything (desktop annotator + backend)
npm run dev

# Start mobile annotator (accessible on LAN for phone)
npm run dev:backend & npm run dev:annotator-mobile

# Start consumer app
npm run dev:consumer

# Sync mobile annotations
npm run sync:mobile

# Export to YOLO
curl -X POST http://localhost:3001/api/annotate/export

# Validate dataset
python3 scripts/validate_yolo_dataset.py backend/yolo_dataset

# Run tests
cd backend && npm test
cd scripts && pytest test_validate_yolo_dataset.py -v

# Check logs
tail -f backend/logs/all.log
```

## Appendix B: Ports

| Service | Port |
|---------|------|
| Desktop annotator (Vite) | 5173 |
| Backend API (Express) | 3001 |
| Consumer scanner (Vite) | 5174 |
| Mobile annotator (Vite) | 5175 |

## Appendix C: Key Technical Decisions

| Decision | Chosen | Alternative Considered | Rationale |
|----------|--------|----------------------|-----------|
| Undo/redo | Command pattern | State snapshots | Memory efficient — operations are reversible |
| Coordinate transforms | Centralised functions | Per-handler transforms | Single source of truth prevents bugs |
| Validation | Two-tier (error/warning) | Block on all issues | Balance safety with usability |
| Hierarchical bboxes | YOLO-Pose keypoints | Custom format | Compatible with standard YOLO training |
| Base bbox drawing | Auto-constrain inside model | Post-draw validation | Better UX, prevents most common error |
| Mobile storage | IndexedDB | localStorage / Cache API | Handles blobs, structured queries, ~1GB capacity |
| Mobile touch | Native touch events | Pointer events | iOS Safari breaks setPointerCapture |
| File sync | pCloud | Custom sync server | Already in use, zero setup, works offline-to-online |
| Inference | Python subprocess | ONNX.js / HTTP server | Fastest to implement; Ultralytics API is Python-native |
| Training | Google Colab | Local GPU / cloud ML | Free GPU, Jupyter notebook workflow, easy sharing |
