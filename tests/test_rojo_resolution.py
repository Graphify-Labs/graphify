"""Luau require() resolved through Rojo project files (#2520).

On a Rojo repository `require(ReplicatedStorage.Shared.Util.Logger)` names an
instance that `default.project.json` maps onto a folder, so the Lua handler's
dotted-name reading left every such require on an external stub. The fixture
under `fixtures/rojo_project/` mounts `ReplicatedStorage.Shared -> src/shared`,
`ServerScriptService.Server -> src/server` and a `Packages` vendor folder that
is not checked out.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import graphify.extract as extract_module
from graphify.extract import extract

FIXTURE = Path(__file__).parent / "fixtures" / "rojo_project"
MAIN = "src/server/Main.server.luau"


def _sources(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.suffix in (".luau", ".lua"))


def _file_ids(result: dict) -> dict[str, str]:
    return {
        n["source_file"]: n["id"]
        for n in result["nodes"]
        if n.get("source_file") and n.get("label") == Path(n["source_file"]).name
    }


def _imports_by_line(result: dict, source_file: str) -> dict[str, str]:
    source = _file_ids(result)[source_file]
    return {
        e["source_location"]: e["target"]
        for e in result["edges"]
        if e["relation"] == "imports" and e["source"] == source
    }


def _full(tmp_path: Path) -> dict:
    return extract(_sources(FIXTURE), root=FIXTURE, cache_root=tmp_path, parallel=False)


def test_instance_path_requires_point_at_file_nodes(tmp_path):
    result = _full(tmp_path)
    ids = _file_ids(result)
    imports = _imports_by_line(result, MAIN)
    assert imports["L4"] == ids["src/shared/Util/Logger.luau"]
    assert imports["L5"] == ids["src/server/Other.luau"]
    assert imports["L6"] == ids["src/shared/Signal/init.luau"]
    assert imports["L7"] == ids["src/server/ServerRef.luau"]


def test_locator_module_field_resolves(tmp_path):
    result = _full(tmp_path)
    imports = _imports_by_line(result, MAIN)
    assert imports["L8"] == _file_ids(result)["src/server/Systems/Thing.luau"]


def test_cast_require_inside_a_function_resolves(tmp_path):
    result = _full(tmp_path)
    imports = _imports_by_line(result, MAIN)
    assert imports["L18"] == _file_ids(result)["src/server/Config.luau"]


def test_dynamic_require_stays_external(tmp_path):
    """`require(module)` on a parameter keeps the Lua handler's target even
    though an outer local of the same name is an instance path."""
    result = _full(tmp_path)
    imports = _imports_by_line(result, MAIN)
    assert imports["L14"] == "module"
    assert imports["L14"] not in _file_ids(result).values()


def test_unmapped_instance_path_is_an_external_named_after_it(tmp_path):
    result = _full(tmp_path)
    imports = _imports_by_line(result, MAIN)
    assert imports["L9"] == "replicatedstorage_packages_promise"
    assert not any(n["id"] == imports["L9"] and n.get("source_file") for n in result["nodes"])


def test_lua_file_keeps_lua_handler_edges(tmp_path):
    result = _full(tmp_path)
    targets = set(_imports_by_line(result, "src/shared/Legacy.lua").values())
    assert targets == {"script_parent_util_logger"}


def test_batch_without_targets_resolves_to_full_build_ids(tmp_path):
    """An incremental batch holding only the requiring file still lands on the
    ids a full build gives its unchanged targets, the locator included."""
    full = _full(tmp_path / "full")
    batch = extract(
        [FIXTURE / MAIN], root=FIXTURE, cache_root=tmp_path / "batch", parallel=False
    )
    expected = _imports_by_line(full, MAIN)
    got = _imports_by_line(batch, MAIN)
    for line in ("L4", "L6", "L8", "L18"):
        assert got[line] == expected[line], line


def test_without_project_file_luau_edges_are_unchanged(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    shutil.copytree(FIXTURE / "src", corpus / "src")
    with_pass = extract(_sources(corpus), root=corpus, cache_root=tmp_path / "a", parallel=False)
    monkeypatch.setattr(extract_module, "resolve_rojo_requires", lambda *_, **__: None)
    without_pass = extract(
        _sources(corpus), root=corpus, cache_root=tmp_path / "b", parallel=False
    )

    def imports(result: dict) -> set[tuple]:
        return {
            (e["source"], e["target"], e["source_location"])
            for e in result["edges"]
            if e["relation"] == "imports"
        }

    assert imports(with_pass) == imports(without_pass)
    assert "script_parent_other" in set(_imports_by_line(with_pass, MAIN).values())


def test_project_file_above_the_scan_root_is_ignored(tmp_path):
    """Only project files inside the scanned tree count: one above it, such
    as a stray file in a parent temp dir, does not describe the corpus."""
    shutil.copytree(FIXTURE, tmp_path / "repo")
    corpus = tmp_path / "repo" / "src"
    result = extract(_sources(corpus), root=corpus, cache_root=tmp_path / "c", parallel=False)
    imports = _imports_by_line(result, "server/Main.server.luau")
    assert "script_parent_other" in set(imports.values())
    assert all(not line.startswith("L") for line in imports)
