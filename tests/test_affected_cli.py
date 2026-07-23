from graphify import __main__ as mainmod
from graphify.affected import affected_nodes, resolve_seed
from tests.native_helpers import make_loaded


def _loaded(tmp_path):
    return make_loaded(
        tmp_path,
        kind="digraph",
        nodes=[
            {"id": "foo", "label": "Foo()", "source_file": "foo.py", "file_type": "code"},
            {"id": "bar", "label": "Bar", "source_file": "bar.py", "file_type": "code"},
            {"id": "baz", "label": "Baz", "source_file": "baz.py", "file_type": "code"},
        ],
        edges=[
            {"source": "bar", "target": "foo", "relation": "calls"},
            {"source": "baz", "target": "bar", "relation": "imports"},
        ],
    )


def test_native_reverse_traversal_and_relation_filter(tmp_path):
    loaded = _loaded(tmp_path)
    graph = loaded.graph
    assert resolve_seed(graph, "Foo", node_query=loaded.query) == "foo"
    all_hits = affected_nodes(graph, "foo", relations={"calls", "imports"}, depth=2)
    assert {row.node_id for row in all_hits} == {"bar", "baz"}
    calls = affected_nodes(graph, "foo", relations={"calls"}, depth=2)
    assert {row.node_id for row in calls} == {"bar"}


def test_cli_reads_helix_store(tmp_path, monkeypatch, capsys):
    loaded = _loaded(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "affected", "Foo", "--store", str(loaded.store_path)],
    )
    mainmod.main()
    output = capsys.readouterr().out
    assert "Bar" in output and "Baz" in output


def test_cli_rejects_legacy_json_path(tmp_path, monkeypatch, capsys):
    legacy = tmp_path / "legacy.json"
    legacy.write_text("{}")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "affected", "Foo", "--store", str(legacy)],
    )
    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code == 1
    assert "obsolete" in capsys.readouterr().err


def _callsite_graph(tmp_path, *, with_location: bool):
    edge = {
        "source": "loader",
        "target": "transition",
        "relation": "calls",
        "confidence": "EXTRACTED",
    }
    if with_location:
        edge.update(
            source_file="apollo_pipeline_status.py",
            source_location="L158",
        )
    return make_loaded(
        tmp_path,
        kind="digraph",
        nodes=[
            {
                "id": "loader",
                "label": "_load_apollo_app_state()",
                "source_file": "apollo_pipeline_status.py",
                "source_location": "L90",
            },
            {
                "id": "transition",
                "label": "transition_state()",
                "source_file": "state.py",
                "source_location": "L56",
            },
        ],
        edges=[edge],
    )


def test_affected_reports_call_site_line_not_def_line(
    monkeypatch, tmp_path, capsys
):
    loaded = _callsite_graph(tmp_path, with_location=True)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        [
            "graphify",
            "affected",
            "transition_state",
            "--store",
            str(loaded.store_path),
        ],
    )

    mainmod.main()

    output = capsys.readouterr().out
    assert "apollo_pipeline_status.py:L158" in output
    assert "apollo_pipeline_status.py:L90" not in output


def test_affected_falls_back_to_def_line_when_edge_has_no_location(
    monkeypatch, tmp_path, capsys
):
    loaded = _callsite_graph(tmp_path, with_location=False)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        [
            "graphify",
            "affected",
            "transition_state",
            "--store",
            str(loaded.store_path),
        ],
    )

    mainmod.main()

    assert "apollo_pipeline_status.py:L90" in capsys.readouterr().out
