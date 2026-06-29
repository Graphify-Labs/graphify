from __future__ import annotations

from pathlib import Path

from graphify.build import build_from_json
from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _node_by_id(result: dict, nid: str) -> dict | None:
    return next((n for n in result["nodes"] if n.get("id") == nid), None)


def test_java_cross_file_implements_resolves_to_real_def(tmp_path: Path):
    # #1318: a cross-file `implements` must land on the real interface def, not a
    # bare no-source shadow stub.
    iface = _write(
        tmp_path / "src/com/x/handler/AIResponseHandler.java",
        "package com.x.handler;\npublic interface AIResponseHandler {}\n",
    )
    impl = _write(
        tmp_path / "src/com/x/service/DifyAiServiceImpl.java",
        "package com.x.service;\n"
        "import com.x.handler.AIResponseHandler;\n"
        "public class DifyAiServiceImpl implements AIResponseHandler {}\n",
    )
    result = extract([iface, impl], cache_root=tmp_path)

    implements = [e for e in result["edges"] if e["relation"] == "implements"]
    assert implements, "expected an implements edge"
    for e in implements:
        tgt = _node_by_id(result, e["target"])
        assert tgt is not None, f"implements target {e['target']} is not a node"
        # The target must be the real definition (has a source_file), not a shadow stub.
        assert tgt.get("source_file"), f"implements landed on shadow stub {e['target']}"
        assert "handler" in tgt["source_file"]


def test_java_ambiguous_implements_disambiguated_by_import(tmp_path: Path):
    # #1318 core case: two interfaces with the SAME simple name in different
    # packages. The importing file's `import` must pick the right one, and no
    # orphan shadow node may remain.
    a = _write(
        tmp_path / "src/com/a/handler/AIResponseHandler.java",
        "package com.a.handler;\npublic interface AIResponseHandler {}\n",
    )
    b = _write(
        tmp_path / "src/com/b/handler/AIResponseHandler.java",
        "package com.b.handler;\npublic interface AIResponseHandler {}\n",
    )
    impl = _write(
        tmp_path / "src/com/x/service/Impl.java",
        "package com.x.service;\n"
        "import com.a.handler.AIResponseHandler;\n"
        "public class Impl implements AIResponseHandler {}\n",
    )
    result = extract([a, b, impl], cache_root=tmp_path)

    # No bare shadow stub for the interface should survive.
    shadow = [
        n for n in result["nodes"]
        if n.get("label") == "AIResponseHandler" and not n.get("source_file")
    ]
    assert not shadow, f"orphan shadow node(s) remain: {[n['id'] for n in shadow]}"

    implements = [e for e in result["edges"] if e["relation"] == "implements"]
    assert len(implements) == 1
    tgt = _node_by_id(result, implements[0]["target"])
    assert tgt is not None and tgt.get("source_file")
    # Must resolve to the imported package (com/a), not com/b.
    assert "com/a/handler" in tgt["source_file"]
    assert "com/b/handler" not in tgt["source_file"]


def test_java_implements_edge_survives_build(tmp_path: Path):
    # #1318: the re-pointed edge must connect real nodes after graph assembly,
    # so the interface is not classified as an isolated community.
    iface = _write(
        tmp_path / "src/com/x/handler/Handler.java",
        "package com.x.handler;\npublic interface Handler {}\n",
    )
    impl = _write(
        tmp_path / "src/com/x/service/Svc.java",
        "package com.x.service;\n"
        "import com.x.handler.Handler;\n"
        "public class Svc implements Handler {}\n",
    )
    result = extract([iface, impl], cache_root=tmp_path)
    G = build_from_json(result, directed=True)
    impl_edges = [
        (u, v) for u, v, d in G.edges(data=True) if d.get("relation") == "implements"
    ]
    assert impl_edges
    # The interface node has an incoming implements edge (not isolated).
    assert any(G.in_degree(v) >= 1 for _, v in impl_edges)


def _label_edges(result: dict, relations):
    by_id = {n["id"]: n.get("label", "") for n in result["nodes"]}
    return {
        (by_id.get(e["source"], ""), e["relation"], by_id.get(e["target"], ""))
        for e in result["edges"]
        if e.get("relation") in relations
    }


def test_java_record_becomes_type_node(tmp_path: Path):
    # #1373: a Java `record` must produce a first-class type node (with a
    # `contains` edge from its file), not be left as an isolated file node.
    rec = _write(
        tmp_path / "Foo.java",
        "package com.app;\npublic record Foo(int x, String y) {}\n",
    )
    result = extract([rec], cache_root=tmp_path)

    foo = [n for n in result["nodes"]
           if n.get("label") == "Foo" and n.get("source_file")]
    assert foo, "record Foo should be a type node, not just the file node"
    contains = _label_edges(result, {"contains"})
    assert ("Foo.java", "contains", "Foo") in contains


def test_java_record_implements_interface(tmp_path: Path):
    # Records reuse class interface handling: `record Foo implements I` emits it.
    iface = _write(tmp_path / "I.java", "package com.app;\npublic interface I {}\n")
    rec = _write(
        tmp_path / "Foo.java",
        "package com.app;\npublic record Foo(int x) implements I {}\n",
    )
    result = extract([iface, rec], cache_root=tmp_path)
    implements = [e for e in result["edges"] if e["relation"] == "implements"]
    assert implements, "record implementing an interface should emit an implements edge"


def test_java_type_parameters_do_not_resolve_to_real_class(tmp_path: Path):
    real_type = _write(tmp_path / "T.java", "public class T {}\n")
    generic = _write(
        tmp_path / "Generic.java",
        "public class Generic<T> { java.util.List<T> values; }\n",
    )

    result = extract([real_type, generic], cache_root=tmp_path)

    references = _label_edges(result, {"references"})
    assert ("Generic", "references", "T") not in references


def test_java_cross_file_constructor_call_resolves(tmp_path: Path):
    # #1373: `new Foo(...)` in a method body must produce a cross-file edge to the
    # Foo definition. Foo is NOT used as a return type here, so the edge can only
    # come from the constructor call (object_creation_expression), not return-type
    # handling.
    foo = _write(
        tmp_path / "Foo.java",
        "package com.app;\npublic record Foo(int x, String y) {}\n",
    )
    caller = _write(
        tmp_path / "Helper.java",
        "package com.app;\n"
        "public class Helper {\n"
        "    public void build() {\n"
        "        Object o = new Foo(1, \"a\");\n"
        "        System.out.println(o);\n"
        "    }\n"
        "}\n",
    )
    result = extract([foo, caller], cache_root=tmp_path)

    foo_id = next(n["id"] for n in result["nodes"]
                  if n.get("label") == "Foo" and n.get("source_file"))
    call_targets = {
        e["target"] for e in result["edges"]
        if e.get("relation") in ("calls", "references")
    }
    assert foo_id in call_targets, "new Foo(...) should produce a calls/references edge to Foo"

    # Survives graph construction (target is a real node).
    g = build_from_json(result)
    assert foo_id in set(g.nodes())
