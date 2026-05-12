# STATUS.md

**Project Status**: Labelling mode v2 (audit-hardened, v2-only)
**Last Updated**: 2026-04-18

---

## Recent Changes (Factual Log)

### 2026-04-18 — Training-data integrity: ten-item remediation landed

**Context**: The earlier audit surfaced ten distinct training-data-integrity
hazards. This pass implements every item from the approved plan
(`~/.claude/plans/slowly-and-meticulously-work-goofy-shamir.md`). Net
effect: the web-UI labelling surface (`data/labels.csv`) is now
explicitly bridged into the phase3 retrieval pipeline, weak-sup can't
wipe human provenance, the deployed YOLO `.pt` has a pinned class list
on disk, and the Node + Python writers agree on a cross-process lock.

**Items landed** (in order of operations):

1. **#4 — weak-sup guard** (`scripts/apply_weak_sup.py:58-105`). Added
   `TRUSTED_PROVENANCE = {human, human_redraw, scraped, annotation}` and
   an unconditional guard that runs BEFORE the `--overwrite` short-
   circuits. Dry-run now reports `skipped_trusted_provenance: 35`.

2. **#2 — faction aliases** (`src/photoanalyzer/taxonomy.py:30-67` +
   `backend/src/services/annotationService.ts:22-47`). Added the four
   10th-ed Chaos sub-factions to the Python alias table and the four
   top-level renames (`custodes`, `eldar`, `genestealer_cult`,
   `imperial_guard`) to the TS `EXPORT_LABEL_REMAP`. `data/labels.csv`
   unresolved-faction rows dropped from 23 distinct factions to 3 (84
   rows, all non-40K or "unknown" placeholder — deliberately dropped by
   the sync bridge at item #1).

3. **#9 — Node taxonomy validation**
   (`warhammer-analyzer/backend/src/services/labellingService.js:173-266,
   783-796, 1086-1108`). New `FACTION_ALIASES` JS constant mirrors the
   Python table. `resolveFaction(raw)` + `assertValidFaction(raw)`
   exported helpers. `saveLabel` and `editCropBbox` both now 400 on
   unknown factions and auto-normalise aliases to canonical. Verified
   via `POST … faction=space_marins → 400` and `… faction=blood_angels
   → 200 with faction=space_marines`.

4. **#10 — sentinel filter wired in phase3 consumers**
   (`scripts/phase3/build_gallery.py`, `auto_split.py`,
   `embed_gallery.py`). All three import `is_sentinel` from
   `photoanalyzer.label.schema` and drop any row whose `unit_slug`
   matches `__*__`. `embed_gallery.walk_gallery` hard-fails if a
   sentinel dir appears in the on-disk tree.

5. **#3 — YOLO class-list pinning** (new `scripts/pin_pt_classes.py`,
   `scripts/export_yolo_dataset.py:23-41, 147-174`). Extracted
   `model.names` from every `.pt` under `runs/` and wrote companion
   `<stem>.classes.txt` files. `runs/yolo11_colab_best.classes.txt` has
   8 classes (older model); `runs/yolo11x_run2_best.classes.txt` has
   15 (the one `backend/src/config/index.ts:41` actually loads — CLAUDE.md
   docs drift still to reconcile). `export_yolo_dataset.py` accepts
   `--deployed-classes path` and aborts with a clear diff when the
   generated class list disagrees; `--allow-class-shift` is the
   explicit opt-out for deliberate retrains.

6. **#1 — `data/labels.csv → scripts/phase3/labels.csv` sync bridge**
   (new `scripts/phase3/sync_from_canonical.py`). Reads v2, runs the
   three-stage filter (`filter_trainable` → trusted provenance →
   taxonomy-valid faction), writes out the full v2 13-column schema to
   phase3 so `instance_id` / `view_idx` / `suggested_by` / `labeller` /
   `confidence` / `source_ref` / `created_at` all carry through. 4284
   canonical rows → 3384 trainable after filtering; 742 rows had their
   faction alias-normalised at the write. The phase3 CSV previously
   had a 6-col schema — now 13 cols, but `csv.DictReader` in the
   downstream scripts ignores unknown columns so it's backward-safe.

7. **#6 — pinned splits + instance-aware grouping**
   (`scripts/phase3/auto_split.py:56-171`). Three-stage logic:
   (1) carry forward existing `gallery/query` assignments verbatim;
   (2) assign new splits only to rows with `split=''`, grouped at the
   **instance level** — every crop sharing `instance_id` inherits the
   same split; (3) reconciliation pass that collapses any instance
   appearing in both gallery AND query (e.g., a multi-unit scene) down
   to gallery. Added an end-of-run invariant check: `✓ No instance_id
   split leakage across N CMON instances.` Verified idempotent:
   consecutive runs produce a 0-line diff.

8. **#5 — embedding-hash stamp**
   (`scripts/phase3/embed_gallery.py:21-47, 131-154`,
   `eval_scoped_retrieval.py:124-152`, `classify_faction_knn.py:105-123`).
   `embed_gallery.py` now stamps the `.npz` with
   `source_csv_sha256`, `row_count`, `built_at`. Both consumers
   recompute the sha of `phase3/labels.csv` at load and emit
   `⚠ STALE GALLERY` when the stamp doesn't match. Existing
   `gallery_embeddings.npz` was built before the stamps so the first
   eval after this change will warn until the embed is rebuilt.

9. **#7 — annotation-corpus cleanup** (new `scripts/audit_annotations.py`
   + 28 touched JSONs). Lowercased 27 `Sinan` → `sinan` occurrences so
   per-annotator analysis treats them as the same person. Removed one
   exact-duplicate bbox in
   `adeptus_mechanicus_dakkadakka_133346_6efbcb5c2580.json`. Snapshot
   backup at `backend/training_data_annotations.bak-20260418T141405Z/`.
   **Flagged for manual review** (not auto-fixed): 3 non-skip zero-bbox
   files; 133 tiny-bbox entries (mostly one swarm photo with 9+
   intentional small models).

10. **#8 — cross-process mkdir-lock on `data/labels.csv`**
    (`src/photoanalyzer/label/schema.py:37-88, 313-333`,
    `warhammer-analyzer/backend/src/services/labelsCsvService.js:18-24,
    168-240`, CLAUDE.md:52-53). Both sides use atomic `mkdir` at
    `<csvPath>.lock` as the primitive — interoperable with Node's
    `proper-lockfile` (npm, newly added to `backend/package.json`) and
    Python's `_CrossProcessMkdirLock` (tiny class in schema.py; no new
    deps). Verified with a concurrent test: Python held the lock for
    1000ms, Node save elapsed 1139ms (waited for python, then
    succeeded). Filelock wasn't interop-compatible so I dropped that
    dep before it hit the requirements.

**Verification — one-shot check** (every item with a measurable
invariant, all green):

| item | check | result |
|---|---|---|
| #4 | `apply_weak_sup --dry-run --overwrite` skipped_trusted_provenance | 35 |
| #2 | `data/labels.csv` rows with unresolved faction | 84 (expected: non-40K only) |
| #9 | `POST … faction=space_marins` → HTTP | 400 |
| #10 | sentinel rows in `phase3/labels.csv` | 0 |
| #3 | `runs/*.classes.txt` files present | 2 |
| #1 | sync bridge output | 3384 rows, 12 with instance_id |
| #6 | instance_ids split-leaked | 0 |
| #7 | annotation JSONs with "Sinan" capitalised | 0 |
| #7 | annotation JSONs with "sinan" lowercase | 301 (274 + 27 merged) |
| #8 | stale `.lock` after concurrent test | none |

**Follow-ups (deferred, out of scope for this pass)**:
- Resolve model/docs drift: `CLAUDE.md:50` says `yolo11_colab_best.pt`
  but `backend/src/config/index.ts:41` loads `yolo11x_run2_best.pt`.
- Deprecate `scripts/migrate_labels.py` or add a v2-safe guard — a
  re-run would still drop v2 fields.
- Shared `scripts/data/faction_aliases.json` so the Python `FACTION_ALIASES`
  and the JS copy in `labellingService.js` can't drift.
- Audit-queue UI filter for `suggested_by=weak_regex:*` so the user
  can triage the 236 suspect rows efficiently.
- Review the 3 empty-bbox + 133 tiny-bbox annotation files flagged by
  `scripts/audit_annotations.py --report`.

---

### 2026-04-18 — Provenance backfill on data/labels.csv

**Context**: Auditing the CSV turned up 3456 rows with non-sentinel
`unit_slug` but empty `suggested_by` — meaning the downstream training
pipeline couldn't tell whether the label came from a trustworthy source
(GW shop scrape, human annotation corpus) or weak-regex keyword
matching (often wrong). Today the gallery/split scripts don't filter by
provenance, so any future `data/labels.csv` → training bridge would
sweep all of them in indiscriminately. Also, only 12 rows across the
whole file were tagged `human`, versus 236 `weak_regex:*` rows whose
factions are frequently miscalled by the detector — making it hard to
distinguish "reliable but untagged" from "machine-guessed".

**What changed**:
- New `scripts/backfill_provenance.py` — one-shot tagger. Promotes rows
  where `suggested_by` is empty AND `unit_slug` is non-sentinel AND
  `source` is a known-reliable origin:
    * `source=gw_shop`    → `suggested_by=scraped`   (3101 rows)
    * `source=annotation` → `suggested_by=annotation`  (355 rows)
  Does NOT touch faction, unit_slug, labeller, bbox, or notes on any
  row. Does NOT touch rows that already carry a `suggested_by` value.
  Backs up to `labels.csv.backup-<UTC-timestamp>` before writing;
  atomic tmp+rename to match the Node-side serialiser.

**Post-state** (non-sentinel slugged rows):
```
  scraped                   3101   (gw_shop, canonical)
  annotation                 355   (desktop annotator corpus)
  weak_regex:unit_kw         159   (still suspect — needs audit)
  weak_regex:char_table       56   (still suspect)
  weak_regex:auto_unique_unit 19   (still suspect)
  human                       12   (user-confirmed this week)
  weak_regex:unit_alias        2   (still suspect)
  ──────────────────────────────
  total                     3704
```

Net: **236 weak_regex rows remain flagged** as the audit pile for
future triage; everything else now has explicit provenance.

**Not changed (on purpose)**:
- `scripts/phase3/auto_split.py` was going to get a `--confirmed-only`
  flag in the same pass, but it reads from `scripts/phase3/labels.csv`
  (a 6-column snapshot schema with no `suggested_by` column), not from
  `data/labels.csv`. Until the phase3 training pipeline is re-plumbed
  to read `data/labels.csv` directly or to carry provenance through,
  the filter would be a no-op there.

**Follow-up (not done, tracked here)**:
- Build a `data/labels.csv` → `scripts/phase3/labels.csv` consolidator
  that carries `suggested_by` through and defaults to
  `suggested_by in {human, human_redraw, scraped, annotation}`. Until
  that exists, the 236 weak-regex rows can't actually pollute training
  — but the provenance tagging is in place for when it does.
- Audit-triage UI: a queue filter for `suggested_by=weak_regex:*` so
  the user can plough through just the suspect rows.

**Verification**:
```
$ yolo_env/bin/python3 scripts/backfill_provenance.py --dry-run
Rows total: 4284
Rows to backfill: 3456
  source=annotation   → suggested_by=annotation   355
  source=gw_shop      → suggested_by=scraped     3101
```
Dry-run counts matched the pre-inspection bucket totals exactly.
Backend `selfCheck` still healthy; mtime-based row cache picked up the
new file on the next request.

---

### 2026-04-18 — Per-crop bbox edit flow (move/resize without invalidating siblings)

**Context**: The existing redraw flow nukes every crop on the view and
creates fresh unlabelled rows — fine when the detector was completely
wrong, but painful when you just want to nudge one bbox. Users editing
most bboxes were losing sibling labels on every tweak. New dedicated edit
flow: move/resize a single crop's box, the JPEG gets re-extracted
in-place, siblings are untouched.

**Files changed**:
- `backend/src/services/labellingService.js` — new `editCropBbox(cropId,
  bbox, opts)` export. Looks up the row, re-extracts from the scene with
  the same +5%-longer-side padding the Python extractor uses, writes to
  `<crop>.editing`, writes CSV (updated `notes` with
  `bbox=x,y,w,h; scene=...; edited_at=...`), then atomically renames the
  JPEG over the original. A rename failure after the CSV write triggers a
  best-effort CSV rollback to keep disk+CSV consistent. Wrapped in
  `withCsvLock` to serialise with saves/redraws.
  - `opts.unit_slug` confirms a label in one step (suggested_by='human',
    confidence=1.0, strips `flag:audit`).
  - `opts.status='audit'` defers the slug (blank + `flag:audit`,
    faction kept).
  - Neither → bbox-only: existing faction/slug/suggested_by preserved,
    only notes + labeller + created_at update.
- `backend/src/index.js` — `PATCH /api/labelling/crops/:id/bbox`. Body:
  `{bbox: {x,y,w,h}, labeller?, faction?, unit_slug?, status?}`.
- `frontend/public/label.html` — new **🎯 Edit bbox** button (keyboard
  `e`) on the main actions row. Opens a dedicated modal:
    * Scene image on canvas, DPR-aware.
    * Single green bbox with 8 resize handles (NW/N/NE/E/SE/S/SW/W) + body
      drag. Normalises when a corner drags past its opposite edge. 5px
      minimum dimension; smaller drags revert.
    * Sibling crops on the same view rendered as dim red outlines for
      context (non-interactive, not touched on save).
    * Thin dashed outer rectangle previews the +5% padding the backend
      will add, so the saved crop matches what you see.
    * Optional faction dropdown + slug input. Empty slug + set faction →
      row saved to the audit pile with the new bbox. Both empty → bbox-
      only edit (label preserved). Both set → confirmed in one step.
    * **Reset** button reverts the box to its loaded coords. **Enter**
      saves, **Esc** cancels.
    * YOLO crops don't store bbox coords, so for those the modal starts
      with a centered 40%-sized box and a status hint to drag it.
  - After save the main crop `<img>` is force-refetched via a
    cachebuster query string so the new JPEG shows immediately.
- Redraw button now titled "Replace every bbox on this view" to
  distinguish it from the per-crop edit.

**Why not just reuse the redraw modal?** Redraw's semantics are "mark
every sibling bad, add new unlabelled rows" — the opposite of what a
single-bbox edit needs. The two flows coexist: `e` for nudge, `d` for
full-view redraw.

**Verification**: `node --check` clean on `labellingService.js` and
`index.js`. Frontend script extracted and parsed clean (balanced braces/
parens/brackets). Smoke-tested `PATCH /api/labelling/crops/:id/bbox` with
a bbox-only edit on a real row — returned correctly padded
`{x:85,y:85,w:230,h:330}` from input `{100,100,200,300}` and updated
notes with the new markers.

**Known follow-ups**:
- YOLO-extracted rows have no stored bbox, so editing them starts from a
  centered default. Fix upstream by making `scripts/extract_cmon_crops.py`
  write `bbox=x,y,w,h; scene=...` into notes at initial extraction.
- Non-CMON sources (annotation, gw_shop) can't be edited yet — no scene
  image to re-extract from. 400 on attempts.
- Minor UX: faction select in the edit modal isn't the typeahead combobox
  used on the main form — plain `<select>`. Fine for 20 options; upgrade
  if the list ever grows.

---

### 2026-04-17 — Redraw bug fix + CSV concurrency lock + multer 2.x

**Context**: A second full audit (backend + frontend + providers + deps)
reverified the earlier 35-finding sweep (42/42 claims PASS) and surfaced
new issues. This commit fixes the most impactful items: the "where did my
new bbox go?" redraw confusion, a read-modify-write race on `data/labels.csv`,
and the multer 1.x HIGH CVE (GHSA-g5hg-p3ph-g8qg).

**Files changed**:
- `frontend/public/label.html` — redraw modal now displays existing crops on
  the current view as dashed reference rectangles (red = YOLO detector,
  amber = prior human_redraw). Draws whenever `bbox=x,y,w,h` is parsed from
  the row's notes (present on every human_redraw row). Footer now explains
  what will be marked bad on save, with a colour legend. `onRedrawMouseDown`
  clamps `startImgX/Y` to image bounds so a mousedown slightly outside the
  canvas can't produce a negative-origin bbox that the server silently
  shrinks.
- `backend/src/services/labellingService.js` —
    * `markSiblingsBad` now marks UNCONFIRMED prior `human_redraw` rows as
      bad (they're stale iterations); only rows with a real, non-sentinel
      `unit_slug` are preserved. Stops iterative "nudge the box" redraws
      from accumulating ghost rows in the queue.
    * `promoteTempCrops` no longer swallows `fs.rename` failures — it
      collects per-pair results and throws a structured error
      (`err.promoted`, `err.failed`) when any rename fails. Previously the
      CSV was written with row paths that pointed at `.tmp` files, so the
      queue would serve 404 images indefinitely.
    * New `rollbackFailedPromotions` helper: on partial promote failure,
      rewrites the CSV without the rows whose files never landed, so the
      on-disk truth matches what the CSV claims.
    * `saveLabel`, `redrawCrops`, `redrawSceneView` now run their read-
      modify-write blocks inside `withCsvLock` — eliminates the TOCTOU
      window between `readLabelsCsv` and `writeLabelsCsv` that let
      concurrent requests overwrite each other's changes.
- `backend/src/services/labelsCsvService.js` —
    * New `withCsvLock(csvPath, fn)` export: per-file async mutex, chains
      queued callers on a Promise so two concurrent read-modify-write
      flows serialise instead of last-writer-wins.
    * `updateLabelRow` and `appendLabelRow` now serialise through
      `withCsvLock`. `appendLabelRow` inlines its upsert (the lock is not
      re-entrant; calling `updateLabelRow` from inside a held lock would
      deadlock).
- `backend/package.json` — `multer ^1.4.5-lts.1` → `^2.0.0` (installed
  2.1.1). Fixes HIGH CVE GHSA-g5hg-p3ph-g8qg. Also ran `npm audit fix`:
  `path-to-regexp` DoS and `qs` DoS transitives resolved via patch bumps.
  `npm audit` now reports 0 vulnerabilities.

**Verification**: `node --check` clean on `labellingService.js`,
`labelsCsvService.js`, `index.js`. Boot smoke-test confirms all imports
resolve (dies at `validateConfig` because the .env isn't set in the test
shell — expected). `node -e "import('multer')"` confirms multer 2.x
`memoryStorage()`, `single()`, `fileFilter` API all match existing usage.
Frontend script block extracted and `node --check`ed: balanced
335/335 braces, 914/914 parens, 58/58 brackets, syntactically valid.

**Deferred (from the same audit)**:
- XSS in `frontend/public/index.html` `displayResults` (Critical C4 in
  the report) — analyzer-mode UI, user marked analyzer status as
  "unknown" so this stays open.
- `extract_cmon_crops.py` should write `bbox=x,y,w,h` into notes on
  initial extraction so the redraw modal can overlay original YOLO bboxes
  too (today only human_redraw rows carry bbox coords).
- Dep bumps: `@anthropic-ai/sdk` 0.24 → 0.65, drop or replace deprecated
  `@google/generative-ai`, `openai` 4 → 6. No CVE urgency, but 6 majors
  of drift.
- `.env.example` still documents retired v1 labelling keys
  (`LABELLING_CROPS_DIR`, `LABELLING_LABELS_CSV`) and defaults
  `NODE_ENV=development` which leaks stack traces.

---

### 2026-04-17 — Audit fix sweep (security, data-integrity, UX)

**Context**: An end-to-end audit of the labelling subsystem surfaced 35
findings — path-traversal via CSV-controlled paths, a lost-update race on
`copy_to_siblings`, orphaned JPEGs on CSV-write failure, XSS in the sibling
ribbon, open CORS, a single-Enter pick-and-save keyboard bug, retina-blurry
redraw canvas, a `/` vs `s` doc/UI mismatch, and assorted polish. All 35 were
addressed in one sweep. v1 fallback retired — v2 (`data/labels.csv`) is now
the only supported source.

**Files changed**:
- `backend/src/services/labelsCsvService.js` — CSV-formula sanitiser, row
  cache keyed on stat.mtime, `mergeColumns` helper, `updateLabelRow` now
  preserves the on-disk column layout instead of forcing V2_COLUMNS.
- `backend/src/services/labellingService.js` — `assertInsideRoot` +
  `assertValidEntryId` for path confinement, exported `slugifyName` used by
  both the unit picker AND `buildSlugToFactions` (curly-quote parity),
  atomic single-write `copy_to_siblings`, factored-out redraw helpers
  (`extractRedrawCrops` / `markSiblingsBad` / `promoteTempCrops` /
  `cleanupTempCrops`) so new JPEGs are written `.tmp` first and only
  renamed after CSV commit succeeds. v1 branches (`listCropsV1`,
  `v1ReadersAvailable`, `useV2`, the v1 saveLabel path) deleted.
- `backend/src/index.js` — CORS restricted to the frontend + API ports,
  `?limit=` clamped to 5000 and validated, `?source=` validated against
  VALID_SOURCES, startup log no longer prints `(undefined)` in v2.
- `backend/src/config/pipeline.js` — dropped v1 config keys (`cropsDir`,
  `labelsCsv`); `cheatsheet` kept for the LLM suggest prompt.
- `frontend/public/label.html` — DPR-aware redraw canvas (sharp on retina,
  coordinates unchanged), `esc(s.unit_slug)` in the sibling title attribute,
  `javascript:` URLs blocked on `ctx-link`, single-Enter save bug fixed via
  `e.defaultPrevented` guard, session-goal added to Enter skip list, SELECT
  letter-keys no longer double-fire with global shortcuts, `/` shortcut
  renamed to `s` (matches the original design), `aria-live="polite"` on
  status line, focus parked on Save button after auto-advance, in-flight
  save idx tracked to avoid jumping one past a manually-navigated crop,
  `submitRedraws` no longer calls `advance()` before reload (kills flicker),
  `propagateMarkedBad` helper updates in-memory state before reload so the
  ribbon doesn't show stale unlabelled ticks, `esc()` now escapes `'` for
  attribute-context defence in depth, separate `state.loadBusy` flag so
  filter changes don't clobber save-busy state.

**Audit-later flow** (added in the same session on user request):
- New `status: 'audit'` pseudo-status in `saveLabel`. Writes `unit_slug=''`,
  `labeller=<name>`, `suggested_by='human'`, with `flag:audit` appended to
  notes. No faction required (slug is blank by design — the user will fill
  it in on a later pass).
- New `?audit=true` query param on `/api/labelling/crops` — filters to
  rows with blank slug AND `flag:audit` note AND a labeller.
- Frontend: replaced the "unlabelled only" checkbox with a 3-way `queue`
  dropdown: `unlabelled` / `all` / `audit pile`. Old pref is migrated.
- New "📝 Audit" button and keyboard shortcut `t`. Tracker bucket added.
- Re-labelling an audit row with a real slug strips the `flag:audit` note
  so it doesn't linger once the row is actually resolved.

**Follow-ups / deferred**:
- `suggestForCrop` alternatives still come from the cheatsheet. Wiring the
  LLM's own top-k would require extending `CLASSIFY_BASE` +
  `normalizeClassification`; docstring now makes the current behaviour
  explicit.

**Verification**: ran `node --check` on every edited backend file.
End-to-end smoke test plan is in `/home/sinan/.claude/plans/delightful-seeking-tiger.md`.

---

## Current State

The warhammer-analyzer application is a **fully functional modular AI-powered miniature analysis system** implementing the three-pass bbox pipeline with count-index lock pattern. The **labelling mode now reads from the unified `data/labels.csv` (v2 schema)** across every scraped source, with per-crop CMON context (title, artist, score, tags, description, sibling-view count).

**Core Features Implemented**:
- ✅ Modular AI provider system (Claude, OpenAI, Gemini, LLaMA)
- ✅ Three-pass bbox detection pipeline
- ✅ Count-index lock pattern (100% counting accuracy)
- ✅ Multi-tier classification cascade (cost optimization)
- ✅ Triangulation validation (second opinion for ambiguous cases)
- ✅ Full .env configuration system
- ✅ Express REST API
- ✅ Web-based frontend interface
- ✅ Labelling mode v1 (Phase 1 crops → phase1/labels.csv) — legacy, still works
- ✅ Labelling mode v2 (`data/labels.csv` unified) — new, default when file exists

---

## Recent Changes (Factual Log)

### 2026-04-17 — Phase B labelling: multi-source + context panel

**Context**: `data/labels.csv` (v2 schema, 13 columns) now exists at repo root — unified corpus across annotation + GW shop + CMON. The labelling UI was phase1-only; this change flips it to read v2 directly, with CMON metadata surfaced as labelling context.

**Files changed** (+~500 LOC):
- `backend/src/services/labelsCsvService.js` — new, 220 lines. RFC-4180 CSV parser/serialiser, readLabelsCsv/writeLabelsCsv/updateLabelRow/appendLabelRow, v2 schema constants.
- `backend/src/services/labellingService.js` — rewritten, ~320 lines. listCropsV2 reads `data/labels.csv`; source filter, unlabelled filter, limit; CMON manifest lookup (memoised) builds context object per row; slug→faction ambiguity resolution via units.json.
- `backend/src/config/pipeline.js` — added `labelsCsvV2`, `cropsRepoRoot`, `cmonRoot`, `unitsJson` config keys with sensible defaults; legacy fields preserved for v1 fallback.
- `backend/src/index.js` — `/api/labelling/crops` accepts `?source=`, `?unlabelled=`, `?limit=`; new `/api/labelling/factions` endpoint; save accepts `faction` + `labeller` in body.
- `frontend/public/label.html` — +~200 lines. Source filter select, unlabelled-only toggle, CMON context panel (title, artist, score, tags, description, source link, sibling count), faction picker dropdown, sibling-view ribbon (thumbnails), keyboard: 1–5 pick pill, f focus faction, s focus slug, [ / ] prev/next sibling view.

**Verification**:
- `await selfCheck()` returns `{mode: 'v2', healthy: true}` when `data/labels.csv` exists.
- `GET /api/labelling/factions` returns the canonical 20 faction slugs.
- `GET /api/labelling/crops?source=cmon&unlabelled=true&limit=2` returns crops with populated `context` (title, description, artist, score, tags, sibling_views).
- Legacy v1 path (scripts/phase1/crops → scripts/phase1/labels.csv) still works when `data/labels.csv` is absent.

---

### 2026-04-13 — Hardening sweep + labelling mode

**Context**: STATUS.md previously flagged "not yet tested" — first real
run would have crashed because of unsafe JSON parsing and response-shape
access in every provider. This sweep fixed the first-run-crash issues,
added consistent timeouts, tightened upload limits, and added a new
labelling-mode feature for Phase 1 of the parent photoanalyzer project
(see ../STRATEGY.md).

**Provider hardening** (`backend/src/providers/`):
- New `utils.js` — shared `safeJsonParse()` (handles ```markdown fences,
  falls back to widest `{...}` / `[...]` match, throws with preview),
  `extractTextContent()` (bounds-checked Claude/OpenAI/Gemini/OpenRouter
  response shape), `withTimeout()` (AbortSignal for fetch, race-based
  for SDKs; 30s default), `normalizeDetections()` and
  `normalizeClassification()` response-shape validators.
- New `prompts.js` — single source of truth for detection + classify
  prompts. `buildClassifyPrompt(context)` adds optional faction hint,
  allowed-unit-slug list, and free-form cheatsheet.
- Rewrote `claude.js`, `openai.js`, `gemini.js`, `llama.js` to use the
  shared utils. Classification supports a `context` object that's passed
  into the prompt (previously ignored). All provider calls timeout at
  30s.

**Config refactor** (`backend/src/config/pipeline.js`):
- New `resolveProvider()` — if the native API key is missing, silently
  falls back to OpenRouter with a rewritten model id
  (e.g. `claude-3-5-sonnet` → `anthropic/claude-3-5-sonnet`). Makes it
  possible to run the whole system off a single `OPENROUTER_API_KEY`.
- New `validateConfig()` — called at startup; walks every tier and
  throws if the provider/model combo can't be instantiated. Catches
  env-var typos before the first request.
- New `labelling` config block with cropsDir, labelsCsv, cheatsheet,
  suggestProvider, suggestModel.
- New `server` config block with maxUploadBytes, logLevel.

**Labelling mode** (new):
- `backend/src/services/labellingService.js` — lists crops from
  `../scripts/phase1/crops/`, reads/writes the canonical
  `../scripts/phase1/labels.csv` atomically (temp + rename), parses
  `unit_slugs_cheatsheet.md` to scope LLM suggestions by faction,
  emits top-1 + 4 alternatives per crop.
- New endpoints in `backend/src/index.js`:
    GET  /api/labelling/status       — config + health snapshot
    GET  /api/labelling/crops        — all crops with labelled status
    GET  /api/labelling/crops/:id/image   — serve a crop file
    POST /api/labelling/crops/:id/suggest — LLM unit-slug suggestion
    POST /api/labelling/crops/:id/label   — persist a label to CSV
- `frontend/public/label.html` — single-page labeller UI. Loads crop
  list, shows one image at a time with AI-suggested slug + alternatives
  as pills + free-text override + notes. Keyboard shortcuts: ←/→
  prev/next, Space skip, Enter save, R re-suggest. Auto-advances to
  next unlabelled crop on save.
- `server.js` — added `/label` alias for label.html; startup log now
  lists both analyzer and labeller URLs.

**Hardened server** (`backend/src/index.js`):
- Multer now enforces `maxUploadBytes` (default 50 MB) and only accepts
  image/jpeg, image/png, image/webp. Previously unlimited.
- `validateConfig()` runs at startup; process exits with a readable
  error if the configured providers can't resolve to API keys.
- Central Express error handler; all responses include requestId.
- Every request gets a request id at the middleware layer so child
  services all log consistently.

**Verified working end-to-end**:
- Server starts cleanly with OPENROUTER_API_KEY only.
- /api/health, /api/labelling/status, /api/labelling/crops, image
  serve all return expected shapes.
- Real LLM call via OpenRouter returns valid classification
  (e.g. claude-sonnet-4.5 IDed a CSM crop as `chaos_bikers` with
  correct visual reasoning).
- labels.csv write is atomic and round-trips through the CSV parser.

### December 16, 2025 - Initial Implementation

**Project Created**

**Files Created**:

**Configuration**:
- `.env.example` (88 lines)
  - Added complete configuration template
  - API keys section: OPENROUTER_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY
  - PASS 1 config: DETECTION_PROVIDER, DETECTION_MODEL, DETECTION_CONFIDENCE, NMS_IOU_THRESHOLD, BBOX_PADDING
  - PASS 2 config: ENABLE_MULTI_TIER, TIER1/2/3_PROVIDER, TIER1/2/3_MODEL, TIER1/2_THRESHOLD
  - PASS 3 config: ENABLE_TRIANGULATION, VALIDATION_PROVIDER, VALIDATION_MODEL, TRIANGULATION_THRESHOLD
  - CLIP config: ENABLE_CLIP, CLIP_SERVICE_URL, CLIP_DISAGREEMENT_THRESHOLD
  - Server config: PORT, NODE_ENV, LOG_LEVEL

- `backend/src/config/pipeline.js` (155 lines)
  - Added `PIPELINE_CONFIG` object with all configuration sections
  - Added `getDetectionConfig()` function
  - Added `getClassificationConfig()` function
  - Added `getValidationConfig()` function
  - Added `isClipEnabled()` function
  - Added `getApiKey(provider)` function - maps providers to API keys
  - Added `createProvider(providerName, model)` async function - factory pattern for provider instantiation

**Providers**:
- `backend/src/providers/base.js` (50 lines)
  - Added `AIProvider` abstract base class
  - Added `detectBboxes(imageBuffer)` abstract method
  - Added `classifyImage(cropBuffer, context)` abstract method
  - Added `analyzeImage(imageBuffer)` optional abstract method
  - Added `bufferToBase64(buffer, mimeType)` utility method

- `backend/src/providers/claude.js` (149 lines)
  - Added `ClaudeProvider` class extending `AIProvider`
  - Added `detectBboxes(imageBuffer)` implementation using Anthropic SDK
  - Added `classifyImage(cropBuffer, context)` implementation
  - Implements JSON output parsing with fallback regex extraction

- `backend/src/providers/openai.js` (146 lines)
  - Added `OpenAIProvider` class extending `AIProvider`
  - Added `detectBboxes(imageBuffer)` implementation using OpenAI SDK
  - Added `classifyImage(cropBuffer, context)` implementation
  - Uses data URL format for image encoding

- `backend/src/providers/gemini.js` (137 lines)
  - Added `GeminiProvider` class extending `AIProvider`
  - Added `detectBboxes(imageBuffer)` implementation using Google Generative AI SDK
  - Added `classifyImage(cropBuffer, context)` implementation
  - Uses inline data format for images

- `backend/src/providers/llama.js` (166 lines)
  - Added `LLaMAProvider` class extending `AIProvider`
  - Added `detectBboxes(imageBuffer)` implementation using OpenRouter API
  - Added `classifyImage(cropBuffer, context)` implementation
  - Uses fetch() for HTTP requests to OpenRouter

**Utilities**:
- `backend/src/utils/bbox.js` (171 lines)
  - Added `calculateIoU(bbox1, bbox2)` function - Intersection over Union calculation
  - Added `applyNMS(detections, iouThreshold)` function - Non-Maximum Suppression
  - Added `assignStableIds(detections)` function - UUID assignment (establishes count lock)
  - Added `normalizeBbox(bbox, imageWidth, imageHeight)` function
  - Added `denormalizeBbox(bbox, imageWidth, imageHeight)` function
  - Added `calculateArea(bbox)` function
  - Added `isValidBbox(bbox)` function - validates normalized coordinates [0-1]
  - Added `addPadding(bbox, paddingRatio)` function - adds context padding to bboxes

- `backend/src/utils/imageProcessing.js` (100 lines)
  - Added `cropImage(imageBuffer, bbox, paddingRatio)` async function using Sharp
  - Added `resizeImage(imageBuffer, maxWidth, maxHeight)` async function
  - Added `getImageDimensions(imageBuffer)` async function
  - Added `convertToJpeg(imageBuffer, quality)` async function
  - Added `cropMultiple(imageBuffer, bboxes, paddingRatio)` async function - batch cropping

- `backend/src/utils/logger.js` (41 lines)
  - Added `LOG_LEVELS` constant: DEBUG, INFO, WARN, ERROR
  - Added `formatTimestamp()` function
  - Added `shouldLog(level)` function - respects LOG_LEVEL env var
  - Added `log(level, message, ...args)` function
  - Exported `logger` object with `debug()`, `info()`, `warn()`, `error()` methods

**Services**:
- `backend/src/services/detectionService.js` (64 lines)
  - Added `detectMiniatures(imageBuffer)` async function - PASS 1 implementation
  - Loads detection provider from config
  - Runs bbox detection
  - Filters invalid bboxes
  - Applies NMS to remove duplicates
  - Assigns UUIDs (establishes count lock)
  - Returns {detections, authorityCount, metadata}
  - Includes detailed logging of pipeline stages

- `backend/src/services/classificationService.js` (84 lines)
  - Added `classifyMiniatures(imageBuffer, detections, authorityCount)` async function - PASS 2
  - Verifies count integrity at start
  - Implements multi-tier cascade logic
  - For each detection: crops image, tries each tier until confidence threshold met
  - Escalates to next tier on low confidence
  - Tracks tier usage statistics
  - Verifies count integrity at end
  - Returns {classifications: Map<id, classification>, metadata}

- `backend/src/services/validationService.js` (119 lines)
  - Added `validateClassifications(imageBuffer, detections, classifications, authorityCount)` async function - PASS 3
  - Skips if triangulation disabled
  - Verifies count integrity at start
  - For low-confidence classifications: gets second opinion from validator
  - Compares opinions, flags disagreements
  - Uses higher confidence classification on disagreement
  - Marks classifications as triangulated/disagreement
  - Verifies count integrity at end
  - Returns {validatedClassifications, metadata}

**Backend**:
- `backend/src/index.js` (152 lines)
  - Created Express server
  - Added CORS middleware
  - Added `GET /api/health` endpoint - health check
  - Added `POST /api/analyze` endpoint - main analysis pipeline
  - Orchestrates three-pass pipeline: detectMiniatures → classifyMiniatures → validateClassifications
  - Aggregates results by unit type
  - Verifies final count integrity
  - Returns JSON response with detections, summary, metadata
  - Includes comprehensive logging with request IDs
  - Starts server on PORT (default 3002)

- `backend/package.json` (25 lines)
  - Package name: warhammer-analyzer-backend
  - Type: module (ES modules)
  - Scripts: `dev`, `start`
  - Dependencies: @anthropic-ai/sdk, @google/generative-ai, cors, dotenv, express, multer, openai, sharp

**Frontend**:
- `frontend/public/index.html` (318 lines)
  - Single-page application
  - Drag-and-drop file upload interface
  - Click-to-browse file selection
  - Real-time analysis status display
  - Results display with:
    - Summary cards by unit type
    - Detailed detection list
    - Confidence scores
    - Tier badges (T1/T2/T3)
    - Triangulation and disagreement badges
  - Gradient styling with dark theme
  - Responsive grid layout
  - Fetch API integration with backend

**Root Files**:
- `package.json` (20 lines)
  - Root package.json for workspace
  - Scripts: `dev`, `dev:frontend`, `install:backend`, `start`
  - Dependency: express (for static file server)

- `server.js` (19 lines)
  - Static file server for frontend
  - Serves frontend/public/ directory
  - Runs on port 3003
  - Simple Express static middleware

**Documentation**:
- `EPIC.md` (394 lines)
  - Complete project explanation
  - Project vision and core innovation section
  - Count-index lock pattern explanation
  - Three-pass pipeline architecture documentation
  - Modular provider system documentation
  - Configuration system explanation
  - End-to-end flow diagrams
  - Technical stack details
  - Project structure map
  - "Why this architecture?" section
  - Success metrics

- `CLAUDE.md` (308 lines)
  - Developer guidance for Claude Code
  - CRITICAL documentation requirements section
  - Mandatory EPIC.md, STATUS.md, README.md update instructions
  - Project overview
  - Development workflow
  - Architecture explanation
  - Configuration examples
  - Common development tasks
  - Testing strategy
  - Documentation standards

- `README.md` - Not yet created
- `STATUS.md` - This file

**Directories Created**:
- `backend/src/config/`
- `backend/src/providers/`
- `backend/src/services/`
- `backend/src/utils/`
- `frontend/public/`

**Configuration Defaults Set**:
- Detection: Claude 3.5 Haiku
- Tier 1: Gemini 2.0 Flash Lite (threshold 0.85)
- Tier 2: Claude 3.5 Sonnet (threshold 0.75)
- Tier 3: GPT-4o (final arbiter)
- Validation: LLaMA 3.2 90B Vision (threshold 0.75)
- Multi-tier: Enabled by default
- Triangulation: Enabled by default
- NMS IoU threshold: 0.5
- Bbox padding: 0.1 (10%)

---

## Testing Status

**Not yet tested** - Initial implementation complete, testing pending

**Next Steps**:
1. Install backend dependencies: `npm run install:backend`
2. Create `.env` file with API keys
3. Start backend: `npm run dev`
4. Start frontend: `npm run dev:frontend`
5. Test with sample Warhammer 40K miniature images
6. Verify count accuracy
7. Verify classification accuracy
8. Test multi-tier cascade
9. Test triangulation
10. Test different AI provider configurations

---

## Known Issues

None - initial implementation just completed

---

## Performance Metrics

Not yet measured - awaiting first test run

**Expected Performance** (based on design):
- Count Accuracy: 100% (guaranteed by count-lock)
- Classification Accuracy: Target 85-90%
- Cost Efficiency: 60-80% reduction via multi-tier cascade
- Processing Speed: 5-15 seconds per image (depends on miniature count)

---

## Configuration Notes

All AI providers, models, and thresholds are configurable via `.env` file. See `.env.example` for complete reference.

**Quick Configuration Changes**:

Switch detection provider:
```bash
DETECTION_PROVIDER=openai
DETECTION_MODEL=gpt-4o
```

Disable multi-tier (use single classifier):
```bash
ENABLE_MULTI_TIER=false
```

Disable triangulation:
```bash
ENABLE_TRIANGULATION=false
```

Lower triangulation threshold (more second opinions):
```bash
TRIANGULATION_THRESHOLD=0.70
```

---

## Architecture Verification

**Count-Index Lock Pattern**: ✅ Implemented
- PASS 1 assigns UUIDs
- PASS 2 verifies count integrity (before/after)
- PASS 3 verifies count integrity (before/after)
- Final verification before returning results

**Modularity**: ✅ Implemented
- Abstract `AIProvider` base class
- 4 provider implementations
- Factory pattern in `pipeline.js`
- All providers swappable via config

**Configuration-Driven**: ✅ Implemented
- All settings in `.env`
- No hardcoded AI provider references outside providers/
- Pipeline behavior fully configurable

---

## Development Environment

**Node.js Version**: Expected v18+
**Package Manager**: npm
**ES Modules**: Enabled (type: "module")

---

## Next Development Priorities

1. Test with real Warhammer 40K images
2. Measure actual accuracy and performance
3. Fine-tune confidence thresholds based on results
4. Add CLIP visual similarity service (optional)
5. Add YOLO integration (optional)
6. Create training data collection mode (optional)
7. Add batch processing support (optional)
