"""`graphify --help` must list user-facing commands that dispatch_command implements.

#3140: the top-level listing in graphify/__main__.py is hand-maintained and
drifted from dispatch_command() — prs, provider, and 7 of 8 export formats
never appeared. Precedent: #2071 / PR #2075 (one usage line + stdout assert).
"""
from __future__ import annotations

import subprocess
import sys

PYTHON = sys.executable


def test_help_lists_prs_provider_and_export_formats():
    """#3140: `graphify --help` must advertise prs, provider, and all export formats."""
    r = subprocess.run(
        [PYTHON, "-m", "graphify", "--help"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"--help should exit 0: {r.stderr}"
    out = r.stdout
    assert "  prs" in out, "`graphify --help` must list prs (#3140)"
    assert "provider" in out, "`graphify --help` must list provider (#3140)"
    for fmt in (
        "html",
        "callflow-html",
        "obsidian",
        "wiki",
        "svg",
        "graphml",
        "neo4j",
        "falkordb",
    ):
        assert f"export {fmt}" in out, (
            f"`graphify --help` must list export {fmt} (#3140)"
        )
    # Silent hook internals — deliberately excluded from user-facing help.
    assert "hook-check" not in out
    assert "hook-guard" not in out
