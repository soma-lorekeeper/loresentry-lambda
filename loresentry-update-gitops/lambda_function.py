import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import boto3


secrets_manager = boto3.client("secretsmanager")

GITHUB_OWNER = os.environ["GITHUB_OWNER"]
GITOPS_REPO = os.environ["GITOPS_REPO"]
GITOPS_BRANCH = os.environ.get("GITOPS_BRANCH", "main")
GITOPS_ROOT = os.environ.get("GITOPS_ROOT", "workload").rstrip("/")
ECR_REGISTRY = os.environ["ECR_REGISTRY"].rstrip("/")
GITHUB_TOKEN_SECRET = os.environ["GITHUB_TOKEN_SECRET"]

GITHUB_API_VERSION = "2026-03-10"

# namespace/application 형태만 허용
REPOSITORY_PATTERN = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*"
    r"(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+$"
)

TAG_PATTERN = re.compile(
    r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$"
)


class GitHubApiError(Exception):
    def __init__(self, status, body):
        super().__init__(
            f"GitHub API failed: status={status}, body={body}"
        )
        self.status = status
        self.body = body


def get_github_token():
    response = secrets_manager.get_secret_value(
        SecretId=GITHUB_TOKEN_SECRET
    )
    secret = response["SecretString"]

    try:
        secret_json = json.loads(secret)
        return secret_json["github_token"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return secret


def github_request(method, url, token, payload=None):
    request_body = None

    if payload is not None:
        request_body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url=url,
        data=request_body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "Content-Type": "application/json",
            "User-Agent": "loresentry-update-gitops-lambda"
        }
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8")
        raise GitHubApiError(error.code, body) from error


class ImageEntryNotFound(Exception):
    pass


def replace_image_tag(manifest, image_name, new_tag):
    name_pattern = re.compile(
        r"^(\s*)-\s+name:\s*(['\"]?)"
        + re.escape(image_name)
        + r"\2\s*(?:#.*)?$"
    )
    tag_pattern = re.compile(
        r"^(\s*)(newTag:\s*)(['\"]?)([^\s'\"#]*)\3(\s*(?:#.*)?)$"
    )

    lines = manifest.split("\n")
    hits = []

    for index, line in enumerate(lines):
        name_match = name_pattern.match(line)

        if not name_match:
            continue

        item_indent = len(name_match.group(1))

        for offset in range(index + 1, len(lines)):
            candidate = lines[offset]

            if not candidate.strip():
                continue

            indent = len(candidate) - len(candidate.lstrip())

            if indent <= item_indent:
                break

            tag_match = tag_pattern.match(candidate)

            if tag_match:
                hits.append((offset, tag_match))
                break

    if len(hits) != 1:
        raise ImageEntryNotFound(
            f"Expected exactly one images entry with a newTag for {image_name}, "
            f"but found {len(hits)}"
        )

    offset, tag_match = hits[0]
    current_tag = tag_match.group(4)

    if current_tag == new_tag:
        return manifest, False

    lines[offset] = (
        f"{tag_match.group(1)}{tag_match.group(2)}"
        f"{tag_match.group(3)}{new_tag}{tag_match.group(3)}"
        f"{tag_match.group(5)}"
    )

    return "\n".join(lines), True


def lambda_handler(event, context):
    repository = event.get("repository")
    image_tag = event.get("imageTag")

    if not repository or not REPOSITORY_PATTERN.fullmatch(repository):
        raise ValueError(
            "repository must use namespace/application format, "
            "for example graph-rag/api"
        )

    if not image_tag or not TAG_PATTERN.fullmatch(image_tag):
        raise ValueError("imageTag is missing or invalid")

    manifest_path = f"{GITOPS_ROOT}/kustomization.yaml"
    image_name = f"{ECR_REGISTRY}/{repository}"
    new_image = f"{image_name}:{image_tag}"

    token = get_github_token()

    encoded_path = urllib.parse.quote(
        manifest_path,
        safe="/"
    )
    encoded_branch = urllib.parse.quote(
        GITOPS_BRANCH,
        safe=""
    )

    read_url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_OWNER}/{GITOPS_REPO}"
        f"/contents/{encoded_path}"
        f"?ref={encoded_branch}"
    )

    update_url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_OWNER}/{GITOPS_REPO}"
        f"/contents/{encoded_path}"
    )

    # 다른 애플리케이션 배포와 Git commit이 충돌하면 재시도
    for attempt in range(1, 4):
        current_file = github_request(
            "GET",
            read_url,
            token
        )

        current_manifest = base64.b64decode(
            current_file["content"]
        ).decode("utf-8")

        updated_manifest, changed = replace_image_tag(
            current_manifest,
            image_name,
            image_tag
        )

        if not changed:
            return {
                "status": "unchanged",
                "repository": repository,
                "manifestPath": manifest_path,
                "image": new_image
            }

        payload = {
            "message": (
                f"deploy({repository}): "
                f"update image to {image_tag}"
            ),
            "content": base64.b64encode(
                updated_manifest.encode("utf-8")
            ).decode("ascii"),
            "sha": current_file["sha"],
            "branch": GITOPS_BRANCH
        }

        try:
            result = github_request(
                "PUT",
                update_url,
                token,
                payload
            )

            return {
                "status": "updated",
                "repository": repository,
                "manifestPath": manifest_path,
                "image": new_image,
                "commit": result["commit"]["sha"]
            }

        except GitHubApiError as error:
            if error.status == 409 and attempt < 3:
                time.sleep(0.5 * attempt)
                continue

            raise

    raise RuntimeError("Failed to update GitOps repository")