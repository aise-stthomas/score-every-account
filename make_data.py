"""Make the lab's tables. Instructor-run; the output is committed under data/.

    uv run make_data.py

Synthetic, seeded. A subscription business with 2,000 accounts. Twelve weekly feature
rows per account (the features table), one prediction per account from an older model
(the inference table), and the truth, which arrives later (the labels table). The truth
depends on what the account looked like *when the prediction was made*; after a
cancellation the account goes quiet, which is exactly the leak Part 2 shows.
"""
from __future__ import annotations

import json
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path

random.seed(4)
N = 2000
WEEKS = [date(2026, 7, 6) + timedelta(weeks=k) for k in range(12)]      # Mondays, Jul 6 .. Sep 21
T = Path("data/tables"); T.mkdir(parents=True, exist_ok=True)
Path("data/nights").mkdir(parents=True, exist_ok=True)


def sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-z))


accounts, features, inference, labels = [], [], [], []
for i in range(N):
    aid = f"A-{10000 + i}"
    plan = random.choice(["basic", "basic", "pro", "team"])
    tenure0 = max(1, int(random.expovariate(1 / 18)))
    sessions0 = max(0, int(random.gauss(12, 6)))
    tickets0 = min(6, int(random.expovariate(1 / 0.8)))
    refunds0 = 1 if random.random() < 0.08 else 0
    accounts.append({"account_id": aid, "plan": plan, "since": (WEEKS[0] - timedelta(days=30 * tenure0)).isoformat()})

    # the prediction: made by the old model (v11) at a random moment between week 4 and week 8
    k = random.randint(3, 7)
    pred_time = datetime.combine(WEEKS[k], datetime.min.time()) + timedelta(hours=random.randint(8, 20), minutes=random.randint(0, 59))
    # what the account looked like then
    tenure = tenure0 + k // 4
    sessions = max(0, sessions0 + int(random.gauss(0, 2)))
    tickets = max(0, tickets0 + (1 if random.random() < 0.15 else 0))
    refunds = refunds0 + (1 if random.random() < 0.05 else 0)
    # the truth: cancels within 90 days, from the point-in-time features plus noise
    z = -0.9 - 0.05 * tenure + 0.5 * tickets + 1.0 * refunds - 0.14 * sessions + random.gauss(0, 0.5)
    cancelled = random.random() < sigmoid(z)
    cancel_day = pred_time + timedelta(days=random.randint(5, 35)) if cancelled else None   # most are visible in the table by the last week
    arrived = (cancel_day if cancelled else pred_time + timedelta(days=90))

    # the twelve weekly rows, written as the weeks went by
    for wk, d in enumerate(WEEKS):
        s = max(0, sessions0 + int(random.gauss(0, 2)) + (wk - k))
        t = max(0, tickets0 + (1 if random.random() < 0.1 else 0))
        r = refunds0 + (1 if wk >= k and random.random() < 0.05 else 0)
        if cancelled and datetime.combine(d, datetime.min.time()) >= cancel_day:   # after cancelling, the account goes quiet
            s = 0
            r = r + 1
        features.append({"account_id": aid, "as_of": d.isoformat(), "tenure_months": tenure0 + wk // 4,
                         "tickets_90d": t, "refunds_90d": r, "sessions_30d": s})
    old_score = round(sigmoid(z - 0.4 + random.gauss(0, 0.8)), 4)
    inference.append({"account_id": aid, "time": pred_time.isoformat(timespec="minutes"), "model_version": "v11", "score": old_score})
    labels.append({"account_id": aid, "cancelled": cancelled, "arrived_at": arrived.date().isoformat()})

for name, rows in [("accounts", accounts), ("features", features), ("inference", inference), ("labels", labels)]:
    (T / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"{name:10s} {len(rows):>6d} rows")

# last night's table, as the online function sees it: the newest row per account
latest = {}
for r in features:
    if r["account_id"] not in latest or r["as_of"] > latest[r["account_id"]]["as_of"]:
        latest[r["account_id"]] = r
night = [latest[a["account_id"]] for a in accounts]
Path("src/model/features_latest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in night))
Path("data/nights/2026-10-05.jsonl").write_text("".join(json.dumps(r) + "\n" for r in night))
print(f"features_latest {len(night)} rows (as_of {night[0]['as_of']}) → src/model/ and data/nights/2026-10-05.jsonl")
print(f"base rate: {sum(l['cancelled'] for l in labels) / N:.1%} cancelled within 90 days")
