#!/usr/bin/env bash
set -euo pipefail

PROFILE="${AWS_PROFILE:-lorekeeper}"
REGION="${AWS_REGION:-ap-northeast-2}"
FUNCTIONS=("loresentry-update-gitops" "loresentry-update-gitops-dev")

cd "$(dirname "$0")"

ZIP="$(mktemp -d)/function.zip"
zip -q -X "$ZIP" lambda_function.py

for FUNCTION in "${FUNCTIONS[@]}"; do
  if ! aws lambda get-function --profile "$PROFILE" --region "$REGION" \
      --function-name "$FUNCTION" >/dev/null 2>&1; then
    echo "${FUNCTION}: not found, skipped (create it with ./configure.sh dev)"
    continue
  fi
  aws lambda update-function-code \
    --profile "$PROFILE" --region "$REGION" \
    --function-name "$FUNCTION" \
    --zip-file "fileb://${ZIP}" \
    --query '{Function:FunctionName,CodeSize:CodeSize,LastUpdate:LastUpdateStatus}' \
    --output json
done

rm -rf "$(dirname "$ZIP")"
