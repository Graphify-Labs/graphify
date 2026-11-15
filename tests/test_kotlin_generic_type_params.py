"""Kotlin generic type parameters must not mint sourceless god nodes.

A `class Box<T>` / `fun <R> map(...)` binds `T`/`R` as local names, not corpus
symbols. The Kotlin type-ref pass appended the bare `T`/`R` identifiers used in
a signature or property type as type references and ran them through the
sourceless-stub path, so every generic class/function in the corpus collapsed
its `T` onto one bare `t` node — a god node (single-letter type params are not
in the analyzer's builtin-noise filter). C#, Java, TypeScript, and Go already
exclude their type parameters; Kotlin now matches.
"""
from pathlib import Path

from graphify.extract import extract


def _sourceless(r):
    return sorted({(n["id"], n.get("label")) for n in r["nodes"] if not n.get("source_file")})


def test_generic_class_and_method_type_params_mint_no_stub(tmp_path):
    (tmp_path / "K.kt").write_text(
        "class Box<T>(val v: T) {\n"
        "    fun get(): T? = v\n"
        "    fun <R> map(f: (T) -> R): R? = null\n"
        "}\n"
    )
    r = extract([tmp_path / "K.kt"], cache_root=tmp_path, parallel=False)
    assert _sourceless(r) == []
    assert not any(e.get("target") in ("t", "r") for e in r["edges"])


def test_user_and_container_types_still_referenced(tmp_path):
    (tmp_path / "K.kt").write_text(
        "class User(val name: String)\n"
        "class Box<T>(val v: T)\n"
        "fun wrap(u: User): Box<User> = Box(u)\n"
    )
    r = extract([tmp_path / "K.kt"], cache_root=tmp_path, parallel=False)
    targets = {
        rn["label"]
        for e in r["edges"] if e.get("relation") == "references"
        for rn in r["nodes"] if rn["id"] == e["target"]
    }
    assert "User" in targets
    assert "Box" in targets
    assert "T" not in targets
    assert _sourceless(r) == []
