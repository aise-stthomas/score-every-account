"""Record: score a sample of accounts and keep every served score, with both clocks.

    uv run record.py --runs 1                                   # in this process, no URL -> data/fixtures/local/
    uv run record.py --provider http --runs 3                   # the deployed function -> data/fixtures/http/
    uv run record.py --provider http --url http://127.0.0.1:9000/score --runs 1    # the local server
    uv run record.py --provider http --name http-cold --runs 1  # any condition, named yourself

The sample is the first N accounts of data/nights/2026-10-05.jsonl (default 50). Over HTTP
every record carries the function's own clocks (init, elapsed) and client_ms, the round
trip measured here. Calls to a deployed function URL are signed with your AWS session
credentials; a local server needs no signature.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from src.harness import fixtures

load_dotenv()
NIGHT = Path("data/nights/2026-10-05.jsonl")


def _signer():
    try:
        import botocore.session
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest
    except ImportError:
        return None
    creds = botocore.session.get_session().get_credentials()
    if creds is None:
        return None
    auth = SigV4Auth(creds, "lambda", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))

    def sign(url: str, body: bytes, headers: dict) -> dict:
        req = AWSRequest(method="POST", url=url, data=body, headers=headers)
        auth.add_auth(req)
        return dict(req.headers)
    return sign


_SIGN = None


def call_http(url: str, token: str | None, account_id: str, timeout: float) -> dict:
    global _SIGN
    body = json.dumps({"account_id": account_id}).encode()
    headers = {"content-type": "application/json"}
    if token:
        headers["x-lab-token"] = token
    if "lambda-url" in url:
        if _SIGN is None:
            _SIGN = _signer() or (lambda u, b, h: h)
        headers = _SIGN(url, body, headers)
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            rec = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        rec = {"account_id": account_id, "score": None, "error": f"HTTP {e.code}: {e.read().decode(errors='replace')[:200]}"}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        rec = {"account_id": account_id, "score": None, "error": f"{type(e).__name__}: {e}"}
    rec["client_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return rec


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--provider", choices=["local", "http"], default="local")
    p.add_argument("--url", default=os.environ.get("LAB_URL"))
    p.add_argument("--token", default=os.environ.get("LAB_TOKEN"))
    p.add_argument("--name", help="the condition; default: local or http")
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--n", type=int, default=50, help="accounts in the sample")
    p.add_argument("--timeout", type=float, default=30)
    p.add_argument("--fresh", action="store_true", help="discard this condition's fixtures first (recording resumes otherwise)")
    args = p.parse_args()
    name = args.name or args.provider
    if args.provider == "http" and not args.url:
        raise SystemExit("no URL: run ./deploy.sh, or pass --url")
    ids = [json.loads(l)["account_id"] for l in NIGHT.read_text().splitlines() if l.strip()][: args.n]
    if args.provider == "local":
        from src.function.app import score_one
    for run in range(1, args.runs + 1):
        path = fixtures.run_path(name, run)
        if args.fresh and path.exists():
            path.unlink()
        done = fixtures.recorded_ids(path)
        todo = [i for i in ids if i not in done]
        print(f"{name} run {run}: {len(done)} recorded, {len(todo)} to go  ({args.url if args.provider == 'http' else 'in this process'})", flush=True)
        for aid in todo:
            if args.provider == "http":
                rec = call_http(args.url, args.token, aid, args.timeout)
            else:
                t0 = time.perf_counter(); rec = score_one(aid); rec["local_ms"] = round((time.perf_counter() - t0) * 1000, 3)
            rec.update({"run": run, "condition": name})
            fixtures.append(path, rec)
            fn = rec.get("function") or {}
            tag = "cold" if fn.get("cold_start") else ("warm" if fn else "")
            ms = f"{rec.get('client_ms', rec.get('local_ms', '?'))} ms"
            what = f"{rec['score']:.3f} {rec.get('decision', '')}" if rec.get("score") is not None else f"error: {rec.get('error', '')[:60]}"
            print(f"  {aid}  {what:16s} {ms:>10s} {tag}", flush=True)


if __name__ == "__main__":
    main()
