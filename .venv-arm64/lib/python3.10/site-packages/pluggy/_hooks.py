"""
Internal hook annotation, representation and calling machinery.
"""

from __future__ import annotations

from collections.abc import Generator
from collections.abc import Mapping
from collections.abc import Sequence
from collections.abc import Set
import inspect
import sys
from types import ModuleType
from typing import Any
from typing import Callable
from typing import Final
from typing import final
from typing import Optional
from typing import overload
from typing import TYPE_CHECKING
from typing import TypedDict
from typing import TypeVar
from typing import Union
import warnings

from ._result import Result


_T = TypeVar("_T")
_F = TypeVar("_F", bound=Callable[..., object])
_Namespace = Union[ModuleType, type]
_Plugin = object
_HookExec = Callable[
    [str, Sequence["HookImpl"], Mapping[str, object], bool],
    Union[object, list[object]],
]
_HookImplFunction = Callable[..., Union[_T, Generator[None, Result[_T], None]]]


class HookspecOpts(TypedDict):
    """Options for a hook specification."""

    #: Whether the hook is :ref:`first result only <firstresult>`.
    firstresult: bool
    #: Whether the hook is :ref:`historic <historic>`.
    historic: bool
    #: Whether the hook :ref:`warns when implemented <warn_on_impl>`.
    warn_on_impl: Warning | None
    #: Whether the hook warns when :ref:`certain arguments are requested
    #: <warn_on_impl>`.
    #:
    #: .. versionadded:: 1.5
    warn_on_impl_args: Mapping[str, Warning] | None


class HookimplOpts(TypedDict):
    """Options for a hook implementation."""

    #: Whether the hook implementation is a :ref:`wrapper <hookwrapper>`.
    wrapper: bool
    #: Whether the hook implementation is an :ref:`old-style wrapper
    #: <old_style_hookwrappers>`.
    hookwrapper: bool
    #: Whether validation against a hook specification is :ref:`optional
    #: <optionalhook>`.
    optionalhook: bool
    #: Whether to try to order this hook implementation :ref:`first
    #: <callorder>`.
    tryfirst: bool
    #: Whether to try to order this hook implementation :ref:`last
    #: <callorder>`.
    trylast: bool
    #: The name of the hook specification to match, see :ref:`specname`.
    specname: str | None


@final
class HookspecMarker:
    """Decorator for marking functions as hook specifications.

    Instantiate it with a project_name to get a decorator.
    Calling :meth:`PluginManager.add_hookspecs` later will discover all marked
    functions if the :class:`PluginManager` uses the same project name.
    """

    __slots__ = ("project_name",)

    def __init__(self, project_name: str) -> None:
        self.project_name: Final = project_name

    @overload
    def __call__(
        self,
        function: _F,
        firstresult: bool = False,
        historic: bool = False,
        warn_on_impl: Warning | None = None,
        warn_on_impl_args: Mapping[str, Warning] | None = None,
    ) -> _F: ...

    @overload  # noqa: F811
    def __call__(  # noqa: F811
        self,
        function: None = ...,
        firstresult: bool = ...,
        historic: bool = ...,
        warn_on_impl: Warning | None = ...,
        warn_on_impl_args: Mapping[str, Warning] | None = ...,
    ) -> Callable[[_F], _F]: ...

    def __call__(  # noqa: F811
        self,
        function: _F | None = None,
        firstresult: bool = False,
        historic: bool = False,
        warn_on_impl: Warning | None = None,
        warn_on_impl_args: Mapping[str, Warning] | None = None,
    ) -> _F | Callable[[_F], _F]:
        """If passed a function, directly sets attributes on the function
        which will make it discoverable to :meth:`PluginManager.add_hookspecs`.

        If passed no function, returns a decorator which can be applied to a
        function later using the attributes supplied.

        :param firstresult:
            If ``True``, the 1:N hook call (N being the number of registered
            hook implementation functions) will stop at I<=N when the I'th
            function returns a non-``None`` result. See :ref:`firstresult`.

        :param historic:
            If ``True``, every call to the hook will be memorized and replayed
            on plugins registered after the call was made. See :ref:`historic`.

        :param warn_on_impl:
            If given, every implementation of this hook will trigger the given
            warning. See :ref:`warn_on_impl`.

        :param warn_on_impl_args:
            If given, every implementation of this hook which requests one of
            the arguments in the dict will trigger the corresponding warning.
            See :ref:`warn_on_impl`.

            .. versionadded:: 1.5
        """

        def setattr_hookspec_opts(func: _F) -> _F:
            if historic and firstresult:
                raise ValueError("cannot have a historic firstresult hook")
            opts: HookspecOpts = {
                "firstresult": firstresult,
                "historic": historic,
                "warn_on_impl": warn_on_impl,
                "warn_on_impl_args": warn_on_impl_args,
            }
            setattr(func, self.project_name + "_spec", opts)
            return func

        if function is not None:
            return setattr_hookspec_opts(function)
        else:
            return setattr_hookspec_opts


@final
class HookimplMarker:
    """Decorator for marking functions as hook implementations.

    Instantiate it with a ``project_name`` to get a decorator.
    Calling :meth:`PluginManager.register` later will discover all marked
    functions if the :class:`PluginManager` uses the same project name.
    """

    __slots__ = ("project_name",)

    def __init__(self, project_name: str) -> None:
        self.project_name: Final = project_name

    @overload
    def __call__(
        self,
        function: _F,
        hookwrapper: bool = ...,
        optionalhook: bool = ...,
        tryfirst: bool = ...,
        trylast: bool = ...,
        specname: str | None = ...,
        wrapper: bool = ...,
    ) -> _F: ...

    @overload  # noqa: F811
    def __call__(  # noqa: F811
        self,
        function: None = ...,
        hookwrapper: bool = ...,
        optionalhook: bool = ...,
        tryfirst: bool = ...,
        trylast: bool = ...,
        specname: str | None = ...,
        wrapper: bool = ...,
    ) -> Callable[[_F], _F]: ...

    def __call__(  # noqa: F811
        self,
        function: _F | None = None,
        hookwrapper: bool = False,
        optionalhook: bool = False,
        tryfirst: bool = False,
        trylast: bool = False,
        specname: str | None = None,
        wrapper: bool = False,
    ) -> _F | Callable[[_F], _F]:
        """If passed a function, directly sets attributes on the function
        which will make it discoverable to :meth:`PluginManager.register`.

        If passed no function, returns a decorator which can be applied to a
        function later using the attributes supplied.

        :param optionalhook:
            If ``True``, a missing matching hook specification will not result
            in an error (by default it is an error if no matching spec is
            found). See :ref:`optionalhook`.

        :param tryfirst:
            If ``True``, this hook implementation will run as early as possible
            in the chain of N hook implementations for a specification. See
            :ref:`callorder`.

        :param trylast:
            If ``True``, this hook implementation will run as late as possible
            in the chain of N hook implementations for a specification. See
            :ref:`callorder`.

        :param wrapper:
            If ``True`` ("new-style hook wrapper"), the hook implementation
            needs to execute exactly one ``yield``. The code before the
            ``yield`` is run early before any non-hook-wrapper function is run.
            The code after the ``yield`` is run after all non-hook-wrapper
            functions have run. The ``yield`` receives the result value of the
            inner calls, or raises the exception of inner calls (including
            earlier hook wrapper calls). The return value of the function
            becomes the return value of the hook, and a raised exception becomes
            the exception of the hook. See :ref:`hookwrapper`.

        :param hookwrapper:
            If ``True`` ("old-style hook wrapper"), the hook implementation
            needs to execute exactly one ``yield``. The code before the
            ``yield`` is run early before any non-hook-wrapper function is run.
            The code after the ``yield`` is run after all non-hook-wrapper
            function have run  The ``yield`` receives a :class:`Result` object
            representing the exception or result outcome of the inner calls
            (including earlier hook wrapper calls). This option is mutually
            exclusive with ``wrapper``. See :ref:`old_style_hookwrapper`.

        :param specname:
            If provided, the given name will be used instead of the function
            name when matching this hook implementation to a hook specification
            during registration. See :ref:`specname`.

        .. versionadded:: 1.2.0
            The ``wrapper`` parameter.
        """

        def setattr_hookimpl_opts(func: _F) -> _F:
            opts: HookimplOpts = {
                "wrapper": wrapper,
                "hookwrapper": hookwrapper,
                "optionalhook": optionalhook,
                "tryfirst": tryfirst,
                "trylast": trylast,
                "specname": specname,
            }
            setattr(func, self.project_name + "_impl", opts)
            return func

        if function is None:
            return setattr_hookimpl_opts
        else:
            return setattr_hookimpl_opts(function)


def normalize_hookimpl_opts(opts: HookimplOpts) -> None:
    opts.setdefault("tryfirst", False)
    opts.setdefault("trylast", False)
    opts.setdefault("wrapper", False)
    opts.setdefault("hookwrapper", False)
    opts.setdefault("optionalhook", False)
    opts.setdefault("specname", None)


_PYPY = hasattr(sys, "pypy_version_info")


def varnames(func: object) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return tuple of positional and keywrord argument names for a function,
    method, class or callable.

    In case of a class, its ``__init__`` method is considered.
    For methods the ``self`` parameter is not included.
    """
    if inspect.isclass(func):
        try:
            func = func.__init__
        except AttributeError:  # pragma: no cover - pypy special case
            return (), ()
    elif not inspect.isroutine(func):  # callable object?
        try:
            func = getattr(func, "__call__", func)
        except Exception:  # pragma: no cover - pypy special case
            return (), ()

    try:
        # func MUST be a function or method here or we won't parse any args.
        sig = inspect.signature(
            func.__func__ if inspect.ismethod(func) else func  # type:ignore[arg-type]
        )
    except TypeError:  # pragma: no cover
        return (), ()

    _valid_param_kinds = (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )
    _valid_params = {
        name: param
        for name, param in sig.parameters.items()
        if param.kind in _valid_param_kinds
    }
    args = tuple(_valid_params)
    defaults = (
        tuple(
            param.default
            for param in _valid_params.values()
            if param.default is not param.empty
        )
        or None
    )

    if defaults:
        index = -len(defaults)
        args, kwargs = args[:index], tuple(args[index:])
    else:
        kwargs = ()

    # strip any implicit instance arg
    # pypy3 uses "obj" instead of "self" for default dunder methods
    if not _PYPY:
        implicit_names: tuple[str, ...] = ("self",)
    else:  # pragma: no cover
        implicit_names = ("self", "obj")
    if args:
        qualname: str = getattr(func, "__qualname__", "")
        if inspect.ismethod(func) or ("." in qualname and args[0] in implicit_names):
            args = args[1:]

    return args, kwargs


@final
class HookRelay:
    """Hook holder object for performing 1:N hook calls where N is the number
    of registered plugins."""

    __slots__ = ("__dict__",)

    def __init__(self) -> None:
        """:meta private:"""

    if TYPE_CHECKING:

        def __getattr__(self, name: str) -> HookCaller: ...


# Historical name (pluggy<=1.2), kept for backward compatibility.
_HookRelay = HookRelay


_CallHistory = list[tuple[Mapping[str, object], Optional[Callable[[Any], None]]]]


class HookCaller:
    """A caller of all registered implementations of a hook specification."""

    __slots__ = (
        "name",
        "spec",
        "_hookexec",
        "_hookimpls",
        "_call_history",
    )

    def __init__(
        self,
        name: str,
        hook_execute: _HookExec,
        specmodule_or_class: _Namespace | None = None,
        spec_opts: HookspecOpts | None = None,
    ) -> None:
        """:meta private:"""
        #: Name of the hook getting called.
        self.name: Final = name
        self._hookexec: Final = hook_execute
        # The hookimpls list. The caller iterates it *in reverse*. Format:
        # 1. trylast nonwrappers
        # 2. nonwrappers
        # 3. tryfirst nonwrappers
        # 4. trylast wrappers
        # 5. wrappers
        # 6. tryfirst wrappers
        self._hookimpls: Final[list[HookImpl]] = []
        self._call_history: _CallHistory | None = None
        # TODO: Document, or make private.
        self.spec: HookSpec | None = None
        if specmodule_or_class is not None:
            assert spec_opts is not None
            self.set_specification(specmodule_or_class, spec_opts)

    # TODO: Document, or make private.
    def has_spec(self) -> bool:
        return self.spec is not None

    # TODO: Document, or make private.
    def set_specification(
        self,
        specmodule_or_class: _Namespace,
        spec_opts: HookspecOpts,
    ) -> None:
        if self.spec is not None:
            raise ValueError(
                f"Hook {self.spec.name!r} is already registered "
                f"within namespace {self.spec.namespace}"
            )
        self.spec = HookSpec(specmodule_or_class, self.name, spec_opts)
        if spec_opts.get("historic"):
            self._call_history = []

    def is_historic(self) -> bool:
        """Whether this caller is :ref:`historic <historic>`."""
        return self._call_history is not None

    def _remove_plugin(self, plugin: _Plugin) -> None:
        for i, method in enumerate(self._hookimpls):
            if method.plugin == plugin:
                del self._hookimpls[i]
                return
        raise ValueError(f"plugin {plugin!r} not found")

    def get_hookimpls(self) -> list[HookImpl]:
        """Get all registered hook implementations for this hook."""
        return self._hookimpls.copy()

    def _add_hookimpl(self, hookimpl: HookImpl) -> None:
        """Add an implementation to the callback chain."""
        for i, method in enumerate(self._hookimpls):
            if method.hookwrapper or method.wrapper:
                splitpoint = i
                break
        else:
            splitpoint = len(self._hookimpls)
        if hookimpl.hookwrapper or hookimpl.wrapper:
            start, end = splitpoint, len(self._hookimpls)
        else:
            start, end = 0, splitpoint

        if hookimpl.trylast:
            self._hookimpls.insert(start, hookimpl)
        elif hookimpl.tryfirst:
            self._hookimpls.insert(end, hookimpl)
        else:
            # find last non-tryfirst method
            i = end - 1
            while i >= start and self._hookimpls[i].tryfirst:
                i -= 1
            self._hookimpls.insert(i + 1, hookimpl)

    def __repr__(self) -> str:
        return f"<HookCaller {self.name!r}>"

    def _verify_all_args_are_provided(self, kwargs: Mapping[str, object]) -> None:
        # This is written to avoid expensive operations when not needed.
        if self.spec:
            for argname in self.spec.argnames:
                if argname not in kwargs:
                    notincall = ", ".join(
                        repr(argname)
                        for argname in self.spec.argnames
                        # Avoid self.spec.argnames - kwargs.keys()
                        # it doesn't preserve order.
                        if argname not in kwargs.keys()
                    )
                    warnings.warn(
                        f"Argument(s) {notincall} which are declared in the hookspec "
                        "cannot be found in this hook call",
                        stacklevel=2,
                    )
                    break

    def __call__(self, **kwargs: object) -> Any:
        """Call the hook.

        Only accepts keyword arguments, which should match the hook
        specification.

        Returns the result(s) of calling all registered plugins, see
        :ref:`calling`.
        """
        assert not self.is_historic(), (
            "Cannot directly call a historic hook - use call_historic instead."
        )
        self._verify_all_args_are_provided(kwargs)
        firstresult = self.spec.opts.get("firstresult", False) if self.spec else False
        # Copy because plugins may register other plugins during iteration (#438).
        return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)

    def call_historic(
        self,
        result_callback: Callable[[Any], None] | None = None,
        kwargs: Mapping[str, object] | None = None,
    ) -> None:
        """Call the hook with given ``kwargs`` for all registered plugins and
        for all plugins which will be registered afterwards, see
        :ref:`historic`.

        :param result_callback:
            If provided, will be called for each non-``None`` result obtained
            from a hook implementation.
        """
        assert self._call_history is not None
        kwargs = kwargs or {}
        self._verify_all_args_are_provided(kwargs)
        self._call_history.append((kwargs, result_callback))
        # Historizing hooks don't return results.
        # Remember firstresult isn't compatible with historic.
        # Copy because plugins may register other plugins during iteration (#438).
        res = self._hookexec(self.name, self._hookimpls.copy(), kwargs, False)
        if result_callback is None:
            return
        if isinstance(res, list):
            for x in res:
                result_callback(x)

    def call_extra(
        self, methods: Sequence[Callable[..., object]], kwargs: Mapping[str, object]
    ) -> Any:
        """Call the hook with some additional temporarily participating
        methods using the specified ``kwargs`` as call parameters, see
        :ref:`call_extra`."""
        assert not self.is_historic(), (
            "Cannot directly call a historic hook - use call_historic instead."
        )
        self._verify_all_args_are_provided(kwargs)
        opts: HookimplOpts = {
            "wrapper": False,
            "hookwrapper": False,
            "optionalhook": False,
            "trylast": False,
            "tryfirst": False,
            "specname": None,
        }
        hookimpls = self._hookimpls.copy()
        for method in methods:
            hookimpl = HookImpl(None, "<temp>", method, opts)
            # Find last non-tryfirst nonwrapper method.
            i = len(hookimpls) - 1
            while i >= 0 and (
                # Skip wrappers.
                (hookimpls[i].hookwrapper or hookimpls[i].wrapper)
                # Skip tryfirst nonwrappers.
                or hookimpls[i].tryfirst
            ):
                i -= 1
            hookimpls.insert(i + 1, hookimpl)
        firstresult = self.spec.opts.get("firstresult", False) if self.spec else False
        return self._hookexec(self.name, hookimpls, kwargs, firstresult)

    def _maybe_apply_history(self, method: HookImpl) -> None:
        """Apply call history to a new hookimpl if it is marked as historic."""
        if self.is_historic():
            assert self._call_history is not None
            for kwargs, result_callback in self._call_history:
                res = self._hookexec(self.name, [method], kwargs, False)
                if res and result_callback is not None:
                    # XXX: remember firstresult isn't compat with historic
                    assert isinstance(res, list)
                    result_callback(res[0])


# Historical name (pluggy<=1.2), kept for backward compatibility.
_HookCaller = HookCaller


class _SubsetHookCaller(HookCaller):
    """A proxy to another HookCaller which manages calls to all registered
    plugins except the ones from remove_plugins."""

    # This class is unusual: in inhertits from `HookCaller` so all of
    # the *code* runs in the class, but it delegates all underlying *data*
    # to the original HookCaller.
    # `subset_hook_caller` used to be implemented by creating a full-fledged
    # HookCaller, copying all hookimpls from the original. This had problems
    # with memory leaks (#346) and historic calls (#347), which make a proxy
    # approach better.
    # An alternative implementation is to use a `_getattr__`/`__getattribute__`
    # proxy, however that adds more overhead and is more tricky to implement.

    __slots__ = (
        "_orig",
        "_remove_plugins",
    )

    def __init__(self, orig: HookCaller, remove_plugins: Set[_Plugin]) -> None:
        self._orig = orig
        self._remove_plugins = remove_plugins
        self.name = orig.name  # type: ignore[misc]
        self._hookexec = orig._hookexec  # type: ignore[misc]

    @property  # type: ignore[misc]
    def _hookimpls(self) -> list[HookImpl]:
        return [
            impl
            for impl in self._orig._hookimpls
            if impl.plugin not in self._remove_plugins
        ]

    @property
    def spec(self) -> HookSpec | None:  # type: ignore[override]
        return self._orig.spec

    @property
    def _call_history(self) -> _CallHistory | None:  # type: ignore[override]
        return self._orig._call_history

    def __repr__(self) -> str:
        return f"<_SubsetHookCaller {self.name!r}>"


@final
class HookImpl:
    """A hook implementation in a :class:`HookCaller`."""

    __slots__ = (
        "function",
        "argnames",
        "kwargnames",
        "plugin",
        "opts",
        "plugin_name",
        "wrapper",
        "hookwrapper",
        "optionalhook",
        "tryfirst",
        "trylast",
    )

    def __init__(
        self,
        plugin: _Plugin,
        plugin_name: str,
        function: _HookImplFunction[object],
        hook_impl_opts: HookimplOpts,
    ) -> None:
        """:meta private:"""
        #: The hook implementation function.
        self.function: Final = function
        argnames, kwargnames = varnames(self.function)
        #: The positional parameter names of ``function```.
        self.argnames: Final = argnames
        #: The keyword parameter names of ``function```.
        self.kwargnames: Final = kwargnames
        #: The plugin which defined this hook implementation.
        self.plugin: Final = plugin
        #: The :class:`HookimplOpts` used to configure this hook implementation.
        self.opts: Final = hook_impl_opts
        #: The name of the plugin which defined this hook implementation.
        self.plugin_name: Final = plugin_name
        #: Whether the hook implementation is a :ref:`wrapper <hookwrapper>`.
        self.wrapper: Final = hook_impl_opts["wrapper"]
        #: Whether the hook implementation is an :ref:`old-style wrapper
        #: <old_style_hookwrappers>`.
        self.hookwrapper: Final = hook_impl_opts["hookwrapper"]
        #: Whether validation against a hook specification is :ref:`optional
        #: <optionalhook>`.
        self.optionalhook: Final = hook_impl_opts["optionalhook"]
        #: Whether to try to order this hook implementation :ref:`first
        #: <callorder>`.
        self.tryfirst: Final = hook_impl_opts["tryfirst"]
        #: Whether to try to order this hook implementation :ref:`last
        #: <callorder>`.
        self.trylast: Final = hook_impl_opts["trylast"]

    def __repr__(self) -> str:
        return f"<HookImpl plugin_name={self.plugin_name!r}, plugin={self.plugin!r}>"


@final
class HookSpec:
    __slots__ = (
        "namespace",
        "function",
        "name",
        "argnames",
        "kwargnames",
        "opts",
        "warn_on_impl",
        "warn_on_impl_args",
    )

    def __init__(self, namespace: _Namespace, name: str, opts: HookspecOpts) -> None:
        self.namespace = namespace
        self.function: Callable[..., object] = getattr(namespace, name)
        self.name = name
        self.argnames, self.kwargnames = varnames(self.function)
        self.opts = opts
        self.warn_on_impl = opts.get("warn_on_impl")
        self.warn_on_impl_args = opts.get("warn_on_impl_args")
