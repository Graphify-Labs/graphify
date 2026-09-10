#!/usr/bin/env python3
"""Coverage oracle for the F# extractor.

Run directly (not pytest-collected): [OK  ] let function
[OK  ] let value
[OK  ] annotated let
[OK  ] annotated single-arg let
[OK  ] destructuring let
[OK  ] let rec and
[OK  ] nested let scoping
[OK  ] active pattern total
[OK  ] active pattern partial
[OK  ] operator def
[OK  ] record type
[OK  ] union type + cases
[OK  ] enum members
[OK  ] generic type
[OK  ] constrained generic
[OK  ] type abbreviation
[OK  ] struct type
[OK  ] interface type
[OK  ] delegate type
[OK  ] mutually recursive types
[OK  ] class + member
[OK  ] static member
[OK  ] member val
[OK  ] abstract/override
[OK  ] inherit
[OK  ] interface impl
[OK  ] type extension member
[OK  ] object expression
[OK  ] exception
[OK  ] open
[OK  ] nested module
[OK  ] namespace + module
[OK  ] pipe right
[OK  ] pipe left
[OK  ] pipe2 right
[OK  ] composition >>
[OK  ] composition <<
[OK  ] static let in class
[OK  ] local module qualified call
[OK  ] class let vs member collision
[OK  ] generic heritage
[OK  ] inherit args
[OK  ] dotted call
[OK  ] method chain
[OK  ] match with calls
[OK  ] when guard call
[OK  ] lambda body call
[OK  ] try/with call
[OK  ] use binding
[OK  ] do binding
[OK  ] computation expression
[OK  ] task CE
[OK  ] seq expression
[OK  ] string interpolation call
[OK  ] backtick identifier
[OK  ] attribute on function
[OK  ] extension member on local
[OK  ] module rec

58/58 constructs covered
Exit 0 = all constructs covered.

A curated inventory of F# constructs, each with a minimal EXPECTATION: labels
that must appear as sourced nodes and/or (caller, relation, callee) edges that
must exist. Constructs whose expectations fail are OMISSIONS — reported
mechanically so review arms assess consequences instead of hunting.

This is the instrument the first three review rounds lacked: every
omission-class defect they found (generics, active patterns, member val,
heritage, object expressions) would have appeared here for free.
"""
from __future__ import annotations

import pathlib, sys, tempfile

from graphify.extractors.fsharp import extract_fsharp

# (name, source, expected_sourced_labels, expected_edges[, forbidden_labels])
# expected_edges: (src_label, relation, tgt_label); None matches any, but a
# fully-wildcard edge is rejected by run_one (it can never fail — round-4
# mutation audit). forbidden_labels catches COMMISSION defects (a wrong extra
# sourced node), the class every headline round-1..3 bug belonged to.
CONSTRUCTS: list = [
    ("let function", "module M\nlet f x = g x\n", {"f()"}, [("f()", "calls", "g")]),
    ("let value", "module M\nlet port = 8080\n", {"port"}, []),
    ("annotated let", "module M\nlet f (a: A) : R = g a\n", set(),
     [(None, "calls", "g")], {"R", "A"}),
    ("annotated single-arg let", "module M\nlet run (m: string) : int = work m\n",
     set(), [(None, "calls", "work")], {"int", "string"}),
    ("destructuring let", "module M\nlet (a, b) = mk ()\n", {"a", "b"}, []),
    ("let rec and", "module M\nlet rec f x = g x\nand g y = f y\n", {"f()", "g()"},
     [("f()", "calls", "g()"), ("g()", "calls", "f()")]),
    ("nested let scoping", "module M\nlet outer x =\n    let inner = 1\n    use2 inner\n",
     {"outer()"}, [("outer()", "calls", "use2")]),
    ("active pattern total", "module M\nlet (|Even|Odd|) n = cls n\n",
     {"(|Even|Odd|)"}, [("(|Even|Odd|)", "calls", "cls")]),
    ("active pattern partial", "module M\nlet (|Int|_|) (s: string) = tryInt s\n",
     {"(|Int|_|)"}, [("(|Int|_|)", "calls", "tryInt")]),
    ("operator def", "module M\nlet (+.) a b = comb a b\n", {"(+.)"},
     [("(+.)", "calls", "comb")]),
    ("record type", "module M\ntype R = { A: int }\n", {"R"}, []),
    ("union type + cases", "module M\ntype U = | X | Y of int\n", {"U", "X", "Y"},
     [("U", "contains", "X")]),
    ("enum members", "module M\ntype E = | A = 1 | B = 2\n", {"E", "A", "B"},
     [("E", "contains", "A")]),
    ("generic type", "module M\ntype Box<'T>() = member this.Get() = 1\n",
     {"Box", ".Get()"}, [("Box", "contains", ".Get()")]),
    ("constrained generic", "module M\ntype C<'T when 'T :> System.IDisposable> = { V: 'T }\n",
     {"C"}, [], {"T", "IDisposable"}),
    ("type abbreviation", "module M\ntype Alias = System.String\n", {"Alias"}, []),
    ("struct type", "module M\n[<Struct>]\ntype P = { X: int }\n", {"P"}, []),
    ("interface type", "module M\ntype IFoo =\n    abstract member Go: unit -> int\n",
     {"IFoo", ".Go()"}, [("IFoo", "contains", ".Go()")]),
    ("delegate type", "module M\ntype D = delegate of int -> int\n", {"D"}, []),
    ("mutually recursive types", "module M\ntype A = { B: B }\nand B = { A: A }\n",
     {"A", "B"}, []),
    ("class + member", "module M\ntype S(c: int) =\n    member this.Run() = go c\n",
     {"S", ".Run()"}, [(".Run()", "calls", "go")]),
    ("static member", "module M\ntype S() =\n    static member Make() = build ()\n",
     {".Make()"}, [(".Make()", "calls", "build")]),
    ("member val", "module M\ntype S() =\n    member val Name = \"x\" with get, set\n",
     {".Name()"}, []),
    ("abstract/override", "module M\n[<AbstractClass>]\ntype B() =\n    abstract member Go: unit -> int\n    default this.Go() = 1\ntype D() =\n    inherit B()\n    override this.Go() = 2\n",
     {"B", "D"}, [("D", "inherits", "B")]),
    ("inherit", "module M\ntype Sub() =\n    inherit Base()\n", {"Sub"},
     [("Sub", "inherits", "Base")]),
    ("interface impl", "module M\ntype R() =\n    interface System.IDisposable with\n        member this.Dispose() = ()\n",
     {"R", ".Dispose()"}, [("R", "implements", "IDisposable")]),
    ("type extension member", "module M\ntype System.String with\n    member this.Shout() = up this\n",
     {".Shout()"}, [], {"String"}),
    ("object expression", "module M\nlet mk () =\n    { new System.IDisposable with\n        member this.Dispose() = clean () }\n",
     {"mk()"}, [("mk()", "calls", "clean"), ("mk()", "references", "IDisposable")],
     {".Dispose()"}),
    ("exception", "module M\nexception Bad of string\n", {"Bad"}, []),
    # imports edges target _make_id(fqn) — no node is minted, so the target
    # has no label; anchor on the source (the file node) instead.
    ("open", "module M\nopen System.Text\n", set(),
     [("c.fs", "imports", None)], {"Text"}),
    ("nested module", "module M\nmodule Inner =\n    let f x = x\n", {"Inner", "f()"},
     [("Inner", "contains", "f()")]),
    ("namespace + module", "namespace N.S\nmodule Impl =\n    let f x = x\n",
     {"Impl", "f()"}, []),
    ("pipe right", "module M\nlet h x = x |> f1\n", {"h()"}, [("h()", "calls", "f1")]),
    ("pipe left", "module M\nlet h x = f1 <| x\n", {"h()"}, [("h()", "calls", "f1")]),
    ("pipe2 right", "module M\nlet h a b = (a, b) ||> f2\n", {"h()"},
     [("h()", "calls", "f2")]),
    ("composition >>", "module M\nlet h = f1 >> f2\n", {"h"},
     [("h", "calls", "f1"), ("h", "calls", "f2")]),
    ("composition <<", "module M\nlet h = f2 << f1\n", {"h"},
     [("h", "calls", "f1"), ("h", "calls", "f2")]),
    ("static let in class", "module M\ntype C() =\n    static let build x = shape x\n    member this.Go() = build 1\n",
     {"build()", ".Go()"}, [("build()", "calls", "shape"), (".Go()", "calls", "build()")]),
    ("local module qualified call", "module Root\nmodule Config =\n    let create p = p\nlet boot () = Config.create 1\n",
     {"create()", "boot()"}, [("boot()", "calls", "create()")]),
    ("class let vs member collision", "module M\ntype T() =\n    let run () = 1\n    member this.Run() = run ()\n",
     {"run()", ".Run()"}, [(".Run()", "calls", "run()")]),
    ("generic heritage", "module M\ntype Child<'T>() =\n    inherit Base<'T>()\n",
     {"Child"}, [("Child", "inherits", "Base")], {"T", "Base"}),
    ("inherit args", "module M\ntype Sub() =\n    inherit Base(mkArg ())\n",
     {"Sub"}, [("Sub", "calls", "mkArg")]),
    # Bare-name stub target is the ESTABLISHED design (mirrors ocaml.py): it
    # is what lets the corpus rewire collapse the call onto the real `init`.
    ("dotted call", "module M\nlet h x = Grasp.Telemetry.init x\n", {"h()"},
     [("h()", "calls", "init")]),
    ("method chain", "module M\nlet h (sb: B) = sb.Append(1).Append(2)\n", {"h()"},
     [("h()", "calls", None)]),
    ("match with calls", "module M\nlet h x =\n    match x with\n    | Some v -> handle v\n    | None -> fallback ()\n",
     {"h()"}, [("h()", "calls", "handle"), ("h()", "calls", "fallback")]),
    ("when guard call", "module M\nlet h x =\n    match x with\n    | v when isBig v -> v\n    | v -> v\n",
     {"h()"}, [("h()", "calls", "isBig")]),
    ("lambda body call", "module M\nlet h xs = List.map (fun x -> conv x) xs\n",
     {"h()"}, [("h()", "calls", "conv")]),
    ("try/with call", "module M\nlet h x =\n    try risky x\n    with _ -> recover x\n",
     {"h()"}, [("h()", "calls", "risky"), ("h()", "calls", "recover")]),
    ("use binding", "module M\nlet h () =\n    use r = acquire ()\n    work r\n",
     {"h()"}, [("h()", "calls", "acquire"), ("h()", "calls", "work")]),
    ("do binding", "module M\ndo setup ()\n", set(), [(None, "calls", "setup")]),
    ("computation expression", "module M\nlet h () =\n    async {\n        let! r = fetch ()\n        return proc r\n    }\n",
     {"h()"}, [("h()", "calls", "fetch"), ("h()", "calls", "proc")]),
    ("task CE", "module M\nlet h () =\n    task {\n        do! flush ()\n        return 1\n    }\n",
     {"h()"}, [("h()", "calls", "flush")]),
    ("seq expression", "module M\nlet h n = seq { for i in 1..n -> conv i }\n",
     {"h()"}, [("h()", "calls", "conv")]),
    ("string interpolation call", "module M\nlet h x = printfn $\"v={calc x}\"\n",
     {"h()"}, [("h()", "calls", "calc")]),
    ("backtick identifier", "module M\nlet ``my test name`` () = check ()\n",
     set(), [(None, "calls", "check")]),
    ("attribute on function", "module M\n[<EntryPoint>]\nlet main argv = run argv\n",
     {"main()"}, [("main()", "calls", "run")]),
    ("extension member on local", "module M\ntype T() = member this.A() = 1\ntype T with\n    member this.B() = 2\n",
     {"T", ".A()", ".B()"}, []),
    ("module rec", "module rec M\nlet f x = g x\nlet g y = y\n", {"f()", "g()"},
     [("f()", "calls", "g()")]),
]


def run_one(name: str, src: str, want_labels: set, want_edges: list,
            forbidden: set | None = None):
    with tempfile.TemporaryDirectory() as td:
        fp = pathlib.Path(td) / "c.fs"
        fp.write_text(src, encoding="utf-8")
        r = extract_fsharp(fp)
    if "error" in r:
        return [f"extractor error: {r['error']}"]
    lab = {n["id"]: n["label"] for n in r["nodes"]}
    sourced = {n["label"] for n in r["nodes"] if n.get("source_file")}
    edges = {(lab.get(e["source"]), e["relation"], lab.get(e["target"]))
             for e in r["edges"]}
    problems = []
    missing = want_labels - sourced
    if missing:
        problems.append(f"missing sourced labels: {sorted(missing)}")
    hit = sourced & (forbidden or set())
    if hit:
        problems.append(f"FORBIDDEN sourced labels present: {sorted(hit)}")
    for (ws, wr, wt) in want_edges:
        if ws is None and wt is None:
            problems.append(f"vacuous expectation (all-wildcard edge): {wr}")
            continue
        ok = any((ws is None or s == ws) and rel == wr and (wt is None or t == wt)
                 for (s, rel, t) in edges)
        if not ok:
            problems.append(f"missing edge: ({ws}, {wr}, {wt})")
    for e in r["edges"]:
        if e["source"] == e["target"]:
            problems.append(f"self-loop edge: {lab.get(e['source'])} {e['relation']}")
    return problems


def main():
    failures = 0
    for entry in CONSTRUCTS:
        name, src, wl, we = entry[0], entry[1], entry[2], entry[3]
        fb = entry[4] if len(entry) > 4 else None
        problems = run_one(name, src, wl, we, fb)
        status = "OK  " if not problems else "MISS"
        if problems:
            failures += 1
        print(f"[{status}] {name}")
        for pr in problems:
            print(f"        {pr}")
    print(f"\n{len(CONSTRUCTS) - failures}/{len(CONSTRUCTS)} constructs covered")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
