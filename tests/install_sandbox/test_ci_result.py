import json

import pytest

from tools.install_sandbox.ci_result import classify_ci_result, main


@pytest.mark.parametrize(
    ("state", "runner_exit_code", "annotation"),
    [
        ("passed", 0, "notice"),
        ("failed", 1, "warning"),
    ],
)
def test_completed_diagnostics_are_successful_ci_results(
    state,
    runner_exit_code,
    annotation,
):
    result = classify_ci_result(
        {"state": state, "exit_code": runner_exit_code},
        runner_exit_code,
    )

    assert result.annotation == annotation
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("state", "runner_exit_code"),
    [
        ("incomplete", 2),
        ("incomplete", 127),
        ("interrupted", 143),
    ],
)
def test_noncompleted_diagnostics_fail_ci(state, runner_exit_code):
    result = classify_ci_result(
        {"state": state, "exit_code": runner_exit_code},
        runner_exit_code,
    )

    assert result.annotation == "error"
    assert result.exit_code == runner_exit_code


@pytest.mark.parametrize(
    ("metadata", "runner_exit_code", "message"),
    [
        ({"state": "passed", "exit_code": 1}, 1, "passed state"),
        ({"state": "failed", "exit_code": 2}, 2, "failed state"),
        ({"state": "incomplete", "exit_code": 0}, 0, "nonzero exit code"),
        ({"state": "running", "exit_code": 0}, 0, "unknown terminal state"),
        ({"state": "passed", "exit_code": 0}, 1, "does not match"),
        ({"state": "passed", "exit_code": None}, 0, "not an integer"),
    ],
)
def test_invalid_result_contract_fails_ci(metadata, runner_exit_code, message):
    result = classify_ci_result(metadata, runner_exit_code)

    assert result.annotation == "error"
    assert result.exit_code == 2
    assert message in result.message


def test_cli_emits_warning_for_completed_behavioral_findings(tmp_path, capsys):
    run_json = tmp_path / "run.json"
    run_json.write_text(
        json.dumps({"state": "failed", "exit_code": 1}),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--run-json",
            str(run_json),
            "--runner-exit-code",
            "1",
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out.startswith("::warning::")


def test_cli_fails_when_run_metadata_is_missing(tmp_path, capsys):
    run_json = tmp_path / "missing-run.json"

    exit_code = main(
        [
            "--run-json",
            str(run_json),
            "--runner-exit-code",
            "2",
        ]
    )

    assert exit_code == 2
    output = capsys.readouterr().out
    assert output.startswith("::error::")
    assert "cannot read" in output


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("{", "cannot read"),
        ("[]", "root is not an object"),
    ],
)
def test_cli_fails_for_unusable_run_metadata(tmp_path, capsys, contents, message):
    run_json = tmp_path / "run.json"
    run_json.write_text(contents, encoding="utf-8")

    exit_code = main(
        [
            "--run-json",
            str(run_json),
            "--runner-exit-code",
            "1",
        ]
    )

    assert exit_code == 2
    output = capsys.readouterr().out
    assert output.startswith("::error::")
    assert message in output
