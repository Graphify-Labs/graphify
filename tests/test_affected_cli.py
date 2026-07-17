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
    graph = _loaded(tmp_path).graph
    assert resolve_seed(graph, "Foo") == "foo"
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
