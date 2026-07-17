from graphify.helix.model import node_attributes
from graphify.helix.persistence import HelixEmbeddedStore, load_graph
from graphify.watch import _rebuild_code, _rebuild_lock


def _sources(store):
    graph = load_graph(store).graph
    return {
        node_attributes(graph, node.id).get("source_file")
        for node in graph.nodes()
    }


def test_full_and_incremental_delete_activate_native_generations(tmp_path):
    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    first.write_text("from b import value\ndef main():\n    return value\n")
    second.write_text("value = 1\n")
    assert _rebuild_code(tmp_path, block_on_lock=True)
    store = tmp_path / "graphify-out" / "graph.helix"
    before = load_graph(store)
    assert {"a.py", "b.py"} <= _sources(store)
    second.unlink()
    assert _rebuild_code(tmp_path, changed_paths=[second], block_on_lock=True)
    after = load_graph(store)
    assert after.generation != before.generation
    assert "b.py" not in _sources(store)


def test_legacy_json_is_warned_and_ignored(tmp_path, capsys):
    (tmp_path / "app.py").write_text("def app():\n    pass\n")
    out = tmp_path / "graphify-out"
    out.mkdir()
    legacy = out / "graph.json"
    legacy.write_text('{"sentinel": true}')
    assert _rebuild_code(tmp_path, block_on_lock=True)
    assert legacy.read_text() == '{"sentinel": true}'
    assert "obsolete and ignored" in capsys.readouterr().err


def test_rebuild_recovers_store_without_active_generation(tmp_path):
    (tmp_path / "app.py").write_text("def app():\n    pass\n")
    store_path = tmp_path / "graphify-out" / "graph.helix"
    with HelixEmbeddedStore(store_path):
        pass
    assert _rebuild_code(tmp_path, block_on_lock=True)
    assert load_graph(store_path).graph.node_count > 0


def test_rebuild_lock_excludes_second_writer(tmp_path):
    out = tmp_path / "graphify-out"
    with _rebuild_lock(out, blocking=False) as first:
        assert first
        with _rebuild_lock(out, blocking=False) as second:
            assert not second


def test_failed_semantic_pass_keeps_active_generation(tmp_path, monkeypatch):
    (tmp_path / "app.py").write_text("def app():\n    pass\n")
    (tmp_path / "design.md").write_text("# Design")
    assert _rebuild_code(tmp_path, block_on_lock=True)
    store = tmp_path / "graphify-out" / "graph.helix"
    generation = load_graph(store).generation
    monkeypatch.setattr(
        "graphify.llm.extract_corpus_parallel",
        lambda *args, **kwargs: {
            "nodes": [], "edges": [], "hyperedges": [],
            "input_tokens": 0, "output_tokens": 0, "failed_chunks": 1,
        },
    )
    assert not _rebuild_code(
        tmp_path, include_semantic=True, backend="openai", block_on_lock=True
    )
    assert load_graph(store).generation == generation


def test_native_semantic_cache_skips_second_backend_call(tmp_path, monkeypatch):
    doc = tmp_path / "design.md"
    doc.write_text("# Design\nNative only.\n")
    calls = []

    def semantic(paths, **kwargs):
        calls.append(list(paths))
        return {
            "nodes": [{
                "id": "design", "label": "Design", "file_type": "document",
                "source_file": "design.md",
            }],
            "edges": [], "hyperedges": [], "input_tokens": 10,
            "output_tokens": 5, "failed_chunks": 0,
        }

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", semantic)
    assert _rebuild_code(
        tmp_path, include_semantic=True, backend="openai", block_on_lock=True
    )
    assert _rebuild_code(
        tmp_path, include_semantic=True, backend="openai", block_on_lock=True
    )

    loaded = load_graph(tmp_path / "graphify-out" / "graph.helix")
    cache = loaded.state["incremental"]["extraction_cache"]
    assert len(calls) == 1
    assert any(key.startswith("semantic:") for key in cache)
    assert not (tmp_path / "graphify-out" / "cache").exists()


def test_output_root_keeps_source_tree_clean(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    (source / "app.py").write_text("def app():\n    pass\n")

    assert _rebuild_code(source, output_root=destination, block_on_lock=True)

    assert (destination / "graphify-out" / "graph.helix").is_dir()
    assert not (source / "graphify-out").exists()
