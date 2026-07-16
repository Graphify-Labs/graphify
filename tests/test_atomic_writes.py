"""Tests for atomic JSON writes (graph.json / manifest.json).

A crash, kill, or disk-full mid-write must not leave a truncated/corrupt file
that a later load chokes on. `write_text_atomic` writes a temp file in the same
directory then `os.replace`s it into place; on failure the original is untouched.
"""
import json
import os

import pytest

from graphify.paths import write_text_atomic


def test_write_text_atomic_writes_and_leaves_no_tmp(tmp_path):
    p = tmp_path / "out" / "graph.json"  # parent doesn't exist yet
    write_text_atomic(p, '{"a": 1}')
    assert json.loads(p.read_text()) == {"a": 1}
    # No leftover temp file in the target directory.
    assert [x.name for x in p.parent.iterdir()] == ["graph.json"]


def test_write_text_atomic_preserves_existing_on_failure(tmp_path, monkeypatch):
    p = tmp_path / "graph.json"
    p.write_text("original", encoding="utf-8")

    def boom(src, dst):
        raise OSError("simulated disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        write_text_atomic(p, "content-that-must-not-land")

    # The original file is intact and the temp file was cleaned up.
    assert p.read_text() == "original"
    assert sorted(x.name for x in tmp_path.iterdir()) == ["graph.json"]


def test_write_text_atomic_preserves_existing_mode(tmp_path):
    # An atomic replace must not tighten a 0644 file to mkstemp's 0600 default.
    p = tmp_path / "graph.json"
    p.write_text("{}", encoding="utf-8")
    os.chmod(p, 0o644)
    write_text_atomic(p, '{"x": 1}')
    assert (os.stat(p).st_mode & 0o777) == 0o644


def test_write_text_atomic_new_file_respects_umask(tmp_path):
    # A brand-new file must land at the umask default (e.g. 0644), NOT mkstemp's
    # 0600 — otherwise every fresh graph.json would be owner-only.
    p = tmp_path / "new.json"
    write_text_atomic(p, "{}")
    umask = os.umask(0)
    os.umask(umask)
    assert (os.stat(p).st_mode & 0o777) == (0o666 & ~umask)


def test_write_text_atomic_writes_through_symlink(tmp_path):
    # Shared-output setups symlink graph.json to shared storage; the atomic write
    # must update the target and keep the link, not replace it with a real file.
    target = tmp_path / "real.json"
    target.write_text("old", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    write_text_atomic(link, "new")
    assert link.is_symlink()
    assert target.read_text() == "new"


def test_write_json_atomic_roundtrip(tmp_path):
    from graphify.paths import write_json_atomic

    p = tmp_path / "g.json"
    write_json_atomic(p, {"nodes": [1, 2], "x": "é"}, indent=2)
    assert json.loads(p.read_text()) == {"nodes": [1, 2], "x": "é"}
    assert not any(name.name.endswith(".tmp") for name in tmp_path.iterdir())


def test_to_json_writes_atomically_no_tmp_leftover(tmp_path):
    import networkx as nx
    from graphify.export import to_json

    G = nx.Graph()
    G.add_node("a", label="a", file_type="code")
    G.add_node("b", label="b", file_type="code")
    G.add_edge("a", "b")
    out = tmp_path / "graph.json"
    assert to_json(G, {}, str(out), force=True) is True
    json.loads(out.read_text())  # valid JSON
    assert not any(x.name.endswith(".tmp") for x in tmp_path.iterdir())


def test_save_manifest_writes_atomically(tmp_path):
    from graphify.detect import save_manifest

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    mpath = tmp_path / "graphify-out" / "manifest.json"
    save_manifest({"code": [str(tmp_path / "a.py")]}, manifest_path=str(mpath),
                  kind="both", root=tmp_path)
    assert json.loads(mpath.read_text())  # non-empty, valid JSON
    assert not any(x.name.endswith(".tmp") for x in mpath.parent.iterdir())
