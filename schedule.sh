#!/usr/bin/env bash
# The calendar rule: run the batch node every night.
#
#   ./schedule.sh                       nightly at 03:00 UTC (cron(0 3 * * ? *))
#   ./schedule.sh "rate(5 minutes)"     any EventBridge expression; handy for seeing it fire tonight
#   ./schedule.sh --status              the rule, and every run record in the bucket
#   ./schedule.sh --off                 remove the rule
#
# One EventBridge rule with the function as its target, invoked with a constant event
# {"batch": {"key": "accounts/nightly.jsonl"}}: the handler recognises it and runs the node.
# That is a calendar and one node. The ordering and retries of a real DAG are what a
# scheduler product adds; this is the mechanism they all start from.
set -euo pipefail
cd "$(dirname "$0")"
FN="${FUNCTION_NAME:-score-every-account}"; RULE="${FN}-nightly"
export AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
set -a; . ./.env; set +a

if [ "${1:-}" = "--status" ]; then
  aws events describe-rule --name "$RULE" --query '{rule:Name,schedule:ScheduleExpression,state:State}' --output table 2>/dev/null || echo "no rule $RULE"
  uv run run_batch.py --list-runs
  exit 0
fi
if [ "${1:-}" = "--off" ]; then
  aws events remove-targets --rule "$RULE" --ids 1 >/dev/null 2>&1 || true
  aws events delete-rule --name "$RULE" >/dev/null 2>&1 && echo "removed $RULE" || echo "no rule $RULE"
  exit 0
fi

EXPR="${1:-cron(0 3 * * ? *)}"
ARN="$(aws lambda get-function --function-name "$FN" --query Configuration.FunctionArn --output text)"
RULE_ARN="$(aws events put-rule --name "$RULE" --schedule-expression "$EXPR" --state ENABLED --query RuleArn --output text)"
aws lambda add-permission --function-name "$FN" --statement-id "$RULE" --action lambda:InvokeFunction \
  --principal events.amazonaws.com --source-arn "$RULE_ARN" >/dev/null 2>&1 || true
aws events put-targets --rule "$RULE" --targets "[{\"Id\":\"1\",\"Arn\":\"$ARN\",\"Input\":\"{\\\"batch\\\":{\\\"key\\\":\\\"accounts/nightly.jsonl\\\"}}\"}]" >/dev/null
echo "rule $RULE: $EXPR → $FN with {\"batch\": {\"key\": \"accounts/nightly.jsonl\"}}"
echo "the run id is the date the rule fires; ./schedule.sh --status shows the records"
