from __future__ import annotations

import copy
import math
import operator
import typing as t
from contextvars import ContextVar
from functools import partial
from functools import update_wrapper
from operator import attrgetter

from .wsgi import ClosingIterator

if t.TYPE_CHECKING:
    from _typeshed.wsgi import StartResponse
    from _typeshed.wsgi import WSGIApplication
    from _typeshed.wsgi import WSGIEnvironment

T = t.TypeVar("T")
F = t.TypeVar("F", bound=t.Callable[..., t.Any])


def release_local(local: Local | LocalStack[t.Any]) -> None:
    """Release the data for the current context in a :class:`Local` or
    :class:`LocalStack` without using a :class:`LocalManager`.

    This should not be needed for modern use cases, and may be removed
    in the future.

    .. versionadded:: 0.6.1
    """
    local.__release_local__()


class Local:
    """Create a namespace of context-local data. This wraps a
    :class:`ContextVar` containing a :class:`dict` value.

    This may incur a performance penalty compared to using individual
    context vars, as it has to copy data to avoid mutating the dict
    between nested contexts.

    :param context_var: The :class:`~contextvars.ContextVar` to use as
        storage for this local. If not given, one will be created.
        Context vars not created at the global scope may interfere with
        garbage collection.

    .. versionchanged:: 2.0
        Uses ``ContextVar`` instead of a custom storage implementation.
    """

    __slots__ = ("__storage",)

    def __init__(self, context_var: ContextVar[dict[str, t.Any]] | None = None) -> None:
        if context_var is None:
            # A ContextVar not created at global scope interferes with
            # Python's garbage collection. However, a local only makes
            # sense defined at the global scope as well, in which case
            # the GC issue doesn't seem relevant.
            context_var = ContextVar(f"werkzeug.Local<{id(self)}>.storage")

        object.__setattr__(self, "_Local__storage", context_var)

    def __iter__(self) -> t.Iterator[tuple[str, t.Any]]:
        return iter(self.__storage.get({}).items())

    def __call__(
        self, name: str, *, unbound_message: str | None = None
    ) -> LocalProxy[t.Any]:
        """Create a :class:`LocalProxy` that access an attribute on this
        local namespace.

        :param name: Proxy this attribute.
        :param unbound_message: The error message that the proxy will
            show if the attribute isn't set.
        """
        return LocalProxy(self, name, unbound_message=unbound_message)

    def __release_local__(self) -> None:
        self.__storage.set({})

    def __getattr__(self, name: str) -> t.Any:
        values = self.__storage.get({})

        if name in values:
            return values[name]

        raise AttributeError(name)

    def __setattr__(self, name: str, value: t.Any) -> None:
        values = self.__storage.get({}).copy()
        values[name] = value
        self.__storage.set(values)

    def __delattr__(self, name: str) -> None:
        values = self.__storage.get({})

        if name in values:
            values = values.copy()
            del values[name]
            self.__storage.set(values)
        else:
            raise AttributeError(name)


class LocalStack(t.Generic[T]):
    """Create a stack of context-local data. This wraps a
    :class:`ContextVar` containing a :class:`list` value.

    This may incur a performance penalty compared to using individual
    context vars, as it has to copy data to avoid mutating the list
    between nested contexts.

    :param context_var: The :class:`~contextvars.ContextVar` to use as
        storage for this local. If not given, one will be created.
        Context vars not created at the global scope may interfere with
        garbage collection.

    .. versionchanged:: 2.0
        Uses ``ContextVar`` instead of a custom storage implementation.

    .. versionadded:: 0.6.1
    """

    __slots__ = ("_storage",)

    def __init__(self, context_var: ContextVar[list[T]] | None = None) -> None:
        if context_var is None:
            # A ContextVar not created at global scope interferes with
            # Python's garbage collection. However, a local only makes
            # sense defined at the global scope as well, in which case
            # the GC issue doesn't seem relevant.
            context_var = ContextVar(f"werkzeug.LocalStack<{id(self)}>.storage")

        self._storage = context_var

    def __release_local__(self) -> None:
        self._storage.set([])

    def push(self, obj: T) -> list[T]:
        """Add a new item to the top of the stack."""
        stack = self._storage.get([]).copy()
        stack.append(obj)
        self._storage.set(stack)
        return stack

    def pop(self) -> T | None:
        """Remove the top item from the stack and return it. If the
        stack is empty, return ``None``.
        """
        stack = self._storage.get([])

        if len(stack) == 0:
            return None

        rv = stack[-1]
        self._storage.set(stack[:-1])
        return rv

    @property
    def top(self) -> T | None:
        """The topmost item on the stack.  If the stack is empty,
        `None` is returned.
        """
        stack = self._storage.get([])

        if len(stack) == 0:
            return None

        return stack[-1]

    def __call__(
        self, name: str | None = None, *, unbound_message: str | None = None
    ) -> LocalProxy[t.Any]:
        """Create a :class:`LocalProxy` that accesses the top of this
        local stack.

        :param name: If given, the proxy access this attribute of the
            top item, rather than the item itself.
        :param unbound_message: The error message that the proxy will
            show if the stack is empty.
        """
        return LocalProxy(self, name, unbound_message=unbound_message)


class LocalManager:
    """Manage releasing the data for the current context in one or more
    :class:`Local` and :class:`LocalStack` objects.

    This should not be needed for modern use cases, and may be removed
    in the future.

    :param locals: A local or list of locals to manage.

    .. versionchanged:: 2.1
        The ``ident_func`` was removed.

    .. versionchanged:: 0.7
        The ``ident_func`` parameter was added.

    .. versionchanged:: 0.6.1
        The :func:`release_local` function can be used instead of a
        manager.
    """

    __slots__ = ("locals",)

    def __init__(
        self,
        locals: None
        | (Local | LocalStack[t.Any] | t.Iterable[Local | LocalStack[t.Any]]) = None,
    ) -> None:
        if locals is None:
            self.locals = []
        elif isinstance(locals, Local):
            self.locals = [locals]
        else:
            self.locals = list(locals)  # type: ignore[arg-type]

    def cleanup(self) -> None:
        """Release the data in the locals for this context. Call this at
        the end of each request or use :meth:`make_middleware`.
        """
        for local in self.locals:
            release_local(local)

    def make_middleware(self, app: WSGIApplication) -> WSGIApplication:
        """Wrap a WSGI application so that local data is released
        automatically after the response has been sent for a request.
        """

        def application(
            environ: WSGIEnvironment, start_response: StartResponse
        ) -> t.Iterable[bytes]:
            return ClosingIterator(app(environ, start_response), self.cleanup)

        return application

    def middleware(self, func: WSGIApplication) -> WSGIApplication:
        """Like :meth:`make_middleware` but used as a decorator on the
        WSGI application function.

        .. code-block:: python

            @manager.middleware
            def application(environ, start_response):
                ...
        """
        return update_wrapper(self.make_middleware(func), func)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} storages: {len(self.locals)}>"


class _ProxyLookup:
    """Descriptor that handles proxied attribute lookup for
    :class:`LocalProxy`.

    :param f: The built-in function this attribute is accessed through.
        Instead of looking up the special method, the function call
        is redone on the object.
    :param fallback: Return this function if the proxy is unbound
        instead of raising a :exc:`RuntimeError`.
    :param is_attr: This proxied name is an attribute, not a function.
        Call the fallback immediately to get the value.
    :param class_value: Value to return when accessed from the
        ``LocalProxy`` class directly. Used for ``__doc__`` so building
        docs still works.
    """

    __slots__ = ("bind_f", "fallback", "is_attr", "class_value", "name")

    def __init__(
        self,
        f: t.Callable[..., t.Any] | None = None,
        fallback: t.Callable[[LocalProxy[t.Any]], t.Any] | None = None,
        class_value: t.Any | None = None,
        is_attr: bool = False,
    ) -> None:
        bind_f: t.Callable[[LocalProxy[t.Any], t.Any], t.Callable[..., t.Any]] | None

        if hasattr(f, "__get__"):
            # A Python function, can be turned into a bound method.

            def bind_f(
                instance: LocalProxy[t.Any], obj: t.Any
            ) -> t.Callable[..., t.Any]:
                return f.__get__(obj, type(obj))  # type: ignore

        elif f is not None:
            # A C function, use partial to bind the first argument.

            def bind_f(
                instance: LocalProxy[t.Any], obj: t.Any
            ) -> t.Callable[..., t.Any]:
                return partial(f, obj)

        else:
            # Use getattr, which will produce a bound method.
            bind_f = None

        self.bind_f = bind_f
        self.fallback = fallback
        self.class_value = class_value
        self.is_attr = is_attr

    def __set_name__(self, owner: LocalProxy[t.Any], name: str) -> None:
        self.name = name

    def __get__(self, instance: LocalProxy[t.Any], owner: type | None = None) -> t.Any:
        if instance is None:
            if self.class_value is not None:
                return self.class_value

            return self

        try:
            obj = instance._get_current_object()
        except RuntimeError:
            if self.fallback is None:
                raise

            fallback = self.fallback.__get__(instance, owner)

            if self.is_attr:
                # __class__ and __doc__ are attributes, not methods.
                # Call the fallback to get the value.
                return fallback()

            return fallback

        if self.bind_f is not None:
            return self.bind_f(instance, obj)

        return getattr(obj, self.name)

    def __repr__(self) -> str:
        return f"proxy {self.name}"

    def __call__(
        self, instance: LocalProxy[t.Any], *args: t.Any, **kwargs: t.Any
    ) -> t.Any:
        """Support calling unbound methods from the class. For example,
        this happens with ``copy.copy``, which does
        ``type(x).__copy__(x)``. ``type(x)`` can't be proxied, so it
        returns the proxy type and descriptor.
        """
        return self.__get__(instance, type(instance))(*args, **kwargs)


class _ProxyIOp(_ProxyLookup):
    """Look up an augmented assignment method on a proxied object. The
    method is wrapped to return the proxy instead of the object.
    """

    __slots__ = ()

    def __init__(
        self,
        f: t.Callable[..., t.Any] | None = None,
        fallback: t.Callable[[LocalProxy[t.Any]], t.Any] | None = None,
    ) -> None:
        super().__init__(f, fallback)

        def bind_f(instance: LocalProxy[t.Any], obj: t.Any) -> t.Callable[..., t.Any]:
            def i_op(self: t.Any, other: t.Any) -> LocalProxy[t.Any]:
                f(self, other)  # type: ignore
                return instance

            return i_op.__get__(obj, type(obj))  # type: ignore

        self.bind_f = bind_f


def _l_to_r_op(op: F) -> F:
    """Swap the argument order to turn an l-op into an r-op."""

    def r_op(obj: t.Any, other: t.Any) -> t.Any:
        return op(other, obj)

    return t.cast(F, r_op)


def _identity(o: T) -> T:
    return o


class LocalProxy(t.Generic[T]):
    """A proxy to the object bound to a context-local object. All
    operations on the proxy are forwarded to the bound object. If no
    object is bound, a ``RuntimeError`` is raised.

    :param local: The context-local object that provides the proxied
        object.
    :param name: Proxy this attribute from the proxied object.
    :param unbound_message: The error message to show if the
        context-local object is unbound.

    Proxy a :class:`~contextvars.ContextVar` to make it easier to
    access. Pass a name to proxy that attribute.

    .. code-block:: python

        _request_var = ContextVar("request")
        request = LocalProxy(_request_var)
        session = LocalProxy(_request_var, "session")

    Proxy an attribute on a :class:`Local` namespace by calling the
    local with the attribute name:

    .. code-block:: python

        data = Local()
        user = data("user")

    Proxy the top item on a :class:`LocalStack` by calling the local.
    Pass a name to proxy that attribute.

    .. code-block::

        app_stack = LocalStack()
        current_app = app_stack()
        g = app_stack("g")

    Pass a function to proxy the return value from that function. This
    was previously used to access attributes of local objects before
    that was supported directly.

    .. code-block:: python

        session = LocalProxy(lambda: request.session)

    ``__repr__`` and ``__class__`` are proxied, so ``repr(x)`` and
    ``isinstance(x, cls)`` will look like the proxied object. Use
    ``issubclass(type(x), LocalProxy)`` to check if an object is a
    proxy.

    .. code-block:: python

        repr(user)  # <User admin>
        isinstance(user, User)  # True
        issubclass(type(user), LocalProxy)  # True

    .. versionchanged:: 2.2.2
        ``__wrapped__`` is set when wrapping an object, not only when
        wrapping a function, to prevent doctest from failing.

    .. versionchanged:: 2.2
        Can proxy a ``ContextVar`` or ``LocalStack`` directly.

    .. versionchanged:: 2.2
        The ``name`` parameter can be used with any proxied object, not
        only ``Local``.

    .. versionchanged:: 2.2
        Added the ``unbound_message`` parameter.

    .. versionchanged:: 2.0
        Updated proxied attributes and methods to reflect the current
        data model.

    .. versionchanged:: 0.6.1
        The class can be instantiated with a callable.
    """

    __slots__ = ("__wrapped", "_get_current_object")

    _get_current_object: t.Callable[[], T]
    """Return the current object this proxy is bound to. If the proxy is
    unbound, this raises a ``RuntimeError``.

    This should be used if you need to pass the object to something that
    doesn't understand the proxy. It can also be useful for performance
    if you are accessing the object multiple times in a function, rather
    than going through the proxy multiple times.
    """

    def __init__(
        self,
        local: ContextVar[T] | Local | LocalStack[T] | t.Callable[[], T],
        name: str | None = None,
        *,
        unbound_message: str | None = None,
    ) -> None:
        if name is None:
            get_name = _identity
        else:
            get_name = attrgetter(name)  # type: ignore[assignment]

        if unbound_message is None:
            unbound_message = "object is not bound"

        if isinstance(local, Local):
            if name is None:
                raise TypeError("'name' is required when proxying a 'Local' object.")

            def _get_current_object() -> T:
                try:
                    return get_name(local)  # type: ignore[return-value]
                except AttributeError:
                    raise RuntimeError(unbound_message) from None

        elif isinstance(local, LocalStack):

            def _get_current_object() -> T:
                obj = local.top

                if obj is None:
                    raise RuntimeError(unbound_message)

                return get_name(obj)

        elif isinstance(local, ContextVar):

            def _get_current_object() -> T:
                try:
                    obj = local.get()
                except LookupError:
                    raise RuntimeError(unbound_message) from None

                return get_name(obj)

        elif callable(local):

            def _get_current_object() -> T:
                return get_name(local())

        else:
            raise TypeError(f"Don't know how to proxy '{type(local)}'.")

        object.__setattr__(self, "_LocalProxy__wrapped", local)
        object.__setattr__(self, "_get_current_object", _get_current_object)

    __doc__ = _ProxyLookup(
        class_value=__doc__, fallback=lambda self: type(self).__doc__, is_attr=True
    )
    __wrapped__ = _ProxyLookup(
        fallback=lambda self: self._LocalProxy__wrapped,  # type: ignore[attr-defined]
        is_attr=True,
    )
    # __del__ should only delete the proxy
    __repr__ = _ProxyLookup(
        repr, fallback=lambda self: f"<{type(self).__name__} unbound>"
    )
    __str__ = _ProxyLookup(str)
    __bytes__ = _ProxyLookup(bytes)
    __format__ = _ProxyLookup()
    __lt__ = _ProxyLookup(operator.lt)
    __le__ = _ProxyLookup(operator.le)
    __eq__ = _ProxyLookup(operator.eq)
    __ne__ = _ProxyLookup(operator.ne)
    __gt__ = _ProxyLookup(operator.gt)
    __ge__ = _ProxyLookup(operator.ge)
    __hash__ = _ProxyLookup(hash)
    __bool__ = _ProxyLookup(bool, fallback=lambda self: False)
    __getattr__ = _ProxyLookup(getattr)
    # __getattribute__ triggered through __getattr__
    __setattr__ = _ProxyLookup(setattr)
    __delattr__ = _ProxyLookup(delattr)
    __dir__ = _ProxyLookup(dir, fallback=lambda self: [])
    # __get__ (proxying descriptor not supported)
    # __set__ (descriptor)
    # __delete__ (descriptor)
    # __set_name__ (descriptor)
    # __objclass__ (descriptor)
    # __slots__ used by proxy itself
    # __dict__ (__getattr__)
    # __weakref__ (__getattr__)
    # __init_subclass__ (proxying metaclass not supported)
    # __prepare__ (metaclass)
    __class__ = _ProxyLookup(fallback=lambda self: type(self), is_attr=True)
    __instancecheck__ = _ProxyLookup(lambda self, other: isinstance(other, self))
    __subclasscheck__ = _ProxyLookup(lambda self, other: issubclass(other, self))
    # __class_getitem__ triggered through __getitem__
    __call__ = _ProxyLookup(lambda self, *args, **kwargs: self(*args, **kwargs))
    __len__ = _ProxyLookup(len)
    __length_hint__ = _ProxyLookup(operator.length_hint)
    __getitem__ = _ProxyLookup(operator.getitem)
    __setitem__ = _ProxyLookup(operator.setitem)
    __delitem__ = _ProxyLookup(operator.delitem)
    # __missing__ triggered through __getitem__
    __iter__ = _ProxyLookup(iter)
    __next__ = _ProxyLookup(next)
    __reversed__ = _ProxyLookup(reversed)
    __contains__ = _ProxyLookup(operator.contains)
    __add__ = _ProxyLookup(operator.add)
    __sub__ = _ProxyLookup(operator.sub)
    __mul__ = _ProxyLookup(operator.mul)
    __matmul__ = _ProxyLookup(operator.matmul)
    __truediv__ = _ProxyLookup(operator.truediv)
    __floordiv__ = _ProxyLookup(operator.floordiv)
    __mod__ = _ProxyLookup(operator.mod)
    __divmod__ = _ProxyLookup(divmod)
    __pow__ = _ProxyLookup(pow)
    __lshift__ = _ProxyLookup(operator.lshift)
    __rshift__ = _ProxyLookup(operator.rshift)
    __and__ = _ProxyLookup(operator.and_)
    __xor__ = _ProxyLookup(operator.xor)
    __or__ = _ProxyLookup(operator.or_)
    __radd__ = _ProxyLookup(_l_to_r_op(operator.add))
    __rsub__ = _ProxyLookup(_l_to_r_op(operator.sub))
    __rmul__ = _ProxyLookup(_l_to_r_op(operator.mul))
    __rmatmul__ = _ProxyLookup(_l_to_r_op(operator.matmul))
    __rtruediv__ = _ProxyLookup(_l_to_r_op(operator.truediv))
    __rfloordiv__ = _ProxyLookup(_l_to_r_op(operator.floordiv))
    __rmod__ = _ProxyLookup(_l_to_r_op(operator.mod))
    __rdivmod__ = _ProxyLookup(_l_to_r_op(divmod))
    __rpow__ = _ProxyLookup(_l_to_r_op(pow))
    __rlshift__ = _ProxyLookup(_l_to_r_op(operator.lshift))
    __rrshift__ = _ProxyLookup(_l_to_r_op(operator.rshift))
    __rand__ = _ProxyLookup(_l_to_r_op(operator.and_))
    __rxor__ = _ProxyLookup(_l_to_r_op(operator.xor))
    __ror__ = _ProxyLookup(_l_to_r_op(operator.or_))
    __iadd__ = _ProxyIOp(operator.iadd)
    __isub__ = _ProxyIOp(operator.isub)
    __imul__ = _ProxyIOp(operator.imul)
    __imatmul__ = _ProxyIOp(operator.imatmul)
    __itruediv__ = _ProxyIOp(operator.itruediv)
    __ifloordiv__ = _ProxyIOp(operator.ifloordiv)
    __imod__ = _ProxyIOp(operator.imod)
    __ipow__ = _ProxyIOp(operator.ipow)
    __ilshift__ = _ProxyIOp(operator.ilshift)
    __irshift__ = _ProxyIOp(operator.irshift)
    __iand__ = _ProxyIOp(operator.iand)
    __ixor__ = _ProxyIOp(operator.ixor)
    __ior__ = _ProxyIOp(operator.ior)
    __neg__ = _ProxyLookup(operator.neg)
    __pos__ = _ProxyLookup(operator.pos)
    __abs__ = _ProxyLookup(abs)
    __invert__ = _ProxyLookup(operator.invert)
    __complex__ = _ProxyLookup(complex)
    __int__ = _ProxyLookup(int)
    __float__ = _ProxyLookup(float)
    __index__ = _ProxyLookup(operator.index)
    __round__ = _ProxyLookup(round)
    __trunc__ = _ProxyLookup(math.trunc)
    __floor__ = _ProxyLookup(math.floor)
    __ceil__ = _ProxyLookup(math.ceil)
    __enter__ = _ProxyLookup()
    __exit__ = _ProxyLookup()
    __await__ = _ProxyLookup()
    __aiter__ = _ProxyLookup()
    __anext__ = _ProxyLookup()
    __aenter__ = _ProxyLookup()
    __aexit__ = _ProxyLookup()
    __copy__ = _ProxyLookup(copy.copy)
    __deepcopy__ = _ProxyLookup(copy.deepcopy)
    # __getnewargs_ex__ (pickle through proxy not supported)
    # __getnewargs__ (pickle)
    # __getstate__ (pickle)
    # __setstate__ (pickle)
    # __reduce__ (pickle)
    # __reduce_ex__ (pickle)
