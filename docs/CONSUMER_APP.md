# Battle Scanner Consumer App — Technical Reference

**Version**: 2.0
**Last updated**: March 2026
**Location**: `consumer/` workspace
**Dev URL**: `http://localhost:5174`
**Run**: `npm run dev:consumer` from repo root

---

## What It Is

Battle Scanner is a desktop-first, feature-rich web application for scanning Warhammer 40K armies from photos. It identifies individual units by name, calculates points costs, lets you build and manage army lists, and exports them to PDF or clipboard.

The UI is fully functional. The AI inference layer is mocked — a single hardcoded scan result demonstrates the complete flow. When real YOLO inference is ready, one function body in `services/detectionService.ts` is the only file that changes.

---

## Why It Was Rebuilt (v1 → v2)

The original consumer app was a simple mobile-first PWA with:
- Camera capture + file upload
- Faction-level detection (e.g. "Space Marines: 8 models") — no unit names
- Single results page with confidence bars
- No army building, no history, no export

v2 expands this into a full desktop app with unit-level identification, army management, and export tools. The original PWA concerns (service worker, `vite-plugin-pwa`, `axios`) were removed — no longer needed for a desktop-first tool with local IndexedDB persistence.

---

## Tech Stack

| Concern | Library | Why |
|---------|---------|-----|
| Framework | React 18 + TypeScript | Monorepo standard |
| Build | Vite 4 | Already configured, fast HMR |
| Routing | react-router-dom v6 (hash router) | Tabs → routes, no server config |
| State | Zustand 4 | Minimal boilerplate, clean TypeScript, no providers |
| Image crop | react-easy-crop | Lightweight, returns exact crop Area for canvas |
| PDF export | jsPDF 2 | Simple imperative API, no server needed |
| Persistence | idb 8 (IndexedDB) | Already a dep, works offline, ~unlimited storage |
| HTTP | Native fetch | One fewer dep (removed axios) |

**Removed from v1**: `axios`, `vite-plugin-pwa`
**Added in v2**: `zustand`, `react-router-dom`, `react-easy-crop`, `jspdf`

---

## File Structure — All 57 Source Files

```
consumer/src/
│
├── main.tsx                          # Entry point — creates hash router, mounts RouterProvider
├── index.css                         # Tailwind directives + scrollbar-thin utility
├── vite-env.d.ts                     # Vite client type reference
│
├── types/                            # TypeScript interfaces — shared across app
│   ├── detection.ts                  # BBox, Detection, ScanResult, GroupingMode, FactionSummary
│   ├── army.ts                       # ArmyUnit, Army, ArmySuggestion, PlaystyleTag
│   ├── units.ts                      # UnitDefinition (unit database row)
│   └── export.ts                     # ExportFormat, ExportOptions
│
├── data/                             # Static data — no runtime fetching
│   ├── units.ts                      # ~180 unit definitions across 20 factions
│   ├── mockScan.ts                   # Hardcoded 12-detection example + placeholder image generator
│   ├── battlefieldRoles.ts           # Role definitions: HQ / Troops / Elites / etc.
│   └── suggestions.ts               # 10 hardcoded army composition suggestions
│
├── stores/                           # Zustand global state (4 stores)
│   ├── scanStore.ts                  # Upload queue, scan state, current result, bbox highlights
│   ├── armyStore.ts                  # Army list CRUD, unit counts, save to DB
│   ├── historyStore.ts               # Past scans + armies from IndexedDB
│   └── uiStore.ts                   # Modal state, search query
│
├── services/                         # Side-effecting operations
│   ├── detectionService.ts           # AI call (currently mocked) — single swap point
│   ├── exportService.ts             # PDF generation, text formatting, clipboard
│   └── storageService.ts            # Thin wrapper re-exporting lib/db.ts functions
│
├── hooks/                            # React hooks with logic
│   ├── useBboxInteraction.ts         # Hover/click sync between canvas and unit list cards
│   └── usePointsCalculator.ts       # Derived points/models/percentage from army units
│
├── utils/                            # Pure functions, no side effects
│   ├── factions.ts                  # FACTIONS array, FACTION_MAP, color/name helpers
│   ├── factionDisplay.ts            # formatFactionName (handles T'au, apostrophes)
│   ├── points.ts                    # estimateTotalPoints
│   ├── time.ts                      # relativeTime — "2h ago", "3d ago"
│   ├── resizeImage.ts               # Canvas-based image resize (max 1280px)
│   ├── cropImage.ts                 # Canvas crop from react-easy-crop Area
│   └── formatExport.ts              # armyToShareHash / armyFromShareHash (btoa/atob)
│
├── lib/
│   ├── db.ts                        # IndexedDB via idb: scans store + armies store
│   └── id.ts                        # generateId() — UUID with HTTP-safe fallback
│
├── layouts/
│   └── AppLayout.tsx                # Header + TabNav + <Outlet /> — wraps all pages
│
├── pages/
│   ├── ScanPage.tsx                 # Tab 1: upload photos, crop, scan
│   ├── ResultsPage.tsx              # Tab 2: split bbox canvas / unit list
│   ├── ArmyBuilderPage.tsx          # Tab 3: army list + suggestions + export
│   └── HistoryPage.tsx              # Tab 4: past scans + saved armies
│
└── components/
    ├── Header.tsx                   # Top bar: "BATTLE SCANNER" logo + version
    ├── TabNav.tsx                   # NavLink tabs: Scan | Results | Army Builder | History
    ├── Spinner.tsx                  # Animated border spinner (sm/md/lg)
    ├── EmptyState.tsx               # Centered icon + title + message + optional action button
    ├── FactionIcon.tsx              # Colored square with 2-letter faction initials
    │
    ├── scan/
    │   ├── PhotoUploader.tsx        # Drag-drop or click to upload (JPEG/PNG/WebP, ≤20MB)
    │   ├── ImagePreviewGrid.tsx     # 4-col thumbnail grid with Crop/Remove overlays
    │   ├── ImageCropper.tsx         # react-easy-crop fullscreen modal with zoom slider
    │   ├── FactionHintSelector.tsx  # Optional faction dropdown — 20 factions listed
    │   └── ScanButton.tsx           # Calls detectionService, shows spinner, navigates
    │
    ├── results/
    │   ├── SplitView.tsx            # CSS grid 55fr/45fr layout container
    │   ├── BboxCanvas.tsx           # Canvas: draw image + colored bboxes + labels
    │   ├── UnitList.tsx             # Right panel: grouped/flat unit card list
    │   ├── UnitCard.tsx             # Single unit: faction icon, name, role, confidence bar
    │   ├── UnitEditInline.tsx       # Inline edit form: name + points (appears on selected)
    │   ├── GroupingToggle.tsx       # Faction | Role | Flat toggle pill buttons
    │   ├── UncertainSection.tsx     # Separate section for confidence < 50% detections
    │   └── ConfidenceBar.tsx        # Colored mini progress bar (green/yellow/orange/red)
    │
    ├── army/
    │   ├── ArmyHeader.tsx           # Inline-editable army name + faction icons + points limit
    │   ├── PointsSummary.tsx        # Points total, progress bar, over-limit warning
    │   ├── ArmyUnitRow.tsx          # Unit row: icon, name, +/- count, pts, remove button
    │   ├── UnitSearchAdd.tsx        # Fuzzy search over UNIT_DATABASE, dropdown results
    │   ├── CompositionSuggestions.tsx # Top 3 suggestions filtered by faction + playstyle
    │   ├── PlaystyleFilter.tsx      # Aggressive/defensive/balanced/competitive chip toggles
    │   ├── ExportMenu.tsx           # PDF / Copy Text / BattleScribe (stub) buttons
    │   └── ShareButton.tsx          # Encodes army to URL hash, copies link to clipboard
    │
    └── history/
        ├── ScanHistoryGrid.tsx      # Grid of past scan cards
        ├── HistoryCard.tsx          # Scan: thumbnail + detections count + points + factions
        ├── SavedArmyList.tsx        # Grid of saved army cards
        └── SavedArmyCard.tsx        # Army: name + points/limit + factions + timestamp
```

---

## The Four Tabs

### Tab 1 — Scan (`/#/scan`)

**Purpose**: Upload photos and trigger a scan.

**User flow**:
1. Drop images or click to browse — `PhotoUploader` accepts JPEG/PNG/WebP up to 20MB each
2. Images appear in a 4-column thumbnail grid (`ImagePreviewGrid`)
3. Click any thumbnail to open the full-screen `ImageCropper` modal (react-easy-crop, 4:3 aspect, zoom slider)
4. After cropping, the thumbnail shows a "Cropped" badge and the cropped version is stored
5. Optionally pick a faction hint from the dropdown (20 factions — helps the future AI model prioritise)
6. Click **Scan Army** — `ScanButton` calls `detectionService.detectFromImages(files, factionHint)`, shows a spinner
7. On success: result saved to IndexedDB + scanStore, router navigates to `/results/{id}`

**State managed by**: `scanStore` (upload queue, crop blobs, scanning flag, error), `uiStore` (which image is being cropped)

---

### Tab 2 — Results (`/#/results/:scanId?`)

**Purpose**: View detections overlaid on the photo, inspect and edit individual unit identifications.

**Layout**: `SplitView` — 55% canvas on left, 45% scrollable unit list on right.

**Canvas (`BboxCanvas`)**:
- Draws the scan image scaled to container width via `ResizeObserver`
- Iterates `detections` array, draws a colored rectangle per detection (color from `getFactionColor()`)
- Fill: 15% opacity normally, 30% when hovered/selected
- Stroke: 1px normal, 2px hovered, 3px selected
- Label above bbox: `"{unitName} {confidence}%"` in Orbitron 11px on a matching color background
- Mouse move → hit-tests bboxes → calls `useBboxInteraction.onCanvasHover()` → `scanStore.setHighlightedDetection()`
- Click → `onCanvasClick()` → `setSelectedDetection()` + scrolls the matching unit card into view

**Unit list (`UnitList` → `UnitCard`)**:
- Grouped by faction, role, or flat — toggled by `GroupingToggle`
- Each `UnitCard` shows: `FactionIcon`, unit name, points, role label, `ConfidenceBar`
- Hover on a card → `onCardHover()` → canvas redraws with that bbox highlighted
- Click on a card → `onCardClick()` → canvas selects that bbox
- When selected, card expands to show Edit and Remove buttons
- Edit opens `UnitEditInline` — inputs for name and points, saves via `scanStore.editDetection()`
- Remove calls `scanStore.removeDetection()` — removes from both list and canvas

**Uncertain detections (`UncertainSection`)**:
- Any detection with `confidence < 0.5` rendered separately at the bottom
- Same `UnitCard` component, but visually separated with an orange "Uncertain Detections (N)" header
- Still interactive — can edit, remove, or add to army

**"Add to Army" button**:
- Copies all `confident` detections (≥0.5) into `armyStore` as `ArmyUnit` entries
- Navigates to `/army`

**Deep-link support**: If navigated to `/results/abc123` directly (from History), the page fetches `getScan('abc123')` from IndexedDB and loads it into `scanStore.currentResult`.

---

### Tab 3 — Army Builder (`/#/army`)

**Purpose**: Manage an army list: add/remove units, track points, get composition suggestions, export.

**Layout**: Two-column grid — main army list on left (flexible), suggestions panel on right (380px fixed).

**Army Header (`ArmyHeader`)**:
- Army name is rendered as a heading, click to switch to an inline `<input>` — blur or Enter saves
- Faction icons auto-generated from the set of factions in current units
- Points limit selector: 500 / 1000 / 1500 / 2000 / 2500 / 3000

**Points Summary (`PointsSummary`)**:
- Displays `{totalPoints} / {pointsLimit}` in large font (red if over limit)
- Progress bar: green → orange (>90%) → red (over limit)
- "Over by N points" message when over

**Unit Search (`UnitSearchAdd`)**:
- Text input — debounce-free, reacts on every keystroke after 2+ characters
- `useMemo` filters `UNIT_DATABASE` (~180 entries) by unit name, faction key, or keywords
- Dropdown shows up to 15 results: faction icon, name, role, points/model, "+ Add" button
- Adding creates an `ArmyUnit` in `armyStore` with `count = unit.minModels`
- Dropdown closes on outside click (via a fixed-inset transparent div overlay)

**Army Unit Rows (`ArmyUnitRow`)**:
- Faction icon, unit name, total points (count × pointsPerModel)
- Role label and per-model points in secondary text
- `-` button: decrements count, removes unit if count reaches 0
- `+` button: increments count
- `×` button: removes unit regardless of count

**Composition Suggestions (`CompositionSuggestions`)**:
- Reads factions from current army units — shows only suggestions for matching factions
- If no units yet, shows suggestions for all factions
- Filtered by active `PlaystyleFilter` chip (aggressive / defensive / balanced / competitive)
- Shows top 3 matching suggestions
- Each suggestion: faction icon, title, playstyle tag, total points, description, unit list with reasons
- "Apply" button adds all suggested units to the army at once

**Export options**:
- **Export PDF**: jsPDF generates a multi-page document grouped by battlefield role, auto-paginating. Downloads as `{armyName}.pdf`
- **Copy as Text**: Formats army as plain text (role headers, unit rows, totals) → copies to clipboard. Button briefly shows "Copied!"
- **BattleScribe**: Disabled stub with "Coming soon" tooltip — `.rosz` format requires JSZip and is deferred
- **Share Link**: `armyToShareHash()` encodes the army as a compact JSON → `btoa()` → appended as `?share=` hash param. Full URL copied to clipboard

**Save**: `saveCurrentArmy()` calls `storageService.saveArmy()` which writes to IndexedDB `armies` store.

---

### Tab 4 — History (`/#/history`)

**Purpose**: Browse and reload past scans and saved armies.

**On mount**: `useHistoryStore.loadHistory()` fetches all scans and armies from IndexedDB (both stores, sorted by timestamp desc).

**Scan grid (`ScanHistoryGrid` → `HistoryCard`)**:
- 4-column grid of past scans
- Each card: scan image thumbnail (4:3 aspect-ratio), timestamp (`relativeTime()`), total points, detection count, faction icons
- Click: `setCurrentResult(scan)` → navigate to `/results/{scan.id}`
- Hover reveals a `×` delete button in the top-right corner
- Delete: `historyStore.removeScan(id)` → removes from IndexedDB and local state

**Army grid (`SavedArmyList` → `SavedArmyCard`)**:
- 3-column grid of saved armies
- Each card: army name, points/limit, unit count, faction icons, `updatedAt` timestamp
- Click: navigates to `/army` (TODO: load specific army into armyStore)
- Hover reveals delete button

---

## State Architecture — Zustand Stores

### `scanStore`

Central store for the entire scan lifecycle.

```typescript
// Upload queue
uploadedImages: UploadedImage[]    // { id, file, previewUrl, croppedBlob?, croppedUrl? }
factionHint: string | undefined
addImages(files: File[])           // creates blob URLs, pushes to array
removeImage(id)                    // revokes blob URLs, removes
setCroppedImage(id, blob, url)     // stores cropped version
clearUpload()                      // revokes all blob URLs, resets

// Scan execution
isScanning: boolean
scanError: string | null
startScan(): Promise<ScanResult | null>  // calls detectionService, saves to DB

// Current result
currentResult: ScanResult | null
setCurrentResult(result)
editDetection(id, updates)         // mutates detection in currentResult
removeDetection(id)

// Bbox interaction (driven by useBboxInteraction hook)
highlightedDetectionId: string | null
selectedDetectionId: string | null
setHighlightedDetection(id)
setSelectedDetection(id)

// Display
groupingMode: 'faction' | 'role' | 'flat'
setGroupingMode(mode)
```

### `armyStore`

Manages the "current working army" — one army at a time.

```typescript
currentArmy: Army                        // { id, name, units, pointsLimit, ... }
resetArmy()                              // creates fresh army with new UUID
setArmyName(name)
setPointsLimit(limit)
addUnitsFromDetections(detections, scanId)  // filters confidence ≥ 0.5, maps to ArmyUnit
addUnit(unit)                            // manual add from UnitSearchAdd
removeUnit(id)
updateUnitCount(id, delta)               // removes unit if count reaches 0
saveCurrentArmy(): Promise<void>         // persists to IndexedDB
```

### `historyStore`

Read-only view of IndexedDB contents (loaded on mount of HistoryPage).

```typescript
scans: ScanResult[]
armies: Army[]
isLoading: boolean
loadHistory()               // fetches all from both IndexedDB stores
removeScan(id)              // deletes from DB + removes from local state
removeArmy(id)
```

### `uiStore`

Ephemeral UI state with no persistence.

```typescript
cropImageId: string | null     // which image is currently open in the crop modal
setCropImageId(id)
searchQuery: string            // currently unused in routing, ready for global search
setSearchQuery(query)
exportMenuOpen: boolean
setExportMenuOpen(open)
```

---

## Hooks

### `useBboxInteraction`

Manages the bidirectional highlight sync between the canvas and unit card list.

```typescript
// Returned values
highlightedId: string | null    // read from scanStore
selectedId: string | null       // read from scanStore
onCanvasHover(x, y, detections, scale)   // hit-tests bboxes, sets highlighted
onCanvasClick(x, y, detections, scale)   // hit-tests bboxes, sets selected, scrolls card
onCardHover(id | null)                   // directly sets highlighted
onCardClick(id)                          // sets selected
registerCardRef(id, el)                  // stores DOM ref for scrollIntoView

// Hit test logic
// Iterates detections backwards (topmost drawn = last in array = found first)
// bbox coords scaled by `scale` (canvas pixels per image pixel)
// Returns first Detection whose scaled bbox contains the cursor point
```

### `usePointsCalculator`

```typescript
usePointsCalculator(units: ArmyUnit[], pointsLimit: number)
// Returns (memoized):
// { totalPoints, totalModels, percentage, isOver, remaining }
// percentage = min(100, totalPoints / pointsLimit * 100)
// isOver = totalPoints > pointsLimit
// remaining = pointsLimit - totalPoints (negative when over)
```

---

## Data Layer

### Unit Database (`data/units.ts`)

~180 `UnitDefinition` entries covering 20 factions:

| Faction | Units |
|---------|-------|
| Space Marines | 21 (Captain through Land Raider) |
| Necrons | 18 (Overlord through Monolith) |
| Chaos Space Marines | 14 |
| Orks | 14 |
| T'au Empire | 16 |
| Tyranids | 12 |
| Astra Militarum | 11 |
| Adeptus Custodes | 7 |
| Adeptus Mechanicus | 9 |
| Adepta Sororitas | 8 |
| Craftworld Aeldari | 12 |
| Chaos Daemons | 8 |
| Drukhari | 7 |
| Genestealer Cults | 6 |
| Leagues of Votann | 5 |
| Imperial Knights | 5 |
| Chaos Knights | 4 |

Each entry: `{ name, faction, role, pointsPerModel, minModels, maxModels, keywords[] }`

Keywords are used for search (e.g. "psyker", "terminator", "vehicle") to let users find units without knowing exact names.

### Mock Scan (`data/mockScan.ts`)

12 detections in a 1200×900 image space:

| Detection | Faction | Confidence | Role |
|-----------|---------|------------|------|
| Captain | Space Marines | 96% | HQ |
| Intercessors × 2 | Space Marines | 93%, 91% | Troops |
| Redemptor Dreadnought | Space Marines | 89% | Elites |
| Eradicator Squad | Space Marines | 85% | Heavy Support |
| Bladeguard Veterans | Space Marines | 82% | Elites |
| Overlord | Necrons | 94% | HQ |
| Necron Warriors | Necrons | 88% | Troops |
| Skorpekh Destroyers | Necrons | 79% | Elites |
| Canoptek Wraiths | Necrons | 72% | Fast Attack |
| Scouts (uncertain) | Space Marines | 42% | Troops |
| Scarab Swarms (uncertain) | Necrons | 35% | Fast Attack |

Bboxes are realistic (spread across the image, no overlaps). The `generatePlaceholderImage()` function creates a dark navy canvas with a grid, brass title text, and grey subtitle — used as the display image for the mock scan since no real photo is available.

### Suggestions (`data/suggestions.ts`)

10 `ArmySuggestion` entries:

| ID | Faction | Playstyle | Title |
|----|---------|-----------|-------|
| sm-aggressive | Space Marines | Aggressive | Assault Spearhead |
| sm-balanced | Space Marines | Balanced | Gladius Task Force |
| sm-competitive | Space Marines | Competitive | Ironstorm Gunline |
| nec-defensive | Necrons | Defensive | Living Metal Wall |
| nec-aggressive | Necrons | Aggressive | Destroyer Cult |
| ork-aggressive | Orks | Aggressive | WAAAGH! Stampede |
| tau-defensive | T'au | Defensive | Mont'ka Gunline |
| nid-balanced | Tyranids | Balanced | Synaptic Swarm |
| cust-competitive | Adeptus Custodes | Competitive | Golden Host |
| am-balanced | Astra Militarum | Balanced | Cadian Combined Arms |

Each includes: title, description, playstyle tag, faction, suggested units with reasons, and total points.

### Battlefield Roles (`data/battlefieldRoles.ts`)

8 roles as a `const` tuple for full type inference:
`hq` | `troops` | `elites` | `fast_attack` | `heavy_support` | `dedicated_transport` | `lord_of_war` | `fortification`

`getRoleLabel(key)` converts role keys to display labels (e.g. `'fast_attack'` → `'Fast Attack'`).

---

## Services

### `detectionService.ts` — The AI Swap Point

```typescript
export async function detectFromImages(
  images: File[],
  factionHint?: string
): Promise<ScanResult>
```

Currently: waits 1500ms (simulates network), returns `MOCK_SCAN_RESULT` with a fresh UUID and timestamp. The `generatePlaceholderImage()` canvas image is used as the display image.

**To connect real inference**: replace the function body with a `fetch('/api/detect', { method: 'POST', body: formData })` call and a response mapper. Nothing else in the app changes.

### `exportService.ts`

```typescript
exportAsText(army: Army): string
// Returns multi-line text grouped by role:
// === Army Name ===
// Points: 1240 / 2000
//
// ── HQ ──
//   Captain x1 — 80 pts [Space Marines]
// ...

exportAsPdf(army: Army): void
// jsPDF document: title, points subtitle, role sections with units
// Auto-paginates at 260mm. Saves as {armyName}.pdf via browser download.

copyToClipboard(text: string): Promise<void>
// navigator.clipboard.writeText wrapper
```

### `storageService.ts`

Thin re-export of `lib/db.ts` functions. Exists so components import from `services/` not `lib/`, keeping the layer separation clean.

---

## IndexedDB Schema

Database name: `battle-scanner`, version 1.

**`scans` store**:
- Key path: `id` (UUID string)
- Index: `by-timestamp` on `timestamp` (ISO string) — used for sorted retrieval
- Value: full `ScanResult` including `imageDataUrl` (base64 JPEG, ~200–400KB per scan)

**`armies` store**:
- Key path: `id` (UUID string)
- Index: `by-updated` on `updatedAt` (ISO string)
- Value: full `Army` with all `ArmyUnit` entries

Storage note: base64 images in IndexedDB can grow large. At ~300KB per scan, 100 scans = ~30MB. IndexedDB has no practical size limit on desktop Chrome/Firefox.

---

## Routing

```
/#/                 → redirect to /#/scan
/#/scan             → ScanPage
/#/results          → ResultsPage (shows empty state if no current result)
/#/results/:scanId  → ResultsPage (loads scan from IndexedDB if not in memory)
/#/army             → ArmyBuilderPage
/#/history          → HistoryPage
```

Hash routing (`createHashRouter`) was chosen because:
- No server-side route configuration needed (works on `file://`, Netlify, GitHub Pages)
- Share links and history links remain valid even on page refresh
- Future army share links use `?share=` hash parameter within the army route

`TabNav` uses `NavLink` from react-router-dom — the active tab gets `border-brass-light text-brass-light` styling automatically via the `isActive` callback.

---

## Design System

Tailwind config extends the existing gothic/grim theme:

```javascript
colors: {
  gothic: { darker: '#0a0a0a', dark: '#2a3d52', medium: '#3d4a63', light: '#5a6b82' },
  brass:  { dark: '#8b6914', DEFAULT: '#b08d57', light: '#d4af37' },
  gold:   { DEFAULT: '#ffd700', muted: '#b8960c' },
  surface: { '1': '#111', '2': '#1a1a1a', '3': '#222', '4': '#2a2a2a' },
}
fonts: {
  gothic: 'Cinzel, serif'     // headings, army names, labels
  grim: 'Orbitron, monospace' // data values, tabs, tags, points
}
```

**Color usage conventions**:
- `brass-light` — active tabs, headings, key values (army name, selected states)
- `brass` — buttons, points values, badges
- `surface-1/2/3/4` — layered card backgrounds (gets lighter as nesting increases)
- `gothic-light` — secondary/placeholder text
- Faction colors from `getFactionColor()` — used on `FactionIcon`, bbox strokes, labels

**No animations** — all keyframe/animation config removed from tailwind. The spinner uses `animate-spin` (built into Tailwind, not the removed custom ones).

---

## Configuration Files Changed

### `consumer/package.json`
- Version bumped to 2.0.0
- Added: `zustand ^4.4.7`, `react-router-dom ^6.21.0`, `react-easy-crop ^5.0.8`, `jspdf ^2.5.1`
- Removed: `axios ^1.6.0`, `vite-plugin-pwa ^0.17.4`
- Scripts unchanged: `dev` / `build` / `preview`

### `consumer/vite.config.ts`
- Removed VitePWA plugin import and configuration
- Kept React plugin and `/api` proxy to `localhost:3001`

### `consumer/tailwind.config.js`
- Added `brass`, `gold`, `surface` color scales
- Removed all `keyframes` and `animation` extensions
- Kept fonts, gothic colors, and shadow-glow variants

### `consumer/index.html`
- Removed: `theme-color` meta, apple PWA meta tags, manifest link
- Kept: Google Fonts preconnect + Cinzel/Orbitron stylesheet link
- Updated title (already "Battle Scanner")

---

## Build Output

```
dist/index.html                            0.80 kB  (gzip: 0.44 kB)
dist/assets/index.css                     16.12 kB  (gzip: 3.99 kB)
dist/assets/purify.es.js                  22.03 kB  (gzip: 8.72 kB)   ← jsPDF dep
dist/assets/index.es.js                  150.63 kB  (gzip: 51.35 kB)  ← main bundle
dist/assets/html2canvas.esm.js           201.43 kB  (gzip: 47.71 kB)  ← jsPDF dep
dist/assets/index.js                     676.62 kB  (gzip: 213.67 kB) ← vendor bundle
```

Total gzip: ~325KB. The large main chunk is dominated by jsPDF + its html2canvas dependency. If bundle size becomes a concern, `exportService.ts` can dynamically import jsPDF (`const { jsPDF } = await import('jspdf')`) to split it into a lazy chunk.

---

## What's Not Yet Done

| Feature | Status | Notes |
|---------|--------|-------|
| Real AI inference | Mock | One function swap in `detectionService.ts` |
| BattleScribe export | Stub (disabled button) | `.rosz` needs JSZip, deferred |
| Load saved army into armyStore | TODO stub | History page navigates to `/army` but doesn't load the army data yet |
| Army share link decode | Implemented but not applied on load | `armyFromShareHash()` exists; `ArmyBuilderPage` needs a `useEffect` to check `?share=` param on mount |
| Multi-image scan stitching | Single result | `detectFromImages` currently ignores the files array length; real inference would need to process all images and merge detections |
| Camera capture | Removed | Was in v1 (`CameraCapture.tsx` with `getUserMedia`). Removed in v2 as desktop-first. Can be re-added as a scan component. |

---

## Running the App

```bash
# From repo root
npm run dev:consumer       # starts Vite on port 5174

# Or from consumer/ directory
cd consumer
npm run dev                # same thing
npm run build              # TypeScript check + Vite production build
```

Navigate to `http://localhost:5174` → lands on Scan tab.

**Quick demo of the full flow**:
1. Drop any image onto the upload zone
2. Optionally click it to crop
3. Click "Scan Army" — waits 1.5s (mock latency), then navigates to Results
4. Canvas shows 12 detected units (Space Marines blue + Necrons cyan)
5. Hover/click bboxes and unit cards to see sync
6. Click "Add to Army" → navigates to Army Builder with 10 confident detections pre-loaded
7. Adjust counts, search for additional units
8. Click "Save Army" → go to History tab to see it persisted
