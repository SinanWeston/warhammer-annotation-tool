#!/usr/bin/env python3
"""
Lightweight review server — shows each image with faction + cosine score,
user clicks Yes (miniature) or No (not a mini). Votes saved to
state/review_votes.json incrementally.

Usage:
    yolo_env/bin/python3 scripts/warhammer_community/review_server.py
    # Opens http://localhost:8765 in browser
"""

from __future__ import annotations

import csv
import json
import sys
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
IMAGES_ROOT = HERE / "images"
STATE_DIR = HERE / "state"
VALIDATION_CSV = STATE_DIR / "validation.csv"
VOTES_FILE = STATE_DIR / "review_votes.json"
REVIEW_HTML = HERE / "review_tool.html"

PORT = 8765


def _load_images() -> list[dict]:
    """Load images above threshold from validation.csv, sorted by cosine ascending
    (hardest first — gets the borderline cases reviewed first)."""
    if not VALIDATION_CSV.exists():
        return []
    rows = []
    for r in csv.DictReader(VALIDATION_CSV.open()):
        cos = float(r["dino_cosine"])
        if cos < 0.71:
            continue
        path = r["path"]
        if not Path(path).exists():
            continue
        rows.append({
            "path": path,
            "faction": r["faction"],
            "article": r["article_slug"],
            "cosine": cos,
        })
    rows.sort(key=lambda x: x["cosine"])
    return rows


def _load_votes() -> dict:
    if VOTES_FILE.exists():
        return json.loads(VOTES_FILE.read_text())
    return {}


def _save_vote(path: str, vote: str) -> None:
    votes = _load_votes()
    votes[path] = vote
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    VOTES_FILE.write_text(json.dumps(votes, indent=2))


class ReviewHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/" or parsed.path == "/index.html":
            self._serve_file(REVIEW_HTML, "text/html")

        elif parsed.path == "/api/images":
            images = _load_images()
            self._json_response(images)

        elif parsed.path == "/api/votes":
            votes = _load_votes()
            self._json_response(votes)

        elif parsed.path == "/image":
            qs = parse_qs(parsed.query)
            img_path = qs.get("path", [""])[0]
            p = Path(img_path)
            if p.exists() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                self._serve_file(p, f"image/{p.suffix.lstrip('.')}")
            else:
                self.send_error(404)

        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/vote":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            _save_vote(body["path"], body["vote"])
            self._json_response({"ok": True})
        else:
            self.send_error(404)

    def _json_response(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path, content_type: str):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass  # suppress request logs


def main():
    images = _load_images()
    votes = _load_votes()
    remaining = sum(1 for img in images if img["path"] not in votes)
    print(f"Images to review: {len(images)} ({remaining} unvoted)")
    print(f"Votes so far: {len(votes)}")
    print(f"\nStarting review server at http://localhost:{PORT}")
    print("Keyboard: Y = miniature, N = not a mini, S = skip, ← = go back")
    print("Press Ctrl+C to stop.\n")

    webbrowser.open(f"http://localhost:{PORT}")
    server = HTTPServer(("", PORT), ReviewHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\nSaved {len(_load_votes())} votes to {VOTES_FILE}")


if __name__ == "__main__":
    main()
