"""#4854: a file node and a declaration inside it must never share an id.

Every fixture states the labels and edges the extractor must produce. The tests
assert behaviour (which nodes and edges exist, and what references point at),
not the helper that assigns the id.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from graphify.build import build
from graphify.extract import extract


def _corpus(tmp_path: Path, files: dict[str, str], name: str = "corpus") -> tuple[Path, Path]:
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root, tmp_path / f"{name}-cache"


def _run(tmp_path: Path, files: dict[str, str], name: str = "corpus") -> dict:
    root, cache = _corpus(tmp_path, files, name)
    return extract(
        sorted(p for p in root.rglob("*") if p.is_file()),
        cache_root=cache,
        root=root,
        parallel=False,
    )


def _labels(result: dict) -> set[tuple[str, str]]:
    return {(node["label"], node["source_file"]) for node in result["nodes"]}


def _id_of(result: dict, label: str, source_file: str) -> str:
    found = [
        node["id"] for node in result["nodes"]
        if node["label"] == label and node["source_file"] == source_file
    ]
    assert len(found) == 1, f"expected one {label!r} in {source_file}, got {found}"
    return found[0]


def _edge_facts(result: dict) -> set[tuple[tuple[str, str], str, tuple[str, str]]]:
    by_id = {
        node["id"]: (node["label"], node["source_file"]) for node in result["nodes"]
    }
    facts = set()
    for edge in result["edges"]:
        facts.add((by_id[edge["source"]], edge["relation"], by_id[edge["target"]]))
    return facts


def _assert_clean(result: dict, *, labels: list[tuple[str, str]]) -> None:
    got = _labels(result)
    for fact in labels:
        assert fact in got, f"missing node {fact}; got {sorted(got)}"
    ids = [node["id"] for node in result["nodes"]]
    assert len(ids) == len(set(ids)), f"duplicate ids: {sorted(i for i in ids if ids.count(i) > 1)}"
    self_edges = [
        edge for edge in result["edges"]
        if edge["source"] == edge["target"] and edge["relation"] == "contains"
    ]
    assert not self_edges, f"self-contains edges: {self_edges}"


FIXTURES = [
    ("js_class", {"a.js": "class Js { run() { return 1; } }\n"},
     [("a.js", "a.js"), ("Js", "a.js"), (".run()", "a.js")],
     [(("a.js", "a.js"), "contains", ("Js", "a.js")),
      (("Js", "a.js"), "method", (".run()", "a.js"))]),
    ("js_export_class", {"a.js": "export class Js { run() { return 1; } }\n"},
     [("a.js", "a.js"), ("Js", "a.js"), (".run()", "a.js")],
     [(("a.js", "a.js"), "contains", ("Js", "a.js")),
      (("Js", "a.js"), "method", (".run()", "a.js"))]),
    ("js_func_decl", {"a.js": "function js() { return 1; }\n"},
     [("a.js", "a.js"), ("js()", "a.js")],
     [(("a.js", "a.js"), "contains", ("js()", "a.js"))]),
    ("js_const", {"a.js": "export const Js = 1;\n"},
     [("a.js", "a.js"), ("Js", "a.js")],
     [(("a.js", "a.js"), "contains", ("Js", "a.js"))]),
    ("js_arrow_const", {"a.js": "const js = () => 1;\n"},
     [("a.js", "a.js"), ("js()", "a.js")],
     [(("a.js", "a.js"), "contains", ("js()", "a.js"))]),
    ("ts_class", {"a.ts": "class Ts { run() { return 1; } }\n"},
     [("a.ts", "a.ts"), ("Ts", "a.ts"), (".run()", "a.ts")],
     [(("a.ts", "a.ts"), "contains", ("Ts", "a.ts")),
      (("Ts", "a.ts"), "method", (".run()", "a.ts"))]),
    ("py_class", {"m.py": "class Py:\n    def run(self):\n        return 1\n"},
     [("m.py", "m.py"), ("Py", "m.py"), (".run()", "m.py")],
     [(("m.py", "m.py"), "contains", ("Py", "m.py")),
      (("Py", "m.py"), "method", (".run()", "m.py"))]),
    ("java_class", {"Foo.java": "class Java { void run() {} }\n"},
     [("Foo.java", "Foo.java"), ("Java", "Foo.java"), (".run()", "Foo.java")],
     [(("Foo.java", "Foo.java"), "contains", ("Java", "Foo.java")),
      (("Java", "Foo.java"), "method", (".run()", "Foo.java"))]),
    ("php_class", {"x.php": "<?php class Php { function run() {} }\n"},
     [("x.php", "x.php"), ("Php", "x.php"), (".run()", "x.php")],
     [(("x.php", "x.php"), "contains", ("Php", "x.php")),
      (("Php", "x.php"), "method", (".run()", "x.php"))]),
    ("rb_class", {"x.rb": "class Rb\n  def run; 1; end\nend\n"},
     [("x.rb", "x.rb"), ("Rb", "x.rb"), (".run()", "x.rb")],
     [(("x.rb", "x.rb"), "contains", ("Rb", "x.rb")),
      (("Rb", "x.rb"), "method", (".run()", "x.rb"))]),
    ("cpp_header_class", {"a.h": "class H { public: void run(); };\n"},
     [("a.h", "a.h"), ("H", "a.h"), (".run()", "a.h")],
     [(("a.h", "a.h"), "contains", ("H", "a.h")),
      (("H", "a.h"), "method", (".run()", "a.h"))]),
    ("control_notjs", {"a.js": "class NotJs { run() { return 1; } }\n"},
     [("a.js", "a.js"), ("NotJs", "a.js"), (".run()", "a.js")],
     [(("a.js", "a.js"), "contains", ("NotJs", "a.js")),
      (("NotJs", "a.js"), "method", (".run()", "a.js"))]),
    ("intra_file_inherits", {"a.js": "class Js {}\nclass Other extends Js {}\n"},
     [("a.js", "a.js"), ("Js", "a.js"), ("Other", "a.js")],
     [(("a.js", "a.js"), "contains", ("Js", "a.js")),
      (("a.js", "a.js"), "contains", ("Other", "a.js")),
      (("Other", "a.js"), "inherits", ("Js", "a.js"))]),
    ("ts_decorator_ref", {"a.ts": "class Ts {}\n@Ts class Other {}\n"},
     [("a.ts", "a.ts"), ("Ts", "a.ts"), ("Other", "a.ts")],
     [(("a.ts", "a.ts"), "contains", ("Ts", "a.ts")),
      (("a.ts", "a.ts"), "contains", ("Other", "a.ts")),
      (("Other", "a.ts"), "references", ("Ts", "a.ts"))]),
    ("cross_file_use", {
        "a.js": "export class Js { run() { return 1; } }\n",
        "main.js": 'import { Js } from "./a.js";\nnew Js().run();\n',
    },
     [("a.js", "a.js"), ("Js", "a.js"), (".run()", "a.js"), ("main.js", "main.js")],
     [(("a.js", "a.js"), "contains", ("Js", "a.js")),
      (("Js", "a.js"), "method", (".run()", "a.js")),
      (("main.js", "main.js"), "imports", ("Js", "a.js"))]),
    ("ts_cross_file_decorator", {
        "a.ts": "export class Ts {}\n",
        "b.ts": 'import { Ts } from "./a";\n@Ts class Other {}\n',
    },
     [("a.ts", "a.ts"), ("Ts", "a.ts"), ("b.ts", "b.ts"), ("Other", "b.ts")],
     [(("b.ts", "b.ts"), "contains", ("Other", "b.ts")),
      (("Other", "b.ts"), "references", ("Ts", "a.ts"))]),
    ("adversarial_kind_salt", {"a.js": "class Js {}\nclass Js_type {}\n"},
     [("a.js", "a.js"), ("Js", "a.js"), ("Js_type", "a.js")],
     [(("a.js", "a.js"), "contains", ("Js", "a.js")),
      (("a.js", "a.js"), "contains", ("Js_type", "a.js"))]),
    ("empty_name_const", {"a.js": "const $ = 1;\n"},
     [("a.js", "a.js")], []),
    ("empty_name_arrow", {"a.js": "const $ = () => 1;\n"},
     [("a.js", "a.js")], []),
]


@pytest.mark.parametrize(
    "name,files,labels,edges",
    FIXTURES,
    ids=[fixture[0] for fixture in FIXTURES],
)
def test_fixture_matrix(tmp_path, name, files, labels, edges):
    result = _run(tmp_path, files, name)
    _assert_clean(result, labels=labels)
    facts = _edge_facts(result)
    for edge in edges:
        assert edge in facts, f"missing edge {edge}; got {sorted(facts)}"
    if name.startswith("empty_name_"):
        assert _labels(result) == {("a.js", "a.js")}
    _assert_build_keeps(result, labels)


def _assert_build_keeps(result: dict, labels: list[tuple[str, str]]) -> None:
    built = {data.get("label") for _, data in build([result]).nodes(data=True)}
    for label, _source in labels:
        assert label in built, f"build() dropped {label!r}; kept {sorted(built)}"


def test_salt_cannot_be_occupied_by_a_real_symbol(tmp_path):
    """A legal identifier equal to the salt must not steal the class id."""
    salt = hashlib.sha1(b"Js").hexdigest()[:12]
    result = _run(
        tmp_path,
        {"a.js": f"class Js {{}}\nexport const ${salt} = 1;\n"},
        "salt-clash",
    )
    _assert_clean(result, labels=[("a.js", "a.js"), ("Js", "a.js"), (f"${salt}", "a.js")])
    ids = {_id_of(result, "Js", "a.js"), _id_of(result, f"${salt}", "a.js")}
    assert len(ids) == 2
    _assert_build_keeps(result, [("a.js", "a.js"), ("Js", "a.js"), (f"${salt}", "a.js")])


def test_bundle_min_js_keeps_class_and_method(tmp_path):
    result = _run(
        tmp_path,
        {"bundle.min.js": "class Js { run() { return 1; } }\n"},
        "bundle",
    )
    _assert_clean(result, labels=[("bundle.min.js", "bundle.min.js"), ("Js", "bundle.min.js"), (".run()", "bundle.min.js")])
    assert (("bundle.min.js", "bundle.min.js"), "contains", ("Js", "bundle.min.js")) in _edge_facts(result)
    assert (("Js", "bundle.min.js"), "method", (".run()", "bundle.min.js")) in _edge_facts(result)


def test_rust_struct_keeps_its_node(tmp_path):
    result = _run(
        tmp_path,
        {"a.rs": "struct Rs { x: i32 }\nfn main() {}\n"},
        "rust",
    )
    _assert_clean(result, labels=[("a.rs", "a.rs"), ("Rs", "a.rs"), ("main()", "a.rs")])
    assert _id_of(result, "Rs", "a.rs") != _id_of(result, "a.rs", "a.rs")


def test_cross_file_decorator_targets_the_declared_class(tmp_path):
    result = _run(
        tmp_path,
        {
            "a.ts": "export class Ts {}\n",
            "b.ts": 'import { Ts } from "./a";\n@Ts class Other {}\n',
        },
        "cross-decorator",
    )
    class_id = _id_of(result, "Ts", "a.ts")
    other_id = _id_of(result, "Other", "b.ts")
    file_id = _id_of(result, "b.ts", "b.ts")
    targets = {edge["target"] for edge in result["edges"] if edge["source"] == other_id}
    assert class_id in targets, f"decorator reference missing; targets={targets}"
    assert file_id not in targets, "decorator reference points at the file node"


def test_cross_file_decorator_prefers_the_imported_module(tmp_path):
    """Two modules declare Ts; the decorator must bind the imported one."""
    result = _run(
        tmp_path,
        {
            "a1.ts": "export class Ts {}\n",
            "a2.ts": "export class Ts {}\n",
            "b.ts": 'import { Ts } from "./a1";\n@Ts class Other {}\n',
        },
        "cross-ambiguous",
    )
    first = _id_of(result, "Ts", "a1.ts")
    second = _id_of(result, "Ts", "a2.ts")
    other = _id_of(result, "Other", "b.ts")
    targets = {edge["target"] for edge in result["edges"] if edge["source"] == other}
    assert first in targets, f"decorator did not bind the imported Ts; targets={targets}"
    assert second not in targets, "decorator bound the wrong module's Ts"


def test_cross_file_inheritance_targets_the_declared_class(tmp_path):
    result = _run(
        tmp_path,
        {
            "a.ts": "export class Ts {}\n",
            "b.ts": 'import { Ts } from "./a";\nexport class Other extends Ts {}\n',
        },
        "cross-inherits",
    )
    class_id = _id_of(result, "Ts", "a.ts")
    assert (("Other", "b.ts"), "inherits", ("Ts", "a.ts")) in _edge_facts(result)
    other_id = _id_of(result, "Other", "b.ts")
    targets = {edge["target"] for edge in result["edges"] if edge["source"] == other_id}
    assert class_id in targets


def test_prototype_method_attaches_to_the_salted_class(tmp_path):
    result = _run(
        tmp_path,
        {"a.js": "class Js {}\nJs.prototype.run = function run() {}\n"},
        "prototype",
    )
    _assert_clean(result, labels=[("a.js", "a.js"), ("Js", "a.js"), (".run()", "a.js")])
    assert (("Js", "a.js"), "method", (".run()", "a.js")) in _edge_facts(result)
    assert len([n for n in result["nodes"] if n["label"] == "Js"]) == 1


ZOO = [
    ("a.js", "class Js {}", "class Zzz {}"),
    ("a.js", "function js() {}", "function zzz() {}"),
    ("a.js", "const js = () => 1;", "const zzz = () => 1;"),
    ("a.ts", "class Ts {}", "class Zzz {}"),
    ("a.ts", "interface Ts {}", "interface Zzz {}"),
    ("a.ts", "enum Ts { A }", "enum Zzz { A }"),
    ("a.ts", "type Ts = number;", "type Zzz = number;"),
    ("m.py", "class Py: pass", "class Zzz: pass"),
    ("m.py", "def py(): pass", "def zzz(): pass"),
    ("Foo.java", "class Java {}", "class Zzz {}"),
    ("Foo.java", "interface Java {}", "interface Zzz {}"),
    ("Foo.java", "enum Java { A }", "enum Zzz { A }"),
    ("Foo.java", "record Java(int x) {}", "record Zzz(int x) {}"),
    ("x.php", "<?php class Php {}", "<?php class Zzz {}"),
    ("x.php", "<?php interface Php {}", "<?php interface Zzz {}"),
    ("x.php", "<?php trait Php {}", "<?php trait Zzz {}"),
    ("x.rb", "class Rb\nend", "class Zzz\nend"),
    ("x.rb", "module Rb\nend", "module Zzz\nend"),
    ("a.cpp", "class C {};", "class Zzz {};"),
    ("a.cpp", "namespace C { int x; }", "namespace Zzz { int x; }"),
    ("a.h", "class H {};", "class Zzz {};"),
    ("a.rs", "struct Rs;", "struct Zzz;"),
    ("a.rs", "enum Rs { A }", "enum Zzz { A }"),
    ("a.rs", "trait Rs {}", "trait Zzz {}"),
    ("a.go", "package p\ntype Go struct{}", "package p\ntype Zzz struct{}"),
    ("a.go", "package p\ntype Go interface{}", "package p\ntype Zzz interface{}"),
    ("x.go", "package p\nfunc Go() {}", "package p\nfunc Zzz() {}"),
    ("a.jl", "struct Jl end", "struct Zzz end"),
    ("x.cs", "class Cs {}", "class Zzz {}"),
    ("x.cs", "struct Cs {}", "struct Zzz {}"),
    ("x.cs", "interface Cs {}", "interface Zzz {}"),
    ("x.cs", "record Cs();", "record Zzz();"),
    ("x.cs", "enum Cs { A }", "enum Zzz { A }"),
    ("a.swift", "class Swift {}", "class Zzz {}"),
    ("a.swift", "struct Swift {}", "struct Zzz {}"),
    ("a.swift", "enum Swift { case a }", "enum Zzz { case a }"),
    ("a.kt", "class Kt", "class Zzz"),
    ("a.kt", "object Kt", "object Zzz"),
    ("a.kt", "interface Kt", "interface Zzz"),
    ("a.scala", "class Scala", "class Zzz"),
    ("a.scala", "object Scala", "object Zzz"),
    ("a.scala", "trait Scala", "trait Zzz"),
]


def _declared_name(body: str) -> str | None:
    import re

    match = re.search(
        r"(?:class|struct|interface|record|enum|trait|module|object|type|namespace|function|const|def|fn|fun|func|protocol)\s+([A-Za-z_]\w*)",
        body,
    )
    return match.group(1) if match else None


def _label_for(result: dict, filename: str, name: str) -> str | None:
    for label, source in _labels(result):
        if source == filename and label.rstrip("()") == name:
            return label
    return None


@pytest.mark.parametrize("filename,body,control", ZOO, ids=[f"{i}-{z[0]}" for i, z in enumerate(ZOO)])
def test_zoo_declaration_kinds_keep_their_node(tmp_path, filename, body, control):
    declared = _declared_name(body)
    control_name = _declared_name(control)
    assert declared and control_name
    control_result = _run(tmp_path, {filename: control}, f"zoo-control-{declared}")
    control_label = _label_for(control_result, filename, control_name)
    if control_label is None:
        pytest.skip(f"extractor does not model this kind ({filename}: {control_name})")
    result = _run(tmp_path, {filename: body}, f"zoo-{declared}")
    declared_label = _label_for(result, filename, declared)
    assert declared_label is not None, f"{filename}: {declared} was dropped"
    _assert_clean(result, labels=[(filename, filename), (declared_label, filename)])
    assert _id_of(result, declared_label, filename) != _id_of(result, filename, filename)
    _assert_build_keeps(result, [(filename, filename), (declared_label, filename)])


def test_fresh_and_cached_extraction_agree(tmp_path):
    files = {
        "a.ts": "export class Ts {}\n",
        "b.ts": 'import { Ts } from "./a";\n@Ts class Other {}\n',
    }
    root, cache = _corpus(tmp_path, files, "cache-parity")
    paths = sorted(p for p in root.rglob("*") if p.is_file())
    first = extract(paths, cache_root=cache, root=root, parallel=False)
    second = extract(paths, cache_root=cache, root=root, parallel=False)
    assert first["nodes"] == second["nodes"]
    assert first["edges"] == second["edges"]


def test_schema_bumped_for_the_id_change():
    from graphify import cache

    assert cache._AST_CACHE_SCHEMA >= 30
    source = Path(cache.__file__).read_text(encoding="utf-8")
    marker = f"_AST_CACHE_SCHEMA = {cache._AST_CACHE_SCHEMA}"
    line = next(line for line in source.splitlines() if line.startswith(marker))
    assert "#4854" in line, "schema bump must document #4854"


def test_decl_ids_survive_the_ast_cache(tmp_path):
    root, cache = _corpus(tmp_path, {"a.ts": "export class Ts {}\n@Ts class Other {}\n"}, "decl-cache")
    paths = sorted(p for p in root.rglob("*") if p.is_file())
    fresh = extract(paths, cache_root=cache, root=root, parallel=False)
    warm = extract(paths, cache_root=cache, root=root, parallel=False)
    assert _id_of(fresh, "Ts", "a.ts") == _id_of(warm, "Ts", "a.ts")
    assert (("Other", "a.ts"), "references", ("Ts", "a.ts")) in _edge_facts(warm)
