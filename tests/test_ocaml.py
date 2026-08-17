"""Tests for the OCaml extractor (graphify/extractors/ocaml.py)."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_ocaml")

from graphify.extract import extract_ocaml


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def _labels(r) -> set[str]:
    return {n["label"] for n in r["nodes"]}


def _rel_pairs(r, relation: str) -> set[tuple[str, str]]:
    lab = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (lab.get(e["source"], e["source"]), lab.get(e["target"], e["target"]))
        for e in r["edges"]
        if e["relation"] == relation
    }


IMPL = """\
open Stdlib

module Shapes = struct
  type shape = Circle | Square | Triangle

  let pi = 3.14159

  let area_of radius =
    let squared = radius *. radius in
    pi *. squared

  let describe r =
    let a = area_of r in
    print_float a
end

let main () =
  let a = Shapes.area_of 2.0 in
  print_float a
"""


def test_impl_defines_module_values_and_types(tmp_path):
    r = extract_ocaml(_write(tmp_path, "shapes.ml", IMPL))
    assert "error" not in r
    labels = _labels(r)
    # module, values/functions, type, variant constructors
    assert {"Shapes", "pi", "area_of", "describe", "main", "shape"} <= labels
    assert {"Circle", "Square", "Triangle"} <= labels


def test_impl_containment_and_defines(tmp_path):
    r = extract_ocaml(_write(tmp_path, "shapes.ml", IMPL))
    # file defines the top-level module and top-level `main`
    defines = _rel_pairs(r, "defines")
    assert ("shapes.ml", "Shapes") in defines
    assert ("shapes.ml", "main") in defines
    # module contains its members
    contains = _rel_pairs(r, "contains")
    assert ("Shapes", "area_of") in contains
    assert ("Shapes", "shape") in contains
    # variant constructors are contained by their type
    assert ("shape", "Circle") in contains


def test_impl_calls_resolve_same_file(tmp_path):
    r = extract_ocaml(_write(tmp_path, "shapes.ml", IMPL))
    calls = _rel_pairs(r, "calls")
    # describe -> area_of is a same-file, unambiguous resolution
    assert ("describe", "area_of") in calls
    # a qualified call `Shapes.area_of` resolves to the value `area_of`, NOT the
    # module qualifier `Shapes`.
    assert ("main", "area_of") in calls
    assert ("main", "Shapes") not in calls


def test_qualified_external_call_does_not_bind_to_local_same_name(tmp_path):
    """A qualified call `M.f` to an EXTERNAL module (not defined in this file)
    must not bind to a same-named local `f` — that would be a false edge and,
    when the caller is that local `f`, a `f -> f` self-loop. It is kept as a
    distinct external target labelled by the full path (e.g. Hardcaml's
    `Reg_spec.create` next to a local `let create`)."""
    src = (
        "let create x =\n"
        "  let spec = Reg_spec.create x in\n"  # external, same bare name as local
        "  spec\n"
        "let run () = Scope.create ()\n"       # external, same bare name
    )
    r = extract_ocaml(_write(tmp_path, "counter.ml", src))
    calls = _rel_pairs(r, "calls")
    assert ("create", "create") not in calls              # no self-loop
    assert ("create", "Reg_spec.create") in calls         # kept distinct
    assert ("run", "Scope.create") in calls
    assert ("run", "create") not in calls                 # not the local create
    # no dangling edges introduced by the qualified external stubs
    ids = {n["id"] for n in r["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in r["edges"])


def test_qualified_call_into_local_module_resolves(tmp_path):
    """A qualified call whose qualifier IS a module defined in this file still
    resolves to the local definition."""
    src = (
        "module M = struct\n"
        "  let helper x = x\n"
        "end\n"
        "let run () = M.helper 1\n"
    )
    r = extract_ocaml(_write(tmp_path, "m.ml", src))
    calls = _rel_pairs(r, "calls")
    assert ("run", "helper") in calls
    assert not any(t == "M.helper" for _, t in calls)  # not left as an external stub


def test_impl_open_emits_import(tmp_path):
    r = extract_ocaml(_write(tmp_path, "shapes.ml", IMPL))
    imports = _rel_pairs(r, "imports_from")
    assert ("shapes.ml", "Stdlib") in imports


def test_open_stub_is_sourceless(tmp_path):
    # An `open`ed external module must be a SOURCELESS stub so the corpus rewire
    # can collapse/prune it without baking this file's path into the id (#1402).
    r = extract_ocaml(_write(tmp_path, "shapes.ml", IMPL))
    stubs = [n for n in r["nodes"] if n["label"] == "Stdlib"]
    assert stubs and all(n["source_file"] == "" for n in stubs)
    # origin_file is an internal rewire hint, never a real source path.
    assert all(n.get("source_location") == "" for n in stubs)


INTERFACE = """\
open Base

module type Store = sig
  type t
  val make : int -> t
  val size : t -> int
end

type color = Red | Green | Blue

val hello : string -> unit
"""


def test_interface_defines_signatures(tmp_path):
    r = extract_ocaml(_write(tmp_path, "store.mli", INTERFACE))
    assert "error" not in r
    labels = _labels(r)
    assert {"Store", "make", "size", "color", "hello"} <= labels
    assert {"Red", "Green", "Blue"} <= labels
    # interfaces have no expression bodies -> no calls
    assert not [e for e in r["edges"] if e["relation"] == "calls"]


def test_no_dangling_edges(tmp_path):
    r = extract_ocaml(_write(tmp_path, "shapes.ml", IMPL))
    ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in ids, e
        assert e["target"] in ids, e


def test_missing_file_returns_error(tmp_path):
    r = extract_ocaml(tmp_path / "nope.ml")
    assert r["nodes"] == [] and r["edges"] == []
    assert "error" in r
