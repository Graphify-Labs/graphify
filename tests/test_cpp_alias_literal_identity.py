"""INC-QML-112: literal C++ aliases survive normalized-name collisions."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.paths import load_node_link_graph
from tests.cpp_alias_helpers import declarations, produce, references, source


@pytest.mark.parametrize("mode", ["direct", "facade"])
@pytest.mark.parametrize("form", ["using", "typedef"])
@pytest.mark.parametrize("scope,names", [("", ("Alias", "alias")), ("", ("Alias", "_Alias")),
                                         ("nested", ("Alias", "alias")), ("separate", ("Alias", "Alias"))])
@pytest.mark.parametrize("profile", ["lf", "bom_crlf"])
def test_req_qml022_ac06_literal_aliases_keep_actual_source_reference_targets(tmp_path, mode, form, scope, names, profile):
    """Each admitted declaration and reference retain exact identity, spelling and original line."""
    raw = source(form, scope, names)
    if profile == "bom_crlf":
        raw = b"\xef\xbb\xbf// \xcf\x80\r\n" + raw.replace(b"\n", b"\r\n")
    result = produce(tmp_path, raw, mode=mode)
    aliases = declarations(result, names)
    assert len(aliases) == 2 and len({node["id"] for node in aliases}) == 2
    aliases.sort(key=lambda node: int(node["source_location"][1:]))
    for node, expected in zip(aliases, names):
        assert node["label"] == expected
        original_line = raw.splitlines()[int(node["source_location"][1:]) - 1]
        assert expected.encode() in original_line
        assert (b"using " if form == "using" else b"typedef ") in original_line
    refs = references(result)
    assert refs["UsesUpper"]["id"] == aliases[0]["id"]
    assert refs["UsesLower"]["id"] == aliases[1]["id"]
    output = tmp_path / "aliases.json"
    assert to_json(build_from_json(result, root=tmp_path), {}, str(output), force=True)
    restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    for node in aliases:
        assert restored.nodes[node["id"]]["label"] == node["label"]
        assert restored.nodes[node["id"]]["source_location"] == node["source_location"]
    for owner, alias in zip(("UsesUpper", "UsesLower"), aliases):
        declaration, = [node for node in result["nodes"] if node["label"] == owner]
        assert restored.has_edge(declaration["id"], alias["id"])
        assert restored.get_edge_data(declaration["id"], alias["id"])["relation"] == "references"
        wrong, = [other for other in aliases if other["id"] != alias["id"]]
        assert not restored.has_edge(declaration["id"], wrong["id"])


@pytest.mark.parametrize("mode", ["direct", "facade"])
def test_req_qml022_ac06_alias_chain_does_not_erase_its_case_distinct_source_declaration(tmp_path, mode):
    """Chain declarations remain source facts; this does not infer alias execution or native targets."""
    raw = source().replace(b"struct UsesUpper {Alias value;};", b"using Upper=Alias;\nstruct UsesUpper {Upper value;};")
    raw = raw.replace(b"struct UsesLower {alias value;};", b"using Lower=alias;\nstruct UsesLower {Lower value;};")
    result = produce(tmp_path, raw, mode=mode)
    assert len(declarations(result, ("Alias", "alias", "Upper", "Lower"))) == 4
    refs = references(result)
    assert refs["UsesUpper"]["label"] == "Upper" and refs["UsesLower"]["label"] == "Lower"
