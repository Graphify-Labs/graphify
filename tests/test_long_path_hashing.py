r"""#1655 — files whose absolute path exceeds Windows MAX_PATH (260) must still
be hashed, or their manifest entry never stabilizes and ``detect_incremental``
re-flags them as changed on every run.

The plain file APIs reject long paths on win32 unless prefixed with the
extended-length marker ``\\?\``. :func:`graphify.paths.io_path` adds it for I/O,
while cache keys and manifests retain ordinary paths.
"""
from __future__ import annotations

from pathlib import Path

from graphify import detect
from graphify.paths import io_path


def test_os_path_noop_on_posix(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    path = Path("/home/user/deep/file.py")
    assert io_path(path) == str(path)


def test_os_path_adds_prefix_on_win32(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    assert io_path(Path(r"C:\already\abs\file.py")) == r"\\?\C:\already\abs\file.py"


def test_os_path_idempotent_on_win32(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    already = r"\\?\C:\a\file.py"
    assert io_path(Path(already)) == already


def test_hashing_still_works_and_stabilizes(tmp_path):
    # End-to-end (POSIX): a hashed file must produce a stable, non-empty hash so
    # its manifest entry does not churn. This guards against the I/O adapter
    # breaking ordinary Linux/macOS hashing while fixing Windows long paths.
    source = tmp_path / "deep" / "nested" / "module.py"
    source.parent.mkdir(parents=True)
    source.write_text("def x():\n    return 1\n", encoding="utf-8")

    first = detect._md5_file(source)
    second = detect._md5_file(source)
    assert first and first == second

    stat_and_hash = detect._stat_and_hash(str(source))
    assert stat_and_hash is not None
    assert stat_and_hash[0] == str(source)
    assert stat_and_hash[2] == first


def test_cache_relative_source_probe_uses_filesystem_boundary(tmp_path, monkeypatch):
    """0.9.41's CWD-relative cache repair must not bypass long-path I/O."""
    import graphify.cache as cache

    project = tmp_path / "project"
    root = project / "src"
    source = root / "module.py"
    source.parent.mkdir(parents=True)
    source.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.chdir(project)

    calls: list[Path] = []

    def _exists(path: str | Path) -> bool:
        calls.append(Path(path))
        return True

    monkeypatch.setattr(cache, "_path_exists", _exists)
    payload = {"nodes": [{"id": "n", "source_file": "src/module.py"}]}

    cache._relativize_source_files_in(payload, root)

    assert calls == [source]
    assert payload["nodes"][0]["source_file"] == "module.py"
