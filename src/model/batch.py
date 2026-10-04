"""The batch run: score every account in a file, as one node of a nightly job.

Idempotent by construction: the output is keyed by the run id, so running the same night
twice replaces the scores file rather than appending to it. Every row carries the run id,
the as-of time, the model version and the weights hash. The run record is what the
scheduler and a person read in the morning; the check compares the share above the
threshold with the previous run and refuses to publish a run that moved too far.
"""
from __future__ import annotations

import json
import time

from .features import vector
from .score import score_vector, weights_hash

CHECK_TOLERANCE = 0.15   # a run whose share above the threshold moves more than this is not published


def run(rows: list[dict], w: dict, run_id: str, as_of: str, threshold: float = 0.5,
        previous: dict | None = None) -> tuple[list[dict], dict]:
    t0 = time.perf_counter()
    wh = weights_hash(w)
    scores = []
    for r in rows:
        scores.append({"account_id": r["account_id"], "run_id": run_id, "as_of": as_of,
                       "model_version": w["model_version"], "weights_hash": wh,
                       "score": score_vector(vector(r), w)})
    n = len(scores)
    above = sum(1 for s in scores if s["score"] >= threshold) / n if n else 0.0
    record = {"run_id": run_id, "as_of": as_of, "rows": n, "share_above_threshold": round(above, 4),
              "threshold": threshold, "model_version": w["model_version"], "weights_hash": wh,
              "seconds": round(time.perf_counter() - t0, 3), "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if previous and abs(previous.get("share_above_threshold", above) - above) > CHECK_TOLERANCE:
        record["check"] = f"refused: {above:.0%} above the threshold, previous run {previous['share_above_threshold']:.0%}"
        record["published"] = False
    else:
        record["check"] = "ok"
        record["published"] = True
    return scores, record


def to_jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(r) + "\n" for r in rows)
