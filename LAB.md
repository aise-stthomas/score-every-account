# Lab: score every account, nightly and at the request

One trained model, one number per account: how likely is this account to cancel in the
next 90 days. Tonight the same weights file goes into two placements, a nightly batch run
and a per-request URL, and you measure what each one gives you. Write down three things
by the end: **the batch run's record**, **the online score's latency**, and whether
**served equals recomputed**, exactly.

**What this lab shows.**

1. **The training set is a join, and the join is the rule.** Built with the lazy join
   the number lies; built point in time it tells the truth, and the truth is lower.
2. **A batch run is one node of a job**, idempotent by construction: run it twice, get one
   scores file, with the run id and the weights hash on every row, and a record a person
   can read in the morning.
3. **The same weights behind a URL answer in milliseconds**, and the cold start is the
   weights load. Beside the previous lab's seconds, this is what a trained scorer costs.
4. **This model is deterministic.** A served score recomputed from its logged inputs is
   the same number, not a close one. A difference is a bug, found by a test.

No model key is needed. Parts 0 to 2 need no AWS.

## Part 0: the arithmetic, before anything is deployed

On paper, for a business with **400,000 accounts**:

| | your number |
|---|---|
| nightly: seconds to score every account at 10,000 scores a second | |
| nightly: function-seconds a month, and what that costs at the Lambda price you look up | |
| online: 2,000 cancellation-page visits a day: invocations a month | |
| online: the latency budget for one score, if the page has 100 ms for it | |
| the age of the feature table when the page reads it, if the nightly run finishes at 03:30 | |

Keep it; Part 5 comes back to it.

## Part 1: fit it

The tables are in `data/tables/`: `accounts`, `features` (one row per account per week,
as the weeks went by), `inference` (one prediction per account, made by an older model
at some moment in the summer), and `labels` (whether the account cancelled within 90
days, and when the truth arrived). Read a few rows of each.

```bash
uv run build_dataset.py            # the training set: inference ⋈ features (point in time) ⋈ labels
uv run train.py                    # a logistic regression, pure Python -> src/model/weights.json
```

Open `src/model/weights.json`. It is a few numbers, the feature names, and the hash of
the dataset it was fitted to. Write down **precision at k** on the held-out accounts: of
the k highest-scored accounts the model never trained on, the share that cancelled.

## Part 2: join it the wrong way, and see the number lie

Build the same training set with the lazy join, the one that takes each account's newest
feature row whatever its date, and fit on that:

```bash
uv run build_dataset.py --join latest
uv run train.py --dataset data/datasets/latest.jsonl --no-save
```

The number is far better. It is also false. Look at `build_dataset.py`'s output: how many
feature rows are dated **after** the prediction they are joined to? Then look at what
those rows contain for a cancelled account (`grep` one in `data/tables/features.jsonl`):
after cancelling, the account's sessions go to zero and a refund appears. The lazy join
hands the model the future, the model learns to read it, and in production the future is
not available.

The two joins are two functions in `src/model/features.py`, five lines apart. Read them.
The honest one is the point-in-time join: the newest row that existed **when the
prediction was made**. Keep the weights file from Part 1; it was fitted on that.

## Part 3: the nightly run

Start a Learner Lab session, paste the CLI credentials into `~/.aws/credentials`, then:

```bash
./deploy.sh
```

Read what it prints. It makes a bucket, installs the dependencies for Lambda's Linux,
zips them with `src/` (the weights file and last night's feature table ride inside), and
creates the function with a URL. Then run one night:

```bash
uv run run_batch.py data/nights/2026-10-05.jsonl
```

The night's file goes to the bucket; the function reads it, scores every account, and
writes three things back: `scores/run-2026-10-05.jsonl` (every row with the run id, the
as-of, the model version and the weights hash), `runs/2026-10-05.json` (the run record:
rows, share above the threshold, seconds, the check), and `scores/current.json` (the
pointer, moved only if the check passed). Both land in `data/runs/` too. Read the record.

Now run it again, the same night:

```bash
uv run run_batch.py data/nights/2026-10-05.jsonl
uv run run_batch.py --list-runs
```

One run record for that night, one scores file, replaced. Nothing was appended. That is
what makes a retry safe, and a scheduler retries.

*No AWS?* `uv run run_batch.py data/nights/2026-10-05.jsonl --local` runs the same node in
your process and writes to `data/runs/`.

## Part 4: the same weights, one request at a time

```bash
./call.sh                                      # one signed request: one account's score
uv run record.py --provider http --runs 3      # 150 requests over the URL -> data/fixtures/http/
uv run latency.py http
```

Per run: the cold start, split into init (the imports and the weights load) and the
score; warm p50 and p95 of the round trip, beside the function's own time for the dot
product. Put the numbers next to the previous lab's: seconds for a language model,
milliseconds for this. If no run shows a cold start, `./deploy.sh --recycle` and record
once more.

Every `/score` response carries the feature vector as served, the row's as-of date and
its age in days, the model version and the weights hash. The function also prints the
same thing as one JSON line per request: that is the inference table, in the log. Now:

```bash
uv run consistency.py http
```

For every served score, the score is recomputed here from the served feature vector and
this repository's weights. **Exactly equal**, every one. Change one number in
`src/model/weights.json`, run it again, and watch it fail: the weights hash on every
record says which weights were served, and it no longer matches.

## Part 5: schedule it

```bash
./schedule.sh                     # nightly at 03:00 UTC
./schedule.sh "rate(5 minutes)"   # or: fire it in a few minutes so you can see it tonight
./schedule.sh --status            # the rule, and every run record in the bucket
```

One EventBridge rule, the function as its target, invoked with a constant event the
handler recognises. That is a calendar and one node. Look at the run record it produces,
then write two sentences from Part 0: when the page reads the table at 09:00, how old is
it, and what should the page do if last night's run did not publish?

Then take it down:

```bash
./schedule.sh --off
./teardown.sh                     # the function, the URL, the rule; keeps the bucket
./teardown.sh --bucket            # and the bucket
```

## Keep

- precision at k under both joins, and one sentence on why the better number is false
- the run record from Part 3, and the listing after the second run
- cold start, warm p50 and p95 from Part 4; the consistency result
- the run record the schedule produced, and your Part 5 sentences

## If something breaks

| Symptom | What it is |
|---|---|
| `aws sts get-caller-identity failed` | No session, or the pasted credentials expired. Start a session and paste again. |
| `AccessDenied` on `create-function` or `create-bucket` | The role name is not `LabRole`, or the bucket name is taken globally. `aws iam list-roles --query 'Roles[].RoleName'`; or set `BUCKET=` in `.env` to another name. |
| `HTTP 401` from `record.py` | The token in `.env` does not match the function's. `./deploy.sh` again. |
| `HTTP 403` on every call | The request was not signed, or the session expired. Start a session, paste credentials, run again. |
| `HTTP 404 no feature row` | The account id is not in last night's table (`src/model/features_latest.jsonl`). Use one from `data/nights/`. |
| `BUCKET is not set on the function` | Deployed before the bucket line existed. `./deploy.sh` again. |
| the rule never fires | `./schedule.sh --status` shows the rule; `aws logs tail /aws/lambda/score-every-account --since 1h` shows whether it was invoked. The Learner Lab allows EventBridge rules; if `add-permission` was refused, say so in your write-up and run the night by hand. |
| `consistency.py` reports mismatches | The deployed weights differ from the repository's: you retrained after deploying. `./deploy.sh` again, or check out the weights file you deployed. |
