"""Types named in a Go package-level `var` initialiser are referenced by the file.

#2360 credits calls in a package-level initialiser to the file, but the types named
there, in `new(T)`, `new(*pkg.T)` or a composite literal, produced no edge. A file
holding only a google/wire set (`wire.Bind(new(Iface), new(*Impl))`) then referenced
nothing and was reported as yielding no symbols.
"""
from __future__ import annotations

import importlib

import pytest

from graphify.extract import extract

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("tree_sitter_go") is None,
    reason="tree_sitter_go not installed",
)

GO_MOD = "module example.com/app\n\ngo 1.22\n"
VALIDATOR = (
    "package validator\n\n"
    "type DataSourceRequestValidator interface{ Validate() error }\n\n"
    "type OSSDataSourceRequestValidator struct{}\n\n"
    "func (v *OSSDataSourceRequestValidator) Validate() error { return nil }\n\n"
    "func ProvideValidator() *OSSDataSourceRequestValidator {\n"
    "\treturn &OSSDataSourceRequestValidator{}\n}\n"
)


def _extract(tmp_path, files: dict[str, str]) -> dict:
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return extract([tmp_path / n for n in files if n.endswith(".go")],
                   cache_root=tmp_path / "graphify-out", root=tmp_path, parallel=False)


def _file_refs(result: dict, file_label: str) -> set[tuple[str, str]]:
    """(target label, target source file name) of each `references` edge from a file."""
    by_id = {n["id"]: n for n in result["nodes"]}
    file_ids = {n["id"] for n in result["nodes"] if n["label"] == file_label}
    out = set()
    for e in result["edges"]:
        if e["relation"] == "references" and e["source"] in file_ids:
            tgt = by_id.get(e["target"], {})
            out.add((tgt.get("label"), str(tgt.get("source_file") or "").replace("\\", "/")
                     .rpartition("/")[2]))
    return out


def test_wire_bind_new_types_are_referenced_by_the_file(tmp_path):
    result = _extract(tmp_path, {
        "go.mod": GO_MOD,
        "validator/validator.go": VALIDATOR,
        "server/wire.go": (
            "package server\n\nimport (\n\t\"github.com/google/wire\"\n"
            "\t\"example.com/app/validator\"\n)\n\n"
            "var wireSet = wire.NewSet(\n\tvalidator.ProvideValidator,\n"
            "\twire.Bind(new(validator.DataSourceRequestValidator), "
            "new(*validator.OSSDataSourceRequestValidator)),\n)\n"
        ),
    })
    refs = _file_refs(result, "wire.go")
    assert ("DataSourceRequestValidator", "validator.go") in refs, refs
    assert ("OSSDataSourceRequestValidator", "validator.go") in refs, refs


def test_composite_literal_and_bare_new_types_are_referenced_by_the_file(tmp_path):
    result = _extract(tmp_path, {
        "go.mod": GO_MOD,
        "validator/validator.go": VALIDATOR,
        "server/types.go": "package server\n\ntype Registry struct{}\n\ntype Entry struct{}\n",
        "server/vars.go": (
            "package server\n\nimport \"example.com/app/validator\"\n\n"
            "var (\n"
            "\tdefaultValidator = validator.OSSDataSourceRequestValidator{}\n"
            "\tregistry         = new(Registry)\n"
            "\tentries          = []*Entry{{}}\n"
            "\tchecker          validator.DataSourceRequestValidator\n"
            ")\n"
        ),
    })
    refs = _file_refs(result, "vars.go")
    assert ("OSSDataSourceRequestValidator", "validator.go") in refs, refs
    assert ("Registry", "types.go") in refs, refs
    assert ("Entry", "types.go") in refs, refs
    assert ("DataSourceRequestValidator", "validator.go") in refs, refs


def test_an_external_type_does_not_bind_to_a_local_type_or_mint_call_nodes(tmp_path):
    # `http.Client` is parked on its import path, as an external struct field type is,
    # never bound to the same-named local `Client`; the external `wire` calls add nothing.
    result = _extract(tmp_path, {
        "go.mod": GO_MOD,
        "server/client.go": "package server\n\ntype Client struct{}\n",
        "server/wire.go": (
            "package server\n\nimport (\n\t\"net/http\"\n\t\"github.com/google/wire\"\n)\n\n"
            "var wireSet = wire.NewSet(wire.Bind(new(http.Doer), new(*http.Client)))\n"
        ),
    })
    refs = _file_refs(result, "wire.go")
    assert ("Client", "client.go") not in refs, refs
    assert refs == {("net/http.Doer", ""), ("net/http.Client", "")}, refs
    labels = {n["label"] for n in result["nodes"]}
    assert not labels & {"NewSet", "NewSet()", "Bind", "Bind()", "wire.NewSet", "wire.Bind"}
    wire_ids = {n["id"] for n in result["nodes"] if n["label"] == "wire.go"}
    assert not [e for e in result["edges"]
                if e["source"] in wire_ids and e["relation"] in ("calls", "indirect_call")]


def test_a_type_inside_a_var_closure_body_is_not_credited_to_the_file(tmp_path):
    # A closure body is function code, which emits no body type references.
    result = _extract(tmp_path, {
        "go.mod": GO_MOD,
        "svc/types.go": "package svc\n\ntype Conn struct{}\n",
        "svc/hook.go": "package svc\n\nvar dial = func() any { return &Conn{} }\n",
    })
    assert ("Conn", "types.go") not in _file_refs(result, "hook.go")
