"""A Go method value passed as an argument links the caller to the method.

`routing.Wrap(s.Handle)` and `r.Get("/p", s.Handle)` are how Go registers a handler or a
callback. The method is not called at that site, so the call walk never saw it and a
handler reached only through its registration had no caller at all. It is recorded as
an INFERRED `indirect_call`, like a callback passed by name in Python and JS (#1566),
typed through the receiver's declared type the way the member-call resolver types a
direct call.
"""
from __future__ import annotations

import importlib

import pytest

from graphify.extract import extract

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("tree_sitter_go") is None,
    reason="tree_sitter_go not installed",
)

ROUTING = (
    "package routing\n\ntype Handler func(string) string\n\n"
    "func Wrap(h Handler) Handler { return h }\n"
)
SERVER = (
    "package api\n\ntype Server struct{}\n\n"
    "func (s *Server) Health(name string) string { return name }\n"
)


def _edges(tmp_path, files: dict[str, str]) -> dict[tuple[str, str, str], dict]:
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    result = extract([tmp_path / n for n in files if n.endswith(".go")],
                     cache_root=tmp_path / "graphify-out", parallel=False)
    label = {n["id"]: n["label"] for n in result["nodes"]}
    return {(label.get(e["source"]), e["relation"], label.get(e["target"])): e
            for e in result["edges"] if e["relation"] in ("calls", "indirect_call")}


def _files(register: str) -> dict[str, str]:
    return {
        "go.mod": "module example.com/m\n\ngo 1.22\n",
        "routing/routing.go": ROUTING,
        "api/server.go": SERVER,
        "api/routes.go": "package api\n\nimport \"example.com/m/routing\"\n\n" + register,
    }


def test_a_method_value_on_the_methods_own_receiver_is_an_indirect_call(tmp_path):
    edges = _edges(tmp_path, _files(
        "func (s *Server) Register() routing.Handler {\n"
        "\treturn routing.Wrap(s.Health)\n}\n"))
    edge = edges.get((".Register()", "indirect_call", ".Health()"))
    assert edge is not None, edges
    assert edge["confidence"] == "INFERRED"
    assert (".Register()", "calls", ".Health()") not in edges, edges
    # The registration call itself is unchanged.
    assert (".Register()", "calls", "Wrap()") in edges, edges


def test_a_method_value_on_a_typed_parameter_is_an_indirect_call(tmp_path):
    edges = _edges(tmp_path, _files(
        "func Register(s *Server) routing.Handler {\n"
        "\treturn routing.Wrap(s.Health)\n}\n"))
    assert ("Register()", "indirect_call", ".Health()") in edges, edges


def test_a_field_passed_as_an_argument_links_nothing_and_parks_nothing(tmp_path):
    # `s.name` is a field, not a method; and `Unknown` is declared nowhere, which for a
    # direct call would park it for a merge. A value argument is neither.
    files = _files(
        "type Holder struct {\n\tname string\n}\n\n"
        "func (h *Holder) Use(u *Unknown) {\n\tprintln(h.name)\n\tkeep(u.Health)\n}\n\n"
        "func keep(v any) {}\n")
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    result = extract([tmp_path / n for n in files if n.endswith(".go")],
                     cache_root=tmp_path / "graphify-out", parallel=False)
    label = {n["id"]: n["label"] for n in result["nodes"]}
    assert not [e for e in result["edges"] if e["relation"] == "indirect_call"], result["edges"]
    use = next(n for n in result["nodes"] if label[n["id"]] == ".Use()")
    assert not (use.get("metadata") or {}).get("unresolved_calls"), use


def test_a_package_function_value_is_not_read_as_a_method_value(tmp_path):
    # `routing.Wrap` names a function of an imported package, not a method of a value.
    edges = _edges(tmp_path, _files(
        "func Register(s *Server) any {\n\treturn keep(routing.Wrap)\n}\n\n"
        "func keep(v any) any { return v }\n"))
    assert not [k for k in edges if k[1] == "indirect_call"], edges
