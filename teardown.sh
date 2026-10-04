#!/usr/bin/env bash
# Remove everything the lab created, in AWS and here.
#
#   ./teardown.sh             the rule, the function and its URL; the build directory; the
#                             LAB_URL, LAB_TOKEN and BUCKET lines in .env. The bucket and the
#                             log group are kept: the bucket holds your run records.
#   ./teardown.sh --bucket    also empty and delete the bucket
set -uo pipefail
cd "$(dirname "$0")"
FN="${FUNCTION_NAME:-score-every-account}"; RULE="${FN}-nightly"
export AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
[ -f .env ] && { set -a; . ./.env; set +a; }

if command -v aws >/dev/null && aws sts get-caller-identity >/dev/null 2>&1; then
  aws events remove-targets --rule "$RULE" --ids 1 >/dev/null 2>&1 && aws events delete-rule --name "$RULE" >/dev/null 2>&1 && echo "removed the rule $RULE"
  aws lambda delete-function-url-config --function-name "$FN" >/dev/null 2>&1 && echo "removed the URL of $FN"
  aws lambda delete-function --function-name "$FN" >/dev/null 2>&1 && echo "deleted the function $FN" || echo "the function $FN was not there"
  if [ "${1:-}" = "--bucket" ] && [ -n "${BUCKET:-}" ]; then
    aws s3 rm "s3://$BUCKET" --recursive >/dev/null 2>&1; aws s3api delete-bucket --bucket "$BUCKET" >/dev/null 2>&1 && echo "deleted the bucket $BUCKET"
  else
    echo "kept the bucket ${BUCKET:-?} (./teardown.sh --bucket to delete it) and the log group /aws/lambda/$FN"
  fi
else
  echo "no AWS session: start a Learner Lab session, paste credentials, and run this again."
fi
rm -rf build && echo "removed build/"
[ -f .env ] && sed -i.bak '/^LAB_URL=/d; /^LAB_TOKEN=/d; /^BUCKET=/d' .env && rm -f .env.bak && echo "cleared LAB_URL, LAB_TOKEN and BUCKET from .env"
