# loresentry-update-gitops

Bridges CI to the GitOps repository. GitHub Actions pushes an image to ECR, then
invokes this function, which rewrites one image tag in
`soma-lorekeeper/loresentry-gitops` and commits it. Argo CD picks the commit up
from there.

```
GitHub Actions ──invoke──> this function ──commit──> loresentry-gitops ──> Argo CD
```

## Input

```json
{
  "repository": "graph-rag/api",
  "imageTag": "build-3-1"
}
```

`repository` is the ECR repository name and must be `<namespace>/<application>`.
`imageTag` must match `^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$`.

## What it edits

It resolves a single file:

```
${GITOPS_ROOT}/kustomization.yaml   →   workload/overlays/prod/kustomization.yaml
```

and updates the `newTag` of the `images:` entry whose `name` equals
`${ECR_REGISTRY}/${repository}`:

```yaml
images:
  - name: 197179613039.dkr.ecr.ap-northeast-2.amazonaws.com/graph-rag/api
    newTag: build-3-1          # ← only this value is rewritten
```

The edit is a targeted line replacement, not a YAML re-serialisation, so comments,
key order and quoting style survive.

`GITOPS_ROOT` is what scopes the function to one environment. Pointing it at
`workload/overlays/dev` would make the same code deploy to dev, so adding a dev
pipeline means a second function (or a new field in the payload), not a code
change here.

## Failure behaviour

It fails loudly rather than guessing:

| Condition | Result |
| --- | --- |
| `repository` or `imageTag` malformed | `ValueError` |
| Manifest missing | GitHub 404 surfaces as `GitHubApiError` |
| No `images:` entry for that image, or more than one | `ImageEntryNotFound` |
| Entry exists but has no `newTag` | `ImageEntryNotFound` |
| Tag already current | returns `{"status": "unchanged"}` without committing |
| Concurrent commit (`409`) | re-reads the file and retries, up to 3 attempts |

It never creates a manifest and never edits a file it was not pointed at.

## Response

```json
{
  "status": "updated",
  "repository": "graph-rag/api",
  "manifestPath": "workload/overlays/prod/kustomization.yaml",
  "image": "197179613039.dkr.ecr.ap-northeast-2.amazonaws.com/graph-rag/api:build-3-1",
  "commit": "..."
}
```

The caller should treat `updated` and `unchanged` as success and anything else as
failure.

## Environment

| Variable | Value |
| --- | --- |
| `GITHUB_OWNER` | `soma-lorekeeper` |
| `GITOPS_REPO` | `loresentry-gitops` |
| `GITOPS_BRANCH` | `main` |
| `GITOPS_ROOT` | `workload/overlays/prod` |
| `ECR_REGISTRY` | `197179613039.dkr.ecr.ap-northeast-2.amazonaws.com` |
| `GITHUB_TOKEN_SECRET` | `loresentry/github/gitops-token` |

Runtime `python3.13`, 256 MB, 30 s timeout, no VPC attachment — it needs to reach
`api.github.com`.

Execution role `loresentry-update-gitops-lambda-role`, which grants
`secretsmanager:GetSecretValue` on the token secret plus basic execution. The
console-generated `loresentry-update-gitops-role-nrexpw65` lacks the Secrets
Manager permission and must not be used.

The secret holds a GitHub fine-grained PAT with Contents read/write, either as a
raw string or as JSON with a `github_token` key.

## Test

```bash
pip install -r requirements-dev.txt
pytest
```

The suite covers the tag replacement logic against a fixture copy of the real
`kustomization.yaml`; it makes no AWS or GitHub calls.

## Deploy

```bash
./configure.sh   # role, timeout, memory, environment variables
./deploy.sh      # handler code
```

`configure.sh` replaces the entire environment variable map, so it always sends
every variable. Run it after changing any of them.
