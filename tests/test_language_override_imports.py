"""Declared JS-family suffixes participate in local extensionless imports."""

import pytest

from graphify.extractors.resolution import _resolve_js_module_path
from graphify.rcfile import activate_language_overrides, set_language_overrides


@pytest.fixture(autouse=True)
def reset_overrides():
    set_language_overrides(None)
    yield
    set_language_overrides(None)


@pytest.mark.parametrize("relative", ["dep.tpl", "dep/index.tpl"])
def test_extensionless_import_finds_declared_source_or_directory_index(tmp_path, relative):
    (tmp_path / ".graphifyrc").write_text("language.tpl=typescript\n")
    source = tmp_path / relative
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("export function chosen() {}\n")
    activate_language_overrides(tmp_path)
    assert _resolve_js_module_path("./dep", tmp_path) == source


@pytest.mark.parametrize("directory", [False, True])
def test_native_source_precedence_and_literal_declared_paths_are_preserved(tmp_path, directory):
    (tmp_path / ".graphifyrc").write_text("language.tpl=typescript\n")
    stem = tmp_path / ("dep/index" if directory else "dep")
    stem.parent.mkdir(parents=True, exist_ok=True)
    native, declared = stem.with_suffix(".ts"), stem.with_suffix(".tpl")
    native.write_text("export function native() {}\n")
    declared.write_text("export function declared() {}\n")
    activate_language_overrides(tmp_path)
    assert _resolve_js_module_path("./dep", tmp_path) == native
    assert _resolve_js_module_path(declared) == declared


def test_extensionless_js_lookup_does_not_claim_other_declared_languages(tmp_path):
    (tmp_path / ".graphifyrc").write_text("language.tpl=php\n")
    (tmp_path / "dep.tpl").write_text("<?php function chosen() {}\n")
    activate_language_overrides(tmp_path)
    assert _resolve_js_module_path("./dep", tmp_path) == tmp_path / "dep"


def test_import_candidates_ignore_mapping_keys_that_are_not_literal_suffixes(tmp_path):
    (tmp_path / ".graphifyrc").write_text("language.tpl/../secret.ts=typescript\n")
    (tmp_path / "dep.tpl").mkdir()
    (tmp_path / "secret.ts").write_text("export function unrelated() {}\n")
    activate_language_overrides(tmp_path)
    assert _resolve_js_module_path("./dep", tmp_path) == tmp_path / "dep"


@pytest.mark.parametrize("layout", ["module", "package", "reexport", "submodule", "namespace"])
def test_python_imports_bind_declared_providers_instead_of_same_named_alternatives(tmp_path, layout):
    from graphify.extract import extract

    (tmp_path / ".graphifyrc").write_text("language.pyx=python\n")
    sources = {"other.pyx": "def chosen(): return 2\n"}
    statement = "from one import chosen as local\ndef caller(): return local()\n"
    if layout == "module":
        target = "one.pyx"
    elif layout == "package":
        target = "one/__init__.pyx"
    elif layout == "reexport":
        target = "one/body.pyx"
        sources["one/__init__.pyx"] = "from .body import chosen\n"
    else:
        target = "pkg/one.pyx"
        statement = "from pkg import one\ndef caller(): return one.chosen()\n"
        if layout == "submodule":
            sources["pkg/__init__.pyx"] = ""
    sources[target] = "def chosen(): return 1\n"
    sources["caller.pyx"] = statement
    paths = []
    for relative, content in sources.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        paths.append(path)
    result = extract(paths, root=tmp_path, cache_root=tmp_path)
    nodes = {node["id"]: node for node in result["nodes"]}
    targets = {(nodes[edge["target"]]["label"], nodes[edge["target"]].get("source_file"))
               for edge in result["edges"] if edge["relation"] == "calls"
               and nodes.get(edge["source"], {}).get("label") == "caller()"}
    assert targets == {("chosen()", target)}


def test_python_native_module_and_package_precedence_is_preserved(tmp_path):
    from graphify.extractors.resolution import _resolve_python_module_path

    (tmp_path / ".graphifyrc").write_text("language.pyx=python\n")
    (tmp_path / "one").mkdir()
    (tmp_path / "one/__init__.pyx").write_text("def declared(): pass\n")
    native = tmp_path / "one.py"
    native.write_text("def native(): pass\n")
    activate_language_overrides(tmp_path)
    caller = tmp_path / "caller.py"
    assert _resolve_python_module_path("one", caller, tmp_path, 0) == native
    native_package = tmp_path / "one/__init__.py"
    native_package.write_text("def package(): pass\n")
    assert _resolve_python_module_path("one", caller, tmp_path, 0) == native_package


def test_python_lookup_does_not_claim_another_declared_language(tmp_path):
    from graphify.extractors.resolution import _resolve_python_module_path

    (tmp_path / ".graphifyrc").write_text("language.tpl=php\n")
    (tmp_path / "one.tpl").write_text("<?php function chosen() {}\n")
    activate_language_overrides(tmp_path)
    assert _resolve_python_module_path("one", tmp_path / "caller.py", tmp_path, 0) is None


def test_declared_native_suffix_can_supply_an_additional_directory_index(tmp_path):
    (tmp_path / ".graphifyrc").write_text("language.cjs=typescript\n")
    source = tmp_path / "dep/index.cjs"
    source.parent.mkdir()
    source.write_text("export function chosen() {}\n")
    activate_language_overrides(tmp_path)
    assert _resolve_js_module_path("./dep", tmp_path) == source


@pytest.mark.parametrize("suffix", [".py", ".pyx"])
@pytest.mark.parametrize("namespace", [False, True])
def test_declared_packages_preserve_absolute_and_explicit_relative_import_scope(tmp_path, suffix, namespace):
    from graphify.extract import extract

    (tmp_path / ".graphifyrc").write_text("language.pyx=python\n")
    package = tmp_path / "src/pkg"
    package.mkdir(parents=True)
    init = package / f"__init__{suffix}"
    init.write_text("")
    target = package / (f"utilities/helper{suffix}" if namespace else f"helper{suffix}")
    target.parent.mkdir(exist_ok=True)
    target.write_text("def chosen(): return 1\n")
    caller = package / f"caller{suffix}"
    for relative in (True, False):
        prefix = "." if relative else ""
        statement = (
            f"from {prefix}utilities import helper\ndef caller(): return helper.chosen()\n"
            if namespace else
            f"from {prefix}helper import chosen as local\ndef caller(): return local()\n"
        )
        caller.write_text(statement)
        result = extract([init, target, caller], root=tmp_path, cache_root=tmp_path)
        nodes = {node["id"]: node for node in result["nodes"]}
        targets = {nodes[edge["target"]].get("source_file") for edge in result["edges"]
                   if edge["relation"] == "calls" and nodes.get(edge["source"], {}).get("label") == "caller()"}
        assert targets == ({target.relative_to(tmp_path).as_posix()} if relative else set())


def test_declared_package_initializer_is_not_a_namespace_package(tmp_path):
    from graphify.extractors.resolution import _resolve_python_namespace_dir

    (tmp_path / ".graphifyrc").write_text("language.pyx=python\n")
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.pyx").write_text("def chosen(): return 1\n")
    activate_language_overrides(tmp_path)
    assert _resolve_python_namespace_dir("pkg", tmp_path / "caller.py", tmp_path, 0) is None


def test_import_of_declared_src_layout_package_targets_its_real_initializer(tmp_path):
    from graphify.extract import extract

    (tmp_path / ".graphifyrc").write_text("language.pyx=python\n")
    package = tmp_path / "src/pkg"
    package.mkdir(parents=True)
    init = package / "__init__.pyx"
    init.write_text("def chosen(): return 1\n")
    caller = tmp_path / "src/caller.pyx"
    caller.write_text("import pkg\n")
    result = extract([init, caller], root=tmp_path, cache_root=tmp_path)
    nodes = {node["id"]: node for node in result["nodes"]}
    targets = {nodes.get(edge["target"], {}).get("source_file") for edge in result["edges"]
               if edge["relation"] in {"imports", "imports_from"}
               and nodes.get(edge["source"], {}).get("source_file") == "src/caller.pyx"}
    assert targets == {"src/pkg/__init__.pyx"}
