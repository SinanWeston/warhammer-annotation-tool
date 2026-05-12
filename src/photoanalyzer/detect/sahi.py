"""Shared SAHI tiling + post-process helpers for detectors.

Lifted from scripts/phaseF/autolabel.py so every detector in
photoanalyzer.detect.ensemble can tile crowded scenes the same way.

SAHI (Slicing Aided Hyper Inference) — crop the image into overlapping
tiles, run the detector on each, offset detections back into image
coordinates, then merge via class-agnostic NMS. Good recall on dense
scenes where the global resolution is too coarse for small objects.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import torch
import torchvision.ops as ops
from PIL import Image


# Defaults mirror the original autolabel.py values. Each call site can
# override; these are the shipping defaults.
DEFAULT_LONG_EDGE_THRESHOLD = 1200
DEFAULT_SLICE_SIZE = 640
DEFAULT_OVERLAP = 0.2
DEFAULT_NMS_IOU = 0.5
DEFAULT_MIN_AREA_FRAC = 0.005
DEFAULT_MAX_AREA_FRAC = 0.80


# A "tile detector" is any callable that takes a PIL image and returns
# (xyxy_boxes, scores). Both detect_with_sahi and post_process work on
# this shape so we don't couple to any specific model wrapper.
TileDetector = Callable[[Image.Image], tuple[np.ndarray, np.ndarray]]


def _anchors(dim: int, slice_size: int, stride: int) -> list[int]:
    """Anchor offsets so the last tile reaches the edge without missing
    pixels. If (dim - slice_size) isn't a multiple of stride we snap the
    last anchor to dim - slice_size."""
    if dim <= slice_size:
        return [0]
    pts = list(range(0, dim - slice_size, stride))
    pts.append(dim - slice_size)
    return pts


def detect_with_sahi(
    detect_fn: TileDetector,
    image: Image.Image,
    slice_size: int = DEFAULT_SLICE_SIZE,
    overlap: float = DEFAULT_OVERLAP,
    nms_iou: float = DEFAULT_NMS_IOU,
) -> tuple[np.ndarray, np.ndarray]:
    """Run `detect_fn` on overlapping tiles, merge via class-agnostic NMS.

    detect_fn: PIL.Image -> (xyxy_boxes, scores). Tile offsets are added
    to the boxes before merging, so the returned boxes are in the input
    image's coordinate system.
    """
    w, h = image.size
    stride = max(1, int(slice_size * (1 - overlap)))
    xs = _anchors(w, slice_size, stride)
    ys = _anchors(h, slice_size, stride)

    all_boxes: list[np.ndarray] = []
    all_scores: list[np.ndarray] = []
    for y in ys:
        for x in xs:
            tile = image.crop((x, y, x + slice_size, y + slice_size))
            tb, ts = detect_fn(tile)
            if len(tb) == 0:
                continue
            tb = tb.copy()
            tb[:, [0, 2]] += x
            tb[:, [1, 3]] += y
            all_boxes.append(tb)
            all_scores.append(ts)

    if not all_boxes:
        return np.zeros((0, 4), dtype=np.float32), np.zeros((0,), dtype=np.float32)
    boxes = np.concatenate(all_boxes, axis=0)
    scores = np.concatenate(all_scores, axis=0)
    keep = ops.nms(torch.from_numpy(boxes), torch.from_numpy(scores), nms_iou).tolist()
    return boxes[keep].astype(np.float32), scores[keep].astype(np.float32)


def post_process(
    boxes: np.ndarray,
    scores: np.ndarray,
    w: int,
    h: int,
    nms_iou: float = DEFAULT_NMS_IOU,
    min_area_frac: float = DEFAULT_MIN_AREA_FRAC,
    max_area_frac: float = DEFAULT_MAX_AREA_FRAC,
) -> tuple[np.ndarray, np.ndarray]:
    """Clip-to-bounds → area filter → class-agnostic NMS.
    Boxes are xyxy; returned shapes match the input semantics."""
    if len(boxes) == 0:
        return boxes, scores
    boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, w)
    boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, h)
    img_area = float(w * h)
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    keep_mask = (
        (areas >= img_area * min_area_frac)
        & (areas <= img_area * max_area_frac)
        & (boxes[:, 2] > boxes[:, 0])
        & (boxes[:, 3] > boxes[:, 1])
    )
    boxes, scores = boxes[keep_mask], scores[keep_mask]
    if len(boxes) == 0:
        return boxes, scores
    keep = ops.nms(torch.from_numpy(boxes), torch.from_numpy(scores), nms_iou).tolist()
    return boxes[keep], scores[keep]


def should_tile(image: Image.Image, long_edge_threshold: int = DEFAULT_LONG_EDGE_THRESHOLD) -> bool:
    """Decide whether an image warrants SAHI. Images at or below the
    threshold are better off as a single pass — tiling small images can
    split minis across tile boundaries and double-count."""
    return max(image.size) > long_edge_threshold
