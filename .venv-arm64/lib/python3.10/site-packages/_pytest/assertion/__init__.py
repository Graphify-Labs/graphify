# mypy: allow-untyped-defs
"""Support for presenting detailed information in failing assertions."""

from __future__ import annotations

from collections.abc import Generator
import sys
from typing import Any
from typing import Protocol
from typing import TYPE_CHECKING

from _pytest.assertion import rewrite
from _pytest.assertion import truncate
from _pytest.assertion import util
from _pytest.assertion.rewrite import assertstate_key
from _pytest.config import Config
from _pytest.config import hookimpl
from _pytest.config.argparsing import Parser
from _pytest.nodes import Item


if TYPE_CHECKING:
    from _pytest.main import Session


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("debugconfig")
    group.addoption(
        "--assert",
        action="store",
        dest="assertmode",
        choices=("rewrite", "plain"),
        default="rewrite",
        metavar="MODE",
        help=(
            "Control assertion debugging tools.\n"
            "'plain' performs no assertion debugging.\n"
            "'rewrite' (the default) rewrites assert statements in test modules"
            " on import to provide assert expression information."
        ),
    )
    parser.addini(
        "enable_assertion_pass_hook",
        type="bool",
        default=False,
        help="Enables the pytest_assertion_pass hook. "
        "Make sure to delete any previously generated pyc cache files.",
    )

    parser.addini(
        "truncation_limit_lines",
        default=None,
        help="Set threshold of LINES after which truncation will take effect",
    )
    parser.addini(
        "truncation_limit_chars",
        default=None,
        help=("Set threshold of CHARS after which truncation will take effect"),
    )
    parser.addini(
        "assertion_text_diff_style",
        default=util.ASSERTION_TEXT_DIFF_STYLE_NDIFF,
        help=(
            "Choose how pytest renders diffs for string equality assertions: "
            f"{util.ASSERTION_TEXT_DIFF_STYLE_NDIFF} or "
            f"{util.ASSERTION_TEXT_DIFF_STYLE_BLOCK}"
        ),
    )

    Config._add_verbosity_ini(
        parser,
        Config.VERBOSITY_ASSERTIONS,
        help=(
            "Specify a verbosity level for assertions, overriding the main level. "
            "Higher levels will provide more detailed explanation when an assertion fails."
        ),
    )


def pytest_configure(config: Config) -> None:
    util.validate_assertion_text_diff_style(config)


def register_assert_rewrite(*names: str) -> None:
    """Register one or more module names to be rewritten on import.

    This function will make sure that this module or all modules inside
    the package will get their assert statements rewritten.
    Thus you should make sure to call this before the module is
    actually imported, usually in your __init__.py if you are a plugin
    using a package.

    :param names: The module names to register.
    """
    for name in names:
        if not isinstance(name, str):
            msg = "expected module names as *args, got {0} instead"  # type: ignore[unreachable]
            raise TypeError(msg.format(repr(names)))
    rewrite_hook: RewriteHook
    for hook in sys.meta_path:
        if isinstance(hook, rewrite.AssertionRewritingHook):
            rewrite_hook = hook
            break
    else:
        rewrite_hook = DummyRewriteHook()
    rewrite_hook.mark_rewrite(*names)


class RewriteHook(Protocol):
    def mark_rewrite(self, *names: str) -> None: ...


class DummyRewriteHook:
    """A no-op import hook for when rewriting is disabled."""

    def mark_rewrite(self, *names: str) -> None:
        pass


class AssertionState:
    """State for the assertion plugin."""

    def __init__(self, config: Config, mode) -> None:
        self.mode = mode
        self.trace = config.trace.root.get("assertion")
        self.hook: rewrite.AssertionRewritingHook | None = None


def install_importhook(config: Config) -> rewrite.AssertionRewritingHook:
    """Try to install the rewrite hook, raise SystemError if it fails."""
    config.stash[assertstate_key] = AssertionState(config, "rewrite")
    config.stash[assertstate_key].hook = hook = rewrite.AssertionRewritingHook(config)
    sys.meta_path.insert(0, hook)
    config.stash[assertstate_key].trace("installed rewrite import hook")

    def undo() -> None:
        hook = config.stash[assertstate_key].hook
        if hook is not None and hook in sys.meta_path:
            sys.meta_path.remove(hook)

    config.add_cleanup(undo)
    return hook


def pytest_collection(session: Session) -> None:
    # This hook is only called when test modules are collected
    # so for example not in the managing process of pytest-xdist
    # (which does not collect test modules).
    assertstate = session.config.stash.get(assertstate_key, None)
    if assertstate:
        if assertstate.hook is not None:
            assertstate.hook.set_session(session)


@hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_protocol(item: Item) -> Generator[None, object, object]:
    """Setup the pytest_assertrepr_compare and pytest_assertion_pass hooks.

    The rewrite module will use util._reprcompare if it exists to use custom
    reporting via the pytest_assertrepr_compare hook.  This sets up this custom
    comparison for the test.
    """
    ihook = item.ihook

    def callbinrepr(op, left: object, right: object) -> str | None:
        """Call the pytest_assertrepr_compare hook and prepare the result.

        This uses the first result from the hook and then ensures the
        following:
        * Overly verbose explanations are truncated unless configured otherwise
          (eg. if running in verbose mode).
        * Embedded newlines are escaped to help util.format_explanation()
          later.
        * If the rewrite mode is used embedded %-characters are replaced
          to protect later % formatting.

        The result can be formatted by util.format_explanation() for
        pretty printing.
        """
        hook_result = ihook.pytest_assertrepr_compare(
            config=item.config, op=op, left=left, right=right
        )
        for new_expl in hook_result:
            if new_expl:
                new_expl = truncate.truncate_if_required(new_expl, item)
                new_expl = [line.replace("\n", "\\n") for line in new_expl]
                res = "\n~".join(new_expl)
                if item.config.getvalue("assertmode") == "rewrite":
                    res = res.replace("%", "%%")
                return res
        return None

    saved_assert_hooks = util._reprcompare, util._assertion_pass
    util._reprcompare = callbinrepr
    util._config = item.config

    if ihook.pytest_assertion_pass.get_hookimpls():

        def call_assertion_pass_hook(lineno: int, orig: str, expl: str) -> None:
            ihook.pytest_assertion_pass(item=item, lineno=lineno, orig=orig, expl=expl)

        util._assertion_pass = call_assertion_pass_hook

    try:
        return (yield)
    finally:
        util._reprcompare, util._assertion_pass = saved_assert_hooks
        util._config = None


def pytest_sessionfinish(session: Session) -> None:
    assertstate = session.config.stash.get(assertstate_key, None)
    if assertstate:
        if assertstate.hook is not None:
            assertstate.hook.set_session(None)


def pytest_assertrepr_compare(
    config: Config, op: str, left: Any, right: Any
) -> list[str] | None:
    if config.pluginmanager.has_plugin("terminalreporter"):
        highlighter = config.get_terminal_writer()._highlight
    else:
        # Keep it plaintext when not using terminalrepoterer (#14377).
        highlighter = util.dummy_highlighter
    explanation = list(
        util.assertrepr_compare(
            op=op,
            left=left,
            right=right,
            verbose=config.get_verbosity(Config.VERBOSITY_ASSERTIONS),
            highlighter=highlighter,
            assertion_text_diff_style=util.get_assertion_text_diff_style(config),
        )
    )
    return explanation or None
