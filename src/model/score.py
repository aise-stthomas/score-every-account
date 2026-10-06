"""Score a feature vector with a weights file. Pure Python, deterministic: the same vector
and the same weights give the same number, every time, on every machine.

"Every machine" has to be engineered. The dot product is IEEE arithmetic, correctly rounded,
the same bits on every CPU. exp() is not: it is a library call, and glibc on Lambda's Linux
and libm on a Mac disagree in the last bit for some inputs, which the consistency check
catches as a one-ulp mismatch. So the sigmoid goes through the decimal module, whose exp is
correctly rounded by specification and ships with CPython, the same everywhere.

    weights.json: {"model_version", "features", "mean", "std", "weights", "bias", "weights_hash", ...}
"""
from __future__ import annotations

import hashlib
import json
import os
from decimal import Decimal, localcontext

from .features import FEATURES, vector

WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weights.json")


def load_weights(path: str = WEIGHTS_PATH) -> dict:
    w = json.loads(open(path).read())
    assert w["features"] == FEATURES, "weights.json was fitted to a different feature list"
    return w


def weights_hash(w: dict) -> str:
    body = json.dumps({k: w[k] for k in ("features", "mean", "std", "weights", "bias")}, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()[:12]


def score_vector(x: list[float], w: dict) -> float:
    z = w["bias"]
    for xi, m, s, wi in zip(x, w["mean"], w["std"], w["weights"]):
        z += wi * ((xi - m) / s)
    with localcontext() as ctx:
        ctx.prec = 24                                   # more than a double carries; exp is correctly rounded here
        return float(1 / (1 + Decimal(-z).exp()))      # Decimal(float) is exact; float(Decimal) is correctly rounded


def score_row(row: dict, w: dict) -> float:
    return score_vector(vector(row), w)
