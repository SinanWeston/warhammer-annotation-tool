"""Tier 2 faction classifier — frozen-embedding linear probe (production).

The benched recipe (2026-06-05 probe bench, 2026-06-09 compounded bench):
StandardScaler + LogisticRegression(C=1.0, max_iter=3000) over frozen
DINOv2-large CLS embeddings, with predictions **restricted to the v1 faction
set by default**. On real crops the 20-way argmax routes at 0.284 faction
top-1 while the v1-restricted argmax routes at 0.588 (SM 0.39 → 0.94) — the
restriction is the production behaviour, not an eval trick. See
`docs/benchmarks/2026-06-09-review-experiments.md`.

`predict()` returns per-crop (faction, confidence) where confidence is the
probability renormalized over the candidate set — the quantity the future
"unknown" threshold will cut on.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from ..taxonomy import V1_FACTIONS

EMBED_MODEL = "facebook/dinov2-large"


@dataclass(frozen=True)
class FactionPrediction:
    faction: str
    confidence: float  # renormalized over the candidate (restricted) set


class FactionProbe:
    """Linear probe over frozen embeddings, v1-restricted by default."""

    def __init__(self) -> None:
        self._scaler = None
        self._clf = None

    # ── training ────────────────────────────────────────────────────────────
    def fit(self, X: np.ndarray, y: Sequence[str]) -> "FactionProbe":
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        X = np.asarray(X, dtype=np.float32)
        y = np.asarray([str(v) for v in y])
        self._scaler = StandardScaler().fit(X)
        self._clf = LogisticRegression(max_iter=3000, C=1.0).fit(
            self._scaler.transform(X), y)
        return self

    @property
    def classes(self) -> tuple[str, ...]:
        self._require_fitted()
        return tuple(self._clf.classes_)

    # ── inference ───────────────────────────────────────────────────────────
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Full unrestricted distribution, columns ordered as `self.classes`."""
        self._require_fitted()
        X = np.asarray(X, dtype=np.float32)
        return self._clf.predict_proba(self._scaler.transform(X))

    def predict(
        self,
        X: np.ndarray,
        restrict: Iterable[str] | None = V1_FACTIONS,
    ) -> list[FactionPrediction]:
        """Predict a faction per row. `restrict` limits the candidate set
        (default: the v1 factions); pass None for unrestricted 20-way argmax.
        """
        proba = self.predict_proba(X)
        classes = np.asarray(self._clf.classes_)
        if restrict is None:
            cols = np.arange(len(classes))
        else:
            wanted = list(dict.fromkeys(str(f) for f in restrict))
            missing = [f for f in wanted if f not in set(classes)]
            if missing:
                raise ValueError(
                    f"restricted factions absent from training data: {missing} "
                    f"(trained classes: {sorted(classes)})")
            cols = np.array([int(np.where(classes == f)[0][0]) for f in wanted])
        sub = proba[:, cols]
        denom = sub.sum(axis=1, keepdims=True)
        denom[denom == 0] = 1.0
        sub = sub / denom
        best = np.argmax(sub, axis=1)
        return [FactionPrediction(faction=str(classes[cols[b]]),
                                  confidence=float(sub[i, b]))
                for i, b in enumerate(best)]

    # ── persistence ─────────────────────────────────────────────────────────
    def save(self, path: str | Path) -> None:
        import joblib

        self._require_fitted()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"scaler": self._scaler, "clf": self._clf,
                     "embed_model": EMBED_MODEL, "version": 1}, path)

    @classmethod
    def load(cls, path: str | Path) -> "FactionProbe":
        import joblib

        blob = joblib.load(path)
        probe = cls()
        probe._scaler = blob["scaler"]
        probe._clf = blob["clf"]
        return probe

    def _require_fitted(self) -> None:
        if self._clf is None or self._scaler is None:
            raise RuntimeError("FactionProbe is not fitted — call fit() or load()")
