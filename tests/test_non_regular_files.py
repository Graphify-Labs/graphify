"""A repository may contain files that are not regular files.

``clone <github-url>`` exists to point the extractor at trees the operator did
not write, and ``watch`` re-runs the scan silently, so the corpus walk has to
survive whatever a repository happens to contain.

The decisive case is a FIFO carrying a source suffix: ``open()`` on a named
pipe with no writer blocks forever and never raises, so the ``try``/``except``
around every reader cannot help — ``graphify update`` simply never returns and
prints nothing. A unix socket fails differently (``ENXIO``) but for the same
reason: it is not a regular file.
"""
import os
import socket
import stat
import tempfile
from pathlib import Path

import pytest

from graphify.detect import _is_regular_file


@pytest.fixture()
def tree():
    d = tempfile.mkdtemp(prefix="nonregular-")
    src = Path(d, "src")
    src.mkdir()
    (src / "module.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    yield Path(d)


def test_regular_source_file_is_accepted(tree):
    assert _is_regular_file(tree / "src" / "module.py") is True


def test_fifo_is_rejected(tree):
    """The shape that hangs the whole run."""
    fifo = tree / "src" / "pipe.py"
    os.mkfifo(fifo)
    assert stat.S_ISFIFO(os.stat(fifo).st_mode)
    assert _is_regular_file(fifo) is False


def test_unix_socket_is_rejected(tree):
    sock_path = tree / "src" / "sock.py"
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(str(sock_path))
        assert _is_regular_file(sock_path) is False
    finally:
        sock.close()


def test_directory_named_like_a_source_file_is_rejected(tree):
    d = tree / "src" / "package.py"
    d.mkdir()
    assert _is_regular_file(d) is False


def test_symlink_to_a_regular_file_is_accepted(tree):
    target = tree / "src" / "module.py"
    link = tree / "src" / "alias.py"
    link.symlink_to(target)
    assert _is_regular_file(link) is True


def test_symlink_pointing_at_a_fifo_is_rejected(tree):
    """A link to a FIFO blocks exactly like the FIFO, so stat must follow it."""
    fifo = tree / "src" / "real.py"
    os.mkfifo(fifo)
    link = tree / "src" / "link.py"
    link.symlink_to(fifo)
    assert _is_regular_file(link) is False


def test_broken_symlink_is_rejected_without_raising(tree):
    link = tree / "src" / "dangling.py"
    link.symlink_to(tree / "src" / "does-not-exist.py")
    assert _is_regular_file(link) is False


def test_missing_path_is_rejected_without_raising(tree):
    assert _is_regular_file(tree / "src" / "absent.py") is False


def test_char_device_is_rejected():
    dev = Path("/dev/null")
    if not dev.exists():
        pytest.skip("/dev/null unavailable")
    assert _is_regular_file(dev) is False
