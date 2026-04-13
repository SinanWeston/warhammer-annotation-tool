# Improvement Plan

Prioritized improvements based on codebase audit and spec review (March 2026).
Ordered by impact and risk. Honest disagreements noted inline.

> **April 2026 update — read [STRATEGY.md](STRATEGY.md) first.** The architectural direction has shifted from "scale end-to-end YOLO to 900 classes" to "class-agnostic detection + retrieval against a reference gallery". Items below remain useful but should be re-evaluated against the strategy before execution. Items that are purely YOLO-scaling (e.g. "Switch to YOLO11s/m with heavy augmentation" in §2.5) are demoted.

---

## Tier 1 — Do Now (high impact, low risk)

### 1.1 Atomic Annotation Saves
**Problem**: `annotationService.ts` writes directly via `fs.writeFile()`. A crash, power loss, or disk error mid-write corrupts the JSON and permanently loses that annotation.
**Fix**: Write to `{path}.tmp`, then `fs.rename()` (atomic on ext4/APFS). ~10 lines of code.
**Risk of not doing**: Loss of irreplaceable human work (1,500+ annotations).
**Effort**: 15 minutes.

### 1.2 YOLO Export Test Coverage
**Problem**: `remapExportLabel()`, coordinate normalization, keypoint generation, and train/val split logic have zero tests. 28 validation tests exist but 0 export tests. If export silently breaks, training on the dataset wastes GPU hours and produces misleading metrics.
**Fix**: Add `annotationService.export.test.ts` covering:
- Label remapping (chapter marines → space_marines, all aliases)
- Coordinate normalization (pixel → 0-1, edge cases: image boundary, tiny boxes)
- Keypoint generation (4 base corners with visibility, missing base → 5 values not 17)
- Train/val split ratios and file output structure
**Effort**: 2 hours.

### 1.3 SchemaVersion on Annotations
**Problem**: `ImageAnnotation` has no version field. Changing the format later means migrating 1,500+ JSON files with no way to distinguish old from new.
**Fix**: Add `schemaVersion: 1` to the interface and to every save. Write a one-time backfill script for existing files.
**Effort**: 20 minutes.

### 1.4 Fix 24 vs 30 Class Inconsistency in Spec
**Problem**: Section 3 says "24 model classes", Section 15 says "30 factions". Both are correct (30 image directories, 24 YOLO classes after chapter marine collapse) but the distinction is never explained in one clear place.
**Fix**: Add a one-paragraph explanation in Section 3 or 14 and reference it consistently elsewhere.
**Effort**: 10 minutes.

### 1.5 Annotation Backup
**Problem**: 1,500 annotations = months of human labour with no backup beyond the filesystem.
**Fix**: Git-track `training_data_annotations/` — commit periodically. Simplest, most reliable option.
**Effort**: 5 minutes to set up, discipline to maintain.

---

## Tier 2 — Do Soon (high impact, moderate effort)

### 2.1 Persistent FastAPI Inference Server
**Problem**: Each YOLO predict call spawns a Python subprocess and loads the model from scratch (~2s cold start). Confirmed in code: `child_process.spawn()` per call.
**Fix**: Create `scripts/inference_server.py`:
- FastAPI app, `POST /predict` endpoint
- Model loaded once at startup, kept in GPU/CPU memory
- Backend calls via HTTP instead of subprocess
- Add `uvicorn` to yolo_env
**Impact**: Inference drops from 2-5s to ~200-500ms. Makes AI-assist during annotation actually fluid.
**Effort**: 3-4 hours.

### 2.2 Wire Consumer Scanner to Real Inference
**Problem**: Consumer v2 UI is fully built on mock data. The mock→real swap point (`detectionService.ts`) is clean. But until wired, the app isn't useful.
**Fix** (after 2.1):
1. Update `detectionService.ts` to `fetch('/api/detect', { method: 'POST', body: formData })`
2. Add `mapBackendResponse()` to convert backend `DetectionResult` to consumer `ScanResult`
3. Test with real photos — will likely reveal data shape mismatches between mock and real
**Effort**: 2-3 hours.

### 2.3 Document Grounding DINO Strategy in Spec
**Problem**: Working pipeline exists (`grounding_dino_propose.py`, `/api/annotate/proposals/:imageId`, frontend auto-loads proposals) but none of it is mentioned in the spec milestones or architecture.
**Fix**: Add subsection to Section 6.4 describing the pipeline, and add a milestone for full-batch proposal generation.
**Effort**: 30 minutes.

### 2.4 Add "Beta: 5-Faction Scanner" Milestone
**Problem**: All milestones point toward "annotate everything, then ship." No milestone for getting real user feedback early.
**Fix**: Add milestone: "Beta release: 5-faction scanner with real inference" targeting Space Marines, Necrons, Orks, Custodes, Tyranids — the factions with the most annotations and highest model confidence.
**Effort**: 10 minutes for the spec update. The underlying work is 2.1 + 2.2.

### 2.5 Switch to YOLO11s/m with Heavy Augmentation
**Problem**: YOLO11x with ~600 training images is massive overfitting. A smaller model with strong augmentation will generalise far better with the current data volume.
**Fix**: In next Colab run, switch to `yolo11s.pt` or `yolo11m.pt`. Enable: `mosaic: 1.0`, `mixup: 0.1`, `hsv_h/s/v` for paint scheme variation, `fliplr: 0.5`.
**Effort**: 1 hour (config change + Colab run).

---

## Tier 3 — Do When Convenient (moderate impact)

### 3.1 In-Memory Image Index on Startup
**Problem**: `getImageList()` has caching (cleared on save) but cache misses re-walk ~25K files. The permanent path map helps for individual lookups, but a full refresh is still slow.
**Fix**: Build a `Map<imageId, ImageMeta>` on startup. Optionally use `chokidar` to update incrementally.
**Effort**: 2-3 hours.

### 3.2 API Integration Tests
**Problem**: No integration tests for API endpoints. Full annotation flow (next → image → save → export) is only manually tested.
**Fix**: `supertest` + temp directory of test images. Test the full flow and mobile sync coordinate scaling.
**Effort**: 4-5 hours.

### 3.3 Active Learning Pipeline Tests
**Problem**: Confidence scoring and prioritized ordering have no tests. If they break, annotation effort goes to the wrong images.
**Fix**: Unit tests for score calculation, priority ordering, and corrupt `confidence_scores.json` handling.
**Effort**: 2 hours.

### 3.4 Consumer: Load Saved Army from History
**Problem**: `HistoryPage` navigates to `/army` when clicking a saved army but doesn't load it into `armyStore`.
**Fix**: Add `loadArmy(id)` to armyStore, call from `handleSelectArmy()`.
**Effort**: 30 minutes.

### 3.5 Consumer: Decode Share Hash on Army Page Load
**Problem**: `armyToShareHash()` and `armyFromShareHash()` are implemented but `ArmyBuilderPage` doesn't check `?share=` on mount.
**Fix**: Add `useEffect` that reads URL params, decodes army, loads it.
**Effort**: 20 minutes.

### 3.6 Mobile Sync Data Safety Indicator
**Problem**: iOS Safari can evict IndexedDB data under storage pressure. Users annotating 500 images offline need to know their work is safe.
**Fix**: Prominent "X annotations pending sync" badge with warning color when overdue. Storage usage estimate on home page.
**Effort**: 1-2 hours.

### 3.7 Coordinate Scaling Unit Tests
**Problem**: Mobile sync scales bboxes from 1200px back to original dimensions. This is the kind of math that produces subtle rounding bugs.
**Fix**: Pure function tests covering rounding, odd aspect ratios, images smaller than 1200px.
**Effort**: 1 hour.

---

## Tier 4 — Consider Later (lower priority or higher effort)

| Item | When to do it |
|------|---------------|
| **Shared types package** across workspaces | If type drift causes real bugs. Types are intentionally different per workspace right now. |
| **BboxAnnotator hook extraction** (958 lines) | If you need to make significant canvas changes. Works correctly as-is. |
| **Event emitter for cache invalidation** | If a second service starts modifying annotations. Manual invalidation works at current scale. |
| **Data-driven validation rules** | If you're frequently adding new validation rules. 28-test if-chain works fine. |
| **Monitoring stack** | Over-engineering for solo localhost. `tail -f logs/error.log` is sufficient. |
| **Drop base bboxes** | Still TBD — adds annotation time but provides real precision for crowded bases. Revisit once annotation throughput improves via DINO proposals. |
| **Re-split chapter marines** | Once 500+ images per chapter. The remap is reversible. |
| **Multi-user auth for annotator** | When crowdsourcing annotation. `annotatedBy` field already exists. |

---

## Decided Against

| Suggestion | Why skip |
|------------|----------|
| Split SPEC.md into SPEC + REFERENCE | One well-structured doc beats two half-synced docs |
| Monitoring stack (Prometheus/Grafana) | Over-engineering for solo localhost. Winston + `tail -f` is sufficient |
| Validation as data-driven rule array | Working code with 28 tests. Refactoring for elegance, not need |
| Image licensing in spec | Valid legal concern, wrong document. One-liner in README |
| Consumer v2 section "too detailed" | Disagree — detailed mock contracts prevent confusion when wiring real inference |
| Command pattern simplification | 4 command classes is fine. Single-command abstraction would be more abstract, not cleaner |

---

## Recommended Execution Order

```
Session 1 (2-3 hours):
  1.1 Atomic saves
  1.3 SchemaVersion
  1.4 Spec class fix
  1.5 Git-track annotations
  2.3 Document DINO in spec
  2.4 Beta milestone in spec

Session 2 (3-4 hours):
  1.2 Export tests

Session 3 (half day):
  2.1 FastAPI inference server
  2.2 Wire consumer to real API
  3.4 + 3.5 Consumer small fixes

Session 4 (when ready to retrain):
  2.5 Switch to YOLO11s/m + augmentation
```

After sessions 1-3: annotations are safer, export is tested, AI-assist is fast, and the consumer app runs on real inference.

---

## Scraper Suite — Setup & Run Checklist

### One-time setup
- [ ] Create Reddit "script" app at https://www.reddit.com/prefs/apps → get client ID + secret
- [x] ~~Flickr API key~~ — requires Pro, skipped
- [ ] Add Reddit credentials to `.env` if/when Reddit API access is sorted:
  ```
  REDDIT_CLIENT_ID=...
  REDDIT_CLIENT_SECRET=...
  REDDIT_USER_AGENT=BattleScanner/1.0 by your_username
  ```

### Dry-run verification (do before any real collection)
- [ ] `python scripts/reddit_collector.py --subreddit Necrons --limit 10 --dry-run`
- [x] ~~Flickr dry-run~~ — skipped (requires Pro)
- [ ] `python scripts/youtube_collector.py --all-channels --limit 3 --frame-limit 5 --dry-run`

### Collection runs (run in order)
- [ ] Reddit — faction subreddits: `python scripts/reddit_collector.py --all --limit 200`
- [x] ~~Flickr~~ — requires Pro account, skip. Use `collect_unit_images.py` (Bing/Google) instead: `python scripts/collect_unit_images.py --num 30`
- [ ] YouTube — battle reports: `python scripts/youtube_collector.py --all-channels --limit 20`

### Post-collection quality passes (run after each collection batch)
- [ ] CLIP score-only pass (no files moved yet): `python scripts/clip_scorer.py --score-only`
- [ ] Review score distribution, tune threshold if needed: `python scripts/clip_scorer.py --dry-run`
- [ ] Apply CLIP rejection: `python scripts/clip_scorer.py`
- [ ] Dedup index-only pass: `python scripts/deduplicate.py --index-only`
- [ ] Dedup dry-run (check what would be removed): `python scripts/deduplicate.py --dry-run`
- [ ] Apply dedup: `python scripts/deduplicate.py`

### Verify results
- [ ] Check output counts: `ls training_data_v2/necrons/reddit/ | wc -l`
- [ ] Check CSV: `tail -20 training_data_v2/metadata/scrape_log.csv`
- [ ] Check rejected: `ls training_data_v2/rejected/`
- [ ] Run scrape progress dashboard: `python scripts/scrape_progress.py`

---

## Resolved

- ✅ Chapter marine collapse (blood_angels etc. → space_marines)
- ✅ Quality dashboard + active learning pipeline
- ✅ Mobile offline annotator PWA
- ✅ Consumer scanner v2.0 (desktop-first, tabbed, mock data, full army builder)
- ✅ YOLO export pipeline with validation
- ✅ Grounding DINO batch proposal pipeline
- ✅ Frontend bbox resize handles

### April 2026 cleanup sweep

- ✅ Doc consolidation — root has canonical {README, CLAUDE, OVERVIEW, SPEC, TODO, DEPLOY}; `docs/` holds reference guides; `docs/archive/` holds historical plans; `docs/decisions/` holds research artifacts
- ✅ `backend/src/config/index.ts` — centralized env-driven config (3.4 done)
- ✅ Unified YOLO model path for both inference and active-learning (both now use `yolo11x_run2_best.pt`); paths, confidence thresholds, Python binary all env-configurable
- ✅ Root `requirements.txt` supersedes scripts-only one; covers ML + scraper + quality deps
- ✅ `.env.example` rewritten — trimmed the LLM cascade config that no longer maps to the codebase
- ✅ Consumer v2: `armyStore.loadArmy`, history army load (3.4 done), `?share=` hash decode (3.5 done)
- ✅ Removed orphan `consumer/src/utils/points.ts`
- ✅ Python scripts: consolidated 3 training scripts into `scripts/train_yolo.py` with CLI flags; removed 2 dedup/scraper duplicates; `.gitignore` updated for build artifacts
- ✅ Test infra: deleted dead Jest tests referencing removed services; migrated `annotationService.validation.test.ts` to Vitest (19 pass, 5 skipped pending `BASE_OUTSIDE_MODEL` feature); deleted broken frontend `ImageUpload.test.tsx` + `trainingData.ts` mock
- ✅ Extracted `frontend/src/utils/coordinates.ts` — `screenToImage`, `scaleBbox`, `fitScale`, `clampBbox` as pure helpers; `BboxAnnotator` uses them

### Still outstanding from the sweep

- [ ] **AnnotationInterface split** — 1,515 lines, 16 `useState` calls. Pure-function extraction (coordinates) is done; the component split is a real refactor that needs manual UI testing. Defer until next canvas change.
- [ ] **`BASE_OUTSIDE_MODEL` validation** — spec'd in SPEC.md §6.1 ("errors block save: base outside model"), 5 tests skipped in `annotationService.validation.test.ts`. Implementation missing from `annotationService.validateAnnotation()`.
- [ ] **Frontend vitest infrastructure** — `jsdom`/`vitest 0.34` dep conflict with `html-encoding-sniffer` (ESM/CJS). Either upgrade vitest to ≥1.x or pin jsdom. Blocking frontend component tests.
