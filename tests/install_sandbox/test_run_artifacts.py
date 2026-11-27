from __future__ import annotations

import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tools.install_sandbox import run_artifacts
from tools.install_sandbox.run_artifacts import (
    ArtifactError,
    RunArtifacts,
    complete_outputs,
    make_run_id,
    prune_managed_runs,
)


NOW = datetime(2026, 7, 26, 12, 34, 56, tzinfo=timezone.utc)


def fixed_clock() -> datetime:
    return NOW


def read_metadata(output: Path) -> dict:
    return json.loads((output / "run.json").read_text(encoding="utf-8"))


def allocate(tmp_path: Path, **overrides) -> RunArtifacts:
    arguments = {
        "repo": tmp_path / "repo",
        "target": "demo",
        "all_targets": False,
        "scope": "both",
        "managed_root": tmp_path / "managed",
        "clock": fixed_clock,
    }
    arguments.update(overrides)
    return RunArtifacts.allocate(**arguments)


def write_managed_run(
    root: Path,
    *,
    stamp: datetime,
    collision: int = 1,
    state: str = "passed",
    managed: bool = True,
) -> Path:
    run_id = make_run_id(
        target="demo",
        all_targets=False,
        scope="both",
        started_at=stamp,
        collision=collision,
    )
    output = root / run_id
    output.mkdir(parents=True)
    finished = stamp + timedelta(minutes=1)
    metadata = {
        "schema_version": 1,
        "run_id": run_id,
        "managed": managed,
        "started_at": stamp.isoformat().replace("+00:00", "Z"),
        "updated_at": finished.isoformat().replace("+00:00", "Z"),
        "finished_at": (
            None if state == "running" else finished.isoformat().replace("+00:00", "Z")
        ),
        "repository": str(root.parent / "repo"),
        "output": str(output.resolve()),
        "selection": {"all": False, "target": "demo", "scope": "both"},
        "phase": "container_run",
        "state": state,
        "exit_code": None if state == "running" else 0,
    }
    (output / "run.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )
    return output


def test_run_ids_use_utc_basic_iso_selection_scope_and_numeric_collisions():
    local_time = datetime(
        2026,
        7,
        26,
        8,
        34,
        56,
        tzinfo=timezone(timedelta(hours=-4)),
    )

    assert (
        make_run_id(
            target=None,
            all_targets=True,
            scope="project",
            started_at=local_time,
        )
        == "20260726T123456Z-all-project"
    )
    assert (
        make_run_id(
            target="demo",
            all_targets=False,
            scope="both",
            started_at=NOW,
            collision=2,
        )
        == "20260726T123456Z-demo-both-02"
    )
    assert (
        make_run_id(
            target="demo",
            all_targets=False,
            scope="both",
            started_at=NOW,
            collision=100,
        )
        == "20260726T123456Z-demo-both-100"
    )


def test_allocation_creates_host_artifacts_and_complete_running_metadata(tmp_path):
    artifacts = allocate(tmp_path)

    assert artifacts.output.name == "20260726T123456Z-demo-both"
    assert artifacts.managed is True
    assert (artifacts.output / "runner.log").is_file()
    assert artifacts.logger.closed is False
    assert read_metadata(artifacts.output) == {
        "schema_version": 1,
        "run_id": artifacts.run_id,
        "managed": True,
        "started_at": "2026-07-26T12:34:56Z",
        "updated_at": "2026-07-26T12:34:56Z",
        "finished_at": None,
        "repository": str((tmp_path / "repo").resolve()),
        "output": str(artifacts.output.resolve()),
        "selection": {"all": False, "target": "demo", "scope": "both"},
        "phase": "host_preflight",
        "state": "running",
        "exit_code": None,
    }
    artifacts.logger.close()


def test_same_second_managed_allocations_claim_numeric_collisions_atomically(tmp_path):
    root = tmp_path / "managed"

    def allocate_one(_: int) -> RunArtifacts:
        return RunArtifacts.allocate(
            repo=tmp_path / "repo",
            target="demo",
            all_targets=False,
            scope="both",
            managed_root=root,
            clock=fixed_clock,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        artifacts = list(executor.map(allocate_one, range(12)))

    names = sorted(item.output.name for item in artifacts)
    assert len(set(names)) == 12
    assert "20260726T123456Z-demo-both" in names
    assert "20260726T123456Z-demo-both-02" in names
    assert "20260726T123456Z-demo-both-12" in names
    for item in artifacts:
        assert read_metadata(item.output)["run_id"] == item.output.name
        item.logger.close()


@pytest.mark.parametrize("precreate", [False, True])
def test_external_output_may_be_absent_or_an_empty_real_directory(tmp_path, precreate):
    output = tmp_path / "external" / "leaf"
    if precreate:
        output.mkdir(parents=True)

    artifacts = allocate(tmp_path, output=output)

    assert artifacts.output == output.resolve()
    assert artifacts.managed is False
    assert read_metadata(output)["managed"] is False
    artifacts.logger.close()


def test_external_output_rejects_non_empty_directory_file_and_symlink(tmp_path):
    non_empty = tmp_path / "non-empty"
    non_empty.mkdir()
    (non_empty / "stale").write_text("old", encoding="utf-8")
    file_output = tmp_path / "file"
    file_output.write_text("not a directory", encoding="utf-8")
    real_output = tmp_path / "real"
    real_output.mkdir()
    symlink_output = tmp_path / "link"
    symlink_output.symlink_to(real_output, target_is_directory=True)

    with pytest.raises(ArtifactError, match="must be empty"):
        allocate(tmp_path, output=non_empty)
    with pytest.raises(ArtifactError, match="not a real directory"):
        allocate(tmp_path, output=file_output)
    with pytest.raises(ArtifactError, match="must not be a symlink"):
        allocate(tmp_path, output=symlink_output)


@pytest.mark.parametrize("relative", [".", "manual", "nested/manual"])
def test_explicit_output_must_be_separate_from_managed_root(tmp_path, relative):
    managed_root = tmp_path / "managed"
    output = managed_root / relative

    with pytest.raises(ArtifactError, match="outside the managed output root"):
        allocate(tmp_path, managed_root=managed_root, output=output)


def test_explicit_output_logically_beneath_managed_root_cannot_escape_via_symlink(
    tmp_path,
):
    managed_root = tmp_path / "managed"
    managed_root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (managed_root / "escape").symlink_to(elsewhere, target_is_directory=True)

    with pytest.raises(ArtifactError, match="outside the managed output root"):
        allocate(
            tmp_path,
            managed_root=managed_root,
            output=managed_root / "escape" / "leaf",
        )


def test_set_phase_replaces_run_json_with_a_complete_document(tmp_path, monkeypatch):
    artifacts = allocate(tmp_path)
    metadata_path = artifacts.output / "run.json"
    original_replace = run_artifacts.os.replace
    observations = []

    def observing_replace(source, destination):
        source_value = json.loads(Path(source).read_text(encoding="utf-8"))
        destination_value = json.loads(Path(destination).read_text(encoding="utf-8"))
        observations.append((source_value, destination_value))
        original_replace(source, destination)

    monkeypatch.setattr(run_artifacts.os, "replace", observing_replace)

    artifacts.set_phase("docker_build")

    assert observations[0][0]["phase"] == "docker_build"
    assert observations[0][1]["phase"] == "host_preflight"
    assert read_metadata(artifacts.output)["phase"] == "docker_build"
    assert list(artifacts.output.glob(".run.json.*.tmp")) == []
    artifacts.logger.close()


@pytest.mark.parametrize(
    ("state", "exit_code"),
    [
        ("passed", 0),
        ("failed", 1),
        ("incomplete", 127),
        ("interrupted", 130),
    ],
)
def test_running_run_transitions_to_every_terminal_state(tmp_path, state, exit_code):
    artifacts = allocate(tmp_path)

    artifacts.finalize(state, exit_code)

    metadata = read_metadata(artifacts.output)
    assert metadata["state"] == state
    assert metadata["exit_code"] == exit_code
    assert metadata["finished_at"] == "2026-07-26T12:34:56Z"
    assert artifacts.logger.closed is True
    with pytest.raises(RuntimeError, match="already been finalized"):
        artifacts.finalize(state, exit_code)


def test_phase_logger_labels_file_and_mirrored_console_output(tmp_path, capsys):
    artifacts = allocate(tmp_path)

    artifacts.logger.write("command", "$ preflight")
    artifacts.logger.write("stdout", "preflight ok")
    artifacts.set_phase("docker_build")
    artifacts.logger.write("stderr", "build warning\nsecond line")
    artifacts.logger.close()

    captured = capsys.readouterr()
    log = (artifacts.output / "runner.log").read_text(encoding="utf-8")
    assert "[host_preflight] [command] $ preflight" in captured.out
    assert "[host_preflight] [stdout] preflight ok" in captured.out
    assert "[docker_build] [stderr] build warning" in captured.err
    assert "[docker_build] [stderr] second line" in captured.err
    assert "[host_preflight] [stdout] preflight ok" in log
    assert "[docker_build] [stderr] build warning" in log


def test_complete_outputs_require_fresh_non_empty_regular_non_symlink_files(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    start = NOW
    manifest = output / "manifest.json"
    report = output / "report.md"
    manifest.write_text("{}\n", encoding="utf-8")
    report.write_text("# Report\n", encoding="utf-8")
    fresh = start.timestamp() + 1
    os.utime(manifest, (fresh, fresh))
    os.utime(report, (fresh, fresh))

    assert complete_outputs(output, start) is True

    stale = start.timestamp() - 1
    os.utime(report, (stale, stale))
    assert complete_outputs(output, start) is False

    report.unlink()
    report.write_text("", encoding="utf-8")
    os.utime(report, (fresh, fresh))
    assert complete_outputs(output, start) is False

    report.unlink()
    real_report = output / "real-report.md"
    real_report.write_text("# Report\n", encoding="utf-8")
    os.utime(real_report, (fresh, fresh))
    report.symlink_to(real_report)
    assert complete_outputs(output, start) is False


def test_pruning_counts_all_terminal_states_equally_and_keeps_newest_five(tmp_path):
    root = tmp_path / "managed"
    states = ["passed", "failed", "incomplete", "interrupted", "passed", "failed", "passed"]
    runs = [
        write_managed_run(
            root,
            stamp=NOW + timedelta(minutes=index),
            state=state,
        )
        for index, state in enumerate(states)
    ]

    removed = prune_managed_runs(root, keep=5, warn=lambda message: None)

    assert set(removed) == set(runs[:2])
    assert all(not path.exists() for path in runs[:2])
    assert all(path.is_dir() for path in runs[2:])


def test_pruning_uses_numeric_collision_order_for_same_second_runs(tmp_path):
    root = tmp_path / "managed"
    runs = [
        write_managed_run(root, stamp=NOW, collision=collision)
        for collision in range(1, 8)
    ]

    removed = prune_managed_runs(root, keep=5, warn=lambda message: None)

    assert set(removed) == set(runs[:2])


def test_pruning_preserves_ambiguous_unowned_active_and_symlink_entries(tmp_path):
    root = tmp_path / "managed"
    root.mkdir()
    valid_runs = [
        write_managed_run(root, stamp=NOW + timedelta(minutes=index + 10))
        for index in range(6)
    ]
    running = write_managed_run(root, stamp=NOW, state="running")

    malformed = root / "malformed"
    malformed.mkdir()
    (malformed / "run.json").write_text("{", encoding="utf-8")

    unreadable = root / "unreadable"
    unreadable.mkdir()
    (unreadable / "run.json").write_bytes(b"\xff")

    unmarked = root / "unmarked"
    unmarked.mkdir()

    external = write_managed_run(
        root,
        stamp=NOW + timedelta(minutes=1),
        managed=False,
    )

    symlink_target = tmp_path / "symlink-target"
    symlink_target.mkdir()
    (symlink_target / "sentinel").write_text("keep", encoding="utf-8")
    symlink = root / "20260726T123456Z-demo-both-99"
    symlink.symlink_to(symlink_target, target_is_directory=True)
    warnings = []

    removed = prune_managed_runs(root, keep=5, warn=warnings.append)

    assert removed == (valid_runs[0],)
    for preserved in (running, malformed, unreadable, unmarked, external, symlink):
        assert preserved.exists()
    assert (symlink_target / "sentinel").read_text(encoding="utf-8") == "keep"
    assert any("running managed run" in warning for warning in warnings)
    assert any("malformed run metadata" in warning for warning in warnings)
    assert any("unreadable run metadata" in warning for warning in warnings)
    assert any("unmarked managed-root directory" in warning for warning in warnings)
    assert any("externally owned run" in warning for warning in warnings)
    assert any("symlinked managed-root entry" in warning for warning in warnings)


def test_pruning_tolerates_a_concurrent_removal_race(tmp_path, monkeypatch):
    root = tmp_path / "managed"
    runs = [
        write_managed_run(root, stamp=NOW + timedelta(minutes=index))
        for index in range(2)
    ]
    original_rmtree = shutil.rmtree

    def racing_rmtree(path):
        original_rmtree(path)
        raise FileNotFoundError(path)

    monkeypatch.setattr(run_artifacts.shutil, "rmtree", racing_rmtree)

    assert prune_managed_runs(root, keep=1, warn=lambda message: None) == ()
    assert runs[0].exists() is False
    assert runs[1].exists() is True


def test_pruning_does_not_touch_external_output(tmp_path):
    managed_root = tmp_path / "managed"
    external_output = tmp_path / "external"
    artifacts = allocate(
        tmp_path,
        managed_root=managed_root,
        output=external_output,
    )
    artifacts.finalize("passed", 0)

    assert prune_managed_runs(managed_root, keep=0) == ()
    assert external_output.is_dir()
