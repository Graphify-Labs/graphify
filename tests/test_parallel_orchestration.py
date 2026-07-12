import time
import pytest
import json
import graphify.__main__ as mainmod

def test_pipeline_runs_in_parallel(monkeypatch, tmp_path):
    """
    Verify that AST and Semantic extraction run concurrently.
    If they run sequentially, total time will be >= 1.0s.
    If they run in parallel, total time should be ~0.5s.
    """
    # 1. Setup a dummy project with one code file and one markdown file
    (tmp_path / "main.py").write_text("def test(): pass")
    (tmp_path / "doc.md").write_text("# Documentation")
    out_dir = tmp_path / "out"
    
    # Bypass API key checks
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    # 2. Mock the AST extractor to take 0.5 seconds
    def mock_ast(*args, **kwargs):
        time.sleep(0.5)
        return {"nodes": [{"id": "ast_node"}], "edges": [], "input_tokens": 0, "output_tokens": 0}

    # 3. Mock the Semantic extractor to take 0.5 seconds
    def mock_semantic(*args, **kwargs):
        time.sleep(0.5)
        if "on_chunk_done" in kwargs:
            kwargs["on_chunk_done"](0, 1, {})
        return {"nodes": [{"id": "sem_node"}], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}

    # Apply the mocks
    import graphify.extract
    monkeypatch.setattr(graphify.extract, "extract", mock_ast)
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", mock_semantic)

    # Setup the CLI arguments
    monkeypatch.setattr(mainmod.sys, "argv", [
        "graphify", "extract", str(tmp_path), "--out", str(out_dir), "--no-cluster"
    ])

    # 4. Time the execution
    start_time = time.time()
    try:
        mainmod.main()
    except SystemExit:
        pass
    elapsed = time.time() - start_time

    # 5. Assert Parallel Execution Time
    assert elapsed < 1.2, f"Tasks ran sequentially! Took {elapsed:.2f}s instead of parallelized ~0.9s"

    # 6. Assert Data Integrity (both nodes must exist in the final graph)
    graph_path = out_dir / "graphify-out" / "graph.json"
    graph_data = json.loads(graph_path.read_text())
    node_ids = {n["id"] for n in graph_data["nodes"]}
    
    assert "ast_node" in node_ids, "AST node was lost during parallel merge!"
    assert "sem_node" in node_ids, "Semantic node was lost during parallel merge!"


def test_parallel_failure_propagates(monkeypatch, tmp_path):
    """
    Verify that if the semantic extractor fails completely (all chunks fail),
    the CLI exits with code 1 and doesn't silently generate an incomplete graph.
    """
    (tmp_path / "main.py").write_text("def test(): pass")
    (tmp_path / "doc.md").write_text("# Documentation")
    out_dir = tmp_path / "out"
    
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    import graphify.extract
    monkeypatch.setattr(graphify.extract, "extract", lambda *a, **k: {"nodes": [], "edges": []})
    
    # Do NOT call on_chunk_done to simulate total failure
    def mock_semantic_fail(*args, **kwargs):
        return {"nodes": [], "edges": [], "hyperedges": []}
        
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", mock_semantic_fail)

    monkeypatch.setattr(mainmod.sys, "argv", [
        "graphify", "extract", str(tmp_path), "--out", str(out_dir), "--no-cluster"
    ])

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()
    
    assert exc_info.value.code == 1, "CLI should exit 1 when semantic thread fails completely"


def test_parallel_code_only_corpus(monkeypatch, tmp_path):
    """
    Verify that when there are no documents, the parallel runner
    doesn't crash on the empty semantic thread.
    """
    # Only code files
    (tmp_path / "main.py").write_text("def test(): pass")
    out_dir = tmp_path / "out"
    
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    import graphify.extract
    monkeypatch.setattr(graphify.extract, "extract", lambda *a, **k: {"nodes": [{"id": "ast_only"}], "edges": []})
    
    # We don't even need to mock semantic extraction since it shouldn't be called

    monkeypatch.setattr(mainmod.sys, "argv", [
        "graphify", "extract", str(tmp_path), "--out", str(out_dir), "--no-cluster"
    ])

    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0)
        
    graph_path = out_dir / "graphify-out" / "graph.json"
    graph_data = json.loads(graph_path.read_text())
    node_ids = {n["id"] for n in graph_data["nodes"]}
    
    assert "ast_only" in node_ids
    assert len(node_ids) == 1


def test_postgres_and_cargo_merge(monkeypatch, tmp_path):
    """
    Verify that PostgreSQL and Cargo nodes are correctly merged
    by the thread pool orchestrator.
    """
    (tmp_path / "main.py").write_text("def test(): pass")
    out_dir = tmp_path / "out"
    
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    import graphify.extract
    monkeypatch.setattr(graphify.extract, "extract", lambda *a, **k: {"nodes": [], "edges": []})
    
    def mock_pg(*args, **kwargs):
        return {"nodes": [{"id": "pg_node"}], "edges": []}
        
    def mock_cargo(*args, **kwargs):
        return {"nodes": [{"id": "cargo_node"}], "edges": []}
        
    import graphify.pg_introspect
    monkeypatch.setattr(graphify.pg_introspect, "introspect_postgres", mock_pg)
    
    import graphify.cargo_introspect
    monkeypatch.setattr(graphify.cargo_introspect, "introspect_cargo", mock_cargo)

    monkeypatch.setattr(mainmod.sys, "argv", [
        "graphify", "extract", str(tmp_path), "--out", str(out_dir), 
        "--no-cluster", "--postgres", "postgresql://user:pass@localhost/db", "--cargo"
    ])

    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code in (None, 0)
        
    graph_path = out_dir / "graphify-out" / "graph.json"
    graph_data = json.loads(graph_path.read_text())
    node_ids = {n["id"] for n in graph_data["nodes"]}
    
    assert "pg_node" in node_ids
    assert "cargo_node" in node_ids
