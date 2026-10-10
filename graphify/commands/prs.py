"""`graphify prs`."""
from __future__ import annotations

import sys


def prs() -> None:
    """`graphify prs` (moved verbatim from dispatch_command)."""
    from graphify.prs import cmd_prs
    cmd_prs(sys.argv[2:])
