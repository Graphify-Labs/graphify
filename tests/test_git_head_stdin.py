"""_git_head must not hand git the caller's stdin (#4440).

Under an MCP stdio host, stdin is the protocol pipe. On Windows a git child that
inherits it blocks, so `graph_stats` stalls on the timeout or hangs. Same class
as the prs.py isolation in #3318.
"""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from graphify import export, watch


@pytest.mark.parametrize("module", [export, watch], ids=["export", "watch"])
def test_git_head_passes_devnull_stdin(module, tmp_path):
    completed = MagicMock(returncode=0, stdout="abc123\n", stderr="")
    with patch("subprocess.run", return_value=completed) as mock_run:
        assert module._git_head(tmp_path) == "abc123"
    _args, kwargs = mock_run.call_args
    assert kwargs.get("stdin") == subprocess.DEVNULL
