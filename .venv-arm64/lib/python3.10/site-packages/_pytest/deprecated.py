"""Deprecation messages and bits of code used elsewhere in the codebase that
is planned to be removed in the next pytest release.

Keeping it in a central location makes it easy to track what is deprecated and should
be removed when the time comes.

All constants defined in this module should be either instances of
:class:`PytestWarning`, or :class:`UnformattedWarning`
in case of warnings which need to format their messages.
"""

from __future__ import annotations

from warnings import warn

from _pytest.warning_types import PytestDeprecationWarning
from _pytest.warning_types import PytestRemovedIn10Warning
from _pytest.warning_types import UnformattedWarning


# set of plugins which have been integrated into the core; we use this list to ignore
# them during registration to avoid conflicts
DEPRECATED_EXTERNAL_PLUGINS = {
    "pytest_catchlog",
    "pytest_capturelog",
    "pytest_faulthandler",
    "pytest_subtests",
}


# This could have been removed pytest 8, but it's harmless and common, so no rush to remove.
YIELD_FIXTURE = PytestDeprecationWarning(
    "@pytest.yield_fixture is deprecated.\n"
    "Use @pytest.fixture instead; they are the same."
)

CLASS_FIXTURE_INSTANCE_METHOD = PytestRemovedIn10Warning(
    "Class-scoped fixture defined as instance method is deprecated.\n"
    "Instance attributes set in this fixture will NOT be visible to test methods,\n"
    "as each test gets a new instance while the fixture runs only once per class.\n"
    "Use @classmethod decorator and set attributes on cls instead.\n"
    "See https://docs.pytest.org/en/stable/deprecations.html#class-scoped-fixture-as-instance-method"
)

# This deprecation is never really meant to be removed.
PRIVATE = PytestDeprecationWarning("A private pytest class or function was used.")


HOOK_LEGACY_MARKING = UnformattedWarning(
    PytestRemovedIn10Warning,
    "The hook{type} {fullname} uses old-style configuration options (marks or attributes).\n"
    "Please use the pytest.hook{type}({hook_opts}) decorator instead\n"
    " to configure the hooks.\n"
    " See https://docs.pytest.org/en/latest/deprecations.html"
    "#configuring-hook-specs-impls-using-markers",
)

MONKEYPATCH_LEGACY_NAMESPACE_PACKAGES = PytestRemovedIn10Warning(
    "monkeypatch.syspath_prepend() called with pkg_resources legacy namespace packages detected.\n"
    "Legacy namespace packages (using pkg_resources.declare_namespace) are deprecated.\n"
    "Please use native namespace packages (PEP 420) instead.\n"
    "See https://docs.pytest.org/en/stable/deprecations.html#monkeypatch-fixup-namespace-packages"
)

PARAMETRIZE_NON_COLLECTION_ITERABLE = UnformattedWarning(
    PytestRemovedIn10Warning,
    "Passing a non-Collection iterable to parametrize is deprecated.\n"
    "Test: {nodeid}, argvalues type: {type_name}\n"
    "Please convert to a list or tuple.\n"
    "See https://docs.pytest.org/en/stable/deprecations.html#parametrize-iterators",
)

CONSOLE_MAIN = PytestRemovedIn10Warning(
    "pytest.console_main() is deprecated and will be removed in pytest 10.\n"
    "It was never intended for programmatic use; use pytest.main() instead.\n"
    "See https://docs.pytest.org/en/stable/deprecations.html#console-main"
)

CONFIG_INICFG = PytestRemovedIn10Warning(
    "config.inicfg is deprecated, use config.getini() to access configuration values instead.\n"
    "See https://docs.pytest.org/en/stable/deprecations.html#config-inicfg"
)

FIXTURE_GETFIXTUREVALUE_DURING_TEARDOWN = UnformattedWarning(
    PytestRemovedIn10Warning,
    'Calling request.getfixturevalue("{argname}") during teardown is deprecated.\n'
    "Please request the fixture before teardown begins, either by declaring it in the fixture signature "
    "or by calling request.getfixturevalue() before the fixture yields.\n"
    "See https://docs.pytest.org/en/stable/deprecations.html#dynamic-fixture-request-during-teardown",
)

PASTEBIN = PytestRemovedIn10Warning(
    "The --pastebin option is deprecated. "
    "The functionality is now available in an external plugin package, pytest-pastebin.\n"
    "See https://docs.pytest.org/en/stable/deprecations.html#the-pastebin-option"
)

# You want to make some `__init__` or function "private".
#
#   def my_private_function(some, args):
#       ...
#
# Do this:
#
#   def my_private_function(some, args, *, _ispytest: bool = False):
#       check_ispytest(_ispytest)
#       ...
#
# Change all internal/allowed calls to
#
#   my_private_function(some, args, _ispytest=True)
#
# All other calls will get the default _ispytest=False and trigger
# the warning (possibly error in the future).


FIXTURE_BASEID_DEPRECATED = PytestRemovedIn10Warning(
    "Passing baseid to FixtureDef is deprecated. Pass node instead for fixture scoping."
)

FIXTURE_NODEID_DEPRECATED = PytestRemovedIn10Warning(
    "Passing nodeid to _register_fixture is deprecated. "
    "Pass node instead for fixture scoping."
)

FIXTUREDEF_HAS_LOCATION_DEPRECATED = PytestRemovedIn10Warning(
    "FixtureDef.has_location is deprecated and will be removed in pytest 10. "
    "See https://docs.pytest.org/en/stable/deprecations.html#fixturedef-has-location-deprecated"
)

PARSEFACTORIES_NODEID_DEPRECATED = PytestRemovedIn10Warning(
    "Passing nodeid string to parsefactories is deprecated. "
    "Use parsefactories(holder=obj, node=node) instead."
)


def check_ispytest(ispytest: bool) -> None:
    if not ispytest:
        warn(PRIVATE, stacklevel=3)
