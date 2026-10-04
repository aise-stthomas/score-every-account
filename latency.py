"""Latency: what the round trip cost, from the fixtures, per run.

    uv run latency.py http           # every run under data/fixtures/http/
    uv run latency.py http http-cold

Per run: cold starts (how many, how long, and how much of that was loading the weights),
warm calls (median and 95th percentile of the round trip, beside the function's own
elapsed time, which is the dot product), and errors. Compare with the previous lab: the
language model's seconds against this model's milliseconds.
"""
from __future__ import annotations

import sys

from src.harness import fixtures


def pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, round(q * (len(xs) - 1))))]


def main() -> None:
    for cond in (sys.argv[1:] or ["http"]):
        runs = fixtures.runs(cond)
        if not runs:
            print(f"no fixtures under data/fixtures/{cond}")
            continue
        print(f"\n{'=' * 78}\n{cond.upper()}")
        for name, recs in runs:
            http = [r for r in recs if "client_ms" in r]
            if not http:
                print(f"  {name}: recorded in-process; the score itself took p50 {pct([r['local_ms'] for r in recs], .5)} ms")
                continue
            ok = [r for r in http if r.get("score") is not None]
            errors = [r for r in http if r.get("score") is None]
            cold = [r for r in ok if r.get("function", {}).get("cold_start")]
            warm = [r for r in ok if r.get("function") and not r["function"].get("cold_start")]
            print(f"\n  {name}: {len(http)} calls · {len(ok)} completed · {len(errors)} errors")
            for r in cold:
                f = r["function"]
                print(f"    cold start   round trip {r['client_ms']:>8.1f} ms   = init {f['init_ms']} ms (imports + the weights load) + the score {f['elapsed_ms']} ms + the rest")
            if not cold:
                print("    cold start   none in this run (the sandbox was already warm)")
            if warm:
                rt = [r["client_ms"] for r in warm]; fe = [r["function"]["elapsed_ms"] for r in warm]
                print(f"    warm         round trip p50 {pct(rt, .5):>8.1f} ms · p95 {pct(rt, .95):>8.1f} ms · max {max(rt):>8.1f} ms")
                print(f"                 of which the score p50 {pct(fe, .5):>6.2f} ms   (the URL and the signature cost the difference)")
            for r in errors[:5]:
                print(f"    error        {r.get('error', '?')[:90]}")


if __name__ == "__main__":
    main()
