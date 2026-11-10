"""C# `new Foo(...)` links the constructing method to Foo.

The C# config only listed `invocation_expression` in `call_types`, so an
`object_creation_expression` was never dispatched and a type a method merely
constructs got no edge at all. Java has taken `new Foo(...)` as a call since
#1373; C# had not caught up. The types this loses are the ones handed straight
to something else — `Send(new OrderPlaced { ... })` on a message bus, a locally
built collaborator — so publishers looked unconnected while the class sat right
there in the graph.

Only the explicit form is claimed. Target-typed `new()` parses as
`implicit_object_creation_expression` and needs the assignment target's declared
type to name anything, so it stays out.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from graphify.build import build_from_json, edge_data
from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=Path(tempfile.mkdtemp()))
    finally:
        os.chdir(old)
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    return calls, r


def _find(r, label, id_contains):
    return next(n["id"] for n in r["nodes"]
                if n["label"] == label and id_contains in n["id"])


def test_explicitly_declared_local_links_to_constructed_type(tmp_path):
    calls, r = _extract(tmp_path, {"S.cs": (
        "public class Worker { }\n"
        "public class Caller {\n"
        "    public void Go() { Worker w = new Worker(); }\n"
        "}\n"
    )})
    assert (_find(r, ".Go()", "go"), _find(r, "Worker", "worker")) in calls


def test_var_local_links_to_constructed_type(tmp_path):
    calls, r = _extract(tmp_path, {"S.cs": (
        "public class Worker { }\n"
        "public class Caller {\n"
        "    public void Go() { var w = new Worker(); }\n"
        "}\n"
    )})
    assert (_find(r, ".Go()", "go"), _find(r, "Worker", "worker")) in calls


def test_argument_position_links_to_constructed_type(tmp_path):
    # The publish shape: the message type never appears in a declared position.
    calls, r = _extract(tmp_path, {"S.cs": (
        "public class OrderPlaced { }\n"
        "public class Publisher {\n"
        "    public void Publish() { Send(new OrderPlaced()); }\n"
        "    private void Send(object payload) { }\n"
        "}\n"
    )})
    assert (_find(r, ".Publish()", "publish"), _find(r, "OrderPlaced", "orderplaced")) in calls


def test_object_initializer_without_parens_links(tmp_path):
    calls, r = _extract(tmp_path, {"S.cs": (
        "public class OrderPlaced { public long Id { get; set; } }\n"
        "public class Publisher {\n"
        "    public void Publish(long id) { Send(new OrderPlaced { Id = id }); }\n"
        "    private void Send(object payload) { }\n"
        "}\n"
    )})
    assert (_find(r, ".Publish()", "publish"), _find(r, "OrderPlaced", "orderplaced")) in calls


def test_generic_construction_names_the_outer_type(tmp_path):
    calls, r = _extract(tmp_path, {"S.cs": (
        "public class Cache<T> { }\n"
        "public class Caller {\n"
        "    public void Go() { var c = new Cache<string>(); }\n"
        "}\n"
    )})
    assert (_find(r, ".Go()", "go"), _find(r, "Cache", "cache")) in calls


def test_qualified_construction_names_the_last_segment(tmp_path):
    calls, r = _extract(tmp_path, {
        "Store.cs": (
            "namespace Infra.Data;\n"
            "public class Cache { }\n"
        ),
        "Caller.cs": (
            "public class Caller {\n"
            "    public void Go() { var c = new Infra.Data.Cache(); }\n"
            "}\n"
        ),
    })
    assert (_find(r, ".Go()", "go"), _find(r, "Cache", "cache")) in calls


def test_target_typed_new_produces_no_edge(tmp_path):
    # `new()` carries no type node; guessing one needs the target's declared type.
    calls, r = _extract(tmp_path, {"S.cs": (
        "public class Worker { }\n"
        "public class Caller {\n"
        "    public Worker Build() { Worker w = new(); return w; }\n"
        "}\n"
    )})
    worker = _find(r, "Worker", "worker")
    assert not any(target == worker for _, target in calls)


def test_cross_file_publisher_reaches_the_message_class(tmp_path):
    calls, r = _extract(tmp_path, {
        "Events/OrderPlaced.cs": (
            "namespace Demo.Events;\n"
            "public class OrderPlaced { public long Id { get; set; } }\n"
        ),
        "Publisher.cs": (
            "using Demo.Events;\n"
            "public class Publisher {\n"
            "    public void Publish(long id) { Send(new OrderPlaced { Id = id }); }\n"
            "    private void Send(object payload) { }\n"
            "}\n"
        ),
    })
    assert (_find(r, ".Publish()", "publish"), _find(r, "OrderPlaced", "orderplaced")) in calls


def test_ambiguous_type_name_produces_no_edge(tmp_path):
    # Two classes share a name, so the construction site cannot be pinned to one
    # of them. No edge beats a coin flip here — #437 is about exactly the kind of
    # false edge a name-only guess creates.
    calls, r = _extract(tmp_path, {
        "Left.cs": "namespace Left;\npublic class Cache { }\n",
        "Right.cs": "namespace Right;\npublic class Cache { }\n",
        "Caller.cs": (
            "using Right;\n"
            "public class Caller {\n"
            "    public void Go() { var c = new Cache(); }\n"
            "}\n"
        ),
    })
    caches = {n["id"] for n in r["nodes"] if n["label"] == "Cache"}
    assert len(caches) == 2
    assert not any(target in caches for _, target in calls)


_COLLIDING_CACHES = {
    "Left.cs": "namespace Infra.Data;\npublic class Cache { }\n",
    "Right.cs": "namespace Other;\npublic class Cache { }\n",
}


def test_qualified_construction_picks_the_named_namespace(tmp_path):
    # The bare name is ambiguous, but the source says which Cache it means.
    calls, r = _extract(tmp_path, {**_COLLIDING_CACHES, "Caller.cs": (
        "public class Caller {\n"
        "    public void Go() { var c = new Infra.Data.Cache(); }\n"
        "}\n"
    )})
    wanted = _find(r, "Cache", "left")
    other = _find(r, "Cache", "right")
    go = _find(r, ".Go()", "go")
    assert (go, wanted) in calls
    assert (go, other) not in calls


def test_partially_qualified_construction_stays_unresolved(tmp_path):
    # `new Data.Cache()` under `using Infra;` would need the using directives in
    # scope to become a namespace. Resolving it by suffix would be a guess.
    calls, r = _extract(tmp_path, {**_COLLIDING_CACHES, "Caller.cs": (
        "using Infra;\n"
        "public class Caller {\n"
        "    public void Go() { var c = new Data.Cache(); }\n"
        "}\n"
    )})
    caches = {n["id"] for n in r["nodes"] if n["label"] == "Cache"}
    assert not any(target in caches for _, target in calls)


def test_qualified_construction_with_two_candidates_in_one_namespace(tmp_path):
    # Same namespace declared in two files, both holding a Cache: the qualifier
    # cannot separate them either, so the guard still applies.
    calls, r = _extract(tmp_path, {
        "One.cs": "namespace Infra.Data;\npublic class Cache { }\n",
        "Two.cs": "namespace Infra.Data;\npublic class Cache { }\n",
        "Caller.cs": (
            "public class Caller {\n"
            "    public void Go() { var c = new Infra.Data.Cache(); }\n"
            "}\n"
        ),
    })
    caches = {n["id"] for n in r["nodes"] if n["label"] == "Cache"}
    assert not any(target in caches for _, target in calls)


def test_receiver_typed_member_call_still_resolves(tmp_path):
    # Guard for #1609: adding a node type to call_types must not disturb the
    # invocation path that binds a call to its receiver's declared type.
    calls, r = _extract(tmp_path, {"S.cs": (
        "public class Server { public bool Save() => true; }\n"
        "public class Cache  { public bool Save() => false; }\n"
        "public class Repo {\n"
        "    private Server _server = new Server();\n"
        "    public bool Commit() { return _server.Save(); }\n"
        "}\n"
    )})
    commit = _find(r, ".Commit()", "commit")
    assert (commit, _find(r, ".Save()", "server")) in calls
    assert (commit, _find(r, ".Save()", "cache")) not in calls

def test_qualified_construction_resolves_when_the_method_also_declares_the_type(tmp_path):
    # The method takes the type as a parameter and constructs it. The declared
    # position mints a bare-name stub in this file, and binding the construction
    # to that stub would keep it away from the namespace resolver, so the call
    # would land on a sourceless node instead of the class.
    calls, r = _extract(tmp_path, {**_COLLIDING_CACHES, "Caller.cs": (
        "public class Caller {\n"
        "    public void Go(Infra.Data.Cache existing) { var c = new Infra.Data.Cache(); }\n"
        "}\n"
    )})
    go = _find(r, ".Go()", "go")
    assert (go, _find(r, "Cache", "left")) in calls
    sourceless = {n["id"] for n in r["nodes"]
                  if n["label"] == "Cache" and not n.get("source_file")}
    assert not any(target in sourceless for _, target in calls)


def test_factory_constructing_its_own_type_keeps_the_method_edge(tmp_path):
    # `Fault` both belongs to `Report` and constructs it. On the default
    # undirected graph those are one pair, and the `calls` edge used to be
    # the one that survived, so `Report` had no `method` edge to `Fault`.
    # The siblings that do not call the type were never affected.
    _, r = _extract(tmp_path, {"Report.cs": (
        "namespace Demo\n"
        "{\n"
        "    public sealed class Report\n"
        "    {\n"
        "        public string Verb;\n"
        "        public static Report Fault(string verb) { return new Report { Verb = verb }; }\n"
        "        public static string NotImplementedJson(string verb) { return verb; }\n"
        "        public string ToJson() { return Verb; }\n"
        "    }\n"
        "}\n"
    )})
    report = _find(r, "Report", "report")
    fault = _find(r, ".Fault()", "fault")
    G = build_from_json(r)
    kept = edge_data(G, report, fault)
    assert kept.get("relation") == "method"
    assert (kept.get("_src"), kept.get("_tgt")) == (report, fault)
    assert edge_data(G, report, _find(r, ".NotImplementedJson()", "notimplemented")).get(
        "relation") == "method"
    assert edge_data(G, report, _find(r, ".ToJson()", "tojson")).get("relation") == "method"
    # Directed storage has room for both facts.
    D = build_from_json(r, directed=True)
    assert edge_data(D, report, fault).get("relation") == "method"
    assert edge_data(D, fault, report).get("relation") == "calls"


def test_qualified_construction_of_a_foreign_type_makes_no_stub_edge(tmp_path):
    # `new System.Text.StringBuilder()` has no declaration in the corpus. No edge
    # beats an edge into a sourceless placeholder that stands for nothing.
    calls, r = _extract(tmp_path, {"Caller.cs": (
        "public class Caller {\n"
        "    public void Go() { var b = new System.Text.StringBuilder(); }\n"
        "}\n"
    )})
    builders = {n["id"] for n in r["nodes"] if n["label"] == "StringBuilder"}
    assert not any(target in builders for _, target in calls)


# `new X()` constructs a type. A method that merely shares X's name is never its
# target, yet the call was resolved against every same-named definition: inside
# the method it became a self-loop (`static Bounds Bounds(..) => new Bounds(..)`
# on Unity's Bounds), and across files the bare-name pass bound every
# `new List<T>()` in the corpus to a `List()` method as an INFERRED hub.


def test_construction_never_binds_to_a_same_named_method_cross_file(tmp_path):
    calls, r = _extract(tmp_path, {
        "Market.cs": (
            "namespace Demo { public class Market {"
            " public static int List(int a) { return a; } } }\n"
        ),
        "Use.cs": (
            "namespace Demo { public class Use {"
            " public void Run() { var xs = new List<int>(); } } }\n"
        ),
    })
    run = _find(r, ".Run()", "run")
    assert (run, _find(r, ".List()", "market")) not in calls


def test_construction_inside_a_same_named_method_is_no_self_loop(tmp_path):
    calls, r = _extract(tmp_path, {"Box.cs": (
        "namespace Demo { public class Box {"
        " static Bounds Bounds(int a) { return new Bounds(a); } } }\n"
    )})
    bounds = _find(r, ".Bounds()", "box")
    assert (bounds, bounds) not in calls


def test_construction_still_binds_to_the_type_beside_a_same_named_method(tmp_path):
    calls, r = _extract(tmp_path, {
        "Kit.cs": "namespace Demo { public class Piece { } }\n",
        "Shop.cs": (
            "namespace Demo { public class Shop {"
            " public static int Piece() { return 0; } } }\n"
        ),
        "Setup.cs": (
            "namespace Demo { public class Setup {"
            " public void Link() { var p = new Piece(); } } }\n"
        ),
    })
    link = _find(r, ".Link()", "link")
    assert (link, _find(r, "Piece", "kit")) in calls
    assert (link, _find(r, ".Piece()", "shop")) not in calls


def test_qualified_nested_construction_follows_its_outer_type(tmp_path):
    # `new QuickSlotsBar.Slot()` names the outer type. Two `Slot` classes make
    # the bare name ambiguous, and the path-proximity tie-break picked the one
    # next to the caller — the wrong Slot. With method candidates no longer
    # muddying the tie, that guess would fire more often; a qualified
    # construction now takes the Slot nested in QuickSlotsBar, or no edge.
    calls, r = _extract(tmp_path, {
        "UI/Bar.cs": (
            "namespace Game.UI { public class QuickSlotsBar {"
            " public class Slot { public int kind; } } }\n"
        ),
        "Editor/Towers.cs": (
            "namespace Game.Tools { public class Towers {"
            " class Slot { public string texture; } } }\n"
        ),
        "Editor/Hud.cs": (
            "using Game.UI;\nnamespace Game.Tools { public class Hud {"
            " public void Ensure() { var s = new QuickSlotsBar.Slot { kind = 1 }; } } }\n"
        ),
    })
    ensure = _find(r, ".Ensure()", "ensure")
    def slot_in(stem):
        return next(n["id"] for n in r["nodes"]
                    if n["label"] == "Slot" and stem in str(n.get("source_file", "")))
    assert (ensure, slot_in("Towers")) not in calls
    assert (ensure, slot_in("Bar")) in calls


def test_qualified_construction_with_an_unknown_outer_type_gives_no_edge(tmp_path):
    calls, r = _extract(tmp_path, {
        "UI/Bar.cs": "namespace Game.UI { public class Bar { public class Slot { } } }\n",
        "Editor/Towers.cs": "namespace Game.Tools { public class Towers { class Slot { } } }\n",
        "Editor/Hud.cs": (
            "namespace Game.Tools { public class Hud {"
            " public void Ensure() { var s = new Missing.Slot(); } } }\n"
        ),
    })
    ensure = _find(r, ".Ensure()", "ensure")
    slots = {n["id"] for n in r["nodes"] if n["label"] == "Slot"}
    assert not any(t in slots for s, t in calls if s == ensure)


# Constructors are nodes: `new X(a, b)` and `: base(...)` / `: this(...)` reach
# the overload whose parameter count fits, next to the edge to the type.

def _ctor(r, type_name, signature):
    ids = [n["id"] for n in r["nodes"]
           if n["label"] == f".{type_name}()"
           and (n.get("metadata") or {}).get("kind") == "constructor"
           and (n.get("metadata") or {}).get("signature") == signature]
    assert len(ids) == 1, (type_name, signature, ids)
    return ids[0]


def test_construction_links_the_constructor_overload_its_arguments_fit(tmp_path):
    calls, r = _extract(tmp_path, {
        "Repo.cs": (
            "public class Repo {\n"
            "    public Repo() { }\n"
            "    public Repo(int a) { }\n"
            "    public Repo(int a, int b) { }\n"
            "}\n"
        ),
        "User.cs": "public class User { public void Go() { var r = new Repo(1, 2); } }\n",
    })
    go = _find(r, ".Go()", "user")
    assert (go, _find(r, "Repo", "repo")) in calls  # the type edge stays
    assert (go, _ctor(r, "Repo", "int,int")) in calls
    assert (go, _ctor(r, "Repo", "int")) not in calls
    assert (go, _ctor(r, "Repo", "")) not in calls


def test_construction_two_overloads_fit_gives_no_constructor_edge(tmp_path):
    calls, r = _extract(tmp_path, {"S.cs": (
        "public class Repo { public Repo(int a) { } public Repo(string s) { } }\n"
        "public class User { public void Go() { var r = new Repo(1); } }\n"
    )})
    go = _find(r, ".Go()", "user")
    assert (go, _find(r, "Repo", "repo")) in calls
    assert not {t for s, t in calls if s == go} & {
        _ctor(r, "Repo", "int"), _ctor(r, "Repo", "string")
    }


def test_constructor_body_and_initializer_calls_belong_to_the_constructor(tmp_path):
    calls, r = _extract(tmp_path, {"S.cs": (
        "public class Base { public Base(int a) { } }\n"
        "public class Svc : Base {\n"
        "    public Svc(int x) : base(Seed(x)) { Init(); }\n"
        "    static int Seed(int x) { return x; }\n"
        "    void Init() { }\n"
        "}\n"
    )})
    ctor = _ctor(r, "Svc", "int")
    svc = _find(r, "Svc", "svc")
    for callee in (".Seed()", ".Init()"):
        assert (ctor, _find(r, callee, "svc")) in calls
        assert (svc, _find(r, callee, "svc")) not in calls


def test_this_initializer_links_the_own_overload(tmp_path):
    calls, r = _extract(tmp_path, {"S.cs": (
        "public class Svc {\n"
        "    public Svc() : this(1, 2) { }\n"
        "    public Svc(int a) { }\n"
        "    public Svc(int a, int b) { }\n"
        "}\n"
    )})
    assert (_ctor(r, "Svc", ""), _ctor(r, "Svc", "int,int")) in calls
    assert (_ctor(r, "Svc", ""), _ctor(r, "Svc", "int")) not in calls


def test_base_initializer_links_the_base_constructor_in_another_file(tmp_path):
    calls, r = _extract(tmp_path, {
        "Base.cs": (
            "namespace Demo {\n"
            "    public class Base { public Base(int a) { } public Base(string a, int b) { } }\n"
            "}\n"
        ),
        "Derived.cs": (
            "namespace Demo {\n"
            "    public class Derived : Base { public Derived(int x) : base(\"s\", x) { } }\n"
            "}\n"
        ),
    })
    derived = _ctor(r, "Derived", "int")
    assert (derived, _ctor(r, "Base", "string,int")) in calls
    assert (derived, _ctor(r, "Base", "int")) not in calls


def test_base_initializer_with_an_out_of_corpus_base_gives_no_edge(tmp_path):
    calls, r = _extract(tmp_path, {"S.cs": (
        "public class Local { public Local(int a) { } }\n"
        "public class Derived : System.Exception { public Derived(int x) : base(\"m\") { } }\n"
    )})
    derived = _ctor(r, "Derived", "int")
    assert not {t for s, t in calls if s == derived}


def test_static_constructor_is_its_own_node_and_never_constructed(tmp_path):
    calls, r = _extract(tmp_path, {"S.cs": (
        "public class Reg {\n"
        "    static Reg() { Load(); }\n"
        "    public Reg() { }\n"
        "    static void Load() { }\n"
        "}\n"
        "public class User { public void Go() { var r = new Reg(); } }\n"
    )})
    static_ctor, instance_ctor = _ctor(r, "Reg", "static"), _ctor(r, "Reg", "")
    assert static_ctor != instance_ctor
    assert (static_ctor, _find(r, ".Load()", "reg")) in calls
    go = _find(r, ".Go()", "user")
    assert (go, instance_ctor) in calls
    assert (go, static_ctor) not in calls


def test_primary_constructor_competes_with_the_explicit_ones(tmp_path):
    calls, r = _extract(tmp_path, {"S.cs": (
        "public record Point(int X, int Y) { public Point(int x) : this(x, 0) { } }\n"
        "public class User { public void Go() { var a = new Point(1, 2); var b = new Point(3); } }\n"
    )})
    primary, explicit = _ctor(r, "Point", "int,int"), _ctor(r, "Point", "int")
    go = _find(r, ".Go()", "user")
    assert {(go, primary), (go, explicit), (explicit, primary)} <= calls


def test_constructor_in_an_unchanged_file_resolves_on_an_incremental_rebuild(tmp_path):
    import json

    from graphify.watch import _rebuild_code

    files = {
        "Repo.cs": "public class Repo { public Repo() { } public Repo(int a, int b) { } }\n",
        "User.cs": "public class User { public void Go() { var r = new Repo(1, 2); } }\n",
    }
    for name, body in files.items():
        (tmp_path / name).write_text(body)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False, force=True)
    user = tmp_path / "User.cs"
    user.write_text(user.read_text() + "// touched\n")
    assert _rebuild_code(tmp_path, changed_paths=[user], no_cluster=True, acquire_lock=False)
    graph = json.loads((tmp_path / "graphify-out" / "graph.json").read_text())
    ctor = next(n["id"] for n in graph["nodes"]
                if (n.get("metadata") or {}).get("signature") == "int,int")
    go = next(n["id"] for n in graph["nodes"] if n["label"].endswith("Go()"))
    assert any(l["source"] == go and l["target"] == ctor and l["relation"] == "calls"
               for l in graph["links"])
