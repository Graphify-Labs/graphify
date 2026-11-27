"""An explicit Python import must not fall back to an unrelated local name (#5229)."""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import extract


def _write(root: Path, name: str, source: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _calls(result: dict, context_nodes: list[dict] | None = None) -> set[tuple[str, str, str, str]]:
    nodes = {node["id"]: node for node in [*(context_nodes or []), *result["nodes"]]}
    return {
        (
            nodes[edge["source"]]["label"],
            nodes[edge["target"]]["label"],
            nodes[edge["target"]]["source_file"],
            edge["confidence"],
        )
        for edge in result["edges"]
        if edge["relation"] == "calls"
    }


@pytest.mark.parametrize(
    ("declaration", "callee", "definition"),
    [
        ("from sqlalchemy import text", "text", "def text(*args): pass\n"),
        ("from sqlalchemy import text as render", "render", "def render(*args): pass\n"),
        ("from rdflib import Graph", "Graph", "class Graph: pass\n"),
    ],
)
@pytest.mark.parametrize("relative_paths", [False, True])
def test_external_import_does_not_call_same_named_local_symbol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative_paths: bool,
    declaration: str, callee: str, definition: str,
) -> None:
    caller = _write(
        tmp_path, "app/migrate.py",
        f"{declaration}\n\ndef check():\n    return {callee}()\n",
    )
    target = _write(tmp_path, "tools/convert.py", definition)
    paths = [caller, target]
    if relative_paths:
        monkeypatch.chdir(tmp_path)
        paths = [path.relative_to(tmp_path) for path in paths]
    options = {"root": tmp_path, "cache_root": tmp_path / "out", "parallel": False}

    # Resolution must obey the import on both a cold extraction and a warm AST hit.
    for _ in range(2):
        result = extract(paths, **options)
        assert any(node["source_file"] == "tools/convert.py" for node in result["nodes"])
        assert not _calls(result)


def test_importing_another_symbol_from_decoy_module_is_not_call_evidence(tmp_path: Path) -> None:
    caller = _write(
        tmp_path, "app/migrate.py",
        "from sqlalchemy import text\n"
        "from tools.convert import helper\n\n"
        "def check():\n    return text()\n",
    )
    target = _write(
        tmp_path, "tools/convert.py",
        "def text(): pass\ndef helper(): pass\n",
    )

    result = extract([caller, target], root=tmp_path, cache_root=tmp_path / "out", parallel=False)

    assert not _calls(result)


def test_external_import_does_not_bind_to_an_unchanged_symbol(tmp_path: Path) -> None:
    caller = _write(
        tmp_path, "app/migrate.py",
        "from sqlalchemy import text\ndef check():\n    return text()\n",
    )
    target = _write(tmp_path, "tools/convert.py", "def text(): pass\n")
    options = {"root": tmp_path, "cache_root": tmp_path / "out", "parallel": False}
    original = extract([caller, target], **options)

    result = extract(
        [caller], **options,
        resolution_context_nodes=original["nodes"],
        resolution_context_edges=original["edges"],
    )

    assert not _calls(result, original["nodes"])


@pytest.mark.parametrize("alias", ["text", "render"])
def test_internal_import_still_resolves_to_its_declared_module(tmp_path: Path, alias: str) -> None:
    caller = _write(
        tmp_path, "app/migrate.py",
        f"from tools.convert import text as {alias}\ndef check():\n    return {alias}()\n",
    )
    target = _write(tmp_path, "tools/convert.py", "def text(): pass\n")
    decoy = _write(tmp_path, "other.py", f"def {alias}(): pass\n")

    result = extract([caller, target, decoy], root=tmp_path, cache_root=tmp_path / "out", parallel=False)

    assert _calls(result) == {("check()", "text()", "tools/convert.py", "EXTRACTED")}


def test_local_definition_can_shadow_external_import(tmp_path: Path) -> None:
    caller = _write(
        tmp_path, "app/migrate.py",
        "from sqlalchemy import text\n"
        "def check():\n"
        "    def text(): return 1\n"
        "    return text()\n",
    )
    decoy = _write(tmp_path, "other.py", "def text(): pass\n")

    result = extract([caller, decoy], root=tmp_path, cache_root=tmp_path / "out", parallel=False)

    assert _calls(result) == {("check()", "text()", "app/migrate.py", "EXTRACTED")}


def test_internal_import_in_classmethod_is_preserved(tmp_path: Path) -> None:
    caller = _write(
        tmp_path, "app/migrate.py",
        "from tools.convert import text as render\n"
        "class Runner:\n"
        "    @classmethod\n"
        "    def check(cls):\n"
        "        return render()\n",
    )
    target = _write(tmp_path, "tools/convert.py", "def text(): pass\n")

    result = extract([caller, target], root=tmp_path, cache_root=tmp_path / "out", parallel=False)

    assert _calls(result) == {(".check()", "text()", "tools/convert.py", "EXTRACTED")}


def test_function_local_import_shadows_module_alias(tmp_path: Path) -> None:
    caller = _write(
        tmp_path, "app/migrate.py",
        "from original import text as render\n"
        "def check():\n    from replacement import text as render\n    return render()\n",
    )
    original = _write(tmp_path, "original.py", "def text(): pass\n")
    replacement = _write(tmp_path, "replacement.py", "def text(): pass\n")

    result = extract(
        [caller, original, replacement], root=tmp_path, cache_root=tmp_path / "out", parallel=False,
    )

    assert _calls(result) == {("check()", "text()", "replacement.py", "EXTRACTED")}
