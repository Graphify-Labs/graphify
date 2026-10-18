"""Scala generic type parameters must not mint sourceless god nodes.

A `class Box[T]` / `def map[R](...)` binds `T`/`R` as local names, not corpus
symbols. The Scala type-ref pass appended the bare `T`/`R` identifiers used in
a signature as type references and ran them through the sourceless-stub path,
so every generic class/method in the corpus collapsed its `T` onto one bare `t`
node — a god node (single-letter type params are not in the analyzer's
builtin-noise filter). C#, Java, TypeScript, Kotlin, and Go already exclude
their type parameters; Scala now matches.
"""
from pathlib import Path

from graphify.extract import extract


def _sourceless_labels(r):
    return sorted({n.get("label") for n in r["nodes"] if not n.get("source_file")})


def test_generic_class_and_method_type_params_mint_no_stub(tmp_path):
    (tmp_path / "S.scala").write_text(
        "class Box[T](v: T) {\n"
        "  def get(): T = v\n"
        "  def map[R](f: T => R): R = ???\n"
        "}\n"
    )
    r = extract([tmp_path / "S.scala"], cache_root=tmp_path, parallel=False)
    assert not any(e.get("target") in ("t", "r") for e in r["edges"])
    assert "T" not in _sourceless_labels(r)
    assert "R" not in _sourceless_labels(r)


def test_bounds_param_dropped_but_context_bound_and_real_types_kept(tmp_path):
    # `A` is a parameter (dropped); the `Ordering` context bound is a real
    # dependency (kept, #2046), and a genuine user type in the signature still
    # references. (An upper bound `<: User` is deliberately not emitted, #2046.)
    (tmp_path / "S.scala").write_text(
        "class User(name: String)\n"
        "class Processor[A: Ordering] {\n"
        "  def run(u: User): User = u\n"
        "}\n"
    )
    r = extract([tmp_path / "S.scala"], cache_root=tmp_path, parallel=False)
    refs = {
        rn["label"]
        for e in r["edges"] if e.get("relation") == "references"
        for rn in r["nodes"] if rn["id"] == e["target"]
    }
    assert "Ordering" in refs
    assert "User" in refs
    assert "A" not in refs
