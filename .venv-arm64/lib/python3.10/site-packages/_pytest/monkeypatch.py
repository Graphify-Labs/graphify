# mypy: allow-untyped-defs
"""Monkeypatching and mocking functionality."""

from __future__ import annotations

from collections.abc import Generator
from collections.abc import Mapping
from collections.abc import MutableMapping
from contextlib import contextmanager
import importlib
import os
from pathlib import Path
import re
import sys
from typing import Any
from typing import final
from typing import overload
from typing import TypeVar
import warnings

from _pytest.compat import NOTSET
from _pytest.compat import NotSetType
from _pytest.deprecated import MONKEYPATCH_LEGACY_NAMESPACE_PACKAGES
from _pytest.fixtures import fixture
from _pytest.warning_types import PytestWarning


RE_IMPORT_ERROR_NAME = re.compile(r"^No module named (.*)$")


K = TypeVar("K")
V = TypeVar("V")


@fixture
def monkeypatch() -> Generator[MonkeyPatch]:
    """A convenient fixture for monkey-patching.

    The fixture provides these methods to modify objects, dictionaries, or
    :data:`os.environ`:

    * :meth:`monkeypatch.setattr(obj, name, value, raising=True) <pytest.MonkeyPatch.setattr>`
    * :meth:`monkeypatch.delattr(obj, name, raising=True) <pytest.MonkeyPatch.delattr>`
    * :meth:`monkeypatch.setitem(mapping, name, value) <pytest.MonkeyPatch.setitem>`
    * :meth:`monkeypatch.delitem(obj, name, raising=True) <pytest.MonkeyPatch.delitem>`
    * :meth:`monkeypatch.setenv(name, value, prepend=None) <pytest.MonkeyPatch.setenv>`
    * :meth:`monkeypatch.delenv(name, raising=True) <pytest.MonkeyPatch.delenv>`
    * :meth:`monkeypatch.syspath_prepend(path) <pytest.MonkeyPatch.syspath_prepend>`
    * :meth:`monkeypatch.chdir(path) <pytest.MonkeyPatch.chdir>`
    * :meth:`monkeypatch.context() <pytest.MonkeyPatch.context>`

    All modifications will be undone after the requesting test function or
    fixture has finished. The ``raising`` parameter determines if a :class:`KeyError`
    or :class:`AttributeError` will be raised if the set/deletion operation does not have the
    specified target.

    To undo modifications done by the fixture in a contained scope,
    use :meth:`context() <pytest.MonkeyPatch.context>`.
    """
    mpatch = MonkeyPatch()
    yield mpatch
    mpatch.undo()


def resolve(name: str) -> object:
    # Simplified from zope.dottedname.
    parts = name.split(".")

    used = parts.pop(0)
    found: object = importlib.import_module(used)
    for part in parts:
        used += "." + part
        try:
            found = getattr(found, part)
        except AttributeError:
            pass
        else:
            continue
        # We use explicit un-nesting of the handling block in order
        # to avoid nested exceptions.
        try:
            importlib.import_module(used)
        except ImportError as ex:
            expected = str(ex).split()[-1]
            if expected == used:
                raise
            else:
                raise ImportError(f"import error in {used}: {ex}") from ex
        found = annotated_getattr(found, part, used)
    return found


def annotated_getattr(obj: object, name: str, ann: str) -> object:
    try:
        obj = getattr(obj, name)
    except AttributeError as e:
        raise AttributeError(
            f"{type(obj).__name__!r} object at {ann} has no attribute {name!r}"
        ) from e
    return obj


def derive_importpath(import_path: str, raising: bool) -> tuple[str, object]:
    if not isinstance(import_path, str) or "." not in import_path:
        raise TypeError(f"must be absolute import path string, not {import_path!r}")
    module, attr = import_path.rsplit(".", 1)
    target = resolve(module)
    if raising:
        annotated_getattr(target, attr, ann=module)
    return attr, target


@final
class MonkeyPatch:
    """Helper to conveniently monkeypatch attributes/items/environment
    variables/syspath.

    Returned by the :fixture:`monkeypatch` fixture.

    .. versionchanged:: 6.2
        Can now also be used directly as `pytest.MonkeyPatch()`, for when
        the fixture is not available. In this case, use
        :meth:`with MonkeyPatch.context() as mp: <context>` or remember to call
        :meth:`undo` explicitly.
    """

    def __init__(self) -> None:
        self._setattr: list[tuple[object, str, object]] = []
        self._setitem: list[tuple[Mapping[Any, Any], object, object]] = []
        self._cwd: str | None = None
        self._savesyspath: list[str] | None = None

    @classmethod
    @contextmanager
    def context(cls) -> Generator[MonkeyPatch]:
        """Context manager that returns a new :class:`MonkeyPatch` object
        which undoes any patching done inside the ``with`` block upon exit.

        Example:

        .. code-block:: python

            import functools


            def test_partial(monkeypatch):
                with monkeypatch.context() as m:
                    m.setattr(functools, "partial", 3)

        Useful in situations where it is desired to undo some patches before the test ends,
        such as mocking ``stdlib`` functions that might break pytest itself if mocked (for examples
        of this see :issue:`3290`).
        """
        m = cls()
        try:
            yield m
        finally:
            m.undo()

    @overload
    def setattr(
        self,
        target: str,
        name: object,
        value: NotSetType = ...,
        raising: bool = ...,
    ) -> None: ...

    @overload
    def setattr(
        self,
        target: object,
        name: str,
        value: object,
        raising: bool = ...,
    ) -> None: ...

    def setattr(
        self,
        target: str | object,
        name: object | str,
        value: object = NOTSET,
        raising: bool = True,
    ) -> None:
        """
        Set attribute value on target, memorizing the old value.

        For example:

        .. code-block:: python

            import os

            monkeypatch.setattr(os, "getcwd", lambda: "/")

        The code above replaces the :func:`os.getcwd` function by a ``lambda`` which
        always returns ``"/"``.

        For convenience, you can specify a string as ``target`` which
        will be interpreted as a dotted import path, with the last part
        being the attribute name:

        .. code-block:: python

            monkeypatch.setattr("os.getcwd", lambda: "/")

        Raises :class:`AttributeError` if the attribute does not exist, unless
        ``raising`` is set to False.

        **Where to patch**

        ``monkeypatch.setattr`` works by (temporarily) changing the object that a name points to with another one.
        There can be many names pointing to any individual object, so for patching to work you must ensure
        that you patch the name used by the system under test.

        See the section :ref:`Where to patch <python:where-to-patch>` in the :mod:`unittest.mock`
        docs for a complete explanation, which is meant for :func:`unittest.mock.patch` but
        applies to ``monkeypatch.setattr`` as well.
        """
        __tracebackhide__ = True
        import inspect

        if value is NOTSET:
            if not isinstance(target, str):
                raise TypeError(
                    "use setattr(target, name, value) or "
                    "setattr(target, value) with target being a dotted "
                    "import string"
                )
            value = name
            name, target = derive_importpath(target, raising)
        else:
            if not isinstance(name, str):
                raise TypeError(
                    "use setattr(target, name, value) with name being a string or "
                    "setattr(target, value) with target being a dotted "
                    "import string"
                )

        oldval = getattr(target, name, NOTSET)
        if raising and oldval is NOTSET:
            raise AttributeError(f"{target!r} has no attribute {name!r}")

        # avoid class descriptors like staticmethod/classmethod
        if inspect.isclass(target):
            oldval = target.__dict__.get(name, NOTSET)
        setattr(target, name, value)
        self._setattr.append((target, name, oldval))

    def delattr(
        self,
        target: object | str,
        name: str | NotSetType = NOTSET,
        raising: bool = True,
    ) -> None:
        """Delete attribute ``name`` from ``target``.

        If no ``name`` is specified and ``target`` is a string
        it will be interpreted as a dotted import path with the
        last part being the attribute name.

        Raises AttributeError it the attribute does not exist, unless
        ``raising`` is set to False.
        """
        __tracebackhide__ = True
        import inspect

        if name is NOTSET:
            if not isinstance(target, str):
                raise TypeError(
                    "use delattr(target, name) or "
                    "delattr(target) with target being a dotted "
                    "import string"
                )
            name, target = derive_importpath(target, raising)

        if not hasattr(target, name):
            if raising:
                raise AttributeError(name)
        else:
            oldval = getattr(target, name, NOTSET)
            # Avoid class descriptors like staticmethod/classmethod.
            if inspect.isclass(target):
                oldval = target.__dict__.get(name, NOTSET)
            self._setattr.append((target, name, oldval))
            delattr(target, name)

    def setitem(self, dic: Mapping[K, V], name: K, value: V) -> None:
        """Set dictionary entry ``name`` to value."""
        self._setitem.append((dic, name, dic.get(name, NOTSET)))
        # Not all Mapping types support indexing, but MutableMapping doesn't support TypedDict
        dic[name] = value  # type: ignore[index]

    def delitem(self, dic: Mapping[K, V], name: K, raising: bool = True) -> None:
        """Delete ``name`` from dict.

        Raises ``KeyError`` if it doesn't exist, unless ``raising`` is set to
        False.
        """
        if name not in dic:
            if raising:
                raise KeyError(name)
        else:
            self._setitem.append((dic, name, dic.get(name, NOTSET)))
            # Not all Mapping types support indexing, but MutableMapping doesn't support TypedDict
            del dic[name]  # type: ignore[attr-defined]

    def setenv(self, name: str, value: str, prepend: str | None = None) -> None:
        """Set environment variable ``name`` to ``value``.

        If ``prepend`` is a character, read the current environment variable
        value and prepend the ``value`` adjoined with the ``prepend``
        character.
        """
        if not isinstance(value, str):
            warnings.warn(  # type: ignore[unreachable]
                PytestWarning(
                    f"Value of environment variable {name} type should be str, but got "
                    f"{value!r} (type: {type(value).__name__}); converted to str implicitly"
                ),
                stacklevel=2,
            )
            value = str(value)
        if prepend and name in os.environ:
            value = value + prepend + os.environ[name]
        self.setitem(os.environ, name, value)

    def delenv(self, name: str, raising: bool = True) -> None:
        """Delete ``name`` from the environment.

        Raises ``KeyError`` if it does not exist, unless ``raising`` is set to
        False.
        """
        environ: MutableMapping[str, str] = os.environ
        self.delitem(environ, name, raising=raising)

    def syspath_prepend(self, path) -> None:
        """Prepend ``path`` to ``sys.path`` list of import locations."""
        if self._savesyspath is None:
            self._savesyspath = sys.path[:]
        sys.path.insert(0, str(path))

        # https://github.com/pypa/setuptools/blob/d8b901bc/docs/pkg_resources.txt#L162-L171
        # this is only needed when pkg_resources was already loaded by the namespace package
        if "pkg_resources" in sys.modules:
            import pkg_resources
            from pkg_resources import fixup_namespace_packages

            # Only issue deprecation warning if this call would actually have an
            # effect for this specific path.
            if (
                hasattr(pkg_resources, "_namespace_packages")
                and pkg_resources._namespace_packages
            ):
                path_obj = Path(str(path))
                for ns_pkg in pkg_resources._namespace_packages:
                    if ns_pkg is None:
                        continue
                    ns_pkg_path = path_obj / ns_pkg.replace(".", os.sep)
                    if ns_pkg_path.is_dir():
                        warnings.warn(
                            MONKEYPATCH_LEGACY_NAMESPACE_PACKAGES, stacklevel=2
                        )
                        break

            fixup_namespace_packages(str(path))

        # A call to syspathinsert() usually means that the caller wants to
        # import some dynamically created files, thus with python3 we
        # invalidate its import caches.
        # This is especially important when any namespace package is in use,
        # since then the mtime based FileFinder cache (that gets created in
        # this case already) gets not invalidated when writing the new files
        # quickly afterwards.
        from importlib import invalidate_caches

        invalidate_caches()

    def chdir(self, path: str | os.PathLike[str]) -> None:
        """Change the current working directory to the specified path.

        :param path:
            The path to change into.
        """
        if self._cwd is None:
            self._cwd = os.getcwd()
        os.chdir(path)

    def undo(self) -> None:
        """Undo previous changes.

        This call consumes the undo stack. Calling it a second time has no
        effect unless you do more monkeypatching after the undo call.

        There is generally no need to call `undo()`, since it is
        called automatically during tear-down.

        .. note::
            The same `monkeypatch` fixture is used across a
            single test function invocation. If `monkeypatch` is used both by
            the test function itself and one of the test fixtures,
            calling `undo()` will undo all of the changes made in
            both functions.

            Prefer to use :meth:`context() <pytest.MonkeyPatch.context>` instead.
        """
        for obj, name, value in reversed(self._setattr):
            if value is not NOTSET:
                setattr(obj, name, value)
            else:
                delattr(obj, name)
        self._setattr[:] = []
        for dictionary, key, value in reversed(self._setitem):
            if value is NOTSET:
                try:
                    # Not all Mapping types support indexing, but MutableMapping doesn't support TypedDict
                    del dictionary[key]  # type: ignore[attr-defined]
                except KeyError:
                    pass  # Was already deleted, so we have the desired state.
            else:
                # Not all Mapping types support indexing, but MutableMapping doesn't support TypedDict
                dictionary[key] = value  # type: ignore[index]
        self._setitem[:] = []
        if self._savesyspath is not None:
            sys.path[:] = self._savesyspath
            self._savesyspath = None

        if self._cwd is not None:
            os.chdir(self._cwd)
            self._cwd = None
