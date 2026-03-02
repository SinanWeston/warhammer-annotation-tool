# Project Status
> Auto-generated on **2026-03-02 21:47:02** by `status-hook.py`  
> _Edit this file manually to add persistent notes above the auto-generated section._

---

## Source Files

### Frontend (Annotator) (`frontend/src/`) — 15 files
- **__mocks__/**
  - `trainingData.ts` _1 KB, 12-08 12:51_
- **components/**
  - **__tests__/**
    - `ImageUpload.test.tsx` _929 B, 12-02 20:43_
  - `AnnotationInterface.tsx` _51 KB, 03-02 18:56_
  - `BboxAnnotator.tsx` _23 KB, 03-02 18:56_
  - `ErrorBoundary.tsx` _1 KB, 10-28 18:06_
  - `QualityDashboard.tsx` _26 KB, 03-01 20:47_
  - `QualityIssuesModal.tsx` _10 KB, 12-27 22:44_
- **styles/**
  - `warhammer.css` _5 KB, 12-02 20:40_
- **test/**
  - `setup.ts` _213 B, 10-28 18:06_
- **theme/**
  - `factionThemes.ts` _4 KB, 12-02 20:40_
- **types/**
  - `dashboard.ts` _852 B, 02-15 11:06_
- `App.tsx` _3 KB, 03-01 20:38_
- `index.css` _460 B, 12-16 13:01_
- `main.tsx` _235 B, 10-28 18:05_
- `types.ts` _1023 B, 03-02 18:55_

### Consumer PWA (Battle Scanner) (`consumer/src/`) — 25 files
- **components/**
  - `ArmySummary.tsx` _2 KB, 03-01 15:19_
  - `CameraCapture.tsx` _5 KB, 03-01 14:23_
  - `FactionIcon.tsx` _721 B, 03-01 14:22_
  - `FeedbackModal.tsx` _3 KB, 03-01 15:20_
  - `Header.tsx` _4 KB, 03-01 15:18_
  - `HealthBanner.tsx` _2 KB, 03-01 15:17_
  - `OnboardingModal.tsx` _3 KB, 03-01 15:18_
  - `PhotoUpload.tsx` _3 KB, 03-01 14:24_
  - `ResultsCard.tsx` _4 KB, 03-01 15:20_
  - `ScanAnimation.tsx` _2 KB, 02-15 18:27_
- **lib/**
  - `db.ts` _3 KB, 03-01 15:16_
  - `id.ts` _757 B, 03-01 15:16_
- **pages/**
  - `ArmyPage.tsx` _5 KB, 03-01 15:21_
  - `HistoryPage.tsx` _5 KB, 03-01 15:19_
  - `ResultsPage.tsx` _9 KB, 03-01 15:21_
  - `ScanPage.tsx` _3 KB, 03-01 14:22_
- **types/**
  - `detection.ts` _574 B, 03-01 15:21_
- **utils/**
  - `factionDisplay.ts` _492 B, 03-01 16:33_
  - `factions.ts` _5 KB, 03-01 16:33_
  - `points.ts` _425 B, 03-01 15:19_
  - `resizeImage.ts` _1011 B, 03-01 14:22_
  - `time.ts` _520 B, 03-01 15:19_
- `App.tsx` _6 KB, 03-01 15:17_
- `index.css` _743 B, 02-15 18:26_
- `main.tsx` _231 B, 02-15 18:26_

### Mobile Annotator (`annotator-mobile/src/`) — 14 files
- **components/**
  - `BottomToolbar.tsx` _3 KB, 02-22 16:31_
  - `PredictionCards.tsx` _3 KB, 02-22 11:19_
  - `SyncStatus.tsx` _5 KB, 02-22 16:52_
  - `TouchCanvas.tsx` _15 KB, 02-22 16:43_
- **lib/**
  - `db.ts` _4 KB, 02-22 16:18_
  - `id.ts` _757 B, 02-22 10:30_
  - `sync.ts` _3 KB, 02-22 16:42_
  - `zip.ts` _2 KB, 02-22 16:18_
- **pages/**
  - `AnnotatePage.tsx` _10 KB, 03-02 21:05_
  - `HomePage.tsx` _8 KB, 02-22 11:19_
- `App.tsx` _517 B, 02-21 10:30_
- `index.css` _865 B, 02-22 11:20_
- `main.tsx` _231 B, 02-21 10:30_
- `types.ts` _942 B, 02-22 11:18_

### Backend (Express API) (`backend/src/`) — 15 files
- **config/**
- **middleware/**
  - `errorHandler.ts` _3 KB, 11-02 18:22_
  - `requestId.ts` _615 B, 11-02 17:52_
- **services/**
  - **__tests__/**
    - `aiAnalyzer.test.ts` _7 KB, 11-02 17:23_
    - `annotationService.validation.test.ts` _14 KB, 12-27 23:03_
  - `activeLearningService.ts` _8 KB, 02-15 11:08_
  - `annotationService.ts` _24 KB, 03-02 17:15_
  - `batchYoloInference.py` _2 KB, 02-15 11:08_
  - `dashboardStatsService.ts` _7 KB, 02-15 11:07_
  - `yoloInferenceService.ts` _6 KB, 03-02 16:53_
- **utils/**
  - `logger.ts` _2 KB, 11-02 18:20_
- `index.ts` _33 KB, 03-01 20:46_
- `test-bbox-pipeline.ts` _5 KB, 11-02 22:53_
- `test-full-pipeline.ts` _5 KB, 11-02 22:59_
- `test-sprint1.ts` _5 KB, 12-07 16:53_
- `types.ts` _3 KB, 12-15 12:08_

### Scripts (`scripts/`) — 15 files
- `actions-hook.py` _2 KB, 03-02 19:41_
- `audit_faction_labels.py` _8 KB, 03-01 16:44_
- `audit_report.json` _43 KB, 02-15 17:05_
- `augment_dataset.py` _7 KB, 03-01 20:46_
- `deduplicate_images.py` _6 KB, 03-01 20:45_
- `export_yolo_dataset.py` _6 KB, 03-02 12:56_
- `import-mobile-annotations.js` _3 KB, 02-22 16:52_
- `scrape_dakkadakka_images.py` _16 KB, 03-02 12:37_
- `scrape_faction_images.py` _16 KB, 03-02 12:32_
- `setup_training_env.py` _14 KB, 12-27 23:00_
- `status-hook.py` _5 KB, 03-02 19:41_
- `test_validate_yolo_dataset.py` _14 KB, 12-27 23:04_
- `test_yolo_model.py` _17 KB, 12-27 23:01_
- `timeline-hook.py` _1 KB, 02-22 18:16_
- `validate_yolo_dataset.py` _15 KB, 12-27 22:36_

---

## Data Directories

- **Annotations** (`backend/training_data_annotations/`) — 1513 `.json` files, 1 MB total
- **YOLO Dataset** (`backend/yolo_dataset/`) — 1188 files, 183 MB total
- **Training Images** (`backend/training_data/`) — 25383 files, 14 GB total

---

## Root-Level Files

