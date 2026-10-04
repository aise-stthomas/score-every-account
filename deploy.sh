#!/usr/bin/env bash
# Deploy the churn scorer as a function behind a URL, with a bucket for the nightly run,
# in the AWS Academy Learner Lab.
#
#   ./deploy.sh                    build the package, create or update the function and the bucket, print the URL
#   ./deploy.sh --threshold 0.5    the policy table, as one number (default 0.75)
#   ./deploy.sh --recycle          no rebuild: force every sandbox cold, so the next call is a cold start
#
# What it assumes: the AWS CLI with a live Learner Lab session pasted into ~/.aws/credentials
# (Configuring AWS, section 3) and uv. It uses the pre-created LabRole, never creates IAM
# anything, and stays in us-east-1. No model key: the scorer is a weights file.
set -euo pipefail
cd "$(dirname "$0")"

FN="${FUNCTION_NAME:-score-every-account}"
export AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
TIMEOUT=60; MEMORY=512; RECYCLE=0; THRESHOLD=0.75
while [ $# -gt 0 ]; do
  case "$1" in
    --threshold) THRESHOLD="$2"; shift 2 ;;
    --recycle) RECYCLE=1; shift ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac
done

command -v aws >/dev/null || { echo "aws CLI not found: brew install awscli (or see Configuring AWS)"; exit 1; }
command -v uv  >/dev/null || { echo "uv not found: see the README"; exit 1; }
[ -f src/model/weights.json ] || { echo "no weights.json: run  uv run train.py  first (Part 1)"; exit 1; }
touch .env; set -a; . ./.env; set +a
if [ -z "${LAB_TOKEN:-}" ]; then
  LAB_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  printf '\nLAB_TOKEN=%s\n' "$LAB_TOKEN" >> .env
  echo "made a LAB_TOKEN and saved it in .env (the function checks it on every request)"
fi
ACCOUNT="$(aws sts get-caller-identity --query Account --output text 2>/dev/null)" \
  || { echo "aws sts get-caller-identity failed: start a Learner Lab session and paste fresh credentials"; exit 1; }
ROLE="arn:aws:iam::${ACCOUNT}:role/LabRole"
BUCKET="${BUCKET:-aise-${ACCOUNT}-scores}"
ENV_VARS="Variables={LAB_TOKEN=${LAB_TOKEN},BUCKET=${BUCKET},THRESHOLD=${THRESHOLD},DEPLOYED_AT=$(date +%s)}"

if [ "$RECYCLE" = 1 ]; then
  aws lambda update-function-configuration --function-name "$FN" --environment "$ENV_VARS" >/dev/null
  aws lambda wait function-updated --function-name "$FN"
  echo "recycled: the next call to $FN is a cold start"; exit 0
fi

# --- the bucket: the nightly input, the scores, the run records -------------------------
if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  echo "bucket $BUCKET exists"
else
  aws s3api create-bucket --bucket "$BUCKET" >/dev/null && echo "created bucket $BUCKET"
fi
grep -q '^BUCKET=' .env && sed -i.bak "s|^BUCKET=.*|BUCKET=${BUCKET}|" .env && rm -f .env.bak || printf 'BUCKET=%s\n' "$BUCKET" >> .env

# --- build: the dependencies for Lambda's Linux, plus src/ (the weights file and last night's table ride inside it)
echo "building the package..."
rm -rf build && mkdir -p build/pkg
uv pip install --quiet --target build/pkg --python-platform x86_64-manylinux_2_28 --python-version 3.12 \
  "fastapi>=0.115" "mangum>=0.17"
cp -R src build/pkg/src
find build/pkg/src -name "__pycache__" -type d -prune -exec rm -rf {} +
( cd build/pkg && zip -qr ../function.zip . -x '*.pyc' -x '*/__pycache__/*' )
echo "  $(du -h build/function.zip | cut -f1) zipped"

# --- create or update ------------------------------------------------------------------
if aws lambda get-function --function-name "$FN" >/dev/null 2>&1; then
  echo "updating $FN..."
  aws lambda update-function-code --function-name "$FN" --zip-file "fileb://build/function.zip" >/dev/null
  aws lambda wait function-updated --function-name "$FN"
  aws lambda update-function-configuration --function-name "$FN" --handler src.function.handler.handler \
    --runtime python3.12 --timeout "$TIMEOUT" --memory-size "$MEMORY" --environment "$ENV_VARS" >/dev/null
  aws lambda wait function-updated --function-name "$FN"
else
  echo "creating $FN as $ROLE..."
  aws lambda create-function --function-name "$FN" --runtime python3.12 --architectures x86_64 \
    --handler src.function.handler.handler --role "$ROLE" --zip-file "fileb://build/function.zip" \
    --timeout "$TIMEOUT" --memory-size "$MEMORY" --environment "$ENV_VARS" >/dev/null
  aws lambda wait function-active --function-name "$FN"
fi

# --- the URL: IAM-authenticated (the Learner Lab blocks anonymous function URLs) ---------
URL="$(aws lambda get-function-url-config --function-name "$FN" --query FunctionUrl --output text 2>/dev/null || true)"
if [ -z "$URL" ] || [ "$URL" = "None" ]; then
  URL="$(aws lambda create-function-url-config --function-name "$FN" --auth-type AWS_IAM --query FunctionUrl --output text)"
else
  aws lambda update-function-url-config --function-name "$FN" --auth-type AWS_IAM >/dev/null
fi
grep -q '^LAB_URL=' .env && sed -i.bak "s|^LAB_URL=.*|LAB_URL=${URL}score|" .env && rm -f .env.bak || printf 'LAB_URL=%s\n' "${URL}score" >> .env

echo
echo "deployed: $FN   timeout ${TIMEOUT}s   memory ${MEMORY} MB   threshold ${THRESHOLD}   bucket ${BUCKET}"
echo "url:      ${URL}score   (saved to .env as LAB_URL; /batch is beside it)"
echo
echo "try it:   ./call.sh                                   (one signed request)"
echo "batch:    uv run run_batch.py data/nights/2026-10-05.jsonl"
echo "online:   uv run record.py --provider http --runs 3"
echo "logs:     aws logs tail /aws/lambda/$FN --follow     (every /score line is the inference table)"
