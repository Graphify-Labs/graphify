from __future__ import annotations

from collections.abc import Generator

from _pytest._io.saferepr import saferepr
from _pytest.config import Config
from _pytest.config import ExitCode
from _pytest.config.argparsing import Parser
from _pytest.fixtures import FixtureDef
from _pytest.fixtures import SubRequest
from _pytest.scope import Scope
import pytest


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("debugconfig")
    group.addoption(
        "--setuponly",
        "--setup-only",
        action="store_true",
        help="Only setup fixtures, do not execute tests",
    )
    group.addoption(
        "--setupshow",
        "--setup-show",
        action="store_true",
        help="Show setup of fixtures while executing tests",
    )


@pytest.hookimpl(wrapper=True)
def pytest_fixture_setup(
    fixturedef: FixtureDef[object], request: SubRequest
) -> Generator[None, object, object]:
    try:
        return (yield)
    finally:
        if request.config.option.setupshow:
            if hasattr(request, "param"):
                # Save the fixture parameter so ._show_fixture_action() can
                # display it now and during the teardown (in .finish()).
                if fixturedef.ids:
                    if callable(fixturedef.ids):
                        param = fixturedef.ids(request.param)
                    else:
                        param = fixturedef.ids[request.param_index]
                else:
                    param = request.param
                fixturedef.cached_param = param  # type: ignore[attr-defined]
            _show_fixture_action(fixturedef, request.config, "SETUP")


def pytest_fixture_post_finalizer(
    fixturedef: FixtureDef[object], request: SubRequest
) -> None:
    if fixturedef.cached_result is not None:
        config = request.config
        if config.option.setupshow:
            _show_fixture_action(fixturedef, request.config, "TEARDOWN")
            if hasattr(fixturedef, "cached_param"):
                del fixturedef.cached_param


def _show_fixture_action(
    fixturedef: FixtureDef[object], config: Config, msg: str
) -> None:
    capman = config.pluginmanager.getplugin("capturemanager")
    if capman:
        capman.suspend_global_capture()

    tw = config.get_terminal_writer()
    tw.line()
    # Use smaller indentation the higher the scope: Session = 0, Package = 1, etc.
    scope_indent = list(reversed(Scope)).index(fixturedef._scope)
    tw.write(" " * 2 * scope_indent)

    scopename = fixturedef.scope[0].upper()
    tw.write(f"{msg:<8} {scopename} {fixturedef.argname}")

    if msg == "SETUP":
        deps = sorted(arg for arg in fixturedef.argnames if arg != "request")
        if deps:
            tw.write(" (fixtures used: {})".format(", ".join(deps)))

    if hasattr(fixturedef, "cached_param"):
        tw.write(f"[{saferepr(fixturedef.cached_param, maxsize=42)}]")

    tw.flush()

    if capman:
        capman.resume_global_capture()


@pytest.hookimpl(tryfirst=True)
def pytest_cmdline_main(config: Config) -> int | ExitCode | None:
    if config.option.setuponly:
        config.option.setupshow = True
    return None
