# Scraping Pipeline — How It Works

This document covers the image collection system that builds `training_data_v2/` — the clean, unit-level dataset used to train Battle Scanner's detection model.

---

## Overview

Two scrapers run in parallel, targeting the same output directory:

| Scraper | Source | Bot detection | Speed |
|---------|--------|---------------|-------|
| `scrape_ebay.py` | eBay listings | High — requires real browser (Playwright) | Slow (~5–10s/search) |
| `scrape_dakkadakka.py` | DakkaDakka gallery | None — plain HTTP | Faster (~3–6s/search) |

Both scrapers share the same:
- Output directory: `training_data_v2/`
- Metadata log: `training_data_v2/metadata/scrape_log.csv`
- Deduplication file: `training_data_v2/metadata/duplicates.txt`

A progress dashboard (`scrape_progress.py`) reads both in real time.

---

## Unit Database (`scripts/data/units.json`)

Single source of truth for all 20 factions and their units. Scrapers read this file to know what to search for.

### Structure

```json
{
  "search_templates": {
    "isolation": [
      "{unit} warhammer 40k painted",
      "{unit} {faction} painted miniature"
    ],
    "combat_patrol": [
      "combat patrol {faction} warhammer 40k painted",
      "combat patrol {faction} assembled painted warhammer"
    ]
  },
  "factions": {
    "space_marines": {
      "name": "Space Marines",
      "combat_patrol": {
        "box_name": "Combat Patrol: Space Marines",
        "contents": ["Captain in Terminator Armour", "Infernus Squad", ...]
      },
      "units": [
        { "name": "Intercessor Squad", "category": "infantry" },
        ...
      ]
    }
  }
}
```

### Current scale

| Stat | Value |
|------|-------|
| Factions | 20 |
| Total units | ~837 |
| Combat patrols | 17 (3 factions have no CP box) |
| Target images | ~15 per unit + 20 per combat patrol |

### Factions without a combat patrol box

Harlequins, Ynnari, and Imperial Agents have no standalone Combat Patrol set — their `combat_patrol` field is `null`.

---

## Image Types Collected

### 1. Unit isolation shots

Individual photos of a single unit, ideally from eBay listings (painted, on a plain background) or DakkaDakka gallery entries with a high paintjob rating.

**Folder**: `training_data_v2/{faction}/isolation/{unit_slug}/`
**Target**: 15 images per unit

### 2. Combat patrol group shots

Photos showing all units from a Combat Patrol box together — useful as multi-unit scene training data.

**Folder**: `training_data_v2/{faction}/combat_patrol/`
**Target**: 20 images per faction

---

## Scraper: eBay (`scrape_ebay.py`)

### How it works

1. Reads `units.json` for the unit list
2. For each unit, runs 2–3 search queries on eBay
3. Extracts listing IDs from the rendered page using regex (eBay renders via JavaScript — CSS selectors don't work)
4. Visits each listing page and extracts all carousel image URLs
5. Downloads images via plain `requests` (eBay CDN has no bot detection)
6. Applies quality filters and saves

### Why Playwright?

eBay's search results are JavaScript-rendered. CSS selectors return 0 results on the raw HTML. A real Chromium browser (Playwright) is required to load the page fully. The browser runs non-headless using the existing X display (`DISPLAY=:0`).

### Key technical details

- Listing ID extraction: `re.finditer(r'/itm/(\d{10,})', content)` on full page HTML
- Image URL normalisation: replaces `/s-l{size}.jpg` → `/s-l1600.jpg` for max resolution
- Session initialisation: visits eBay homepage first to establish cookies before searching
- Delays: 5–10s between searches, 3–6s between listing page loads

### Running it

```bash
source yolo_env/bin/activate
DISPLAY=:0 python3 scripts/scrape_ebay.py --all --limit 15
```

**Common flags:**

| Flag | Description |
|------|-------------|
| `--all` | Scrape all 20 factions |
| `--faction space_marines` | Single faction |
| `--unit "Intercessor Squad"` | Single unit only |
| `--limit 15` | Max images per unit (default: 15) |
| `--combat-patrol-only` | Only combat patrol group shots |
| `--dry-run` | Show what would be scraped without downloading |
| `--list-factions` | Print all faction slugs |
| `--list-units necrons` | Print all units for a faction |

---

## Scraper: DakkaDakka (`scrape_dakkadakka.py`)

[DakkaDakka](https://www.dakkadakka.com) is a Warhammer forum with 1.1M+ gallery images. The gallery is server-rendered HTML — no Playwright needed.

### How it works

1. Reads `units.json`
2. Searches the gallery with `sort1=1` (paintjob rating, best first) and `paintjoblow=4` (only well-painted models)
3. Parses result thumbnails from the HTML table
4. For each result, visits the gallery detail page to get the full-size image URL (thumbnails are only 320px; full-size is typically 900–3000px)
5. Downloads and saves

### Why visit the detail page?

Search result thumbnails (`_mb-` prefix) are 320×240 — below our 400px minimum. The detail page has the original upload at full resolution. This adds one extra HTTP request per image but is necessary for quality.

### Quality tiers

For each search query, the scraper tries two passes:
1. **Pass 1**: `paintjoblow=4` — only images rated ≥4/10 for paintjob quality
2. **Pass 2**: no paintjob filter — used only if a rare unit gets fewer than half its target from pass 1

### Key technical details

- Search endpoint: `GET /core/gallery-search.jsp?dq={query}&sort1=1&paintjoblow=4&start=0&skip=30`
- Pagination: `start` parameter in steps of 30
- Image ID extraction: `/(\d+)_(?:mb|th|tb)-` from thumbnail URLs
- Full-size URL: first `images.dakkadakka.com` img without `_th-`/`_mb-`/`_tb-` on detail page

### Running it

```bash
source yolo_env/bin/activate
python3 scripts/scrape_dakkadakka.py --all --limit 15
```

Same flags as the eBay scraper (`--faction`, `--unit`, `--limit`, `--dry-run`, `--list-factions`, `--list-units`).

---

## Shared Quality Filters

Both scrapers apply the same filters at download time:

| Filter | Value |
|--------|-------|
| Minimum resolution | 400 × 400 px |
| Minimum file size | 15 KB |
| Maximum file size | 20 MB |
| Maximum aspect ratio | 5:1 |
| Format | Saved as JPEG at quality 92 |
| MD5 deduplication | Checked against `duplicates.txt` |

Images that fail any filter are silently skipped (not saved, not logged).

---

## Resume Safety

Both scrapers are designed to be safely interrupted and restarted:

- **eBay**: tracks scraped listing IDs from `scrape_log.csv`. Already-scraped listings are skipped. Units with ≥ limit images are skipped entirely.
- **DakkaDakka**: tracks scraped DakkaDakka image IDs from `scrape_log.csv`. Same skip logic.

Restarting after a crash or `Ctrl+C` continues from where it left off.

---

## Output Structure

```
training_data_v2/
  {faction_slug}/
    isolation/
      {unit_slug}/
        {faction}_{unit}_ebay_{listing_id}_{idx}.jpg
        {faction}_{unit}_dakka_{image_id}_{idx}.jpg
    combat_patrol/
        {faction}_combat_patrol_ebay_{listing_id}_{idx}.jpg
        {faction}_combat_patrol_dakka_{image_id}_{idx}.jpg
  metadata/
    scrape_log.csv      ← one row per downloaded image
    duplicates.txt      ← MD5 hashes of all downloaded images
```

### scrape_log.csv columns

| Column | Description |
|--------|-------------|
| `filename` | Saved filename |
| `unit_name` | Unit name from units.json |
| `faction` | Faction slug |
| `image_type` | `isolation` or `combat_patrol` |
| `source_url` | Direct image URL |
| `page_url` | Listing/gallery page URL |
| `source_platform` | `ebay` or `dakkadakka` |
| `width_px` / `height_px` | Image dimensions |
| `file_hash` | MD5 of saved JPEG |
| `search_query` | The query that found it |
| `timestamp` | UTC ISO timestamp |

---

## Progress Dashboard (`scrape_progress.py`)

A self-contained HTTP server serving a live visual dashboard.

### Starting it

```bash
source yolo_env/bin/activate
python3 scripts/scrape_progress.py         # http://localhost:9090
python3 scripts/scrape_progress.py --port 8080
```

### What it shows

- **Summary strip**: total images collected, eBay count, DakkaDakka count, overall % toward target
- **Overall progress bar**: stacked amber (eBay) + purple (DakkaDakka)
- **Per-faction cards**: progress bar + `done units / total units` + `collected / target images`
- **Unit table** (click to expand): every unit with its own mini progress bar and source breakdown

### Browsing images

Click any unit row to open a gallery modal showing all images collected for that unit:
- Thumbnail grid with source badge (eBay / Dakka)
- Click any thumbnail → full-size lightbox
- Arrow keys or `←`/`→` buttons to navigate between images
- `Escape` to close

The dashboard auto-refreshes every 30 seconds. Images are served directly from `training_data_v2/` by the same server.

---

## Running Everything Together

```bash
# Terminal 1 — eBay scraper (needs X display for Playwright)
source yolo_env/bin/activate
DISPLAY=:0 nohup python3 -u scripts/scrape_ebay.py --all --limit 15 \
  > /tmp/scrape_ebay.log 2>&1 &

# Terminal 2 — DakkaDakka scraper
source yolo_env/bin/activate
nohup python3 -u scripts/scrape_dakkadakka.py --all --limit 15 \
  > /tmp/scrape_dakka.log 2>&1 &

# Terminal 3 — Progress dashboard
source yolo_env/bin/activate
python3 scripts/scrape_progress.py
# Open http://localhost:9090

# Watch logs live
tail -f /tmp/scrape_ebay.log
tail -f /tmp/scrape_dakka.log

# Count images at any time
find training_data_v2 -name "*.jpg" | wc -l
```

---

## Requirements

```
requests>=2.31.0
beautifulsoup4>=4.12.0
Pillow>=10.0.0
playwright (install via pip, then: playwright install chromium)
```

Install:
```bash
source yolo_env/bin/activate
pip install requests beautifulsoup4 Pillow playwright
playwright install chromium
```

The progress dashboard uses only Python stdlib — no extra dependencies.
