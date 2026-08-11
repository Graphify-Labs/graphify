from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from graphify.build import build_from_json
from graphify.extract import extract
from graphify.lattice_ingest import (
    extract_lattice_markdown,
    is_lattice_markdown_path,
    validate_lattice,
)
from graphify.serve import _query_graph_text


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_lattice_markdown_emits_stable_sections_summaries_and_wiki_edges(tmp_path):
    overview = _write(
        tmp_path / "lat.md" / "architecture" / "overview.md",
        "# Architecture\n\nSystem-wide design constraints.\n\n"
        "## Tenant isolation\n\nEvery query is scoped by tenant_id. See [[operations#Deployment]].\n",
    )
    _write(
        tmp_path / "lat.md" / "operations.md",
        "# Operations\n\nOperational guidance.\n\n## Deployment\n\nDeploy through the documented pipeline.\n",
    )

    result = extract_lattice_markdown(overview)
    nodes = {node["knowledge_id"]: node for node in result["nodes"] if node.get("knowledge_id")}

    assert is_lattice_markdown_path(overview)
    assert "architecture/overview#Architecture" in nodes
    assert "architecture/overview#Architecture#Tenant isolation" in nodes
    tenant = nodes["architecture/overview#Architecture#Tenant isolation"]
    assert tenant["type"] == "knowledge_section"
    assert tenant["summary"] == "Every query is scoped by tenant_id. See [[operations#Deployment]]."
    assert tenant["source_location"] == "L5"

    relations = {(edge["relation"], edge.get("knowledge_target")) for edge in result["edges"]}
    assert ("references", "operations#Deployment") in relations
    assert any(edge["relation"] == "contains" for edge in result["edges"])


def test_lattice_ignores_example_links_and_emits_source_documentation_edges(tmp_path):
    source = _write(tmp_path / "src" / "service.py", "def enforce():\n    return True\n")
    spec = _write(
        tmp_path / "lat.md" / "security.md",
        "# Security\n\nDocuments [[src/service.py#enforce]].\n\n"
        "## Syntax examples\n\nInline `[[not-a-reference]]` and fenced examples are ignored.\n\n"
        "```md\n[[also-not-a-reference]]\n```\n",
    )

    result = extract([spec, source], cache_root=tmp_path, root=tmp_path, parallel=False)
    graph = build_from_json(result, directed=True, root=tmp_path)

    documented = [
        (graph.nodes[src].get("knowledge_id"), graph.nodes[dst].get("source_file"))
        for src, dst, data in graph.edges(data=True)
        if data.get("relation") == "documents"
    ]
    assert ("security#Security", "src/service.py") in documented
    diagnostics = validate_lattice(tmp_path)
    assert diagnostics["valid"] is True, diagnostics["errors"]


def test_full_extract_links_at_lat_comment_to_knowledge_section(tmp_path):
    spec = _write(
        tmp_path / "lat.md" / "security.md",
        "# Security\n\nSecurity constraints.\n\n## Tenant isolation\n\nAll reads require tenant_id.\n",
    )
    source = _write(
        tmp_path / "src" / "repository.py",
        "# @lat: [[security#Security#Tenant isolation]]\n"
        "def load_orders(tenant_id):\n"
        "    return tenant_id\n",
    )

    result = extract([spec, source], cache_root=tmp_path, root=tmp_path, parallel=False)
    graph = build_from_json(result, directed=True, root=tmp_path)

    edges = [
        (src, dst, data)
        for src, dst, data in graph.edges(data=True)
        if data.get("relation") == "implemented_by"
    ]
    assert len(edges) == 1
    src, dst, data = edges[0]
    assert graph.nodes[src]["knowledge_id"] == "security#Security#Tenant isolation"
    assert graph.nodes[dst]["source_file"] == "src/repository.py"
    assert data["source_location"] == "L1"


def test_full_extract_resolves_cross_file_short_wiki_reference(tmp_path):
    overview = _write(
        tmp_path / "lat.md" / "overview.md",
        "# Overview\n\nArchitecture overview.\n\n## Runtime\n\nSee [[operations#Deployment]].\n",
    )
    operations = _write(
        tmp_path / "lat.md" / "operations.md",
        "# Operations\n\nOperations summary.\n\n## Deployment\n\nDeployment constraints.\n",
    )

    result = extract([overview, operations], cache_root=tmp_path, root=tmp_path, parallel=False)
    graph = build_from_json(result, directed=True, root=tmp_path)

    reference_edges = [
        (graph.nodes[src].get("knowledge_id"), graph.nodes[dst].get("knowledge_id"))
        for src, dst, data in graph.edges(data=True)
        if data.get("relation") == "references"
    ]
    assert (
        "overview#Overview#Runtime",
        "operations#Operations#Deployment",
    ) in reference_edges


def test_dotted_lattice_file_reference_is_not_misclassified_as_source(tmp_path):
    overview = _write(
        tmp_path / "lat.md" / "overview.md",
        "# Overview\n\nSee [[operations.v2#Deployment]].\n",
    )
    operations = _write(
        tmp_path / "lat.md" / "operations.v2.md",
        "# Operations\n\n## Deployment\n\nDeployment constraints.\n",
    )

    result = extract([overview, operations], cache_root=tmp_path, root=tmp_path, parallel=False)
    graph = build_from_json(result, directed=True, root=tmp_path)

    assert any(
        data.get("relation") == "references"
        and graph.nodes[dst].get("knowledge_id") == "operations.v2#Operations#Deployment"
        for _, dst, data in graph.edges(data=True)
    )


def test_lattice_change_rescans_unchanged_source_mentions(tmp_path):
    _write(
        tmp_path / "src" / "repository.py",
        "# @lat: [[security#Security#Tenant isolation]]\ndef load():\n    return True\n",
    )
    spec = _write(
        tmp_path / "lat.md" / "security.md",
        "# Security\n\n## Tenant isolation\n\nAll reads require tenant_id.\n",
    )

    # An incremental update may pass only the changed lattice file. Graphify must
    # still rediscover @lat mentions in unchanged source files.
    result = extract([spec], cache_root=tmp_path, root=tmp_path, parallel=False)

    assert any(
        edge.get("relation") == "implemented_by"
        and edge.get("knowledge_id") == "security#Security#Tenant isolation"
        and edge["source_file"] == "src/repository.py"
        for edge in result["edges"]
    )


def test_source_reference_cannot_escape_project_root(tmp_path):
    outside = _write(tmp_path.parent / "outside.py", "SECRET = True\n")
    _write(
        tmp_path / "lat.md" / "security.md",
        "# Security\n\nNever index [[../outside.py#SECRET]].\n",
    )

    diagnostics = validate_lattice(tmp_path)

    assert diagnostics["valid"] is False
    assert any(error["code"] == "unsafe-source-reference" for error in diagnostics["errors"])
    assert str(outside.resolve()) not in json.dumps(diagnostics)


def test_validation_respects_graphifyignore_when_scanning_code_mentions(tmp_path):
    _write(tmp_path / ".graphifyignore", "ignored/\n")
    _write(
        tmp_path / "lat.md" / "security.md",
        "---\nlat:\n  require-code-mention: true\n---\n"
        "# Security\n\n## Tenant isolation\n\nAll reads require tenant_id.\n",
    )
    _write(
        tmp_path / "ignored" / "fake.py",
        "# @lat: [[security#Security#Tenant isolation]]\n",
    )

    diagnostics = validate_lattice(tmp_path)

    assert diagnostics["valid"] is False
    assert any(error["code"] == "missing-code-mention" for error in diagnostics["errors"])


def test_validate_lattice_reports_broken_ambiguous_and_unimplemented_required_sections(tmp_path):
    _write(tmp_path / "lat.md" / "a" / "rules.md", "# Rules\n\nA rules summary.\n")
    _write(tmp_path / "lat.md" / "b" / "rules.md", "# Rules\n\nB rules summary.\n")
    _write(
        tmp_path / "lat.md" / "index.md",
        "---\nlat:\n  require-code-mention: true\n---\n"
        "# Index\n\nIndex summary.\n\n"
        "## Required behavior\n\nMust be implemented. See [[rules#Rules]] and [[missing#Section]].\n",
    )

    diagnostics = validate_lattice(tmp_path)
    codes = {item["code"] for item in diagnostics["errors"]}

    assert diagnostics["valid"] is False
    assert "ambiguous-reference" in codes
    assert "broken-reference" in codes
    assert "missing-code-mention" in codes


def test_check_knowledge_cli_returns_json_and_nonzero_for_invalid_lattice(tmp_path):
    _write(tmp_path / "lat.md" / "index.md", "# Index\n\nSee [[missing#Section]].\n")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[1])

    result = subprocess.run(
        [sys.executable, "-m", "graphify", "check-knowledge", str(tmp_path), "--json"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["valid"] is False
    assert payload["errors"][0]["code"] == "broken-reference"


def test_query_retrieves_lattice_summary_after_normal_extraction(tmp_path):
    spec = _write(
        tmp_path / "lat.md" / "security.md",
        "# Security\n\nAuthentication and authorization constraints.\n\n"
        "## Tenant isolation\n\nEvery database query must include tenant_id.\n",
    )
    result = extract([spec], cache_root=tmp_path, root=tmp_path, parallel=False)
    graph = build_from_json(result, directed=True, root=tmp_path)

    output = _query_graph_text(graph, "tenant_id database query", token_budget=500)

    assert "Tenant isolation" in output
    assert "Every database query must include tenant_id." in output
