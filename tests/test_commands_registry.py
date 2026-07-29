"""The command registry must dispatch, and its keys must not collide with the
if/elif branches still living in cli.dispatch_command.

Part of the __main__/cli command split (issue #1212): commands migrate one at
a time into graphify/commands/, and dispatch_command consults COMMANDS before
its remaining if/elif chain. A key that also appears as an `elif cmd == "..."`
branch would mean a half-migrated command whose old body is now dead — this
test fails if that ever happens.
"""
import re
from pathlib import Path

from graphify.commands import COMMANDS

CLI_SOURCE = (Path(__file__).resolve().parent.parent / "graphify" / "cli.py").read_text(encoding="utf-8")
BRANCH_COMMANDS = set(re.findall(r'cmd == "([^"]+)"', CLI_SOURCE))


def test_registry_is_populated_and_callable() -> None:
    assert COMMANDS, "COMMANDS registry is empty"
    for name, handler in COMMANDS.items():
        assert callable(handler), f"handler for {name!r} is not callable"


def test_no_command_is_both_registered_and_branched() -> None:
    overlap = sorted(set(COMMANDS) & BRANCH_COMMANDS)
    assert overlap == [], (
        f"these commands are in COMMANDS but still have an if/elif branch in "
        f"cli.dispatch_command (dead branch): {overlap}"
    )
