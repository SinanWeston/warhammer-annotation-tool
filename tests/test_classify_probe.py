"""FactionProbe — v1 restriction, confidences, persistence."""
from __future__ import annotations

import numpy as np
import pytest

from photoanalyzer.classify import FactionProbe
from photoanalyzer.taxonomy import V1_FACTIONS

DIM = 16


def _synthetic(classes, n_per=30, seed=40):
    """Linearly separable clusters, one per class."""
    rng = np.random.default_rng(seed)
    means = {c: rng.normal(0, 4, DIM) for c in classes}
    X, y = [], []
    for c in classes:
        X.append(means[c] + rng.normal(0, 0.3, (n_per, DIM)))
        y += [c] * n_per
    return np.concatenate(X), np.array(y), means


CLASSES = list(V1_FACTIONS) + ["orks", "tau_empire"]


@pytest.fixture(scope="module")
def fitted():
    X, y, means = _synthetic(CLASSES)
    return FactionProbe().fit(X, y), means


def test_unrestricted_recovers_all_classes(fitted):
    probe, means = fitted
    for c in CLASSES:
        pred = probe.predict(means[c][None, :], restrict=None)[0]
        assert pred.faction == c
        assert 0 < pred.confidence <= 1


def test_v1_restriction_is_default_and_never_leaves_v1(fitted):
    probe, means = fitted
    # an obvious ork must still come back as some v1 faction by default
    pred = probe.predict(means["orks"][None, :])[0]
    assert pred.faction in V1_FACTIONS
    for c in V1_FACTIONS:
        assert probe.predict(means[c][None, :])[0].faction == c


def test_restricted_confidence_renormalized(fitted):
    probe, means = fitted
    x = means["orks"][None, :]
    unres = probe.predict(x, restrict=None)[0]
    res = probe.predict(x)[0]
    # ork probability mass is excluded → the restricted winner's renormalized
    # confidence must be a valid probability over the v1 candidate set
    assert unres.faction == "orks"
    assert 0 < res.confidence <= 1


def test_restrict_to_unknown_class_raises(fitted):
    probe, _ = fitted
    with pytest.raises(ValueError, match="absent from training"):
        probe.predict(np.zeros((1, DIM)), restrict=["space_marines", "eldar"])


def test_predict_proba_rows_sum_to_one(fitted):
    probe, means = fitted
    p = probe.predict_proba(np.stack([means[c] for c in CLASSES]))
    assert p.shape == (len(CLASSES), len(CLASSES))
    np.testing.assert_allclose(p.sum(axis=1), 1.0, rtol=1e-6)


def test_save_load_roundtrip(fitted, tmp_path):
    probe, means = fitted
    path = tmp_path / "probe.joblib"
    probe.save(path)
    loaded = FactionProbe.load(path)
    x = np.stack([means[c] for c in CLASSES])
    a = [p.faction for p in probe.predict(x, restrict=None)]
    b = [p.faction for p in loaded.predict(x, restrict=None)]
    assert a == b


def test_unfitted_raises():
    with pytest.raises(RuntimeError, match="not fitted"):
        FactionProbe().predict(np.zeros((1, DIM)))
