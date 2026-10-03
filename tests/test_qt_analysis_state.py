"""QML-011 config/parser-contract state; incomplete stages cannot advance a stamp."""
import json

import pytest

from graphify.qt_analysis_state import (
    QT_STATE_FILE, commit_qt_analysis, inspect_qt_analysis, qt_configuration_changed,
    read_qt_fingerprint, save_qt_fingerprint,
)
from graphify.qt_incremental import qt_analysis_fingerprint


def fingerprint(**changes):
    return qt_analysis_fingerprint(**{"parser_version": "qmljs-test-1", "fact_version": 1, **changes})


def test_successful_configuration_checkpoint_and_contract_change_require_refresh(tmp_path):
    original = fingerprint()
    assert qt_configuration_changed(tmp_path, original)
    assert not tmp_path.joinpath(QT_STATE_FILE).exists()
    save_qt_fingerprint(tmp_path, original)
    assert read_qt_fingerprint(tmp_path) == original
    assert not qt_configuration_changed(tmp_path, original)
    for changed in (fingerprint(parser_version="qmljs-test-2"), fingerprint(fact_version=2),
                    fingerprint(import_roots=["imports", "."]), fingerprint(ignore_patterns=["generated/"])):
        assert qt_configuration_changed(tmp_path, changed)
        assert read_qt_fingerprint(tmp_path) == original
    payload = json.loads(tmp_path.joinpath(QT_STATE_FILE).read_text())
    assert set(payload) == {"schema", "fingerprint", "has_qt"}


@pytest.mark.parametrize("raw", [
    b"invalid", b"\xff", b"[]", b'{"schema":2,"fingerprint":"' + b"a" * 64 + b'"}',
    b'{"schema":true,"fingerprint":"' + b"a" * 64 + b'"}',
    b'{"schema":1,"fingerprint":"bad"}', b"x" * 1025,
])
def test_corrupt_or_incompatible_state_cannot_validate_cached_resolution(tmp_path, raw):
    path = tmp_path / QT_STATE_FILE
    path.write_bytes(raw)
    assert read_qt_fingerprint(tmp_path) is None
    assert qt_configuration_changed(tmp_path, fingerprint())
    assert path.read_bytes() == raw


def test_invalid_checkpoint_and_failed_publication_do_not_replace_last_valid_state(tmp_path, monkeypatch):
    save_qt_fingerprint(tmp_path, fingerprint())
    original = (tmp_path / QT_STATE_FILE).read_bytes()
    with pytest.raises(ValueError, match="QT_CONFIG"):
        save_qt_fingerprint(tmp_path, "invalid")
    def unavailable(*_args, **_kwargs):
        raise OSError("isolated persistence failure")
    monkeypatch.setattr("graphify.qt_analysis_state.write_text_atomic", unavailable)
    with pytest.raises(OSError):
        save_qt_fingerprint(tmp_path, fingerprint(fact_version=2))
    assert (tmp_path / QT_STATE_FILE).read_bytes() == original


def test_inspection_import_root_order_and_known_input_inventory(tmp_path, monkeypatch):
    root, out = tmp_path / "root", tmp_path / "out"
    root.mkdir()
    path = root / "Main.qml"
    path.write_text("Item {}")
    state = inspect_qt_analysis(root, out, [path])
    assert state.changed and state.has_qt and state.import_roots == (".",)
    assert not out.exists()
    commit_qt_analysis(out, state)
    assert not inspect_qt_analysis(root, out, [path]).changed
    monkeypatch.setenv("GRAPHIFY_QML_IMPORT_ROOTS", '["imports", "."]')
    imported = inspect_qt_analysis(root, out, [path])
    assert imported.changed and imported.import_roots == ("imports", ".")
    assert not (root / "imports").exists()
    commit_qt_analysis(out, imported)
    monkeypatch.setenv("GRAPHIFY_QML_IMPORT_ROOTS", '[".", "imports"]')
    assert inspect_qt_analysis(root, out, [path]).changed
    removed = inspect_qt_analysis(root, out, [])
    assert removed.changed and removed.has_qt and not removed.current_has_qt
    commit_qt_analysis(out, removed)
    assert not inspect_qt_analysis(root, out, []).has_qt


def test_package_fact_policy_and_ignore_configuration_invalidate_unchanged_qml(tmp_path, monkeypatch):
    from graphify.qt_incremental import QT_POLICY_VERSION

    path = tmp_path / "nested/Main.qml"
    path.parent.mkdir()
    path.write_text("Item {}")
    out = tmp_path / "out"
    monkeypatch.setattr("graphify.qt_analysis_state._package_versions", lambda: "test-pack-1")
    state = inspect_qt_analysis(tmp_path, out, [path])
    commit_qt_analysis(out, state)
    monkeypatch.setattr("graphify.qt_analysis_state._package_versions", lambda: "test-pack-2")
    assert inspect_qt_analysis(tmp_path, out, [path]).changed
    monkeypatch.setattr("graphify.qt_analysis_state._package_versions", lambda: "test-pack-1")
    monkeypatch.setattr("graphify.qt_analysis_state.CONTRACT_VERSION", 2)
    assert inspect_qt_analysis(tmp_path, out, [path]).changed
    monkeypatch.setattr("graphify.qt_analysis_state.CONTRACT_VERSION", 1)
    monkeypatch.setattr("graphify.qt_incremental.QT_POLICY_VERSION", QT_POLICY_VERSION + 1)
    assert inspect_qt_analysis(tmp_path, out, [path]).changed
    monkeypatch.setattr("graphify.qt_incremental.QT_POLICY_VERSION", QT_POLICY_VERSION)
    ignore = path.parent / ".graphifyignore"
    ignore.write_bytes(b"ignored.qml\n")
    assert inspect_qt_analysis(tmp_path, out, [path]).changed
    ignore.unlink()
    (tmp_path / ".gitignore").write_bytes(b"generated/\n")
    assert inspect_qt_analysis(tmp_path, out, [path]).changed
    assert not inspect_qt_analysis(tmp_path, out, [path], gitignore=False).fingerprint == state.fingerprint
    assert inspect_qt_analysis(tmp_path, out, [path], excludes=["generated/"]).changed


@pytest.mark.parametrize("raw", ["invalid", "{}", "[1]", '["../outside"]', '["/outside"]',
                                 '["C:/outside"]', '[""]', '["a/../../outside"]',
                                 "[" + ",".join('"a"' for _ in range(257)) + "]", "x" * 65537],
                         ids=["invalid-json", "object", "number", "parent", "absolute", "drive",
                              "empty", "traversal", "count-limit", "byte-limit"])
def test_malformed_or_outside_import_config_rejects_before_stamp_write(tmp_path, monkeypatch, raw):
    if len(raw) > 32767:
        monkeypatch.setattr("graphify.qt_analysis_state.os.environ", {"GRAPHIFY_QML_IMPORT_ROOTS": raw})
    else:
        monkeypatch.setenv("GRAPHIFY_QML_IMPORT_ROOTS", raw)
    with pytest.raises(ValueError, match="QT_CONFIG"):
        inspect_qt_analysis(tmp_path, tmp_path / "out", [])
    assert not (tmp_path / "out").exists()


def test_inspection_bounded_ignores_and_outside_inputs_do_not_read_host_files(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / ".graphifyignore").write_bytes(b"x" * 1_048_577)
    with pytest.raises(ValueError, match="QT_CONFIG_LIMIT"):
        inspect_qt_analysis(root, root / "out", [])
    with pytest.raises(ValueError, match="QT_CONFIG"):
        inspect_qt_analysis(root, root / "out", [tmp_path / "host.qml"])
    with pytest.raises(ValueError, match="QT_CONFIG"):
        inspect_qt_analysis(root, root / "out", [root])
