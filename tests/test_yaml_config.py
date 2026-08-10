"""Tests for the YAML extractor (graphify/extractors/yaml_config.py).

Covers the two shapes extract_yaml models — Docker Compose services and GitHub
Actions workflows — plus the deliberate non-coverage of data YAML, which stays
with the semantic pass.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.extract import extract, extract_yaml

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


COMPOSE = """\
# leading comment so the mapping is not children[0]
services:
  api:
    image: api:latest
    depends_on:
      redis:
        condition: service_healthy
      db:
        condition: service_started
  web:
    build: ./web
    depends_on:
      - api
  worker:
    extends:
      service: api
  redis:
    image: redis:7
  db:
    image: postgres:16

volumes:
  pgdata:
"""

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


@pytest.fixture(autouse=True)
def _require_grammar():
    pytest.importorskip("tree_sitter_yaml")


# ── Docker Compose ────────────────────────────────────────────────────────────

def test_compose_services_become_nodes(tmp_path):
    r = extract_yaml(_write(tmp_path, "docker-compose.yml", COMPOSE))
    assert r.get("error") is None
    labels = set(_labels(r))
    for expected in ("api", "web", "worker", "redis", "db"):
        assert expected in labels, f"missing service node {expected!r}"


def test_compose_file_contains_services(tmp_path):
    r = extract_yaml(_write(tmp_path, "docker-compose.yml", COMPOSE))
    contains = _rel_pairs(r, "contains")
    assert ("docker-compose.yml", "api") in contains
    assert ("docker-compose.yml", "redis") in contains


def test_compose_depends_on_long_form_mapping(tmp_path):
    # `depends_on: {redis: {condition: ...}}` — the dependency names are the KEYS.
    r = extract_yaml(_write(tmp_path, "docker-compose.yml", COMPOSE))
    deps = _rel_pairs(r, "depends_on")
    assert ("api", "redis") in deps
    assert ("api", "db") in deps


def test_compose_depends_on_list_form_strips_sequence_marker(tmp_path):
    # `depends_on: [- api]` — the block_sequence_item text spans the "- " marker,
    # so reading it raw yields "- api" and mints a bogus node.
    r = extract_yaml(_write(tmp_path, "docker-compose.yml", COMPOSE))
    assert ("web", "api") in _rel_pairs(r, "depends_on")
    assert not any(lbl.startswith("- ") for lbl in _labels(r))


def test_compose_extends_service(tmp_path):
    r = extract_yaml(_write(tmp_path, "docker-compose.yml", COMPOSE))
    assert ("worker", "api") in _rel_pairs(r, "depends_on")


def test_compose_forward_reference_binds_locally(tmp_path):
    # `api` depends on `redis`, which is declared LATER in the file. The
    # definition pass must run first, or the reference mints a stub that then
    # competes with the real node.
    r = extract_yaml(_write(tmp_path, "docker-compose.yml", COMPOSE))
    real_redis = next(n["id"] for n in r["nodes"]
                      if n["label"] == "redis" and n.get("source_file"))
    dep_targets = {e["target"] for e in r["edges"] if e["relation"] == "depends_on"}
    assert real_redis in dep_targets
    assert len([n for n in r["nodes"] if n["label"] == "redis"]) == 1


# ── GitHub Actions ────────────────────────────────────────────────────────────

def test_workflow_jobs_become_nodes(tmp_path):
    r = extract_yaml(_write(tmp_path, "ci.yml", WORKFLOW))
    assert r.get("error") is None
    labels = set(_labels(r))
    for expected in ("lint", "test", "deploy"):
        assert expected in labels, f"missing job node {expected!r}"


def test_workflow_needs_becomes_depends_on(tmp_path):
    r = extract_yaml(_write(tmp_path, "ci.yml", WORKFLOW))
    deps = _rel_pairs(r, "depends_on")
    assert ("test", "lint") in deps       # scalar form: `needs: lint`
    assert ("deploy", "lint") in deps     # list form: `needs: [lint, test]`
    assert ("deploy", "test") in deps


def test_workflow_step_uses_edges(tmp_path):
    r = extract_yaml(_write(tmp_path, "ci.yml", WORKFLOW))
    uses = _rel_pairs(r, "uses")
    assert ("lint", "actions/checkout@v4") in uses
    assert ("lint", "actions/setup-node@v4") in uses


def test_workflow_reusable_workflow_uses_edge(tmp_path):
    # Job-level `uses:` is a reusable-workflow call, not a step.
    r = extract_yaml(_write(tmp_path, "ci.yml", WORKFLOW))
    assert ("deploy", "./.github/workflows/release.yml") in _rel_pairs(r, "uses")


def test_workflow_detected_by_path_without_on_key(tmp_path):
    body = "jobs:\n  build:\n    steps:\n      - uses: actions/checkout@v4\n"
    p = _write(tmp_path, ".github/workflows/build.yml", body)
    assert "build" in set(_labels(extract_yaml(p)))


def test_run_steps_do_not_become_nodes(tmp_path):
    # `- run: pnpm lint` is a shell command, not a reference.
    r = extract_yaml(_write(tmp_path, "ci.yml", WORKFLOW))
    assert not any("pnpm lint" in lbl for lbl in _labels(r))


# ── Data YAML is deliberately not modelled ────────────────────────────────────

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


@pytest.mark.parametrize("name,body", [("deploy.yaml", K8S), ("openapi.yaml", OPENAPI)])
def test_data_yaml_returns_empty(tmp_path, name, body):
    # No dependency structure to model — left to the semantic pass, mirroring
    # how _is_config_json skips data JSON (#1224). Not even a file node, so the
    # file never shows up as an empty orphan in the graph.
    r = extract_yaml(_write(tmp_path, name, body))
    assert r.get("error") is None
    assert r["nodes"] == []
    assert r["edges"] == []


def test_services_list_is_not_mistaken_for_compose(tmp_path):
    # A `services:` LIST (not a mapping) is some other config's key.
    body = "services:\n  - alpha\n  - beta\n"
    r = extract_yaml(_write(tmp_path, "app.yaml", body))
    assert r["nodes"] == []


def test_empty_and_comment_only_files_are_safe(tmp_path):
    assert extract_yaml(_write(tmp_path, "a.yml", "")).get("error") is None
    r = extract_yaml(_write(tmp_path, "b.yml", "# just a comment\n"))
    assert r.get("error") is None
    assert r["nodes"] == []


def test_no_dangling_edge_sources(tmp_path):
    r = extract_yaml(_write(tmp_path, "docker-compose.yml", COMPOSE))
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"dangling source: {e['source']}"
        assert e["target"] in node_ids, f"dangling target: {e['target']}"


# ── Cross-file resolution ─────────────────────────────────────────────────────

def test_overlay_depends_on_resolves_onto_base_definition(tmp_path):
    """A Compose overlay referencing a service the base file defines must
    collapse onto the real node via the sourceless-stub rewire, not dangle as a
    second `db` node (the pattern SQL uses for cross-migration FKs, #2324)."""
    base = _write(tmp_path, "docker-compose.yml", "services:\n  db:\n    image: postgres:16\n")
    overlay = _write(
        tmp_path, "docker-compose.prod.yml",
        "services:\n  api:\n    image: api\n    depends_on:\n      - db\n",
    )

    r = extract([base.resolve(), overlay.resolve()], root=tmp_path)

    db_nodes = [n for n in r["nodes"] if n["label"] == "db"]
    assert len(db_nodes) == 1, f"expected one db node after rewire, got {db_nodes}"
    dep_targets = {e["target"] for e in r["edges"] if e["relation"] == "depends_on"}
    assert db_nodes[0]["id"] in dep_targets


def test_shared_action_merges_across_workflows(tmp_path):
    """The same action pinned by two workflows is one node, so `actions/checkout`
    becomes a real hub instead of one dangling stub per file."""
    a = _write(tmp_path, ".github/workflows/a.yml",
               "on: push\njobs:\n  one:\n    steps:\n      - uses: actions/checkout@v4\n")
    b = _write(tmp_path, ".github/workflows/b.yml",
               "on: push\njobs:\n  two:\n    steps:\n      - uses: actions/checkout@v4\n")

    r = extract([a.resolve(), b.resolve()], root=tmp_path)

    # Both files mint the anchor, so two dicts survive extraction sharing ONE id
    # — the same shape #1327 describes for `import CoreKit` from three files.
    # They collapse into a single graph node.
    checkout_ids = {n["id"] for n in r["nodes"] if n["label"] == "actions/checkout@v4"}
    assert len(checkout_ids) == 1, f"expected one shared action id, got {checkout_ids}"
    checkout_id = checkout_ids.pop()

    G = build_from_json({"nodes": r["nodes"], "edges": r["edges"]})
    assert G.has_node(checkout_id)
    sources = {e["source"] for e in r["edges"]
               if e["relation"] == "uses" and e["target"] == checkout_id}
    assert len(sources) == 2, "both workflows should point at the shared action node"
