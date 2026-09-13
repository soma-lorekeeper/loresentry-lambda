#!/usr/bin/env bash
set -euo pipefail

PROFILE="${AWS_PROFILE:-lorekeeper}"
REGION="${AWS_REGION:-ap-northeast-2}"
FUNCTION="loresentry-update-gitops"

cd "$(dirname "$0")"

ZIP="$(mktemp -d)/${FUNCTION}.zip"
zip -q -X "$ZIP" lambda_function.py

aws lambda update-function-code \
  --profile "$PROFILE" --region "$REGION" \
  --function-name "$FUNCTION" \
  --zip-file "fileb://${ZIP}" \
  --query '{CodeSize:CodeSize,LastUpdate:LastUpdateStatus}' \
  --output json

rm -rf "$(dirname "$ZIP")"
