"""Consistency: served equals recomputed, exactly.

    uv run consistency.py http        # every served score under data/fixtures/http/, recomputed here

For each served score, recompute from the feature vector the function returned, with the
weights file in this repository. This model is deterministic: the numbers must be equal,
not close. A mismatch means the function and the repository disagree about the weights or
the feature code, and that is a bug, not noise. The weights hash on every record says
which weights were served.
"""
from __future__ import annotations

import sys

from src.harness import fixtures
from src.model.features import FEATURES
from src.model.score import load_weights, score_vector, weights_hash


def main() -> None:
    w = load_weights()
    wh = weights_hash(w)
    bad = 0
    for cond in (sys.argv[1:] or ["http"]):
        runs = fixtures.runs(cond)
        if not runs:
            print(f"no fixtures under data/fixtures/{cond}")
            continue
        for name, recs in runs:
            n = same = hash_ok = 0
            for r in recs:
                if r.get("score") is None:
                    continue
                n += 1
                x = [float(r["features"][f]) for f in FEATURES]
                again = score_vector(x, w)
                if again == r["score"]:
                    same += 1
                else:
                    bad += 1
                    print(f"  MISMATCH {r['account_id']}: served {r['score']!r}, recomputed {again!r}")
                hash_ok += r.get("weights_hash") == wh
            print(f"{cond}/{name}: {same} of {n} served scores recomputed exactly · {hash_ok} of {n} carry this repository's weights hash ({wh})")
    print("consistent" if not bad else f"{bad} mismatches: the served weights or feature code differ from this repository")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
