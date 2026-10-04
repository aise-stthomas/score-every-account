"""The one feature function. Training and serving both import it; nothing computes a
feature anywhere else.

A feature row comes from the features table: one row per account per as_of, written by a
batch job. The request brings the account id and the time; this module turns the row the
system chose for that time into the vector the model reads.
"""
from __future__ import annotations

FEATURES = ["tenure_months", "tickets_90d", "refunds_90d", "sessions_30d"]


def vector(row: dict) -> list[float]:
    """The feature vector, in a fixed order, from a features-table row."""
    return [float(row[f]) for f in FEATURES]


def point_in_time(rows: list[dict], at: str) -> dict | None:
    """The newest row whose as_of is not after `at`: what the model could have known then.

    `rows` are one account's feature rows, any order; as_of and at are ISO dates/times, so
    string comparison is time order. Returns None if nothing was known yet.
    """
    known = [r for r in rows if r["as_of"] <= at]
    return max(known, key=lambda r: r["as_of"]) if known else None


def latest(rows: list[dict]) -> dict | None:
    """The newest row, whatever the time: the lazy join. Wrong for training; see LAB.md Part 2."""
    return max(rows, key=lambda r: r["as_of"]) if rows else None
