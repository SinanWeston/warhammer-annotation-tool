#!/usr/bin/env python3
"""
Claude Code Stop hook — regenerates PROJECT_STATUS.md every time Claude
finishes a response. Gives a live snapshot of every file in the project.

Receives JSON on stdin: { session_id, stop_hook_active }
"""
import sys
import os
import json
from datetime import datetime

PROJECT = '/home/sinan/Active/Projects/photoanalyzer'
OUTPUT  = f'{PROJECT}/PROJECT_STATUS.md'

# Directories to skip entirely
SKIP_DIRS = {
    'node_modules', 'dist', '.git', '__pycache__', 'yolo_env',
    'venv', '.cache', 'runs', 'reference_gallery', 'test-images',
    'har_files', '.vite', 'coverage', 'build', 'few_shot_examples',
}

# Source directories to show in detail (relative to PROJECT)
SOURCE_DIRS = [
    ('frontend/src',         'Frontend (Annotator)'),
    ('consumer/src',         'Consumer PWA (Battle Scanner)'),
    ('annotator-mobile/src', 'Mobile Annotator'),
    ('backend/src',          'Backend (Express API)'),
    ('scripts',              'Scripts'),
]

# Data directories — show summary only
DATA_DIRS = [
    ('backend/training_data_annotations', 'Annotations',   '.json'),
    ('backend/yolo_dataset',              'YOLO Dataset',  None),
    ('backend/training_data',             'Training Images', None),
]


def human_size(n):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def file_tree(base, depth=0, max_depth=3):
    """Return list of markdown lines representing the directory tree."""
    lines = []
    if depth > max_depth:
        return lines
    try:
        entries = sorted(os.scandir(base), key=lambda e: (e.is_file(), e.name))
    except (PermissionError, FileNotFoundError):
        return lines

    for entry in entries:
        name = entry.name
        if name.startswith('.') or name in SKIP_DIRS:
            continue
        indent = '  ' * depth
        if entry.is_dir(follow_symlinks=False):
            lines.append(f"{indent}- **{name}/**")
            lines.extend(file_tree(entry.path, depth + 1, max_depth))
        else:
            try:
                size = human_size(entry.stat().st_size)
                mtime = datetime.fromtimestamp(entry.stat().st_mtime).strftime('%m-%d %H:%M')
                lines.append(f"{indent}- `{name}` _{size}, {mtime}_")
            except OSError:
                lines.append(f"{indent}- `{name}`")
    return lines


def count_files(directory, ext=None):
    total = 0
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for f in files:
            if ext is None or f.endswith(ext):
                total += 1
    return total


def dir_size(directory):
    total = 0
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


# ── Only run when inside a photoanalyzer session ──────────────────────────────
# Check that the project actually exists (safe guard for global hook)
if not os.path.isdir(PROJECT):
    sys.exit(0)

now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

lines = [
    f"# Project Status\n",
    f"> Auto-generated on **{now}** by `status-hook.py`  \n",
    f"> _Edit this file manually to add persistent notes above the auto-generated section._\n",
    "\n---\n",
    "\n## Source Files\n",
]

for rel_path, label in SOURCE_DIRS:
    full = os.path.join(PROJECT, rel_path)
    if not os.path.isdir(full):
        continue
    n = count_files(full)
    lines.append(f"\n### {label} (`{rel_path}/`) — {n} files\n")
    tree = file_tree(full, depth=0, max_depth=3)
    if tree:
        lines.append('\n'.join(tree) + '\n')
    else:
        lines.append('_empty_\n')

lines.append("\n---\n\n## Data Directories\n\n")
for rel_path, label, ext in DATA_DIRS:
    full = os.path.join(PROJECT, rel_path)
    if not os.path.isdir(full):
        lines.append(f"- **{label}** (`{rel_path}/`) — _not found_\n")
        continue
    n    = count_files(full, ext=ext)
    size = human_size(dir_size(full))
    ext_label = f"`{ext}` files" if ext else "files"
    lines.append(f"- **{label}** (`{rel_path}/`) — {n} {ext_label}, {size} total\n")

lines += [
    "\n---\n",
    "\n## Root-Level Files\n\n",
]
try:
    root_files = sorted(
        e for e in os.scandir(PROJECT)
        if e.is_file() and not e.name.startswith('.')
    )
    for e in root_files:
        size  = human_size(e.stat().st_size)
        mtime = datetime.fromtimestamp(e.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
        lines.append(f"- `{e.name}` _{size}, modified {mtime}_\n")
except Exception:
    pass

with open(OUTPUT, 'w') as f:
    f.writelines(lines)
