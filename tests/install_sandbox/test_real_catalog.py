from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from time import perf_counter
from typing import Callable

from tools.install_sandbox.specs import load_catalog


REPOSITORY = Path(__file__).resolve().parents[2]
SPEC_DIRECTORY = REPOSITORY / "tools" / "install_sandbox" / "specs"
SEPARATELY_EXPOSED_INSTALL_TARGETS = {"vscode"}


def _published_install_targets(help_text: str) -> set[str]:
    prefix = "Platforms:"
    platforms_line = next(
        (line for line in help_text.splitlines() if line.startswith(prefix)),
        None,
    )
    assert platforms_line is not None, (
        "graphify install --help did not publish a Platforms line"
    )
    return {
        name.strip()
        for name in platforms_line.removeprefix(prefix).split(",")
        if name.strip()
    }


def test_checked_in_catalog_matches_current_checkout_install_help(
    record_property: Callable[[str, object], None],
) -> None:
    started = perf_counter()
    catalog = load_catalog(SPEC_DIRECTORY)
    help_result = subprocess.run(
        [sys.executable, "-m", "graphify", "install", "--help"],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    )
    elapsed = perf_counter() - started
    record_property("real_catalog_contract_seconds", elapsed)

    spec_targets = set(catalog)
    published_targets = (
        _published_install_targets(help_result.stdout)
        | SEPARATELY_EXPOSED_INSTALL_TARGETS
    )
    missing_specs = sorted(published_targets - spec_targets)
    stale_specs = sorted(spec_targets - published_targets)

    diagnostics = []
    if missing_specs:
        diagnostics.append(
            "missing specs for published install targets: "
            + ", ".join(missing_specs)
        )
    if stale_specs:
        diagnostics.append(
            "stale specs without published install targets: "
            + ", ".join(stale_specs)
        )
    assert not diagnostics, "\n".join(diagnostics)
