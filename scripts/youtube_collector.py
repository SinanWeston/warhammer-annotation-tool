#!/usr/bin/env python3
"""
YouTube Battle Report Frame Extractor for Battle Scanner Training Data

Downloads YouTube videos via yt-dlp, detects scene changes with PySceneDetect,
and saves middle frames from each scene as training images.

Prerequisites (in yolo_env):
    pip install yt-dlp "scenedetect[opencv]"
    opencv-python is already in yolo_env

Usage:
    python scripts/youtube_collector.py --all-channels --limit 20
    python scripts/youtube_collector.py --channel https://www.youtube.com/@PlayOnTabletop --channel-slug play_on_tabletop
    python scripts/youtube_collector.py --video "https://youtu.be/abc123" --channel-slug manual --frame-limit 30
    python scripts/youtube_collector.py --playlist "https://www.youtube.com/playlist?list=..." --channel-slug custom
    python scripts/youtube_collector.py --list-channels
    python scripts/youtube_collector.py --all-channels --limit 5 --dry-run
"""

import argparse
import csv
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scraper_utils import (
    OUTPUT_DIR, SCRAPE_LOG,
    compute_md5, init_csv, load_known_hashes, log_image,
    now_iso, quality_check_bytes, save_hash,
)

# ─── Channel Definitions ──────────────────────────────────────────────────────

CHANNELS = {
    "play_on_tabletop": "https://www.youtube.com/@PlayOnTabletop/videos",
    "tabletop_titans":  "https://www.youtube.com/@TabletopTitans/videos",
    "miniwargaming":    "https://www.youtube.com/@MiniWarGaming/videos",
    "winters_seo":      "https://www.youtube.com/@WintersSEO/videos",
    "tabletop_tactics": "https://www.youtube.com/@tabletoptactics/videos",
}

BATTLE_KEYWORDS = ["battle report", "vs ", "batrep", "army showcase", "game"]

FACTION = "multi_faction"
PLATFORM = "youtube"

FALLBACK_FRAME_INTERVAL = 30   # extract every Nth frame if scene detection yields <3 scenes
SCENE_THRESHOLD = 27.0


# ─── Resumability ─────────────────────────────────────────────────────────────

def load_scraped_video_ids() -> set:
    ids = set()
    if not SCRAPE_LOG.exists():
        return ids
    with open(SCRAPE_LOG, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("source_platform") == PLATFORM:
                url = row.get("page_url", "")
                # youtube.com/watch?v=ID
                m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", url)
                if m:
                    ids.add(m.group(1))
                # youtu.be/ID
                m2 = re.search(r"youtu\.be/([A-Za-z0-9_-]{11})", url)
                if m2:
                    ids.add(m2.group(1))
    return ids


# ─── Helpers ─────────────────────────────────────────────────────────────────

def is_battle_report(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in BATTLE_KEYWORDS)


def get_video_id(url: str) -> str | None:
    m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", url)
    if m:
        return m.group(1)
    m2 = re.search(r"youtu\.be/([A-Za-z0-9_-]{11})", url)
    if m2:
        return m2.group(1)
    return None


def list_channel_videos(channel_url: str, limit: int) -> list[dict]:
    """Return up to `limit` video dicts (id, title, webpage_url) from a channel."""
    try:
        import yt_dlp
    except ImportError:
        print("ERROR: yt-dlp is not installed. Run: pip install yt-dlp")
        sys.exit(1)

    ydl_opts = {
        "quiet": True,
        "extract_flat": "in_playlist",
        "playlistend": limit * 5,
        "ignoreerrors": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
            entries = info.get("entries", []) or []
            return [
                {
                    "id": e.get("id", ""),
                    "title": e.get("title", ""),
                    "webpage_url": e.get("url") or e.get("webpage_url") or f"https://www.youtube.com/watch?v={e.get('id','')}",
                }
                for e in entries
                if e.get("id")
            ]
    except Exception as e:
        print(f"  ERROR listing channel videos: {e}")
        return []


def download_video(video_url: str, out_dir: str) -> str | None:
    """Download video at ≤720p to out_dir. Returns path to downloaded file or None."""
    try:
        import yt_dlp
    except ImportError:
        print("ERROR: yt-dlp is not installed.")
        sys.exit(1)

    ydl_opts = {
        "quiet": True,
        "format": "best[height<=720][ext=mp4]/best[height<=720]/best[ext=mp4]/best",
        "outtmpl": str(Path(out_dir) / "%(id)s.%(ext)s"),
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            fname = ydl.prepare_filename(info)
            # yt-dlp may change extension after merge
            p = Path(fname)
            if p.exists():
                return str(p)
            # Try .mp4 fallback
            mp4 = p.with_suffix(".mp4")
            if mp4.exists():
                return str(mp4)
            # Search for any video file in out_dir
            for f in Path(out_dir).iterdir():
                if f.suffix in (".mp4", ".mkv", ".webm"):
                    return str(f)
        return None
    except Exception as e:
        print(f"  ERROR downloading video: {e}")
        return None


def extract_scene_frames(video_path: str, frame_limit: int) -> list[tuple[bytes, int, int]]:
    """
    Detect scene changes and extract the middle frame from each scene.
    Returns list of (jpeg_bytes, width, height).
    Falls back to every-Nth-frame if PySceneDetect finds < 3 scenes.
    """
    try:
        from scenedetect import detect, ContentDetector
    except ImportError:
        print("ERROR: scenedetect is not installed. Run: pip install 'scenedetect[opencv]'")
        sys.exit(1)

    try:
        import cv2
    except ImportError:
        print("ERROR: opencv-python is not installed.")
        sys.exit(1)

    from io import BytesIO
    from PIL import Image

    frames = []

    try:
        scene_list = detect(video_path, ContentDetector(threshold=SCENE_THRESHOLD))
    except Exception as e:
        print(f"    Scene detection failed: {e}")
        scene_list = []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"    ERROR: cannot open video {video_path}")
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    def read_frame_at(frame_no: int) -> tuple[bytes, int, int] | None:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ret, frame = cap.read()
        if not ret or frame is None:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        w, h = pil.size
        buf = BytesIO()
        pil.save(buf, format="JPEG", quality=92)
        return (buf.getvalue(), w, h)

    if len(scene_list) >= 3:
        # Extract middle frame of each scene
        for start_time, end_time in scene_list[:frame_limit]:
            start_fn = start_time.get_frames()
            end_fn = end_time.get_frames()
            mid = (start_fn + end_fn) // 2
            result = read_frame_at(mid)
            if result:
                frames.append(result)
            if len(frames) >= frame_limit:
                break
    else:
        # Fallback: every Nth frame
        print(f"    <3 scenes found, falling back to every {FALLBACK_FRAME_INTERVAL}th frame")
        frame_no = 0
        while frame_no < total_frames and len(frames) < frame_limit:
            result = read_frame_at(frame_no)
            if result:
                frames.append(result)
            frame_no += FALLBACK_FRAME_INTERVAL

    cap.release()
    return frames


# ─── Main Processing ──────────────────────────────────────────────────────────

def process_video(
    video_url: str,
    video_id: str,
    video_title: str,
    channel_slug: str,
    frame_limit: int,
    known_hashes: set,
    dry_run: bool = False,
) -> int:
    """Download one video, extract frames, save passing ones. Returns frame count saved."""
    out_dir = OUTPUT_DIR / FACTION / PLATFORM / channel_slug
    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    if dry_run:
        print(f"    [DRY RUN] Would process: {video_title[:60]}")
        return 0

    print(f"    Processing: {video_title[:60]}")
    saved = 0

    with tempfile.TemporaryDirectory() as tmp_dir:
        video_path = download_video(video_url, tmp_dir)
        if not video_path:
            print(f"    SKIP: failed to download {video_url}")
            return 0

        raw_frames = extract_scene_frames(video_path, frame_limit)
        print(f"    {len(raw_frames)} candidate frames extracted")

        for frame_idx, (frame_bytes, w, h) in enumerate(raw_frames):
            result = quality_check_bytes(
                frame_bytes, known_hashes,
                min_w=400, min_h=400,
                blur_threshold=100.0,
            )
            if result is None:
                continue

            jpg_data, fw, fh, fhash = result
            known_hashes.add(fhash)
            save_hash(fhash)

            fname = f"{FACTION}_{PLATFORM}_{video_id}_{frame_idx:04d}.jpg"
            (out_dir / fname).write_bytes(jpg_data)
            saved += 1

            log_image({
                "filename": fname,
                "unit_name": "",
                "faction": FACTION,
                "image_type": "battle_report_frame",
                "source_url": video_url,
                "page_url": f"https://www.youtube.com/watch?v={video_id}",
                "source_platform": PLATFORM,
                "width_px": fw,
                "height_px": fh,
                "file_hash": fhash,
                "search_query": channel_slug,
                "timestamp": now_iso(),
            })

    print(f"    Saved {saved} frames from {video_id}")
    return saved


def process_channel(
    channel_url: str,
    channel_slug: str,
    video_limit: int,
    frame_limit: int,
    known_hashes: set,
    scraped_ids: set,
    dry_run: bool = False,
) -> int:
    print(f"\n  Channel: {channel_slug}  ({channel_url})")

    videos = list_channel_videos(channel_url, video_limit * 3)
    print(f"  Found {len(videos)} videos, filtering for battle reports...")

    # Filter to battle-report-like titles
    battle_videos = [v for v in videos if is_battle_report(v["title"])]
    print(f"  {len(battle_videos)} battle report videos")

    total = 0
    processed = 0
    for v in battle_videos:
        if processed >= video_limit:
            break
        vid_id = v["id"]
        if vid_id in scraped_ids:
            continue
        n = process_video(
            video_url=v["webpage_url"],
            video_id=vid_id,
            video_title=v["title"],
            channel_slug=channel_slug,
            frame_limit=frame_limit,
            known_hashes=known_hashes,
            dry_run=dry_run,
        )
        if n > 0:
            scraped_ids.add(vid_id)
        total += n
        processed += 1

    print(f"  Done: {total} frames from {channel_slug}")
    return total


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract frames from YouTube battle reports as training data"
    )
    parser.add_argument("--channel", metavar="URL", help="Channel URL")
    parser.add_argument("--channel-slug", metavar="SLUG", help="Output dir slug (required with --channel)")
    parser.add_argument("--video", metavar="URL", help="Single video URL")
    parser.add_argument("--playlist", metavar="URL", help="Playlist URL")
    parser.add_argument("--all-channels", action="store_true", help="Process all channels in CHANNELS dict")
    parser.add_argument("--limit", type=int, default=20, help="Max videos per channel (default: 20)")
    parser.add_argument("--frame-limit", type=int, default=30, help="Max frames per video (default: 30)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list-channels", action="store_true")
    args = parser.parse_args()

    if args.list_channels:
        print("\nPredefined channels:")
        for slug, url in CHANNELS.items():
            print(f"  {slug:25s} {url}")
        return

    if not any([args.all_channels, args.channel, args.video, args.playlist]):
        parser.print_help()
        sys.exit(1)

    if args.channel and not args.channel_slug:
        print("ERROR: --channel-slug is required when using --channel")
        sys.exit(1)

    init_csv()
    known_hashes = load_known_hashes()
    scraped_ids = load_scraped_video_ids()

    print("=" * 60)
    print("YouTube Collector")
    print(f"Frame limit per video: {args.frame_limit}")
    print(f"Dry run: {args.dry_run}")
    print(f"Known hashes: {len(known_hashes)}")
    print(f"Output: {OUTPUT_DIR / FACTION / PLATFORM}")
    print("=" * 60)

    grand_total = 0

    try:
        if args.all_channels:
            for slug, url in CHANNELS.items():
                n = process_channel(
                    channel_url=url,
                    channel_slug=slug,
                    video_limit=args.limit,
                    frame_limit=args.frame_limit,
                    known_hashes=known_hashes,
                    scraped_ids=scraped_ids,
                    dry_run=args.dry_run,
                )
                grand_total += n

        elif args.channel:
            n = process_channel(
                channel_url=args.channel,
                channel_slug=args.channel_slug,
                video_limit=args.limit,
                frame_limit=args.frame_limit,
                known_hashes=known_hashes,
                scraped_ids=scraped_ids,
                dry_run=args.dry_run,
            )
            grand_total += n

        elif args.video:
            slug = args.channel_slug or "manual"
            vid_id = get_video_id(args.video) or "unknown"
            n = process_video(
                video_url=args.video,
                video_id=vid_id,
                video_title="manual",
                channel_slug=slug,
                frame_limit=args.frame_limit,
                known_hashes=known_hashes,
                dry_run=args.dry_run,
            )
            grand_total += n

        elif args.playlist:
            slug = args.channel_slug or "playlist"
            videos = list_channel_videos(args.playlist, args.limit * 3)
            for v in videos[:args.limit]:
                if v["id"] in scraped_ids:
                    continue
                n = process_video(
                    video_url=v["webpage_url"],
                    video_id=v["id"],
                    video_title=v["title"],
                    channel_slug=slug,
                    frame_limit=args.frame_limit,
                    known_hashes=known_hashes,
                    dry_run=args.dry_run,
                )
                if n > 0:
                    scraped_ids.add(v["id"])
                grand_total += n

    except KeyboardInterrupt:
        print("\n\nInterrupted. Progress is saved — safe to resume.")

    print(f"\n{'='*60}")
    print(f"DONE. Total new frames: {grand_total}")
    print(f"Output: {OUTPUT_DIR / FACTION / PLATFORM}")
    print(f"Log: {SCRAPE_LOG}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
