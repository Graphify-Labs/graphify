"""graphify.commands registry: the seam for splitting dispatch_command (#2474)."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from graphify import cli
from graphify.commands.registry import COMMANDS, lookup


def _inline_commands() -> set[str]:
    """Command names still dispatched by an `if cmd == "..."` branch."""
    tree = ast.parse(Path(cli.__file__).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "dispatch_command")
    names: set[str] = set()
    for node in ast.walk(fn):
        if (isinstance(node, ast.Compare) and isinstance(node.left, ast.Name)
                and node.left.id == "cmd"):
            for comp in node.comparators:
                for const in ast.walk(comp):
                    if isinstance(const, ast.Constant) and isinstance(const.value, str):
                        names.add(const.value)
    return names


def test_a_migrated_command_has_no_inline_branch_left():
    """A command in the table whose old branch survived would leave dead code
    that silently drifts from the handler that actually runs."""
    assert not set(COMMANDS) & _inline_commands()


@pytest.mark.parametrize("name", sorted(COMMANDS))
def test_every_registered_command_resolves_to_a_handler(name):
    handler = lookup(name)
    assert callable(handler), f"{name} -> {COMMANDS[name]} is not importable"


def test_unregistered_command_is_left_to_the_inline_chain():
    assert lookup("extract") is None


def test_dispatch_runs_the_registered_handler(monkeypatch, capsys):
    """`hook` with no subcommand prints its usage and exits 1, as the old branch did."""
    monkeypatch.setattr(sys, "argv", ["graphify", "hook"])
    with pytest.raises(SystemExit) as exc:
        cli.dispatch_command("hook")
    assert exc.value.code == 1
    assert "Usage: graphify hook" in capsys.readouterr().err
