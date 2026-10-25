"""Commercial-clean, deterministic NumPy-only ranking of NEW GM42 events.

Fit strictly on annotated DEVELOPMENT/TRAIN recordings. All five acoustic
features derive from the existing candidate-STFT extractor. Model parameters
are data-derived and are NOT a product-released/checkpoint-cleared model until
training-source rights and independent validation have been reviewed.

Cut 27 contract: frozen feature order, fixed 0.80 score threshold,
L2-regularized logistic ranker. A model trained on Validation/Test fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np

from midivolt.hat_candidate_confidence import (
    HatCandidateConfidence, evaluate_candidate_confidence,
)

SCHEMA = "midivolt.hat_candidate_ranker.v1"
FEATURES = (
    "high_to_mid", "noise_flatness", "two_band_balance",
    "attack_to_prior", "tail_to_attack",
)
DECISION_THRESHOLD = 0.80
TRAIN_EPOCHS = 900
LEARNING_RATE = 0.12
L2 = 0.10


def vectorize(features: dict) -> np.ndarray:
    if not isinstance(features, dict):
        raise ValueError("Expected feature dictionary")
    try:
        v = np.asarray([features[k] for k in FEATURES], dtype=np.float64)
    except (KeyError, TypeError) as err:
        raise ValueError("Feature schema mismatch") from err
    if not np.isfinite(v).all() or np.any(v < 0):
        raise ValueError("Features must be finite and non-negative")
    # Ratios have very long tails. Fixed transform; no Test calibration.
    return np.log1p(v)


def _sigmoid(v):
    return 1.0 / (1.0 + np.exp(-np.clip(v, -45, 45)))


@dataclass(frozen=True)
class HatRankerModel:
    mean: tuple[float, ...]
    scale: tuple[float, ...]
    weights: tuple[float, ...]
    intercept: float
    source_songs: int
    positive_examples: int
    negative_examples: int
    training_manifest_sha256: str
    schema: str = SCHEMA
    training_split: str = "train"
    decision_threshold: float = DECISION_THRESHOLD

    def __post_init__(self):
        if self.schema != SCHEMA or self.training_split != "train":
            raise ValueError("Unknown model schema or non-TRAIN model")
        if (len(self.mean) != len(FEATURES) or len(self.scale) != len(FEATURES)
                or len(self.weights) != len(FEATURES)):
            raise ValueError("Ranker parameter dimension mismatch")
        numbers = list(self.mean) + list(self.scale) + list(self.weights) + [self.intercept]
        if not all(type(v) in (float, int) and math.isfinite(v) for v in numbers):
            raise ValueError("Nonfinite ranker parameters")
        if any(v <= 0 for v in self.scale):
            raise ValueError("Invalid normalization scale")
        if (type(self.source_songs) is not int or self.source_songs < 4
                or type(self.positive_examples) is not int or self.positive_examples < 10
                or type(self.negative_examples) is not int or self.negative_examples < 10):
            raise ValueError("Insufficient TRAIN source recordings/candidate labels")
        if (len(self.training_manifest_sha256) != 64
                or any(v not in "0123456789abcdef" for v in self.training_manifest_sha256)):
            raise ValueError("Missing pinned TRAIN manifest checksum")
        if self.decision_threshold != DECISION_THRESHOLD:
            raise ValueError("Decision threshold must be frozen before Validation")

    def to_dict(self) -> dict:
        return {
            "schema": self.schema, "training_split": self.training_split,
            "features": list(FEATURES),
            "decision_threshold": self.decision_threshold,
            "normalization_mean": list(self.mean),
            "normalization_scale": list(self.scale),
            "weights": list(self.weights), "intercept": self.intercept,
            "source_songs": self.source_songs,
            "positive_examples": self.positive_examples,
            "negative_examples": self.negative_examples,
            "training_manifest_sha256": self.training_manifest_sha256,
            "frozen_hyperparameters": {
                "epochs": TRAIN_EPOCHS, "learning_rate": LEARNING_RATE, "l2": L2
            },
            "commercial_distribution_approved": False,
        }

    @classmethod
    def from_dict(cls, obj: dict) -> "HatRankerModel":
        if not isinstance(obj, dict) or set(obj.get("features", [])) != set(FEATURES) or obj.get("features") != list(FEATURES):
            raise ValueError("Model features not ordered as frozen extractor")
        if obj.get("commercial_distribution_approved") is not False:
            raise ValueError("Model must not claim independently unreviewed distribution approval")
        if obj.get("frozen_hyperparameters") != {
            "epochs": TRAIN_EPOCHS, "learning_rate": LEARNING_RATE, "l2": L2
        }:
            raise ValueError("Ranker hyperparameters were changed")
        return cls(
            mean=tuple(obj["normalization_mean"]),
            scale=tuple(obj["normalization_scale"]),
            weights=tuple(obj["weights"]),
            intercept=obj["intercept"],
            source_songs=obj["source_songs"],
            positive_examples=obj["positive_examples"],
            negative_examples=obj["negative_examples"],
            training_manifest_sha256=obj["training_manifest_sha256"],
            schema=obj["schema"], training_split=obj["training_split"],
            decision_threshold=obj["decision_threshold"],
        )

    def probability(self, features: dict) -> float:
        row = vectorize(features)
        standardized = np.clip((row - self.mean) / self.scale, -5, 5)
        return float(_sigmoid(standardized @ self.weights + self.intercept))


def fit_ranker(rows: list[dict], *, manifest_sha256: str) -> HatRankerModel:
    """Fit with train-only labels. Never use validation/test in this function."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("Empty training candidate set")
    songs: set[str] = set()
    examples, targets = [], []
    for row in rows:
        if row.get("split") != "train":
            raise ValueError("Validation/Test examples forbidden in ranker fit")
        sid = row.get("source_song_id")
        if not isinstance(sid, str) or not sid:
            raise ValueError("Missing original TRAIN source performance identity")
        songs.add(sid)
        if type(row.get("label")) is not int or row["label"] not in (0, 1):
            raise ValueError("Each candidate requires binary reference onset label")
        examples.append(vectorize(row["features"]))
        targets.append(row["label"])
    y = np.array(targets, dtype=np.float64)
    if len(songs) < 4 or (y == 1).sum() < 10 or (y == 0).sum() < 10:
        raise ValueError("Insufficient positive/negative TRAIN examples or source songs")
    x = np.stack(examples)
    center = x.mean(axis=0)
    spread = np.maximum(x.std(axis=0), 0.05)
    z = np.clip((x - center) / spread, -5.0, 5.0)
    w = np.zeros(len(FEATURES), dtype=np.float64)
    bias = float(np.log(np.clip(y.mean(), .001, .999) / np.clip(1-y.mean(), .001, .999)))
    for _ in range(TRAIN_EPOCHS):
        p = _sigmoid(z @ w + bias)
        residual = p - y
        w -= LEARNING_RATE * (z.T @ residual / len(y) + L2 * w)
        bias -= LEARNING_RATE * float(residual.mean())
    return HatRankerModel(
        mean=tuple(map(float, center)),
        scale=tuple(map(float, spread)),
        weights=tuple(map(float, w)),
        intercept=float(bias),
        source_songs=len(songs),
        positive_examples=int(y.sum()),
        negative_examples=int(len(y)-y.sum()),
        training_manifest_sha256=manifest_sha256,
    )


def score_onset(
    magnitude: np.ndarray, frequencies: np.ndarray, frame_index: int,
    *, hop_seconds: float, model: HatRankerModel,
) -> dict:
    if not isinstance(model, HatRankerModel):
        raise ValueError("Explicit TRAIN-only HatRankerModel required")
    # Reuse the frozen acoustic measurements, but NOT the old hard
    # acceptance thresholds. Missing edge-window features are rejected.
    inspected = evaluate_candidate_confidence(
        magnitude, frequencies, frame_index,
        hop_seconds=hop_seconds, config=HatCandidateConfidence(),
    )
    features = inspected.get("features")
    if not features:
        return {"accepted": False, "reason": inspected["reason"],
                "ranker_probability": None, "ranker_schema": SCHEMA}
    probability = model.probability(features)
    return {
        "accepted": probability >= model.decision_threshold,
        "reason": "passed" if probability >= model.decision_threshold else "below_frozen_ranker_threshold",
        "ranker_probability": round(probability, 8),
        "ranker_schema": SCHEMA,
    }


def json_sha256(data: dict) -> str:
    return hashlib.sha256(json.dumps(
        data, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()
