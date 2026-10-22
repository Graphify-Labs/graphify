"""INC-QML-45: native filename admission refuses unsafe partial extraction."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path

import pytest

import graphify.extract as extraction
import graphify.source_identity as identity
import graphify.watch as watch
from tests.test_qt_final_incremental_parity import clean, normalized, project, run
from tests.test_qt_product_publication import no_scratch, snapshot


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows native filename admission")


def caches(output):
    """Retain exact pre-admission cache bytes alongside the accepted product cohort."""
    return {path.relative_to(output).as_posix(): path.read_bytes()
            for path in (output / "cache").rglob("*") if path.is_file()}


def reject_native_api(monkeypatch, source, alternative, fault):
    """Isolate only GetLongPathNameW; filesystem checks and callers remain real."""
    original = ctypes.windll.kernel32.GetLongPathNameW
    observed = []

    def reject(path, buffer, capacity):
        if Path(path).name != source.name:
            return original(path, buffer, capacity)
        observed.append(path)
        if fault == "backend":
            raise PermissionError("synthetic-private-native-body\ncredentials=redact")
        if fault == "zero":
            return 0
        if fault == "oversize":
            return capacity
        if fault == "empty":
            return 1
        if fault == "length":
            buffer.value = str(source)
            return 1
        buffer.value = str(alternative)
        return len(buffer.value.encode("utf-16-le")) // 2

    monkeypatch.setattr(ctypes.windll.kernel32, "GetLongPathNameW", reject)
    return observed


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("fault", ["zero", "oversize", "empty", "length", "target", "backend"])
def test_req_qml012_ac01_ac02_qml020_ac01_native_failure_retains_repairs_and_repeats(
        tmp_path, monkeypatch, capsys, operation, fault):
    """Admission failure precedes workers/cache writes; actual updates recover and repeat."""
    root = tmp_path.resolve()
    source = project(root)
    alternative = root / "keep.py"
    monkeypatch.chdir(root)
    initial = run(root, monkeypatch, operation)
    output = root / "graphify-out"
    before, cached = snapshot(output), caches(output)
    assert cached
    source.write_bytes(source.read_bytes().replace(b"adjustment", b"offset"))
    capsys.readouterr()
    with monkeypatch.context() as failed:
        observed = reject_native_api(failed, source, alternative, fault)
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                run(root, monkeypatch, operation, [source])
            assert rejected.value.code == 1
        else:
            assert not watch._rebuild_code(root, changed_paths=[source], no_cluster=True)
    assert observed and snapshot(output) == before and caches(output) == cached
    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert "SOURCE_INPUT_IDENTITY_FAILED" in text
    assert f"source={json.dumps(source.relative_to(root).as_posix())};" in text
    assert "synthetic-private-native-body" not in text and "credentials=redact" not in text
    assert str(root) not in text.split("Rebuild failed:")[-1]
    no_scratch(output)
    repaired = run(root, monkeypatch, operation, [source])
    assert normalized(repaired) != normalized(initial)
    assert normalized(repaired) == normalized(clean(root, root / "clean-cache"))
    accepted = snapshot(output)
    run(root, monkeypatch, operation, [])
    assert snapshot(output) == accepted
    no_scratch(output)


@pytest.mark.parametrize("shape", ["missing", "directory", "child_of_file"])
def test_req_qml020_ac01_missing_and_nonfile_keep_existing_admission_shape(tmp_path, monkeypatch, shape):
    """Legacy missing/non-file inputs bypass filename expansion and keep their path."""
    source = tmp_path / "existing.py"
    source.write_bytes(b"def existing():\n    return 1\n")
    path = {"missing": tmp_path / "missing.py", "directory": tmp_path,
            "child_of_file": source / "child.py"}[shape]

    def forbidden(*args):
        raise AssertionError("native expansion must not run")

    monkeypatch.setattr(ctypes.windll.kernel32, "GetLongPathNameW", forbidden)
    assert identity.normalize_input_source(path, tmp_path) == path


@pytest.mark.parametrize("label", ["a;delimiter.py", "a\u2028.py", "x" * 157 + ".py", "x" * 158 + ".py"])
def test_req_qml012_ac04_native_context_is_quoted_bounded_and_lexical(tmp_path, monkeypatch, label):
    """Diagnostic context rejects control/oversized text without exposing backend bodies."""
    source = tmp_path / label
    source.write_bytes(b"pass\n")
    reject_native_api(monkeypatch, source, source, "backend")
    with pytest.raises(ValueError) as rejected:
        identity.normalize_input_source(source, tmp_path)
    context = label if len(label) <= 160 and "\u2028" not in label else ""
    assert str(rejected.value) == (f'SOURCE_INPUT_IDENTITY_FAILED: source={json.dumps(context)}; native source '
                                  'spelling unavailable; repair filesystem access and retry')
    assert identity._source_context(source, None) == ""


@pytest.mark.parametrize("fault", [OSError, RuntimeError])
def test_req_qml012_ac04_failed_context_lookup_keeps_bounded_admission_error(tmp_path, monkeypatch, fault):
    """A failed CWD/lexical adapter cannot replace the actual native rejection diagnostic."""
    source = tmp_path / "source.py"
    source.write_bytes(b"pass\n")
    reject_native_api(monkeypatch, source, source, "backend")
    original = os.path.abspath

    def unavailable(path):
        if Path(path) == source:
            raise fault("synthetic-private-cwd-body")
        return original(path)

    monkeypatch.setattr(identity.os.path, "abspath", unavailable)
    with pytest.raises(ValueError) as rejected:
        identity.normalize_input_source(source, tmp_path)
    assert str(rejected.value) == ('SOURCE_INPUT_IDENTITY_FAILED: source=""; native source '
                                   'spelling unavailable; repair filesystem access and retry')


def test_req_qml012_ac01_native_admission_refuses_before_any_worker_or_cache_write(tmp_path, monkeypatch):
    """Direct extraction reports refusal without claiming writer retention or doing work."""
    source = tmp_path / "source.py"
    source.write_bytes(b"def original():\n    return 1\n")
    cache = tmp_path / "cache-owner"
    extraction.extract([source], root=tmp_path, cache_root=cache, parallel=False)
    before = {path.relative_to(cache): path.read_bytes() for path in cache.rglob("*") if path.is_file()}
    assert before
    source.write_bytes(b"def changed():\n    return 2\n")
    reject_native_api(monkeypatch, source, source, "zero")

    def forbidden(*args):
        raise AssertionError("worker must not run")

    monkeypatch.setattr(extraction, "_safe_extract_with_xaml_root", forbidden)
    with pytest.raises(ValueError, match="SOURCE_INPUT_IDENTITY_FAILED") as rejected:
        extraction.extract([source], root=tmp_path, cache_root=cache, parallel=False)
    assert "retained" not in str(rejected.value)
    assert before == {path.relative_to(cache): path.read_bytes() for path in cache.rglob("*") if path.is_file()}


@pytest.mark.parametrize("operation,fault", [("stat", OSError), ("stat", RuntimeError),
                                            ("samefile", None)])
def test_req_qml012_ac01_native_filesystem_identity_failure_is_bounded(tmp_path, monkeypatch, operation, fault):
    """A stat failure or changed entry proof cannot silently admit an existing file."""
    source = tmp_path / "source.py"
    source.write_bytes(b"pass\n")
    original = getattr(Path, operation)

    def unavailable(path, *args, **kwargs):
        if path == source:
            if fault is not None:
                raise fault("synthetic-private-filesystem-body")
            return False
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, operation, unavailable)
    with pytest.raises(ValueError) as rejected:
        identity.normalize_input_source(source, tmp_path)
    assert str(rejected.value) == ('SOURCE_INPUT_IDENTITY_FAILED: source="source.py"; native source '
                                   'spelling unavailable; repair filesystem access and retry')


def test_req_qml020_ac01_nonwindows_input_needs_no_native_lookup(tmp_path, monkeypatch):
    """The platform guard retains POSIX source handling without a Windows dependency."""
    source = tmp_path / "source.py"
    with monkeypatch.context() as other_platform:
        other_platform.setattr(identity.os, "name", "posix")
        assert identity.normalize_input_source(source, tmp_path) is source
