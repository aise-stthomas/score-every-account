"""The churn scorer as a web service: one FastAPI app that runs on your laptop (uvicorn)
and on AWS Lambda (through Mangum, see handler.py) without changing a line.

    POST /score   {"account_id": "A-10042"}   -> the score for one account, from last night's
                  feature row, plus everything the inference table needs: the feature vector
                  as served, the row's as_of and age, the model version, the weights hash
    POST /batch   {"key": "accounts/2026-10-05.jsonl", "run_id": "2026-10-05"}
                  -> score every row in that file in the bucket; write scores/run-<id>.jsonl,
                  runs/<id>.json, and move scores/current.json if the check passes
    GET  /        a health check: no scoring
    GET  /docs    Swagger UI (locally; the deployed URL needs a signed request, see call.sh)

Every /score call prints one JSON line: that is the inference table, in CloudWatch.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_T0 = time.perf_counter()
from fastapi import Depends, FastAPI, Header, HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from src.model import batch as B  # noqa: E402
from src.model.features import FEATURES, vector  # noqa: E402
from src.model.score import load_weights, score_vector, weights_hash  # noqa: E402

WEIGHTS = load_weights()                       # the weights load is the cold start
WEIGHTS_HASH = weights_hash(WEIGHTS)
_LATEST_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "model", "features_latest.jsonl")
LATEST = {r["account_id"]: r for r in (json.loads(l) for l in open(_LATEST_PATH).read().splitlines() if l.strip())}
INIT_MS = round((time.perf_counter() - _T0) * 1000)
INVOCATIONS = 0
THRESHOLD = float(os.environ.get("THRESHOLD", "0.75"))   # the policy table, as one number

app = FastAPI(title="score-every-account", version="1.0", description="The churn score, behind a URL.")


class ScoreRequest(BaseModel):
    account_id: str = Field(..., examples=["A-10042"])


class BatchRequest(BaseModel):
    key: str = Field(..., examples=["accounts/2026-10-05.jsonl"])
    run_id: str | None = Field(default=None, examples=["2026-10-05"])


def check_token(x_lab_token: str | None = Header(default=None)) -> None:
    expected = os.environ.get("LAB_TOKEN")
    if expected and x_lab_token != expected:
        raise HTTPException(status_code=401, detail="bad or missing x-lab-token header")


def _meta(started: float, cold: bool) -> dict:
    return {"cold_start": cold, "init_ms": INIT_MS, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "invocation": INVOCATIONS, "model_version": WEIGHTS["model_version"], "weights_hash": WEIGHTS_HASH}


@app.get("/")
def health() -> dict:
    global INVOCATIONS
    started = time.perf_counter(); cold = INVOCATIONS == 0; INVOCATIONS += 1
    return {"ok": True, "accounts_in_table": len(LATEST), "table_as_of": next(iter(LATEST.values()))["as_of"], "function": _meta(started, cold)}


def score_one(account_id: str, today: str | None = None) -> dict:
    row = LATEST.get(account_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no feature row for {account_id}")
    x = vector(row)
    s = score_vector(x, WEIGHTS)
    today = today or date.today().isoformat()
    age = (date.fromisoformat(today) - date.fromisoformat(row["as_of"])).days
    return {"account_id": account_id, "score": s, "decision": "offer" if s >= THRESHOLD else "no offer", "threshold": THRESHOLD,
            "features": dict(zip(FEATURES, x)), "as_of": row["as_of"], "age_days": age,
            "model_version": WEIGHTS["model_version"], "weights_hash": WEIGHTS_HASH}


@app.post("/score")
def score_endpoint(req: ScoreRequest, _: None = Depends(check_token)) -> dict:
    global INVOCATIONS
    started = time.perf_counter(); cold = INVOCATIONS == 0; INVOCATIONS += 1
    rec = score_one(req.account_id)
    rec["function"] = _meta(started, cold)
    print(json.dumps({"table": "inference", "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **{k: rec[k] for k in ("account_id", "features", "as_of", "score", "decision", "model_version", "weights_hash")}}))
    return rec


def run_batch(key: str, run_id: str | None) -> dict:
    """One node of the nightly job: read the night's file from the bucket, score it, write
    the scores and the run record back, and move the pointer if the check passes."""
    import boto3  # in the Lambda runtime already; installed locally by uv
    bucket = os.environ.get("BUCKET")
    if not bucket:
        raise HTTPException(status_code=500, detail="BUCKET is not set on the function")
    s3 = boto3.client("s3")
    run_id = run_id or date.today().isoformat()
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode()
    rows = [json.loads(l) for l in body.splitlines() if l.strip()]
    as_of = rows[0]["as_of"] if rows else run_id
    previous = None
    try:
        previous = json.loads(s3.get_object(Bucket=bucket, Key="scores/current.json")["Body"].read().decode())
        previous = json.loads(s3.get_object(Bucket=bucket, Key=f"runs/{previous['run_id']}.json")["Body"].read().decode())
    except Exception:  # noqa: BLE001  (no current run yet)
        previous = None
    scores, record = B.run(rows, WEIGHTS, run_id, as_of, previous=previous)
    record["input_key"] = key
    s3.put_object(Bucket=bucket, Key=f"scores/run-{run_id}.jsonl", Body=B.to_jsonl(scores).encode())   # replaced, never appended
    s3.put_object(Bucket=bucket, Key=f"runs/{run_id}.json", Body=json.dumps(record, indent=1).encode())
    if record["published"]:
        s3.put_object(Bucket=bucket, Key="scores/current.json", Body=json.dumps({"run_id": run_id, "published_at": record["finished_at"]}).encode())
    print(json.dumps({"table": "runs", **record}))
    return record


@app.post("/batch")
def batch_endpoint(req: BatchRequest, _: None = Depends(check_token)) -> dict:
    global INVOCATIONS
    started = time.perf_counter(); cold = INVOCATIONS == 0; INVOCATIONS += 1
    record = run_batch(req.key, req.run_id)
    record["function"] = _meta(started, cold)
    return record
