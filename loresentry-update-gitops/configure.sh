#!/usr/bin/env bash
set -euo pipefail

PROFILE="${AWS_PROFILE:-lorekeeper}"
REGION="${AWS_REGION:-ap-northeast-2}"
ACCOUNT="197179613039"
TARGET="${1:-prod}"

case "$TARGET" in
  prod)
    FUNCTION="loresentry-update-gitops"
    GITOPS_ROOT="workload/overlays/prod"
    ;;
  dev)
    FUNCTION="loresentry-update-gitops-dev"
    GITOPS_ROOT="workload/overlays/dev"
    ;;
  *)
    echo "usage: $0 [prod|dev]" >&2
    exit 1
    ;;
esac

ROLE="arn:aws:iam::${ACCOUNT}:role/loresentry-update-gitops-lambda-role"
ENVIRONMENT="Variables={\
GITHUB_OWNER=soma-lorekeeper,\
GITOPS_REPO=loresentry-gitops,\
GITOPS_BRANCH=main,\
GITOPS_ROOT=${GITOPS_ROOT},\
ECR_REGISTRY=${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com,\
GITHUB_TOKEN_SECRET=loresentry/github/gitops-token}"

cd "$(dirname "$0")"

if ! aws lambda get-function --profile "$PROFILE" --region "$REGION" \
    --function-name "$FUNCTION" >/dev/null 2>&1; then
  ZIP="$(mktemp -d)/${FUNCTION}.zip"
  zip -q -X "$ZIP" lambda_function.py
  aws lambda create-function \
    --profile "$PROFILE" --region "$REGION" \
    --function-name "$FUNCTION" \
    --runtime python3.13 \
    --handler lambda_function.lambda_handler \
    --zip-file "fileb://${ZIP}" \
    --role "$ROLE" \
    --timeout 30 \
    --memory-size 256 \
    --environment "$ENVIRONMENT" \
    --tags "Project=lore-sentry,Environment=${TARGET}" \
    --query FunctionArn --output text
  rm -rf "$(dirname "$ZIP")"
  aws lambda wait function-active-v2 --profile "$PROFILE" --region "$REGION" --function-name "$FUNCTION"
fi

aws lambda update-function-configuration \
  --profile "$PROFILE" --region "$REGION" \
  --function-name "$FUNCTION" \
  --role "$ROLE" \
  --timeout 30 \
  --memory-size 256 \
  --environment "$ENVIRONMENT" \
  --query '{Function:FunctionName,Role:Role,Timeout:Timeout,Memory:MemorySize,Env:Environment.Variables}' \
  --output json
