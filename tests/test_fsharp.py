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
            "defaultPort", "makeConfig()", "validate()", "start()"} <= labels
    # DU cases and class members
    assert {"Fast", "Careful", "Server", ".Run()", ".Default()"} <= labels


def test_containment_shape(tmp_path):
    r = extract_fsharp(_write(tmp_path, "demo.fs", IMPL))
    defines = _rel_pairs(r, "defines")
    contains = _rel_pairs(r, "contains")
    # file defines the top-level module; module contains its declarations
    assert ("demo.fs", "Demo") in defines
    assert ("Demo", "makeConfig()") in contains
    assert ("Demo", "Config") in contains
    # DU cases contained by their type; members contained by their class
    assert ("Mode", "Fast") in contains
    assert ("Mode", "Careful") in contains
    assert ("Server", ".Run()") in contains
    assert ("Server", ".Default()") in contains


def test_nested_let_does_not_mint_a_definition(tmp_path):
    r = extract_fsharp(_write(tmp_path, "demo.fs", IMPL))
    # `let sb = ...` is local to `start` and must not become a node.
    assert "sb" not in _labels(r)


def test_pipeline_calls_resolve_same_file(tmp_path):
    r = extract_fsharp(_write(tmp_path, "demo.fs", IMPL))
    calls = _rel_pairs(r, "calls")
    # `makeConfig cfg.Host |> validate` inside `start`:
    # the application edge AND the pipeline edge, both attributed to `start`.
    assert ("start()", "makeConfig()") in calls
    assert ("start()", "validate()") in calls


def test_member_body_calls_attribute_to_member(tmp_path):
    r = extract_fsharp(_write(tmp_path, "demo.fs", IMPL))
    calls = _rel_pairs(r, "calls")
    # `member this.Run() = start cfg` — caller is Run, not the file.
    assert (".Run()", "start()") in calls


def test_pipeline_callee_left_of_backpipe(tmp_path):
    src = "module M\nlet f x = x\nlet g y =\n    f <| y\n"
    r = extract_fsharp(_write(tmp_path, "back.fs", src))
    assert ("g()", "f()") in _rel_pairs(r, "calls")



def test_qualified_external_call_stays_distinct(tmp_path):
    # `sb.Append(...)`: `sb` is not a local container, so the callee must be a
    # stub and never bind to a hypothetical local `Append`.
    src = ("module M\n"
           "let Append x = x\n"
           "let go (sb: System.Text.StringBuilder) =\n"
           "    sb.Append(\"y\") |> ignore\n")
    r = extract_fsharp(_write(tmp_path, "qual.fs", src))
    lab = {n["id"]: n for n in r["nodes"]}
    # The edge must EXIST: without this, the loop below is vacuously green when
    # no call edge is emitted at all (caught by graphify's own review of this PR).
    append_edges = [e for e in r["edges"] if e["relation"] == "calls"
                    and lab[e["target"]]["label"] in ("Append", "sb.Append")]
    assert append_edges, "no call edge emitted for sb.Append at all"
    for e in append_edges:
        # must NOT resolve to the local definition (which has a source_file)
        assert lab[e["target"]]["source_file"] == "", (
            "external qualified call bound to a local definition")


def test_fsx_script_parses(tmp_path):
    src = "let hello name =\n    printfn \"hi %s\" name\nhello \"world\"\n"
    r = extract_fsharp(_write(tmp_path, "script.fsx", src))
    assert "error" not in r
    assert "hello()" in _labels(r)
    calls = _rel_pairs(r, "calls")
    assert ("script.fsx", "hello()") in calls
    assert ("hello()", "printfn") in calls


def test_same_named_members_of_different_types_stay_distinct(tmp_path):
    # Two types in ONE file, each with a Dispose member: file-scoped member ids
    # would merge them into a single node (caught by graphify's own review).
    src = ("module M\n"
           "type A() =\n"
           "    member this.Dispose() = 1\n"
           "type B() =\n"
           "    member this.Dispose() = 2\n")
    r = extract_fsharp(_write(tmp_path, "two.fs", src))
    disp = [n for n in r["nodes"] if n["label"] == ".Dispose()" and n.get("source_file")]
    assert len(disp) == 2, f"expected 2 Dispose nodes, got {len(disp)}"
    contains = _rel_pairs(r, "contains")
    assert ("A", ".Dispose()") in contains and ("B", ".Dispose()") in contains


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
    assert "subscribe" in sourced or "subscribe()" in sourced
    assert "port" in sourced
    assert "IDisposable" not in sourced
    assert "int" not in sourced


def test_dotted_callee_records_call(tmp_path):
    # `Grasp.Telemetry.init args` parses as application > dot_expression; the
    # callee must be recorded as a full-path stub, not silently skipped.
    src = "module M\nlet go args =\n    Grasp.Telemetry.init args\n"
    r = extract_fsharp(_write(tmp_path, "dot.fs", src))
    calls = _rel_pairs(r, "calls")
    assert ("go()", "Grasp.Telemetry.init") in calls or ("go()", "init") in calls, calls


def test_let_rec_and_mints_every_binding(tmp_path):
    src = "module M\nlet rec f x = g x\nand g y = f y\n"
    r = extract_fsharp(_write(tmp_path, "rec.fs", src))
    sourced = {n["label"] for n in r["nodes"] if n.get("source_file")}
    assert {"f()", "g()"} <= sourced
    calls = _rel_pairs(r, "calls")
    assert ("f()", "g()") in calls
    assert ("g()", "f()") in calls
    assert ("f()", "f()") not in calls, "false self-loop from mis-attributed and-binding"


def test_enum_members_are_emitted(tmp_path):
    src = "module M\ntype Color =\n    | Red = 0\n    | Blue = 1\n"
    r = extract_fsharp(_write(tmp_path, "enum.fs", src))
    contains = _rel_pairs(r, "contains")
    assert ("Color", "Red") in contains and ("Color", "Blue") in contains


def test_destructuring_let_mints_each_name(tmp_path):
    src = "module M\nlet (major, minor) = parseVersion v\n"
    r = extract_fsharp(_write(tmp_path, "destr.fs", src))
    sourced = {n["label"] for n in r["nodes"] if n.get("source_file")}
    assert {"major", "minor"} <= sourced


def test_comment_inside_pipeline_keeps_call_edge(tmp_path):
    src = "module M\nlet f x = x\nlet h x =\n    x // note\n    |> f\n"
    r = extract_fsharp(_write(tmp_path, "cpipe.fs", src))
    assert ("h()", "f()") in _rel_pairs(r, "calls")


def test_same_named_union_cases_stay_type_scoped(tmp_path):
    src = ("module M\n"
           "type ParseResult = | Ok of int | Bad\n"
           "type SaveResult = | Ok of string | Failed\n")
    r = extract_fsharp(_write(tmp_path, "du.fs", src))
    oks = [n for n in r["nodes"] if n["label"] == "Ok" and n.get("source_file")]
    assert len(oks) == 2, f"expected 2 type-scoped Ok nodes, got {len(oks)}"


def test_single_case_du_has_no_self_loop(tmp_path):
    src = "module M\ntype Email = Email of string\n"
    r = extract_fsharp(_write(tmp_path, "email.fs", src))
    for e in r["edges"]:
        assert e["source"] != e["target"], f"self-loop: {e}"
    emails = [n for n in r["nodes"] if n["label"] == "Email" and n.get("source_file")]
    assert len(emails) == 2  # the type AND its case, distinct


def test_namespace_is_canonical_and_marked(tmp_path):
    src_a = "namespace Grasp.Core\ntype A() = member this.Go() = 1\n"
    src_b = "namespace Grasp.Core\ntype B() = member this.Ho() = 2\n"
    ra = extract_fsharp(_write(tmp_path, "a.fs", src_a))
    rb = extract_fsharp(_write(tmp_path, "b.fs", src_b))
    ns_a = [n for n in ra["nodes"] if n.get("type") == "namespace"]
    ns_b = [n for n in rb["nodes"] if n.get("type") == "namespace"]
    assert ns_a and ns_b
    assert ns_a[0]["id"] == ns_b[0]["id"], "namespace id must be canonical across files"
    assert ns_a[0]["id"].startswith("csharp_namespace:")
    assert ns_a[0]["label"] == "Grasp.Core"


def test_namespace_segment_does_not_bind_local(tmp_path):
    # Under `namespace Grasp.Sidecar`, the call `Sidecar.validate c` must stay
    # a stub — the namespace is corpus-wide, not a local qualifier.
    src = ("namespace Grasp.Sidecar\n"
           "module Impl =\n"
           "    let validate c = c\n"
           "    let go c = Sidecar.validate c\n")
    r = extract_fsharp(_write(tmp_path, "ns.fs", src))
    lab = {n["id"]: n for n in r["nodes"]}
    vcalls = [e for e in r["edges"] if e["relation"] == "calls"
              and lab[e["target"]]["label"] in ("validate", "validate()",
                                                "Sidecar.validate")]
    assert vcalls, "no call edge for Sidecar.validate at all"
    for e in vcalls:
        assert not lab[e["target"]].get("source_file"), (
            "namespace-rooted call falsely bound to local definition")


# ── Findings from the four-model panel (round 3) ─────────────────────────────


def test_generic_type_named_after_itself_not_its_parameter(tmp_path):
    src = ("module M\n"
           "type Box<'T>() =\n"
           "    static member Create(x: 'T) = x\n"
           "type Cache<'T when 'T :> System.IDisposable> = { Item: 'T }\n")
    r = extract_fsharp(_write(tmp_path, "gen.fs", src))
    sourced = {n["label"] for n in r["nodes"] if n.get("source_file")}
    assert {"Box", "Cache"} <= sourced
    assert "T" not in sourced
    assert "IDisposable" not in sourced, "constraint type minted as sourced definition"


def test_type_extension_does_not_impersonate_foreign_type(tmp_path):
    src = ("module M\n"
           "type System.String with\n"
           "    member this.Shout() = 1\n")
    r = extract_fsharp(_write(tmp_path, "ext.fs", src))
    sourced = {n["label"] for n in r["nodes"] if n.get("source_file")}
    assert "String" not in sourced, "extension minted a sourced foreign-type node"
    # the member still exists, hung off the sourceless stub
    assert ".Shout()" in sourced
    lab = {n["id"]: n for n in r["nodes"]}
    owners = [lab[e["source"]] for e in r["edges"]
              if e["relation"] == "contains" and lab[e["target"]]["label"] == ".Shout()"]
    assert owners and all(o["source_file"] == "" for o in owners)


def test_heritage_edges_emitted(tmp_path):
    src = ("module M\n"
           "type Derived() =\n"
           "    inherit Base()\n"
           "    interface System.IDisposable with\n"
           "        member this.Dispose() = ()\n")
    r = extract_fsharp(_write(tmp_path, "her.fs", src))
    rels = _rel_pairs(r, "inherits") | _rel_pairs(r, "implements")
    assert ("Derived", "Base") in rels
    assert ("Derived", "IDisposable") in rels
    # stubs, not sourced definitions
    sourced = {n["label"] for n in r["nodes"] if n.get("source_file")}
    assert "Base" not in sourced and "IDisposable" not in sourced


def test_object_expression_members_are_anonymous(tmp_path):
    src = ("module M\n"
           "let cleanup () = ()\n"
           "let mk () =\n"
           "    { new System.IDisposable with\n"
           "        member this.Dispose() = cleanup () }\n"
           "let Go x = x\n"
           "let caller y = Go y\n")
    r = extract_fsharp(_write(tmp_path, "obj.fs", src))
    sourced = {n["label"] for n in r["nodes"] if n.get("source_file")}
    assert ".Dispose()" not in sourced, "object-expression member minted as owned member"
    calls = _rel_pairs(r, "calls")
    assert ("mk()", "cleanup()") in calls, calls
    # the real Go binding must not be poisoned into ambiguity
    assert ("caller()", "Go()") in calls, calls


def test_active_pattern_and_operator_are_minted_and_attributed(tmp_path):
    src = ("module M\n"
           "let classify n = n\n"
           "let combine a b = a\n"
           "let (|Even|Odd|) n = classify n\n"
           "let (+.) a b = combine a b\n")
    r = extract_fsharp(_write(tmp_path, "ops.fs", src))
    sourced = {n["label"] for n in r["nodes"] if n.get("source_file")}
    assert "(|Even|Odd|)" in sourced
    assert "(+.)" in sourced
    calls = _rel_pairs(r, "calls")
    assert ("(|Even|Odd|)", "classify()") in calls
    assert ("(+.)", "combine()") in calls
    assert ("M", "classify()") not in calls, "body call attributed to module"


def test_member_val_auto_property_is_emitted(tmp_path):
    src = ("module M\n"
           "type T() =\n"
           "    member val Name = \"x\" with get, set\n"
           "    member this.Go() = 1\n")
    r = extract_fsharp(_write(tmp_path, "mv.fs", src))
    contains = _rel_pairs(r, "contains")
    assert ("T", ".Name()") in contains
    assert ("T", ".Go()") in contains


def test_same_named_bindings_in_sibling_modules_stay_distinct(tmp_path):
    src = ("module Root\n"
           "module A =\n"
           "    let encode x = x\n"
           "    let run x = encode x\n"
           "module B =\n"
           "    let decode y = y\n"
           "    let run y = decode y\n")
    r = extract_fsharp(_write(tmp_path, "sib.fs", src))
    runs = [n for n in r["nodes"] if n["label"] == "run()" and n.get("source_file")]
    assert len(runs) == 2, f"expected 2 run() nodes, got {len(runs)}"


def test_companion_type_and_module_stay_distinct(tmp_path):
    src = ("module Root\n"
           "type Config = { Port: int }\n"
           "module Config =\n"
           "    let create p = p\n")
    r = extract_fsharp(_write(tmp_path, "comp.fs", src))
    configs = [n for n in r["nodes"] if n["label"] == "Config" and n.get("source_file")]
    assert len(configs) == 2, f"companion type/module merged: {len(configs)} node(s)"


def test_open_mirrors_csharp_using(tmp_path):
    src = "module M\nopen System.Text\n"
    r = extract_fsharp(_write(tmp_path, "op.fs", src))
    imports = [e for e in r["edges"] if e["relation"] == "imports"]
    assert imports, "no imports edge for open"
    e = imports[0]
    assert e["confidence"] == "EXTRACTED"
    assert e["metadata"]["target_fqn"] == "System.Text"
    # no minted last-segment stub that could rewire onto an unrelated `Text`
    assert not any(n["label"] == "Text" for n in r["nodes"])


# ── Findings from the round-4 lensed panel ───────────────────────────────────


def test_annotated_single_arg_let_does_not_mint_type(tmp_path):
    # The R2 regression test was proven VACUOUS by mutation: its multi-arg
    # source parses via function_declaration_left, never exercising
    # bound_value_names. A SINGLE-arg annotated let goes down the value path.
    src = "module M\nlet run (mode: string) : int = work mode\n"
    r = extract_fsharp(_write(tmp_path, "sann.fs", src))
    sourced = {n["label"] for n in r["nodes"] if n.get("source_file")}
    assert "int" not in sourced
    assert "run" in sourced or "run()" in sourced


def test_object_expression_references_interface(tmp_path):
    # This edge was DEAD CODE (wrong child type matched) — two arms proved it
    # fired on zero corpus files. Positive assertion pins it.
    src = ("module M\n"
           "let mk () =\n"
           "    { new System.IDisposable with\n"
           "        member this.Dispose() = () }\n")
    r = extract_fsharp(_write(tmp_path, "oref.fs", src))
    assert ("mk()", "IDisposable") in _rel_pairs(r, "references")


def test_generic_heritage_edges_emitted(tmp_path):
    src = ("module M\n"
           "type Child<'T>() =\n"
           "    inherit Base<'T>()\n"
           "    interface System.Collections.Generic.IComparer<'T> with\n"
           "        member this.Compare(a, b) = 0\n")
    r = extract_fsharp(_write(tmp_path, "gher.fs", src))
    assert ("Child", "Base") in _rel_pairs(r, "inherits")
    assert ("Child", "IComparer") in _rel_pairs(r, "implements")
    sourced = {n["label"] for n in r["nodes"] if n.get("source_file")}
    assert "T" not in sourced, "type parameter leaked from generic heritage"


def test_static_let_minted_and_resolvable(tmp_path):
    src = ("module M\n"
           "type C() =\n"
           "    static let build x = shape x\n"
           "    member this.Go() = build 1\n")
    r = extract_fsharp(_write(tmp_path, "slet.fs", src))
    sourced = {n["label"] for n in r["nodes"] if n.get("source_file")}
    assert "build()" in sourced
    calls = _rel_pairs(r, "calls")
    assert ("build()", "shape") in calls, "static-let body call misattributed"
    assert (".Go()", "build()") in calls, "member call did not resolve to local static let"


def test_class_let_and_member_do_not_collide(tmp_path):
    # _make_id case-folds: `let capacity` and `member .Capacity()` merged into
    # one node on the real corpus (RingBuffer.fs lost its public member), and
    # produced a false self-loop elsewhere. Member ids now carry a kind tag.
    src = ("module M\n"
           "type T() =\n"
           "    let run () = 1\n"
           "    member this.Run() = run ()\n")
    r = extract_fsharp(_write(tmp_path, "coll.fs", src))
    sourced = {n["label"] for n in r["nodes"] if n.get("source_file")}
    assert "run()" in sourced and ".Run()" in sourced
    for e in r["edges"]:
        assert e["source"] != e["target"], f"self-loop: {e}"


def test_composition_records_both_callees(tmp_path):
    src = ("module M\n"
           "let f1 x = x\n"
           "let f2 x = x\n"
           "let pipeline = f1 >> f2\n"
           "let rev = f2 << f1\n")
    r = extract_fsharp(_write(tmp_path, "comp.fs", src))
    calls = _rel_pairs(r, "calls")
    assert ("pipeline", "f1()") in calls and ("pipeline", "f2()") in calls
    assert ("rev", "f1()") in calls and ("rev", "f2()") in calls


def test_inherit_argument_calls_recorded(tmp_path):
    src = "module M\ntype Sub() =\n    inherit Base(mkArg ())\n"
    r = extract_fsharp(_write(tmp_path, "iarg.fs", src))
    calls = _rel_pairs(r, "calls")
    assert ("Sub", "mkArg") in calls, calls


def test_local_module_qualified_call_binds_extracted(tmp_path):
    # The POSITIVE half of local_containers — previously only negative tests
    # existed, so deleting the feature survived every test (64 corpus edges
    # silently demoted to stubs).
    src = ("module Root\n"
           "module Config =\n"
           "    let create p = p\n"
           "let boot () = Config.create 1\n")
    r = extract_fsharp(_write(tmp_path, "lq.fs", src))
    lab = {n["id"]: n for n in r["nodes"]}
    hits = [e for e in r["edges"] if e["relation"] == "calls"
            and lab[e["target"]]["label"] == "create()"]
    assert hits, "qualified call through local module did not bind"
    assert all(e["confidence"] == "EXTRACTED" for e in hits)
    assert all(lab[e["target"]].get("source_file") for e in hits)


def test_abstract_members_emitted(tmp_path):
    src = ("module M\n"
           "type IFoo =\n"
           "    abstract member Go: unit -> int\n")
    r = extract_fsharp(_write(tmp_path, "abs.fs", src))
    assert ("IFoo", ".Go()") in _rel_pairs(r, "contains")


def test_partial_active_pattern_label_keeps_wildcard(tmp_path):
    src = "module M\nlet (|Int|_|) (s: string) = tryInt s\n"
    r = extract_fsharp(_write(tmp_path, "pap.fs", src))
    sourced = {n["label"] for n in r["nodes"] if n.get("source_file")}
    assert "(|Int|_|)" in sourced, sourced


def test_heritage_confidence_is_inferred(tmp_path):
    src = "module M\ntype Sub() =\n    inherit Base()\n"
    r = extract_fsharp(_write(tmp_path, "hconf.fs", src))
    her = [e for e in r["edges"] if e["relation"] == "inherits"]
    assert her and all(e["confidence"] == "INFERRED" for e in her)


def test_qualified_call_binds_only_to_owning_container(tmp_path):
    # `B.helper` where module B defines no helper must NOT bind to A's helper
    # just because B is also a local container (found by graphify's own bot,
    # round 6 — missed by all four panel arms).
    src = ("module Root\n"
           "module A =\n"
           "    let helper x = x\n"
           "module B =\n"
           "    let go y = A.helper y\n"
           "    let bad z = B.helper z\n")
    r = extract_fsharp(_write(tmp_path, "own.fs", src))
    lab = {n["id"]: n for n in r["nodes"]}
    calls = [(lab[e["source"]]["label"], lab[e["target"]], e["confidence"])
             for e in r["edges"] if e["relation"] == "calls"]
    good = [(s, t, c) for s, t, c in calls if s == "go()"]
    bad = [(s, t, c) for s, t, c in calls if s == "bad()"]
    assert good and all(t["label"] == "helper()" and t.get("source_file")
                        and c == "EXTRACTED" for s, t, c in good)
    assert bad and all(not t.get("source_file") for s, t, c in bad), (
        "B.helper falsely bound to A's sourced helper")


def test_nested_destructuring_let_mints_all_names(tmp_path):
    src = "module M\nlet (a, (b, c)) = mk ()\n"
    r = extract_fsharp(_write(tmp_path, "nest.fs", src))
    sourced = {n["label"] for n in r["nodes"] if n.get("source_file")}
    assert {"a", "b", "c"} <= sourced
