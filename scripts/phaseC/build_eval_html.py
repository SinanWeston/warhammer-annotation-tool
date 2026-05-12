"""Render `data/scene_benchmark/eval_200.json` as a browsable HTML index.

Reads the frozen manifest + per-image annotation JSONs, emits
`data/scene_benchmark/index.html` — bbox-overlaid thumbnails grouped by
bucket (single / sparse / medium / crowded). Pure read-only review;
images are loaded via file:// URIs so no server is required.

Usage:
    yolo_env/bin/python scripts/phaseC/build_eval_html.py
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "data/scene_benchmark/eval_200.json"
ANN_DIR = REPO_ROOT / "backend/training_data_annotations"
OUT = REPO_ROOT / "data/scene_benchmark/index.html"

BUCKET_ORDER = ["single", "sparse", "medium", "crowded"]
THUMB_WIDTH = 320  # px, render width — bbox overlay scales from pixel coords


def load_annotation(image_id: str) -> dict | None:
    p = ANN_DIR / f"{image_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def render_card(item: dict) -> str:
    image_id = item["imageId"]
    img_path = item["imagePath"]
    img_w = item["width"] or 1
    img_h = item["height"] or 1
    faction = item["faction"]
    source = item["source"]
    n_boxes = item["n_boxes"]

    ann = load_annotation(image_id)
    boxes = ann.get("annotations", []) if ann else []

    # SVG overlay sized to the natural image; CSS scales it to thumb width.
    rects = []
    labels = []
    for b in boxes:
        bb = b.get("modelBbox") or b.get("baseBbox") or {}
        x, y, w, h = (bb.get("x", 0), bb.get("y", 0), bb.get("width", 0), bb.get("height", 0))
        unit = b.get("unit_slug") or b.get("classLabel") or "?"
        rects.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'fill="none" stroke="#22d3ee" stroke-width="{max(2, img_w/200):.1f}" />'
        )
        labels.append(
            f'<text x="{x:.1f}" y="{max(y - 6, 14):.1f}" '
            f'fill="#22d3ee" font-size="{max(12, img_w/40):.0f}" '
            f'font-family="ui-sans-serif, system-ui">{escape(str(unit))}</text>'
        )

    svg = (
        f'<svg viewBox="0 0 {img_w} {img_h}" preserveAspectRatio="none" '
        f'style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none">'
        + "".join(rects)
        + "".join(labels)
        + "</svg>"
    )

    return (
        f'<figure class="card" data-faction="{escape(faction)}" data-source="{escape(source)}">'
        f'<div class="thumb">'
        f'<img loading="lazy" src="file://{escape(img_path)}" alt="{escape(image_id)}" />'
        f"{svg}"
        f"</div>"
        f"<figcaption>"
        f'<div class="cap-id">{escape(image_id)}</div>'
        f'<div class="cap-meta">'
        f'<span class="faction">{escape(faction)}</span> · '
        f'<span class="source">{escape(source)}</span> · '
        f'<span class="boxes">{n_boxes} box{"es" if n_boxes != 1 else ""}</span>'
        f"</div>"
        f"</figcaption>"
        f"</figure>"
    )


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    images = manifest["images"]

    by_bucket: dict[str, list[dict]] = {b: [] for b in BUCKET_ORDER}
    for im in images:
        by_bucket.setdefault(im["bucket"], []).append(im)

    sections = []
    for bucket in BUCKET_ORDER:
        items = sorted(by_bucket.get(bucket, []), key=lambda x: (x["faction"], x["imageId"]))
        cards = "\n".join(render_card(i) for i in items)
        sections.append(
            f'<section id="bucket-{bucket}">'
            f"<h2>{bucket} <small>({len(items)})</small></h2>"
            f'<div class="grid">{cards}</div>'
            f"</section>"
        )

    head_nav = " · ".join(
        f'<a href="#bucket-{b}">{b} ({len(by_bucket.get(b, []))})</a>' for b in BUCKET_ORDER
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Phase C · Frozen scene benchmark ({len(images)})</title>
<style>
  body {{ margin: 0; background: #0b0b0b; color: #eee;
         font-family: ui-sans-serif, system-ui, sans-serif; }}
  header {{ position: sticky; top: 0; z-index: 10;
            background: rgba(11,11,11,.95); backdrop-filter: blur(6px);
            padding: 1rem 1.5rem; border-bottom: 1px solid #222; }}
  header h1 {{ margin: 0 0 .25rem; font-size: 1.1rem; }}
  header nav a {{ color: #22d3ee; margin-right: .25rem; text-decoration: none; }}
  header .meta {{ color: #888; font-size: .85rem; margin-top: .25rem; }}
  section {{ padding: 1rem 1.5rem 2rem; }}
  section h2 {{ font-size: 1rem; color: #ccc; margin: .25rem 0 .75rem;
                text-transform: capitalize; }}
  section h2 small {{ color: #666; font-weight: 400; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax({THUMB_WIDTH}px, 1fr)); gap: 1rem; }}
  .card {{ margin: 0; background: #161616; border: 1px solid #222; border-radius: 6px; overflow: hidden; }}
  .thumb {{ position: relative; aspect-ratio: 1 / 1; background: #000; overflow: hidden; }}
  .thumb img {{ width: 100%; height: 100%; object-fit: contain; display: block; }}
  figcaption {{ padding: .5rem .65rem; }}
  .cap-id {{ font-size: .72rem; color: #777; word-break: break-all; }}
  .cap-meta {{ font-size: .8rem; margin-top: .2rem; }}
  .cap-meta .faction {{ color: #a855f7; }}
  .cap-meta .source  {{ color: #fbbf24; }}
  .cap-meta .boxes   {{ color: #888; }}
</style>
</head>
<body>
<header>
  <h1>Phase C · Frozen scene benchmark — {len(images)} images</h1>
  <nav>{head_nav}</nav>
  <div class="meta">
    seed={manifest.get("seed")} · frozen_at={manifest.get("frozen_at")} ·
    source: <code>{escape(manifest.get("source_annotation_dir", ""))}</code>
  </div>
</header>
{"".join(sections)}
</body>
</html>
"""

    OUT.write_text(html)
    print(f"Wrote {OUT} ({len(images)} images across {len(by_bucket)} buckets)")


if __name__ == "__main__":
    main()
