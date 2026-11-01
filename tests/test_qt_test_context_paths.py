"""INC-QML-78: quoted context paths never expand source discovery or escape root."""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extractors.qt_cpp_test_context import build_qt_test_contexts
from graphify.extractors.qt_cpp_syntax import QtCppError, read_cpp


def fixture(root, literal):
    path = root / "checks.cpp"
    path.write_text('#include "' + literal + '"\n#include <QTest>\nvoid run(){QFETCH(int,value);}\n', encoding="utf-8")
    return path


@pytest.mark.parametrize("failure", [OSError, RuntimeError])
def test_req_qml022_ac06_unresolvable_quoted_path_is_explicitly_unavailable(tmp_path, monkeypatch, failure):
    """Resolver errors on an untrusted literal are rejection evidence, not a global abort."""
    path = fixture(tmp_path, "loop.hpp")
    resolve = Path.resolve

    def resolve_path(self, *args, **kwargs):
        if self.name == "loop.hpp":
            raise failure("untrusted path detail must not escape")
        return resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve_path)
    snapshot = build_qt_test_contexts([path], root=tmp_path)
    with pytest.raises(QtCppError) as error:
        read_cpp(path, tmp_path, qt_test_context=snapshot.for_path(path))
    assert error.value.code == "QT_CPP_SYNTAX" and "untrusted path" not in str(error.value)


def test_req_qml022_ac06_foreign_and_dangling_inputs_are_not_opened(tmp_path, monkeypatch):
    """An existing outside file and an absent header remain outside caller admission."""
    root = tmp_path / "root"
    root.mkdir()
    path = fixture(root, "../outside.hpp")
    outside = tmp_path / "outside.hpp"
    outside.write_bytes(b"#include <QTest>\n")
    opened, original = [], Path.open

    def open_path(self, *args, **kwargs):
        opened.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_path)
    snapshot = build_qt_test_contexts([path, outside], root=root)
    assert outside not in opened
    assert len(snapshot.paths) == 1
    path.write_text('#include "dangling.hpp"\n#include <QTest>\nvoid run(){QFETCH(int,value);}\n', encoding="utf-8")
    opened.clear()
    build_qt_test_contexts([path], root=root)
    assert all(item.name != "dangling.hpp" for item in opened)


def test_req_qml022_ac06_real_symlink_cycle_is_bounded_when_platform_allows(tmp_path):
    """An actual filesystem loop cannot become include context or abort the snapshot."""
    first, second = tmp_path / "first.hpp", tmp_path / "second.hpp"
    try:
        first.symlink_to(second)
        second.symlink_to(first)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"Creating symlinks is unavailable on this platform ({type(error).__name__})")
    path = fixture(tmp_path, "first.hpp")
    snapshot = build_qt_test_contexts([path], root=tmp_path)
    with pytest.raises(QtCppError) as error:
        read_cpp(path, tmp_path, qt_test_context=snapshot.for_path(path))
    assert error.value.code == "QT_CPP_SYNTAX"
