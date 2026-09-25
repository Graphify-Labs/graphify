"""Translate install-sandbox lifecycle metadata into a GitHub Actions result."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Annotation = Literal["notice", "warning", "error"]


@dataclass(frozen=True)
class CIResult:
    """One GitHub Actions annotation and the step exit code it accompanies."""

    annotation: Annotation
    message: str
    exit_code: int


def _invalid(message: str) -> CIResult:
    return CIResult("error", f"Invalid install-sandbox result: {message}", 2)


def classify_ci_result(
    metadata: Mapping[str, object],
    runner_exit_code: int,
) -> CIResult:
    """Keep completed findings advisory while failing broken diagnostic runs."""

    if not 0 <= runner_exit_code <= 255:
        return _invalid(f"runner exit code is out of range: {runner_exit_code}")

    state = metadata.get("state")
    metadata_exit_code = metadata.get("exit_code")
    if not isinstance(state, str):
        return _invalid("run.json state is not a string")
    if type(metadata_exit_code) is not int:
        return _invalid("run.json exit_code is not an integer")
    if metadata_exit_code != runner_exit_code:
        return _invalid(
            "run.json exit_code "
            f"{metadata_exit_code} does not match runner exit code {runner_exit_code}"
        )

    if state == "passed":
        if runner_exit_code != 0:
            return _invalid("passed state must have exit code 0")
        return CIResult(
            "notice",
            "Install sandbox completed without behavioral findings.",
            0,
        )

    if state == "failed":
        if runner_exit_code != 1:
            return _invalid("failed state must have exit code 1")
        return CIResult(
            "warning",
            "Install sandbox completed with behavioral findings; "
            "see the job summary and uploaded diagnostic bundle.",
            0,
        )

    if state in {"incomplete", "interrupted"}:
        if runner_exit_code == 0:
            return _invalid(f"{state} state must have a nonzero exit code")
        return CIResult(
            "error",
            f"Install sandbox diagnostic {state} with exit code {runner_exit_code}.",
            runner_exit_code,
        )

    return _invalid(f"unknown terminal state: {state!r}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--run-json", required=True, type=Path)
    result.add_argument("--runner-exit-code", required=True, type=int)
    return result


def _load_metadata(path: Path) -> Mapping[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("run.json root is not an object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        metadata = _load_metadata(args.run_json)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        result = _invalid(f"cannot read {args.run_json}: {exc}")
    else:
        result = classify_ci_result(metadata, args.runner_exit_code)

    print(f"::{result.annotation}::{result.message}")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
