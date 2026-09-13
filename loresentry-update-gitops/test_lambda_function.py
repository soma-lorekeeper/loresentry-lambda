import os
import sys
import types

import pytest

os.environ.setdefault("GITHUB_OWNER", "soma-lorekeeper")
os.environ.setdefault("GITOPS_REPO", "loresentry-gitops")
os.environ.setdefault("GITOPS_BRANCH", "main")
os.environ.setdefault("GITOPS_ROOT", "workload/overlays/prod")
os.environ.setdefault("ECR_REGISTRY", "197179613039.dkr.ecr.ap-northeast-2.amazonaws.com")
os.environ.setdefault("GITHUB_TOKEN_SECRET", "loresentry/github/gitops-token")

_boto3 = types.ModuleType("boto3")
_boto3.client = lambda *args, **kwargs: None
sys.modules.setdefault("boto3", _boto3)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lambda_function as lf

REGISTRY = "197179613039.dkr.ecr.ap-northeast-2.amazonaws.com"
GRAPH_RAG = f"{REGISTRY}/graph-rag/api"
GATEWAY = f"{REGISTRY}/gateway/api"

KUSTOMIZATION = f"""apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: prod

resources:
  - namespace.yaml
  - ../../base
  - ingress.yaml

images:
  - name: {GATEWAY}
    newTag: bootstrap
  - name: {GRAPH_RAG}
    newTag: build-3-1

replicas:
  - name: gateway-api
    count: 0
"""


def test_replaces_the_matching_tag():
    updated, changed = lf.replace_image_tag(KUSTOMIZATION, GRAPH_RAG, "build-9-1")

    assert changed is True
    assert "newTag: build-9-1" in updated


def test_leaves_other_entries_untouched():
    updated, _ = lf.replace_image_tag(KUSTOMIZATION, GRAPH_RAG, "build-9-1")

    assert "newTag: bootstrap" in updated
    assert updated.count("build-9-1") == 1


def test_preserves_every_other_line():
    updated, _ = lf.replace_image_tag(KUSTOMIZATION, GRAPH_RAG, "build-9-1")

    assert updated.count("\n") == KUSTOMIZATION.count("\n")
    assert "namespace: prod" in updated
    assert "count: 0" in updated


def test_reports_unchanged_when_tag_is_identical():
    updated, changed = lf.replace_image_tag(KUSTOMIZATION, GRAPH_RAG, "build-3-1")

    assert changed is False
    assert updated == KUSTOMIZATION


def test_updates_gateway_independently():
    updated, changed = lf.replace_image_tag(KUSTOMIZATION, GATEWAY, "build-1-1")

    assert changed is True
    assert "newTag: build-1-1" in updated
    assert "newTag: build-3-1" in updated


def test_rejects_unknown_image():
    with pytest.raises(lf.ImageEntryNotFound):
        lf.replace_image_tag(KUSTOMIZATION, f"{REGISTRY}/nope/api", "build-9-1")


def test_does_not_match_on_name_prefix():
    manifest = KUSTOMIZATION.replace(
        f"  - name: {GRAPH_RAG}\n", f"  - name: {GRAPH_RAG}-v2\n"
    )

    with pytest.raises(lf.ImageEntryNotFound):
        lf.replace_image_tag(manifest, GRAPH_RAG, "build-9-1")


def test_keeps_quoting_style():
    manifest = KUSTOMIZATION.replace("newTag: build-3-1", 'newTag: "build-3-1"')

    updated, changed = lf.replace_image_tag(manifest, GRAPH_RAG, "build-5-1")

    assert changed is True
    assert 'newTag: "build-5-1"' in updated


def test_rejects_entry_without_newtag():
    manifest = KUSTOMIZATION.replace("    newTag: build-3-1\n", "")

    with pytest.raises(lf.ImageEntryNotFound):
        lf.replace_image_tag(manifest, GRAPH_RAG, "build-9-1")


@pytest.mark.parametrize("repository", ["graph-rag", "/graph-rag/api", "../../etc", "Graph-Rag/api"])
def test_repository_pattern_rejects_bad_input(repository):
    assert lf.REPOSITORY_PATTERN.fullmatch(repository) is None


@pytest.mark.parametrize("tag", ["", "-leading-dash", "a" * 129])
def test_tag_pattern_rejects_bad_input(tag):
    assert lf.TAG_PATTERN.fullmatch(tag) is None
