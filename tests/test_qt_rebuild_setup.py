"""INC-QML-123: unavailable coordination storage is not contention or publication."""
from __future__ import annotations

import builtins
from contextlib import contextmanager, nullcontext
import errno
import os
from pathlib import Path
import stat

import pytest

import graphify.watch as watch
from tests.test_qt_final_incremental_parity import manual_update, run


def snapshot(root):
    """Keep every accepted product/cache/state byte outside coordination files."""
    output = root / "graphify-out"
    return {path.relative_to(output).as_posix(): path.read_bytes()
            for path in output.rglob("*") if path.is_file()
            and path.name not in {".rebuild.lock", ".pending_changes", ".pending_full"}}


def project(root, monkeypatch, operation):
    source = root / "unit.py"
    source.write_bytes(b"def retained(): return 1\n")
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    run(root, monkeypatch, operation)
    source.write_bytes(b"def retained(): return 2\n")
    output = root / "graphify-out"
    (output / ".pending_changes").write_bytes(b"older.py\n")
    (output / ".pending_full").write_bytes(b"")
    return source, output


@contextmanager
def native_denial(output):
    """Qualify native denial; real Windows holder bytes survive a failed opener."""
    lock = output / ".rebuild.lock"
    if os.name == "nt":
        with watch._rebuild_lock(output) as acquired:
            assert acquired is True
            contents, mode = lock.read_bytes(), lock.stat().st_mode
            lock.chmod(stat.S_IREAD)
            try:
                with pytest.raises(PermissionError):
                    with open(lock, "a+", encoding="utf-8"):
                        pass
                yield contents
                assert lock.read_bytes() == contents
            finally:
                lock.chmod(mode)
                assert lock.stat().st_mode == mode
        assert not lock.exists()
    else:
        # Privileged hosts must not claim a directory denial they can bypass.
        mode = output.stat().st_mode
        probe = output / ".native-lock-parent-probe"
        output.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        try:
            try:
                descriptor = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except PermissionError:
                pass
            else:
                os.close(descriptor)
                pytest.skip("Host bypasses native directory denial; EACCES seam cases remain applicable")
            assert not lock.exists()
            yield None
            assert not lock.exists()
        finally:
            output.chmod(mode)
            probe.unlink(missing_ok=True)
            assert output.stat().st_mode == mode


@contextmanager
def denied_setup(output, mechanism, monkeypatch):
    """Inject only the unavailable POSIX setup syscall, never validation or writer results."""
    with monkeypatch.context() as fault:
        if mechanism == "open":
            original = builtins.open

            def unavailable(file, *args, **kwargs):
                if isinstance(file, (str, os.PathLike)) and Path(file).resolve() == (output / ".rebuild.lock").resolve():
                    raise PermissionError(errno.EACCES, "Test-owned lock open denial")
                return original(file, *args, **kwargs)

            fault.setattr(builtins, "open", unavailable)
        else:
            original_mkdir = Path.mkdir

            def unavailable_parent(path, *args, **kwargs):
                if path.resolve() == output.resolve():
                    raise PermissionError(errno.EACCES, "Test-owned lock-parent mkdir denial")
                return original_mkdir(path, *args, **kwargs)

            fault.setattr(Path, "mkdir", unavailable_parent)
        yield


def assert_repeat(before, after, operation):
    """A full queued recovery can acquire an incremental stamp on explicit repetition."""
    import json
    changed = {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
    if changed:
        assert operation == "watch" and changed == {".graphify_build_state.json"}
        old, new = (json.loads(values[".graphify_build_state.json"]) for values in (before, after))
        assert old["full_clean"] is True and new["full_clean"] is False
        assert {k: v for k, v in old.items() if k != "full_clean"} == {k: v for k, v in new.items() if k != "full_clean"}


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("mechanism", ["native", "open", "mkdir"])
def test_req_qml012_ac01_lock_storage_denial_retains_then_recovers(tmp_path, monkeypatch, capsys, operation, mechanism):
    """Actual CLI/watch denial retains products/cache/input/pending/holder before repair."""
    source, output = project(tmp_path, monkeypatch, operation)
    accepted = snapshot(tmp_path)
    previous_queue = (output / ".pending_changes").read_bytes()
    input_before = source.read_bytes(), source.stat().st_mtime_ns
    lock_context = native_denial(output) if mechanism == "native" else nullcontext(None)
    with lock_context as holder:
        fault = denied_setup(output, mechanism, monkeypatch) if mechanism != "native" else nullcontext()
        with fault:
            for attempt in range(2):
                if operation == "manual":
                    with pytest.raises(SystemExit) as error:
                        manual_update(tmp_path, monkeypatch)
                    assert error.value.code == 1
                else:
                    assert not watch._rebuild_code(tmp_path, changed_paths=[source], no_cluster=True)
                captured = capsys.readouterr()
                assert "REBUILD_SETUP_FAILED" in captured.out + captured.err
                stage = "queue" if operation == "watch" and mechanism == "mkdir" else "lock"
                assert f"stage={stage}" in captured.out + captured.err
                assert "already in progress" not in captured.out + captured.err
                assert snapshot(tmp_path) == accepted
                assert (source.read_bytes(), source.stat().st_mtime_ns) == input_before
                assert (output / ".pending_full").read_bytes() == b""
                current_queue = (output / ".pending_changes").read_bytes()
                assert current_queue.startswith(previous_queue)
                if operation == "manual" or mechanism == "mkdir":
                    assert current_queue == previous_queue
                else:
                    assert current_queue == previous_queue + (str(source) + os.linesep).encode() * (attempt + 1)
                if holder is not None:
                    assert (output / ".rebuild.lock").read_bytes() == holder
    run(tmp_path, monkeypatch, operation, [source])
    assert not any((output / name).exists() for name in (".pending_changes", ".pending_full", ".rebuild.lock"))
    repaired = snapshot(tmp_path)
    run(tmp_path, monkeypatch, operation, [source])
    assert_repeat(repaired, snapshot(tmp_path), operation)
    assert (source.read_bytes(), source.stat().st_mtime_ns) == input_before
    assert not list(output.glob(".gfy-*.tmp"))


@pytest.mark.parametrize("full", [False, True])
def test_req_qml012_ac02_queue_setup_denial_is_controlled_before_lock(tmp_path, monkeypatch, capsys, full):
    """Failed queue append/marker setup neither enters analysis nor claims it queued work."""
    source, output = project(tmp_path, monkeypatch, "watch")
    accepted = snapshot(tmp_path)
    queue = {name: (output / name).read_bytes() for name in (".pending_changes", ".pending_full")}
    target = output / (".pending_full" if full else ".pending_changes")
    with monkeypatch.context() as fault:
        if full:
            original_touch = Path.touch

            def denied_touch(path, *args, **kwargs):
                if path.resolve() == target.resolve():
                    raise PermissionError(errno.EACCES, "Test-owned queue marker denial")
                return original_touch(path, *args, **kwargs)

            fault.setattr(Path, "touch", denied_touch)
        else:
            original_open = builtins.open

            def denied_append(file, *args, **kwargs):
                if isinstance(file, (str, os.PathLike)) and Path(file).resolve() == target.resolve():
                    raise PermissionError(errno.EACCES, "Test-owned queue append denial")
                return original_open(file, *args, **kwargs)

            fault.setattr(builtins, "open", denied_append)
        for _ in range(2):
            assert not watch._rebuild_code(tmp_path, changed_paths=None if full else [source], no_cluster=True)
            captured = capsys.readouterr()
            assert "REBUILD_SETUP_FAILED" in captured.out and "stage=queue" in captured.out
            assert "already in progress" not in captured.out and "changes queued" not in captured.out
            assert snapshot(tmp_path) == accepted and not (output / ".rebuild.lock").exists()
            assert {name: (output / name).read_bytes() for name in queue} == queue
    run(tmp_path, monkeypatch, "watch", [source])
    assert not any((output / name).exists() for name in (*queue, ".rebuild.lock"))


@pytest.mark.parametrize("full", [False, True])
def test_req_qml012_ac01_real_contention_keeps_holder_and_pending_requests(tmp_path, monkeypatch, capsys, full):
    """Writable coordination storage still reports real native contention, not an error."""
    source, output = project(tmp_path, monkeypatch, "watch")
    accepted = snapshot(tmp_path)
    with watch._rebuild_lock(output) as acquired:
        assert acquired is True
        holder = (output / ".rebuild.lock").read_bytes()
        assert not watch._rebuild_code(tmp_path, changed_paths=None if full else [source], no_cluster=True)
        captured = capsys.readouterr()
        assert "already in progress" in captured.out and "REBUILD_SETUP_FAILED" not in captured.out + captured.err
        assert (output / ".rebuild.lock").read_bytes() == holder and snapshot(tmp_path) == accepted
        assert (output / ".pending_changes").read_bytes().startswith(b"older.py\n")
    run(tmp_path, monkeypatch, "watch", [source])
    assert not (output / ".rebuild.lock").exists()


def test_req_qml012_ac02_body_error_is_not_relabelled_as_lock_storage(tmp_path, monkeypatch, capsys):
    """An expensive body failure propagates past the setup guard and releases its real mutex."""
    source, output = project(tmp_path, monkeypatch, "watch")
    accepted = snapshot(tmp_path)
    original = watch._rebuild_code

    def failing_body(path, **kwargs):
        assert kwargs.get("acquire_lock") is False
        raise OSError(errno.EIO, "Test-owned body boundary failure")

    with monkeypatch.context() as fault:
        fault.setattr(watch, "_rebuild_code", failing_body)
        with pytest.raises(OSError) as failure:
            original(tmp_path, changed_paths=[source], no_cluster=True)
        assert failure.value.errno == errno.EIO
    assert "REBUILD_SETUP_FAILED" not in capsys.readouterr().out
    assert not (output / ".rebuild.lock").exists() and snapshot(tmp_path) == accepted
