"""QML-005 component IDs, shadowing, singletons and source-only member lookup."""

import copy

from graphify.extractors.qml_facts import encode_metadata, qml_metadata
from graphify.qml_resolution import build_qml_index
from tests.qml_resolution_helpers import component_key, index_for, named


def _member(index, nodes, file, receiver, expression, *, lexical_names=()):
    owner = named(nodes, file, "object", receiver)
    md = qml_metadata(owner)
    return index.resolve_member(file, md["component_key"], md["object_scope_key"], expression,
                                lexical_names=lexical_names)


def test_component_ids_do_not_leak_between_files_or_inline_components(tmp_path):
    """AC01: equal ID spellings are component-local, including nested definitions."""
    sources = {"Main.qml": """QtObject {
        id: root
        property int value: 1
        component Local: QtObject { id: root; property int value: 2 }
        Local { id: child }
    }""", "Other.qml": "QtObject { id: root; property int value: 3; QtObject { id: foreign } }"}
    index, _, nodes, _ = index_for(tmp_path, sources)
    outer = [node for node in nodes if
        node["source_file"] == "Main.qml" and qml_metadata(node).get("kind") == "property" and
        qml_metadata(node).get("component_key") == component_key(nodes)][0]
    assert _member(index, nodes, "Main.qml", "child", "root.value").target_id == outer["id"]
    inner_root = [node for node in nodes if node["source_file"] == "Main.qml" and
                  qml_metadata(node).get("kind") == "object" and
                  qml_metadata(node).get("component_key") != component_key(nodes)][0]
    md = qml_metadata(inner_root)
    inner = index.resolve_member("Main.qml", md["component_key"], md["object_scope_key"], "root.value")
    assert inner.target_id != outer["id"]
    assert qml_metadata(index.nodes[inner.target_id])["component_key"] == md["component_key"]
    assert _member(index, nodes, "Main.qml", "child", "foreign").status == "unavailable"


def test_inline_shadow_and_inherited_members_are_distinct_roles(tmp_path):
    """AC02/04: local inline names shadow imported types; instances inherit members."""
    sources = {"Public/Tools/qmldir": "module Public.Tools\nBase 1.0 Base.qml",
               "Public/Tools/Base.qml": "QtObject { property int inheritedValue: 1 }",
               "Main.qml": """import Public.Tools 1.0
               QtObject { id: root; property int Base: 7
                   component Base: QtObject { property int inlineValue: 2 }
                   Base { id: local }
               }""",
               "Inherited.qml": "import Public.Tools 1.0\nBase { id: derived }"}
    index, _, nodes, _ = index_for(tmp_path, sources)
    inline = named(nodes, "Main.qml", "inline_component", "Base")
    assert index.resolve_type("Main.qml", component_key(nodes), "Base").target_id == inline["id"]
    assert _member(index, nodes, "Main.qml", "local", "local.inlineValue").target_id == named(nodes, "Main.qml", "property", "inlineValue")["id"]
    inherited = _member(index, nodes, "Inherited.qml", "derived", "inheritedValue")
    assert inherited.target_id == named(nodes, "Public/Tools/Base.qml", "property", "inheritedValue")["id"]
    same_label = _member(index, nodes, "Main.qml", "root", "Base")
    assert same_label.target_id == named(nodes, "Main.qml", "property", "Base")["id"]
    assert len({inline["id"], same_label.target_id, named(nodes, "Main.qml", "object", "local")["id"]}) == 3


def test_singleton_pragma_and_qualified_access(tmp_path):
    """AC02: singleton metadata must agree with source pragma before member use."""
    sources = {"Public/Tools/qmldir": "module Public.Tools\nsingleton State 1.0 State.qml\nBroken 1.0 Broken.qml",
               "Public/Tools/State.qml": "pragma Singleton\nQtObject { property int value: 1 }",
               "Public/Tools/Broken.qml": "QtObject { property int value: 2 }",
               "Main.qml": "import Public.Tools 1.0 as Tools\nQtObject { id: root }"}
    index, _, nodes, _ = index_for(tmp_path, sources)
    result = _member(index, nodes, "Main.qml", "root", "Tools.State.value")
    assert result.target_id == named(nodes, "Public/Tools/State.qml", "property", "value")["id"]
    assert _member(index, nodes, "Main.qml", "root", "Tools.Broken.value").status != "resolved"
    bad_nodes = copy.deepcopy(nodes)
    # A provider's singleton export without a matching source pragma is rejected.
    state = named(nodes, "Public/Tools/State.qml", "component")
    for node in bad_nodes:
        if node["id"] == state["id"]:
            node["metadata"]["qml"] = encode_metadata({**qml_metadata(node), "singleton": False})
    bad_index = build_qml_index(bad_nodes, [], root=tmp_path)
    assert bad_index.module_type("Public.Tools", 1, 0, "State", importer="Main.qml").reason == "singleton_pragma_missing"


def test_internal_external_dynamic_and_lexical_members_stay_unresolved(tmp_path):
    """AC03/04: visibility and unknown runtime context cannot become label matches."""
    sources = {"Public/Tools/qmldir": "module Public.Tools\nPublic 1.0 Public.qml\ninternal Hidden Hidden.qml",
               "Public/Tools/Public.qml": "QtObject { property int value: 1 }",
               "Public/Tools/Hidden.qml": "QtObject {}",
               "Main.qml": "import Public.Tools 1.0\nQtObject { id: root; property int value: 2 }",
               "Unrelated.qml": "QtObject { property int runtimeValue: 3 }"}
    index, _, nodes, edges = index_for(tmp_path, sources)
    assert index.resolve_type("Main.qml", component_key(nodes), "Hidden").reason == "internal_export"
    assert _member(index, nodes, "Main.qml", "root", "runtimeValue").status == "unavailable"
    assert _member(index, nodes, "Main.qml", "root", "dynamicLookup.value").status == "unavailable"
    lexical = _member(index, nodes, "Main.qml", "root", "root.value", lexical_names=("root",))
    assert lexical.status == "dynamic" and lexical.reason == "javascript_lexical_binding"
    private_nodes = copy.deepcopy(nodes)
    value = named(nodes, "Main.qml", "property", "value")
    for node in private_nodes:
        if node["id"] == value["id"]:
            node["metadata"]["qml"] = encode_metadata({**qml_metadata(node), "internal": True})
    private = build_qml_index(private_nodes, edges, root=tmp_path)
    assert _member(private, private_nodes, "Main.qml", "root", "value").reason == "member_not_visible"


def test_inheritance_cycles_are_bounded_and_do_not_select_unrelated_members(tmp_path):
    """Recursive source types give a coverage reason rather than recursion or guessing."""
    index, _, nodes, _ = index_for(tmp_path, {"A.qml": "B { id: a }", "B.qml": "A {}",
                                             "Other.qml": "QtObject { property int missing: 1 }"})
    result = _member(index, nodes, "A.qml", "a", "missing")
    assert result.status == "unsupported"
    assert result.reason == "inheritance_cycle_or_limit"


def test_typed_properties_this_and_explicit_static_parent(tmp_path):
    """Continuation reuses scoped member APIs; lexical ownership alone is no parent proof."""
    index, _, nodes, edges = index_for(tmp_path, {"Value.qml": "QtObject { property int count: 1 }",
        "Main.qml": "QtObject { id: root; property int rootValue: 2; property Value value; QtObject { id: child } }"})
    expected = named(nodes, "Value.qml", "property", "count")["id"]
    assert _member(index, nodes, "Main.qml", "child", "value.count").target_id == expected
    value = named(nodes, "Main.qml", "property", "value")
    assert index.follow_member(value["id"], ["count"]).target_id == expected
    assert _member(index, nodes, "Main.qml", "root", "this.rootValue").status == "resolved"
    assert _member(index, nodes, "Main.qml", "child", "parent.rootValue").reason == "runtime_parent_unestablished"
    static_nodes = copy.deepcopy(nodes)
    child = named(nodes, "Main.qml", "object", "child")
    for node in static_nodes:
        if node["id"] == child["id"]:
            node["metadata"]["qml"] = encode_metadata({**qml_metadata(node),
                "static_parent_scope_key": qml_metadata(node)["parent_scope_key"]})
    static = build_qml_index(static_nodes, edges, root=tmp_path)
    assert _member(static, static_nodes, "Main.qml", "child", "parent.rootValue").target_id == named(nodes, "Main.qml", "property", "rootValue")["id"]
