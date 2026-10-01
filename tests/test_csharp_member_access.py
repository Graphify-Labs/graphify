"""C# member access resolves to the receiver type's property node (#3528).

An ORM query site never names its table: `db.Users.Where(...)` reaches the
`AspNetUsers` table through the `DbSet<ApplicationUser> Users` property, and
only the property appears in source. The property has been a node since
#3006, but nothing pointed at it except its own type's `defines` edge — the
invocation branch keeps only a simple receiver, so the chained `db.Users` was
dropped and every query site in the corpus was invisible from the data layer.

`recv.Prop` is now recorded like `recv.Method()` and resolved by the same
receiver-typed pass (#1609): the receiver is typed from the method-scoped
field/param/local table, the property is looked up on that type and its
`inherits` chain, and a `uses` edge lands on the property node. Same tiers as
the calls — `this.` / `Type.` are EXTRACTED, a typed receiver is INFERRED —
and the same guards: an untypable or ambiguous receiver yields no edge.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from graphify.extract import extract, extract_csharp


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
    uses = [e for e in r["edges"] if e["relation"] == "uses"]
    return uses, r


def _find(r, label, id_contains=""):
    return next(n["id"] for n in r["nodes"]
                if n["label"] == label and id_contains in n["id"])


def _pairs(uses):
    return {(e["source"], e["target"]) for e in uses}


_EF = {
    "Data/ApplicationUser.cs": (
        "namespace App.Data;\n"
        "public class ApplicationUser {\n"
        "    public int Id { get; set; }\n"
        "    public string Email { get; set; }\n"
        "}\n"
    ),
    "Data/Order.cs": (
        "namespace App.Data;\n"
        "public class Order { public int Id { get; set; } }\n"
    ),
    "Data/AppDbContext.cs": (
        "using Microsoft.EntityFrameworkCore;\n"
        "namespace App.Data;\n"
        "public class AppDbContext : DbContext {\n"
        "    public DbSet<ApplicationUser> Users { get; set; }\n"
        "    public DbSet<Order> Orders { get; set; }\n"
        "}\n"
    ),
    "Services/UserService.cs": (
        "using System.Linq;\n"
        "using App.Data;\n"
        "namespace App.Services;\n"
        "public class UserService {\n"
        "    private readonly AppDbContext db;\n"
        "    public UserService(AppDbContext db) { this.db = db; }\n"
        "    public ApplicationUser FindByEmail(string email) {\n"
        "        return db.Users.AsNoTracking().Where(u => u.Email == email).FirstOrDefault();\n"
        "    }\n"
        "    public int CountOrders() { return db.Orders.Count(); }\n"
        "    public void AddUser(ApplicationUser u) { db.Users.Add(u); }\n"
        "}\n"
    ),
}


def test_dbset_query_site_links_the_method_to_the_dbset_property(tmp_path):
    # The issue's shape: the table name is nowhere in source, only the
    # property is. This is the test that fails without the fix.
    uses, r = _extract(tmp_path, _EF)
    users = _find(r, "Users", "appdbcontext")
    orders = _find(r, "Orders", "appdbcontext")
    assert (_find(r, ".FindByEmail()"), users) in _pairs(uses)
    assert (_find(r, ".CountOrders()"), orders) in _pairs(uses)
    assert (_find(r, ".AddUser()"), users) in _pairs(uses)


def test_edge_carries_the_query_line_not_the_declaration_line(tmp_path):
    uses, r = _extract(tmp_path, _EF)
    edge = next(e for e in uses
                if e["source"] == _find(r, ".CountOrders()"))
    assert edge["source_location"] == "L10"
    assert edge["source_file"].endswith("UserService.cs")
    assert edge["context"] == "member_access"
    # Typed through the field table, not named in source — INFERRED, like a
    # `recv.Method()` call resolved the same way.
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.8


def test_untyped_lambda_parameter_yields_no_edge(tmp_path):
    # `u => u.Email == email`: `u` is an untyped lambda parameter, so
    # `u.Email` must not bind to ApplicationUser.Email — never a guess.
    uses, r = _extract(tmp_path, _EF)
    email = _find(r, "Email")
    assert not any(t == email for _, t in _pairs(uses))


def test_bare_access_without_a_call_is_an_edge_too(tmp_path):
    uses, r = _extract(tmp_path, {
        "S.cs": (
            "public class Ctx { public System.Collections.Generic.List<int> Rows { get; set; } }\n"
            "public class Svc {\n"
            "    private Ctx ctx;\n"
            "    public object Snapshot() { var rows = ctx.Rows; return rows; }\n"
            "    public void Walk() { foreach (var r in ctx.Rows) { } }\n"
            "}\n"
        )
    })
    rows = _find(r, "Rows")
    assert (_find(r, ".Snapshot()"), rows) in _pairs(uses)
    assert (_find(r, ".Walk()"), rows) in _pairs(uses)


def test_explicit_this_field_receiver_is_typed_like_the_bare_field(tmp_path):
    uses, r = _extract(tmp_path, {
        "S.cs": (
            "public class Ctx { public int Rows { get; set; } }\n"
            "public class Svc {\n"
            "    private Ctx ctx;\n"
            "    public int Count() { return this.ctx.Rows; }\n"
            "}\n"
        )
    })
    assert (_find(r, ".Count()"), _find(r, "Rows")) in _pairs(uses)


def test_this_property_and_static_type_property_are_extracted(tmp_path):
    uses, r = _extract(tmp_path, {
        "S.cs": (
            "public class Config { public static Config Instance { get; set; } }\n"
            "public class Svc {\n"
            "    public int Size { get; set; }\n"
            "    public int Own() { return this.Size; }\n"
            "    public Config Shared() { return Config.Instance; }\n"
            "}\n"
        )
    })
    by_pair = {(e["source"], e["target"]): e for e in uses}
    own = by_pair[(_find(r, ".Own()"), _find(r, "Size"))]
    shared = by_pair[(_find(r, ".Shared()"), _find(r, "Instance"))]
    for edge in (own, shared):
        assert edge["confidence"] == "EXTRACTED"
        assert edge["confidence_score"] == 1.0


def test_base_property_resolves_against_the_single_base_class(tmp_path):
    uses, r = _extract(tmp_path, {
        "S.cs": (
            "public class BaseCtx { public int Rows { get; set; } }\n"
            "public class Ctx : BaseCtx {\n"
            "    public int Count() { return base.Rows; }\n"
            "}\n"
        )
    })
    edge = next(e for e in uses if e["target"] == _find(r, "Rows"))
    assert edge["source"] == _find(r, ".Count()")
    assert edge["confidence"] == "EXTRACTED"


def test_interface_typed_receiver_binds_to_the_interface_property(tmp_path):
    # The Clean Architecture shape: handlers take `IApplicationDbContext`,
    # whose DbSet properties are declared on the interface.
    uses, r = _extract(tmp_path, {
        "S.cs": (
            "using Microsoft.EntityFrameworkCore;\n"
            "public class TodoItem { public int Id { get; set; } }\n"
            "public interface IAppDb { DbSet<TodoItem> TodoItems { get; } }\n"
            "public class Handler {\n"
            "    private readonly IAppDb _context;\n"
            "    public Handler(IAppDb context) { _context = context; }\n"
            "    public int Total() => _context.TodoItems.Count();\n"
            "}\n"
        )
    })
    assert (_find(r, ".Total()"), _find(r, "TodoItems", "iappdb")) in _pairs(uses)


def test_inherited_property_resolves_through_the_base_chain(tmp_path):
    uses, r = _extract(tmp_path, {
        "Base.cs": "public class BaseCtx { public int Rows { get; set; } }\n",
        "S.cs": (
            "public class Ctx : BaseCtx { }\n"
            "public class Svc {\n"
            "    private Ctx ctx;\n"
            "    public int Count() { return ctx.Rows; }\n"
            "}\n"
        ),
    })
    assert (_find(r, ".Count()"), _find(r, "Rows", "basectx")) in _pairs(uses)


def test_partial_dbcontext_property_in_the_other_half(tmp_path):
    # The DbSet lives in one half of a partial class and the receiver is
    # typed by the class name; the merge must land before this pass.
    uses, r = _extract(tmp_path, {
        "Ctx.cs": "public partial class Ctx { }\n",
        "Ctx.Sets.cs": "public partial class Ctx { public int Rows { get; set; } }\n",
        "S.cs": (
            "public class Svc {\n"
            "    private Ctx ctx;\n"
            "    public int Count() { return ctx.Rows; }\n"
            "}\n"
        ),
    })
    assert (_find(r, ".Count()"), _find(r, "Rows")) in _pairs(uses)


def test_receiver_type_outside_the_corpus_yields_no_edge_and_is_not_parked(tmp_path):
    # Both receiver tiers that can park a call: a typed lowercase receiver
    # (`http` is an HttpContext) and an explicit type name (`Environment`).
    uses, r = _extract(tmp_path, {
        "S.cs": (
            "public class Svc {\n"
            "    public string Path(Microsoft.AspNetCore.Http.HttpContext http) {\n"
            "        return http.Request.Path + System.Environment.MachineName + Environment.NewLine;\n"
            "    }\n"
            "}\n"
        )
    })
    assert not uses
    # Parked entries are cross-repo CALL candidates (#3152); a property read
    # is not one and must not be parked as if it were.
    path = next(n for n in r["nodes"] if n["label"] == ".Path()")
    parked = (path.get("metadata") or {}).get("unresolved_calls", [])
    assert not any(p.get("callee") in ("Request", "NewLine") for p in parked)


def test_ambiguous_receiver_type_yields_no_edge(tmp_path):
    # Two `Ctx` types, neither in scope of the caller: the god-node guard
    # that already applies to `ctx.Method()` applies to `ctx.Rows` too.
    uses, r = _extract(tmp_path, {
        "A.cs": "namespace A; public class Ctx { public int Rows { get; set; } }\n",
        "B.cs": "namespace B; public class Ctx { public int Rows { get; set; } }\n",
        "S.cs": (
            "namespace S;\n"
            "public class Svc {\n"
            "    private Ctx ctx;\n"
            "    public int Count() { return ctx.Rows; }\n"
            "}\n"
        ),
    })
    assert not uses


def test_field_or_method_member_is_not_a_property_edge(tmp_path):
    # `_conn` is a field (no node, #3006) and `Save` a method group: neither
    # is a property, so neither becomes a `uses` edge — and the method-group
    # read must not become a `calls` edge either.
    uses, r = _extract(tmp_path, {
        "S.cs": (
            "public class Ctx {\n"
            "    public string _conn;\n"
            "    public bool Save() => true;\n"
            "}\n"
            "public class Svc {\n"
            "    private Ctx ctx;\n"
            "    public object Grab() { var f = ctx.Save; return ctx._conn; }\n"
            "}\n"
        )
    })
    assert not uses
    grab = _find(r, ".Grab()")
    assert not any(e["source"] == grab and e["relation"] == "calls" for e in r["edges"])


def test_repeated_access_in_one_method_is_one_edge(tmp_path):
    uses, r = _extract(tmp_path, {
        "S.cs": (
            "public class Ctx { public int Rows { get; set; } }\n"
            "public class Svc {\n"
            "    private Ctx ctx;\n"
            "    public int Twice() { return ctx.Rows + ctx.Rows; }\n"
            "}\n"
        )
    })
    assert len(uses) == 1


def test_shadowing_local_of_another_type_poisons_the_receiver(tmp_path):
    # The scoped-table rule from #2299: a local disagreeing with the field's
    # type drops the name entirely rather than guessing.
    uses, r = _extract(tmp_path, {
        "S.cs": (
            "public class Ctx { public int Rows { get; set; } }\n"
            "public class Other { public int Rows { get; set; } }\n"
            "public class Svc {\n"
            "    private Ctx ctx;\n"
            "    public int Count() { Other ctx = new Other(); return ctx.Rows; }\n"
            "}\n"
        )
    })
    assert not uses


def test_generic_set_call_and_outer_chain_are_not_property_accesses(tmp_path):
    # `db.Set<Order>()` names a generic method (the type argument is already
    # linked by #2911); `db.Users.Local` only yields the inner `db.Users`.
    uses, r = _extract(tmp_path, {
        "S.cs": (
            "using Microsoft.EntityFrameworkCore;\n"
            "public class Order { }\n"
            "public class Ctx : DbContext { public DbSet<Order> Users { get; set; } }\n"
            "public class Svc {\n"
            "    private Ctx db;\n"
            "    public object A() { return db.Set<Order>(); }\n"
            "    public object B() { return db.Users.Local; }\n"
            "}\n"
        )
    })
    assert _pairs(uses) == {(_find(r, ".B()"), _find(r, "Users"))}


def test_same_named_cpp_member_is_not_a_target(tmp_path):
    # A C# receiver must never reach a C++ data member through the shared
    # `defines` relation, even when the bare type name would resolve there.
    uses, r = _extract(tmp_path, {
        "w.hpp": "class Widget { public: int Size; };\n",
        "S.cs": (
            "public class Svc {\n"
            "    public int Measure(Widget w) { return w.Size; }\n"
            "}\n"
        ),
    })
    assert not uses


def test_raw_entry_is_flagged_as_both_member_call_and_member_access(tmp_path):
    # `is_member_call` keeps every bare-name resolver off the entry, the way
    # it does for `recv.Method()`; `is_member_access` is what the C# resolver
    # branches on. Both must be present or another pass could claim it.
    p = tmp_path / "S.cs"
    p.write_text(
        "public class Svc {\n"
        "    private Ctx db;\n"
        "    public object Q() { return db.Users; }\n"
        "}\n"
    )
    entries = [rc for rc in extract_csharp(p)["raw_calls"] if rc.get("callee") == "Users"]
    assert len(entries) == 1
    rc = entries[0]
    assert rc["is_member_call"] is True
    assert rc["is_member_access"] is True
    assert rc["lang"] == "csharp"
    assert rc["receiver"] == "db"
    assert rc["receiver_type"] == "Ctx"
    assert rc["source_location"] == "L3"


def test_untypable_lowercase_receiver_records_no_raw_entry(tmp_path):
    # raw_calls ride the AST cache; an access the resolver could never bind
    # (no receiver type, not `this`/`base`, not a type name) is not recorded.
    p = tmp_path / "S.cs"
    p.write_text(
        "public class Svc {\n"
        "    public object Q(System.Collections.Generic.List<Row> rows) {\n"
        "        return rows.Select(u => u.Email);\n"
        "    }\n"
        "}\n"
    )
    entries = [rc for rc in extract_csharp(p)["raw_calls"] if rc.get("is_member_access")]
    assert entries == []


def test_invocation_callee_is_a_call_entry_not_an_access_entry(tmp_path):
    # `db.Save()` reaches the walk twice: once as the invocation, once as the
    # member_access_expression that is its callee. The callee must surface
    # only as the call — never as a second, dead access entry for `Save`.
    # The walk is pre-order, so the invocation records the callee's node id
    # before the access branch reaches it; nested and chained shapes must
    # keep that straight too.
    p = tmp_path / "S.cs"
    p.write_text(
        "public class Svc {\n"
        "    private Ctx db;\n"
        "    public void Q() { db.Save(); db.Log(db.Users); db.Users.Add(db.Orders.First()); }\n"
        "}\n"
    )
    raw = [rc for rc in extract_csharp(p)["raw_calls"] if rc.get("lang") == "csharp"]
    accesses = sorted(rc["callee"] for rc in raw if rc.get("is_member_access"))
    calls = sorted(rc["callee"] for rc in raw if not rc.get("is_member_access"))
    assert accesses == ["Orders", "Users", "Users"]
    assert calls == ["Add", "First", "Log", "Save"]
