"""Per-command handlers, incrementally migrated out of cli.dispatch_command.

Dispatch still flows through graphify.cli.dispatch_command, which consults
COMMANDS first and falls through to the remaining if/elif chain for commands
that have not been ported yet. Each handler reads sys.argv and calls sys.exit
exactly as its original branch did, so a move is behavior-preserving. See
MIGRATION.md for how to port another command. Tracks issue #1212.
"""
from __future__ import annotations

from typing import Callable

from graphify.commands.merge_chunks import merge_chunks

COMMANDS: dict[str, Callable[[], None]] = {
    "merge-chunks": merge_chunks,
}
