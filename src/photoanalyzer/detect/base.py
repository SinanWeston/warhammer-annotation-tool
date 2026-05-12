"""Detector abstraction.

Every detector (YOLO today, OWLv2 in Phase D5) produces the same `Detection`
shape so `photoanalyzer.pipeline` and `photoanalyzer.label.extract` can be
detector-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Union

import numpy as np


ImageSource = Union[str, Path, np.ndarray]


@dataclass(frozen=True)
class Detection:
    """One detected object in image-pixel coordinates.

    bbox is (x, y, w, h) with origin top-left — matches photoanalyzer.eval.metrics.Bbox.
    """
    bbox: tuple[float, float, float, float]
    confidence: float
    class_id: int = -1        # -1 when the detector is class-agnostic
    class_name: str = ""      # free-text, useful for logging; don't branch on it

    @property
    def xyxy(self) -> tuple[float, float, float, float]:
        x, y, w, h = self.bbox
        return (x, y, x + w, y + h)


class Detector(ABC):
    """Detector contract.

    Implementations should:
    - Load their model lazily (on first `predict`) to keep import costs low.
    - Accept a file path, a Path, OR a numpy image array (H x W x 3 BGR/RGB —
      implementation's choice, document it).
    - Never raise on empty detections — return an empty list.
    """

    @abstractmethod
    def predict(self, image: ImageSource) -> list[Detection]:
        """Return zero or more detections for one image."""
        ...

    def predict_many(self, images: list[ImageSource]) -> list[list[Detection]]:
        """Default batched impl — override for GPU-batching in subclasses."""
        return [self.predict(img) for img in images]
