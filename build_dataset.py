"""Build the training set: the inference table joined with the features table and the labels.

    uv run build_dataset.py --join point-in-time     # the honest join -> data/datasets/point-in-time.jsonl
    uv run build_dataset.py --join latest            # the lazy join   -> data/datasets/latest.jsonl

One row per prediction: the account, the time the prediction was made, the feature row
the join chose, and the label. The two joins differ in one line (src/model/features.py):
point-in-time takes the newest feature row that existed when the prediction was made;
latest takes the newest row there is, which for a cancelled account was written after it
cancelled. Every dataset file ends with its hash, so a weights file can say what it was
fitted to.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from src.model import features as F

T = Path("data/tables")
OUT = Path("data/datasets")


def read(name: str) -> list[dict]:
    return [json.loads(l) for l in (T / f"{name}.jsonl").read_text().splitlines() if l.strip()]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--join", choices=["point-in-time", "latest"], default="point-in-time")
    args = p.parse_args()

    by_account: dict[str, list[dict]] = defaultdict(list)
    for r in read("features"):
        by_account[r["account_id"]].append(r)
    labels = {l["account_id"]: l for l in read("labels")}

    rows, missing = [], 0
    for pred in read("inference"):
        frows = by_account[pred["account_id"]]
        chosen = F.point_in_time(frows, pred["time"]) if args.join == "point-in-time" else F.latest(frows)
        if chosen is None:
            missing += 1
            continue
        lab = labels[pred["account_id"]]
        rows.append({"account_id": pred["account_id"], "time": pred["time"], "features_as_of": chosen["as_of"],
                     **{f: chosen[f] for f in F.FEATURES}, "cancelled": lab["cancelled"], "label_arrived_at": lab["arrived_at"]})
    OUT.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(r) + "\n" for r in rows)
    h = hashlib.sha256(body.encode()).hexdigest()[:12]
    path = OUT / f"{args.join}.jsonl"
    path.write_text(body)
    (OUT / f"{args.join}.hash").write_text(h + "\n")
    after = sum(1 for r in rows if r["features_as_of"] > r["time"][:10])
    print(f"{args.join}: {len(rows)} rows, {missing} predictions with no feature row yet → {path}  hash {h}")
    print(f"  feature rows dated after the prediction: {after} of {len(rows)}"
          + ("   ← these are from the future" if after else ""))
    print(f"  cancelled: {sum(r['cancelled'] for r in rows)} ({sum(r['cancelled'] for r in rows) / len(rows):.1%})")


if __name__ == "__main__":
    main()
