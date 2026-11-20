"""C#: a simple type name resolves against the nested types of the enclosing types.

Inside ``Outer`` a nested type sees its sibling nested types by simple name
(``class Derived : Base`` with both nested in ``Outer``). The base list used to
land on a sourceless placeholder, so every inherited-member lookup through it
bailed: a field or property declared on the base, ``this.M()`` and ``base.M()``.
A field inherited from the base is also tried before the receiver is read as a
type name.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path: Path, files: dict[str, str]) -> dict:
    paths = []
    for name, text in files.items():
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    result = extract(paths, root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    assert not result["failed_sources"]
    return result


def _node(result: dict, label: str, file: str, line: int) -> str:
    hits = [
        n["id"] for n in result["nodes"]
        if n.get("label") == label
        and Path(n.get("source_file") or "").name == file
        and n.get("source_location") == f"L{line}"
    ]
    assert len(hits) == 1, (label, file, line, hits)
    return hits[0]


def _targets(result: dict, source: str, relation: str) -> set[str]:
    return {e["target"] for e in result["edges"] if e["source"] == source and e["relation"] == relation}


SIBLING_SAME_FILE = """namespace Demo
{
    public static partial class Outer
    {
        public class Base { protected Store _store; }
        public class Derived : Base { public bool Save() { return this._store.Write(); } }
        public class Store { public bool Write() { return true; } }
    }
}
"""


def test_sibling_nested_base_resolves_and_inherited_field_is_typed(tmp_path: Path):
    result = _extract(tmp_path, {"A.cs": SIBLING_SAME_FILE})
    derived = _node(result, "Derived", "A.cs", 6)
    assert _targets(result, derived, "inherits") == {_node(result, "Base", "A.cs", 5)}
    save = _node(result, ".Save()", "A.cs", 6)
    assert _node(result, ".Write()", "A.cs", 7) in _targets(result, save, "calls")


def test_sibling_nested_base_in_another_file(tmp_path: Path):
    result = _extract(tmp_path, {
        "A.cs": """namespace Demo
{
    public static partial class Outer
    {
        public class Base { protected Store _store; }
        public class Store { public bool Write() { return true; } }
    }
}
""",
        "B.cs": """namespace Demo
{
    public static partial class Outer
    {
        public class Derived : Base { public bool Save() { return _store.Write(); } }
    }
}
""",
    })
    derived = _node(result, "Derived", "B.cs", 5)
    assert _targets(result, derived, "inherits") == {_node(result, "Base", "A.cs", 5)}
    save = _node(result, ".Save()", "B.cs", 5)
    assert _node(result, ".Write()", "A.cs", 6) in _targets(result, save, "calls")


def test_this_and_base_calls_through_sibling_nested_base(tmp_path: Path):
    result = _extract(tmp_path, {"A.cs": """namespace Demo
{
    public class Outer
    {
        public class Base { public virtual bool Helper() { return true; } public bool Ping() { return true; } }
        public class Derived : Base
        {
            public bool A() { return this.Ping(); }
            public override bool Helper() { return base.Helper(); }
        }
    }
}
"""})
    base_helper = _node(result, ".Helper()", "A.cs", 5)
    ping = _node(result, ".Ping()", "A.cs", 5)
    assert ping in _targets(result, _node(result, ".A()", "A.cs", 8), "calls")
    assert base_helper in _targets(result, _node(result, ".Helper()", "A.cs", 9), "calls")


def test_enclosing_nested_type_shadows_namespace_type(tmp_path: Path):
    # C# looks in the enclosing types before the namespace: `Store` inside
    # `Outer` is `Outer.Store`, not the namespace-level `Demo.Store`.
    result = _extract(tmp_path, {"A.cs": """namespace Demo
{
    public class Store { public bool Write() { return false; } }
    public class Outer
    {
        public class Store { public bool Write() { return true; } }
        public class Base { protected Store _store; }
        public class Derived : Base { public bool Save() { return _store.Write(); } }
    }
}
"""})
    save_calls = _targets(result, _node(result, ".Save()", "A.cs", 8), "calls")
    assert _node(result, ".Write()", "A.cs", 6) in save_calls
    assert _node(result, ".Write()", "A.cs", 3) not in save_calls


def test_same_named_sibling_bases_under_two_owners(tmp_path: Path):
    result = _extract(tmp_path, {"A.cs": """namespace Demo
{
    public class Left
    {
        public class Base { public bool Ping() { return true; } }
        public class Derived : Base { public bool A() { return this.Ping(); } }
    }
    public class Right
    {
        public class Base { public bool Ping() { return false; } }
        public class Derived : Base { public bool B() { return this.Ping(); } }
    }
}
"""})
    assert _targets(result, _node(result, "Derived", "A.cs", 6), "inherits") == {_node(result, "Base", "A.cs", 5)}
    assert _targets(result, _node(result, "Derived", "A.cs", 11), "inherits") == {_node(result, "Base", "A.cs", 10)}
    assert _node(result, ".Ping()", "A.cs", 5) in _targets(result, _node(result, ".A()", "A.cs", 6), "calls")
    assert _node(result, ".Ping()", "A.cs", 10) in _targets(result, _node(result, ".B()", "A.cs", 11), "calls")


def test_nested_type_inherited_by_the_enclosing_type(tmp_path: Path):
    result = _extract(tmp_path, {"A.cs": """namespace Demo
{
    public class OuterBase
    {
        public class Base { public bool Ping() { return true; } }
    }
    public class Outer : OuterBase
    {
        public class Derived : Base { public bool A() { return this.Ping(); } }
    }
}
"""})
    assert _targets(result, _node(result, "Derived", "A.cs", 9), "inherits") == {_node(result, "Base", "A.cs", 5)}


def test_sibling_two_levels_up(tmp_path: Path):
    result = _extract(tmp_path, {"A.cs": """namespace Demo
{
    public class Outer
    {
        public class Base { public bool Ping() { return true; } }
        public class Mid
        {
            public class Derived : Base { public bool A() { return this.Ping(); } }
        }
    }
}
"""})
    assert _targets(result, _node(result, "Derived", "A.cs", 8), "inherits") == {_node(result, "Base", "A.cs", 5)}
    assert _node(result, ".Ping()", "A.cs", 5) in _targets(result, _node(result, ".A()", "A.cs", 8), "calls")


def test_field_of_out_of_corpus_base_is_not_guessed(tmp_path: Path):
    # The base is declared outside the corpus, so `_store` may be declared there
    # with any type: no edge to the in-corpus `Store`.
    result = _extract(tmp_path, {"A.cs": """namespace Demo
{
    public class Derived : External.Base
    {
        public bool Save() { return _store.Write(); }
    }
    public class Store { public bool Write() { return true; } }
}
"""})
    assert not _targets(result, _node(result, ".Save()", "A.cs", 5), "calls")


def test_partial_halves_that_both_resolve_the_base_keep_one_edge(tmp_path: Path):
    half = """using static App.Agents;
namespace App
{
    public static partial class Agents
    {
        public partial class Derived : Base { public void MEMBER() {} }
    }
}
"""
    result = _extract(tmp_path, {
        "Base.cs": """namespace App
{
    public static partial class Agents
    {
        public class Base { public virtual void Init() {} }
    }
}
""",
        "DA.cs": half.replace("MEMBER", "One"),
        "DB.cs": half.replace("MEMBER", "Two"),
    })
    derived = [n["id"] for n in result["nodes"] if n.get("label") == "Derived" and n.get("source_file")]
    assert len(set(derived)) == 1
    edges = [e for e in result["edges"] if e["relation"] == "inherits" and e["source"] == derived[0]]
    assert [e["target"] for e in edges] == [_node(result, "Base", "Base.cs", 5)]


def test_factory_returning_its_own_nested_type_keeps_the_construction(tmp_path: Path):
    # The factory names `Ticket` as its return type (a `references` edge to the
    # now-resolved nested type) and also builds one with `new Ticket(...)`.
    # The reference must not stand in for the call or its constructor.
    result = _extract(tmp_path, {"A.cs": """namespace Demo
{
    public class Service
    {
        private class Ticket
        {
            public static Ticket Create() { return new Ticket(1); }
            private Ticket(int id) { }
        }
    }
}
"""})
    create = _node(result, ".Create()", "A.cs", 7)
    ticket = _node(result, "Ticket", "A.cs", 5)
    assert ticket in _targets(result, create, "references")
    calls = _targets(result, create, "calls")
    assert ticket in calls
    assert _node(result, ".Ticket()", "A.cs", 8) in calls


def test_construction_of_a_type_named_in_the_signature(tmp_path: Path):
    # Same shape without nesting: a method returning `Ticket` that builds one.
    result = _extract(tmp_path, {
        "A.cs": """namespace Demo
{
    public class Service
    {
        public Ticket Make() { return new Ticket(1); }
    }
}
""",
        "B.cs": """namespace Demo
{
    public class Ticket
    {
        public Ticket(int id) { }
    }
}
""",
    })
    make = _node(result, ".Make()", "A.cs", 5)
    calls = _targets(result, make, "calls")
    assert _node(result, "Ticket", "B.cs", 3) in calls
    assert _node(result, ".Ticket()", "B.cs", 5) in calls


def test_field_type_names_the_types_own_nested_type_first(tmp_path: Path):
    # Inside `Inner`, `Node` is `Inner.Node`, not the outer `Outer.Node`.
    result = _extract(tmp_path, {"A.cs": """namespace Demo
{
    public class Outer
    {
        public class Node { }
        public class Inner
        {
            public class Node { }
            private Node _head;
        }
    }
}
"""})
    inner = _node(result, "Inner", "A.cs", 6)
    refs = _targets(result, inner, "references")
    assert _node(result, "Node", "A.cs", 8) in refs
    assert _node(result, "Node", "A.cs", 5) not in refs


def test_enclosing_nested_type_wins_over_using_alias(tmp_path: Path):
    # A `using` alias belongs to the namespace lookup, which comes after the
    # enclosing types.
    result = _extract(tmp_path, {"A.cs": """using Store = Other.Remote;
namespace Demo
{
    public class Outer
    {
        public class Store { public bool Write() { return true; } }
        public class Derived
        {
            private Store _s;
            public bool Save() { return _s.Write(); }
        }
    }
}
namespace Other { public class Remote { public bool Write() { return false; } } }
"""})
    save_calls = _targets(result, _node(result, ".Save()", "A.cs", 10), "calls")
    assert _node(result, ".Write()", "A.cs", 6) in save_calls
    assert _node(result, ".Write()", "A.cs", 14) not in save_calls


def test_out_of_corpus_base_does_not_hide_outer_nested_types(tmp_path: Path):
    result = _extract(tmp_path, {"A.cs": """namespace Demo
{
    public class Outer
    {
        public class Store { }
        public class Inner : External.Base
        {
            public Store Get() { return null; }
        }
    }
}
"""})
    get = _node(result, ".Get()", "A.cs", 8)
    assert _node(result, "Store", "A.cs", 5) in _targets(result, get, "references")
