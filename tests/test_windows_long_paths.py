r"""Regression coverage for Windows extended-length path handling.

Graphify keeps normal drive/UNC spellings as its public path identity and uses
``\\?\`` only when crossing an operating-system I/O boundary. These tests run
on every host; the deep-path integrations exercise native long paths on Windows
and verify that Linux/macOS remain unchanged.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from graphify.cache import file_hash
from graphify.detect import FileType, detect, load_manifest, save_manifest
from graphify.extract import collect_files, extract
from graphify.extractors.markdown import extract_markdown
from graphify.paths import (
    glob_paths,
    io_path,
    iterdir_path,
    logical_path,
    make_dirs,
    path_exists,
    path_is_file,
    path_stat,
    read_bytes,
    read_text,
    walk_path,
    write_text,
)


def _deep_parent(root: Path, filename: str, *, minimum_length: int = 320) -> Path:
    """Return a parent whose ordinary child path exceeds ``minimum_length``."""
    parent = root
    index = 0
    while len(str(parent / filename)) <= minimum_length:
        parent /= f"level_{index:02d}_{'x' * 28}"
        index += 1
    return parent


def _remove_tree(path: Path) -> None:
    """Clean up a deep Windows tree without relying on pytest's plain path I/O."""
    shutil.rmtree(io_path(path), ignore_errors=True)


def test_io_path_is_a_noop_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    value = "/tmp/a/deep/file.py"
    assert io_path(value) == value
    assert logical_path(value) == value


@pytest.mark.parametrize(
    ("ordinary", "extended"),
    [
        (r"C:\repo\src\module.py", r"\\?\C:\repo\src\module.py"),
        (
            r"\\server\share\manuals\deep\file.pdf",
            r"\\?\UNC\server\share\manuals\deep\file.pdf",
        ),
    ],
)
def test_io_path_converts_windows_drive_and_unc_paths(
    monkeypatch: pytest.MonkeyPatch,
    ordinary: str,
    extended: str,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert io_path(ordinary) == extended
    assert logical_path(extended) == ordinary
    assert io_path(extended) == extended


def test_io_path_normalizes_before_prefixing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert io_path(r"C:\repo\one\..\two/file.py") == r"\\?\C:\repo\two\file.py"


def test_walk_path_uses_extended_unc_and_yields_logical_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    root = r"\\server\share\root"
    extended = r"\\?\UNC\server\share\root"
    called_with: list[str] = []

    def fake_walk(top, *, topdown, followlinks, onerror):
        called_with.append(top)
        assert topdown is True
        assert followlinks is False
        assert onerror is not None
        yield top, ["deep"], ["root.py"]
        yield top + r"\deep", [], ["nested.py"]

    monkeypatch.setattr("graphify.paths.os.walk", fake_walk)
    rows = list(walk_path(root, onerror=lambda _error: None))

    assert called_with == [extended]
    assert rows == [
        (root, ["deep"], ["root.py"]),
        (root + r"\deep", [], ["nested.py"]),
    ]


def test_walk_path_preserves_relative_windows_spelling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    root = r"relative\root"

    def fake_walk(top, *, topdown, followlinks, onerror):
        del topdown, followlinks, onerror
        yield top, ["deep"], ["root.py"]
        yield top + r"\deep", [], ["nested.py"]

    monkeypatch.setattr("graphify.paths.os.walk", fake_walk)
    rows = list(walk_path(root))

    assert rows == [
        (root, ["deep"], ["root.py"]),
        (root + r"\deep", [], ["nested.py"]),
    ]


def test_walk_path_removes_prefix_from_reported_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    root = r"\\server\share\root"
    reported: list[OSError] = []

    def fake_walk(top, *, topdown, followlinks, onerror):
        del topdown, followlinks
        assert onerror is not None
        onerror(FileNotFoundError(3, "not found", top + r"\too\deep"))
        return []

    monkeypatch.setattr("graphify.paths.os.walk", fake_walk)
    assert list(walk_path(root, onerror=reported.append)) == []
    assert len(reported) == 1
    assert reported[0].filename == root + r"\too\deep"


def test_deep_path_discovery_hash_manifest_and_markdown_extraction(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    cache_root = tmp_path / "cache"
    parent = _deep_parent(root, "notes.md")
    source = parent / "notes.md"
    manifest_path = parent / "graphify-out" / "manifest.json"

    try:
        make_dirs(parent, exist_ok=True)
        write_text(source, "# Deep manual\n\nLong-path content.\n", encoding="utf-8")
        assert len(str(source)) > 300
        assert path_exists(source)
        assert path_is_file(source)
        assert path_stat(source).st_size > 0
        assert source in set(iterdir_path(parent))
        assert source in set(glob_paths(parent, "*.md"))
        assert source in set(glob_paths(root, "**/*.md"))
        assert read_bytes(source, limit=13) == b"# Deep manual"

        result = detect(root, cache_root=cache_root)
        assert result["walk_errors"] == []
        assert str(source) in result["files"][FileType.DOCUMENT]
        assert source in collect_files(root, root=root)

        first_hash = file_hash(source, root, cache_root=cache_root)
        second_hash = file_hash(source, root, cache_root=cache_root)
        assert first_hash and first_hash == second_hash

        save_manifest(
            {FileType.DOCUMENT: [str(source)]},
            str(manifest_path),
            root=root,
        )
        loaded = load_manifest(str(manifest_path), root=root)
        assert str(source) in loaded
        assert "\\\\?\\" not in read_text(manifest_path, encoding="utf-8")
        for cache_file in glob_paths(cache_root, "**/*.json"):
            assert "\\\\?\\" not in read_text(cache_file, encoding="utf-8")

        extracted = extract_markdown(source)
        assert any(node.get("label") == "Deep manual" for node in extracted["nodes"])

        serialized = json.dumps({"detect": result, "extract": extracted}, default=str)
        assert "\\\\?\\" not in serialized
    finally:
        _remove_tree(root)


def test_deep_python_path_full_extraction(tmp_path: Path) -> None:
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_python")

    root = tmp_path / "corpus"
    cache_root = tmp_path / "cache"
    parent = _deep_parent(root, "deep_module.py")
    source = parent / "deep_module.py"

    try:
        make_dirs(parent, exist_ok=True)
        write_text(
            source,
            "class DeepThing:\n"
            "    def answer(self):\n"
            "        return 42\n",
            encoding="utf-8",
        )

        first = extract(
            [source],
            root=root,
            cache_root=cache_root,
            parallel=False,
        )
        # Exercise the warm-cache path as well as first-pass parsing. The 0.9.30
        # cache portability code resolves both the corpus root and source path;
        # those lookups must cross the same Windows I/O boundary.
        second = extract(
            [source],
            root=root,
            cache_root=cache_root,
            parallel=False,
        )

        for result in (first, second):
            assert any(node.get("label") == "DeepThing" for node in result["nodes"])
            assert "\\\\?\\" not in json.dumps(result, default=str)
        for cache_file in glob_paths(cache_root, "**/*.json"):
            assert "\\\\?\\" not in read_text(cache_file, encoding="utf-8")
    finally:
        _remove_tree(root)


def test_static_js_import_existence_check_uses_filesystem_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """0.9.41's local-import guard must not call ``Path.is_file`` directly."""
    import graphify.extract as extract_module

    class _Node:
        def __init__(
            self,
            node_type: str,
            *,
            start: int = 0,
            end: int = 0,
            children: tuple["_Node", ...] = (),
        ) -> None:
            self.type = node_type
            self.start_byte = start
            self.end_byte = end
            self.start_point = (0, 0)
            self.children = list(children)

        def child_by_field_name(self, _name: str) -> None:
            return None

    source = b"import './dep.js'"
    string_start = source.index(b"'")
    string_node = _Node("string", start=string_start, end=len(source))
    import_node = _Node("import_statement", children=(string_node,))
    target = Path(r"C:\very\deep\dep.js")
    calls: list[Path] = []

    monkeypatch.setattr(
        extract_module,
        "_resolve_js_import_target",
        lambda _raw, _source: ("dep_file", target),
    )
    monkeypatch.setattr(
        extract_module,
        "_path_is_file",
        lambda path: calls.append(Path(path)) or True,
    )

    edges: list[dict] = []
    extract_module._import_js(
        import_node,
        source,
        "main_file",
        "main",
        edges,
        "main.js",
    )

    assert calls == [target]
    assert edges[0]["target"] == "dep_file"
    assert edges[0]["target_file"] == str(target)
