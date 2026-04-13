# photoanalyzer — Warhammer 40K Miniature Annotation & Scanner

## Overview
Monorepo annotation tool (desktop) + consumer scanner (PWA). 4 workspaces: desktop frontend (React/TS), backend (Express/TS), consumer PWA, mobile annotator PWA. ~18K training images, YOLO model integration (63.2% mAP50).

## Dev Commands

```bash
npm run dev                    # Desktop frontend + backend concurrently
npm run dev:frontend           # Vite dev server on port 5173
npm run dev:backend            # Express server on port 3001
npm run dev:consumer           # Consumer PWA on port 5174
npm run dev:annotator-mobile   # Mobile annotator PWA on port 5175 (--host for LAN)

# Mobile annotator typical workflow:
npm run dev:backend &
npm run dev:annotator-mobile
# Access from iPhone at http://<your-lan-ip>:5175

npm run build                  # Build everything
npm run build:frontend         # → frontend/dist/
npm run build:backend          # → backend/dist/
```

## Key Architecture
- **Command pattern** for undo/redo → `frontend/src/commands/`
- **Centralized coordinate transforms** → `frontend/src/utils/coordinates.ts`
- **Two-tier validation**: errors block save, warnings inform
- **YOLO-Pose export** for keypoint annotations (5 or 17 values per line)
- **DINO pipeline** for auto-annotation proposals via backend
- **Active learning** pipeline prioritizes low-confidence images
- **Mobile annotator**: IndexedDB offline storage, native touch events, WiFi sync

## iOS Safari / Mobile PWA — READ BEFORE ANY MOBILE CHANGES
- `crypto.randomUUID()` HTTPS-only — use `generateId()` fallback
- Buttons over canvas don't get touches — place outside canvas container
- Use native touch events, not pointer events (`setPointerCapture` breaks)
- IndexedDB ~1GB limit on iOS — batch imports to 500-1000
- `overscroll-behavior: none` to prevent pull-to-refresh on canvas
- `env(safe-area-inset-bottom)` on bottom toolbars
- Minimum 44px touch targets (Apple HIG)

Full details: `/debug` skill

## Data Paths
- **Images**: `backend/training_data/{faction}/{source}/`
- **Annotations**: `backend/training_data_annotations/` (JSON)
- **YOLO export**: `backend/yolo_dataset/`
- **Confidence scores**: `backend/confidence_scores.json`
- **Model**: `runs/yolo11_colab_best.pt`
- **Logs**: `backend/logs/all.log`, `backend/logs/error.log`

## SPEC.md
Update `SPEC.md` (root) when making architecture changes. Show before/after comparison format. Structural changes only — not bug fixes or typos.

## Skills
`/test` — full test suite (TS + Python). `/export` — YOLO dataset export/validation. `/debug` — troubleshooting, logs, iOS gotchas.

## Constraints
- NEVER commit files in `images/` or `runs/` to git (training data ~50GB)
- NEVER modify `runs/*.pt` — trained model files are read-only
- NEVER `git add -A` or `git add .` — always stage specific files
