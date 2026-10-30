# loresentry-lambda

Source for the Lore Sentry Lambda functions. These were originally authored in the
AWS console; this directory is the version-controlled copy that the console should
be considered a deployment target of, not the source of truth.

| Function | Directory |
| --- | --- |
| `loresentry-update-gitops`, `loresentry-update-gitops-dev` | [`loresentry-update-gitops/`](loresentry-update-gitops/) |

Each directory holds the handler, its tests, and the two scripts that push it to
AWS. No packaging step or dependencies beyond the runtime's built-in `boto3`.

This repository is deployed from a workstation, not from CI. The console and the
deployed function are targets; this repository is the source of truth.
