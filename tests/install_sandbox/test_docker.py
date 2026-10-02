import sys
from pathlib import Path

import pytest

from tools.install_sandbox import docker
from tools.install_sandbox.docker import (
    CONTAINER_HOME,
    CONTAINER_OUTPUT,
    CONTAINER_PROJECT,
    CONTAINER_REPO,
    CONTAINER_SOURCE,
    CONTAINER_USER_CWD,
    CONTAINER_XDG,
    build_image_command,
    build_run_command,
)
from tools.install_sandbox import sandbox_runner
from tools.install_sandbox.models import SandboxRoots, ScenarioResult


def test_docker_commands_mount_source_read_only_and_isolate_every_root(tmp_path):
    repo = tmp_path / "repo"
    output = tmp_path / "output"
    command = build_run_command(
        runtime="docker",
        image="sandbox:test",
        repo=repo,
        output=output,
        target="demo",
        all_targets=False,
        scope="project",
    )

    assert build_image_command("docker", "sandbox:test")[:4] == [
        "docker",
        "build",
        "--tag",
        "sandbox:test",
    ]
    assert f"{repo}:{CONTAINER_REPO}:ro" in command
    assert f"{output}:{CONTAINER_OUTPUT}:rw" in command
    for path in {
        CONTAINER_HOME,
        CONTAINER_XDG,
        CONTAINER_PROJECT,
        CONTAINER_USER_CWD,
        CONTAINER_SOURCE,
        CONTAINER_REPO,
        CONTAINER_OUTPUT,
    }:
        assert path in " ".join(command)
    assert len(
        {
            CONTAINER_HOME,
            CONTAINER_XDG,
            CONTAINER_PROJECT,
            CONTAINER_USER_CWD,
            CONTAINER_SOURCE,
            CONTAINER_REPO,
            CONTAINER_OUTPUT,
        }
    ) == 7
    assert command[-4:] == ["--scope", "project", "--target", "demo"]


def test_docker_command_requires_exactly_one_selection(tmp_path):
    with pytest.raises(ValueError, match="exactly one"):
        build_run_command(
            runtime="docker",
            image="image",
            repo=tmp_path / "repo",
            output=tmp_path / "out",
            target=None,
            all_targets=False,
            scope="both",
        )


def test_host_command_output_is_streamed_with_phase_and_stream_labels():
    observed = []

    exit_code = docker._run(
        [
            sys.executable,
            "-c",
            "import sys; print('from stdout'); print('from stderr', file=sys.stderr)",
        ],
        10,
        phase="example",
        on_output=lambda phase, stream, text: observed.append(
            (phase, stream, text)
        ),
    )

    assert exit_code == 0
    assert observed[0][0:2] == ("example", "command")
    assert ("example", "stdout", "from stdout\n") in observed
    assert ("example", "stderr", "from stderr\n") in observed


def test_run_sandbox_announces_build_and_container_phases(tmp_path, monkeypatch):
    phases = []
    commands = []

    def fake_run(argv, timeout, *, phase, on_output):
        commands.append((argv, timeout, phase, on_output))
        return 0

    monkeypatch.setattr(docker, "_run", fake_run)

    exit_code = docker.run_sandbox(
        repo=tmp_path / "repo",
        output=tmp_path / "output",
        target="demo",
        all_targets=False,
        scope="project",
        on_phase=phases.append,
    )

    assert exit_code == 0
    assert phases == ["docker_build", "container"]
    assert [item[2] for item in commands] == ["docker_build", "container"]


def test_container_oracle_is_packaged_with_harness_not_subject_repo(
    tmp_path,
    monkeypatch,
):
    harness_specs = tmp_path / "harness" / "specs"
    subject_repo = tmp_path / "subject"
    subject_specs = subject_repo / "tools" / "install_sandbox" / "specs"
    harness_specs.mkdir(parents=True)
    subject_specs.mkdir(parents=True)
    body = (
        "unsupported:\n"
        "  project: unavailable\n"
        "scopes:\n"
        "  user:\n"
        "    effects:\n"
        "      - {root: home, path: fixture.txt}\n"
    )
    (harness_specs / "demo.yaml").write_text(
        body,
        encoding="utf-8",
    )
    (subject_specs / "subject-only.yaml").write_text(
        body,
        encoding="utf-8",
    )

    root_paths = {
        name: tmp_path / name
        for name in (
            "home",
            "xdg",
            "project",
            "user_cwd",
            "source",
            "output",
        )
    }
    roots = SandboxRoots(repo_mount=subject_repo, **root_paths)
    observed = {}

    def fake_copy_and_install_package(actual_roots, catalog):
        observed["repo_mount"] = actual_roots.repo_mount
        observed["catalog_names"] = tuple(catalog)
        return {
            "repo_mount_read_only": True,
            "package_version": "1.0",
        }

    def fake_run_scenario(scenario, actual_roots, *, expected_version):
        observed["scenario_target"] = scenario.target.name
        return ScenarioResult(
            scenario=scenario.name,
            target=scenario.target.name,
            scope=scenario.scope.value,
            status="PASS",
            phases=[],
        )

    monkeypatch.setattr(
        sandbox_runner,
        "roots_from_environment",
        lambda: roots,
    )
    monkeypatch.setattr(
        sandbox_runner,
        "copy_and_install_package",
        fake_copy_and_install_package,
    )
    monkeypatch.setattr(sandbox_runner, "run_scenario", fake_run_scenario)
    monkeypatch.setattr(
        sandbox_runner,
        "run_purge_check",
        lambda actual_roots: {"status": "PASS"},
    )
    monkeypatch.setattr(
        sandbox_runner,
        "write_run_outputs",
        lambda output, manifest: None,
    )

    exit_code = sandbox_runner.main(
        ["--target", "demo", "--scope", "user"],
        spec_dir=harness_specs,
    )

    assert exit_code == 0
    assert observed == {
        "repo_mount": subject_repo,
        "catalog_names": ("demo",),
        "scenario_target": "demo",
    }
    assert harness_specs.resolve() != subject_specs.resolve()
