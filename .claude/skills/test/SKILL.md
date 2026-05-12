---
name: test
description: Run all TypeScript and Python test suites for photoanalyzer. Use when testing, debugging failures, or checking coverage.
---

# Run photoanalyzer Tests

## Frontend Smoke Tests (Vitest + RTL)

**Location**: `frontend/src/test/`

```bash
cd frontend && npm test           # one-shot run
cd frontend && npm run test:watch # watch mode
```

**Coverage** (5 tests, intentionally minimal — guardrails against regressing
load-bearing flows during the Big Refactor; per-component tests land
alongside component extractions):
- `AnnotationInterface.test.tsx` — mount → /progress + /taxonomy, "Start
  Annotating" → /next, status-pill triggers /next, save POST wire shape.
- `BboxAnnotator.test.tsx` — faction-edit gotcha (no bbox selected →
  no mutation).

## Backend Unit Tests (Vitest)

**Location**: `backend/src/services/__tests__/annotationService.validation.test.ts`

```bash
cd backend && npm test
```

**Status**: Backend's `vitest@^0.34` is stale and incompatible with current
jsdom (html-encoding-sniffer ESM/CJS error). Tests don't currently run end
to end; see TODO.md "Frontend vitest infrastructure" note for the bump
path. The frontend bumped to vitest@4.x in May 2026.

**Coverage** (when the version is fixed): 28 test cases covering bbox
bounds, size, base-outside-model, duplicates, complex scenarios, IoU.

## Unit Tests (Python/pytest)

**Location**: `scripts/test_validate_yolo_dataset.py`

```bash
# Install pytest
pip install pytest pytest-cov

# Run all Python tests
cd scripts && pytest test_validate_yolo_dataset.py -v

# Run with coverage
pytest test_validate_yolo_dataset.py -v --cov=validate_yolo_dataset --cov-report=html
```

**Coverage**: 25+ test cases covering:
- Directory structure validation
- data.yaml validation
- Label format validation (5 vs 17 values)
- Coordinate range validation
- Keypoint validation
- Overlap detection

## Manual Testing

1. Start servers: `npm run dev`
2. Open `http://localhost:5173`
3. Click "Start Annotating"
4. Draw a few bboxes
5. Test zoom/pan (mouse wheel, click-and-drag)
6. Test undo/redo (Ctrl+Z, Ctrl+Y)
7. Click "Save & Next"
8. Verify validation (try invalid bbox out of bounds)
9. Verify next image loads
10. Check annotation saved: `backend/training_data_annotations/`

## Test Export

```bash
# Validate before export (recommended)
curl -X POST http://localhost:3001/api/annotate/validate-export

# Export to YOLO
curl -X POST http://localhost:3001/api/annotate/export \
  -H "Content-Type: application/json" \
  -d '{}'

# Validate exported dataset
python3 scripts/validate_yolo_dataset.py backend/yolo_dataset
```

## Coverage Goals
- Validation logic: ~90% (achieved)
- Export logic: ~85% (achieved)
- UI components: Not tested (manual testing only)

After running, report: total tests, pass/fail, coverage gaps in recently changed files.
