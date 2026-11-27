"""Go member-level interface dispatch.

`d.provider.GetWithDataSource()` on a field typed with a local interface
resolves to the interface's own `.GetWithDataSource()` requirement, which is
what the call site names. Go types satisfy an interface implicitly, so there
is no `implements` edge for the shared dispatch mechanism to read, and the
concrete method used to sit unreachable from every call through the interface.

`resolve_go_interface_dispatch` infers the implementers from method sets (every
method name the interface requires) and links each requirement to the matching
method. Confidence falls as the implementer count grows (0.85 / 0.75 / 0.65).
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract

_GO_MOD = "module example.com/app\n\ngo 1.22\n"

_PROVIDER = (
    "package plugincontext\n\n"
    "type Provider struct{}\n\n"
    "func (p *Provider) GetWithDataSource(uid string) error { return p.lookup(uid) }\n\n"
    "func (p *Provider) lookup(uid string) error { return nil }\n"
)

_NODES = (
    "package expr\n\n"
    "type pluginContextProvider interface {\n"
    "\tGetWithDataSource(uid string) error\n"
    "}\n\n"
    "type DSNode struct {\n"
    "\tprovider pluginContextProvider\n"
    "}\n\n"
    "func (d *DSNode) Execute() error {\n"
    "\treturn d.provider.GetWithDataSource(\"x\")\n"
    "}\n"
)


def _extract(tmp_path: Path, files: dict[str, str]):
    (tmp_path / "go.mod").write_text(_GO_MOD)
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    r = extract(
        sorted(tmp_path / n for n in files),
        cache_root=tmp_path / "cache",
        root=tmp_path,
        parallel=False,
    )
    dispatch = {(e["source"], e["target"]) for e in r["edges"]
                if e["relation"] == "dispatches_to"}
    return dispatch, r


def _find(r, label, id_contains):
    return next(n["id"] for n in r["nodes"]
                if n["label"] == label and id_contains in n["id"])


def _reachable(r, start: str) -> set[str]:
    adjacency: dict[str, list[str]] = {}
    for e in r["edges"]:
        adjacency.setdefault(e["source"], []).append(e["target"])
    seen = {start}
    queue = [start]
    while queue:
        for nxt in adjacency.get(queue.pop(0), []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def test_local_interface_dispatches_to_an_implementer_in_another_package(tmp_path):
    dispatch, r = _extract(tmp_path, {
        "plugincontext/provider.go": _PROVIDER,
        "expr/nodes.go": _NODES,
    })
    requirement = _find(r, ".GetWithDataSource()", "plugincontextprovider")
    concrete = _find(r, ".GetWithDataSource()", "plugincontext_provider")
    assert dispatch == {(requirement, concrete)}
    edge = next(e for e in r["edges"] if e["relation"] == "dispatches_to")
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.85
    assert edge["context"] == "call"
    assert edge["source_file"].endswith("provider.go")
    # Additive: the call to the interface method stays, and the chain now
    # continues into the concrete method's own callees.
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    assert (_find(r, ".Execute()", "dsnode"), requirement) in calls
    assert _find(r, ".lookup()", "provider") in _reachable(r, _find(r, ".Execute()", "dsnode"))
    # The inferred pairs feed the dispatch pass; they are not graph edges.
    assert not any(e["relation"] == "implements" for e in r["edges"])


def test_value_and_pointer_receivers_both_count(tmp_path):
    dispatch, r = _extract(tmp_path, {"shape/shape.go": (
        "package shape\n\n"
        "type Shape interface {\n\tArea() float64\n\tName() string\n}\n\n"
        "type Square struct{ side float64 }\n\n"
        "func (s Square) Area() float64 { return s.side * s.side }\n\n"
        "func (s *Square) Name() string { return \"square\" }\n"
    )})
    assert dispatch == {
        (_find(r, ".Area()", "shape_shape"), _find(r, ".Area()", "square")),
        (_find(r, ".Name()", "shape_shape"), _find(r, ".Name()", "square")),
    }


def test_a_type_missing_one_method_does_not_implement(tmp_path):
    dispatch, _ = _extract(tmp_path, {"shape/shape.go": (
        "package shape\n\n"
        "type Shape interface {\n\tArea() float64\n\tName() string\n}\n\n"
        "type Square struct{}\n\n"
        "func (s Square) Area() float64 { return 1 }\n"
    )})
    assert not dispatch


def test_two_implementers_both_get_an_edge_at_lower_confidence(tmp_path):
    dispatch, r = _extract(tmp_path, {"shape/shape.go": (
        "package shape\n\n"
        "type Shape interface {\n\tArea() float64\n}\n\n"
        "type Square struct{}\n\n"
        "func (s Square) Area() float64 { return 1 }\n\n"
        "type Circle struct{}\n\n"
        "func (c *Circle) Area() float64 { return 2 }\n"
    )})
    requirement = _find(r, ".Area()", "shape_shape")
    assert dispatch == {
        (requirement, _find(r, ".Area()", "square")),
        (requirement, _find(r, ".Area()", "circle")),
    }
    assert {e["confidence_score"] for e in r["edges"]
            if e["relation"] == "dispatches_to"} == {0.75}


def test_empty_interface_is_ignored(tmp_path):
    dispatch, _ = _extract(tmp_path, {"box/box.go": (
        "package box\n\n"
        "type Anything interface{}\n\n"
        "type Box struct{ v Anything }\n\n"
        "func (b Box) Get() Anything { return b.v }\n"
    )})
    assert not dispatch


def test_embedded_interface_methods_are_required(tmp_path):
    # ReadCloser requires Read (via Reader) and Close; File has both, Pipe only Close.
    dispatch, r = _extract(tmp_path, {"io2/io.go": (
        "package io2\n\n"
        "type Reader interface {\n\tRead() int\n}\n\n"
        "type ReadCloser interface {\n\tReader\n\tClose() error\n}\n\n"
        "type File struct{}\n\n"
        "func (f *File) Read() int { return 0 }\n\n"
        "func (f *File) Close() error { return nil }\n\n"
        "type Pipe struct{}\n\n"
        "func (p *Pipe) Close() error { return nil }\n"
    )})
    assert (_find(r, ".Close()", "readcloser"), _find(r, ".Close()", "file")) in dispatch
    assert (_find(r, ".Read()", "reader"), _find(r, ".Read()", "file")) in dispatch
    assert not any("pipe" in target for _, target in dispatch)


def test_interface_embedding_an_external_interface_is_skipped(tmp_path):
    # io.Reader's methods are not in the corpus, so the method set is unknown.
    dispatch, _ = _extract(tmp_path, {"rc/rc.go": (
        "package rc\n\n"
        "import \"io\"\n\n"
        "type ReadCloser interface {\n\tio.Reader\n\tClose() error\n}\n\n"
        "type Pipe struct{}\n\n"
        "func (p *Pipe) Close() error { return nil }\n"
    )})
    assert not dispatch


def test_unexported_method_is_only_implemented_in_the_same_package(tmp_path):
    dispatch, r = _extract(tmp_path, {
        "a/a.go": (
            "package a\n\n"
            "type runner interface {\n\trun()\n}\n\n"
            "type local struct{}\n\n"
            "func (l local) run() {}\n"
        ),
        "b/b.go": "package b\n\ntype remote struct{}\n\nfunc (r remote) run() {}\n",
    })
    assert dispatch == {(_find(r, ".run()", "a_runner"), _find(r, ".run()", "a_local"))}


def test_interface_with_too_many_implementers_is_skipped(tmp_path):
    from graphify.go_dispatch import _MAX_IMPLICIT_IMPLEMENTERS

    types = "".join(
        f"type T{i} struct{{}}\n\nfunc (t T{i}) Close() error {{ return nil }}\n\n"
        for i in range(_MAX_IMPLICIT_IMPLEMENTERS + 1)
    )
    dispatch, _ = _extract(tmp_path, {"c/c.go": (
        "package c\n\ntype closer interface {\n\tClose() error\n}\n\n" + types
    )})
    assert not dispatch


def test_a_non_go_interface_is_untouched(tmp_path):
    from graphify.go_dispatch import resolve_go_interface_dispatch

    nodes = [
        {"id": "iface", "label": "IR", "source_file": "a.cs",
         "metadata": {"language": "go", "kind": "interface"}},
        {"id": "impl", "label": "A", "source_file": "a.go"},
        {"id": "iface_m", "label": ".M()", "source_file": "a.cs"},
        {"id": "impl_m", "label": ".M()", "source_file": "a.go"},
    ]
    edges = [
        {"source": "iface", "target": "iface_m", "relation": "method"},
        {"source": "impl", "target": "impl_m", "relation": "method"},
    ]
    resolve_go_interface_dispatch([], nodes, edges)
    assert not any(e["relation"] == "dispatches_to" for e in edges)
