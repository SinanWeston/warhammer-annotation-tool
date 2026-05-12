"""Text-prompt open-vocab detector — Grounding DINO today, DINO-X
swappable via config if/when DeepDataSpace API access is provisioned.

Named `dinox` because STRATEGY aspires to DINO-X (Apache-2.0, best
published open-vocab detector per arXiv 2411.14347). DINO-X weights
are not on HuggingFace Hub as of 2026-04; DeepDataSpace hosts them
behind a paid API. Until that's resolved we ship Grounding DINO base
from HF (also Apache-2.0, ~4 AP weaker on COCO but drop-in install).

The ensemble compensates via SAM 3 as the primary quality anchor and
OWLv2 visual-prompt as the complementary pass.

Config surface (via constructor):
  backend="grounding_dino_base"   (default, open-weights on HF)
  backend="grounding_dino_large"  (same family, larger)
  backend="dinox_api"             (future; requires DINOX_API_KEY)

Prompt choice follows cv-researcher's April 2026 review: drop the
"tabletop model" phrase that triggers terrain false-positives on
scenes like display dioramas with scenic rocks.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import numpy as np
import torch
from PIL import Image

from photoanalyzer.detect.base import Detection, Detector, ImageSource
from photoanalyzer.detect.sahi import (
    DEFAULT_LONG_EDGE_THRESHOLD,
    detect_with_sahi,
    post_process,
    should_tile,
)


# Default prompt — multi-concept, dot-separated, trailing period
# (Grounding DINO's documented input format). "tabletop model" was
# dropped because it triggers detections on painted terrain / dioramas.
DEFAULT_PROMPT = "miniature . figurine . painted model . warhammer model ."

# Thresholds: detection is deliberately lenient because the ensemble
# relies on SAM 2 refinement + agreement voting to reject junk. Keep in
# step with autolabel.py so cross-comparison bench is apples-to-apples
# until we lock final thresholds after F1.7.
DEFAULT_BOX_THRESHOLD = 0.25
DEFAULT_TEXT_THRESHOLD = 0.20


Backend = Literal["grounding_dino_base", "grounding_dino_large", "dinox_api"]

_HF_MODEL_IDS: dict[Backend, str] = {
    "grounding_dino_base": "IDEA-Research/grounding-dino-base",
    "grounding_dino_large": "IDEA-Research/grounding-dino-large",
}


class DinoXDetector(Detector):
    """Text-prompted class-agnostic detector.

    Example:
        det = DinoXDetector()
        boxes = det.predict("path/to/image.jpg")  # list[Detection]
    """

    def __init__(
        self,
        backend: Backend = "grounding_dino_base",
        prompt: str = DEFAULT_PROMPT,
        box_threshold: float = DEFAULT_BOX_THRESHOLD,
        text_threshold: float = DEFAULT_TEXT_THRESHOLD,
        device: str | None = None,
        use_sahi: bool = True,
        sahi_long_edge: int = DEFAULT_LONG_EDGE_THRESHOLD,
    ) -> None:
        self.backend = backend
        self.prompt = prompt
        self.box_threshold = box_threshold
        self.text_threshold = text_threshold
        self.use_sahi = use_sahi
        self.sahi_long_edge = sahi_long_edge
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        # Lazy load — keeps import cheap per the Detector ABC contract.
        self._processor = None
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        if self.backend == "dinox_api":
            if not os.environ.get("DINOX_API_KEY"):
                raise RuntimeError(
                    "backend='dinox_api' requires DINOX_API_KEY in env. "
                    "Request one at https://deepdataspace.com/."
                )
            raise NotImplementedError(
                "dinox_api backend not yet wired — awaiting DINOX access. "
                "Use backend='grounding_dino_base' in the meantime."
            )
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        model_id = _HF_MODEL_IDS[self.backend]
        self._processor = AutoProcessor.from_pretrained(model_id)
        self._model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(self.device)
        self._model.eval()

    @torch.inference_mode()
    def _detect_tile(self, image: Image.Image) -> tuple[np.ndarray, np.ndarray]:
        """Single-pass detection on the given PIL image. Returns
        (xyxy_boxes, scores) in the input image's coordinate system."""
        assert self._processor is not None and self._model is not None
        inputs = self._processor(images=image, text=self.prompt, return_tensors="pt").to(self.device)
        outputs = self._model(**inputs)
        h, w = image.size[1], image.size[0]
        # transformers ≥ 4.50 accepts both `threshold` and `box_threshold`;
        # the 5.x name is `threshold`. Pass both for forwards-compat.
        results = self._processor.post_process_grounded_object_detection(
            outputs,
            inputs.input_ids,
            threshold=self.box_threshold,
            text_threshold=self.text_threshold,
            target_sizes=[(h, w)],
        )[0]
        if len(results["boxes"]) == 0:
            return np.zeros((0, 4), dtype=np.float32), np.zeros((0,), dtype=np.float32)
        boxes = results["boxes"].detach().cpu().numpy().astype(np.float32)
        scores = results["scores"].detach().cpu().numpy().astype(np.float32)
        return boxes, scores

    def predict(self, image: ImageSource) -> list[Detection]:
        self._load()
        if isinstance(image, (str, Path)):
            pil = Image.open(image).convert("RGB")
        elif isinstance(image, np.ndarray):
            # Caller gave us H x W x 3. Trust RGB per Detector docstring.
            pil = Image.fromarray(image)
        elif isinstance(image, Image.Image):
            pil = image.convert("RGB")
        else:
            raise TypeError(f"unsupported image type: {type(image)}")

        w, h = pil.size
        if self.use_sahi and should_tile(pil, self.sahi_long_edge):
            boxes_xyxy, scores = detect_with_sahi(self._detect_tile, pil)
        else:
            boxes_xyxy, scores = self._detect_tile(pil)
        boxes_xyxy, scores = post_process(boxes_xyxy, scores, w, h)

        out: list[Detection] = []
        for (x1, y1, x2, y2), s in zip(boxes_xyxy, scores):
            out.append(Detection(
                bbox=(float(x1), float(y1), float(x2 - x1), float(y2 - y1)),
                confidence=float(s),
                class_id=-1,
                class_name="miniature",
            ))
        return out
