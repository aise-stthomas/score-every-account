"""Fixtures: every served score, saved as it lands, under data/fixtures/<condition>/run-<k>.jsonl.

Record once, score many times. Nothing in here calls the function.
"""
from __future__ import annotations

import json
from pathlib import Path

FIXTURES = Path("data/fixtures")


def run_path(condition: str, run: int) -> Path:
    return FIXTURES / condition / f"run-{run}.jsonl"


def recorded_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {json.loads(line)["account_id"] for line in path.read_text().splitlines() if line.strip()}


def append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def runs(condition: str) -> list[tuple[str, list[dict]]]:
    out = []
    for path in sorted((FIXTURES / condition).glob("run-*.jsonl")):
        out.append((path.stem, [json.loads(l) for l in path.read_text().splitlines() if l.strip()]))
    return out
