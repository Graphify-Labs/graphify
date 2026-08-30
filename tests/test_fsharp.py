"""Tests for the F# extractor (graphify/extractors/fsharp.py)."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_fsharp")

from graphify.extract import extract_fsharp


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
module Grasp.Sidecar.Demo

open System.Text
open Grasp.Abstractions

type Config = { Port: int; Host: string }
type Mode = | Fast | Careful of int

exception BadFrame of string

let defaultPort = 8080

let makeConfig host =
    { Port = defaultPort; Host = host }

let validate cfg = cfg

let start (cfg: Config) =
    let sb = StringBuilder()
    sb.Append(cfg.Host) |> ignore
    makeConfig cfg.Host |> validate

type Server(cfg: Config) =
    member this.Run() = start cfg
    static member Default = Server(makeConfig "x")
"""


def test_defines_module_types_values_and_members(tmp_path):
    r = extract_fsharp(_write(tmp_path, "demo.fs", IMPL))
    assert "error" not in r
    labels = _labels(r)
    # module (last segment), record + DU types, exception, let-bound defs
    assert {"Demo", "Config", "Mode", "BadFrame",
            "defaultPort", "makeConfig", "validate", "start"} <= labels
    # DU cases and class members
    assert {"Fast", "Careful", "Server", "Run", "Default"} <= labels


def test_containment_shape(tmp_path):
    r = extract_fsharp(_write(tmp_path, "demo.fs", IMPL))
    defines = _rel_pairs(r, "defines")
    contains = _rel_pairs(r, "contains")
    # file defines the top-level module; module contains its declarations
    assert ("demo.fs", "Demo") in defines
    assert ("Demo", "makeConfig") in contains
    assert ("Demo", "Config") in contains
    # DU cases contained by their type; members contained by their class
    assert ("Mode", "Fast") in contains
    assert ("Mode", "Careful") in contains
    assert ("Server", "Run") in contains
    assert ("Server", "Default") in contains


def test_nested_let_does_not_mint_a_definition(tmp_path):
    r = extract_fsharp(_write(tmp_path, "demo.fs", IMPL))
    # `let sb = ...` is local to `start` and must not become a node.
    assert "sb" not in _labels(r)


def test_pipeline_calls_resolve_same_file(tmp_path):
    r = extract_fsharp(_write(tmp_path, "demo.fs", IMPL))
    calls = _rel_pairs(r, "calls")
    # `makeConfig cfg.Host |> validate` inside `start`:
    # the application edge AND the pipeline edge, both attributed to `start`.
    assert ("start", "makeConfig") in calls
    assert ("start", "validate") in calls


def test_member_body_calls_attribute_to_member(tmp_path):
    r = extract_fsharp(_write(tmp_path, "demo.fs", IMPL))
    calls = _rel_pairs(r, "calls")
    # `member this.Run() = start cfg` — caller is Run, not the file.
    assert ("Run", "start") in calls


def test_pipeline_callee_left_of_backpipe(tmp_path):
    src = "module M\nlet f x = x\nlet g y =\n    f <| y\n"
    r = extract_fsharp(_write(tmp_path, "back.fs", src))
    assert ("g", "f") in _rel_pairs(r, "calls")


def test_open_becomes_imports_from_stub(tmp_path):
    r = extract_fsharp(_write(tmp_path, "demo.fs", IMPL))
    imports = _rel_pairs(r, "imports_from")
    targets = {t for _, t in imports}
    assert {"Text", "Abstractions"} <= targets
    # the stub is sourceless so the corpus rewire can collapse it (#1402)
    by_label = {n["label"]: n for n in r["nodes"]}
    assert by_label["Abstractions"]["source_file"] == ""


def test_qualified_external_call_stays_distinct(tmp_path):
    # `sb.Append(...)`: `sb` is not a local container, so the callee must be a
    # stub and never bind to a hypothetical local `Append`.
    src = ("module M\n"
           "let Append x = x\n"
           "let go (sb: System.Text.StringBuilder) =\n"
           "    sb.Append(\"y\") |> ignore\n")
    r = extract_fsharp(_write(tmp_path, "qual.fs", src))
    lab = {n["id"]: n for n in r["nodes"]}
    for e in r["edges"]:
        if e["relation"] != "calls":
            continue
        tgt = lab[e["target"]]
        if tgt["label"] in ("Append", "sb.Append"):
            # must NOT resolve to the local definition (which has a source_file)
            assert tgt["source_file"] == "", (
                "external qualified call bound to a local definition")


def test_fsx_script_parses(tmp_path):
    src = "let hello name =\n    printfn \"hi %s\" name\nhello \"world\"\n"
    r = extract_fsharp(_write(tmp_path, "script.fsx", src))
    assert "error" not in r
    assert "hello" in _labels(r)
    assert ("script.fsx", "hello") in _rel_pairs(r, "calls") or \
           ("hello", "printfn") in _rel_pairs(r, "calls")


def test_annotated_let_names_the_binding_not_the_type(tmp_path):
    # `let subscribe (a: A) (b: B) : IDisposable = ...` parses as a
    # value_declaration_left whose LAST identifier is the return type. The
    # minted definition must be `subscribe`; a sourced `IDisposable` node here
    # would absorb every BCL `implements IDisposable` stub in the corpus
    # rewire (found live on Grasp.Sidecar/SpanEmitter.fs L68).
    src = ("module M\n"
           "let subscribe (source: A) (events: B) : IDisposable =\n"
           "    ignore source\n"
           "let port : int = 8080\n")
    r = extract_fsharp(_write(tmp_path, "ann.fs", src))
    sourced = {n["label"] for n in r["nodes"] if n.get("source_file")}
    assert "subscribe" in sourced
    assert "port" in sourced
    assert "IDisposable" not in sourced
    assert "int" not in sourced


def test_missing_grammar_is_reported_not_raised(tmp_path, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "tree_sitter_fsharp":
            raise ImportError("boom")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    r = extract_fsharp(_write(tmp_path, "x.fs", "module M\n"))
    assert r["nodes"] == [] and "not installed" in r["error"]
