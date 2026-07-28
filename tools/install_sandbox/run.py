"""Run Graphify installer lifecycle contracts inside isolated Docker roots."""

from __future__ import annotations

import argparse
import os
import signal
import sys
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.install_sandbox.docker import run_sandbox
from tools.install_sandbox.run_artifacts import (
    MANAGED_ROOT,
    ArtifactError,
    RunArtifacts,
    prune_managed_runs,
)
from tools.install_sandbox.specs import SpecError, catalog_names, load_catalog


HARNESS_SPEC_DIR = Path(__file__).resolve().parent / "specs"


class RunInterrupted(Exception):
    """Raised when the host catches a signal while a run is active."""

    def __init__(self, signum: int) -> None:
        self.signum = signum
        super().__init__(f"caught signal {signum}")


def parser(target_names: Iterable[str]) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repo", required=True, type=Path)
    selection = result.add_mutually_exclusive_group(required=True)
    selection.add_argument("--target", choices=tuple(target_names))
    selection.add_argument("--all", action="store_true", dest="all_targets")
    result.add_argument(
        "--scope",
        choices=("user", "project", "both"),
        default="both",
    )
    result.add_argument("--output", type=Path)
    return result


@contextmanager
def _caught_run_signals() -> Generator[None, None, None]:
    watched = (signal.SIGINT, signal.SIGTERM)
    previous = {signum: signal.getsignal(signum) for signum in watched}

    def interrupt(signum, _frame) -> None:
        raise RunInterrupted(signum)

    try:
        for signum in watched:
            signal.signal(signum, interrupt)
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def classify_result(exit_code: int, *, complete: bool) -> tuple[str, int]:
    """Classify the raw runner result without hiding nonzero exit codes."""

    if complete and exit_code == 0:
        return "passed", exit_code
    if complete and exit_code == 1:
        return "failed", exit_code
    return "incomplete", exit_code or 2


def _finish(artifacts: RunArtifacts, state: str, exit_code: int) -> int:
    stream = "stderr" if exit_code else "stdout"
    artifacts.logger.write(
        stream,
        f"run finished: state={state} exit_code={exit_code}\n",
    )
    artifacts.finalize(state, exit_code)
    if artifacts.managed:
        prune_managed_runs(MANAGED_ROOT, keep=5)
    return exit_code


def _forward_output(
    artifacts: RunArtifacts,
    phase: str,
    stream: str,
    text: str,
) -> None:
    if artifacts.metadata["phase"] != phase:
        artifacts.set_phase(phase)
    artifacts.logger.write(stream, text)


def main(
    argv: list[str] | None = None,
    *,
    spec_dir: Path = HARNESS_SPEC_DIR,
) -> int:
    args = parser(catalog_names(spec_dir)).parse_args(argv)
    repo = args.repo.expanduser().resolve()
    if not (repo / "pyproject.toml").is_file() or not (repo / "graphify").is_dir():
        print(f"error: not a Graphify source checkout: {repo}", file=sys.stderr)
        return 2

    if args.output is None:
        prune_managed_runs(MANAGED_ROOT, keep=5)
    try:
        artifacts = RunArtifacts.allocate(
            repo=repo,
            target=args.target,
            all_targets=args.all_targets,
            scope=args.scope,
            output=args.output,
        )
    except (ArtifactError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    artifacts.logger.write("stdout", f"artifacts: {artifacts.output}\n")
    try:
        with _caught_run_signals():
            artifacts.logger.write(
                "stdout",
                f"loading strict catalog from {spec_dir.resolve()}\n",
            )
            catalog = load_catalog(spec_dir)
            artifacts.logger.write(
                "stdout",
                f"catalog preflight passed: {len(catalog)} targets\n",
            )
            runtime = os.environ.get("GRAPHIFY_SANDBOX_RUNTIME", "docker")
            exit_code = run_sandbox(
                repo=repo,
                output=artifacts.output,
                target=args.target,
                all_targets=args.all_targets,
                scope=args.scope,
                runtime=runtime,
                on_phase=artifacts.set_phase,
                on_output=lambda phase, stream, text: _forward_output(
                    artifacts,
                    phase,
                    stream,
                    text,
                ),
            )
    except SpecError as exc:
        artifacts.logger.write("stderr", f"catalog preflight failed: {exc}\n")
        return _finish(artifacts, "incomplete", 2)
    except RunInterrupted as exc:
        exit_code = 128 + exc.signum
        artifacts.logger.write(
            "stderr",
            f"run interrupted by signal {exc.signum}\n",
        )
        return _finish(artifacts, "interrupted", exit_code)
    except Exception as exc:
        artifacts.logger.write(
            "stderr",
            f"host runner failed: {type(exc).__name__}: {exc}\n",
        )
        return _finish(artifacts, "incomplete", 2)

    state, final_exit_code = classify_result(
        exit_code,
        complete=artifacts.complete_outputs(),
    )
    return _finish(artifacts, state, final_exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
