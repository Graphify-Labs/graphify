"""Saved production graph fixtures shared across CLI/HTML/MCP acceptance."""
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qml_facts import qml_metadata
from tests.qt_analysis_helpers import analysis


def saved_graph(root):
    result = analysis(root, {"Main.qml": '''import QtQml
QtObject { id: root; property int input: 1; property int output: input;
 signal changed(); onChanged: { output = input }
 function run() { changed() }
}''', "Other.qml": 'import QtQml\nQtObject { property int input: 2 }'})
    graph = build_from_json(result, root=root, directed=True)
    output = root / "graph.json"
    assert to_json(graph, {}, str(output), force=True)
    component = next(node for node in result["nodes"] if node["source_file"] == "Main.qml" and qml_metadata(node).get("kind") == "component")
    prop = next(node for node in result["nodes"] if node["source_file"] == "Main.qml" and qml_metadata(node).get("kind") == "property" and qml_metadata(node).get("raw_name") == "input")
    read = next(node for node in result["nodes"] if node["source_file"] == "Main.qml" and qml_metadata(node).get("kind") == "read" and qml_metadata(node).get("reference") == "input")
    return output, result, component, prop, read


def cli(monkeypatch, capsys, graph, *arguments):
    import graphify.__main__ as main
    # Query stamps belong to the isolated persisted fixture, not the checkout.
    monkeypatch.chdir(graph.parent)
    monkeypatch.setattr(main, "_check_skill_version", lambda *_: None)
    monkeypatch.setattr(main.sys, "argv", ["graphify", *arguments, "--graph", str(graph)])
    capsys.readouterr()
    main.main()
    return capsys.readouterr().out.strip()
