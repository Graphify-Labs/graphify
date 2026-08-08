r"""#1655 — files whose absolute path exceeds Windows MAX_PATH (260) must still
be hashed, or their manifest entry never stabilizes and detect_incremental
re-flags them as changed on every run.

The plain file APIs reject long paths on win32 unless prefixed with the
extended-length marker `\\?\`. _os_path adds it (for I/O), the mirror of
cache._normalize_path which strips it (for stable keys).
"""
from __future__ import annotations

from pathlib import Path

from graphify import detect


def test_os_path_noop_on_posix(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    p = Path("/home/user/deep/file.py")
    assert detect._os_path(p) == str(p)


def test_os_path_adds_prefix_on_win32(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    # os.path.abspath is posix here, so exercise the already-qualified branch:
    # a value that abspath leaves intact still gets the prefix.
    out = detect._os_path(Path("/already/abs/file.py"))
    assert out.startswith("\\\\?\\")


def test_os_path_idempotent_on_win32(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    already = "\\\\?\\C:\\a\\file.py"
    assert detect._os_path(Path(already)) == already


def test_hashing_still_works_and_stabilizes(tmp_path):
    # End-to-end (posix): a hashed file must produce a stable, non-empty hash so
    # its manifest entry doesn't churn. Guards against the _os_path indirection
    # breaking normal hashing.
    f = tmp_path / "deep" / "nested" / "module.py"
    f.parent.mkdir(parents=True)
    f.write_text("def x():\n    return 1\n")
    h1 = detect._md5_file(f)
    h2 = detect._md5_file(f)
    assert h1 and h1 == h2

    got = detect._stat_and_hash(str(f))
    assert got is not None
    assert got[0] == str(f)
    assert got[2] == h1
