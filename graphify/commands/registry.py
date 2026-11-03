"""Command table for ``graphify.cli.dispatch_command``.

Values are ``"module:function"`` strings and the module is imported only when
its command runs, so ``graphify <cmd>`` loads no more than the old inline
branch did. Handlers take no arguments.
"""
from __future__ import annotations

import importlib
from collections.abc import Callable

COMMANDS: dict[str, str] = {
    "benchmark": "graphify.commands.benchmark:benchmark",
    "check-update": "graphify.commands.watch:check_update",
    "clone": "graphify.commands.clone:clone",
    "hook": "graphify.commands.hooks:hook",
    "hook-check": "graphify.commands.hooks:hook_check",
    "hook-guard": "graphify.commands.hooks:hook_guard",
    "prs": "graphify.commands.prs:prs",
    "watch": "graphify.commands.watch:watch",
}


def lookup(cmd: str) -> Callable[[], None] | None:
    """The handler registered for ``cmd``, or None if it is still dispatched inline."""
    target = COMMANDS.get(cmd)
    if target is None:
        return None
    module, _, func = target.partition(":")
    return getattr(importlib.import_module(module), func)
