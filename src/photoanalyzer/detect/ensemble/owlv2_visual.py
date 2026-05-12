"""OWLv2 image-guided detection.

OWLv2 (Minderer et al., 2024, google/owlv2-base-patch16-ensemble) can
do one-shot/few-shot detection given an exemplar image. Here we feed
it ~30 gold miniature crops (stratified by faction × scale) and union
per-exemplar detections on the target image.

Complements text-prompted passes: text descriptions generalise poorly
to painted miniatures' specific visual signature (painted plastic,
round base, hobby-paint colour palettes). Visual exemplars carry that
prior directly. See the HF transformers visual-prompt workaround
(issue #39710) — for quality we may need to switch from the default
query-embedding selection to an alternative; implemented as a flag on
this class.

License: Apache-2.0 (base model).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from photoanalyzer.detect.base import Detection, Detector, ImageSource


DEFAULT_MODEL_ID = "google/owlv2-base-patch16-ensemble"
DEFAULT_EXEMPLAR_DIR = Path("data/exemplars")
DEFAULT_EXEMPLAR_MANIFEST = DEFAULT_EXEMPLAR_DIR / "manifest.json"
# Low default — visual-prompt precision is noisy; we rely on ensemble
# agreement voting to filter false positives.
DEFAULT_THRESHOLD = 0.90
# OWLv2 has a fixed input size; no SAHI integration yet because
# image_guided_detection at 960² tile + query is ~2s on a T4 and the
# per-exemplar × tile product explodes. If recall on crowds is poor
# after F1.7 bench, revisit with a smaller subset of exemplars + SAHI.


class OwlV2VisualDetector(Detector):
    """One-shot detection with OWLv2, union over an exemplar set.

    Typical use:
        det = OwlV2VisualDetector.from_exemplar_dir(Path("data/exemplars"))
        detections = det.predict("target.jpg")
    """

    def __init__(
        self,
        exemplar_paths: list[Path],
        model_id: str = DEFAULT_MODEL_ID,
        threshold: float = DEFAULT_THRESHOLD,
        nms_iou: float = 0.5,
        device: str | None = None,
    ) -> None:
        if not exemplar_paths:
            raise ValueError("OwlV2VisualDetector requires at least one exemplar")
        self.exemplar_paths = exemplar_paths
        self.model_id = model_id
        self.threshold = threshold
        self.nms_iou = nms_iou
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._processor = None
        self._model = None
        self._exemplar_images: list[Image.Image] = []

    @classmethod
    def from_exemplar_dir(
        cls,
        exemplar_dir: Path = DEFAULT_EXEMPLAR_DIR,
        **kwargs,
    ) -> "OwlV2VisualDetector":
        """Build from the exemplar directory emitted by
        scripts/phaseF/build_exemplar_set.py. Falls back to walking
        the directory if no manifest is present."""
        manifest = exemplar_dir / "manifest.json"
        if manifest.exists():
            data = json.loads(manifest.read_text())
            paths = [exemplar_dir / e["file"] for e in data.get("exemplars", [])]
        else:
            paths = sorted(exemplar_dir.glob("*.jpg"))
        if not paths:
            raise FileNotFoundError(
                f"No exemplars at {exemplar_dir}. "
                f"Run: yolo_env/bin/python scripts/phaseF/build_exemplar_set.py"
            )
        return cls(exemplar_paths=paths, **kwargs)

    def _load(self) -> None:
        if self._model is not None:
            return
        from transformers import Owlv2Processor, Owlv2ForObjectDetection
        self._processor = Owlv2Processor.from_pretrained(self.model_id)
        self._model = Owlv2ForObjectDetection.from_pretrained(self.model_id).to(self.device)
        self._model.eval()
        # Pre-open exemplar PIL images — reused on every predict call.
        self._exemplar_images = [
            Image.open(p).convert("RGB") for p in self.exemplar_paths
        ]

    @torch.inference_mode()
    def _detect_with_exemplar(
        self, target: Image.Image, query: Image.Image,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Single-exemplar image-guided detection. Returns
        (xyxy_boxes, scores) in target's pixel coords."""
        assert self._processor is not None and self._model is not None
        inputs = self._processor(
            images=target, query_images=query, return_tensors="pt",
        ).to(self.device)
        outputs = self._model.image_guided_detection(**inputs)
        target_sizes = torch.tensor([[target.size[1], target.size[0]]], device=self.device)
        results = self._processor.post_process_image_guided_detection(
            outputs, threshold=self.threshold, target_sizes=target_sizes,
        )[0]
        if "boxes" not in results or len(results["boxes"]) == 0:
            return np.zeros((0, 4), dtype=np.float32), np.zeros((0,), dtype=np.float32)
        boxes = results["boxes"].detach().cpu().numpy().astype(np.float32)
        scores = results["scores"].detach().cpu().numpy().astype(np.float32)
        return boxes, scores

    def predict(self, image: ImageSource) -> list[Detection]:
        self._load()
        if isinstance(image, (str, Path)):
            target = Image.open(image).convert("RGB")
        elif isinstance(image, np.ndarray):
            target = Image.fromarray(image)
        elif isinstance(image, Image.Image):
            target = image.convert("RGB")
        else:
            raise TypeError(f"unsupported image type: {type(image)}")

        # Union detections across every exemplar. Exemplar-level parallelism
        # could be added later; the model call itself batches internally.
        all_boxes: list[np.ndarray] = []
        all_scores: list[np.ndarray] = []
        for query in self._exemplar_images:
            b, s = self._detect_with_exemplar(target, query)
            if len(b):
                all_boxes.append(b)
                all_scores.append(s)

        if not all_boxes:
            return []

        import torchvision.ops as ops
        boxes = np.concatenate(all_boxes, axis=0)
        scores = np.concatenate(all_scores, axis=0)
        # Class-agnostic NMS merges identical objects detected via multiple
        # exemplars — keeps the highest-score-per-cluster survivor.
        keep = ops.nms(
            torch.from_numpy(boxes), torch.from_numpy(scores), self.nms_iou,
        ).tolist()
        boxes = boxes[keep]
        scores = scores[keep]

        out: list[Detection] = []
        for (x1, y1, x2, y2), s in zip(boxes, scores):
            out.append(Detection(
                bbox=(float(x1), float(y1), float(x2 - x1), float(y2 - y1)),
                confidence=float(s),
                class_id=-1,
                class_name="miniature",
            ))
        return out
