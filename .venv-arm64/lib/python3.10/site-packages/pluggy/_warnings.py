from typing import final


class PluggyWarning(UserWarning):
    """Base class for all warnings emitted by pluggy."""

    __module__ = "pluggy"


@final
class PluggyTeardownRaisedWarning(PluggyWarning):
    """A plugin raised an exception during an :ref:`old-style hookwrapper
    <old_style_hookwrappers>` teardown.

    Such exceptions are not handled by pluggy, and may cause subsequent
    teardowns to be executed at unexpected times, or be skipped entirely.

    This is an issue in the plugin implementation.

    If the exception is unintended, fix the underlying cause.

    If the exception is intended, switch to :ref:`new-style hook wrappers
    <hookwrappers>`, or use :func:`result.force_exception()
    <pluggy.Result.force_exception>` to set the exception instead of raising.
    """

    __module__ = "pluggy"
