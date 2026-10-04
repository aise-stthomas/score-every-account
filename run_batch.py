"""The nightly run, started by hand.

    uv run run_batch.py data/nights/2026-10-05.jsonl            # upload the night's file, run /batch on it, fetch the result
    uv run run_batch.py data/nights/2026-10-05.jsonl --local    # the same node, in this process, no AWS -> data/runs/
    uv run run_batch.py --list-runs                             # every run record in the bucket, and the current pointer

Deployed: the file goes to s3://<bucket>/accounts/<night>.jsonl (and accounts/nightly.jsonl,
which the schedule reads); the function writes scores/run-<night>.jsonl, runs/<night>.json
and, if the check passes, scores/current.json. Run it twice over the same night and look:
one scores file, replaced, never a second copy. The scores file and the record are
downloaded to data/runs/ so you can read them.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
RUNS = Path("data/runs")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("night", nargs="?", help="data/nights/<date>.jsonl")
    p.add_argument("--local", action="store_true", help="run the node in this process, no AWS")
    p.add_argument("--list-runs", action="store_true")
    p.add_argument("--run-id", help="default: the night's date")
    args = p.parse_args()
    RUNS.mkdir(parents=True, exist_ok=True)

    if args.list_runs:
        import boto3
        s3 = boto3.client("s3"); bucket = os.environ["BUCKET"]
        keys = [o["Key"] for o in s3.list_objects_v2(Bucket=bucket, Prefix="runs/").get("Contents", [])]
        for k in sorted(keys):
            rec = json.loads(s3.get_object(Bucket=bucket, Key=k)["Body"].read().decode())
            print(f"  {rec['run_id']}  rows {rec['rows']:>6}  above {rec['share_above_threshold']:.1%}  {rec['check']:40s} {'published' if rec['published'] else 'not published'}")
        try:
            cur = json.loads(s3.get_object(Bucket=bucket, Key="scores/current.json")["Body"].read().decode())
            print(f"  current run: {cur['run_id']} (published {cur['published_at']})")
        except Exception:  # noqa: BLE001
            print("  current run: none yet")
        scores = [o["Key"] for o in s3.list_objects_v2(Bucket=bucket, Prefix="scores/run-").get("Contents", [])]
        print(f"  scores files in the bucket: {len(scores)}")
        return

    if not args.night:
        sys.exit("which night? uv run run_batch.py data/nights/2026-10-05.jsonl")
    night = Path(args.night)
    run_id = args.run_id or night.stem
    rows = [json.loads(l) for l in night.read_text().splitlines() if l.strip()]

    if args.local:
        from src.model import batch as B
        from src.model.score import load_weights
        prev_path = RUNS / "current.json"
        previous = None
        if prev_path.exists():
            cur = json.loads(prev_path.read_text())
            previous = json.loads((RUNS / f"{cur['run_id']}.json").read_text())
        scores, record = B.run(rows, load_weights(), run_id, rows[0]["as_of"], previous=previous)
        (RUNS / f"run-{run_id}.jsonl").write_text(B.to_jsonl(scores))      # replaced, never appended
        (RUNS / f"{run_id}.json").write_text(json.dumps(record, indent=1) + "\n")
        if record["published"]:
            prev_path.write_text(json.dumps({"run_id": run_id, "published_at": record["finished_at"]}) + "\n")
        print(json.dumps(record, indent=1))
        print(f"→ data/runs/run-{run_id}.jsonl ({len(scores)} rows), data/runs/{run_id}.json, data/runs/current.json")
        return

    import boto3
    from record import _signer
    bucket = os.environ.get("BUCKET"); url = os.environ.get("LAB_URL"); token = os.environ.get("LAB_TOKEN")
    if not (bucket and url):
        sys.exit("no BUCKET or LAB_URL in .env: run ./deploy.sh first (or use --local)")
    s3 = boto3.client("s3")
    key = f"accounts/{night.name}"
    s3.upload_file(str(night), bucket, key)
    s3.upload_file(str(night), bucket, "accounts/nightly.jsonl")
    print(f"uploaded {night} → s3://{bucket}/{key} (and accounts/nightly.jsonl for the schedule)")
    body = json.dumps({"key": key, "run_id": run_id}).encode()
    headers = {"content-type": "application/json", "x-lab-token": token or ""}
    burl = url.rsplit("/", 1)[0] + "/batch"
    headers = (_signer() or (lambda u, b, h: h))(burl, body, headers)
    req = urllib.request.Request(burl, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        record = json.loads(resp.read().decode())
    print(json.dumps(record, indent=1))
    s3.download_file(bucket, f"scores/run-{run_id}.jsonl", str(RUNS / f"run-{run_id}.jsonl"))
    (RUNS / f"{run_id}.json").write_text(json.dumps(record, indent=1) + "\n")
    print(f"→ data/runs/run-{run_id}.jsonl, data/runs/{run_id}.json   (uv run run_batch.py --list-runs to see the bucket)")


if __name__ == "__main__":
    main()
