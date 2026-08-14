"""Tests for the GitHub Actions extractor (graphify/extractors/github_actions.py)
and its detect.classify_file() carve-out.

Scoped to GitHub Actions workflow YAML only -- no Docker Compose (out of this
fork's scope; see the module docstring in github_actions.py). Two concerns
are tested together since they are two halves of the same feature:
1. extract_github_actions() itself (job/needs/uses extraction).
2. classify_file() routing recognized workflow paths to FileType.CODE, which
   is what makes them usable under `graphify extract --code-only` -- the
   actual point of this feature, not just adding a semantic-pass extractor.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.detect import FileType, classify_file
from graphify.extract import extract, extract_github_actions


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _labels(r) -> list[str]:
    return [n["label"] for n in r["nodes"]]


def _rel_pairs(r, relation: str) -> set[tuple[str, str]]:
    lab = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (lab.get(e["source"], e["source"]), lab.get(e["target"], e["target"]))
        for e in r["edges"]
        if e["relation"] == relation
    }


@pytest.fixture(autouse=True)
def _require_grammar():
    pytest.importorskip("tree_sitter_yaml")


WORKFLOW = """\
name: CI
on:
  push:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: pnpm lint
  test:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
  deploy:
    needs: [lint, test]
    uses: ./.github/workflows/release.yml
"""


# ── extract_github_actions() ─────────────────────────────────────────────────

def test_workflow_jobs_become_nodes(tmp_path):
    r = extract_github_actions(_write(tmp_path, "ci.yml", WORKFLOW))
    assert r.get("error") is None
    labels = set(_labels(r))
    for expected in ("lint", "test", "deploy"):
        assert expected in labels, f"missing job node {expected!r}"


def test_workflow_file_contains_jobs(tmp_path):
    r = extract_github_actions(_write(tmp_path, "ci.yml", WORKFLOW))
    contains = _rel_pairs(r, "contains")
    assert ("ci.yml", "lint") in contains
    assert ("ci.yml", "deploy") in contains


def test_workflow_needs_becomes_depends_on(tmp_path):
    r = extract_github_actions(_write(tmp_path, "ci.yml", WORKFLOW))
    deps = _rel_pairs(r, "depends_on")
    assert ("test", "lint") in deps       # scalar form: `needs: lint`
    assert ("deploy", "lint") in deps     # list form: `needs: [lint, test]`
    assert ("deploy", "test") in deps


def test_workflow_step_uses_edges(tmp_path):
    r = extract_github_actions(_write(tmp_path, "ci.yml", WORKFLOW))
    uses = _rel_pairs(r, "uses")
    assert ("lint", "actions/checkout@v4") in uses
    assert ("lint", "actions/setup-node@v4") in uses


def test_workflow_reusable_workflow_uses_edge(tmp_path):
    # Job-level `uses:` is a reusable-workflow call, not a step.
    r = extract_github_actions(_write(tmp_path, "ci.yml", WORKFLOW))
    assert ("deploy", "./.github/workflows/release.yml") in _rel_pairs(r, "uses")


def test_workflow_detected_by_path_without_on_key(tmp_path):
    body = "jobs:\n  build:\n    steps:\n      - uses: actions/checkout@v4\n"
    p = _write(tmp_path, ".github/workflows/build.yml", body)
    assert "build" in set(_labels(extract_github_actions(p)))


def test_run_steps_do_not_become_nodes(tmp_path):
    # `- run: pnpm lint` is a shell command, not a reference.
    r = extract_github_actions(_write(tmp_path, "ci.yml", WORKFLOW))
    assert not any("pnpm lint" in lbl for lbl in _labels(r))


def test_no_dangling_edge_endpoints(tmp_path):
    r = extract_github_actions(_write(tmp_path, "ci.yml", WORKFLOW))
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"dangling source: {e['source']}"
        assert e["target"] in node_ids, f"dangling target: {e['target']}"


def test_shared_action_merges_across_workflows(tmp_path):
    """The same action pinned by two workflows is one node, so
    `actions/checkout` becomes a real hub instead of one dangling stub per
    file."""
    a = _write(tmp_path, ".github/workflows/a.yml",
               "on: push\njobs:\n  one:\n    steps:\n      - uses: actions/checkout@v4\n")
    b = _write(tmp_path, ".github/workflows/b.yml",
               "on: push\njobs:\n  two:\n    steps:\n      - uses: actions/checkout@v4\n")

    r = extract([a.resolve(), b.resolve()], root=tmp_path)

    checkout_ids = {n["id"] for n in r["nodes"] if n["label"] == "actions/checkout@v4"}
    assert len(checkout_ids) == 1, f"expected one shared action id, got {checkout_ids}"
    checkout_id = checkout_ids.pop()

    G = build_from_json({"nodes": r["nodes"], "edges": r["edges"]})
    assert G.has_node(checkout_id)
    sources = {e["source"] for e in r["edges"]
               if e["relation"] == "uses" and e["target"] == checkout_id}
    assert len(sources) == 2, "both workflows should point at the shared action node"


# ── Data YAML / non-workflow YAML is deliberately not modelled ──────────────

K8S = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 3
"""

OPENAPI = """\
openapi: 3.0.0
paths:
  /users:
    get:
      summary: list users
"""

COMPOSE = """\
services:
  api:
    image: api:latest
    depends_on:
      - db
  db:
    image: postgres:16
"""


@pytest.mark.parametrize("name,body", [("deploy.yaml", K8S), ("openapi.yaml", OPENAPI)])
def test_data_yaml_returns_empty(tmp_path, name, body):
    r = extract_github_actions(_write(tmp_path, name, body))
    assert r.get("error") is None
    assert r["nodes"] == []
    assert r["edges"] == []


def test_docker_compose_is_out_of_scope_and_returns_empty(tmp_path):
    # Compose is deliberately not modelled by this extractor (out of this
    # ticket's scope) -- confirms it stays with the semantic pass rather than
    # silently doing something half-implemented.
    r = extract_github_actions(_write(tmp_path, "docker-compose.yml", COMPOSE))
    assert r["nodes"] == []
    assert r["edges"] == []


def test_jobs_key_alone_without_on_or_workflows_path_is_not_enough(tmp_path):
    # `jobs:` is too generic a key to trust alone (other tools use it too);
    # without `on:` and outside `.github/workflows/`, this must not be
    # mistaken for a real workflow.
    body = "jobs:\n  something: true\n"
    r = extract_github_actions(_write(tmp_path, "notes/plan.yaml", body))
    assert r["nodes"] == []


def test_empty_and_comment_only_files_are_safe(tmp_path):
    assert extract_github_actions(_write(tmp_path, "a.yml", "")).get("error") is None
    r = extract_github_actions(_write(tmp_path, "b.yml", "# just a comment\n"))
    assert r.get("error") is None
    assert r["nodes"] == []


# ── classify_file() carve-out: the actual --code-only fix ───────────────────
#
# classify_file() requires BOTH a workflow path AND workflow-shaped content
# (a cheap regex sniff for a top-level `jobs:` key, see
# github_actions.looks_like_workflow_shape) -- path alone used to be enough,
# but that let a non-workflow file sitting at a workflow path get routed to
# CODE, extracted as empty, and never reach the semantic pass at all (a real
# content-loss bug, not just a missed-nodes one; caught in review). So these
# tests write real files rather than asserting on paths that don't exist on
# disk.

def test_workflow_path_classified_as_code(tmp_path):
    assert classify_file(_write(tmp_path, ".github/workflows/ci.yml", WORKFLOW)) == FileType.CODE
    assert classify_file(_write(tmp_path, ".github/workflows/nightly-build.yaml", WORKFLOW)) == FileType.CODE


def test_workflow_path_classified_as_code_absolute(tmp_path):
    p = _write(tmp_path, ".github/workflows/ci.yml", WORKFLOW)
    assert classify_file(p.resolve()) == FileType.CODE


def test_non_workflow_yaml_at_workflow_path_is_not_reclassified(tmp_path):
    # A file that merely sits in .github/workflows/ but isn't workflow-shaped
    # (no `jobs:` key at all) must fall through to DOCUMENT, not CODE --
    # otherwise it is extracted as empty and never reaches the semantic pass.
    p = _write(tmp_path, ".github/workflows/README.yml", "title: not a workflow\n")
    assert classify_file(p) == FileType.DOCUMENT


def test_nested_workflows_dir_is_not_reclassified(tmp_path):
    # GitHub only recognizes workflow files directly in .github/workflows/,
    # not nested deeper -- so neither does this carve-out.
    p = _write(tmp_path, ".github/workflows/nested/ci.yml", WORKFLOW)
    assert classify_file(p) == FileType.DOCUMENT


def test_composite_action_yml_is_not_reclassified(tmp_path):
    # .github/actions/<name>/action.yml (composite/local actions) is a
    # different, unmodelled shape -- explicitly out of this ticket's scope,
    # must not be swept in by a loose ".github/**/*.yml" check.
    p = _write(tmp_path, ".github/actions/setup/action.yml", WORKFLOW)
    assert classify_file(p) == FileType.DOCUMENT


def test_other_yaml_still_classified_as_document(tmp_path):
    # The whole point of scoping this narrowly: Helm values, k8s manifests,
    # OpenAPI specs, docker-compose.yml must keep their existing,
    # correctly-working semantic-pass classification untouched.
    assert classify_file(_write(tmp_path, "charts/myapp/values.yaml", "replicaCount: 1\n")) == FileType.DOCUMENT
    assert classify_file(_write(tmp_path, "k8s/deployment.yaml", "apiVersion: v1\nkind: Deployment\n")) == FileType.DOCUMENT
    assert classify_file(_write(tmp_path, "openapi.yaml", "openapi: 3.0.0\n")) == FileType.DOCUMENT
    assert classify_file(_write(tmp_path, "docker-compose.yml", COMPOSE)) == FileType.DOCUMENT


def test_workflow_extracted_under_code_only_semantics(tmp_path):
    """End-to-end: a file classified as CODE for a recognized workflow path
    actually produces real job/needs/uses nodes via the same extract() path
    --code-only calls, not just that classify_file() returns CODE in
    isolation."""
    p = _write(tmp_path, ".github/workflows/ci.yml", WORKFLOW)
    assert classify_file(p) == FileType.CODE

    r = extract([p.resolve()], root=tmp_path)
    labels = set(_labels(r))
    for expected in ("lint", "test", "deploy"):
        assert expected in labels
    assert ("test", "lint") in _rel_pairs(r, "depends_on")
    assert ("lint", "actions/checkout@v4") in _rel_pairs(r, "uses")


def test_non_workflow_yaml_gets_no_extractor(tmp_path):
    # _get_extractor() must gate .yaml/.yml the same way classify_file()
    # does: a file that isn't workflow-shaped (wrong path, or right path but
    # wrong content) gets no extractor at all rather than being dispatched
    # to extract_github_actions and misreported as a failed/empty
    # extraction (review round 3).
    from graphify.extract import _get_extractor
    assert _get_extractor(_write(tmp_path, "docker-compose.yml", COMPOSE)) is None
    assert _get_extractor(_write(tmp_path, ".github/workflows/README.yml", "title: x\n")) is None
    assert _get_extractor(_write(tmp_path, ".github/workflows/ci.yml", WORKFLOW)) is extract_github_actions


# ── extract_github_actions(): missing vs broken grammar (#2602-style) ───────

def test_github_actions_reports_load_failure_not_missing(tmp_path, monkeypatch):
    # Same distinction as extractors/sql.py: an installed-but-broken grammar
    # (e.g. a wheel built for a different Python ABI) raises ImportError at
    # import time just like an absent one. Must not claim "not installed" --
    # that sends the user to a no-op `pip install` -- but surface the real
    # load exception instead.
    import builtins
    pytest.importorskip("tree_sitter_yaml")  # find_spec must see it as installed

    _orig_import = builtins.__import__

    def _broken_import(name, *args, **kwargs):
        if name == "tree_sitter_yaml":
            raise ImportError("dynamic module does not define module export function")
        return _orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _broken_import)
    err = extract_github_actions(_write(tmp_path, ".github/workflows/ci.yml", WORKFLOW)).get("error") or ""
    assert "failed to load" in err
    assert "dynamic module does not define module export function" in err
    assert "pip install" not in err


def test_github_actions_reports_grammar_init_failure_as_load_failure(tmp_path, monkeypatch):
    # A grammar init failure (Language()/Parser() raising, e.g. an ABI
    # version mismatch surfacing one call later than the import itself) must
    # get the same "failed to load" marker as an ImportError, not be
    # conflated with an unrelated file-read error.
    pytest.importorskip("tree_sitter_yaml")
    import tree_sitter

    def _broken_language(*args, **kwargs):
        raise ValueError("Incompatible Language version")

    monkeypatch.setattr(tree_sitter, "Language", _broken_language)
    err = extract_github_actions(_write(tmp_path, ".github/workflows/ci.yml", WORKFLOW)).get("error") or ""
    assert "failed to load" in err
    assert "Incompatible Language version" in err
