"""SAM 3 detector — Meta's Nov-2025 Segment-Anything-3 model.

Gated on HuggingFace: requires accepting the license at
https://huggingface.co/facebook/sam3 and setting HUGGINGFACE_HUB_TOKEN.

SAM 3 is text-prompted and concept-exhaustive ("find every instance of
the concept") — exactly matching our need to detect every miniature
in a photo. On published SA-Co benchmarks it more than doubles OWLv2
and DINO-X on this exhaustive-detection axis (arXiv 2511.16719).

Pipeline:
    processor(images=image, text=CONCEPT, ...)  →  model(**inputs)
    → post_process_object_detection → xyxy boxes + scores.

Optional SAHI tiling for > 1200 px long-edge images — SAM 3 handles
100+ objects per image natively, but tiling still helps on very large
crowd scenes where small rear-rank figures would otherwise be below
the attention resolution.

License note: STRATEGY.md §3.1 previously stated SAM had a
"competing foundation models" clause — the current SAM 3 license (as
of Nov 2025) does NOT contain such a clause, permits commercial use,
and does not force share-alike on outputs. We still keep SAM 3 offline
only: its outputs (pseudo-boxes) train RF-DETR-Medium (Apache-2.0)
which is what ships.
"""
from __future__ import annotations

import os
from pathlib import Path

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


DEFAULT_MODEL_ID = "facebook/sam3"
# Concept phrase — lowercase, short. SAM 3 is robust to prompt wording
# (SA-Co training was exhaustive rather than contrastive). Longer
# multi-concept prompts like DINO's dot-separated list don't help here.
DEFAULT_CONCEPT = "painted miniature"
DEFAULT_THRESHOLD = 0.25


class Sam3Detector(Detector):
    """SAM 3 class-agnostic detector."""

    def __init__(
        self,
        concept: str = DEFAULT_CONCEPT,
        model_id: str = DEFAULT_MODEL_ID,
        threshold: float = DEFAULT_THRESHOLD,
        device: str | None = None,
        use_sahi: bool = True,
        sahi_long_edge: int = DEFAULT_LONG_EDGE_THRESHOLD,
    ) -> None:
        self.concept = concept
        self.model_id = model_id
        self.threshold = threshold
        self.use_sahi = use_sahi
        self.sahi_long_edge = sahi_long_edge
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._processor = None
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        token = os.environ.get("HUGGINGFACE_HUB_TOKEN") or os.environ.get("HF_TOKEN")
        if not token:
            raise RuntimeError(
                "SAM 3 is a gated model. Set HUGGINGFACE_HUB_TOKEN in .env "
                "and accept the license at https://huggingface.co/facebook/sam3."
            )
        from huggingface_hub import login
        # add_to_git_credential=False keeps the token out of ~/.gitconfig.
        try:
            login(token=token, add_to_git_credential=False)
        except Exception:
            pass
        from transformers import Sam3Processor, Sam3Model
        try:
            self._processor = Sam3Processor.from_pretrained(self.model_id)
            self._model = Sam3Model.from_pretrained(self.model_id).to(self.device)
        except Exception as e:
            if "gated" in str(e).lower() or "401" in str(e):
                raise RuntimeError(
                    "SAM 3 access denied. Either (a) request access at "
                    "https://huggingface.co/facebook/sam3 and wait for approval, "
                    "or (b) run with --no-sam3 / Ensemble(include_sam3=False)."
                ) from e
            raise
        self._model.eval()

    @torch.inference_mode()
    def _detect_tile(self, image: Image.Image) -> tuple[np.ndarray, np.ndarray]:
        """Single-pass SAM 3 detection. Returns (xyxy_boxes, scores) in
        the input image's pixel coordinates."""
        assert self._processor is not None and self._model is not None
        inputs = self._processor(
            images=image, text=self.concept, return_tensors="pt",
        ).to(self.device)
        outputs = self._model(**inputs)
        h, w = image.size[1], image.size[0]
        results = self._processor.post_process_object_detection(
            outputs,
            threshold=self.threshold,
            target_sizes=[(h, w)],
        )[0]
        if len(results.get("boxes", [])) == 0:
            return np.zeros((0, 4), dtype=np.float32), np.zeros((0,), dtype=np.float32)
        boxes = results["boxes"].detach().cpu().numpy().astype(np.float32)
        scores = results["scores"].detach().cpu().numpy().astype(np.float32)
        return boxes, scores

    def predict(self, image: ImageSource) -> list[Detection]:
        self._load()
        if isinstance(image, (str, Path)):
            pil = Image.open(image).convert("RGB")
        elif isinstance(image, np.ndarray):
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
