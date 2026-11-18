"""A/B harness for candidate C# extension-call binding strategies (#4828).

The issue is a *design* question, not just a bug: binding ``x.Ext()`` to a
``this``-parameter method can be done with very different amounts of proof. This
module implements the candidates behind one engine so the only thing that varies
is a flag, and pairs them with fixtures whose ground truth is decidable from the
C# spec alone (``expect`` = a correct implementation must bind, ``forbid`` = a
correct implementation must not bind, ``optional`` = genuinely unknowable without
a BCL symbol table, never scored).

Strategy ids:

  S0  baseline            current main (no extension pass)
  S1  typed_exact         in-corpus receiver, extended type name == receiver name
  S2  typed_exact_scope   S1 + declaring namespace must be in scope at the call
  S3  typed_assignable    S2 + inherits/implements applicability + unresolved-base poison
  S4  roc_naive           S3 + out-of-corpus receivers, no deny-list
  S5  roc_guarded         S3 + out-of-corpus receivers with deny-list + uniqueness
  S6  reporter_patch      the issue's local patch: exact match, no scope, deny-list,
                          untyped-receiver rung
  S7  all_rungs           S5 + untyped-receiver rung
  S8  bare_name_control   control: bind any unique same-named method in the corpus
  S9  signature_parse     S3 but reads the extended type out of ``metadata.signature``
"""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from graphify import resolver_registry
from graphify.extract import extract, extract_csharp
from graphify.extractors.csharp import CsharpNameResolver

# --------------------------------------------------------------------------- #
# ground-truth fixtures
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Fixture:
    """One corpus with markers; expectations are markers, not line numbers.

    ``expect[m]  = (decl_file, decl_marker)``  must bind (compile-time certain)
    ``forbid``   markers that must NOT bind    (compile-time certain, any target)
    ``forbid_pairs[m] = (decl_file, decl_marker)`` must not bind to that target
    ``optional`` markers whose truth needs a BCL symbol table (never scored)
    """

    files: dict[str, str]
    expect: dict[str, tuple[str, str]] = field(default_factory=dict)
    forbid: list[str] = field(default_factory=list)
    forbid_pairs: dict[str, tuple[str, str]] = field(default_factory=dict)
    optional: list[str] = field(default_factory=list)
    note: str = ""


FIXTURES: dict[str, Fixture] = {
    # The reporter's exact corpus. `s.Mask()` is decidably an extension call;
    # `v.ToString().Mask()` is a chain whose inner return type is BCL, so the
    # *only* way to bind it is the untyped rung (kept as `expect` because the
    # issue states it, and scoring shows exactly which strategies reach it).
    "issue_repro": Fixture(
        files={
            "Ext.cs": (
                "namespace Ext {\n"
                "  public static class StringExtensions {\n"
                "    public static string Mask(this string s, char m = '*') { return s; } // D1\n"
                "  }\n"
                "}\n"
            ),
            "Svc.cs": (
                "using Ext;\n"
                "public class Svc {\n"
                "  public string A(string s) { return s.Mask(); } // E1\n"
                "  public string B(long v) { return v.ToString().Mask(); } // E2\n"
                "}\n"
            ),
        },
        expect={"// E1": ("Ext.cs", "// D1"), "// E2": ("Ext.cs", "// D1")},
        note="issue #4828 body",
    ),
    # Typed receiver, cross-file, overload chosen by argument count.
    "domain_cross_file": Fixture(
        files={
            "Model.cs": (
                "namespace App {\n"
                "  public class Widget { }\n"
                "  public static class WidgetExtensions {\n"
                "    public static void Paint(this Widget w) { } // D1\n"
                "    public static void Paint(this Widget w, int c) { } // D2\n"
                "  }\n"
                "}\n"
            ),
            "Use.cs": (
                "using App;\n"
                "namespace App {\n"
                "  public class Painter {\n"
                "    public void Run(Widget w) {\n"
                "      w.Paint(); // E1\n"
                "      w.Paint(3); // E2\n"
                "    }\n"
                "  }\n"
                "}\n"
            ),
        },
        expect={"// E1": ("Model.cs", "// D1"), "// E2": ("Model.cs", "// D2")},
    ),
    # Same file as the declaration: proves this is not a cross-file bug.
    "same_file": Fixture(
        files={
            "All.cs": (
                "namespace App {\n"
                "  public class Widget { }\n"
                "  public static class WExt {\n"
                "    public static void Paint(this Widget w) { } // D1\n"
                "  }\n"
                "  public class Painter {\n"
                "    public void Run(Widget w) { w.Paint(); } // E1\n"
                "  }\n"
                "}\n"
            ),
        },
        expect={"// E1": ("All.cs", "// D1")},
    ),
    # Applicability beyond name equality: base class and implemented interface.
    "base_and_interface": Fixture(
        files={
            "Domain.cs": (
                "namespace App {\n"
                "  public class Animal { }\n"
                "  public class Dog : Animal { }\n"
                "  public interface IStore { }\n"
                "  public class SqlStore : IStore { }\n"
                "  public static class Exts {\n"
                "    public static void Speak(this Animal a) { } // D1\n"
                "    public static void SaveStore(this IStore s) { } // D2\n"
                "  }\n"
                "}\n"
            ),
            "UseApp.cs": (
                "using App;\n"
                "namespace App {\n"
                "  public class Svc {\n"
                "    public void A(Dog d) { d.Speak(); } // E1\n"
                "    public void B(SqlStore s) { s.SaveStore(); } // E2\n"
                "  }\n"
                "}\n"
            ),
        },
        expect={"// E1": ("Domain.cs", "// D1"), "// E2": ("Domain.cs", "// D2")},
        note="exact-name matching cannot reach these",
    ),
    # The receiver's base is out of corpus: it may declare an instance member of
    # that name, which always beats an extension — so nothing may bind.
    "unresolved_base_poison": Fixture(
        files={
            "W.cs": (
                "namespace App {\n"
                "  public class W : ThirdParty.Base { }\n"
                "  public static class WExt {\n"
                "    public static void Reset(this W w) { } // D1\n"
                "  }\n"
                "}\n"
            ),
            "Use.cs": (
                "using App;\n"
                "namespace App {\n"
                "  public class U {\n"
                "    public void A(W w) { w.Reset(); } // E1\n"
                "  }\n"
                "}\n"
            ),
        },
        forbid=["// E1"],
        note="an out-of-corpus base may declare Reset() and win",
    ),
    # Two applicable extensions in the same scope: C# rejects the call.
    "ambiguous_same_scope": Fixture(
        files={
            "Common.cs": "public class Thing { }\n",
            "A.cs": (
                "namespace N1 { public static class X1 {\n"
                "  public static void Go(this Thing t) { } // D1\n"
                "} }\n"
            ),
            "B.cs": (
                "namespace N2 { public static class X2 {\n"
                "  public static void Go(this Thing t) { } // D2\n"
                "} }\n"
            ),
            "Use.cs": (
                "using N1;\n"
                "using N2;\n"
                "public class U {\n"
                "  public void Run(Thing o) { o.Go(); } // E1\n"
                "}\n"
            ),
        },
        forbid=["// E1"],
    ),
    # Nested-namespace preference: the inner declaration wins, per the spec's
    # innermost-scope-first lookup.
    "inner_scope_wins": Fixture(
        files={
            "Outer.cs": (
                "namespace N {\n"
                "  public class Thing { }\n"
                "  public static class OuterExt {\n"
                "    public static void Go(this Thing t) { } // D1\n"
                "  }\n"
                "}\n"
            ),
            "Inner.cs": (
                "namespace N.Inner { public static class InnerExt {\n"
                "  public static void Go(this Thing t) { } // D2\n"
                "} }\n"
            ),
            "Use.cs": (
                "using N;\n"
                "namespace N.Inner {\n"
                "  public class U { public void Run(Thing o) { o.Go(); } // E1\n"
                "  }\n"
                "}\n"
            ),
        },
        expect={"// E1": ("Inner.cs", "// D2")},
        forbid_pairs={"// E1": ("Outer.cs", "// D1")},
        note="bind D2, never D1",
    ),
    # The declaration's namespace is not imported at the call site.
    "out_of_scope": Fixture(
        files={
            "Other.cs": (
                "namespace Other {\n"
                "  public static class OExt {\n"
                "    public static void Secret(this App.Widget w) { } // D1\n"
                "  }\n"
                "}\n"
            ),
            "Model.cs": "namespace App { public class Widget { } }\n",
            "Use.cs": (
                "using App;\n"
                "namespace App {\n"
                "  public class U { public void Run(Widget w) { w.Secret(); } // E1\n"
                "  }\n"
                "}\n"
            ),
        },
        forbid=["// E1"],
    ),
    # Instance member always wins over an extension of the same name.
    "instance_wins": Fixture(
        files={
            "Cache.cs": (
                "namespace App {\n"
                "  public class Cache {\n"
                "    public object GetValue() { return null; } // D1\n"
                "  }\n"
                "  public static class CacheExt {\n"
                "    public static object GetValue(this Cache c) { return c; } // D2\n"
                "  }\n"
                "  public class U {\n"
                "    public object Run(Cache c) { return c.GetValue(); } // E1\n"
                "  }\n"
                "}\n"
            ),
        },
        expect={"// E1": ("Cache.cs", "// D1")},
        forbid_pairs={"// E1": ("Cache.cs", "// D2")},
        note="forbid D2; the D1 edge is baseline, the harness scores only added edges",
    ),
    # A BCL member name on an out-of-corpus receiver: unknowable without a symbol
    # table, so it is `forbid` for the guarded strategies and the cost of the
    # deny-list is visible as a missed `optional` call.
    "bcl_name_cost": Fixture(
        files={
            "E.cs": (
                "public static class ObjExt {\n"
                "  public static object GetValue(this object o) { return o; } // D1\n"
                "  public static object GetValue(this object o, object idx) { return o; } // D2\n"
                "}\n"
            ),
            "U.cs": (
                "using System.Reflection;\n"
                "public class U {\n"
                "  public object A(PropertyInfo p) { return p.GetValue(null); } // E1\n"
                "  public object B(object o) { return o.GetValue(); } // E2\n"
                "}\n"
            ),
        },
        forbid=["// E1"],
        optional=["// E2"],
        note="E1 is a real BCL instance member; no strategy may bind it to ObjExt",
    ),
    # Arity / optional / params, all on an in-corpus receiver. One caller per
    # call site: the graph keeps one edge per (caller, target) pair, so two calls
    # from one caller to the same declaration would collapse into one edge and
    # the call-site expectation would be unobservable.
    "arity": Fixture(
        files={
            "Arity.cs": (
                "namespace App {\n"
                "  public class W { }\n"
                "  public static class E {\n"
                "    public static void Log(this W w) { } // D1\n"
                "    public static void Log(this W w, int n) { } // D2\n"
                "    public static void Opt(this W w, int a, int b = 0) { } // D3\n"
                "    public static void Many(this W w, params object[] rest) { } // D4\n"
                "  }\n"
                "  public class U {\n"
                "    public void C1(W w) { w.Log(); } // E1\n"
                "    public void C2(W w) { w.Log(1); } // E2\n"
                "    public void C3(W w) { w.Opt(1); } // E3\n"
                "    public void C4(W w) { w.Opt(1, 2); } // E4\n"
                "    public void C5(W w) { w.Many(); } // E5\n"
                "    public void C6(W w) { w.Many(1, 2, 3); } // E6\n"
                "    public void C7(W w) { w.Opt(); } // F1\n"
                "    public void C8(W w) { w.Log(1, 2); } // F2\n"
                "  }\n"
                "}\n"
            ),
        },
        expect={
            "// E1": ("Arity.cs", "// D1"),
            "// E2": ("Arity.cs", "// D2"),
            "// E3": ("Arity.cs", "// D3"),
            "// E4": ("Arity.cs", "// D3"),
            "// E5": ("Arity.cs", "// D4"),
            "// E6": ("Arity.cs", "// D4"),
        },
        forbid=["// F1", "// F2"],
    ),
    # Primitive and third-party receivers: the reporter's headline case.
    "primitive_and_thirdparty": Fixture(
        files={
            "Ext.cs": (
                "namespace App {\n"
                "  public static class StringExt {\n"
                "    public static string Mask(this string s) { return s; } // D1\n"
                "    public static int Twice(this int i) { return i * 2; } // D2\n"
                "  }\n"
                "  public static class HttpExt {\n"
                "    public static string GetJson(this System.Net.Http.HttpClient c) { return \"\"; } // D3\n"
                "  }\n"
                "}\n"
            ),
            "Use.cs": (
                "using App;\n"
                "using System.Net.Http;\n"
                "namespace App {\n"
                "  public class U {\n"
                "    public string A(string s) { return s.Mask(); } // E1\n"
                "    public int B(int i) { return i.Twice(); } // E2\n"
                "    public string C(HttpClient c) { return c.GetJson(); } // E3\n"
                "  }\n"
                "}\n"
            ),
        },
        expect={
            "// E1": ("Ext.cs", "// D1"),
            "// E2": ("Ext.cs", "// D2"),
            "// E3": ("Ext.cs", "// D3"),
        },
    ),
    # A real class named T vs a generic `this T`: the non-generic exact match
    # wins; the generic one is the wildcard.
    "type_param_vs_class": Fixture(
        files={
            "T.cs": (
                "public class T { }\n"
                "public static class TExt {\n"
                "  public static void Go(this T t) { } // D1\n"
                "}\n"
                "public static class GenExt {\n"
                "  public static void Go<T>(this T t) { } // D2\n"
                "}\n"
            ),
            "U.cs": (
                "public class U {\n"
                "  public void A(T t) { t.Go(); } // E1\n"
                "}\n"
            ),
        },
        expect={"// E1": ("T.cs", "// D1")},
        note="signature-only resolution cannot tell the two `this T`s apart",
    ),
    # A generic extension reaches any receiver, including one the corpus never
    # declares. This is the wildcard rung, and it needs the `extended_is_type_param`
    # fact: the concrete class named T above must keep winning over it.
    "generic_wildcard": Fixture(
        files={
            "Gen.cs": (
                "public static class GenExt {\n"
                "  public static void Go<T>(this T t) { } // D1\n"
                "}\n"
            ),
            "U.cs": (
                "public class U {\n"
                "  public void A(int i) { i.Go(); } // E1\n"
                "}\n"
            ),
        },
        expect={"// E1": ("Gen.cs", "// D1")},
    ),
    # A capitalized untyped receiver is a type name (`Convert.ToInt32`), never a
    # variable an extension could apply to.
    "static_class_receiver": Fixture(
        files={
            "E.cs": (
                "public static class Conv {\n"
                "  public static int ToInt32(object o) { return 0; } // D1\n"
                "}\n"
                "public static class SExt {\n"
                "  public static int ToInt32(this string s) { return 0; } // D2\n"
                "}\n"
            ),
            "U.cs": (
                "public class U {\n"
                "  public int A(object o) { return Conv.ToInt32(o); } // B1\n"
                "  public int B(string s) { return s.ToInt32(); } // E1\n"
                "}\n"
            ),
        },
        expect={"// E1": ("E.cs", "// D2"), "// B1": ("E.cs", "// D1")},
        forbid_pairs={"// B1": ("E.cs", "// D2")},
        note="B1 is a correct baseline static call; it must never be re-bound to the extension",
    ),
    # A chained receiver with no type: the untyped rung's name proofs are the
    # whole evidence. Here a regular method elsewhere spells the name, so the
    # conservative rule refuses, and the call stays unbound (documented miss).
    "untyped_regular_name": Fixture(
        files={
            "Cache.cs": "public class Cache {\n  public void Flush() { } // D1\n}\n",
            "E.cs": (
                "public static class Ext {\n"
                "  public static void Flush(this string s) { } // D2\n"
                "}\n"
            ),
            "U.cs": (
                "public class U {\n"
                "  public void A(long v) { v.ToString().Flush(); } // F1\n"
                "}\n"
            ),
        },
        forbid=["// F1"],
        note="the regular-name guard refuses this binding on purpose",
    ),
    # The #1609 regression the fail-closed guard prevents: a member call on a type
    # that declares no such member must not bind to an unrelated same-named method.
    "god_node_control": Fixture(
        files={
            "Cache.cs": "public class Cache {\n  public void Save() { } // D1\n}\n",
            "Server.cs": "public class Server { }\n",
            "Use.cs": (
                "public class U {\n"
                "  public void Run(Server s) { s.Save(); } // F1\n"
                "}\n"
            ),
        },
        forbid=["// F1"],
        note="only the bare-name control may bind this; it is why the guard exists",
    ),
}

# The production deny-list, so the A/B record cannot drift from the rule the
# fix actually applies.
from graphify.extract import _CSHARP_BCL_MEMBER_NAMES as BCL_MEMBER_NAMES  # noqa: E402


# --------------------------------------------------------------------------- #
# strategy configs
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Strategy:
    id: str
    scope: bool = False
    assignable: bool = False
    poison: bool = False
    # None: refuse out-of-corpus receivers; "naive": allow; "guarded": deny-list
    # + no same-named regular method in the corpus.
    roc: str | None = None
    untyped: bool = False
    data: str = "metadata"  # "metadata" | "signature"
    bare_name: bool = False


STRATEGIES: dict[str, Strategy] = {
    s.id: s
    for s in (
        Strategy("S0_baseline"),
        Strategy("S1_typed_exact"),
        Strategy("S2_typed_exact_scope", scope=True),
        Strategy("S3_typed_assignable", scope=True, assignable=True, poison=True),
        Strategy("S4_roc_naive", scope=True, assignable=True, poison=True, roc="naive"),
        Strategy("S5_roc_guarded", scope=True, assignable=True, poison=True, roc="guarded"),
        Strategy("S6_reporter_patch", roc="guarded", untyped=True),
        Strategy("S7_all_rungs", scope=True, assignable=True, poison=True,
                 roc="guarded", untyped=True),
        Strategy("S8_bare_name_control", bare_name=True),
        Strategy("S9_signature_parse", scope=True, assignable=True, poison=True,
                 data="signature"),
    )
}

STRATEGY_IDS = list(STRATEGIES)


# --------------------------------------------------------------------------- #
# index + engine
# --------------------------------------------------------------------------- #


def _key(label: str) -> str:
    return re.sub(r"\W+", "", str(label))


def _site(node: dict) -> tuple[str, str]:
    return str(node.get("source_file") or ""), str(node.get("source_location") or "")


@dataclass
class ExtDecl:
    method_id: str
    name_key: str
    extended: str
    extended_arity: int
    is_type_param: bool
    arity: int
    low: int
    variadic: bool
    namespace: str


def _signature_extended_type(meta: dict) -> tuple[str, int, bool]:
    """Derive the extended type from ``metadata.signature`` (S9's data source).

    Returns ``(simple_name, generic_arity, is_unknown)``. A ``this T`` where T is
    a method type parameter is indistinguishable from a class named T here: the
    signature only carries the parameter *text*, not the declaration's type-param
    names, so S9 has to guess (it guesses "not a type param").
    """
    sig = str(meta.get("signature") or "")
    if ":" in sig.split(",", 1)[0]:
        sig = sig.split(":", 1)[1]
    depth = 0
    first = ""
    for ch in sig:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        elif ch == "," and depth == 0:
            break
        first += ch
    first = first.strip()
    if not first.startswith("this "):
        return "", 0, True
    type_text = first[len("this "):].strip()
    if not type_text:
        return "", 0, True
    arity = 0
    depth = 0
    for ch in type_text:
        if ch == "<":
            if depth == 0:
                arity = 1
            elif depth == 1 and ch == ",":
                arity += 1
            depth += 1
        elif ch == ">":
            depth -= 1
    base = type_text.split("<", 1)[0]
    simple = base.rsplit(".", 1)[-1]
    return simple, arity, False


def _build_decls(nodes: list[dict], strategy: Strategy) -> list[ExtDecl]:
    decls: list[ExtDecl] = []
    for n in nodes:
        meta = n.get("metadata") or {}
        if not isinstance(meta, dict):
            continue
        if not n.get("source_file"):
            continue
        if strategy.data == "metadata":
            if not meta.get("extension"):
                continue
            extended = str(meta.get("extended_type") or "")
            ext_arity = int(meta.get("extended_type_arity") or 0)
            is_tp = bool(meta.get("extended_is_type_param"))
        else:
            extended, ext_arity, unknown = _signature_extended_type(meta)
            if unknown:
                continue
            is_tp = False
        arity = meta.get("arity")
        if not isinstance(arity, int):
            continue
        low = meta.get("min_arity", arity)
        decls.append(ExtDecl(
            method_id=n["id"],
            name_key=_key(n.get("label", "")),
            extended=extended,
            extended_arity=ext_arity,
            is_type_param=is_tp,
            arity=arity,
            low=low if isinstance(low, int) else arity,
            variadic=bool(meta.get("variadic")),
            namespace=str(meta.get("namespace") or ""),
        ))
    return decls


class _Graph:
    """The graph facts every strategy is allowed to use."""

    def __init__(self, nodes: list[dict], edges: list[dict]) -> None:
        self.nodes = nodes
        self.node_by_id = {n["id"]: n for n in nodes if n.get("id")}
        contained = {e.get("target") for e in edges if e.get("relation") == "contains"}
        self.is_type = {
            n["id"] for n in nodes
            if n.get("id") in contained and n.get("source_file") and n.get("id") in self.node_by_id
        }
        self.type_index: dict[str, list[str]] = {}
        for nid in self.is_type:
            self.type_index.setdefault(_key(self.node_by_id[nid].get("label", "")), []).append(nid)

        self.owner: dict[str, str] = {}
        self.methods_by_owner: dict[tuple[str, str], list[str]] = {}
        for e in edges:
            if e.get("relation") != "method":
                continue
            owner, mid = e.get("source"), e.get("target")
            mn = self.node_by_id.get(mid)
            if not owner or mn is None:
                continue
            self.owner.setdefault(mid, owner)
            self.methods_by_owner.setdefault((owner, _key(mn.get("label", ""))), []).append(mid)

        self.supers: dict[str, set[str]] = {}
        self.supers_unresolved: dict[str, bool] = {}
        for e in edges:
            if e.get("relation") not in ("inherits", "implements"):
                continue
            src, tgt = e.get("source"), e.get("target")
            if not src or not tgt:
                continue
            self.supers.setdefault(src, set()).add(tgt)

        # "a regular method in the corpus has this name" — extensions excluded,
        # since they are the thing being resolved.
        ext_ids = {
            n["id"] for n in nodes
            if isinstance(n.get("metadata"), dict) and n["metadata"].get("extension")
        }
        self.methods_by_name: dict[str, list[str]] = {}
        for (owner, key), mids in self.methods_by_owner.items():
            self.methods_by_name.setdefault(key, []).extend(mids)

        self.regular_method_names = {
            _key(self.node_by_id[mid].get("label", ""))
            for mids in self.methods_by_owner.values() for mid in mids
            if mid not in ext_ids
        }

    def type_closure(self, nid: str) -> tuple[set[str], bool]:
        """(self + supertypes, unresolved?) — a source-less super is a stub."""
        out: set[str] = set()
        unresolved = False
        stack = [nid]
        while stack:
            cur = stack.pop()
            if cur in out:
                continue
            out.add(cur)
            for sup in self.supers.get(cur, ()):
                sn = self.node_by_id.get(sup)
                if sn is None or not sn.get("source_file"):
                    unresolved = True
                    continue
                stack.append(sup)
        return out, unresolved

    def has_instance_member(self, nid: str, name_key: str) -> bool:
        closure, _ = self.type_closure(nid)
        return any((owner, name_key) in self.methods_by_owner for owner in closure)

    def resolve_type(self, name: str | None, caller_node: dict | None,
                     src_file: str, resolver: CsharpNameResolver) -> tuple[str | None, bool]:
        if not name:
            return None, False
        if caller_node is not None:
            nid, decisive = resolver.resolve_type_name(name, caller_node, src_file)
            if nid:
                return nid, True
            if decisive:
                return None, True
        hits = self.type_index.get(_key(name), [])
        return (hits[0], True) if len(hits) == 1 else (None, False)


def apply_strategy(
    strategy: Strategy,
    per_file: list[dict],
    nodes: list[dict],
    edges: list[dict],
) -> list[dict]:
    """Run one candidate over the extraction and return the edges it adds."""
    if strategy.id.startswith("S0"):
        return []

    g = _Graph(nodes, edges)
    resolver = CsharpNameResolver(nodes, edges)
    decls = _build_decls(nodes, strategy)
    existing = {(e.get("source"), e.get("target")) for e in edges}
    added: list[dict] = []

    for result in per_file:
        for rc in result.get("raw_calls") or []:
            if rc.get("lang") != "csharp" or not rc.get("is_member_call"):
                continue
            caller = rc.get("caller_nid")
            callee = rc.get("callee")
            if not caller or not callee or caller not in g.node_by_id:
                continue
            name_key = _key(callee)
            argc = rc.get("arity")
            if not isinstance(argc, int):
                continue
            src_file = str(rc.get("source_file") or "")
            caller_node = g.node_by_id.get(caller)

            recv_type = rc.get("receiver_type")
            chain = rc.get("receiver_chain") or []
            receiver = rc.get("receiver")
            if receiver == "base":
                continue
            if not recv_type and chain:
                recv_type = chain[0]
            if not recv_type and receiver == "this":
                owner = g.owner.get(caller)
                recv_type = (g.node_by_id.get(owner) or {}).get("label") if owner else None

            recv_nid: str | None = None
            roc = False  # receiver type is not declared in this corpus
            if recv_type:
                recv_nid, decisive = g.resolve_type(recv_type, caller_node, src_file, resolver)
                if recv_nid is None:
                    if decisive:
                        # The receiver's own type is ambiguous at this call site:
                        # nothing about the call is provable, so bail rather than
                        # treat it as an out-of-corpus receiver.
                        continue
                    roc = True
                    # A capitalized receiver that is not a typed local is a type
                    # name (`Convert.ToInt32`) — never a value an extension can
                    # apply to.
                    if receiver and not rc.get("receiver_type") and str(receiver)[:1].isupper():
                        continue

            # Instance members always win over extensions.
            if recv_nid and g.has_instance_member(recv_nid, name_key):
                continue
            # An out-of-corpus base may declare the member; cannot prove anything.
            if strategy.poison and recv_nid:
                _, unresolved = g.type_closure(recv_nid)
                if unresolved:
                    continue

            if strategy.bare_name:
                # Control: the pre-#1609 behaviour — resolve a member call by the
                # bare method name, ignoring the receiver entirely. Restricted to
                # a corpus-wide unique name, which is exactly the fallback the
                # god-node guard removed.
                by_name = g.methods_by_name.get(name_key, [])
                if len(by_name) != 1:
                    continue
                target = by_name[0]
                if (caller, target) in existing:
                    continue
                existing.add((caller, target))
                added.append(_edge_id(caller, target, rc, 0.55))
                continue

            candidates = [d for d in decls if d.name_key == name_key]
            if not candidates:
                continue

            # Scope: walk the enclosing namespace declarations outward, and at
            # each level consider (a) that namespace itself and (b) the usings
            # declared at that level. The first level with candidates wins; more
            # than one candidate at that level is ambiguous (dropped later).
            if strategy.scope:
                levels = resolver.visible_namespaces(caller_node, src_file)
                for visible in levels:
                    at_level = [d for d in candidates if d.namespace in visible]
                    if at_level:
                        candidates = at_level
                        break
                else:
                    candidates = []
                if not candidates:
                    continue

            wildcards = [d for d in candidates
                         if d.is_type_param or d.extended in ("object", "dynamic")]
            if recv_type:
                if strategy.assignable and recv_nid is not None:
                    closure, _ = g.type_closure(recv_nid)
                    names = {_key(g.node_by_id[c].get("label", "")) for c in closure}
                    exact = [d for d in candidates
                             if not d.is_type_param and _key(d.extended) == _key(recv_type)]
                    parents = [d for d in candidates
                               if not d.is_type_param and _key(d.extended) in names
                               and _key(d.extended) != _key(recv_type)]
                    applicable = exact or parents
                else:
                    applicable = [d for d in candidates
                                  if not d.is_type_param
                                  and _key(d.extended) == _key(recv_type)]
                if not applicable:
                    applicable = wildcards
                if not applicable:
                    continue
                if roc:
                    if strategy.roc is None:
                        continue
                    if strategy.roc == "guarded":
                        if name_key in g.regular_method_names:
                            continue
                        if callee in BCL_MEMBER_NAMES:
                            continue
                    applicable = [d for d in applicable if True]
            else:
                # Untyped receiver (a chain): only the explicit untyped rung.
                if not strategy.untyped:
                    continue
                if name_key in g.regular_method_names:
                    continue
                if callee in BCL_MEMBER_NAMES:
                    continue
                applicable = candidates

            fits = [d for d in applicable
                    if d.low <= argc and (argc <= d.arity - 1 or d.variadic)]
            if len(fits) != 1:
                continue
            cand = fits[0]
            if (caller, cand.method_id) in existing:
                continue
            existing.add((caller, cand.method_id))
            score = 0.85 if not (roc or recv_type is None) else 0.75
            added.append(_edge(caller, cand, rc, score))
    return added


def _edge(caller: str, decl: ExtDecl, rc: dict, score: float) -> dict:
    return _edge_id(caller, decl.method_id, rc, score)


def _edge_id(caller: str, target: str, rc: dict, score: float) -> dict:
    return {
        "source": caller,
        "target": target,
        "relation": "calls",
        "context": "call",
        "confidence": "INFERRED",
        "confidence_score": score,
        "source_file": rc.get("source_file", ""),
        "source_location": rc.get("source_location"),
        "weight": 1.0,
    }


# --------------------------------------------------------------------------- #
# scoring helpers used by the tests
# --------------------------------------------------------------------------- #


def line_of(text: str, marker: str) -> str:
    """The ``L<n>`` location of the single line carrying ``marker``."""
    hits = [i for i, line in enumerate(text.splitlines(), start=1) if marker in line]
    assert len(hits) == 1, (marker, hits)
    return f"L{hits[0]}"


def marker_at_line(text: str, location: str) -> str:
    n = int(str(location).lstrip("L"))
    line = text.splitlines()[n - 1]
    for token in re.findall(r"//\s*[A-Z]\d+", line):
        return token
    raise AssertionError(f"no marker on {location}: {line!r}")


# --------------------------------------------------------------------------- #
# corpus extraction + scoring
# --------------------------------------------------------------------------- #

_CORPORA: dict[tuple[str, bool], dict] = {}


def corpus(name: str, *, production_extension: bool = True) -> dict:
    """Extract a fixture once.

    ``production_extension=False`` removes the production extension resolver from
    the registry for the extraction, so the candidate strategies are measured on
    the same nominal graph no matter which stage of the fix has landed. It is the
    only way for the decision record to stay comparable across commits.
    """
    key = (name, production_extension)
    if key in _CORPORA:
        return _CORPORA[key]
    fixture = FIXTURES[name]
    tmp = Path(tempfile.mkdtemp(prefix=f"csharp-ext-{name}-"))
    for filename, body in fixture.files.items():
        path = tmp / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    saved = resolver_registry._REGISTRY[:]
    if not production_extension:
        resolver_registry._REGISTRY[:] = [
            r for r in saved if r.name != "csharp_extension_calls"
        ]
    old = os.getcwd()
    try:
        os.chdir(tmp)
        paths = [Path(f) for f in fixture.files]
        result = extract(paths, cache_root=Path(tempfile.mkdtemp()))
        per_file = [extract_csharp(Path(f)) for f in fixture.files]
    finally:
        resolver_registry._REGISTRY[:] = saved
        os.chdir(old)
    payload = {
        "fixture": fixture,
        "nodes": result["nodes"],
        "edges": result["edges"],
        "per_file": per_file,
    }
    _CORPORA[key] = payload
    return payload


def _bindings_from_edges(fixture: Fixture, nodes: list[dict], edges: list[dict]):
    """Map `calls` edges to ``(call_marker, (target_file, target_marker))``.

    Edges whose source or target line has no marker are returned as phantoms: a
    strategy must never invent a call site, and a fixture must not silently
    accept an edge it did not describe.
    """
    by_id = {n["id"]: n for n in nodes}
    bindings: set[tuple[str, tuple[str, str]]] = set()
    phantoms: list[dict] = []
    for edge in edges:
        if edge.get("relation") != "calls":
            continue
        src_file = str(edge.get("source_file") or "")
        if src_file not in fixture.files:
            phantoms.append(edge)
            continue
        try:
            call_marker = marker_at_line(fixture.files[src_file], str(edge.get("source_location") or ""))
        except AssertionError:
            phantoms.append(edge)
            continue
        target = by_id.get(edge.get("target"))
        if target is None or str(target.get("source_file") or "") not in fixture.files:
            phantoms.append(edge)
            continue
        try:
            t_marker = marker_at_line(
                fixture.files[str(target["source_file"])],
                str(target.get("source_location") or ""),
            )
        except AssertionError:
            phantoms.append(edge)
            continue
        bindings.add((call_marker, (str(target["source_file"]), t_marker)))
    return bindings, phantoms


def expected_pairs(name: str) -> set[tuple[str, tuple[str, str]]]:
    return {(marker, target) for marker, target in FIXTURES[name].expect.items()}


def strategy_bindings(name: str, strategy_id: str) -> dict:
    """Final graph of one candidate strategy + its violations."""
    data = corpus(name, production_extension=False)
    fixture: Fixture = data["fixture"]
    added = apply_strategy(STRATEGIES[strategy_id], data["per_file"], data["nodes"], data["edges"])
    bindings, phantoms = _bindings_from_edges(fixture, data["nodes"], list(data["edges"]) + list(added))
    violations: set = set(phantoms)
    for call_marker, target in bindings:
        if call_marker in fixture.forbid:
            violations.add((call_marker, target))
        if fixture.forbid_pairs.get(call_marker) == target:
            violations.add((call_marker, target))
    return {"bindings": bindings, "added": added, "phantoms": phantoms, "violations": violations}


def graph_bindings(name: str) -> dict:
    """Final graph as the production pipeline builds it."""
    data = corpus(name)
    fixture: Fixture = data["fixture"]
    bindings, phantoms = _bindings_from_edges(fixture, data["nodes"], data["edges"])
    violations: set = set(phantoms)
    for call_marker, target in bindings:
        if call_marker in fixture.forbid:
            violations.add((call_marker, target))
        if fixture.forbid_pairs.get(call_marker) == target:
            violations.add((call_marker, target))
    return {"bindings": bindings, "phantoms": phantoms, "violations": violations}
