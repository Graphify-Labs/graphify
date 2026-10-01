"""Regression tests for issue #3246: Semantic whole-file aliases canonicalize onto AST file nodes.

When a documentation or plan file (e.g. `_PLANS/SLICE_2026-08-15_rotating-testpilot-keys.md`)
mentions a code file (e.g. `scripts/generate-testpilot-keys.mjs`), semantic extraction
mints a suffixed entity node (e.g. `scripts_generate_testpilot_keys_module`,
`scripts_generate_testpilot_keys_script`, or `scripts_generate_testpilot_keys_file`)
rather than matching the bare file stem AST node `scripts_generate_testpilot_keys`.

These tests enforce that:
1. Whole-file semantic aliases canonicalize onto the existing AST file-level node.
2. The AST node remains the canonical survivor (preserving _origin="ast", source_file, source_location).
3. Semantic attributes (e.g. rationale, metadata) are merged without overwriting authoritative AST fields.
4. Incoming/outgoing edges and hyperedges targeting the semantic alias are rewired to the AST file node.
5. Genuine nested symbol definitions (e.g. `scripts_generate_testpilot_keys_run`) are NOT collapsed.
6. Cross-file safety: similarly named files in different paths remain distinct.
"""
from __future__ import annotations

import pytest
from graphify.build import build_from_json


def test_primary_regression_semantic_module_alias_canonicalizes_to_ast_file_node():
    """#3246 Primary regression:
    An AST file node and a semantic `*_module` alias describing that file must
    collapse into the single canonical AST node, and references must rewire."""
    ext = {
        "nodes": [
            {
                "id": "scripts_generate_testpilot_keys",
                "label": "generate-testpilot-keys.mjs",
                "source_file": "scripts/generate-testpilot-keys.mjs",
                "source_location": "L1",
                "_origin": "ast",
                "file_type": "code",
            },
            {
                "id": "scripts_generate_testpilot_keys_module",
                "label": "generate-testpilot-keys.mjs script",
                "source_file": "_PLANS/SLICE_2026-08-15_rotating-testpilot-keys.md",
                "_origin": "semantic",
                "file_type": "code",
                "rationale": "Utility script for rotating testpilot keys",
            },
            {
                "id": "plans_slice_rotating_keys",
                "label": "Rotating Testpilot Keys Plan",
                "source_file": "_PLANS/SLICE_2026-08-15_rotating-testpilot-keys.md",
                "source_location": "L1",
                "_origin": "ast",
                "file_type": "document",
            },
        ],
        "edges": [
            {
                "source": "plans_slice_rotating_keys",
                "target": "scripts_generate_testpilot_keys_module",
                "relation": "references",
                "confidence": "EXTRACTED",
                "source_file": "_PLANS/SLICE_2026-08-15_rotating-testpilot-keys.md",
                "weight": 1.0,
            }
        ],
        "input_tokens": 0,
        "output_tokens": 0,
    }

    G = build_from_json(ext)

    # Exactly one code file node must survive
    assert "scripts_generate_testpilot_keys" in G.nodes
    assert "scripts_generate_testpilot_keys_module" not in G.nodes

    # AST node is canonical survivor and retains authoritative metadata
    ast_node = G.nodes["scripts_generate_testpilot_keys"]
    assert ast_node["source_file"] == "scripts/generate-testpilot-keys.mjs"
    assert ast_node["source_location"] == "L1"
    assert ast_node["_origin"] == "ast"
    assert ast_node["label"] == "generate-testpilot-keys.mjs"

    # Semantic attributes are preserved
    assert ast_node.get("rationale") == "Utility script for rotating testpilot keys"

    # Incoming edge targeting the semantic alias is rewired to the AST file node
    assert G.has_edge("plans_slice_rotating_keys", "scripts_generate_testpilot_keys")
    assert not G.has_edge("plans_slice_rotating_keys", "scripts_generate_testpilot_keys_module")


@pytest.mark.parametrize("suffix,label_suffix", [
    ("script", "script"),
    ("file", "file"),
    ("module", "module"),
])
def test_other_whole_file_aliases(suffix, label_suffix):
    """#3246: Verify canonicalization for supported whole-file alias suffixes (_script, _file, _module)."""
    alias_id = f"src_auth_session_{suffix}"
    ext = {
        "nodes": [
            {
                "id": "src_auth_session",
                "label": "session.py",
                "source_file": "src/auth/session.py",
                "source_location": "L1",
                "_origin": "ast",
                "file_type": "code",
            },
            {
                "id": alias_id,
                "label": f"session.py {label_suffix}",
                "source_file": "docs/architecture.md",
                "_origin": "semantic",
                "file_type": "code",
                "summary": "Session management implementation",
            },
            {
                "id": "docs_architecture",
                "label": "Architecture Guide",
                "source_file": "docs/architecture.md",
                "source_location": "L1",
                "_origin": "ast",
                "file_type": "document",
            },
        ],
        "edges": [
            {
                "source": "docs_architecture",
                "target": alias_id,
                "relation": "describes",
                "confidence": "EXTRACTED",
                "source_file": "docs/architecture.md",
                "weight": 1.0,
            }
        ],
        "input_tokens": 0,
        "output_tokens": 0,
    }

    G = build_from_json(ext)

    assert "src_auth_session" in G.nodes
    assert alias_id not in G.nodes
    assert G.has_edge("docs_architecture", "src_auth_session")


def test_symbol_safety_nested_symbols_not_collapsed():
    """#3246 Symbol safety:
    Genuine symbol definitions beneath the file stem (e.g. `_run`, `_validatetoken`)
    must NEVER be collapsed into the file-level node."""
    ext = {
        "nodes": [
            {
                "id": "scripts_generate_testpilot_keys",
                "label": "generate-testpilot-keys.mjs",
                "source_file": "scripts/generate-testpilot-keys.mjs",
                "source_location": "L1",
                "_origin": "ast",
                "file_type": "code",
            },
            {
                "id": "scripts_generate_testpilot_keys_run",
                "label": "run",
                "source_file": "_PLANS/SLICE_2026-08-15_rotating-testpilot-keys.md",
                "_origin": "semantic",
                "file_type": "code",
            },
            {
                "id": "scripts_generate_testpilot_keys_parse_args",
                "label": "parseArgs",
                "source_file": "scripts/generate-testpilot-keys.mjs",
                "source_location": "L15",
                "_origin": "ast",
                "file_type": "code",
            },
        ],
        "edges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }

    G = build_from_json(ext)

    # All three distinct entities must survive
    assert "scripts_generate_testpilot_keys" in G.nodes
    assert "scripts_generate_testpilot_keys_run" in G.nodes
    assert "scripts_generate_testpilot_keys_parse_args" in G.nodes
    assert G.number_of_nodes() == 3


def test_cross_file_safety_similarly_named_files_do_not_merge():
    """#3246 Cross-file safety:
    Aliases must only canonicalize onto the AST file node that matches their exact path stem."""
    ext = {
        "nodes": [
            {
                "id": "scripts_generate_testpilot_keys",
                "label": "generate-testpilot-keys.mjs",
                "source_file": "scripts/generate-testpilot-keys.mjs",
                "source_location": "L1",
                "_origin": "ast",
                "file_type": "code",
            },
            {
                "id": "tools_generate_testpilot_keys",
                "label": "generate-testpilot-keys.mjs",
                "source_file": "tools/generate-testpilot-keys.mjs",
                "source_location": "L1",
                "_origin": "ast",
                "file_type": "code",
            },
            {
                "id": "tools_generate_testpilot_keys_module",
                "label": "tools generate-testpilot-keys.mjs",
                "source_file": "docs/tools.md",
                "_origin": "semantic",
                "file_type": "code",
            },
            {
                "id": "docs_tools",
                "label": "Tools Guide",
                "source_file": "docs/tools.md",
                "source_location": "L1",
                "_origin": "ast",
                "file_type": "document",
            },
        ],
        "edges": [
            {
                "source": "docs_tools",
                "target": "tools_generate_testpilot_keys_module",
                "relation": "references",
                "confidence": "EXTRACTED",
                "source_file": "docs/tools.md",
                "weight": 1.0,
            }
        ],
        "input_tokens": 0,
        "output_tokens": 0,
    }

    G = build_from_json(ext)

    # scripts node remains untouched
    assert "scripts_generate_testpilot_keys" in G.nodes
    # tools alias merges ONLY into tools AST node
    assert "tools_generate_testpilot_keys" in G.nodes
    assert "tools_generate_testpilot_keys_module" not in G.nodes
    assert G.has_edge("docs_tools", "tools_generate_testpilot_keys")
    assert not G.has_edge("docs_tools", "scripts_generate_testpilot_keys")


def test_provenance_ast_authority_preserved_and_semantic_attributes_retained():
    """#3246 Provenance:
    The AST survivor must keep its authoritative _origin, source_file, and source_location,
    while inheriting non-conflicting semantic attributes."""
    ext = {
        "nodes": [
            {
                "id": "pkg_worker",
                "label": "worker.py",
                "source_file": "pkg/worker.py",
                "source_location": "L1",
                "_origin": "ast",
                "file_type": "code",
            },
            {
                "id": "pkg_worker_module",
                "label": "worker.py module",
                "source_file": "docs/specs.md",
                "source_location": "L100",
                "_origin": "semantic",
                "file_type": "concept",
                "rationale": "Background job queue processor",
                "custom_metadata": {"concurrency": 4},
            },
        ],
        "edges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }

    G = build_from_json(ext)

    assert "pkg_worker" in G.nodes
    assert "pkg_worker_module" not in G.nodes

    survivor = G.nodes["pkg_worker"]
    # Authoritative AST fields are preserved
    assert survivor["_origin"] == "ast"
    assert survivor["source_file"] == "pkg/worker.py"
    assert survivor["source_location"] == "L1"
    assert survivor["file_type"] == "code"

    # Semantic attributes are retained
    assert survivor.get("rationale") == "Background job queue processor"
    assert survivor.get("custom_metadata") == {"concurrency": 4}


def test_edge_and_hyperedge_rewiring_on_canonical_merge():
    """#3246 Edge and Hyperedge rewiring:
    Incoming edges, outgoing edges, and hyperedge member lists referencing
    the semantic alias must all rewire to the canonical AST file node."""
    ext = {
        "nodes": [
            {
                "id": "scripts_generate_testpilot_keys",
                "label": "generate-testpilot-keys.mjs",
                "source_file": "scripts/generate-testpilot-keys.mjs",
                "source_location": "L1",
                "_origin": "ast",
                "file_type": "code",
            },
            {
                "id": "scripts_generate_testpilot_keys_module",
                "label": "generate-testpilot-keys.mjs script",
                "source_file": "_PLANS/SLICE.md",
                "_origin": "semantic",
                "file_type": "code",
            },
            {
                "id": "target_service",
                "label": "AuthService",
                "source_file": "src/auth.mjs",
                "source_location": "L10",
                "_origin": "ast",
                "file_type": "code",
            },
            {
                "id": "doc_plan",
                "label": "Plan Doc",
                "source_file": "_PLANS/SLICE.md",
                "source_location": "L1",
                "_origin": "ast",
                "file_type": "document",
            },
        ],
        "edges": [
            # Incoming edge to alias
            {
                "source": "doc_plan",
                "target": "scripts_generate_testpilot_keys_module",
                "relation": "references",
                "confidence": "EXTRACTED",
                "source_file": "_PLANS/SLICE.md",
                "weight": 1.0,
            },
            # Outgoing edge from alias
            {
                "source": "scripts_generate_testpilot_keys_module",
                "target": "target_service",
                "relation": "calls",
                "confidence": "INFERRED",
                "source_file": "_PLANS/SLICE.md",
                "weight": 1.0,
            },
        ],
        "hyperedges": [
            {
                "id": "h_auth_setup",
                "label": "Auth Setup Flow",
                "nodes": ["doc_plan", "scripts_generate_testpilot_keys_module", "target_service"],
                "relation": "participate_in",
                "confidence": "INFERRED",
            }
        ],
        "input_tokens": 0,
        "output_tokens": 0,
    }

    G = build_from_json(ext)

    assert "scripts_generate_testpilot_keys_module" not in G.nodes
    assert "scripts_generate_testpilot_keys" in G.nodes

    # Incoming edge rewired
    assert G.has_edge("doc_plan", "scripts_generate_testpilot_keys")
    # Outgoing edge rewired
    assert G.has_edge("scripts_generate_testpilot_keys", "target_service")

    # Hyperedge member list rewired
    he = G.graph.get("hyperedges", [None])[0]
    assert he is not None
    assert "scripts_generate_testpilot_keys" in he["nodes"]
    assert "scripts_generate_testpilot_keys_module" not in he["nodes"]
