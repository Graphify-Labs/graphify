"""C# explicit interface implementations are not ordinary overloads.

``int INative.Get(int a)`` can only be called through an ``INative``; a call on
the class (``svc.Get(1)``, ``this.Get(1)``, a bare ``Get(1)``) never reaches it.
Since every overload got its own node (#4584) the explicit implementation was
just another ``Get`` with the same argument count, so:

* in another partial file it competed with the public ``Get`` and won when its
  file came first: class-typed calls bound to it, and the common wrapper
  ``int INative.Get(int a) => this.Get(a);`` lost its call (resolved to itself);
* in the same file, and for ``IA.Get()`` / ``IB.Get()`` side by side, the
  implementations shared one node, so one body's calls were credited to the
  other and the wrapper's own call vanished.

Now an explicit implementation is a node of its own (its signature carries the
interface), it is never a name-call target, and the interface member
dispatches to it.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str], cache_root: Path | None = None):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        return extract([Path(n) for n in files], cache_root=cache_root or Path(tempfile.mkdtemp()))
    finally:
        os.chdir(old)


def _methods(result, name: str) -> list[dict]:
    return [
        n for n in result["nodes"]
        if str(n.get("label", "")).split("(")[0].rsplit(".", 1)[-1] == name
        and "(" in str(n.get("label", ""))
    ]


def _explicit(result, name: str) -> list[dict]:
    return [n for n in _methods(result, name) if (n.get("metadata") or {}).get("explicit_interface")]


def _public(result, name: str) -> list[dict]:
    return [n for n in _methods(result, name) if not (n.get("metadata") or {}).get("explicit_interface")]


def _edges(result, relation: str) -> set[tuple[str, str]]:
    return {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == relation}


def _calls_into(result, target_id: str) -> set[str]:
    return {s for s, t in _edges(result, "calls") if t == target_id}


_IFACE_AND_WRAPPER = """namespace Demo
{
    public interface INative { int Get(int a); }
    public partial class Service : INative
    {
        int INative.Get(int a) => this.Get(a);
    }
}
"""

_PUBLIC = """namespace Demo
{
    public partial class Service
    {
        public int Get(int a) { return a; }
    }
}
"""

_USER = """namespace Demo
{
    public class User
    {
        public int ViaClass(Service svc) { return svc.Get(1); }
        public int ViaInterface(INative n) { return n.Get(1); }
    }
}
"""


@pytest.mark.parametrize("wrapper_file", ["A.cs", "Z.cs"])
def test_partial_wrapper_calls_public_method_in_either_file_order(tmp_path, wrapper_file):
    r = _extract(tmp_path, {wrapper_file: _IFACE_AND_WRAPPER, "B.cs": _PUBLIC, "C.cs": _USER})
    [explicit] = _explicit(r, "Get")
    public = [n for n in _public(r, "Get") if "Service" in n["id"] or "service" in n["id"]]
    [public] = [n for n in public if n["source_file"].endswith("B.cs")]
    calls = _edges(r, "calls")
    # The wrapper's own call reaches the public method.
    assert (explicit["id"], public["id"]) in calls
    # A call on the class type never binds to the explicit implementation.
    assert not _calls_into(r, explicit["id"])
    [via_class] = [n for n in _methods(r, "ViaClass")]
    assert (via_class["id"], public["id"]) in calls


def test_interface_typed_call_still_names_the_interface_member(tmp_path):
    r = _extract(tmp_path, {"A.cs": _IFACE_AND_WRAPPER, "B.cs": _PUBLIC, "C.cs": _USER})
    [iface_get] = [n for n in _public(r, "Get") if n["source_file"].endswith("A.cs")]
    [via_iface] = _methods(r, "ViaInterface")
    assert (via_iface["id"], iface_get["id"]) in _edges(r, "calls")


def test_interface_member_dispatches_to_the_explicit_implementation(tmp_path):
    r = _extract(tmp_path, {"A.cs": _IFACE_AND_WRAPPER, "B.cs": _PUBLIC, "C.cs": _USER})
    [iface_get] = [n for n in _public(r, "Get") if n["source_file"].endswith("A.cs")]
    [explicit] = _explicit(r, "Get")
    [public] = [n for n in _public(r, "Get") if n["source_file"].endswith("B.cs")]
    dispatch = _edges(r, "dispatches_to")
    assert (iface_get["id"], explicit["id"]) in dispatch
    assert (iface_get["id"], public["id"]) not in dispatch


_SAME_FILE = """namespace Demo
{
    public interface INative { int Get(int a); }
    public class Service : INative
    {
        int INative.Get(int a) => this.Get(a);
        public int Get(int a) { return Helper(); }
        private int Helper() { return 1; }
    }
}
"""


def test_same_file_explicit_and_public_are_two_nodes(tmp_path):
    r = _extract(tmp_path, {"Service.cs": _SAME_FILE})
    [explicit] = _explicit(r, "Get")
    [public] = [n for n in _public(r, "Get") if n.get("source_location") != "L3"]
    [helper] = _methods(r, "Helper")
    assert explicit["id"] != public["id"]
    calls = _edges(r, "calls")
    assert (explicit["id"], public["id"]) in calls
    assert (public["id"], helper["id"]) in calls
    assert (explicit["id"], helper["id"]) not in calls


_TWO_INTERFACES = """namespace Demo
{
    public interface IA { int Get(); }
    public interface IB { int Get(); }
    public class Service : IA, IB
    {
        int IA.Get() { return Alpha(); }
        int IB.Get() { return Beta(); }
        private int Alpha() { return 1; }
        private int Beta() { return 2; }
    }
}
"""


def test_two_explicit_implementations_keep_their_own_calls(tmp_path):
    r = _extract(tmp_path, {"Service.cs": _TWO_INTERFACES})
    explicit = _explicit(r, "Get")
    assert len(explicit) == 2
    by_iface = {(n.get("metadata") or {}).get("explicit_interface"): n["id"] for n in explicit}
    assert set(by_iface) == {"IA", "IB"}
    [alpha] = _methods(r, "Alpha")
    [beta] = _methods(r, "Beta")
    calls = _edges(r, "calls")
    assert (by_iface["IA"], alpha["id"]) in calls
    assert (by_iface["IB"], beta["id"]) in calls
    assert (by_iface["IA"], beta["id"]) not in calls
    assert (by_iface["IB"], alpha["id"]) not in calls
    # Each interface member dispatches to its own implementation.
    iface = {n["source_location"]: n["id"] for n in _public(r, "Get")}
    dispatch = _edges(r, "dispatches_to")
    assert (iface["L3"], by_iface["IA"]) in dispatch
    assert (iface["L4"], by_iface["IB"]) in dispatch
    assert (iface["L3"], by_iface["IB"]) not in dispatch


def test_qualified_and_generic_interface_names_are_simple_names(tmp_path):
    src = """namespace Demo
{
    public interface IStore<T> { void Save(T item); }
    public class Store : Demo.IStore<int>
    {
        void Demo.IStore<int>.Save(int item) { Write(); }
        private void Write() { }
    }
}
"""
    r = _extract(tmp_path, {"Store.cs": src})
    [explicit] = _explicit(r, "Save")
    assert explicit["metadata"]["explicit_interface"] == "IStore"


def test_class_without_explicit_implementations_keeps_its_ids(tmp_path):
    # Ids of ordinary methods and overloads must not move.
    src = """namespace Demo
{
    public class Plain
    {
        public int Get(int a) { return a; }
        public int Get(int a, int b) { return Get(a); }
    }
}
"""
    r = _extract(tmp_path, {"Plain.cs": src})
    ids = sorted(n["id"] for n in _methods(r, "Get"))
    assert len(ids) == 2
    assert not _explicit(r, "Get")
    assert any(i.endswith("plain_get") for i in ids)


def test_prior_ast_cache_is_not_reused(tmp_path, monkeypatch):
    import graphify.cache as cache
    assert cache._AST_CACHE_SCHEMA > 45
    files = {"Service.cs": _TWO_INTERFACES}
    with monkeypatch.context() as old:
        old.setattr(cache, "_AST_CACHE_SCHEMA", 45)
        _extract(tmp_path, files, tmp_path / ".cache")
        # Strip the new metadata as if these entries predated this fix.
        for path in (tmp_path / ".cache").rglob("*.json"):
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace('"explicit_interface"', '"old_flag"'), encoding="utf-8")
    r = _extract(tmp_path, files, tmp_path / ".cache")
    assert len(_explicit(r, "Get")) == 2


def test_explicit_overloads_pair_with_their_interface_overloads(tmp_path):
    # Interface overloads are paired by signature; the explicit specifier must
    # not be part of the signature they are compared on.
    src = """namespace Demo
{
    public interface ILog
    {
        void Write(string message);
        void Write(System.Exception error);
    }
    public class Log : ILog
    {
        void ILog.Write(string message) { Text(); }
        void ILog.Write(System.Exception error) { Fault(); }
        private void Text() { }
        private void Fault() { }
    }
}
"""
    r = _extract(tmp_path, {"Log.cs": src})
    iface = {n["source_location"]: n["id"] for n in _public(r, "Write")}
    impl = {n["source_location"]: n["id"] for n in _explicit(r, "Write")}
    assert set(iface) == {"L5", "L6"} and set(impl) == {"L10", "L11"}
    dispatch = _edges(r, "dispatches_to")
    assert (iface["L5"], impl["L10"]) in dispatch
    assert (iface["L6"], impl["L11"]) in dispatch
    assert (iface["L5"], impl["L11"]) not in dispatch


def test_bare_call_skips_an_explicit_implementation_declared_first(tmp_path):
    # The explicit implementation comes first in the class, so a first-declared
    # pick by name would take it; the bare calls mean the public overloads.
    src = """namespace Demo
{
    public interface IStore { void Put(ref int a, ref int b, bool c); }
    public class Store : IStore
    {
        void IStore.Put(ref int a, ref int b, bool c) { Put(a, 1); }
        public void Put(int key, int value) { }
        public void Put(string key) { Put(1, 2); }
    }
}
"""
    r = _extract(tmp_path, {"Store.cs": src})
    [explicit] = _explicit(r, "Put")
    public = {n["source_location"]: n["id"] for n in _public(r, "Put")}
    two_args, one_arg = public["L7"], public["L8"]
    calls = _edges(r, "calls")
    assert (explicit["id"], two_args) in calls
    assert (one_arg, two_args) in calls
    assert not _calls_into(r, explicit["id"])
