#!/usr/bin/env python3
"""
Shared utilities for all Battle Scanner scrapers.

Imported by reddit_collector.py, flickr_collector.py, youtube_collector.py,
clip_scorer.py, and deduplicate.py.
"""

import csv
import hashlib
import random
import re
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image

# ─── Path Constants ───────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
UNITS_JSON = BASE_DIR / "scripts" / "data" / "units.json"
OUTPUT_DIR = BASE_DIR / "training_data_v2"
METADATA_DIR = OUTPUT_DIR / "metadata"
SCRAPE_LOG = METADATA_DIR / "scrape_log.csv"
DUPLICATES_FILE = METADATA_DIR / "duplicates.txt"

PATH_CONSTANTS = {
    "BASE_DIR": BASE_DIR,
    "UNITS_JSON": UNITS_JSON,
    "OUTPUT_DIR": OUTPUT_DIR,
    "METADATA_DIR": METADATA_DIR,
    "SCRAPE_LOG": SCRAPE_LOG,
    "DUPLICATES_FILE": DUPLICATES_FILE,
}

JPEG_QUALITY = 92

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]


# ─── String Helpers ───────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[''']", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


# ─── Hash / Dedup ─────────────────────────────────────────────────────────────

def compute_md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def load_known_hashes() -> set:
    hashes = set()
    if DUPLICATES_FILE.exists():
        with open(DUPLICATES_FILE) as f:
            for line in f:
                h = line.strip()
                if h:
                    hashes.add(h)
    return hashes


def save_hash(file_hash: str):
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DUPLICATES_FILE, "a") as f:
        f.write(file_hash + "\n")


# ─── CSV Logging ──────────────────────────────────────────────────────────────

CSV_COLUMNS = [
    "filename", "unit_name", "faction", "image_type",
    "source_url", "page_url", "source_platform",
    "width_px", "height_px", "file_hash",
    "search_query", "timestamp",
]


def init_csv():
    """Create scrape_log.csv with header if it doesn't exist."""
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SCRAPE_LOG.exists():
        with open(SCRAPE_LOG, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)


def log_image(row: dict):
    """Append one row to scrape_log.csv. Column order matches CSV_COLUMNS exactly."""
    with open(SCRAPE_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            row["filename"], row["unit_name"], row["faction"],
            row["image_type"], row["source_url"], row["page_url"],
            row["source_platform"], row["width_px"], row["height_px"],
            row["file_hash"], row["search_query"], row["timestamp"],
        ])


# ─── Timing ───────────────────────────────────────────────────────────────────

def rand_delay(lo: float, hi: float):
    time.sleep(random.uniform(lo, hi))


# ─── Image Quality Check ──────────────────────────────────────────────────────

def quality_check_bytes(
    data: bytes,
    known_hashes: set,
    min_w: int = 400,
    min_h: int = 400,
    min_size: int = 15360,       # 15 KB
    max_size: int = 20971520,    # 20 MB
    max_ratio: float = 5.0,
    blur_threshold: float | None = None,
) -> tuple[bytes, int, int, str] | None:
    """
    Validate raw image bytes.

    Returns (jpeg_bytes, width, height, md5_hash) if the image passes all
    quality checks, or None if it fails.

    Checks in order:
    1. File size (min_size / max_size)
    2. MD5 dedup against known_hashes
    3. PIL decode + verify (corrupt images)
    4. Minimum dimensions
    5. Aspect ratio
    6. Optional Laplacian blur check (requires opencv-python)
    7. Convert to JPEG RGB, recompute hash, final dedup check
    """
    if len(data) < min_size or len(data) > max_size:
        return None

    file_hash = compute_md5(data)
    if file_hash in known_hashes:
        return None

    try:
        img = Image.open(BytesIO(data))
        img.verify()
        img = Image.open(BytesIO(data))  # reopen after verify()
        w, h = img.size
    except Exception:
        return None

    if w < min_w or h < min_h:
        return None

    if max(w, h) / max(min(w, h), 1) > max_ratio:
        return None

    if blur_threshold is not None:
        try:
            import cv2
            import numpy as np
            arr = np.array(img.convert("RGB"))
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            fm = cv2.Laplacian(gray, cv2.CV_64F).var()
            if fm < blur_threshold:
                return None
        except ImportError:
            pass  # cv2 not available, skip blur check

    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    jpg_data = buf.getvalue()

    # Recompute hash on the normalised JPEG
    final_hash = compute_md5(jpg_data)
    if final_hash in known_hashes:
        return None

    return (jpg_data, w, h, final_hash)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
