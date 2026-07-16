"""Provides a function to report all internal modules for using freezing
tools."""

from __future__ import annotations

from collections.abc import Iterator
import types


def freeze_includes() -> list[str]:
    """Return a list of module names used by pytest that should be
    included by cx_freeze."""
    import _pytest

    result = list(_iter_all_modules(_pytest))
    return result


def _iter_all_modules(
    package: str | types.ModuleType,
    prefix: str = "",
) -> Iterator[str]:
    """Iterate over the names of all modules that can be found in the given
    package, recursively.

        >>> import _pytest
        >>> list(_iter_all_modules(_pytest))
        ['_pytest._argcomplete', '_pytest._code.code', ...]
    """
    import os
    import pkgutil

    if isinstance(package, str):
        path = package
    else:
        # Type ignored because typeshed doesn't define ModuleType.__path__
        # (only defined on packages).
        package_path = package.__path__
        path, prefix = package_path[0], package.__name__ + "."
    for _, name, is_package in pkgutil.iter_modules([path]):
        if is_package:
            for m in _iter_all_modules(os.path.join(path, name), prefix=name + "."):
                yield prefix + m
        else:
            yield prefix + name
