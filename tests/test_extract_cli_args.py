"""Argument-validation tests for ``graphify extract``."""
from __future__ import annotations

import json

import pytest

import graphify.__main__ as mainmod


_VALID_OPTION_FORMS = [
    ["--backend", "openai"],
    ["--backend=openai"],
    ["--model", "test-model"],
    ["--model=test-model"],
    ["--mode", "deep"],
    ["--mode=deep"],
    ["--out", "output"],
    ["--out=output"],
    ["--output", "output"],
    ["--output=output"],
    ["--no-cluster"],
    ["--dedup-llm"],
    ["--no-dedup"],
    ["--code-only"],
    ["--google-workspace"],
    ["--no-gitignore"],
    ["--global"],
    ["--as", "repo"],
    ["--max-workers", "1"],
    ["--max-workers=1"],
    ["--token-budget", "1"],
    ["--token-budget=1"],
    ["--max-concurrency", "1"],
    ["--max-concurrency=1"],
    ["--api-timeout", "1"],
    ["--api-timeout=1"],
    ["--resolution", "1"],
    ["--resolution=1"],
    ["--exclude-hubs", "0"],
    ["--exclude-hubs", "1"],
    ["--exclude-hubs=1"],
    ["--exclude-hubs=100"],
    ["--exclude", "vendor"],
    ["--exclude=vendor"],
    ["--postgres", "postgresql://localhost/db"],
    ["--postgres=postgresql://localhost/db"],
    ["--postgres", ""],
    ["--postgres="],
    ["--cargo"],
    ["--force"],
    ["--allow-partial"],
    ["--timing"],
]


def _invoke_invalid(monkeypatch, tmp_path, args):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "extract", str(tmp_path), *args],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    return exc_info.value.code


@pytest.mark.parametrize("valid_args", _VALID_OPTION_FORMS)
def test_extract_accepts_every_registered_option_form(
    monkeypatch, tmp_path, capsys, valid_args
):
    missing_path = tmp_path / "missing"
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "extract", str(missing_path), *valid_args],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    assert exc_info.value.code == 1
    assert "path not found" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("option", "inline"),
    [
        ("--out", False),
        ("--out", True),
        ("--output", False),
        ("--output", True),
    ],
)
def test_extract_output_options_write_to_requested_directory(
    monkeypatch, tmp_path, option, inline
):
    (tmp_path / "sample.py").write_text("def sample():\n    return 1\n")
    out_dir = tmp_path / "custom-output"
    output_args = [f"{option}={out_dir}"] if inline else [option, str(out_dir)]
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        [
            "graphify",
            "extract",
            str(tmp_path),
            "--code-only",
            "--no-cluster",
            *output_args,
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    assert exc_info.value.code == 0
    assert (out_dir / "graphify-out" / "graph.json").exists()


def test_extract_accepts_spaced_value_starting_with_single_dash(
    monkeypatch, tmp_path
):
    project = tmp_path / "project"
    project.mkdir()
    (project / "sample.py").write_text("def sample():\n    return 1\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        [
            "graphify",
            "extract",
            str(project),
            "--code-only",
            "--no-cluster",
            "--out",
            "-generated",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    assert exc_info.value.code == 0
    assert (tmp_path / "-generated" / "graphify-out" / "graph.json").exists()


@pytest.mark.parametrize(
    "option",
    [
        "--backend",
        "--model",
        "--mode",
        "--out",
        "--output",
        "--as",
        "--max-workers",
        "--token-budget",
        "--max-concurrency",
        "--api-timeout",
        "--resolution",
        "--exclude-hubs",
        "--exclude",
        "--postgres",
    ],
)
def test_extract_value_options_require_a_value(
    monkeypatch, tmp_path, capsys, option
):
    assert _invoke_invalid(monkeypatch, tmp_path, [option]) == 2
    assert f"{option} requires a value" in capsys.readouterr().err
    assert not (tmp_path / "graphify-out").exists()


@pytest.mark.parametrize(
    "option",
    [
        "--backend=",
        "--model=",
        "--mode=",
        "--out=",
        "--output=",
        "--max-workers=",
        "--token-budget=",
        "--max-concurrency=",
        "--api-timeout=",
        "--resolution=",
        "--exclude-hubs=",
        "--exclude=",
    ],
)
def test_extract_inline_value_options_reject_empty_values(
    monkeypatch, tmp_path, capsys, option
):
    assert _invoke_invalid(monkeypatch, tmp_path, [option]) == 2
    assert f"{option[:-1]} requires a value" in capsys.readouterr().err
    assert not (tmp_path / "graphify-out").exists()


@pytest.mark.parametrize(
    "option",
    [
        "--backend",
        "--model",
        "--mode",
        "--out",
        "--output",
        "--as",
        "--max-workers",
        "--token-budget",
        "--max-concurrency",
        "--api-timeout",
        "--resolution",
        "--exclude-hubs",
        "--exclude",
    ],
)
def test_extract_value_options_reject_empty_separate_values(
    monkeypatch, tmp_path, capsys, option
):
    assert _invoke_invalid(monkeypatch, tmp_path, [option, ""]) == 2
    assert f"{option} requires a value" in capsys.readouterr().err
    assert not (tmp_path / "graphify-out").exists()


@pytest.mark.parametrize(
    ("invalid_args", "message"),
    [
        (["--definitely-unknown"], "unknown extract option: --definitely-unknown"),
        (["--unknown=value"], "unknown extract option: --unknown"),
        (["extra-path"], "unexpected extract positional argument"),
    ],
)
def test_extract_rejects_unknown_options_and_extra_arguments(
    monkeypatch, tmp_path, capsys, invalid_args, message
):
    assert _invoke_invalid(monkeypatch, tmp_path, invalid_args) == 2
    assert message in capsys.readouterr().err
    assert not (tmp_path / "graphify-out").exists()


def test_extract_unknown_inline_option_does_not_echo_its_value(
    monkeypatch, tmp_path, capsys
):
    sensitive_value = "do-not-log-this-value"

    assert (
        _invoke_invalid(
            monkeypatch,
            tmp_path,
            [f"--postgress={sensitive_value}"],
        )
        == 2
    )

    error = capsys.readouterr().err
    assert "unknown extract option: --postgress" in error
    assert sensitive_value not in error


@pytest.mark.parametrize(
    ("invalid_args", "message"),
    [
        (["--code-only=true"], "--code-only does not take a value"),
        (["--no-dedup=true"], "--no-dedup does not take a value"),
        (["--as=repo"], "--as does not support = syntax"),
    ],
)
def test_extract_rejects_unsupported_assignment_forms(
    monkeypatch, tmp_path, capsys, invalid_args, message
):
    assert _invoke_invalid(monkeypatch, tmp_path, invalid_args) == 2
    assert message in capsys.readouterr().err


@pytest.mark.parametrize(
    ("invalid_args", "message"),
    [
        (["--definitely-unknown"], "unknown extract option: --definitely-unknown"),
        (["--out"], "--out requires a value"),
    ],
)
def test_extract_validates_syntax_before_path_existence(
    monkeypatch, tmp_path, capsys, invalid_args, message
):
    missing_path = tmp_path / "missing"
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "extract", str(missing_path), *invalid_args],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    error = capsys.readouterr().err
    assert exc_info.value.code == 2
    assert message in error
    assert "path not found" not in error


@pytest.mark.parametrize(
    "invalid_args",
    [
        ["--exclude-hubs", "do-not-log-this-value"],
        ["--exclude-hubs=do-not-log-this-value"],
        ["--exclude-hubs=nan"],
        ["--exclude-hubs", "inf"],
        ["--exclude-hubs=-1"],
        ["--exclude-hubs", "101"],
    ],
)
def test_extract_rejects_invalid_exclude_hubs_before_path_check_without_echoing_value(
    monkeypatch, tmp_path, capsys, invalid_args
):
    missing_path = tmp_path / "missing"
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "extract", str(missing_path), *invalid_args],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    error = capsys.readouterr().err
    assert exc_info.value.code == 2
    assert "--exclude-hubs must be between 0 and 100" in error
    assert invalid_args[-1].split("=", 1)[-1] not in error
    assert "Traceback" not in error
    assert "path not found" not in error


def test_extract_repeated_scalar_and_boolean_options_preserve_parser_semantics(
    monkeypatch, tmp_path
):
    project = tmp_path / "project"
    project.mkdir()
    (project / "sample.py").write_text("def sample():\n    return 1\n")
    first_out = tmp_path / "first-output"
    final_out = tmp_path / "final-output"
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        [
            "graphify",
            "extract",
            str(project),
            "--code-only",
            "--code-only",
            "--no-cluster",
            "--no-cluster",
            "--out",
            str(first_out),
            f"--output={final_out}",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    assert exc_info.value.code == 0
    assert not first_out.exists()
    assert (final_out / "graphify-out" / "graph.json").exists()


def test_extract_repeated_exclude_options_preserve_append_semantics(
    monkeypatch, tmp_path
):
    project = tmp_path / "project"
    project.mkdir()
    (project / "sample.py").write_text("def sample():\n    return 1\n")
    out_dir = tmp_path / "output"
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        [
            "graphify",
            "extract",
            str(project),
            "--code-only",
            "--no-cluster",
            "--exclude",
            "vendor",
            "--exclude=generated",
            "--out",
            str(out_dir),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    config_path = out_dir / "graphify-out" / ".graphify_build.json"
    assert exc_info.value.code == 0
    assert json.loads(config_path.read_text()) == {
        "excludes": ["vendor", "generated"]
    }


def test_extract_missing_value_does_not_consume_the_next_option(
    monkeypatch, tmp_path, capsys
):
    assert _invoke_invalid(monkeypatch, tmp_path, ["--out", "--code-only"]) == 2
    assert "--out requires a value" in capsys.readouterr().err
    assert not (tmp_path / "graphify-out").exists()
