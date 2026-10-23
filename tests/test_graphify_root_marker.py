"""#4346: `.graphify_root` holds a path exactly as Step 1 saved it. Readers may
drop only a UTF-8 BOM (#3028) and one trailing newline: `.strip()` turned a
folder named `proj ` into its sibling `proj`."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from graphify.paths import read_root_marker

trailing_space = pytest.mark.skipif(
    sys.platform == "win32", reason="Windows does not allow a trailing space in a folder name"
)


def _marker(tmp_path: Path, text: str) -> Path:
    out = tmp_path / "graphify-out"
    out.mkdir(exist_ok=True)
    marker = out / ".graphify_root"
    marker.write_text(text, encoding="utf-8")
    return marker


def _spaced_and_sibling(tmp_path: Path) -> tuple[Path, Path]:
    spaced = tmp_path / "proj "
    sibling = tmp_path / "proj"
    spaced.mkdir()
    sibling.mkdir()
    return spaced, sibling


# --- the shared reader ---------------------------------------------------------


@trailing_space
def test_read_root_marker_keeps_a_trailing_space(tmp_path):
    assert read_root_marker(_marker(tmp_path, "/data/proj ")) == "/data/proj "


def test_read_root_marker_keeps_a_leading_space(tmp_path):
    assert read_root_marker(_marker(tmp_path, " /data/proj")) == " /data/proj"


def test_read_root_marker_drops_the_bom_and_one_trailing_newline(tmp_path):
    assert read_root_marker(_marker(tmp_path, "﻿/data/proj\r\n")) == "/data/proj"


def test_read_root_marker_returns_empty_for_an_empty_file(tmp_path):
    assert read_root_marker(_marker(tmp_path, "")) == ""


# --- each reader uses it ---------------------------------------------------------


@trailing_space
def test_infer_merge_root_does_not_switch_to_a_sibling(tmp_path):
    from graphify.build import _infer_merge_root

    spaced, _ = _spaced_and_sibling(tmp_path)
    marker = _marker(tmp_path, str(spaced))
    assert _infer_merge_root(marker.parent / "graph.json") == str(spaced.resolve())


def test_hook_bodies_read_the_marker_without_stripping_spaces():
    """The hook bodies are copied into .git/hooks, so they can't import the helper.
    They must apply the same rule inline."""
    from graphify import hooks

    for body in (hooks._REBUILD_BODY_COMMIT, hooks._REBUILD_BODY_CHECKOUT):
        reads = [line.strip() for line in body.splitlines()
                 if "_saved.read_text(" in line]
        assert reads, "hook body no longer reads .graphify_root"
        for line in reads:
            # No backslash: the body sits inside a shell double-quoted argument.
            assert ".removesuffix(chr(10)).removesuffix(chr(13))" in line, line
            assert ".strip()" not in line and "rstrip" not in line, line


@trailing_space
def test_update_without_a_path_rebuilds_the_recorded_folder(tmp_path):
    spaced, sibling = _spaced_and_sibling(tmp_path)
    (spaced / "a.py").write_text("def only_in_spaced():\n    pass\n", encoding="utf-8")
    (sibling / "b.py").write_text("def only_in_sibling():\n    pass\n", encoding="utf-8")
    _marker(tmp_path, str(spaced))

    result = subprocess.run([sys.executable, "-m", "graphify", "update"],
                            cwd=tmp_path, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    # update writes its output next to the folder it rebuilt, not into the cwd
    graph = (spaced / "graphify-out" / "graph.json").read_text(encoding="utf-8")
    assert "only_in_spaced" in graph
    assert "only_in_sibling" not in graph


def test_update_without_a_path_stops_on_an_empty_marker(tmp_path):
    """An empty marker means Step 1 failed. Don't guess the current directory."""
    _marker(tmp_path, "")

    result = subprocess.run([sys.executable, "-m", "graphify", "update"],
                            cwd=tmp_path, capture_output=True, text=True)

    assert result.returncode == 1
    assert ".graphify_root is empty" in result.stderr
    assert not (tmp_path / "graphify-out" / "graph.json").exists()


def test_no_module_strips_the_marker_after_decoding_it():
    """Every .graphify_root reader goes through read_root_marker (the hook bodies
    use the same rule inline). `.strip()` after a utf-8-sig read is how the old
    readers trimmed the path; watch.py and reflect.py were missed at first (#4346)."""
    import graphify

    pkg = Path(graphify.__file__).parent
    offenders = [
        f"{path.relative_to(pkg)}:{number}"
        for path in pkg.rglob("*.py")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "utf-8-sig" in line and ".strip()" in line
    ]
    assert not offenders, offenders
