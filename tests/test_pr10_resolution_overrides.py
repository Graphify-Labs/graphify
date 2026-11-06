"""PR10: inferred candidates and call scope honor declared languages."""

import pytest

from graphify.extractors import resolution
from graphify.rcfile import activate_language_overrides, set_language_overrides
from tests.test_language_overrides import _quiet_extract


@pytest.fixture(autouse=True)
def _restore_language_overrides():
    set_language_overrides(None)
    yield
    set_language_overrides(None)


@pytest.mark.parametrize("remap_native", [False, True])
@pytest.mark.parametrize("layout", ["file", "index", "esm"])
def test_js_inferred_candidates_respect_language_and_native_precedence(
    tmp_path, layout, remap_native
):
    config = "language.tpl=typescript\n"
    if remap_native:
        config += "language.ts=php\n"
    (tmp_path / ".graphifyrc").write_text(config, encoding="utf-8")
    activate_language_overrides(tmp_path)
    candidate = tmp_path / ("dep.js" if layout == "esm" else "dep")
    if layout == "index":
        candidate.mkdir()
        native, declared = candidate / "index.ts", candidate / "index.tpl"
    else:
        native, declared = tmp_path / "dep.ts", tmp_path / "dep.tpl"
    native.write_text(
        "<?php function foreign() {}" if remap_native else "export function native() {}",
        encoding="utf-8",
    )
    declared.write_text("export function declared() {}", encoding="utf-8")

    # A missing explicit .js path stays unresolved; it must not substitute PHP.
    expected = (candidate if layout == "esm" else declared) if remap_native else native
    assert resolution._resolve_js_module_path(candidate) == expected


@pytest.mark.parametrize("remap_native", [False, True])
@pytest.mark.parametrize("layout", ["module", "package"])
def test_python_inferred_candidates_respect_language_and_native_precedence(
    tmp_path, layout, remap_native
):
    config = "language.pyx=python\n"
    if remap_native:
        config += "language.py=javascript\n"
    (tmp_path / ".graphifyrc").write_text(config, encoding="utf-8")
    activate_language_overrides(tmp_path)
    if layout == "package":
        package = tmp_path / "dep"
        package.mkdir()
        native, declared = package / "__init__.py", package / "__init__.pyx"
    else:
        native, declared = tmp_path / "dep.py", tmp_path / "dep.pyx"
    native.write_text(
        "export function foreign() {}" if remap_native else "def native(): pass\n",
        encoding="utf-8",
    )
    declared.write_text("def declared(): pass\n", encoding="utf-8")

    assert resolution._resolve_python_module_path(
        "dep", tmp_path / "caller.pyx", tmp_path, 0
    ) == (declared if remap_native else native)


@pytest.mark.parametrize(
    "config, marker, expected",
    [
        ("language.pyx=python\n", "__init__.py", True),
        ("language.py=javascript\nlanguage.pyx=python\n", "__init__.py", False),
        ("language.py=javascript\nlanguage.pyx=python\n", "__init__.pyx", True),
    ],
)
def test_python_package_marker_must_be_python(tmp_path, config, marker, expected):
    (tmp_path / ".graphifyrc").write_text(config, encoding="utf-8")
    (tmp_path / marker).write_text("", encoding="utf-8")
    activate_language_overrides(tmp_path)

    assert resolution._is_python_package_dir(tmp_path) is expected


@pytest.mark.parametrize("caller_suffix", [".ts", ".tpl"])
@pytest.mark.parametrize("has_import", [False, True])
def test_js_cross_file_call_requires_an_import(tmp_path, caller_suffix, has_import):
    (tmp_path / ".graphifyrc").write_text("language.tpl=typescript\n", encoding="utf-8")
    provider = tmp_path / "provider.ts"
    caller = tmp_path / f"caller{caller_suffix}"
    provider.write_text("export function hidden() {}\n", encoding="utf-8")
    caller.write_text(
        ("import { hidden } from './provider';\n" if has_import else "")
        + "export function caller() { hidden(); }\n",
        encoding="utf-8",
    )

    result = _quiet_extract([provider, caller], root=tmp_path, cache_root=tmp_path)
    caller_id = next(
        node["id"] for node in result["nodes"]
        if node.get("source_file") == caller.name and node["label"] == "caller()"
    )
    provider_id = next(
        node["id"] for node in result["nodes"]
        if node.get("source_file") == provider.name and node["label"] == "hidden()"
    )
    assert any(
        edge["source"] == caller_id and edge["target"] == provider_id
        and edge["relation"] == "calls"
        for edge in result["edges"]
    ) is has_import
