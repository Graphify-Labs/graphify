"""Tests for scoped AST symbol inventory generation and integration (Issue #3253)."""
from pathlib import Path
import pytest
from graphify.extract import scope_ast_inventory
from graphify.build import build_from_json
def test_path_matching():
    """Document mentioning graphify/auth/session.py selects symbols from that file."""
    ast_data = {
        "nodes": [
            {"id": "graphify_auth_session_py", "label": "session.py", "source_file": "graphify/auth/session.py"},
            {"id": "graphify_auth_session_sessionmanager", "label": "SessionManager", "source_file": "graphify/auth/session.py"},
            {"id": "other_file_foo", "label": "Foo", "source_file": "other/file.py"},
        ],
        "edges": [
            {"source": "graphify_auth_session_py", "target": "graphify_auth_session_sessionmanager", "relation": "contains"},
        ],
    }
    doc_text = "See graphify/auth/session.py for authentication handling."
    result = scope_ast_inventory(ast_data, ["docs/auth.md"], [doc_text])
    assert "graphify_auth_session_sessionmanager | SessionManager | graphify/auth/session.py" in result
    assert "graphify_auth_session_py | session.py | graphify/auth/session.py" in result
    assert "other_file_foo" not in result
def test_unique_basename():
    """Document mentioning unique basename session.py selects the file and its symbols."""
    ast_data = {
        "nodes": [
            {"id": "src_auth_session_py", "label": "session.py", "source_file": "src/auth/session.py"},
            {"id": "src_auth_session_token", "label": "Token", "source_file": "src/auth/session.py"},
            {"id": "src_other_worker_py", "label": "worker.py", "source_file": "src/other/worker.py"},
        ],
        "edges": [],
    }
    doc_text = "Refer to session.py for token details."
    result = scope_ast_inventory(ast_data, ["docs/spec.md"], [doc_text])
    assert "src_auth_session_token | Token | src/auth/session.py" in result
    assert "src_other_worker_py" not in result
def test_ambiguous_basename():
    """Ambiguous basenames (e.g. index.ts, session.py in multiple dirs) are NOT selected by bare basename."""
    ast_data = {
        "nodes": [
            {"id": "src_a_session_py", "label": "session.py", "source_file": "src/a/session.py"},
            {"id": "src_a_session_foo", "label": "FooA", "source_file": "src/a/session.py"},
            {"id": "src_b_session_py", "label": "session.py", "source_file": "src/b/session.py"},
            {"id": "src_b_session_bar", "label": "BarB", "source_file": "src/b/session.py"},
        ],
        "edges": [],
    }
    # Bare basename "session.py" is ambiguous
    doc_text = "Refer to session.py for details."
    result = scope_ast_inventory(ast_data, ["docs/spec.md"], [doc_text])
    assert result == "None available"
    # Specific path matches the correct one
    doc_text_specific = "Refer to src/a/session.py for details."
    result_specific = scope_ast_inventory(ast_data, ["docs/spec.md"], [doc_text_specific])
    assert "src_a_session_foo | FooA | src/a/session.py" in result_specific
    assert "src_b_session_bar" not in result_specific
def test_distinctive_identifier_matching():
    """Distinctive identifier like ValidateToken matches its AST node."""
    ast_data = {
        "nodes": [
            {"id": "src_auth_session_py", "label": "session.py", "source_file": "src/auth/session.py"},
            {"id": "src_auth_session_validatetoken", "label": "ValidateToken()", "source_file": "src/auth/session.py"},
            {"id": "src_other_unrelated", "label": "UnrelatedHelper()", "source_file": "src/other.py"},
        ],
        "edges": [],
    }
    doc_text = "Clients must call ValidateToken before making API requests."
    result = scope_ast_inventory(ast_data, ["docs/api.md"], [doc_text])
    assert "src_auth_session_validatetoken | ValidateToken() | src/auth/session.py" in result
    assert "unrelated" not in result.lower()
def test_generic_identifier_filtering():
    """Generic identifiers (run, test, parse, data, get, set) do not match every symbol."""
    ast_data = {
        "nodes": [
            {"id": "pkg_a_run", "label": "run()", "source_file": "pkg/a.py"},
            {"id": "pkg_b_run", "label": "run()", "source_file": "pkg/b.py"},
            {"id": "pkg_c_main", "label": "main()", "source_file": "pkg/c.py"},
        ],
        "edges": [],
    }
    doc_text = "Please run the test suite and check the main data pipeline."
    result = scope_ast_inventory(ast_data, ["docs/guide.md"], [doc_text])
    assert result == "None available"
def test_class_containment_expansion():
    """Mentioning a class expands to its contained methods."""
    ast_data = {
        "nodes": [
            {"id": "src_auth_sessionmanager", "label": "SessionManager", "source_file": "src/auth.py"},
            {"id": "src_auth_sessionmanager_validate", "label": ".validate()", "source_file": "src/auth.py"},
            {"id": "src_auth_sessionmanager_logout", "label": ".logout()", "source_file": "src/auth.py"},
            {"id": "src_other_unrelated", "label": "OtherClass", "source_file": "src/other.py"},
        ],
        "edges": [
            {"source": "src_auth_sessionmanager", "target": "src_auth_sessionmanager_validate", "relation": "method"},
            {"source": "src_auth_sessionmanager", "target": "src_auth_sessionmanager_logout", "relation": "method"},
        ],
    }
    doc_text = "The SessionManager coordinates user lifecycle."
    result = scope_ast_inventory(ast_data, ["docs/arch.md"], [doc_text])
    assert "src_auth_sessionmanager | SessionManager | src/auth.py" in result
    assert "src_auth_sessionmanager_validate | SessionManager.validate() | src/auth.py" in result
    assert "src_auth_sessionmanager_logout | SessionManager.logout() | src/auth.py" in result
    assert "OtherClass" not in result
def test_same_file_duplicate_methods_qualified_names():
    """Methods with identical base labels in the same file get disambiguated qualified names."""
    ast_data = {
        "nodes": [
            {"id": "src_service_py", "label": "service.ts", "source_file": "src/service.ts"},
            {"id": "src_service_authservice", "label": "AuthService", "source_file": "src/service.ts"},
            {"id": "src_service_authservice_run", "label": ".run()", "source_file": "src/service.ts"},
            {"id": "src_service_billingservice", "label": "BillingService", "source_file": "src/service.ts"},
            {"id": "src_service_billingservice_run", "label": ".run()", "source_file": "src/service.ts"},
        ],
        "edges": [
            {"source": "src_service_authservice", "target": "src_service_authservice_run", "relation": "method"},
            {"source": "src_service_billingservice", "target": "src_service_billingservice_run", "relation": "method"},
        ],
    }
    doc_text = "Both AuthService and BillingService are service workers."
    result = scope_ast_inventory(ast_data, ["docs/services.md"], [doc_text])
    assert "src_service_authservice_run | AuthService.run() | src/service.ts" in result
    assert "src_service_billingservice_run | BillingService.run() | src/service.ts" in result
def test_file_nodes_included():
    """File node is included when a file or its symbols are referenced."""
    ast_data = {
        "nodes": [
            {"id": "graphify_extract_py", "label": "extract.py", "source_file": "graphify/extract.py"},
            {"id": "graphify_extract_extract", "label": "extract()", "source_file": "graphify/extract.py"},
        ],
        "edges": [
            {"source": "graphify_extract_py", "target": "graphify_extract_extract", "relation": "contains"},
        ],
    }
    doc_text = "The pipeline is implemented in graphify/extract.py."
    result = scope_ast_inventory(ast_data, ["docs/overview.md"], [doc_text])
    assert "graphify_extract_py | extract.py | graphify/extract.py" in result
    assert "graphify_extract_extract | extract() | graphify/extract.py" in result
def test_no_matches_empty_behavior():
    """Pure conceptual doc with no code references returns 'None available'."""
    ast_data = {
        "nodes": [
            {"id": "src_code_a", "label": "SomeFunction()", "source_file": "src/code.py"},
        ],
        "edges": [],
    }
    doc_text = "This whitepaper describes the philosophical foundations of graph structures."
    result = scope_ast_inventory(ast_data, ["docs/whitepaper.md"], [doc_text])
    assert result == "None available"
def test_deterministic_ordering():
    """Scoping produces byte-stable deterministic output across multiple invocations."""
    ast_data = {
        "nodes": [
            {"id": "z_node", "label": "ZetaClass", "source_file": "src/z.py"},
            {"id": "a_node", "label": "AlphaClass", "source_file": "src/a.py"},
            {"id": "m_node", "label": "BetaClass", "source_file": "src/m.py"},
        ],
        "edges": [],
    }
    doc_text = "Mentioning ZetaClass, AlphaClass, and BetaClass together."
    res1 = scope_ast_inventory(ast_data, ["docs/doc.md"], [doc_text])
    res2 = scope_ast_inventory(ast_data, ["docs/doc.md"], [doc_text])
    assert res1 == res2
    # Verify order is by source_file: src/a.py -> src/m.py -> src/z.py
    lines = res1.splitlines()
    assert "src/a.py" in lines[0]
    assert "src/m.py" in lines[1]
    assert "src/z.py" in lines[2]
def test_hard_cap_100():
    """When more than 100 symbols match, candidate set is deterministically capped at 100."""
    nodes = []
    for i in range(150):
        nodes.append({
            "id": f"src_mod_{i:03d}_symbol",
            "label": f"CustomSymbol{i:03d}",
            "source_file": f"src/mod_{i:03d}.py",
        })
    ast_data = {"nodes": nodes, "edges": []}
    doc_text = " ".join([f"CustomSymbol{i:03d}" for i in range(150)])
    result = scope_ast_inventory(ast_data, ["docs/all.md"], [doc_text], max_symbols=100)
    lines = result.splitlines()
    assert len(lines) == 100
    assert "CustomSymbol000" in lines[0]
    assert "CustomSymbol099" in lines[99]
def test_canonical_edge_survives_build_from_json():
    """Integration: An edge targeting a canonical AST node ID survives build_from_json without ghosting."""
    ast_nodes = [
        {"id": "src_auth_session_validatetoken", "label": "ValidateToken()", "file_type": "code", "source_file": "src/auth/session.py"},
    ]
    sem_nodes = [
        {"id": "docs_architecture_authoverview", "label": "AuthOverview", "file_type": "document", "source_file": "docs/architecture.md"},
    ]
    sem_edges = [
        {
            "source": "docs_architecture_authoverview",
            "target": "src_auth_session_validatetoken",
            "relation": "references",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": "docs/architecture.md",
        }
    ]
    combined_data = {
        "nodes": ast_nodes + sem_nodes,
        "edges": sem_edges,
    }
    g = build_from_json(combined_data)
    assert "src_auth_session_validatetoken" in g
    assert "docs_architecture_authoverview" in g
    assert g.has_edge("docs_architecture_authoverview", "src_auth_session_validatetoken")
    edge_data = g.get_edge_data("docs_architecture_authoverview", "src_auth_session_validatetoken")
    assert edge_data["relation"] == "references"
def test_windows_path_normalization():
    """Windows backslash paths in AST nodes are normalized to POSIX in the scoped output."""
    ast_data = {
        "nodes": [
            {"id": "src_auth_session_py", "label": "session.py", "source_file": "src\\auth\\session.py"},
            {"id": "src_auth_session_token", "label": "Token", "source_file": "src\\auth\\session.py"},
        ],
        "edges": [],
    }
    doc_text = "See src/auth/session.py for details."
    result = scope_ast_inventory(ast_data, ["docs/spec.md"], [doc_text])
    assert "src/auth/session.py" in result
    assert "\\" not in result
def test_extraction_system_prompt_formatting():
    """_extraction_system injects CODE_SYMBOLS block when provided, omits when None/empty."""
    from graphify.llm import _extraction_system
    prompt_none = _extraction_system(code_symbols=None)
    assert "Code Symbol Inventory" not in prompt_none
    prompt_empty = _extraction_system(code_symbols="None available")
    assert "Code Symbol Inventory" not in prompt_empty
    symbols = "src_auth_session_validatetoken | ValidateToken() | src/auth/session.py"
    prompt_with_symbols = _extraction_system(code_symbols=symbols)
    assert "Code Symbol Inventory (canonical code symbols available for this chunk):" in prompt_with_symbols
    assert symbols in prompt_with_symbols
    assert "Do NOT create a duplicate file_type=\"code\" node" in prompt_with_symbols
def test_deep_nested_qualified_names():
    """Multi-level class nesting (Outer -> Inner -> method()) produces Outer.Inner.method()."""
    ast_data = {
        "nodes": [
            {"id": "src_tree_py", "label": "tree.py", "source_file": "src/tree.py"},
            {"id": "src_tree_outer", "label": "Outer", "source_file": "src/tree.py"},
            {"id": "src_tree_inner", "label": "Inner", "source_file": "src/tree.py"},
            {"id": "src_tree_method", "label": ".run()", "source_file": "src/tree.py"},
        ],
        "edges": [
            {"source": "src_tree_py", "target": "src_tree_outer", "relation": "contains"},
            {"source": "src_tree_outer", "target": "src_tree_inner", "relation": "contains"},
            {"source": "src_tree_inner", "target": "src_tree_method", "relation": "method"},
        ],
    }
    doc_text = "The Outer container wraps Inner."
    result = scope_ast_inventory(ast_data, ["docs/tree.md"], [doc_text])
    assert "src_tree_method | Outer.Inner.run() | src/tree.py" in result
    assert "src_tree_inner | Outer.Inner | src/tree.py" in result
    assert "src_tree_outer | Outer | src/tree.py" in result
def test_nested_function_containment():
    """Multi-level function nesting (OuterFunction -> InnerFunction -> DeepFunction) reflects the containment chain."""
    ast_data = {
        "nodes": [
            {"id": "src_funcs_py", "label": "funcs.py", "source_file": "src/funcs.py"},
            {"id": "src_funcs_outer", "label": "OuterFunction()", "source_file": "src/funcs.py"},
            {"id": "src_funcs_inner", "label": "InnerFunction()", "source_file": "src/funcs.py"},
            {"id": "src_funcs_deep", "label": "DeepFunction()", "source_file": "src/funcs.py"},
        ],
        "edges": [
            {"source": "src_funcs_py", "target": "src_funcs_outer", "relation": "contains"},
            {"source": "src_funcs_outer", "target": "src_funcs_inner", "relation": "contains"},
            {"source": "src_funcs_inner", "target": "src_funcs_deep", "relation": "contains"},
        ],
    }
    doc_text = "See OuterFunction for the nested execution pipeline."
    result = scope_ast_inventory(ast_data, ["docs/pipeline.md"], [doc_text])
    assert "src_funcs_deep | OuterFunction.InnerFunction.DeepFunction() | src/funcs.py" in result
    assert "src_funcs_inner | OuterFunction.InnerFunction() | src/funcs.py" in result
    assert "src_funcs_outer | OuterFunction() | src/funcs.py" in result
def test_backend_prompt_injection(tmp_path, monkeypatch):
    """extract_files_direct with ast_data automatically scopes symbols and injects them into system prompt."""
    from graphify.llm import extract_files_direct
    doc_file = tmp_path / "spec.md"
    doc_file.write_text("Refer to SessionHandler for authentication.", encoding="utf-8")
    ast_data = {
        "nodes": [
            {"id": "src_auth_py", "label": "auth.py", "source_file": "src/auth.py"},
            {"id": "src_auth_sessionhandler", "label": "SessionHandler", "source_file": "src/auth.py"},
            {"id": "src_auth_sessionhandler_login", "label": ".login()", "source_file": "src/auth.py"},
        ],
        "edges": [
            {"source": "src_auth_sessionhandler", "target": "src_auth_sessionhandler_login", "relation": "method"},
        ],
    }
    captured_kwargs = {}
    def mock_call_openai_compat(base_url, api_key, model, user_message, **kwargs):
        captured_kwargs.update(kwargs)
        return {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 10, "output_tokens": 10, "model": model}
    monkeypatch.setattr("graphify.llm._call_openai_compat", mock_call_openai_compat)
    result = extract_files_direct(
        [doc_file],
        backend="openai",
        api_key="sk-test-fake",
        ast_data=ast_data,
        root=tmp_path,
    )
    code_symbols = captured_kwargs.get("code_symbols")
    assert code_symbols is not None
    assert "src_auth_sessionhandler | SessionHandler | src/auth.py" in code_symbols
    assert "src_auth_sessionhandler_login | SessionHandler.login() | src/auth.py" in code_symbols
    assert "src_auth_py | auth.py | src/auth.py" in code_symbols
def test_malformed_ast_robustness():
    """scope_ast_inventory handles dangling edges, missing nodes, and cyclic containment without looping or crashing."""
    ast_data = {
        "nodes": [
            {"id": "node_a", "label": "AlphaClass", "source_file": "src/alpha.py"},
            {"id": "node_b", "label": "BetaClass", "source_file": "src/alpha.py"},
        ],
        "edges": [
            # Cyclic containment
            {"source": "node_a", "target": "node_b", "relation": "contains"},
            {"source": "node_b", "target": "node_a", "relation": "contains"},
            # Dangling edges pointing to missing IDs
            {"source": "node_a", "target": "nonexistent_child", "relation": "contains"},
            {"source": "nonexistent_parent", "target": "node_a", "relation": "contains"},
            # Malformed edge dict
            {"relation": "contains"},
            None,
        ],
    }
    doc_text = "AlphaClass is used here."
    result = scope_ast_inventory(ast_data, ["docs/guide.md"], [doc_text])
    assert "node_a" in result
    assert "node_b" in result
    assert "None available" not in result
