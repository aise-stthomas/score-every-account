# score-every-account

A lab from *AI Systems Engineering* (University of St. Thomas). One weights file, two
placements: the churn score as a nightly batch run into a bucket, and the same score
behind a URL, one request at a time. **Start with [LAB.md](LAB.md).**

```bash
uv sync                          # Python 3.12, uv: https://docs.astral.sh/uv/
uv run build_dataset.py          # the training set, joined point in time
uv run train.py                  # the weights file
uv run src/function/handler.py   # one score, through the Lambda event shape, no AWS
```

No model key is needed: the scorer is a logistic regression in `src/model/weights.json`.
The AWS parts (a function, a URL, a bucket, a calendar rule) use the Learner Lab; see
*Configuring AWS* in the course guide.

| Where | What |
|---|---|
| `src/model/` | `features.py` (the one feature function, and the two joins), `score.py`, `batch.py` (the nightly node), `weights.json`, `features_latest.jsonl` (last night's table) |
| `src/function/` | the FastAPI app, the Lambda handler, a local server |
| `data/tables/` | the four tables: accounts, features, inference, labels (synthetic) |
| `data/datasets/`, `data/runs/`, `data/fixtures/` | what you build: training sets, run records, served scores |
| `build_dataset.py` `train.py` | Parts 1 and 2 |
| `run_batch.py` `record.py` `latency.py` `consistency.py` | Parts 3 and 4 |
| `deploy.sh` `call.sh` `schedule.sh` `teardown.sh` | the AWS side |
