"""Swift generic type parameters must not mint sourceless god nodes.

A `struct Stack<Element>` / `func map<R>(...)` binds `Element`/`R` as local
names, not corpus symbols. The Swift type-ref pass appended the bare
identifiers used in a signature or stored-property type as type references and
ran them through the sourceless-stub path, so every generic type/function in
the corpus collapsed its `T` onto one bare `t` node — a god node (single-letter
type params are not in the analyzer's builtin-noise filter). C#, Java,
TypeScript, Kotlin, Scala, C++, and Go already exclude their type parameters;
Swift now matches.
"""
from pathlib import Path

from graphify.extract import extract


def _sourceless(r):
    return sorted({(n["id"], n.get("label")) for n in r["nodes"] if not n.get("source_file")})


def test_generic_struct_and_method_type_params_mint_no_stub(tmp_path):
    (tmp_path / "s.swift").write_text(
        "struct Stack<Element> {\n"
        "    var items: [Element]\n"
        "    func peek() -> Element? { return items.last }\n"
        "    func map<R>(_ f: (Element) -> R) -> [R] { return [] }\n"
        "}\n"
    )
    r = extract([tmp_path / "s.swift"], cache_root=tmp_path, parallel=False)
    assert _sourceless(r) == []
    assert not any(e.get("target") in ("element", "r") for e in r["edges"])


def test_constrained_param_dropped_but_real_type_kept(tmp_path):
    # `T` is a parameter (dropped); a genuine user type in the signature still
    # references.
    (tmp_path / "s.swift").write_text(
        "struct User { var id: Int }\n"
        "func wrap<T: Equatable>(_ x: T, u: User) -> User { return u }\n"
    )
    r = extract([tmp_path / "s.swift"], cache_root=tmp_path, parallel=False)
    assert not any(e.get("target") == "t" for e in r["edges"])
    refs = {
        rn["label"]
        for e in r["edges"] if e.get("relation") == "references"
        for rn in r["nodes"] if rn["id"] == e["target"]
    }
    assert "User" in refs
