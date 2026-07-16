"""
Key bindings registry.

A `KeyBindings` object is a container that holds a list of key bindings. It has a
very efficient internal data structure for checking which key bindings apply
for a pressed key.

Typical usage::

    kb = KeyBindings()

    @kb.add(Keys.ControlX, Keys.ControlC, filter=INSERT)
    def handler(event):
        # Handle ControlX-ControlC key sequence.
        pass

It is also possible to combine multiple KeyBindings objects. We do this in the
default key bindings. There are some KeyBindings objects that contain the Emacs
bindings, while others contain the Vi bindings. They are merged together using
`merge_key_bindings`.

We also have a `ConditionalKeyBindings` object that can enable/disable a group of
key bindings at once.


It is also possible to add a filter to a function, before a key binding has
been assigned, through the `key_binding` decorator.::

    # First define a key handler with the `filter`.
    @key_binding(filter=condition)
    def my_key_binding(event):
        ...

    # Later, add it to the key bindings.
    kb.add(Keys.A, my_key_binding)
"""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from inspect import isawaitable
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Hashable,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    cast,
)

from prompt_toolkit.cache import SimpleCache
from prompt_toolkit.filters import FilterOrBool, Never, to_filter
from prompt_toolkit.keys import KEY_ALIASES, Keys

if TYPE_CHECKING:
    # Avoid circular imports.
    from .key_processor import KeyPressEvent

    # The only two return values for a mouse handler (and key bindings) are
    # `None` and `NotImplemented`. For the type checker it's best to annotate
    # this as `object`. (The consumer never expects a more specific instance:
    # checking for NotImplemented can be done using `is NotImplemented`.)
    NotImplementedOrNone = object
    # Other non-working options are:
    # * Optional[Literal[NotImplemented]]
    #      --> Doesn't work, Literal can't take an Any.
    # * None
    #      --> Doesn't work. We can't assign the result of a function that
    #          returns `None` to a variable.
    # * Any
    #      --> Works, but too broad.


__all__ = [
    "NotImplementedOrNone",
    "Binding",
    "KeyBindingsBase",
    "KeyBindings",
    "ConditionalKeyBindings",
    "merge_key_bindings",
    "DynamicKeyBindings",
    "GlobalOnlyKeyBindings",
]

# Key bindings can be regular functions or coroutines.
# In both cases, if they return `NotImplemented`, the UI won't be invalidated.
# This is mainly used in case of mouse move events, to prevent excessive
# repainting during mouse move events.
KeyHandlerCallable = Callable[
    ["KeyPressEvent"],
    Union["NotImplementedOrNone", Coroutine[Any, Any, "NotImplementedOrNone"]],
]


class Binding:
    """
    Key binding: (key sequence + handler + filter).
    (Immutable binding class.)

    :param record_in_macro: When True, don't record this key binding when a
        macro is recorded.
    """

    def __init__(
        self,
        keys: tuple[Keys | str, ...],
        handler: KeyHandlerCallable,
        filter: FilterOrBool = True,
        eager: FilterOrBool = False,
        is_global: FilterOrBool = False,
        save_before: Callable[[KeyPressEvent], bool] = (lambda e: True),
        record_in_macro: FilterOrBool = True,
    ) -> None:
        self.keys = keys
        self.handler = handler
        self.filter = to_filter(filter)
        self.eager = to_filter(eager)
        self.is_global = to_filter(is_global)
        self.save_before = save_before
        self.record_in_macro = to_filter(record_in_macro)

    def call(self, event: KeyPressEvent) -> None:
        result = self.handler(event)

        # If the handler is a coroutine, create an asyncio task.
        if isawaitable(result):
            awaitable = cast(Coroutine[Any, Any, "NotImplementedOrNone"], result)

            async def bg_task() -> None:
                result = await awaitable
                if result != NotImplemented:
                    event.app.invalidate()

            event.app.create_background_task(bg_task())

        elif result != NotImplemented:
            event.app.invalidate()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(keys={self.keys!r}, handler={self.handler!r})"
        )


# Sequence of keys presses.
KeysTuple = Tuple[Union[Keys, str], ...]


class KeyBindingsBase(metaclass=ABCMeta):
    """
    Interface for a KeyBindings.
    """

    @property
    @abstractmethod
    def _version(self) -> Hashable:
        """
        For cache invalidation. - This should increase every time that
        something changes.
        """
        return 0

    @abstractmethod
    def get_bindings_for_keys(self, keys: KeysTuple) -> list[Binding]:
        """
        Return a list of key bindings that can handle these keys.
        (This return also inactive bindings, so the `filter` still has to be
        called, for checking it.)

        :param keys: tuple of keys.
        """
        return []

    @abstractmethod
    def get_bindings_starting_with_keys(self, keys: KeysTuple) -> list[Binding]:
        """
        Return a list of key bindings that handle a key sequence starting with
        `keys`. (It does only return bindings for which the sequences are
        longer than `keys`. And like `get_bindings_for_keys`, it also includes
        inactive bindings.)

        :param keys: tuple of keys.
        """
        return []

    @property
    @abstractmethod
    def bindings(self) -> list[Binding]:
        """
        List of `Binding` objects.
        (These need to be exposed, so that `KeyBindings` objects can be merged
        together.)
        """
        return []

    # `add` and `remove` don't have to be part of this interface.


T = TypeVar("T", bound=Union[KeyHandlerCallable, Binding])


class KeyBindings(KeyBindingsBase):
    """
    A container for a set of key bindings.

    Example usage::

        kb = KeyBindings()

        @kb.add('c-t')
        def _(event):
            print('Control-T pressed')

        @kb.add('c-a', 'c-b')
        def _(event):
            print('Control-A pressed, followed by Control-B')

        @kb.add('c-x', filter=is_searching)
        def _(event):
            print('Control-X pressed')  # Works only if we are searching.

    """

    def __init__(self) -> None:
        self._bindings: list[Binding] = []
        self._get_bindings_for_keys_cache: SimpleCache[KeysTuple, list[Binding]] = (
            SimpleCache(maxsize=10000)
        )
        self._get_bindings_starting_with_keys_cache: SimpleCache[
            KeysTuple, list[Binding]
        ] = SimpleCache(maxsize=1000)
        self.__version = 0  # For cache invalidation.

    def _clear_cache(self) -> None:
        self.__version += 1
        self._get_bindings_for_keys_cache.clear()
        self._get_bindings_starting_with_keys_cache.clear()

    @property
    def bindings(self) -> list[Binding]:
        return self._bindings

    @property
    def _version(self) -> Hashable:
        return self.__version

    def add(
        self,
        *keys: Keys | str,
        filter: FilterOrBool = True,
        eager: FilterOrBool = False,
        is_global: FilterOrBool = False,
        save_before: Callable[[KeyPressEvent], bool] = (lambda e: True),
        record_in_macro: FilterOrBool = True,
    ) -> Callable[[T], T]:
        """
        Decorator for adding a key bindings.

        :param filter: :class:`~prompt_toolkit.filters.Filter` to determine
            when this key binding is active.
        :param eager: :class:`~prompt_toolkit.filters.Filter` or `bool`.
            When True, ignore potential longer matches when this key binding is
            hit. E.g. when there is an active eager key binding for Ctrl-X,
            execute the handler immediately and ignore the key binding for
            Ctrl-X Ctrl-E of which it is a prefix.
        :param is_global: When this key bindings is added to a `Container` or
            `Control`, make it a global (always active) binding.
        :param save_before: Callable that takes an `Event` and returns True if
            we should save the current buffer, before handling the event.
            (That's the default.)
        :param record_in_macro: Record these key bindings when a macro is
            being recorded. (True by default.)
        """
        assert keys

        keys = tuple(_parse_key(k) for k in keys)

        if isinstance(filter, Never):
            # When a filter is Never, it will always stay disabled, so in that
            # case don't bother putting it in the key bindings. It will slow
            # down every key press otherwise.
            def decorator(func: T) -> T:
                return func

        else:

            def decorator(func: T) -> T:
                if isinstance(func, Binding):
                    # We're adding an existing Binding object.
                    self.bindings.append(
                        Binding(
                            keys,
                            func.handler,
                            filter=func.filter & to_filter(filter),
                            eager=to_filter(eager) | func.eager,
                            is_global=to_filter(is_global) | func.is_global,
                            save_before=func.save_before,
                            record_in_macro=func.record_in_macro,
                        )
                    )
                else:
                    self.bindings.append(
                        Binding(
                            keys,
                            cast(KeyHandlerCallable, func),
                            filter=filter,
                            eager=eager,
                            is_global=is_global,
                            save_before=save_before,
                            record_in_macro=record_in_macro,
                        )
                    )
                self._clear_cache()

                return func

        return decorator

    def remove(self, *args: Keys | str | KeyHandlerCallable) -> None:
        """
        Remove a key binding.

        This expects either a function that was given to `add` method as
        parameter or a sequence of key bindings.

        Raises `ValueError` when no bindings was found.

        Usage::

            remove(handler)  # Pass handler.
            remove('c-x', 'c-a')  # Or pass the key bindings.
        """
        found = False

        if callable(args[0]):
            assert len(args) == 1
            function = args[0]

            # Remove the given function.
            for b in self.bindings:
                if b.handler == function:
                    self.bindings.remove(b)
                    found = True

        else:
            assert len(args) > 0
            args = cast(Tuple[Union[Keys, str]], args)

            # Remove this sequence of key bindings.
            keys = tuple(_parse_key(k) for k in args)

            for b in self.bindings:
                if b.keys == keys:
                    self.bindings.remove(b)
                    found = True

        if found:
            self._clear_cache()
        else:
            # No key binding found for this function. Raise ValueError.
            raise ValueError(f"Binding not found: {function!r}")

    # For backwards-compatibility.
    add_binding = add
    remove_binding = remove

    def get_bindings_for_keys(self, keys: KeysTuple) -> list[Binding]:
        """
        Return a list of key bindings that can handle this key.
        (This return also inactive bindings, so the `filter` still has to be
        called, for checking it.)

        :param keys: tuple of keys.
        """

        def get() -> list[Binding]:
            result: list[tuple[int, Binding]] = []

            for b in self.bindings:
                if len(keys) == len(b.keys):
                    match = True
                    any_count = 0

                    for i, j in zip(b.keys, keys):
                        if i != j and i != Keys.Any:
                            match = False
                            break

                        if i == Keys.Any:
                            any_count += 1

                    if match:
                        result.append((any_count, b))

            # Place bindings that have more 'Any' occurrences in them at the end.
            result = sorted(result, key=lambda item: -item[0])

            return [item[1] for item in result]

        return self._get_bindings_for_keys_cache.get(keys, get)

    def get_bindings_starting_with_keys(self, keys: KeysTuple) -> list[Binding]:
        """
        Return a list of key bindings that handle a key sequence starting with
        `keys`. (It does only return bindings for which the sequences are
        longer than `keys`. And like `get_bindings_for_keys`, it also includes
        inactive bindings.)

        :param keys: tuple of keys.
        """

        def get() -> list[Binding]:
            result = []
            for b in self.bindings:
                if len(keys) < len(b.keys):
                    match = True
                    for i, j in zip(b.keys, keys):
                        if i != j and i != Keys.Any:
                            match = False
                            break
                    if match:
                        result.append(b)
            return result

        return self._get_bindings_starting_with_keys_cache.get(keys, get)


def _parse_key(key: Keys | str) -> str | Keys:
    """
    Replace key by alias and verify whether it's a valid one.
    """
    # Already a parse key? -> Return it.
    if isinstance(key, Keys):
        return key

    # Lookup aliases.
    key = KEY_ALIASES.get(key, key)

    # Replace 'space' by ' '
    if key == "space":
        key = " "

    # Return as `Key` object when it's a special key.
    try:
        return Keys(key)
    except ValueError:
        pass

    # Final validation.
    if len(key) != 1:
        raise ValueError(f"Invalid key: {key}")

    return key


def key_binding(
    filter: FilterOrBool = True,
    eager: FilterOrBool = False,
    is_global: FilterOrBool = False,
    save_before: Callable[[KeyPressEvent], bool] = (lambda event: True),
    record_in_macro: FilterOrBool = True,
) -> Callable[[KeyHandlerCallable], Binding]:
    """
    Decorator that turn a function into a `Binding` object. This can be added
    to a `KeyBindings` object when a key binding is assigned.
    """
    assert save_before is None or callable(save_before)

    filter = to_filter(filter)
    eager = to_filter(eager)
    is_global = to_filter(is_global)
    save_before = save_before
    record_in_macro = to_filter(record_in_macro)
    keys = ()

    def decorator(function: KeyHandlerCallable) -> Binding:
        return Binding(
            keys,
            function,
            filter=filter,
            eager=eager,
            is_global=is_global,
            save_before=save_before,
            record_in_macro=record_in_macro,
        )

    return decorator


class _Proxy(KeyBindingsBase):
    """
    Common part for ConditionalKeyBindings and _MergedKeyBindings.
    """

    def __init__(self) -> None:
        # `KeyBindings` to be synchronized with all the others.
        self._bindings2: KeyBindingsBase = KeyBindings()
        self._last_version: Hashable = ()

    def _update_cache(self) -> None:
        """
        If `self._last_version` is outdated, then this should update
        the version and `self._bindings2`.
        """
        raise NotImplementedError

    # Proxy methods to self._bindings2.

    @property
    def bindings(self) -> list[Binding]:
        self._update_cache()
        return self._bindings2.bindings

    @property
    def _version(self) -> Hashable:
        self._update_cache()
        return self._last_version

    def get_bindings_for_keys(self, keys: KeysTuple) -> list[Binding]:
        self._update_cache()
        return self._bindings2.get_bindings_for_keys(keys)

    def get_bindings_starting_with_keys(self, keys: KeysTuple) -> list[Binding]:
        self._update_cache()
        return self._bindings2.get_bindings_starting_with_keys(keys)


class ConditionalKeyBindings(_Proxy):
    """
    Wraps around a `KeyBindings`. Disable/enable all the key bindings according to
    the given (additional) filter.::

        @Condition
        def setting_is_true():
            return True  # or False

        registry = ConditionalKeyBindings(key_bindings, setting_is_true)

    When new key bindings are added to this object. They are also
    enable/disabled according to the given `filter`.

    :param registries: List of :class:`.KeyBindings` objects.
    :param filter: :class:`~prompt_toolkit.filters.Filter` object.
    """

    def __init__(
        self, key_bindings: KeyBindingsBase, filter: FilterOrBool = True
    ) -> None:
        _Proxy.__init__(self)

        self.key_bindings = key_bindings
        self.filter = to_filter(filter)

    def _update_cache(self) -> None:
        "If the original key bindings was changed. Update our copy version."
        expected_version = self.key_bindings._version

        if self._last_version != expected_version:
            bindings2 = KeyBindings()

            # Copy all bindings from `self.key_bindings`, adding our condition.
            for b in self.key_bindings.bindings:
                bindings2.bindings.append(
                    Binding(
                        keys=b.keys,
                        handler=b.handler,
                        filter=self.filter & b.filter,
                        eager=b.eager,
                        is_global=b.is_global,
                        save_before=b.save_before,
                        record_in_macro=b.record_in_macro,
                    )
                )

            self._bindings2 = bindings2
            self._last_version = expected_version


class _MergedKeyBindings(_Proxy):
    """
    Merge multiple registries of key bindings into one.

    This class acts as a proxy to multiple :class:`.KeyBindings` objects, but
    behaves as if this is just one bigger :class:`.KeyBindings`.

    :param registries: List of :class:`.KeyBindings` objects.
    """

    def __init__(self, registries: Sequence[KeyBindingsBase]) -> None:
        _Proxy.__init__(self)
        self.registries = registries

    def _update_cache(self) -> None:
        """
        If one of the original registries was changed. Update our merged
        version.
        """
        expected_version = tuple(r._version for r in self.registries)

        if self._last_version != expected_version:
            bindings2 = KeyBindings()

            for reg in self.registries:
                bindings2.bindings.extend(reg.bindings)

            self._bindings2 = bindings2
            self._last_version = expected_version


def merge_key_bindings(bindings: Sequence[KeyBindingsBase]) -> _MergedKeyBindings:
    """
    Merge multiple :class:`.Keybinding` objects together.

    Usage::

        bindings = merge_key_bindings([bindings1, bindings2, ...])
    """
    return _MergedKeyBindings(bindings)


class DynamicKeyBindings(_Proxy):
    """
    KeyBindings class that can dynamically returns any KeyBindings.

    :param get_key_bindings: Callable that returns a :class:`.KeyBindings` instance.
    """

    def __init__(self, get_key_bindings: Callable[[], KeyBindingsBase | None]) -> None:
        self.get_key_bindings = get_key_bindings
        self.__version = 0
        self._last_child_version = None
        self._dummy = KeyBindings()  # Empty key bindings.

    def _update_cache(self) -> None:
        key_bindings = self.get_key_bindings() or self._dummy
        assert isinstance(key_bindings, KeyBindingsBase)
        version = id(key_bindings), key_bindings._version

        self._bindings2 = key_bindings
        self._last_version = version


class GlobalOnlyKeyBindings(_Proxy):
    """
    Wrapper around a :class:`.KeyBindings` object that only exposes the global
    key bindings.
    """

    def __init__(self, key_bindings: KeyBindingsBase) -> None:
        _Proxy.__init__(self)
        self.key_bindings = key_bindings

    def _update_cache(self) -> None:
        """
        If one of the original registries was changed. Update our merged
        version.
        """
        expected_version = self.key_bindings._version

        if self._last_version != expected_version:
            bindings2 = KeyBindings()

            for b in self.key_bindings.bindings:
                if b.is_global():
                    bindings2.bindings.append(b)

            self._bindings2 = bindings2
            self._last_version = expected_version
