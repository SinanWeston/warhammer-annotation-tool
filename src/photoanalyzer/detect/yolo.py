"""YOLO detector — wraps ultralytics YOLO for the `photoanalyzer.detect.Detector`
interface.

Matches the invocation pattern already in production at
`backend/src/services/yoloInferenceService.ts:33-49`:

    model = YOLO(path)
    results = model.predict(image, conf=..., verbose=False)
    for r.boxes: (xyxy, cls, conf, names[cls])

Loads the model once on first `predict()` and keeps it in memory — the primary
performance difference vs. the legacy subprocess spawn.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import Detection, Detector, ImageSource


DEFAULT_MODEL_PATH = Path("runs/yolo11x_run2_best.pt")


class YoloDetector(Detector):
    """Warhammer-trained YOLO11x detector.

    Parameters
    ----------
    model_path : Path | str | None
        Path to the `.pt` file. Defaults to `runs/yolo11x_run2_best.pt`.
    conf_threshold : float
        Minimum confidence to emit a detection. Default 0.25 (matches existing).
    device : str | None
        `None` → ultralytics auto-selects (CUDA > MPS > CPU). Override for tests
        or CPU-only runs.
    """

    def __init__(
        self,
        model_path: Path | str | None = None,
        conf_threshold: float = 0.25,
        device: Optional[str] = None,
    ):
        self.model_path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
        self.conf_threshold = conf_threshold
        self.device = device
        self._model = None  # lazy

    # ── internals ──
    def _load(self):
        if self._model is not None:
            return
        from ultralytics import YOLO  # heavy import; defer
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"YOLO model not found at {self.model_path}. Set model_path "
                f"or ensure runs/yolo11x_run2_best.pt exists."
            )
        self._model = YOLO(str(self.model_path))
        # Ultralytics auto-selects device on predict(); device can be overridden
        # per-call via predict(device=...)

    # ── public ──
    def predict(self, image: ImageSource) -> list[Detection]:
        self._load()
        kwargs = {"conf": self.conf_threshold, "verbose": False}
        if self.device is not None:
            kwargs["device"] = self.device
        # ultralytics accepts str | Path | ndarray directly
        results = self._model.predict(image, **kwargs)
        detections: list[Detection] = []
        for r in results:
            names = r.names or {}
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                detections.append(Detection(
                    bbox=(x1, y1, x2 - x1, y2 - y1),
                    confidence=conf,
                    class_id=cls,
                    class_name=names.get(cls, "") or "",
                ))
        return detections

    def predict_many(self, images: list[ImageSource]) -> list[list[Detection]]:
        """Batched predict — ultralytics handles batching internally if given a
        list of inputs, so we call once and split results."""
        if not images:
            return []
        self._load()
        kwargs = {"conf": self.conf_threshold, "verbose": False}
        if self.device is not None:
            kwargs["device"] = self.device
        # Accept list of str/Path/ndarray
        results = self._model.predict(list(images), **kwargs)
        out: list[list[Detection]] = []
        for r in results:
            names = r.names or {}
            dets: list[Detection] = []
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                dets.append(Detection(
                    bbox=(x1, y1, x2 - x1, y2 - y1),
                    confidence=conf,
                    class_id=cls,
                    class_name=names.get(cls, "") or "",
                ))
            out.append(dets)
        return out
