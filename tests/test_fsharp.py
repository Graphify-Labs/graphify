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
module Acme.Service.Demo

open System.Text
open Acme.Abstractions

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
    # no call edge is emitted at all.
    append_edges = [e for e in r["edges"] if e["relation"] == "calls"
                    and lab[e["target"]]["label"] in ("Append", "sb.Append")]
    assert append_edges, "no call edge emitted for sb.Append at all"
    for e in append_edges:
        # must NOT resolve to the local definition (which has a source_file)
        assert lab[e["target"]]["source_file"] == "", (
            "external qualified call bound to a local definition")
        # ...nor to a bare `Append` stub, which the corpus rewire would
        # collapse onto that same local definition.
        assert lab[e["target"]]["label"] == "sb.Append"


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
    # would merge them into a single node.
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
    # rewire.
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
    # `Acme.Telemetry.init args` parses as application > dot_expression; the
    # callee must be recorded as a full-path stub, not silently skipped.
    src = "module M\nlet go args =\n    Acme.Telemetry.init args\n"
    r = extract_fsharp(_write(tmp_path, "dot.fs", src))
    calls = _rel_pairs(r, "calls")
    assert ("go()", "Acme.Telemetry.init") in calls or ("go()", "init") in calls, calls


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
    src_a = "namespace Acme.Core\ntype A() = member this.Go() = 1\n"
    src_b = "namespace Acme.Core\ntype B() = member this.Ho() = 2\n"
    ra = extract_fsharp(_write(tmp_path, "a.fs", src_a))
    rb = extract_fsharp(_write(tmp_path, "b.fs", src_b))
    ns_a = [n for n in ra["nodes"] if n.get("type") == "namespace"]
    ns_b = [n for n in rb["nodes"] if n.get("type") == "namespace"]
    assert ns_a and ns_b
    assert ns_a[0]["id"] == ns_b[0]["id"], "namespace id must be canonical across files"
    assert ns_a[0]["id"].startswith("csharp_namespace:")
    assert ns_a[0]["label"] == "Acme.Core"


def test_namespace_segment_does_not_bind_local(tmp_path):
    # Under `namespace Acme.Service`, the call `Service.validate c` must stay
    # a stub — the namespace is corpus-wide, not a local qualifier.
    src = ("namespace Acme.Service\n"
           "module Impl =\n"
           "    let validate c = c\n"
           "    let go c = Service.validate c\n")
    r = extract_fsharp(_write(tmp_path, "ns.fs", src))
    lab = {n["id"]: n for n in r["nodes"]}
    vcalls = [e for e in r["edges"] if e["relation"] == "calls"
              and lab[e["target"]]["label"] in ("validate", "validate()",
                                                "Service.validate")]
    assert vcalls, "no call edge for Service.validate at all"
    for e in vcalls:
        assert not lab[e["target"]].get("source_file"), (
            "namespace-rooted call falsely bound to local definition")


# ── Generic types, type extensions, heritage, object expressions, ids ────────


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


# ── Value-path annotations, static let, composition, qualified calls ─────────


def test_annotated_single_arg_let_does_not_mint_type(tmp_path):
    # The multi-arg annotated-let test above parses via
    # function_declaration_left and never reaches bound_value_names. A
    # SINGLE-arg annotated let goes down the value path.
    src = "module M\nlet run (mode: string) : int = work mode\n"
    r = extract_fsharp(_write(tmp_path, "sann.fs", src))
    sourced = {n["label"] for n in r["nodes"] if n.get("source_file")}
    assert "int" not in sourced
    assert "run" in sourced or "run()" in sourced


def test_object_expression_references_interface(tmp_path):
    # Positive assertion: the edge is easy to lose silently if the interface
    # child type is matched wrongly.
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
    # _make_id case-folds: without a kind tag in member ids, `let run` and
    # `member this.Run` merge into one node, losing the public member and
    # creating a false self-loop.
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
    # The POSITIVE half of container-scoped binding: without it, deleting the
    # feature (every qualified local call demoted to a stub) passes every
    # negative test.
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
    # just because B is also a local container.
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
    # The stub must carry the FULL path: a bare `helper` stub is sourceless
    # too, but the corpus rewire could still collapse it onto A's helper.
    assert [t["label"] for s, t, c in bad] == ["B.helper"]


def test_nested_destructuring_let_mints_all_names(tmp_path):
    src = "module M\nlet (a, (b, c)) = mk ()\n"
    r = extract_fsharp(_write(tmp_path, "nest.fs", src))
    sourced = {n["label"] for n in r["nodes"] if n.get("source_file")}
    assert {"a", "b", "c"} <= sourced


# ── Application to the right of an infix operator ────────────────────────────
# tree-sitter-fsharp parses `a OP f x` as `(a OP f) x` for every infix operator
# except && and ||; the extractor re-associates so the call to f is recorded.


def _call_targets(r, caller: str) -> list[str]:
    lab = {n["id"]: n["label"] for n in r["nodes"]}
    return sorted(lab[e["target"]] for e in r["edges"]
                  if e["relation"] == "calls" and lab[e["source"]] == caller)


def test_call_right_of_cons_is_recorded(tmp_path):
    src = ("module M\n"
           "let rec loop xs =\n"
           "    match xs with\n"
           "    | [] -> []\n"
           "    | x :: rest -> x :: loop rest\n")
    r = extract_fsharp(_write(tmp_path, "cons.fs", src))
    assert _call_targets(r, "loop()") == ["loop()"]


def test_call_right_of_arithmetic_and_comparison_is_recorded(tmp_path):
    src = ("module M\n"
           "let compute y = y\n"
           "let parse s = s\n"
           "let total acc y = acc + compute y\n"
           "let same x s = x = parse s\n")
    r = extract_fsharp(_write(tmp_path, "arith.fs", src))
    assert _call_targets(r, "total()") == ["compute()"]
    assert _call_targets(r, "same()") == ["parse()"]


def test_call_right_of_nested_infix_is_recorded(tmp_path):
    src = "module M\nlet rate y = y\nlet h a b y = a + b * rate y\n"
    r = extract_fsharp(_write(tmp_path, "nested.fs", src))
    assert _call_targets(r, "h()") == ["rate()"]


def test_pipe_with_partial_application_records_one_edge(tmp_path):
    # `x |> f a` also parses as `(x |> f) a`; the pipe rule already records f,
    # so the re-association must not add a second edge for the same call site.
    src = "module M\nlet f a b = a\nlet h x = x |> f 1\n"
    r = extract_fsharp(_write(tmp_path, "pipe1.fs", src))
    assert _call_targets(r, "h()") == ["f()"]


def test_composition_with_partial_application_records_one_edge_each(tmp_path):
    # `g >> f 1` parses as `(g >> f) 1`; the composition rule already records
    # both g and f, so f must not gain a second edge.
    src = "module M\nlet f a b = a\nlet g x = x\nlet h = g >> f 1\n"
    r = extract_fsharp(_write(tmp_path, "comp1.fs", src))
    assert _call_targets(r, "h") == ["f()", "g()"]


def test_backpipe_records_both_applied_functions(tmp_path):
    # `g <| f x`: g receives the result of `f x`, so both are calls.
    src = "module M\nlet f x = x\nlet g y = y\nlet h x = g <| f x\n"
    r = extract_fsharp(_write(tmp_path, "back2.fs", src))
    assert _call_targets(r, "h()") == ["f()", "g()"]


def test_address_of_argument_calls_the_function_not_the_byref(tmp_path):
    # `g &v 1` parses as `(g & v) 1`: g is called; v is only passed by ref.
    src = ("module M\n"
           "let g (p: byref<int>) n = n\n"
           "let h () =\n"
           "    let mutable v = 0\n"
           "    g &v 1\n"
           "let k () =\n"
           "    let mutable v = 0\n"
           "    g &v\n")
    r = extract_fsharp(_write(tmp_path, "addr.fs", src))
    assert _call_targets(r, "h()") == ["g()"]
    assert _call_targets(r, "k()") == ["g()"]


def test_index_read_is_not_a_call(tmp_path):
    # `xs[i]` (F# 6 index syntax) parses as an application of xs to `[i]`.
    # xs is a module-level value, so no shadowing rule can hide the call.
    src = "module M\nlet xs = [| 1; 2 |]\nlet h i = xs[i]\n"
    r = extract_fsharp(_write(tmp_path, "idx.fs", src))
    assert _call_targets(r, "h()") == []


def test_index_read_right_of_infix_is_not_a_call(tmp_path):
    # `a[i] + b[i]` parses as `(a[i] + b)[i]`: neither a nor b is called.
    src = "module M\nlet a = [| 1 |]\nlet b = [| 2 |]\nlet h i = a[i] + b[i]\n"
    r = extract_fsharp(_write(tmp_path, "idx2.fs", src))
    assert _call_targets(r, "h()") == []


def test_qualified_index_read_on_assignment_is_not_a_call(tmp_path):
    src = ("module M\n"
           "let copy (fields: int[]) (args: Args) i =\n"
           "    fields[i] <- args.Payload[i]\n")
    r = extract_fsharp(_write(tmp_path, "idx3.fs", src))
    assert _call_targets(r, "copy()") == []


def test_application_to_a_list_literal_is_a_call(tmp_path):
    # With a space, `f [1; 2]` applies f to a list.
    src = "module M\nlet f xs = xs\nlet h () = f [1; 2]\nlet g acc = acc @ f [3]\n"
    r = extract_fsharp(_write(tmp_path, "lst.fs", src))
    assert _call_targets(r, "h()") == ["f()"]
    assert _call_targets(r, "g()") == ["f()"]


# ── Patterns, scopes, qualification, case ────────────────────────────────────


def _sourced(r) -> list[str]:
    return sorted(n["label"] for n in r["nodes"] if n.get("source_file"))


def test_constructor_pattern_binds_its_argument_not_the_case(tmp_path):
    r = extract_fsharp(_write(tmp_path, "cp.fs", "module M\nlet (Some value) = Some 42\n"))
    assert "value" in _sourced(r)
    assert "Some" not in _sourced(r)


def test_list_and_record_patterns_bind_their_names(tmp_path):
    src = ("module M\n"
           "type R = { X: int; Y: int }\n"
           "let [a; b] = [1; 2]\n"
           "let { X = c; Y = d } = { X = 1; Y = 2 }\n")
    sourced = _sourced(extract_fsharp(_write(tmp_path, "lp.fs", src)))
    assert {"a", "b", "c", "d"} <= set(sourced)
    assert sourced.count("X") == 0 and sourced.count("Y") == 0


def test_parameter_shadows_module_function(tmp_path):
    src = "module M\nlet f x = x + 1\nlet apply f = f 42\n"
    assert _call_targets(extract_fsharp(_write(tmp_path, "sp.fs", src)), "apply()") == []


def test_local_let_shadows_module_function(tmp_path):
    src = ("module M\nlet f x = x + 1\n"
           "let apply x =\n    let f y = y * 2\n    f x\n")
    assert _call_targets(extract_fsharp(_write(tmp_path, "sl.fs", src)), "apply()") == []


def test_lambda_match_and_for_binders_shadow(tmp_path):
    src = ("module M\nlet f x = x\n"
           "let a xs = List.iter (fun f -> f 1) xs\n"
           "let b o =\n    match o with\n    | Some f -> f 1\n    | None -> 0\n"
           "let c fs =\n    for f in fs do\n        f 1\n")
    r = extract_fsharp(_write(tmp_path, "sb.fs", src))
    assert "f()" not in _call_targets(r, "a()")
    assert _call_targets(r, "b()") == []
    assert _call_targets(r, "c()") == []


def test_unshadowed_call_still_binds(tmp_path):
    # Control for the shadowing tests: a binder named differently does not hide f.
    src = "module M\nlet f x = x + 1\nlet apply g = f (g 42)\n"
    assert _call_targets(extract_fsharp(_write(tmp_path, "us.fs", src)), "apply()") == ["f()"]


def test_nested_qualifier_resolves_through_the_full_path(tmp_path):
    src = ("module Root\n"
           "module A =\n    let f x = x + 1\n"
           "    module B =\n        let f x = x * 2\n"
           "let h x = A.B.f x\n")
    r = extract_fsharp(_write(tmp_path, "nq.fs", src))
    by = {n["id"]: n for n in r["nodes"]}
    [e] = [e for e in r["edges"] if e["relation"] == "calls"]
    assert by[e["target"]]["source_location"] == "L5"


def test_ambiguous_qualifier_binds_nothing_locally(tmp_path):
    # A type and a module at the same path both own `create`: neither may be
    # chosen, and the stub must not be rewired to anything elsewhere.
    src = ("module Root\n"
           "type Config() =\n    static member create () = 1\n"
           "module Config =\n    let create () = 2\n"
           "let h () = Config.create ()\n")
    r = extract_fsharp(_write(tmp_path, "amb.fs", src))
    by = {n["id"]: n for n in r["nodes"]}
    [e] = [e for e in r["edges"] if e["relation"] == "calls"]
    assert not by[e["target"]].get("source_file")
    assert by[e["target"]]["label"] == "Config.create"
    assert "metadata" not in by[e["target"]], "a local ambiguity must not rewire elsewhere"


def test_inaccessible_nested_module_is_not_what_a_bare_qualifier_names(tmp_path):
    # `List.map` at Root is FSharp.Core's List, not the nested Other.List.
    src = ("module Root\n"
           "module Other =\n    module List =\n        let map x = x + 1\n"
           "let h xs = List.map id xs\n")
    r = extract_fsharp(_write(tmp_path, "inacc.fs", src))
    by = {n["id"]: n for n in r["nodes"]}
    [e] = [e for e in r["edges"] if e["relation"] == "calls"]
    assert not by[e["target"]].get("source_file")
    assert by[e["target"]]["label"] == "List.map"


def test_sibling_container_resolves_from_the_enclosing_scope(tmp_path):
    # Inside B, `X.f` is B.X.f (the nearest scope), not A.X.f.
    src = ("module Root\n"
           "module A =\n    module X =\n        let f () = 1\n"
           "module B =\n    module X =\n        let f () = 2\n"
           "    let h () = X.f ()\n")
    r = extract_fsharp(_write(tmp_path, "sib2.fs", src))
    by = {n["id"]: n for n in r["nodes"]}
    [e] = [e for e in r["edges"] if e["relation"] == "calls"]
    assert by[e["target"]]["source_location"] == "L7"


def test_open_scopes_a_qualified_call_in_the_same_file(tmp_path):
    src = ("module Root\n"
           "module Outer =\n    module Lib =\n        let map x = x\n"
           "open Outer\n"
           "let h x = Lib.map x\n")
    r = extract_fsharp(_write(tmp_path, "open1.fs", src))
    by = {n["id"]: n for n in r["nodes"]}
    [e] = [e for e in r["edges"] if e["relation"] == "calls"]
    assert by[e["target"]]["source_location"] == "L4"


def test_self_member_call_binds_to_the_enclosing_type(tmp_path):
    src = ("module M\n"
           "type Placement = { Offset: int }\n"
           "type Fixture() =\n"
           "    member this.Placement (n: int) = { Offset = n }\n"
           "    member this.Row n = this.Placement n\n"
           "    member this.Other n = this.Missing n\n")
    r = extract_fsharp(_write(tmp_path, "self.fs", src))
    by = {n["id"]: n for n in r["nodes"]}
    row = [by[e["target"]] for e in r["edges"]
           if e["relation"] == "calls" and by[e["source"]]["label"] == ".Row()"]
    assert [(n["label"], n["source_location"]) for n in row] == [(".Placement()", "L4")]
    other = [by[e["target"]] for e in r["edges"]
             if e["relation"] == "calls" and by[e["source"]]["label"] == ".Other()"]
    assert [(n["label"], n.get("source_file"), "metadata" in n) for n in other] == [("this.Missing", "", False)]


def test_rebound_receiver_is_not_the_enclosing_type(tmp_path):
    src = ("module M\n"
           "type Other() =\n    member _.Go n = n + 1\n"
           "type C() =\n    member _.Go n = n * 2\n"
           "    member this.Run () =\n"
           "        let this = Other()\n"
           "        this.Go 42\n")
    r = extract_fsharp(_write(tmp_path, "rebind.fs", src))
    by = {n["id"]: n for n in r["nodes"]}
    gos = [by[e["target"]] for e in r["edges"] if e["relation"] == "calls"
           and by[e["source"]]["label"] == ".Run()" and "Go" in by[e["target"]]["label"]]
    assert all(not n.get("source_file") for n in gos), gos


def test_as_pattern_alias_binds_and_shadows(tmp_path):
    src = ("module M\nlet f x = x + 1\nlet g x = x * 2\n"
           "let h (f as g) = g 42\n"
           "let (a as b) = 1\n")
    r = extract_fsharp(_write(tmp_path, "as.fs", src))
    assert _call_targets(r, "h()") == []
    assert {"a", "b"} <= set(_sourced(r))


def test_nonrecursive_local_let_does_not_shadow_its_initializer(tmp_path):
    src = ("module M\nlet f x = x + 1\n"
           "let h () =\n    let f = f 42\n    f\n"
           "let k () =\n    let rec f y = f y\n    f 1\n")
    r = extract_fsharp(_write(tmp_path, "nonrec.fs", src))
    assert _call_targets(r, "h()") == ["f()"]   # the initializer calls the outer f
    assert _call_targets(r, "k()") == []         # let rec: f is the local one


def test_prime_and_backtick_names_stay_distinct(tmp_path):
    src = ("module M\nlet f x = x + 1\nlet f' x = x * 2\nlet h x = f' x\n"
           "let ``a-b`` x = x\nlet a_b x = x\nlet k x = a_b x\n")
    r = extract_fsharp(_write(tmp_path, "prime.fs", src))
    assert {"f()", "f'()", "a_b()"} <= set(_sourced(r))
    assert _call_targets(r, "h()") == ["f'()"]
    assert _call_targets(r, "k()") == ["a_b()"]


def test_return_annotated_head_is_a_function_whose_parameters_shadow(tmp_path):
    # tree-sitter-fsharp parses a return-annotated head as a VALUE head when it
    # is the last binding in the file (and as a function head when another
    # binding follows), so each case is the last binding of its own file.
    for name, src in (("ann_h.fs", "module M\nlet g x = x + 1\nlet h (g: int -> int) : int = g 42\n"),
                      ("ann_t.fs", "module M\nlet g x = x + 1\nlet h (g, x) : int = g x\n")):
        r = extract_fsharp(_write(tmp_path, name, src))
        assert "h()" in _sourced(r), name
        assert _call_targets(r, "h()") == [], name


def test_module_level_non_recursive_definition_calls_the_outer_name(tmp_path):
    # Inside a non-rec `let f x = f x`, f is the OUTER f, not itself.
    src = ("module M\nlet f x = x + 1\n"
           "module Inner =\n    let f x = f x\n")
    r = extract_fsharp(_write(tmp_path, "outer.fs", src))
    by = {n["id"]: n for n in r["nodes"]}
    inner = [e for e in r["edges"] if e["relation"] == "calls"
             and by[e["source"]]["source_location"] == "L4"]
    assert [by[e["target"]]["source_location"] for e in inner] == ["L2"]


def test_property_setter_parameter_shadows(tmp_path):
    src = ("module M\nlet value x = x + 1\n"
           "type C() =\n    member _.Setter\n"
           "        with set (value: int -> int) = value 42 |> ignore\n")
    r = extract_fsharp(_write(tmp_path, "setter.fs", src))
    assert "value()" not in _call_targets(r, ".Setter()")


def test_later_open_shadows_an_earlier_module(tmp_path):
    src = ("module Root\n"
           "module Lib =\n    let f () = 1\n"
           "module One =\n    module Lib =\n        let f () = 2\n"
           "open One\n"
           "let h () = Lib.f ()\n")
    r = extract_fsharp(_write(tmp_path, "shadow_open.fs", src))
    by = {n["id"]: n for n in r["nodes"]}
    [e] = [e for e in r["edges"] if e["relation"] == "calls"]
    assert by[e["target"]]["source_location"] == "L6"


def test_inner_open_outranks_an_outer_open(tmp_path):
    src = ("module Root\n"
           "module One =\n    module Lib =\n        let f () = 1\n"
           "module Two =\n    module Lib =\n        let f () = 2\n"
           "open One\n"
           "module Inner =\n    open Two\n    let h () = Lib.f ()\n")
    r = extract_fsharp(_write(tmp_path, "inner_open.fs", src))
    by = {n["id"]: n for n in r["nodes"]}
    [e] = [e for e in r["edges"] if e["relation"] == "calls"]
    assert by[e["target"]]["source_location"] == "L7"


def test_open_resolves_relative_to_its_own_scope(tmp_path):
    src = ("module Root\n"
           "module One =\n    module Lib =\n        let f () = 1\n"
           "module Inner =\n    module One =\n        module Lib =\n            let f () = 2\n"
           "    open One\n    let h () = Lib.f ()\n")
    r = extract_fsharp(_write(tmp_path, "rel_open.fs", src))
    by = {n["id"]: n for n in r["nodes"]}
    [e] = [e for e in r["edges"] if e["relation"] == "calls"]
    assert by[e["target"]]["source_location"] == "L8"


def test_unopened_module_member_is_not_visible_unqualified(tmp_path):
    src = "module Root\nmodule Other =\n    let ignore x = x + 1\nlet h x = ignore x\n"
    r = extract_fsharp(_write(tmp_path, "unopened.fs", src))
    by = {n["id"]: n for n in r["nodes"]}
    [e] = [e for e in r["edges"] if e["relation"] == "calls"]
    assert not by[e["target"]].get("source_file")


def test_forward_reference_is_not_visible(tmp_path):
    src = ("module Root\nlet h x = ignore x\nlet ignore x = x + 1\n"
           "let k xs = List.map id xs\nmodule List =\n    let map x = x + 1\n")
    r = extract_fsharp(_write(tmp_path, "forward.fs", src))
    by = {n["id"]: n for n in r["nodes"]}
    for caller in ("h()", "k()"):
        [e] = [e for e in r["edges"] if e["relation"] == "calls" and by[e["source"]]["label"] == caller]
        assert not by[e["target"]].get("source_file"), caller


def test_module_rec_makes_later_definitions_visible(tmp_path):
    src = "module rec M\nlet h x = g x\nlet g x = x\n"
    assert _call_targets(extract_fsharp(_write(tmp_path, "modrec.fs", src)), "h()") == ["g()"]


def test_class_let_value_is_a_receiver_not_a_module(tmp_path):
    src = ("module Root\n"
           "module Lib =\n    let Map x = x + 1\n"
           "type Other() =\n    member _.Map x = x * 2\n"
           "type C() =\n    let Lib = Other()\n    member _.Run () = Lib.Map 21\n")
    r = extract_fsharp(_write(tmp_path, "classlet.fs", src))
    by = {n["id"]: n for n in r["nodes"]}
    runs = [by[e["target"]] for e in r["edges"] if e["relation"] == "calls"
            and by[e["source"]]["label"] == ".Run()"]
    assert [(n["label"], n.get("source_file"), "metadata" in n) for n in runs] == [("Lib.Map", "", False)]


def test_module_value_receiver_does_not_rewire_to_a_module(tmp_path):
    calls = _extract_files(tmp_path, {
        "lib.fs": "module Lib\nlet Map x = x + 1\n",
        "app.fs": "module App\ntype C() =\n    member _.Map x = x * 2\n"
                  "let Lib = C()\nlet h () = Lib.Map 21\n"})
    assert ("h()", "Map()", "lib.fs") not in calls, calls


def test_nearest_open_decides_across_files(tmp_path):
    calls = _extract_files(tmp_path, {
        "one.fs": "namespace One\nmodule Lib =\n    let f () = 1\n",
        "two.fs": "namespace Two\nmodule Lib =\n    let f () = 2\n",
        "app.fs": "module App\nopen One\nopen Two\nlet h () = Lib.f ()\n"})
    assert ("h()", "f()", "two.fs") in calls, calls


def test_foreign_open_nearer_than_a_local_module_is_not_certain(tmp_path):
    calls = _extract_files(tmp_path, {
        "lib.fs": "namespace External\nmodule Lib =\n    let f () = 2\n",
        "app.fs": "module App\nmodule Lib =\n    let f () = 1\nopen External\nlet h () = Lib.f ()\n"})
    assert ("h()", "f()", "lib.fs") in calls, calls
    assert ("h()", "f()", "app.fs") not in calls, calls


def test_rejected_same_file_definition_is_not_bound_by_the_corpus_rewire(tmp_path):
    # The extractor rejects the later `ignore` and `List.map` (not yet
    # declared); the corpus rewire must not bind them either.
    calls = _extract_files(tmp_path, {
        "fwd.fs": ("module Root\nlet h x = ignore x\nlet ignore x = x + 1\n"
                   "let k xs = List.map id xs\nmodule List =\n    let map x = x + 1\n")})
    assert all(target_file == "-" for caller, _, target_file in calls
               if caller in ("h()", "k()")), calls


def test_cross_file_binding_compares_exact_names(tmp_path):
    # `One` declares f', not f, so `open One` does not shadow Two.f.
    calls = _extract_files(tmp_path, {
        "one.fs": "module One\nlet f' x = x + 1\n",
        "two.fs": "module Two\nlet f x = x * 2\n",
        "app.fs": "module App\nopen Two\nopen One\nlet h () = f 21\n"})
    assert ("h()", "f()", "two.fs") in calls, calls
    assert ("h()", "f'()", "one.fs") not in calls, calls


def test_open_is_resolved_through_earlier_opens(tmp_path):
    # `open A` brings A.Lib into scope, so the following `open Lib` opens A.Lib.
    src = ("module Root\n"
           "module Lib =\n    let f () = 1\n"
           "module A =\n    module Lib =\n        let f () = 2\n"
           "open A\nopen Lib\nlet h () = f ()\n")
    r = extract_fsharp(_write(tmp_path, "oo.fs", src))
    by = {n["id"]: n for n in r["nodes"]}
    [e] = [e for e in r["edges"] if e["relation"] == "calls"]
    assert by[e["target"]]["source_location"] == "L6"


def test_open_cannot_reach_a_module_declared_after_it(tmp_path):
    src = ("module Root\n"
           "module One =\n    let f () = 1\n"
           "module Inner =\n    open One\n    let h () = f ()\n"
           "    module One =\n        let f () = 2\n")
    r = extract_fsharp(_write(tmp_path, "of.fs", src))
    by = {n["id"]: n for n in r["nodes"]}
    [e] = [e for e in r["edges"] if e["relation"] == "calls"]
    assert by[e["target"]]["source_location"] == "L3"


def test_foreign_open_after_a_value_does_not_make_it_a_module(tmp_path):
    calls = _extract_files(tmp_path, {
        "lib.fs": "module Lib\nlet Map x = x + 1\n",
        "app.fs": "module App\ntype C() =\n    member _.Map x = x * 2\n"
                  "let Lib = C()\nopen System\nlet h () = Lib.Map 21\n"})
    assert ("h()", "Map()", "lib.fs") not in calls, calls


def test_value_imported_through_an_open_stops_module_lookup(tmp_path):
    calls = _extract_files(tmp_path, {
        "lib.fs": "module Lib\nlet Map x = x + 1\n",
        "values.fs": "module Values\ntype C() =\n    member _.Map x = x * 2\nlet Lib = C()\n",
        "app.fs": "module App\nopen Values\nlet h () = Lib.Map 21\n"})
    assert ("h()", "Map()", "lib.fs") not in calls, calls


def test_local_module_behind_a_foreign_open_is_the_fallback(tmp_path):
    calls = _extract_files(tmp_path, {
        "app.fs": "module App\nmodule Lib =\n    let f () = 1\nopen System\nlet h () = Lib.f ()\n"})
    assert ("h()", "f()", "app.fs") in calls, calls


def test_return_annotated_member_parameters_shadow(tmp_path):
    src = ("module Root\nlet f x = x + 1\n"
           "type C() =\n"
           "    member _.H (f: int -> int) : int = f 21\n"
           "    member _.T (f: int -> int, x: int) : int = f x\n")
    r = extract_fsharp(_write(tmp_path, "mret.fs", src))
    assert _call_targets(r, ".H()") == []
    assert _call_targets(r, ".T()") == []


def test_and_bang_binders_shadow_the_continuation(tmp_path):
    src = ("module Root\nlet f x = x + 1\nlet g x = x\n"
           "let h () =\n"
           "    task {\n"
           "        let! x = T.FromResult (g 21)\n"
           "        and! f = T.FromResult 2\n"
           "        return f x\n"
           "    }\n")
    r = extract_fsharp(_write(tmp_path, "andbang.fs", src))
    targets = _call_targets(r, "h()")
    assert "f()" not in targets, targets   # `f x` is the and! binding
    assert "g()" in targets, targets       # an initializer still sees the outer g


def test_open_type_never_restores_a_shadowed_local_function(tmp_path):
    calls = _extract_files(tmp_path, {
        "app.fs": "module Root\nlet Abs x = x + 1\nopen type System.Math\nlet h () = Abs -42\n"})
    assert ("h()", "Abs()", "app.fs") not in calls, calls


def test_unqualified_call_binds_only_into_an_opened_module(tmp_path):
    calls = _extract_files(tmp_path, {
        "lib.fs": "module Lib\nlet map x = x + 1\n",
        "app.fs": "module App\nopen Lib\nlet h x = map x\n",
        "app2.fs": "module App2\nlet k x = map x\n"})
    assert ("h()", "map()", "lib.fs") in calls, calls
    assert ("k()", "map()", "lib.fs") not in calls, calls


def test_names_differing_only_in_case_stay_distinct(tmp_path):
    src = "module M\nlet run x = x + 1\nlet Run x = x * 2\nlet h x = Run x\n"
    r = extract_fsharp(_write(tmp_path, "case.fs", src))
    assert {"run()", "Run()"} <= set(_sourced(r))
    assert _call_targets(r, "h()") == ["Run()"]


def test_pipe_into_indexed_value_is_not_a_call(tmp_path):
    src = "module M\nlet fs = [| fun (x: int) -> x |]\nlet h x = x |> fs[0]\n"
    assert _call_targets(extract_fsharp(_write(tmp_path, "pix.fs", src)), "h()") == []


def test_adjacent_array_argument_is_a_call(tmp_path):
    src = "module M\nlet f (xs: int[]) = xs.Length\nlet h () = f[|1; 2|]\n"
    assert _call_targets(extract_fsharp(_write(tmp_path, "arr.fs", src)), "h()") == ["f()"]


def test_adjacent_list_argument_to_a_local_function_is_a_call(tmp_path):
    src = "module M\nlet f (xs: int list) = xs.Length\nlet h () = f[1; 2]\n"
    assert _call_targets(extract_fsharp(_write(tmp_path, "adj.fs", src)), "h()") == ["f()"]


def test_address_of_a_module_level_mutable_is_not_a_call(tmp_path):
    # The byref operand is a module-level value, so no shadowing hides it:
    # `g &cell 1` calls g, never cell.
    src = ("module M\nlet mutable cell = 0\n"
           "let g (p: byref<int>) n = n\n"
           "let h () = g &cell 1\n")
    assert _call_targets(extract_fsharp(_write(tmp_path, "am.fs", src)), "h()") == ["g()"]


def test_space_before_list_argument_is_always_a_call(tmp_path):
    # Non-local callees: only adjacency makes `name[...]` an index read.
    src = "module M\nlet h () = external [1; 2]\nlet k () = List.head [1; 2]\n"
    r = extract_fsharp(_write(tmp_path, "sp2.fs", src))
    assert _call_targets(r, "h()") == ["external"]
    assert _call_targets(r, "k()") == ["List.head"]


def test_adjacent_array_argument_to_a_foreign_function_is_a_call(tmp_path):
    src = "module M\nlet h () = Array.sum[|1; 2|]\n"
    assert _call_targets(extract_fsharp(_write(tmp_path, "arr2.fs", src)), "h()") == ["Array.sum"]


def test_address_of_after_infix_calls_the_function(tmp_path):
    src = ("module M\nlet g (a: byref<int>) = a\n"
           "let h () =\n    let mutable a = 1\n    1 + g &a\n")
    assert _call_targets(extract_fsharp(_write(tmp_path, "ai.fs", src)), "h()") == ["g()"]


def test_native_address_of_calls_the_function(tmp_path):
    src = ("module M\nlet g (p: nativeptr<int>) = 1\n"
           "let h () =\n    let mutable v = 0\n    g &&v\n"
           "let ok = true\nlet k b = ok && g b\n")
    r = extract_fsharp(_write(tmp_path, "an.fs", src))
    assert _call_targets(r, "h()") == ["g()"]
    assert _call_targets(r, "k()") == ["g()"]  # boolean && still records g


def _extract_files(tmp_path, files: dict):
    from graphify.extract import extract
    paths = []
    for name, src in files.items():
        (tmp_path / name).write_text(src, encoding="utf-8")
        paths.append(tmp_path / name)
    r = extract(paths, root=tmp_path, max_workers=1, cache_root=tmp_path / "cache")
    by = {n["id"]: n for n in r["nodes"]}
    return {(by[e["source"]]["label"], by[e["target"]]["label"],
             Path(by[e["target"]].get("source_file") or "-").name)
            for e in r["edges"] if e["relation"] == "calls"
            and e["source"] in by and e["target"] in by}


def test_unopened_namespace_module_is_not_a_bare_qualifier(tmp_path):
    calls = _extract_files(tmp_path, {
        "lib.fs": "namespace Unrelated\nmodule List =\n    let map x = x + 1\n",
        "app.fs": "module App\nlet h xs = List.map id xs\n",
        "app2.fs": "module App2\nopen Unrelated\nlet k x = List.map x\n"})
    assert ("h()", "List.map", "-") in calls, calls     # not opened: FSharp.Core's List
    assert ("k()", "map()", "lib.fs") in calls, calls  # opened: Unrelated.List


def test_same_named_modules_resolve_through_the_open(tmp_path):
    calls = _extract_files(tmp_path, {
        "one.fs": "namespace One\nmodule Lib =\n    let map x = x + 1\n",
        "two.fs": "namespace Two\nmodule Lib =\n    let map x = x * 2\n",
        "app.fs": "module App\nopen One\nlet h x = Lib.map x\n"})
    assert ("h()", "map()", "one.fs") in calls, calls


def test_receiver_and_module_calls_do_not_share_a_stub(tmp_path):
    lib = "module Lib\nlet Map x = x + 1\n"
    for order in ("k-first", "h-first"):
        k = "let k x = Lib.Map x\n"
        h = "let h (Lib: C) = Lib.Map 1\n"
        app = ("module App\ntype C() =\n    member _.Map x = x * 2\n"
               + (k + h if order == "k-first" else h + k))
        calls = _extract_files(tmp_path / order, {"lib.fs": lib, "app.fs": app}) \
            if (tmp_path / order).mkdir() is None else set()
        assert ("k()", "Map()", "lib.fs") in calls, (order, calls)
        assert ("h()", "Map()", "lib.fs") not in calls, (order, calls)


def test_csharp_nested_type_is_not_named_by_its_namespace(tmp_path):
    calls = _extract_files(tmp_path, {
        "lib.cs": "namespace Acme { public class Outer { public class Widget {} } }\n",
        "app.fs": "module App\nlet wrong () = Acme.Widget()\n"})
    assert ("wrong()", "Widget", "lib.cs") not in calls, calls


def test_qualified_call_binds_only_inside_the_named_module_across_files(tmp_path):
    from graphify.extract import extract
    (tmp_path / "lib.fs").write_text("module Lib\nlet map x = x + 1\n", encoding="utf-8")
    (tmp_path / "app.fs").write_text(
        "module App\nlet h xs = List.map id xs\nlet k x = Lib.map x\n", encoding="utf-8")
    r = extract([tmp_path / "lib.fs", tmp_path / "app.fs"], root=tmp_path,
                max_workers=1, cache_root=tmp_path / "cache")
    by = {n["id"]: n for n in r["nodes"]}
    calls = {(by[e["source"]]["label"], by[e["target"]]["label"], bool(by[e["target"]].get("source_file")))
             for e in r["edges"] if e["relation"] == "calls"}
    assert ("h()", "List.map", False) in calls, calls   # List.map never reaches Lib.map
    assert ("k()", "map()", True) in calls, calls       # Lib.map does


# ── Coverage oracle: one case per F# construct ───────────────────────────────
# The inventory lives in tests/fsharp_coverage_oracle.py (also runnable as a
# script); running it here puts every construct under CI.

from tests.fsharp_coverage_oracle import CONSTRUCTS, run_one  # noqa: E402


@pytest.mark.parametrize("entry", CONSTRUCTS, ids=[c[0] for c in CONSTRUCTS])
def test_coverage_oracle_construct(entry):
    name, src, want_labels, want_edges = entry[:4]
    forbidden = entry[4] if len(entry) > 4 else None
    problems = run_one(name, src, want_labels, want_edges, forbidden)
    assert not problems, f"{name}: {problems}"
