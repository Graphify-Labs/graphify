"""After #4634, `class A extends X` with `const X = require('./m')` must inherit
the class the required file exports — not a local binding, and not nothing (#4688).

#4634 correctly stopped minting a module-scope node for the require binding so
`new X()` no longer shadows the required class. Heritage resolution still went
through that missing node, so the inherits edge disappeared. The fix records
CommonJS require bindings (and `module.exports = Name`) as symbol import/export
facts so extends resolves the same way as an ESM default import.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import _make_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _inherits_targets(result: dict, subclass: str) -> list[tuple[str, str]]:
    nodes = {n["id"]: n for n in result["nodes"]}
    out = []
    for edge in result["edges"]:
        if edge["relation"] != "inherits":
            continue
        src = nodes.get(edge["source"])
        tgt = nodes.get(edge["target"])
        if src is None or tgt is None or src["label"] != subclass:
            continue
        sf = Path(str(tgt.get("source_file") or "")).name
        out.append((tgt["label"], sf))
    return sorted(out)


def _calls_targets(result: dict, caller: str) -> list[tuple[str, str]]:
    nodes = {n["id"]: n for n in result["nodes"]}
    out = []
    for edge in result["edges"]:
        if edge["relation"] != "calls":
            continue
        src = nodes.get(edge["source"])
        tgt = nodes.get(edge["target"])
        if src is None or tgt is None or src["label"] != caller:
            continue
        sf = Path(str(tgt.get("source_file") or "")).name
        out.append((tgt["label"], sf))
    return sorted(out)


GEN = "class Generator { run() {} }\nmodule.exports = Generator;\n"
GEN_ESM = "class Generator { run() {} }\nexport default Generator;\n"


def test_const_require_extends_lands_on_required_class(tmp_path: Path):
    gen = _write(tmp_path / "gen.js", GEN)
    use = _write(
        tmp_path / "use.js",
        "const Generator = require('./gen');\n"
        "class A extends Generator { go() {} }\n",
    )
    result = extract([gen, use], cache_root=tmp_path / "_cache", root=tmp_path)

    assert _make_id("use", "Generator") not in {n["id"] for n in result["nodes"]}
    assert _inherits_targets(result, "A") == [("Generator", "gen.js")]


def test_let_var_and_ts_require_extends(tmp_path: Path):
    variants = [
        ("use_let.js", "let Generator = require('./gen');\n"),
        ("use_var.js", "var Generator = require('./gen');\n"),
        ("use.ts", "const Generator = require('./gen');\n"),
    ]
    gen = _write(tmp_path / "gen.js", GEN)
    for name, head in variants:
        use = _write(tmp_path / name, head + "class A extends Generator { go() {} }\n")
        result = extract(
            [gen, use], cache_root=tmp_path / f"_cache_{name}", root=tmp_path
        )
        assert _inherits_targets(result, "A") == [("Generator", "gen.js")], name


def test_esm_default_import_extends_still_works(tmp_path: Path):
    gen = _write(tmp_path / "gen.js", GEN_ESM)
    use = _write(
        tmp_path / "use.js",
        "import Generator from './gen';\n"
        "class A extends Generator { go() {} }\n",
    )
    result = extract([gen, use], cache_root=tmp_path / "_cache", root=tmp_path)
    assert _inherits_targets(result, "A") == [("Generator", "gen.js")]


def test_import_equals_require_extends(tmp_path: Path):
    gen = _write(tmp_path / "gen.js", GEN)
    use = _write(
        tmp_path / "use.ts",
        "import Generator = require('./gen');\n"
        "class A extends Generator { go() {} }\n",
    )
    result = extract([gen, use], cache_root=tmp_path / "_cache", root=tmp_path)
    assert _inherits_targets(result, "A") == [("Generator", "gen.js")]


def test_renamed_require_extends_follows_default_export(tmp_path: Path):
    gen = _write(tmp_path / "gen.js", GEN)
    use = _write(
        tmp_path / "use.js",
        "const Foo = require('./gen');\n"
        "class A extends Foo { go() {} }\n",
    )
    result = extract([gen, use], cache_root=tmp_path / "_cache", root=tmp_path)
    assert _make_id("use", "Foo") not in {n["id"] for n in result["nodes"]}
    assert _inherits_targets(result, "A") == [("Generator", "gen.js")]


def test_require_new_still_lands_on_required_class(tmp_path: Path):
    """#4621 / #4634: `new X()` keeps resolving to the required declaration."""
    logger = _write(
        tmp_path / "logger.js",
        "function Logger(p) { this.p = p }\n"
        "module.exports = Logger\n",
    )
    use = _write(
        tmp_path / "use.js",
        "const Logger = require('./logger')\n"
        "function Watcher() { return new Logger('w') }\n",
    )
    result = extract([logger, use], cache_root=tmp_path / "_cache", root=tmp_path)
    assert _make_id("use", "Logger") not in {n["id"] for n in result["nodes"]}
    assert (_make_id("use", "Watcher"), _make_id("logger", "Logger")) in {
        (e["source"], e["target"])
        for e in result["edges"]
        if e["relation"] == "calls"
    }


def test_external_require_new_matches_esm_no_calls_edge(tmp_path: Path):
    """Unresolved package requires stay without a calls/inherits target.

    #4634 removed the local binding node on purpose. ESM `import X from 'pkg'`
    already emits no calls/inherits edge for the same unresolved external — only
    an `imports_from` to a `ref_…` package id. CJS matches that: no edge rather
    than restoring a shadow binding (#4688).
    """
    cjs = _write(
        tmp_path / "cjs.js",
        "const Plugin = require('some-plugin');\n"
        "function cfg() { return new Plugin(); }\n"
        "class A extends Plugin {}\n",
    )
    esm = _write(
        tmp_path / "esm.js",
        "import Plugin from 'some-plugin';\n"
        "function cfg() { return new Plugin(); }\n"
        "class A extends Plugin {}\n",
    )
    for path in (cjs, esm):
        result = extract([path], cache_root=tmp_path / f"_cache_{path.stem}", root=tmp_path)
        assert _calls_targets(result, "cfg()") == [], path.name
        assert _inherits_targets(result, "A") == [], path.name
        assert _make_id(path.stem, "Plugin") not in {n["id"] for n in result["nodes"]}


def test_bare_exports_assignment_is_not_a_default_export(tmp_path: Path):
    """Bare `exports = X` does not change what require() returns (#4700 review)."""
    lib = _write(
        tmp_path / "lib.js",
        "class Decoy {}\n"
        "class Real {}\n"
        "exports = Decoy;\n"
        "module.exports = Real;\n",
    )
    use = _write(
        tmp_path / "use.js",
        "const X = require('./lib');\n"
        "class A extends X {}\n",
    )
    result = extract([lib, use], cache_root=tmp_path / "_cache", root=tmp_path)
    assert _inherits_targets(result, "A") == [("Real", "lib.js")]


def test_bare_exports_only_does_not_export_a_default(tmp_path: Path):
    """`exports = Decoy` alone must not mint a default export for require()."""
    lib = _write(tmp_path / "lib.js", "class Decoy {}\nexports = Decoy;\n")
    use = _write(
        tmp_path / "use.js",
        "const X = require('./lib');\n"
        "class A extends X {}\n",
    )
    result = extract([lib, use], cache_root=tmp_path / "_cache", root=tmp_path)
    assert _inherits_targets(result, "A") == []
    assert _make_id("use", "X") not in {n["id"] for n in result["nodes"]}


def test_chained_module_exports_exports_equals_uses_final_rhs(tmp_path: Path):
    """`module.exports = exports = Foo` must export Foo, not the name `exports`."""
    lib = _write(
        tmp_path / "lib.js",
        "class Foo { run() {} }\n"
        "module.exports = exports = Foo;\n",
    )
    use = _write(
        tmp_path / "use.js",
        "const X = require('./lib');\n"
        "class A extends X {}\n",
    )
    result = extract([lib, use], cache_root=tmp_path / "_cache", root=tmp_path)
    assert _inherits_targets(result, "A") == [("Foo", "lib.js")]
