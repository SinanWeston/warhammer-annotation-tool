#!/usr/bin/env python3
"""
Scraping Progress Dashboard

Serves a live HTML dashboard at http://localhost:9090 showing image collection
progress per faction and unit. Click any unit to browse its collected images.
Auto-refreshes every 30 seconds.

Usage:
    python3 scripts/scrape_progress.py
    python3 scripts/scrape_progress.py --port 9090
"""

import argparse
import csv
import json
import mimetypes
import re
import http.server
import socketserver
from datetime import datetime
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent.parent
UNITS_JSON = BASE_DIR / "scripts" / "data" / "units.json"
OUTPUT_DIR = BASE_DIR / "training_data_v2"
SCRAPE_LOG = OUTPUT_DIR / "metadata" / "scrape_log.csv"

LIMIT_ISOLATION    = 15
LIMIT_COMBAT_PATROL = 20


# ─── Helpers ─────────────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[''']", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def count_images() -> dict:
    """Scan training_data_v2/ and count images by faction/unit-key/source."""
    counts: dict = defaultdict(lambda: defaultdict(lambda: {"ebay": 0, "dakkadakka": 0, "other": 0}))
    if not OUTPUT_DIR.exists():
        return counts
    for jpg in OUTPUT_DIR.rglob("*.jpg"):
        parts = jpg.relative_to(OUTPUT_DIR).parts
        if len(parts) < 2 or parts[0] == "metadata":
            continue
        faction = parts[0]
        name = jpg.stem
        source = "other"
        if "_ebay_" in name:
            source = "ebay"
        elif "_dakka_" in name:
            source = "dakkadakka"
        if len(parts) >= 4 and parts[1] == "isolation":
            key = f"isolation/{parts[2]}"
        elif len(parts) >= 3 and parts[1] == "combat_patrol":
            key = "combat_patrol"
        else:
            key = "other"
        counts[faction][key][source] += 1
    return counts


def load_log_stats() -> dict:
    stats = {"total": 0, "ebay": 0, "dakkadakka": 0, "other": 0, "first": None, "last": None}
    if not SCRAPE_LOG.exists():
        return stats
    with open(SCRAPE_LOG, newline="") as f:
        for row in csv.DictReader(f):
            stats["total"] += 1
            src = row.get("source_platform", "other")
            stats[src] = stats.get(src, 0) + 1
            ts = row.get("timestamp", "")
            if ts:
                if stats["first"] is None or ts < stats["first"]:
                    stats["first"] = ts
                if stats["last"] is None or ts > stats["last"]:
                    stats["last"] = ts
    return stats


def list_unit_images(faction: str, unit_key: str) -> list[dict]:
    """Return a list of {url, filename, source} for all images in a unit folder."""
    if unit_key == "combat_patrol":
        folder = OUTPUT_DIR / faction / "combat_patrol"
    else:
        slug = unit_key.removeprefix("isolation/")
        folder = OUTPUT_DIR / faction / "isolation" / slug

    if not folder.exists():
        return []

    images = []
    for jpg in sorted(folder.glob("*.jpg")):
        name = jpg.stem
        source = "other"
        if "_ebay_" in name:
            source = "ebay"
        elif "_dakka_" in name:
            source = "dakkadakka"
        # URL served by this dashboard
        rel = jpg.relative_to(OUTPUT_DIR)
        images.append({"url": f"/img/{rel.as_posix()}", "filename": jpg.name, "source": source})

    return images


# ─── HTML builder ─────────────────────────────────────────────────────────────

def build_html() -> str:
    with open(UNITS_JSON) as f:
        db = json.load(f)
    factions = db["factions"]

    counts    = count_images()
    log_stats = load_log_stats()

    total_images = sum(
        sum(src.values())
        for fd in counts.values()
        for src in fd.values()
    )
    total_target = sum(
        (LIMIT_COMBAT_PATROL if d.get("combat_patrol") else 0)
        + len(d.get("units", [])) * LIMIT_ISOLATION
        for d in factions.values()
    )
    pct_overall = min(100, round(100 * total_images / max(total_target, 1)))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Faction cards ────────────────────────────────────────────────────────
    faction_cards = []
    for faction_slug, faction_data in factions.items():
        faction_name = faction_data["name"]
        units        = faction_data.get("units", [])
        has_cp       = bool(faction_data.get("combat_patrol"))
        fc           = counts.get(faction_slug, {})

        f_ebay  = sum(v.get("ebay", 0)        for v in fc.values())
        f_dakka = sum(v.get("dakkadakka", 0)  for v in fc.values())
        f_total = sum(sum(v.values())          for v in fc.values())
        f_target = len(units) * LIMIT_ISOLATION + (LIMIT_COMBAT_PATROL if has_cp else 0)
        f_pct    = min(100, round(100 * f_total / max(f_target, 1)))

        bw_ebay  = min(100, round(100 * f_ebay  / max(f_target, 1)))
        bw_dakka = min(100, round(100 * f_dakka / max(f_target, 1)))

        done_units = sum(
            1 for u in units
            if sum(fc.get(f"isolation/{slugify(u['name'])}", {}).values()) >= LIMIT_ISOLATION
        )

        # Combat patrol row
        cp_row = ""
        if has_cp:
            cp  = fc.get("combat_patrol", {})
            cpt = sum(cp.values())
            cpe = cp.get("ebay", 0)
            cpd = cp.get("dakkadakka", 0)
            cp_status = "done" if cpt >= LIMIT_COMBAT_PATROL else ("partial" if cpt > 0 else "empty")
            cp_row = _unit_row(
                faction_slug, "combat_patrol",
                "⚔ Combat Patrol", "group",
                cpe, cpd, cpt, LIMIT_COMBAT_PATROL, cp_status
            )

        unit_rows = []
        for unit in units:
            u_name = unit["name"]
            u_slug = slugify(u_name)
            key    = f"isolation/{u_slug}"
            uc     = fc.get(key, {})
            u_ebay = uc.get("ebay", 0)
            u_dakka= uc.get("dakkadakka", 0)
            u_total= sum(uc.values())
            status = "done" if u_total >= LIMIT_ISOLATION else ("partial" if u_total > 0 else "empty")
            unit_rows.append(_unit_row(
                faction_slug, key,
                u_name, unit.get("category", ""),
                u_ebay, u_dakka, u_total, LIMIT_ISOLATION, status
            ))

        faction_cards.append(f"""
      <div class="faction-card" id="{faction_slug}">
        <div class="faction-header">
          <span class="faction-name">{faction_name}</span>
          <span class="faction-stats">{done_units}/{len(units)} units &nbsp;|&nbsp; {f_total:,}/{f_target:,} images</span>
          <span class="faction-pct">{f_pct}%</span>
        </div>
        <div class="faction-bar">
          <div class="bar-fill bar-ebay"  style="width:{bw_ebay}%"  title="eBay: {f_ebay}"></div>
          <div class="bar-fill bar-dakka" style="width:{bw_dakka}%" title="DakkaDakka: {f_dakka}"></div>
        </div>
        <details>
          <summary>{len(units)} units · click to expand</summary>
          <table class="unit-table">
            <thead><tr><th>Unit</th><th>Type</th><th>Progress</th><th>Count</th><th>Sources</th></tr></thead>
            <tbody>
              {cp_row}
              {"".join(unit_rows)}
            </tbody>
          </table>
        </details>
      </div>""")

    factions_html = "\n".join(faction_cards)
    ebay_pct  = round(100 * log_stats["ebay"]        / max(log_stats["total"], 1))
    dakka_pct = round(100 * log_stats["dakkadakka"]  / max(log_stats["total"], 1))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="30">
  <title>Battle Scanner — Scrape Progress</title>
  <style>
    *{{ box-sizing:border-box; margin:0; padding:0; }}
    body{{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
          background:#0f1117; color:#e2e8f0; min-height:100vh; padding:24px; }}
    h1{{ font-size:1.4rem; font-weight:700; color:#f8fafc; letter-spacing:.05em; text-transform:uppercase; }}
    .subtitle{{ color:#64748b; font-size:.82rem; margin-top:2px; }}
    .header{{ display:flex; justify-content:space-between; align-items:flex-end;
              border-bottom:1px solid #1e293b; padding-bottom:16px; margin-bottom:24px; }}
    .refresh-note{{ font-size:.75rem; color:#475569; }}

    .summary{{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:24px; }}
    .stat-box{{ background:#1e293b; border-radius:10px; padding:16px; }}
    .stat-label{{ font-size:.72rem; color:#64748b; text-transform:uppercase; letter-spacing:.08em; }}
    .stat-value{{ font-size:1.8rem; font-weight:700; margin-top:4px; }}
    .stat-sub{{ font-size:.75rem; color:#94a3b8; margin-top:2px; }}
    .v-total{{ color:#38bdf8; }} .v-ebay{{ color:#f59e0b; }}
    .v-dakka{{ color:#a78bfa; }} .v-pct{{ color:#34d399; }}

    .overall-bar-wrap{{ background:#1e293b; border-radius:10px; padding:16px; margin-bottom:24px; }}
    .overall-label{{ font-size:.8rem; color:#94a3b8; margin-bottom:8px; }}
    .big-bar{{ height:20px; background:#0f172a; border-radius:6px; overflow:hidden; display:flex; }}
    .legend{{ display:flex; gap:20px; margin-top:8px; font-size:.75rem; }}
    .legend-dot{{ width:10px; height:10px; border-radius:50%; display:inline-block; margin-right:5px; vertical-align:middle; }}
    .dot-ebay{{ background:#f59e0b; }} .dot-dakka{{ background:#a78bfa; }}

    .factions{{ display:grid; grid-template-columns:repeat(auto-fill,minmax(480px,1fr)); gap:16px; }}
    .faction-card{{ background:#1e293b; border-radius:12px; overflow:hidden; border:1px solid #263347; }}
    .faction-header{{ display:flex; align-items:center; padding:14px 16px 10px; gap:12px; }}
    .faction-name{{ font-weight:600; font-size:.95rem; flex:1; }}
    .faction-stats{{ font-size:.72rem; color:#64748b; }}
    .faction-pct{{ font-weight:700; font-size:1rem; color:#34d399; min-width:36px; text-align:right; }}
    .faction-bar{{ height:6px; background:#0f172a; display:flex; margin:0 16px; border-radius:3px; overflow:hidden; }}

    details{{ padding:0; }}
    summary{{ padding:10px 16px; font-size:.78rem; color:#64748b; cursor:pointer; list-style:none; border-top:1px solid #263347; }}
    summary::-webkit-details-marker{{ display:none; }}
    summary::before{{ content:"▶ "; font-size:.6rem; }}
    details[open] summary::before{{ content:"▼ "; }}

    .unit-table{{ width:100%; border-collapse:collapse; font-size:.78rem; }}
    .unit-table thead th{{ padding:6px 12px; text-align:left; color:#475569; font-weight:600;
                           font-size:.7rem; text-transform:uppercase; border-bottom:1px solid #263347; }}
    .unit-row td{{ padding:5px 12px; border-bottom:1px solid #162032; }}
    .unit-row:last-child td{{ border-bottom:none; }}
    .unit-row.done{{ background:#0d1f17; }} .unit-row.partial{{ background:#12161e; }}
    .unit-row.empty{{ background:#0f1117; }} .unit-row.cp-row{{ background:#12111a; }}
    .unit-row{{ cursor:pointer; transition:background .15s; }}
    .unit-row:hover{{ background:#1a2540 !important; }}
    .unit-name{{ color:#cbd5e1; font-weight:500; }}
    .unit-cat{{ color:#475569; font-size:.7rem; }}
    .unit-bar-cell{{ width:140px; }}
    .unit-bar{{ height:8px; background:#0f172a; border-radius:4px; overflow:hidden; display:flex; }}
    .unit-count{{ color:#94a3b8; text-align:right; white-space:nowrap; }}
    .unit-sources{{ text-align:right; white-space:nowrap; }}
    .src-ebay{{ color:#f59e0b; font-size:.7rem; }} .src-dakka{{ color:#a78bfa; font-size:.7rem; }}
    .bar-fill{{ height:100%; transition:width .3s; }}
    .bar-ebay{{ background:#f59e0b; }} .bar-dakka{{ background:#a78bfa; }}

    /* ── Gallery modal ──────────────────────────────────────────────────── */
    #modal-overlay{{
      display:none; position:fixed; inset:0; background:rgba(0,0,0,.85);
      z-index:1000; overflow-y:auto; padding:24px;
    }}
    #modal-overlay.open{{ display:block; }}
    #modal-box{{
      background:#1e293b; border-radius:16px; max-width:1100px; margin:0 auto;
      padding:24px; border:1px solid #334155;
    }}
    #modal-header{{
      display:flex; justify-content:space-between; align-items:flex-start;
      margin-bottom:20px;
    }}
    #modal-title{{ font-size:1.1rem; font-weight:700; color:#f8fafc; }}
    #modal-subtitle{{ font-size:.78rem; color:#64748b; margin-top:4px; }}
    #modal-close{{
      background:none; border:1px solid #334155; color:#94a3b8; border-radius:8px;
      padding:6px 14px; cursor:pointer; font-size:.85rem; flex-shrink:0;
    }}
    #modal-close:hover{{ background:#334155; color:#f8fafc; }}
    #modal-loading{{ text-align:center; color:#64748b; padding:40px; font-size:.9rem; }}
    #modal-empty{{ text-align:center; color:#64748b; padding:40px; font-size:.9rem; }}

    .img-grid{{
      display:grid;
      grid-template-columns:repeat(auto-fill, minmax(200px, 1fr));
      gap:10px;
    }}
    .img-card{{
      background:#0f172a; border-radius:10px; overflow:hidden;
      border:1px solid #263347; cursor:pointer; transition:transform .15s, border-color .15s;
    }}
    .img-card:hover{{ transform:scale(1.02); border-color:#38bdf8; }}
    .img-card img{{
      width:100%; aspect-ratio:4/3; object-fit:cover; display:block;
      background:#162032;
    }}
    .img-card-label{{
      padding:6px 8px; font-size:.68rem; color:#64748b;
      display:flex; justify-content:space-between; align-items:center;
    }}
    .img-card-label .src-badge{{
      font-size:.62rem; padding:1px 5px; border-radius:4px; font-weight:600;
    }}
    .src-badge.ebay{{ background:#78350f; color:#fbbf24; }}
    .src-badge.dakkadakka{{ background:#3b0764; color:#c4b5fd; }}
    .src-badge.other{{ background:#1e293b; color:#94a3b8; }}

    /* ── Lightbox ────────────────────────────────────────────────────────── */
    #lightbox{{
      display:none; position:fixed; inset:0; background:rgba(0,0,0,.95);
      z-index:2000; align-items:center; justify-content:center;
    }}
    #lightbox.open{{ display:flex; }}
    #lightbox img{{
      max-width:90vw; max-height:90vh; object-fit:contain; border-radius:8px;
    }}
    #lightbox-close{{
      position:fixed; top:20px; right:24px; background:none; border:none;
      color:#94a3b8; font-size:2rem; cursor:pointer; line-height:1;
    }}
    #lightbox-close:hover{{ color:#f8fafc; }}
    #lightbox-caption{{
      position:fixed; bottom:20px; left:0; right:0; text-align:center;
      font-size:.8rem; color:#64748b;
    }}
    #lightbox-nav{{
      position:fixed; top:50%; transform:translateY(-50%);
      width:100%; display:flex; justify-content:space-between; padding:0 16px;
      pointer-events:none;
    }}
    .lb-btn{{
      background:rgba(255,255,255,.1); border:none; color:#e2e8f0;
      font-size:1.8rem; padding:8px 16px; border-radius:8px; cursor:pointer;
      pointer-events:all; transition:background .15s;
    }}
    .lb-btn:hover{{ background:rgba(255,255,255,.2); }}
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>⚔ Battle Scanner — Scrape Progress</h1>
      <div class="subtitle">training_data_v2 · {len(factions)} factions · auto-refreshes every 30s · click any unit to browse images</div>
    </div>
    <div class="refresh-note">Last built: {now}</div>
  </div>

  <div class="summary">
    <div class="stat-box">
      <div class="stat-label">Total Images</div>
      <div class="stat-value v-total">{total_images:,}</div>
      <div class="stat-sub">of {total_target:,} target</div>
    </div>
    <div class="stat-box">
      <div class="stat-label">eBay</div>
      <div class="stat-value v-ebay">{log_stats['ebay']:,}</div>
      <div class="stat-sub">{ebay_pct}% of collected</div>
    </div>
    <div class="stat-box">
      <div class="stat-label">DakkaDakka</div>
      <div class="stat-value v-dakka">{log_stats['dakkadakka']:,}</div>
      <div class="stat-sub">{dakka_pct}% of collected</div>
    </div>
    <div class="stat-box">
      <div class="stat-label">Overall Progress</div>
      <div class="stat-value v-pct">{pct_overall}%</div>
      <div class="stat-sub">{total_images:,} / {total_target:,}</div>
    </div>
  </div>

  <div class="overall-bar-wrap">
    <div class="overall-label">Overall collection progress</div>
    <div class="big-bar">
      <div class="bar-ebay"  style="width:{min(100,round(100*log_stats['ebay']/max(total_target,1)))}%"></div>
      <div class="bar-dakka" style="width:{min(100,round(100*log_stats['dakkadakka']/max(total_target,1)))}%"></div>
    </div>
    <div class="legend">
      <span><span class="legend-dot dot-ebay"></span>eBay ({log_stats['ebay']:,} images)</span>
      <span><span class="legend-dot dot-dakka"></span>DakkaDakka ({log_stats['dakkadakka']:,} images)</span>
    </div>
  </div>

  <div class="factions">
    {factions_html}
  </div>

  <!-- Gallery modal -->
  <div id="modal-overlay">
    <div id="modal-box">
      <div id="modal-header">
        <div>
          <div id="modal-title"></div>
          <div id="modal-subtitle"></div>
        </div>
        <button id="modal-close" onclick="closeModal()">✕ Close</button>
      </div>
      <div id="modal-body">
        <div id="modal-loading">Loading images…</div>
      </div>
    </div>
  </div>

  <!-- Lightbox -->
  <div id="lightbox" onclick="closeLightbox()">
    <button id="lightbox-close" onclick="closeLightbox()">✕</button>
    <div id="lightbox-nav">
      <button class="lb-btn" onclick="event.stopPropagation(); lbStep(-1)">&#8249;</button>
      <button class="lb-btn" onclick="event.stopPropagation(); lbStep(1)">&#8250;</button>
    </div>
    <img id="lightbox-img" src="" alt="" onclick="event.stopPropagation()">
    <div id="lightbox-caption"></div>
  </div>

  <script>
    let lbImages = [];
    let lbIndex  = 0;

    function openGallery(faction, unitKey, unitName, count) {{
      const overlay = document.getElementById('modal-overlay');
      const body    = document.getElementById('modal-body');
      document.getElementById('modal-title').textContent = unitName;
      document.getElementById('modal-subtitle').textContent =
        faction.replaceAll('_',' ') + ' · ' + count + ' images collected';
      body.innerHTML = '<div id="modal-loading">Loading images…</div>';
      overlay.classList.add('open');

      fetch('/api/images/' + faction + '/' + encodeURIComponent(unitKey))
        .then(r => r.json())
        .then(images => {{
          lbImages = images;
          lbIndex  = 0;
          if (!images.length) {{
            body.innerHTML = '<div id="modal-empty">No images collected yet for this unit.</div>';
            return;
          }}
          const grid = document.createElement('div');
          grid.className = 'img-grid';
          images.forEach((img, i) => {{
            const card = document.createElement('div');
            card.className = 'img-card';
            card.onclick = (e) => {{ e.stopPropagation(); openLightbox(i); }};
            const srcLabel = img.source === 'ebay' ? 'eBay'
                           : img.source === 'dakkadakka' ? 'Dakka' : img.source;
            card.innerHTML = `
              <img src="${{img.url}}" alt="${{img.filename}}" loading="lazy">
              <div class="img-card-label">
                <span title="${{img.filename}}">${{img.filename.slice(0,28)}}</span>
                <span class="src-badge ${{img.source}}">${{srcLabel}}</span>
              </div>`;
            grid.appendChild(card);
          }});
          body.innerHTML = '';
          body.appendChild(grid);
        }})
        .catch(() => {{
          body.innerHTML = '<div id="modal-empty">Failed to load images.</div>';
        }});
    }}

    function closeModal() {{
      document.getElementById('modal-overlay').classList.remove('open');
    }}

    document.getElementById('modal-overlay').addEventListener('click', function(e) {{
      if (e.target === this) closeModal();
    }});

    function openLightbox(i) {{
      lbIndex = i;
      const lb  = document.getElementById('lightbox');
      const img = document.getElementById('lightbox-img');
      const cap = document.getElementById('lightbox-caption');
      img.src = lbImages[i].url;
      cap.textContent = lbImages[i].filename + '  (' + (i+1) + ' / ' + lbImages.length + ')';
      lb.classList.add('open');
    }}

    function closeLightbox() {{
      document.getElementById('lightbox').classList.remove('open');
    }}

    function lbStep(dir) {{
      lbIndex = (lbIndex + dir + lbImages.length) % lbImages.length;
      openLightbox(lbIndex);
    }}

    document.addEventListener('keydown', e => {{
      const lb = document.getElementById('lightbox');
      if (lb.classList.contains('open')) {{
        if (e.key === 'ArrowRight') lbStep(1);
        if (e.key === 'ArrowLeft')  lbStep(-1);
        if (e.key === 'Escape')     closeLightbox();
      }} else {{
        if (e.key === 'Escape') closeModal();
      }}
    }});
  </script>
</body>
</html>"""


def _unit_row(faction, unit_key, name, cat, u_ebay, u_dakka, u_total, limit, status):
    bw_e = min(100, round(100 * u_ebay  / max(limit, 1)))
    bw_d = min(100, round(100 * u_dakka / max(limit, 1)))
    cp_class = "cp-row " if unit_key == "combat_patrol" else ""
    return f"""
              <tr class="unit-row {cp_class}{status}"
                  onclick="openGallery('{faction}','{unit_key}','{name.replace("'","\\'")}',{u_total})">
                <td class="unit-name">{name}</td>
                <td class="unit-cat">{cat}</td>
                <td class="unit-bar-cell">
                  <div class="unit-bar">
                    <div class="bar-fill bar-ebay"  style="width:{bw_e}%"></div>
                    <div class="bar-fill bar-dakka" style="width:{bw_d}%"></div>
                  </div>
                </td>
                <td class="unit-count">{u_total}/{limit}</td>
                <td class="unit-sources">
                  <span class="src-ebay">{u_ebay}e</span>
                  <span class="src-dakka">{u_dakka}d</span>
                </td>
              </tr>"""


# ─── HTTP server ──────────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]

        # ── /api/images/{faction}/{unit_key} ─────────────────────────────
        if path.startswith("/api/images/"):
            rest    = path.removeprefix("/api/images/")
            parts   = rest.split("/", 1)
            if len(parts) == 2:
                faction, unit_key = parts[0], parts[1]
                images = list_unit_images(faction, unit_key)
                data   = json.dumps(images).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self._404()
            return

        # ── /img/{relative path inside training_data_v2} ─────────────────
        if path.startswith("/img/"):
            rel  = path.removeprefix("/img/")
            file = OUTPUT_DIR / rel
            if file.exists() and file.is_file() and file.suffix.lower() in (".jpg", ".jpeg", ".png"):
                data = file.read_bytes()
                mime = mimetypes.guess_type(str(file))[0] or "image/jpeg"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "max-age=3600")
                self.end_headers()
                self.wfile.write(data)
            else:
                self._404()
            return

        # ── / → dashboard ────────────────────────────────────────────────
        if path in ("/", ""):
            html = build_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        self._404()

    def _404(self):
        self.send_response(404)
        self.end_headers()

    def log_message(self, fmt, *args):
        pass  # suppress request noise


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scraping progress dashboard")
    parser.add_argument("--port", type=int, default=9090)
    args = parser.parse_args()

    print(f"Dashboard: http://localhost:{args.port}")
    print("Click any unit row to browse its images. Ctrl+C to stop.")

    with socketserver.TCPServer(("", args.port), Handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
