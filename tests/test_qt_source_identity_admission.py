"""INC-QML-50: physical admission precedes lexical source labels and diagnostics."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import graphify.source_identity as input_identity
from tests.test_qt_followed_metadata_alias import CASES, owned_facts, reader_for
from tests.test_source_alias_provenance import directory_alias  # noqa: F401


@pytest.mark.skipif(os.name == "nt", reason="POSIX physical link/.. traversal semantics")
@pytest.mark.parametrize("inside", [False, True])
@pytest.mark.parametrize("name,key,text", CASES, ids=[case[0] for case in CASES])
def test_req_qml020_ac02_dotdot_input_keeps_actual_physical_target_and_containment(
        tmp_path, directory_alias, monkeypatch, inside, name, key, text):
    """Actual symlink/.. input cannot borrow a lexical trap file's source name or root admission."""
    root = tmp_path / "repo"
    root.mkdir()
    physical_parent = root / "real" if inside else tmp_path / "outside"
    (physical_parent / "deep").mkdir(parents=True)
    raw = b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")
    (physical_parent / name).write_bytes(raw)
    (root / name).write_bytes(b"\xfflexical-trap")
    directory_alias(root / "link", physical_parent / "deep")
    input_path = root / "link" / ".." / name
    assert input_path.resolve() == physical_parent / name
    opened, real_open = [], Path.open

    def record(path, *args, **kwargs):
        opened.append(path)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", record)
    result = reader_for(key)(input_path, root=root)
    if inside:
        owned_facts(result, f"real/{name}", raw)
        assert opened and all(path.resolve() == physical_parent / name for path in opened)
    else:
        assert result.get("error") and not result["nodes"] and not result["edges"]
        assert not opened


@pytest.mark.skipif(os.name != "nt", reason="Native Windows source spelling admission")
@pytest.mark.parametrize("name,key,text", [CASES[index] for index in (0, 1, 2, 4, 6, 7)],
                         ids=["qml", "qmldir", "cmake", "qmake", "qrc", "qmltypes"])
def test_req_qml020_ac02_native_admission_failure_keeps_its_code_and_recovers(
        tmp_path, monkeypatch, capsys, name, key, text):
    """A failed real native API seam retains the existing code, omits backend bodies and repairs cleanly."""
    source = tmp_path / name
    raw = text.encode("utf-8")
    source.write_bytes(raw)
    reader = reader_for(key)
    accepted = reader(source, root=tmp_path)
    assert accepted["nodes"] and not accepted.get("error")
    observed = []
    private_body = "private-native-backend-body\nsecond-delimiter"

    def failed_native(path):
        observed.append(path)
        raise OSError(private_body)

    with monkeypatch.context() as failed:
        failed.setattr(input_identity, "_native_long_name", failed_native)
        result = reader(source, root=tmp_path)
    assert observed and result.get("error") and not result["nodes"] and not result["edges"]
    assert all(item["code"] == "SOURCE_INPUT_IDENTITY_FAILED" for item in result["diagnostics"])
    assert all(item["source_file"] == "" for item in result["diagnostics"])
    assert "QML_ROOT" not in repr(result)
    assert all(fragment not in repr(result) for fragment in private_body.splitlines())
    output = capsys.readouterr()
    assert all(fragment not in output.out + output.err for fragment in private_body.splitlines())
    assert reader(source, root=tmp_path) == accepted == reader(source, root=tmp_path)
    assert source.read_bytes() == raw
