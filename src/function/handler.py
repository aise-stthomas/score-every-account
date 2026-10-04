"""The Lambda entry point: the FastAPI app in app.py, adapted to Lambda's event shape by Mangum,
plus one non-HTTP event for the scheduler: {"batch": {"key": "...", "run_id": null}}.

Run this file directly to exercise the HTTP path on your laptop, with no AWS:

    uv run src/function/handler.py              # POST /score for one account, through the Lambda event shape
"""
from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from mangum import Mangum  # noqa: E402
from src.function.app import app, run_batch  # noqa: E402

_http = Mangum(app, lifespan="off")


def handler(event, context):
    if isinstance(event, dict) and "batch" in event:          # the nightly rule, not a request
        b = event["batch"] or {}
        return run_batch(b.get("key", "accounts/nightly.jsonl"), b.get("run_id"))
    return _http(event, context)


if __name__ == "__main__":
    body = open(os.path.join(os.path.dirname(__file__), "sample-event-body.json")).read()
    headers = {"content-type": "application/json"}
    if os.environ.get("LAB_TOKEN"):
        headers["x-lab-token"] = os.environ["LAB_TOKEN"]
    event = {"version": "2.0", "routeKey": "$default", "rawPath": "/score", "rawQueryString": "", "headers": headers,
             "requestContext": {"http": {"method": "POST", "path": "/score", "sourceIp": "127.0.0.1"}},
             "body": body, "isBase64Encoded": False}
    out = handler(event, None)
    print(out["statusCode"])
    print(json.dumps(json.loads(out["body"]), indent=2))
