import json
import signal
from pathlib import Path

import pytest

from tools.install_sandbox import run as run_module
from tools.install_sandbox.models import PhaseResult, ScenarioResult
from tools.install_sandbox.reporting import (
    build_manifest,
    render_report,
    write_run_outputs,
)
from tools.install_sandbox.run import RunInterrupted, classify_result, main, parser


def _graphify_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "graphify").mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    return repo


def _valid_spec_dir(tmp_path: Path) -> Path:
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir()
    (spec_dir / "demo.yaml").write_text(
        """
scopes: {}
unsupported:
  user: User scope is unavailable in this fixture.
  project: Project scope is unavailable in this fixture.
""".lstrip(),
        encoding="utf-8",
    )
    return spec_dir


def test_public_cli_has_exact_selection_and_scope_defaults(tmp_path):
    args = parser(("demo", "generic")).parse_args(
        ["--repo", str(tmp_path), "--target", "demo"]
    )

    assert args.target == "demo"
    assert args.all_targets is False
    assert args.scope == "both"
    assert args.output is None


def test_cli_rejects_non_graphify_repo_before_docker(tmp_path, capsys):
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir()

    assert main(
        ["--repo", str(tmp_path), "--all"],
        spec_dir=spec_dir,
    ) == 2
    assert "not a Graphify source checkout" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("raw_exit", "write_outputs", "expected_state", "expected_exit"),
    [
        (0, True, "passed", 0),
        (1, True, "failed", 1),
        (127, False, "incomplete", 127),
        (0, False, "incomplete", 2),
    ],
)
def test_host_runner_classifies_complete_and_incomplete_results(
    tmp_path,
    monkeypatch,
    raw_exit,
    write_outputs,
    expected_state,
    expected_exit,
):
    repo = _graphify_repo(tmp_path)
    spec_dir = _valid_spec_dir(tmp_path)
    output = tmp_path / "output"

    def fake_run_sandbox(**arguments):
        arguments["on_phase"]("docker_build")
        arguments["on_output"](
            "docker_build",
            "stdout",
            "synthetic build output\n",
        )
        arguments["on_phase"]("container")
        if write_outputs:
            (arguments["output"] / "manifest.json").write_text(
                "{}\n",
                encoding="utf-8",
            )
            (arguments["output"] / "report.md").write_text(
                "# report\n",
                encoding="utf-8",
            )
        return raw_exit

    monkeypatch.setattr(run_module, "run_sandbox", fake_run_sandbox)

    exit_code = main(
        ["--repo", str(repo), "--all", "--output", str(output)],
        spec_dir=spec_dir,
    )

    metadata = json.loads((output / "run.json").read_text(encoding="utf-8"))
    assert exit_code == expected_exit
    assert metadata["state"] == expected_state
    assert metadata["exit_code"] == expected_exit
    assert metadata["phase"] == "container"
    assert "[docker_build] [stdout] synthetic build output" in (
        output / "runner.log"
    ).read_text(encoding="utf-8")


def test_catalog_failure_has_host_diagnostics_before_docker(tmp_path, monkeypatch):
    repo = _graphify_repo(tmp_path)
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir()
    (spec_dir / "broken.yaml").write_text("unknown: true\n", encoding="utf-8")
    output = tmp_path / "output"
    called = False

    def fake_run_sandbox(**_arguments):
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(run_module, "run_sandbox", fake_run_sandbox)

    exit_code = main(
        ["--repo", str(repo), "--all", "--output", str(output)],
        spec_dir=spec_dir,
    )

    metadata = json.loads((output / "run.json").read_text(encoding="utf-8"))
    assert exit_code == 2
    assert called is False
    assert metadata["state"] == "incomplete"
    assert "catalog preflight failed" in (output / "runner.log").read_text(
        encoding="utf-8"
    )


def test_caught_signal_uses_conventional_exit_code_and_interrupted_state(
    tmp_path,
    monkeypatch,
):
    repo = _graphify_repo(tmp_path)
    spec_dir = _valid_spec_dir(tmp_path)
    output = tmp_path / "output"

    def interrupt_run(**_arguments):
        raise RunInterrupted(signal.SIGTERM)

    monkeypatch.setattr(run_module, "run_sandbox", interrupt_run)

    exit_code = main(
        ["--repo", str(repo), "--all", "--output", str(output)],
        spec_dir=spec_dir,
    )

    metadata = json.loads((output / "run.json").read_text(encoding="utf-8"))
    assert exit_code == 143
    assert metadata["state"] == "interrupted"
    assert metadata["exit_code"] == 143


def test_result_classification_preserves_raw_nonzero_codes():
    assert classify_result(0, complete=True) == ("passed", 0)
    assert classify_result(1, complete=True) == ("failed", 1)
    assert classify_result(124, complete=False) == ("incomplete", 124)
    assert classify_result(0, complete=False) == ("incomplete", 2)


def test_reporting_is_concise_and_writes_only_top_level_contract_files(tmp_path):
    result = ScenarioResult(
        scenario="demo-project",
        target="demo",
        scope="project",
        status="PASS",
        phases=[
            PhaseResult(name="install", status="PASS"),
            PhaseResult(name="uninstall", status="PASS"),
        ],
        artifact_dir="scenarios/demo-project",
    )
    manifest = build_manifest(
        repo=Path("/repo"),
        selection={"target": "demo", "all": False, "scope": "project"},
        package={"version": "graphify 1.0"},
        results=[result],
        purge={"status": "PASS"},
    )

    report = render_report(manifest)
    write_run_outputs(tmp_path, manifest)

    assert "demo-project" in report
    assert "PASS=1" in report
    assert len(report.splitlines()) < 20
    assert {item.name for item in tmp_path.iterdir()} == {
        "manifest.json",
        "report.md",
    }
