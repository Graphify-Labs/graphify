"""A variadic parameter references its type, like any other parameter.

Each extractor walked its grammar's ordinary parameter node only, so the type of
a variadic one got no `references` edge: Go `opts ...Option` (the functional-
options idiom), Java `Opt... os`, C# `params Opt[] os`, Scala `os: Opt*` and
PHP `Opt ...$os`. Scala's by-name parameter (`o: => Opt`) was dropped the same
way, through its `=> T` wrapper. Kotlin, Swift, Python and Rust already linked
theirs; these five now do too, with the same context a plain parameter gets.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from graphify.extract import extract

CASES = {
    "go": ("tree_sitter_go", "x.go", "package p\n\ntype Opt struct{}\n\nfunc Plain(o Opt) {}\nfunc Vari(os ...Opt) {}\n",
           "Vari()"),
    "java": ("tree_sitter_java", "X.java", "class Opt {}\nclass X {\n  void plain(Opt o) {}\n  void vari(Opt... os) {}\n}\n",
             ".vari()"),
    "java-generic": ("tree_sitter_java", "Y.java",
                     "import java.util.List;\nclass Opt {}\nclass Y {\n  void vari(List<Opt>... os) {}\n}\n", ".vari()"),
    "csharp": ("tree_sitter_c_sharp", "x.cs", "class Opt {}\nclass X {\n  void Plain(Opt o) {}\n  void Vari(params Opt[] os) {}\n}\n",
               ".Vari()"),
    "scala": ("tree_sitter_scala", "x.scala", "class Opt\nobject X {\n  def plain(o: Opt): Unit = ()\n  def vari(os: Opt*): Unit = ()\n}\n",
              ".vari()"),
    "scala-by-name": ("tree_sitter_scala", "y.scala", "class Opt\nobject Y {\n  def lazyp(o: => Opt): Unit = ()\n}\n",
                      ".lazyp()"),
    "php": ("tree_sitter_php", "x.php", "<?php\nclass Opt {}\nfunction plain(Opt $o) {}\nfunction vari(Opt ...$os) {}\n",
            "vari()"),
}


def _refs_to_opt(tmp_path: Path, name: str, src: str) -> dict[str, str]:
    path = tmp_path / name
    path.write_text(src, encoding="utf-8")
    result = extract([path], root=tmp_path, cache_root=tmp_path / "graphify-out", parallel=False)
    label = {n["id"]: n["label"] for n in result["nodes"]}
    opt = [n for n in result["nodes"] if n["label"] == "Opt"]
    assert len(opt) == 1 and opt[0]["source_file"], "the local Opt declaration is the target"
    return {label.get(e["source"], ""): e.get("context", "")
            for e in result["edges"] if e["relation"] == "references" and e["target"] == opt[0]["id"]}


@pytest.mark.parametrize("case", sorted(CASES))
def test_a_variadic_parameter_references_its_type(tmp_path: Path, case: str):
    module, name, src, func = CASES[case]
    if importlib.util.find_spec(module) is None:
        pytest.skip(f"{module} not installed")
    refs = _refs_to_opt(tmp_path, name, src)
    # A type argument keeps the `generic_arg` context, as for a plain parameter.
    expected = "generic_arg" if case == "java-generic" else "parameter_type"
    assert refs.get(func) == expected, refs


@pytest.mark.parametrize("case", ["go", "java", "csharp", "scala", "php"])
def test_an_ordinary_parameter_still_references_its_type(tmp_path: Path, case: str):
    module, name, src, _ = CASES[case]
    if importlib.util.find_spec(module) is None:
        pytest.skip(f"{module} not installed")
    refs = _refs_to_opt(tmp_path, name, src)
    assert any("plain" in f.lower() and ctx == "parameter_type" for f, ctx in refs.items()), refs
