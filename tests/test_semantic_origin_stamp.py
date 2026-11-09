"""Semantic-tier items must carry `_origin`, never be guessed by shape (#2843).

`build._is_ast_tier` reads `_origin` when present and otherwise falls back to
the shape of `source_location`: `L<line>` means AST. extract() stamps its own
items `ast`; nothing stamped the semantic side. A subagent (or a backend)
that reports `L12` for a document section therefore made that node read as
AST, and the next `graphify update` — which replaces the AST tier of every
re-extracted code file — deleted the document's whole semantic layer. On the
reporter's 21-document corpus: 8 files, 133 nodes, 236 edges lost on a
commit that touched one file.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from graphify.build import _is_ast_tier

try:
    from graphify.llm import _stamp_semantic_origin
except ImportError:  # pre-fix tree
    _stamp_semantic_origin = None

FRAGMENTS = Path(__file__).resolve().parent.parent / "tools" / "skillgen" / "fragments" / "core"


def _line_located_doc_node(**extra) -> dict:
    """What a subagent writes for a section of a document without section
    numbers: a line-number location, exactly the AST shape."""
    return {"id": "docs_guide_deploy", "label": "Deploy", "file_type": "document",
            "source_file": "docs/guide.md", "source_location": "L12", **extra}


def test_the_shape_fallback_is_the_trap():
    """Unstamped, a line-located document node reads as AST."""
    assert _is_ast_tier(_line_located_doc_node()) is True
    assert _is_ast_tier(_line_located_doc_node(_origin="semantic")) is False


@pytest.mark.skipif(_stamp_semantic_origin is None, reason="pre-fix tree")
def test_stamping_marks_nodes_and_edges_and_keeps_existing_marks():
    result = {
        "nodes": [_line_located_doc_node(), {"id": "x", "_origin": "ast"}],
        "edges": [{"source": "a", "target": "b", "relation": "references", "source_location": "L3"}],
        "hyperedges": [{"nodes": ["a", "b"]}],
    }
    out = _stamp_semantic_origin(result)
    assert out is result
    assert result["nodes"][0]["_origin"] == "semantic"
    assert result["nodes"][1]["_origin"] == "ast"  # never overwritten
    assert result["edges"][0]["_origin"] == "semantic"
    assert not _is_ast_tier(result["nodes"][0])
    assert not _is_ast_tier(result["edges"][0])
    assert "_origin" not in result["hyperedges"][0]  # hyperedges are semantic by construction


# ---------------------------------------------------------------------------
# The runbook's Part C — the block the reporter's run went through
# ---------------------------------------------------------------------------

def _part_c_python(fragment: Path) -> str:
    """The python passed to `-c` in the fragment's Part C block, unescaped the
    way the shell would hand it to the interpreter."""
    text = fragment.read_text(encoding="utf-8")
    start = text.index("#### Part C - Merge AST + semantic into final extraction")
    block = text[start:]
    m = re.search(r'-c "\n(.*?)\n"\n```', block, re.S)
    assert m, f"no Part C python block in {fragment.name}"
    return m.group(1).replace('\\"', '"')


@pytest.mark.parametrize("fragment", ["core.md", "aider.md", "devin.md"])
def test_part_c_stamps_the_semantic_side(fragment, tmp_path):
    code = _part_c_python(FRAGMENTS / fragment)
    # The three runbooks read their intermediates from different places.
    ast_path = re.search(r"Path\('([^']*\.graphify_ast\.json)'\)", code).group(1)
    sem_path = re.search(r"Path\('([^']*\.graphify_semantic\.json)'\)", code).group(1)
    out_path = re.search(r"Path\('([^']*\.graphify_extract\.json)'\)", code).group(1)
    for rel in (ast_path, sem_path, out_path):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "graphify-out").mkdir(exist_ok=True)
    ast = {"nodes": [{"id": "src_app_main", "label": "main", "file_type": "code",
                      "source_file": "src/app.py", "source_location": "L1", "_origin": "ast"}],
           "edges": []}
    sem = {"nodes": [_line_located_doc_node()],
           "edges": [{"source": "docs_guide_deploy", "target": "src_app_main",
                      "relation": "references", "source_file": "docs/guide.md",
                      "source_location": "L12", "confidence": "EXTRACTED"}],
           "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    (tmp_path / ast_path).write_text(json.dumps(ast), encoding="utf-8")
    (tmp_path / sem_path).write_text(json.dumps(sem), encoding="utf-8")
    r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    merged = json.loads((tmp_path / out_path).read_text(encoding="utf-8"))
    by_id = {n["id"]: n for n in merged["nodes"]}
    assert by_id["src_app_main"]["_origin"] == "ast"
    assert by_id["docs_guide_deploy"]["_origin"] == "semantic"
    assert all(e["_origin"] == "semantic" for e in merged["edges"] if e["source_file"] == "docs/guide.md")
    assert not _is_ast_tier(by_id["docs_guide_deploy"])


# ---------------------------------------------------------------------------
# The consequence: an incremental rebuild keeps the document's layer
# ---------------------------------------------------------------------------

def test_a_stamped_document_survives_the_code_files_re_extraction(tmp_path):
    """The failure the reporter measured: re-extract one code file, and the
    line-located document node — unstamped — is treated as that file's stale
    AST and dropped. Stamped, it stays."""
    from graphify.build import build_from_json, build_merge
    from graphify.export import to_json

    def graph_with(doc_node):
        extraction = {
            "nodes": [
                {"id": "src_app_main", "label": "main", "file_type": "code",
                 "source_file": "src/app.py", "source_location": "L1", "_origin": "ast"},
                doc_node,
            ],
            "edges": [{"source": "docs_guide_deploy", "target": "src_app_main",
                       "relation": "references", "source_file": "docs/guide.md",
                       "confidence": "EXTRACTED", **({"_origin": "semantic"} if "_origin" in doc_node else {})}],
            "hyperedges": [],
        }
        G = build_from_json(extraction)
        p = tmp_path / f"graph_{'stamped' if '_origin' in doc_node else 'bare'}.json"
        to_json(G, {0: list(G.nodes)}, str(p))
        return p

    re_extraction = {
        "nodes": [{"id": "src_app_main", "label": "main", "file_type": "code",
                   "source_file": "src/app.py", "source_location": "L2", "_origin": "ast"}],
        "edges": [], "hyperedges": [],
    }

    stamped = build_merge([re_extraction], graph_with(_line_located_doc_node(_origin="semantic")))
    assert "docs_guide_deploy" in stamped.nodes, "the stamped document node must survive"


@pytest.mark.parametrize("no_cluster", [False, True])
def test_update_keeps_semantic_evidence_when_an_ast_id_collides(tmp_path, no_cluster):
    from graphify.watch import _rebuild_code

    (tmp_path / "sample.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    (tmp_path / "design.md").write_text("# Design\nA stable protocol.\n", encoding="utf-8")
    out = tmp_path / "graphify-out"
    out.mkdir()
    graph = out / "graph.json"
    graph.write_text(json.dumps({
        "nodes": [
            {"id": "sample", "label": "Sample protocol", "file_type": "concept",
             "source_file": "design.md", "source_location": None, "_origin": "semantic"},
            {"id": "sample_answer", "label": "answer()", "file_type": "code",
             "source_file": "sample.py", "source_location": "L1", "_origin": "ast"},
        ],
        "links": [
            {"source": "sample", "target": "sample_answer", "relation": "motivates",
             "source_file": "design.md", "_origin": "semantic",
             "confidence": "INFERRED", "confidence_score": 0.9},
        ],
    }), encoding="utf-8")

    assert _rebuild_code(tmp_path, no_cluster=no_cluster)
    rebuilt = json.loads(graph.read_text(encoding="utf-8"))
    evidence = next(n for n in rebuilt["nodes"] if n["label"] == "Sample protocol")
    assert evidence["_origin"] == "semantic"
    assert evidence["source_file"] == "design.md"
    assert any(n["id"] == "sample" and n["source_file"] == "sample.py"
               for n in rebuilt["nodes"])
    assert any(e["source"] == evidence["id"] and e["target"] == "sample_answer"
               and e["relation"] == "motivates" and e["_origin"] == "semantic"
               for e in rebuilt["links"])

    assert _rebuild_code(tmp_path, no_cluster=no_cluster)
    assert json.loads(graph.read_text(encoding="utf-8")) == rebuilt


@pytest.mark.parametrize("no_cluster", [False, True])
@pytest.mark.parametrize("prior", [
    {"id": "sample_answer", "label": "Old rationale", "file_type": "concept",
     "source_file": "sample.py", "source_location": None, "_origin": "semantic"},
    {"id": "sample", "label": "sample", "file_type": "concept", "source_file": ""},
    {"id": "sample_answer", "label": "Orphan note", "file_type": "concept",
     "source_file": "", "_origin": "semantic"},
], ids=["same-source", "external-stub", "sourceless"])
def test_unattributed_semantics_never_replace_a_fresh_ast_definition(tmp_path, no_cluster, prior):
    from graphify.watch import _rebuild_code

    (tmp_path / "sample.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    out = tmp_path / "graphify-out"
    out.mkdir()
    graph = out / "graph.json"
    graph.write_text(json.dumps({
        "nodes": [prior],
        "links": [{"source": "sample_answer", "target": "sample", "relation": "imports",
                   "source_file": "sample.py", "_origin": "ast", "confidence": "EXTRACTED"}],
    }), encoding="utf-8")

    assert _rebuild_code(tmp_path, no_cluster=no_cluster)
    rebuilt = json.loads(graph.read_text(encoding="utf-8"))
    node = next(n for n in rebuilt["nodes"] if n["id"] == prior["id"])
    assert node["_origin"] == "ast"
    assert node["source_file"] == "sample.py"
    assert node["source_location"] == "L1"
    assert node["label"] == ("sample.py" if prior["id"] == "sample" else "answer()")


@pytest.mark.parametrize("no_cluster", [False, True])
def test_update_keeps_both_semantic_nodes_when_the_reference_namespace_is_taken(tmp_path, no_cluster):
    from graphify.watch import _rebuild_code

    (tmp_path / "sample.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    for name in ("design.md", "notes.md"):
        (tmp_path / name).write_text("# Evidence\nA stable protocol.\n", encoding="utf-8")
    out = tmp_path / "graphify-out"
    out.mkdir()
    graph = out / "graph.json"
    graph.write_text(json.dumps({
        "nodes": [
            {"id": "sample", "label": "Sample protocol", "file_type": "concept",
             "source_file": "design.md", "_origin": "semantic"},
            {"id": "design__ref__sample", "label": "Independent note", "file_type": "concept",
             "source_file": "notes.md", "_origin": "semantic"},
            {"id": "sample_answer", "label": "answer()", "file_type": "code",
             "source_file": "sample.py", "source_location": "L1", "_origin": "ast"},
        ],
        "links": [{"source": "sample", "target": "sample_answer", "relation": "motivates",
                   "source_file": "design.md", "_origin": "semantic",
                   "confidence": "INFERRED", "confidence_score": 0.9}],
    }), encoding="utf-8")

    assert _rebuild_code(tmp_path, no_cluster=no_cluster)
    rebuilt = json.loads(graph.read_text(encoding="utf-8"))
    protocol = next(n for n in rebuilt["nodes"] if n["label"] == "Sample protocol")
    note = next(n for n in rebuilt["nodes"] if n["label"] == "Independent note")
    assert protocol["id"] != note["id"]
    assert any(n["id"] == "sample" and n["source_file"] == "sample.py"
               and n["_origin"] == "ast" for n in rebuilt["nodes"])
    assert any(e["source"] == protocol["id"] and e["target"] == "sample_answer"
               and e["relation"] == "motivates" and e["confidence_score"] == 0.9
               for e in rebuilt["links"])


@pytest.mark.parametrize("no_cluster", [False, True])
def test_semantic_alias_keeps_authored_ast_links_and_document_provenance(tmp_path, no_cluster):
    from graphify.watch import _rebuild_code

    (tmp_path / "sample.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    (tmp_path / "design.md").write_text("# Design\nA stable protocol.\n", encoding="utf-8")
    out = tmp_path / "graphify-out"
    out.mkdir()
    graph = out / "graph.json"
    graph.write_text(json.dumps({
        "nodes": [
            {"id": "sample", "label": "Sample protocol", "file_type": "concept",
             "source_file": "design.md", "_origin": "semantic",
             "attributes": {"document_version": "v1"}},
            {"id": "design", "label": "design.md", "file_type": "document",
             "source_file": "design.md", "source_location": "L1", "_origin": "ast"},
            {"id": "sample_answer", "label": "answer()", "file_type": "code",
             "source_file": "sample.py", "source_location": "L1", "_origin": "ast"},
        ],
        "links": [
            {"source": "design", "target": "sample", "relation": "references",
             "source_file": "design.md", "_origin": "ast", "confidence": "EXTRACTED"},
            {"source": "sample", "target": "sample_answer", "relation": "motivates",
             "source_file": "design.md", "_origin": "semantic",
             "confidence": "INFERRED", "confidence_score": 0.9},
        ],
        "hyperedges": [{"id": "protocol", "nodes": ["design", "sample", "sample_answer"],
                        "source_file": "design.md", "relation": "explains"}],
    }), encoding="utf-8")

    assert _rebuild_code(tmp_path, no_cluster=no_cluster)
    rebuilt = json.loads(graph.read_text(encoding="utf-8"))
    protocol = next(n for n in rebuilt["nodes"] if n["label"] == "Sample protocol")
    assert protocol["attributes"]["document_version"] == "v1"
    assert any(e["source"] == "design" and e["target"] == "sample"
               and e["_origin"] == "ast" for e in rebuilt["links"])
    semantic = next(e for e in rebuilt["links"] if e["relation"] == "motivates")
    assert semantic["source"] == protocol["id"]
    assert semantic["confidence"] == "INFERRED"
    assert semantic["confidence_score"] == 0.9
    assert set(rebuilt["hyperedges"][0]["nodes"]) == {"design", protocol["id"], "sample_answer"}
