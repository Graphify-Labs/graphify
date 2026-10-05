"""REQ-QML-020: real multi-ancestor short paths retain a nearby alias scenario."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import tempfile

import pytest

from tests.test_qt_facade_path_aliases import (
    GENERIC, assert_sources, graph, nearby_parent_alias, normalized, write_generic,
)


@pytest.fixture(autouse=True)
def many_short_ancestors(tmp_path, monkeypatch):
    """Provide actual long TEMP ancestors before the shared alias fixture runs."""
    if os.name != "nt":
        pytest.skip("Windows short-path API is not applicable on this host")
    parent = tmp_path.resolve()
    for index in range(5):
        parent /= f"graphify long ancestor {index}"
        parent.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(parent))


@pytest.mark.parametrize("nearby_parent_alias", ["windows_short"], indirect=True)
def test_req_qml020_ac01_real_short_ancestors_preserve_nearby_facade_provenance(
        nearby_parent_alias):
    """The real fixture admits one short basename, then cold/warm facts stay equal."""
    parent, alias = nearby_parent_alias
    api = ctypes.windll.kernel32.GetShortPathNameW
    api.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32)
    api.restype = ctypes.c_uint32
    buffer = ctypes.create_unicode_buffer(32768)
    length = api(str(parent), buffer, len(buffer))
    assert 0 < length < len(buffer)
    full_short = Path(buffer.value)
    full_relative = Path(os.path.relpath(full_short, parent))
    if sum(part == ".." for part in full_relative.parts) <= 3:
        pytest.skip("Filesystem does not expose multiple ancestor short-path aliases")
    assert full_short.resolve() == parent and alias.resolve() == parent
    nearby_relative = Path(os.path.relpath(alias, parent))
    assert sum(part == ".." for part in nearby_relative.parts) == 1
    assert alias.parent == parent.parent and alias.name == full_short.name

    # Exercise the same production interface as the original hosted regression;
    # reanchoring the fixture must not hide cold/warm source or edge corruption.
    canonical, supplied = parent / "native-profile", alias / "native-profile"
    canonical.mkdir()
    write_generic(canonical)
    expected, _ = graph(canonical, canonical, parent / "canonical-cache", GENERIC)
    cold, cold_result = graph(supplied, supplied, parent / "alias-cache", GENERIC)
    warm, warm_result = graph(supplied, supplied, parent / "alias-cache", GENERIC)
    assert_sources(cold_result, GENERIC)
    assert_sources(warm_result, GENERIC)
    assert normalized(cold) == normalized(warm) == normalized(expected)
    assert GENERIC == {name: (canonical / name).read_bytes() for name in GENERIC}
