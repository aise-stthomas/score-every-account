"""Fit the churn scorer: a logistic regression over four features, pure Python.

    uv run train.py                                        # on data/datasets/point-in-time.jsonl -> src/model/weights.json
    uv run train.py --dataset data/datasets/latest.jsonl --no-save    # see what the lazy join teaches

Held-out accounts (one in five, by a hash of the id) are never trained on; the numbers
printed are theirs: precision at k (of the k highest-scored held-out accounts, the share
that cancelled) and recall at k. The weights file records which dataset it was fitted to.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

from src.model.features import FEATURES
from src.model.score import WEIGHTS_PATH, score_vector, weights_hash


def held_out(account_id: str) -> bool:
    return int(hashlib.sha256(account_id.encode()).hexdigest(), 16) % 5 == 0


def fit(X: list[list[float]], y: list[int], epochs: int = 400, lr: float = 0.3) -> dict:
    n, d = len(X), len(X[0])
    mean = [sum(r[j] for r in X) / n for j in range(d)]
    std = [max(1e-9, math.sqrt(sum((r[j] - mean[j]) ** 2 for r in X) / n)) for j in range(d)]
    Z = [[(r[j] - mean[j]) / std[j] for j in range(d)] for r in X]
    w, b = [0.0] * d, 0.0
    for _ in range(epochs):
        gw, gb = [0.0] * d, 0.0
        for z, yi in zip(Z, y):
            p = 1 / (1 + math.exp(-(b + sum(wj * zj for wj, zj in zip(w, z)))))
            e = p - yi
            gb += e
            for j in range(d):
                gw[j] += e * z[j]
        b -= lr * gb / n
        w = [wj - lr * gj / n for wj, gj in zip(w, gw)]
    return {"features": FEATURES, "mean": mean, "std": std, "weights": w, "bias": b}


def at_k(scored: list[tuple[float, int]], k: int) -> tuple[float, float]:
    top = sorted(scored, key=lambda t: -t[0])[:k]
    hits = sum(y for _, y in top)
    pos = sum(y for _, y in scored)
    return hits / k, (hits / pos if pos else 0.0)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", default="data/datasets/point-in-time.jsonl")
    p.add_argument("--no-save", action="store_true", help="print the numbers; do not write weights.json")
    p.add_argument("--k", type=int, help="k for precision at k (default: one in ten of the held-out accounts)")
    args = p.parse_args()
    rows = [json.loads(l) for l in Path(args.dataset).read_text().splitlines() if l.strip()]
    hpath = Path(args.dataset).with_suffix(".hash")
    dhash = hpath.read_text().strip() if hpath.exists() else "?"
    train = [r for r in rows if not held_out(r["account_id"])]
    test = [r for r in rows if held_out(r["account_id"])]
    X = [[float(r[f]) for f in FEATURES] for r in train]
    y = [int(r["cancelled"]) for r in train]
    t0 = time.perf_counter()
    w = fit(X, y)
    w["model_version"] = "v12"
    w["dataset"] = {"path": args.dataset, "hash": dhash, "rows": len(train)}
    w["trained_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    w["weights_hash"] = weights_hash(w)
    scored = [(score_vector([float(r[f]) for f in FEATURES], w), int(r["cancelled"])) for r in test]
    k = args.k or max(1, len(test) // 10)
    prec, rec = at_k(scored, k)
    print(f"fitted on {len(train)} accounts from {args.dataset} (hash {dhash}) in {time.perf_counter() - t0:.1f} s")
    print(f"weights: " + "  ".join(f"{f} {wi:+.2f}" for f, wi in zip(FEATURES, w["weights"])) + f"  bias {w['bias']:+.2f}")
    print(f"held out: {len(test)} accounts, {sum(y for _, y in scored)} cancelled")
    print(f"precision at {k}: {prec:.0%}   recall at {k}: {rec:.0%}   (of the {k} highest-scored held-out accounts, the share that cancelled; of the cancelled, the share in that {k})")
    if not args.no_save:
        Path(WEIGHTS_PATH).write_text(json.dumps(w, indent=1) + "\n")
        print(f"wrote {WEIGHTS_PATH}  weights_hash {w['weights_hash']}")


if __name__ == "__main__":
    main()
