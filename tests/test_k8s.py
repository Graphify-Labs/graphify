"""Tests for the Kubernetes / ArgoCD / Helm-values YAML extractor."""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.detect import FileType, classify_file
from graphify.extract import extract_k8s
from graphify.extractors.k8s import is_k8s_manifest_path

pytest.importorskip("yaml", reason="k8s extractor needs the [k8s] extra (pyyaml)")


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _labels(r) -> set[str]:
    return {n["label"] for n in r["nodes"]}


def _rel_pairs(r, relation: str) -> set[tuple[str, str]]:
    lab = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (lab.get(e["source"], e["source"]), lab.get(e["target"], e["target"]))
        for e in r["edges"]
        if e["relation"] == relation
    }


APPSET = """\
# leading comment
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: fleet-apps-prod
  namespace: argocd
spec:
  generators:
    - git:
        repoURL: https://github.com/acme/monorepo.git
        files:
          - path: gitops/apps/*.yaml
  template:
    spec:
      project: platform-prod
      source:
        path: "charts/{{.app}}"
      destination:
        namespace: prod-apps
"""

EXTERNAL_SECRET = """\
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: api-runtime
  namespace: dev-apps
spec:
  secretStoreRef:
    kind: ClusterSecretStore
    name: aws-secrets-manager
  target:
    name: api-runtime-secrets
"""

DEPLOYMENT = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  template:
    spec:
      serviceAccountName: api-sa
      containers:
        - name: api
          envFrom:
            - configMapRef:
                name: api-config
            - secretRef:
                name: api-runtime-secrets
"""


def test_object_becomes_a_kind_dot_name_node(tmp_path):
    r = extract_k8s(_write(tmp_path, "appset.yaml", APPSET))
    assert r.get("error") is None
    assert "ApplicationSet.fleet-apps-prod" in _labels(r)
    assert ("appset.yaml", "ApplicationSet.fleet-apps-prod") in _rel_pairs(r, "contains")


def test_git_generator_glob_becomes_generates_from(tmp_path):
    # The edge that makes "which apps does this env deploy?" answerable.
    r = extract_k8s(_write(tmp_path, "appset.yaml", APPSET))
    assert ("ApplicationSet.fleet-apps-prod", "path.gitops/apps/*.yaml") in _rel_pairs(
        r, "generates_from"
    )


def test_refs_nested_under_applicationset_template_are_found(tmp_path):
    # An ApplicationSet nests a whole Application spec under spec.template.spec.
    # The walk matches on key name at any depth, so these need no special case.
    r = extract_k8s(_write(tmp_path, "appset.yaml", APPSET))
    assert ("ApplicationSet.fleet-apps-prod", "AppProject.platform-prod") in _rel_pairs(
        r, "references"
    )
    assert ("ApplicationSet.fleet-apps-prod", "Namespace.prod-apps") in _rel_pairs(
        r, "deploys_to"
    )
    assert ("ApplicationSet.fleet-apps-prod", "path.charts/{{.app}}") in _rel_pairs(
        r, "deploys_chart"
    )


def test_external_secret_store_and_produced_secret(tmp_path):
    r = extract_k8s(_write(tmp_path, "es.yaml", EXTERNAL_SECRET))
    # kind comes from the secretStoreRef mapping itself, not a hardcoded default.
    assert ("ExternalSecret.api-runtime", "ClusterSecretStore.aws-secrets-manager") in _rel_pairs(
        r, "references"
    )
    assert ("ExternalSecret.api-runtime", "Secret.api-runtime-secrets") in _rel_pairs(
        r, "produces"
    )
    assert ("ExternalSecret.api-runtime", "Namespace.dev-apps") in _rel_pairs(
        r, "in_namespace"
    )


def test_workload_config_and_secret_refs(tmp_path):
    r = extract_k8s(_write(tmp_path, "deploy.yaml", DEPLOYMENT))
    refs = _rel_pairs(r, "references")
    assert ("Deployment.api", "ConfigMap.api-config") in refs
    assert ("Deployment.api", "Secret.api-runtime-secrets") in refs
    assert ("Deployment.api", "ServiceAccount.api-sa") in refs


def test_cross_file_reference_resolves_by_global_address(tmp_path):
    # The whole point of global kind.name scoping: an AppProject declared in one
    # file is the SAME node the ApplicationSet in another file points at.
    proj = """\
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: platform-prod
spec:
  description: prod
"""
    a = extract_k8s(_write(tmp_path, "appset.yaml", APPSET))
    b = extract_k8s(_write(tmp_path, "project.yaml", proj))
    target = next(
        e["target"] for e in a["edges"]
        if e["relation"] == "references"
    )
    declared = next(n["id"] for n in b["nodes"] if n["label"] == "AppProject.platform-prod")
    assert target == declared


def test_multi_document_file(tmp_path):
    r = extract_k8s(_write(tmp_path, "multi.yaml", DEPLOYMENT + "---\n" + EXTERNAL_SECRET))
    assert "Deployment.api" in _labels(r)
    assert "ExternalSecret.api-runtime" in _labels(r)


def test_source_locations_are_real_lines(tmp_path):
    r = extract_k8s(_write(tmp_path, "appset.yaml", APPSET))
    node = next(n for n in r["nodes"] if n["label"] == "ApplicationSet.fleet-apps-prod")
    # Line 2 — after the leading comment. Not L1, which is what a loader without
    # position tracking would report for everything.
    assert node["source_location"] == "L2"


def test_helm_template_is_skipped_not_crashed(tmp_path):
    # Go template directives make this invalid YAML. It must degrade to an empty
    # result with an error string, never raise.
    tpl = "{{- if .Values.ingress.enabled }}\nkind: Ingress\n{{- end }}\n"
    r = extract_k8s(_write(tmp_path, "ingress.yaml", tpl))
    assert r["nodes"] == [] and r["edges"] == []
    assert r.get("error")


def test_plain_yaml_is_not_a_manifest(tmp_path):
    # A CI config has `name:`/`on:` but no apiVersion+kind — it must stay a
    # document so it keeps going to the LLM path.
    ci = _write(tmp_path, "ci.yml", "name: build\non: [push]\njobs:\n  a:\n    runs-on: ubuntu\n")
    assert is_k8s_manifest_path(ci) is False
    assert classify_file(ci) is FileType.DOCUMENT


def test_manifest_is_sniffed_and_routed_to_code(tmp_path):
    manifest = _write(tmp_path, "appset.yaml", APPSET)
    assert is_k8s_manifest_path(manifest) is True
    assert classify_file(manifest) is FileType.CODE
