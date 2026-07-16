"""Exception classes and constants handling test outcomes as well as
functions creating them."""

from __future__ import annotations

import importlib
import sys
from typing import Any
from typing import ClassVar
from typing import NoReturn


class OutcomeException(BaseException):
    """OutcomeException and its subclass instances indicate and contain info
    about test and collection outcomes."""

    def __init__(self, msg: str | None = None, pytrace: bool = True) -> None:
        if msg is not None and not isinstance(msg, str):
            error_msg = (  # type: ignore[unreachable]
                "{} expected string as 'msg' parameter, got '{}' instead.\n"
                "Perhaps you meant to use a mark?"
            )
            raise TypeError(error_msg.format(type(self).__name__, type(msg).__name__))
        super().__init__(msg)
        self.msg = msg
        self.pytrace = pytrace

    def __repr__(self) -> str:
        if self.msg is not None:
            return self.msg
        return f"<{self.__class__.__name__} instance>"

    __str__ = __repr__


TEST_OUTCOME = (OutcomeException, Exception)


class Skipped(OutcomeException):
    # XXX hackish: on 3k we fake to live in the builtins
    # in order to have Skipped exception printing shorter/nicer
    __module__ = "builtins"

    def __init__(
        self,
        msg: str | None = None,
        pytrace: bool = True,
        allow_module_level: bool = False,
        *,
        _use_item_location: bool = False,
    ) -> None:
        super().__init__(msg=msg, pytrace=pytrace)
        self.allow_module_level = allow_module_level
        # If true, the skip location is reported as the item's location,
        # instead of the place that raises the exception/calls skip().
        self._use_item_location = _use_item_location


class Failed(OutcomeException):
    """Raised from an explicit call to pytest.fail()."""

    __module__ = "builtins"


class Exit(Exception):
    """Raised for immediate program exits (no tracebacks/summaries)."""

    def __init__(
        self, msg: str = "unknown reason", returncode: int | None = None
    ) -> None:
        self.msg = msg
        self.returncode = returncode
        super().__init__(msg)


class XFailed(Failed):
    """Raised from an explicit call to pytest.xfail()."""


class _Exit:
    """Exit testing process.

    :param reason:
        The message to show as the reason for exiting pytest.  reason has a default value
        only because `msg` is deprecated.

    :param returncode:
        Return code to be used when exiting pytest. None means the same as ``0`` (no error),
        same as :func:`sys.exit`.

    :raises pytest.exit.Exception:
        The exception that is raised.
    """

    Exception: ClassVar[type[Exit]] = Exit

    def __call__(self, reason: str = "", returncode: int | None = None) -> NoReturn:
        __tracebackhide__ = True
        raise Exit(msg=reason, returncode=returncode)


exit: _Exit = _Exit()


class _Skip:
    """Skip an executing test with the given message.

    This function should be called only during testing (setup, call or teardown) or
    during collection by using the ``allow_module_level`` flag.  This function can
    be called in doctests as well.

    :param reason:
        The message to show the user as reason for the skip.

    :param allow_module_level:
        Allows this function to be called at module level.
        Raising the skip exception at module level will stop
        the execution of the module and prevent the collection of all tests in the module,
        even those defined before the `skip` call.

        Defaults to False.

    :raises pytest.skip.Exception:
        The exception that is raised.

    .. note::
        It is better to use the :ref:`pytest.mark.skipif ref` marker when
        possible to declare a test to be skipped under certain conditions
        like mismatching platforms or dependencies.
        Similarly, use the ``# doctest: +SKIP`` directive (see :py:data:`doctest.SKIP`)
        to skip a doctest statically.
    """

    Exception: ClassVar[type[Skipped]] = Skipped

    def __call__(self, reason: str = "", allow_module_level: bool = False) -> NoReturn:
        __tracebackhide__ = True
        raise Skipped(msg=reason, allow_module_level=allow_module_level)


skip: _Skip = _Skip()


class _Fail:
    """Explicitly fail an executing test with the given message.

    :param reason:
        The message to show the user as reason for the failure.

    :param pytrace:
        If False, msg represents the full failure information and no
        python traceback will be reported.

    :raises pytest.fail.Exception:
        The exception that is raised.
    """

    Exception: ClassVar[type[Failed]] = Failed

    def __call__(self, reason: str = "", pytrace: bool = True) -> NoReturn:
        __tracebackhide__ = True
        raise Failed(msg=reason, pytrace=pytrace)


fail: _Fail = _Fail()


class _XFail:
    """Imperatively xfail an executing test or setup function with the given reason.

    This function should be called only during testing (setup, call or teardown).

    No other code is executed after using ``xfail()`` (it is implemented
    internally by raising an exception).

    :param reason:
        The message to show the user as reason for the xfail.

    .. note::
        It is better to use the :ref:`pytest.mark.xfail ref` marker when
        possible to declare a test to be xfailed under certain conditions
        like known bugs or missing features.

    :raises pytest.xfail.Exception:
        The exception that is raised.
    """

    Exception: ClassVar[type[XFailed]] = XFailed

    def __call__(self, reason: str = "") -> NoReturn:
        __tracebackhide__ = True
        raise XFailed(msg=reason)


xfail: _XFail = _XFail()


def importorskip(
    modname: str,
    minversion: str | None = None,
    reason: str | None = None,
    *,
    exc_type: type[ImportError] | None = None,
) -> Any:
    """Import and return the requested module ``modname``, or skip the
    current test if the module cannot be imported.

    :param modname:
        The name of the module to import.
    :param minversion:
        If given, the imported module's ``__version__`` attribute must be at
        least this minimal version, otherwise the test is still skipped.
    :param reason:
        If given, this reason is shown as the message when the module cannot
        be imported.
    :param exc_type:
        The exception that should be captured in order to skip modules.
        Must be :py:class:`ImportError` or a subclass.

        Defaults to :class:`ModuleNotFoundError` when not given, which means
        the module must be missing for the test to be skipped.
        Pass ``exc_type=ImportError`` to also skip modules that raise
        :class:`ImportError` during import.

        See :ref:`import-or-skip-import-error` for details.


    :returns:
        The imported module. This should be assigned to its canonical name.

    :raises pytest.skip.Exception:
        If the module cannot be imported.

    Example::

        docutils = pytest.importorskip("docutils")

    .. versionadded:: 8.2

        The ``exc_type`` parameter.

    .. versionchanged:: 9.1

        The default for ``exc_type`` is now :class:`ModuleNotFoundError`.
    """
    import warnings

    __tracebackhide__ = True
    compile(modname, "", "eval")  # to catch syntaxerrors

    # Keep the public signature compatible while using the pytest 9.1 default behavior.
    if exc_type is None:
        exc_type = ModuleNotFoundError

    skipped: Skipped | None = None

    with warnings.catch_warnings():
        # Make sure to ignore ImportWarnings that might happen because
        # of existing directories with the same name we're trying to
        # import but without a __init__.py file.
        warnings.simplefilter("ignore")

        try:
            importlib.import_module(modname)
        except exc_type as exc:
            # Do not raise or issue warnings inside the catch_warnings() block.
            if reason is None:
                reason = f"could not import {modname!r}: {exc}"
            skipped = Skipped(reason, allow_module_level=True)
    if skipped:
        raise skipped

    mod = sys.modules[modname]
    if minversion is None:
        return mod
    verattr = getattr(mod, "__version__", None)
    if minversion is not None:
        # Imported lazily to improve start-up time.
        from packaging.version import Version

        if verattr is None or Version(verattr) < Version(minversion):
            raise Skipped(
                f"module {modname!r} has __version__ {verattr!r}, required is: {minversion!r}",
                allow_module_level=True,
            )
    return mod
