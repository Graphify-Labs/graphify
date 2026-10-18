"""Go generic type parameters must not mint sourceless god nodes.

A `[T any]` type parameter is a local binding, not a corpus symbol. The Go
type-ref pass appended the bare `T`/`R` identifiers used in a signature, field,
or interface method as type references and ran them through the sourceless-stub
path, so every generic function/type in the corpus collapsed its `T` onto one
bare `t` node — a god node that pollutes god-node rankings (single-letter type
params are not in the analyzer's builtin-noise filter). TS, C#, and Java
already exclude their type parameters; Go now matches.
"""
from pathlib import Path

from graphify.extract import extract


def _sourceless(r):
    return sorted({(n["id"], n.get("label")) for n in r["nodes"] if not n.get("source_file")})


def test_generic_function_type_params_mint_no_stub(tmp_path):
    (tmp_path / "g.go").write_text(
        "package p\n"
        "func Map[T any, R comparable](x T, f func(T) R) R {\n"
        "    var r R\n"
        "    return r\n"
        "}\n"
    )
    r = extract([tmp_path / "g.go"], cache_root=tmp_path, parallel=False)
    assert _sourceless(r) == []
    assert not any(e.get("target") in ("t", "r") for e in r["edges"])


def test_generic_struct_and_method_type_params_mint_no_stub(tmp_path):
    (tmp_path / "g.go").write_text(
        "package p\n"
        "type Box[T any] struct { v T }\n"
        "func (b Box[T]) Get() T { return b.v }\n"
    )
    r = extract([tmp_path / "g.go"], cache_root=tmp_path, parallel=False)
    assert _sourceless(r) == []
    assert not any(e.get("target") == "t" for e in r["edges"])


def test_generic_interface_type_params_mint_no_stub(tmp_path):
    (tmp_path / "g.go").write_text(
        "package p\n"
        "type Container[T any] interface {\n"
        "    Add(item T)\n"
        "    Items() []T\n"
        "}\n"
    )
    r = extract([tmp_path / "g.go"], cache_root=tmp_path, parallel=False)
    assert _sourceless(r) == []
    assert not any(e.get("target") == "t" for e in r["edges"])


def test_user_and_container_types_still_referenced(tmp_path):
    # The guard drops only the declared type parameter; a real user type and the
    # generic container head it instantiates still reference.
    (tmp_path / "g.go").write_text(
        "package p\n"
        "type User struct { name string }\n"
        "type Box[T any] struct { v T }\n"
        "func Wrap[T any](u User) Box[T] { return Box[T]{} }\n"
    )
    r = extract([tmp_path / "g.go"], cache_root=tmp_path, parallel=False)
    targets = {
        r_n["label"]
        for e in r["edges"] if e.get("relation") == "references"
        for r_n in r["nodes"] if r_n["id"] == e["target"]
    }
    assert "User" in targets
    assert "Box" in targets
    assert "T" not in targets
