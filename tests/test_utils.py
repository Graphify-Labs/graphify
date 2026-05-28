"""Shared test utilities and markers."""

import os

import pytest


def skip_in_sandbox():
    """Skip tests that need access to external resources (git, network) in a sandbox."""
    sandbox_variables = ["NIX_ENFORCE_PURITY"]
    return pytest.mark.skipif(
        any(var in os.environ for var in sandbox_variables),
        reason="Sandboxed environment with limited external access"
    )
