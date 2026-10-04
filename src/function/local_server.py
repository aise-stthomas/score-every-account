"""Run the app on a local URL, with Swagger.

    uv run src/function/local_server.py            # http://127.0.0.1:9000 · docs at /docs

Then, in another terminal:  uv run record.py --provider http --url http://127.0.0.1:9000/score --runs 1

Same app the deploy script ships. What it does not reproduce: the cold start and the
network. /batch needs a bucket, so it only works deployed (or use run_batch.py --local).
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

if __name__ == "__main__":
    import uvicorn
    os.environ["LAB_TOKEN"] = ""
    port = int(os.environ.get("PORT", "9000"))
    print(f"try it at http://127.0.0.1:{port}/docs")
    uvicorn.run("src.function.app:app", host="127.0.0.1", port=port, log_level="warning")
