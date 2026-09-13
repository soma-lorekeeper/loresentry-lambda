#!/usr/bin/env bash
set -euo pipefail

PROFILE="${AWS_PROFILE:-lorekeeper}"
REGION="${AWS_REGION:-ap-northeast-2}"
FUNCTION="loresentry-update-gitops"
ACCOUNT="197179613039"

aws lambda update-function-configuration \
  --profile "$PROFILE" --region "$REGION" \
  --function-name "$FUNCTION" \
  --role "arn:aws:iam::${ACCOUNT}:role/loresentry-update-gitops-lambda-role" \
  --timeout 30 \
  --memory-size 256 \
  --environment "Variables={\
GITHUB_OWNER=soma-lorekeeper,\
GITOPS_REPO=loresentry-gitops,\
GITOPS_BRANCH=main,\
GITOPS_ROOT=workload/overlays/prod,\
ECR_REGISTRY=${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com,\
GITHUB_TOKEN_SECRET=loresentry/github/gitops-token}" \
  --query '{Role:Role,Timeout:Timeout,Memory:MemorySize,Env:Environment.Variables}' \
  --output json
