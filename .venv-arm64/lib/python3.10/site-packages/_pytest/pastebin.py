# mypy: allow-untyped-defs
"""Submit failure or test session information to a pastebin service."""

from __future__ import annotations

from io import StringIO
import tempfile
from typing import IO

from _pytest.config import Config
from _pytest.config import create_terminal_writer
from _pytest.config.argparsing import Parser
from _pytest.deprecated import PASTEBIN
from _pytest.stash import StashKey
from _pytest.terminal import TerminalReporter
import pytest


pastebinfile_key = StashKey[IO[bytes]]()


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("terminal reporting")
    group.addoption(
        "--pastebin",
        metavar="mode",
        action="store",
        dest="pastebin",
        default=None,
        choices=["failed", "all"],
        help="Send failed|all info to bpaste.net pastebin service",
    )


@pytest.hookimpl(trylast=True)
def pytest_configure(config: Config) -> None:
    if config.option.pastebin:
        config.issue_config_time_warning(PASTEBIN, 2)

    if config.option.pastebin == "all":
        tr = config.pluginmanager.getplugin("terminalreporter")
        # If no terminal reporter plugin is present, nothing we can do here;
        # this can happen when this function executes in a worker node
        # when using pytest-xdist, for example.
        if tr is not None:
            # pastebin file will be UTF-8 encoded binary file.
            config.stash[pastebinfile_key] = tempfile.TemporaryFile("w+b")
            oldwrite = tr._tw.write

            def tee_write(s, **kwargs):
                oldwrite(s, **kwargs)
                if isinstance(s, str):
                    s = s.encode("utf-8")
                config.stash[pastebinfile_key].write(s)

            tr._tw.write = tee_write


def pytest_unconfigure(config: Config) -> None:
    if pastebinfile_key in config.stash:
        pastebinfile = config.stash[pastebinfile_key]
        # Get terminal contents and delete file.
        pastebinfile.seek(0)
        sessionlog = pastebinfile.read()
        pastebinfile.close()
        del config.stash[pastebinfile_key]
        # Undo our patching in the terminal reporter.
        tr = config.pluginmanager.getplugin("terminalreporter")
        del tr._tw.__dict__["write"]
        # Write summary.
        tr.write_sep("=", "Sending information to Paste Service")
        pastebinurl = create_new_paste(sessionlog)
        tr.write_line(f"pastebin session-log: {pastebinurl}\n")


def create_new_paste(contents: str | bytes) -> str:
    """Create a new paste using the bpaste.net service.

    :contents: Paste contents string.
    :returns: URL to the pasted contents, or an error message.
    """
    import re
    from urllib.error import HTTPError
    from urllib.parse import urlencode
    from urllib.request import urlopen

    params = {"code": contents, "lexer": "text", "expiry": "1week"}
    url = "https://bpa.st"
    try:
        response: str = (
            urlopen(url, data=urlencode(params).encode("ascii")).read().decode("utf-8")
        )
    except HTTPError as e:
        with e:  # HTTPErrors are also http responses that must be closed!
            return f"bad response: {e}"
    except OSError as e:  # eg urllib.error.URLError
        return f"bad response: {e}"
    m = re.search(r'href="/raw/(\w+)"', response)
    if m:
        return f"{url}/show/{m.group(1)}"
    else:
        return "bad response: invalid format ('" + response + "')"


def pytest_terminal_summary(terminalreporter: TerminalReporter) -> None:
    if terminalreporter.config.option.pastebin != "failed":
        return
    if "failed" in terminalreporter.stats:
        terminalreporter.write_sep("=", "Sending information to Paste Service")
        for rep in terminalreporter.stats["failed"]:
            try:
                msg = rep.longrepr.reprtraceback.reprentries[-1].reprfileloc
            except AttributeError:
                msg = terminalreporter._getfailureheadline(rep)
            file = StringIO()
            tw = create_terminal_writer(terminalreporter.config, file)
            rep.toterminal(tw)
            s = file.getvalue()
            assert len(s)
            pastebinurl = create_new_paste(s)
            terminalreporter.write_line(f"{msg} --> {pastebinurl}")
