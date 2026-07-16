# A plugin to register the TerminalProgressPlugin plugin.
#
# This plugin is not loaded by default due to compatibility issues (#13896),
# but can be enabled in one of these ways:
# - The terminal plugin enables it in a few cases where it's safe, and not
#   blocked by the user (using e.g. `-p no:terminalprogress`).
# - The user explicitly requests it, e.g. using `-p terminalprogress`.
#
# In a few years, if it's safe, we can consider enabling it by default. Then,
# this file will become unnecessary and can be inlined into terminal.py.

from __future__ import annotations

import os

from _pytest.config import Config
from _pytest.config import hookimpl
from _pytest.terminal import TerminalProgressPlugin
from _pytest.terminal import TerminalReporter


@hookimpl(trylast=True)
def pytest_configure(config: Config) -> None:
    reporter: TerminalReporter | None = config.pluginmanager.get_plugin(
        "terminalreporter"
    )

    if reporter is not None and reporter.isatty() and os.environ.get("TERM") != "dumb":
        plugin = TerminalProgressPlugin(reporter)
        config.pluginmanager.register(plugin, name="terminalprogress-plugin")
