import collections
import os
import typing
import warnings
from dataclasses import dataclass

__all__ = ["Config"]


@dataclass(init=False, eq=False, slots=True, kw_only=True, match_args=False)
class Config:
    """The base class for NetworkX configuration.

    There are two ways to use this to create configurations. The recommended way
    is to subclass ``Config`` with docs and annotations.

    >>> class MyConfig(Config):
    ...     '''Breakfast!'''
    ...
    ...     eggs: int
    ...     spam: int
    ...
    ...     def _on_setattr(self, key, value):
    ...         assert isinstance(value, int) and value >= 0
    ...         return value
    >>> cfg = MyConfig(eggs=1, spam=5)

    Another way is to simply pass the initial configuration as keyword arguments to
    the ``Config`` instance:

    >>> cfg1 = Config(eggs=1, spam=5)
    >>> cfg1
    Config(eggs=1, spam=5)

    Once defined, config items may be modified, but can't be added or deleted by default.
    ``Config`` is a ``Mapping``, and can get and set configs via attributes or brackets:

    >>> cfg.eggs = 2
    >>> cfg.eggs
    2
    >>> cfg["spam"] = 42
    >>> cfg["spam"]
    42

    For convenience, it can also set configs within a context with the "with" statement:

    >>> with cfg(spam=3):
    ...     print("spam (in context):", cfg.spam)
    spam (in context): 3
    >>> print("spam (after context):", cfg.spam)
    spam (after context): 42

    Subclasses may also define ``_on_setattr`` (as done in the example above)
    to ensure the value being assigned is valid:

    >>> cfg.spam = -1
    Traceback (most recent call last):
        ...
    AssertionError

    If a more flexible configuration object is needed that allows adding and deleting
    configurations, then pass ``strict=False`` when defining the subclass:

    >>> class FlexibleConfig(Config, strict=False):
    ...     default_greeting: str = "Hello"
    >>> flexcfg = FlexibleConfig()
    >>> flexcfg.name = "Mr. Anderson"
    >>> flexcfg
    FlexibleConfig(default_greeting='Hello', name='Mr. Anderson')
    """

    def __init_subclass__(cls, strict=True):
        cls._strict = strict

    def __new__(cls, **kwargs):
        orig_class = cls
        if cls is Config:
            # Enable the "simple" case of accepting config definition as keywords
            cls = type(
                cls.__name__,
                (cls,),
                {"__annotations__": {key: typing.Any for key in kwargs}},
            )
        cls = dataclass(
            eq=False,
            repr=cls._strict,
            slots=cls._strict,
            kw_only=True,
            match_args=False,
        )(cls)
        if not cls._strict:
            cls.__repr__ = _flexible_repr
        cls._orig_class = orig_class  # Save original class so we can pickle
        cls._prev = None  # Stage previous configs to enable use as context manager
        cls._context_stack = []  # Stack of previous configs when used as context
        instance = object.__new__(cls)
        instance.__init__(**kwargs)
        return instance

    def _on_setattr(self, key, value):
        """Process config value and check whether it is valid. Useful for subclasses."""
        return value

    def _on_delattr(self, key):
        """Callback for when a config item is being deleted. Useful for subclasses."""

    # Control behavior of attributes
    def __dir__(self):
        return self.__dataclass_fields__.keys()

    def __setattr__(self, key, value):
        if self._strict and key not in self.__dataclass_fields__:
            raise AttributeError(f"Invalid config name: {key!r}")
        value = self._on_setattr(key, value)
        object.__setattr__(self, key, value)
        self.__class__._prev = None

    def __delattr__(self, key):
        if self._strict:
            raise TypeError(
                f"Configuration items can't be deleted (can't delete {key!r})."
            )
        self._on_delattr(key)
        object.__delattr__(self, key)
        self.__class__._prev = None

    # Be a `collection.abc.Collection`
    def __contains__(self, key):
        return (
            key in self.__dataclass_fields__ if self._strict else key in self.__dict__
        )

    def __iter__(self):
        return iter(self.__dataclass_fields__ if self._strict else self.__dict__)

    def __len__(self):
        return len(self.__dataclass_fields__ if self._strict else self.__dict__)

    def __reversed__(self):
        return reversed(self.__dataclass_fields__ if self._strict else self.__dict__)

    # Add dunder methods for `collections.abc.Mapping`
    def __getitem__(self, key):
        try:
            return getattr(self, key)
        except AttributeError as err:
            raise KeyError(*err.args) from None

    def __setitem__(self, key, value):
        try:
            self.__setattr__(key, value)
        except AttributeError as err:
            raise KeyError(*err.args) from None

    def __delitem__(self, key):
        try:
            self.__delattr__(key)
        except AttributeError as err:
            raise KeyError(*err.args) from None

    _ipython_key_completions_ = __dir__  # config["<TAB>

    # Go ahead and make it a `collections.abc.Mapping`
    def get(self, key, default=None):
        return getattr(self, key, default)

    def items(self):
        return collections.abc.ItemsView(self)

    def keys(self):
        return collections.abc.KeysView(self)

    def values(self):
        return collections.abc.ValuesView(self)

    # dataclass can define __eq__ for us, but do it here so it works after pickling
    def __eq__(self, other):
        if not isinstance(other, Config):
            return NotImplemented
        return self._orig_class == other._orig_class and self.items() == other.items()

    # Make pickle work
    def __reduce__(self):
        return self._deserialize, (self._orig_class, dict(self))

    @staticmethod
    def _deserialize(cls, kwargs):
        return cls(**kwargs)

    # Allow to be used as context manager
    def __call__(self, **kwargs):
        kwargs = {key: self._on_setattr(key, val) for key, val in kwargs.items()}
        prev = dict(self)
        for key, val in kwargs.items():
            setattr(self, key, val)
        self.__class__._prev = prev
        return self

    def __enter__(self):
        if self.__class__._prev is None:
            raise RuntimeError(
                "Config being used as a context manager without config items being set. "
                "Set config items via keyword arguments when calling the config object. "
                "For example, using config as a context manager should be like:\n\n"
                '    >>> with cfg(breakfast="spam"):\n'
                "    ...     ...  # Do stuff\n"
            )
        self.__class__._context_stack.append(self.__class__._prev)
        self.__class__._prev = None
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        prev = self.__class__._context_stack.pop()
        for key, val in prev.items():
            setattr(self, key, val)


def _flexible_repr(self):
    return (
        f"{self.__class__.__qualname__}("
        + ", ".join(f"{key}={val!r}" for key, val in self.__dict__.items())
        + ")"
    )


# Register, b/c `Mapping.__subclasshook__` returns `NotImplemented`
collections.abc.Mapping.register(Config)


class BackendPriorities(Config, strict=False):
    """Configuration to control automatic conversion to and calling of backends.

    Priority is given to backends listed earlier.

    Parameters
    ----------
    algos : list of backend names
        This controls "algorithms" such as ``nx.pagerank`` that don't return a graph.
    generators : list of backend names
        This controls "generators" such as ``nx.from_pandas_edgelist`` that return a graph.
    kwargs : variadic keyword arguments of function name to list of backend names
        This allows each function to be configured separately and will override the config
        in ``algos`` or ``generators`` if present. The dispatchable function name may be
        gotten from the ``.name`` attribute such as ``nx.pagerank.name`` (it's typically
        the same as the name of the function).
    """

    algos: list[str]
    generators: list[str]

    def _on_setattr(self, key, value):
        from .backends import _registered_algorithms, backend_info

        if key in {"algos", "generators"}:
            pass
        elif key not in _registered_algorithms:
            raise AttributeError(
                f"Invalid config name: {key!r}. Expected 'algos', 'generators', or a name "
                "of a dispatchable function (e.g. `.name` attribute of the function)."
            )
        if not (isinstance(value, list) and all(isinstance(x, str) for x in value)):
            raise TypeError(
                f"{key!r} config must be a list of backend names; got {value!r}"
            )
        if missing := {x for x in value if x not in backend_info}:
            missing = ", ".join(map(repr, sorted(missing)))
            raise ValueError(f"Unknown backend when setting {key!r}: {missing}")
        return value

    def _on_delattr(self, key):
        if key in {"algos", "generators"}:
            raise TypeError(f"{key!r} configuration item can't be deleted.")


class NetworkXConfig(Config):
    """Configuration for NetworkX that controls behaviors such as how to use backends.

    Attribute and bracket notation are supported for getting and setting configurations::

        >>> nx.config.backend_priority == nx.config["backend_priority"]
        True

    Parameters
    ----------
    backend_priority : list of backend names or dict or BackendPriorities
        Enable automatic conversion of graphs to backend graphs for functions
        implemented by the backend. Priority is given to backends listed earlier.
        This is a nested configuration with keys ``algos``, ``generators``, and,
        optionally, function names. Setting this value to a list of backend names
        will set ``nx.config.backend_priority.algos``. For more information, see
        ``help(nx.config.backend_priority)``. Default is empty list.

    backends : Config mapping of backend names to backend Config
        The keys of the Config mapping are names of all installed NetworkX backends,
        and the values are their configurations as Config mappings.

    cache_converted_graphs : bool
        If True, then save converted graphs to the cache of the input graph. Graph
        conversion may occur when automatically using a backend from `backend_priority`
        or when using the `backend=` keyword argument to a function call. Caching can
        improve performance by avoiding repeated conversions, but it uses more memory.
        Care should be taken to not manually mutate a graph that has cached graphs; for
        example, ``G[u][v][k] = val`` changes the graph, but does not clear the cache.
        Using methods such as ``G.add_edge(u, v, weight=val)`` will clear the cache to
        keep it consistent. ``G.__networkx_cache__.clear()`` manually clears the cache.
        Default is True.

    fallback_to_nx : bool
        If True, then "fall back" and run with the default "networkx" implementation
        for dispatchable functions not implemented by backends of input graphs. When a
        backend graph is passed to a dispatchable function, the default behavior is to
        use the implementation from that backend if possible and raise if not. Enabling
        ``fallback_to_nx`` makes the networkx implementation the fallback to use instead
        of raising, and will convert the backend graph to a networkx-compatible graph.
        Default is False.

    warnings_to_ignore : set of strings
        Control which warnings from NetworkX are not emitted. Valid elements:

        - `"cache"`: when a cached value is used from ``G.__networkx_cache__``.

    Notes
    -----
    Environment variables may be used to control some default configurations:

    - ``NETWORKX_BACKEND_PRIORITY``: set ``backend_priority.algos`` from comma-separated names.
    - ``NETWORKX_CACHE_CONVERTED_GRAPHS``: set ``cache_converted_graphs`` to True if nonempty.
    - ``NETWORKX_FALLBACK_TO_NX``: set ``fallback_to_nx`` to True if nonempty.
    - ``NETWORKX_WARNINGS_TO_IGNORE``: set `warnings_to_ignore` from comma-separated names.

    and can be used for finer control of ``backend_priority`` such as:

    - ``NETWORKX_BACKEND_PRIORITY_ALGOS``: same as ``NETWORKX_BACKEND_PRIORITY`` to set ``backend_priority.algos``.

    This is a global configuration. Use with caution when using from multiple threads.
    """

    backend_priority: BackendPriorities
    backends: Config
    cache_converted_graphs: bool
    fallback_to_nx: bool
    warnings_to_ignore: set[str]

    def _on_setattr(self, key, value):
        from .backends import backend_info

        if key == "backend_priority":
            if isinstance(value, list):
                getattr(self, key).algos = value
                value = getattr(self, key)
            elif isinstance(value, dict):
                kwargs = value
                value = BackendPriorities(algos=[], generators=[])
                for key, val in kwargs.items():
                    setattr(value, key, val)
            elif not isinstance(value, BackendPriorities):
                raise TypeError(
                    f"{key!r} config must be a dict of lists of backend names; got {value!r}"
                )
        elif key == "backends":
            if not (
                isinstance(value, Config)
                and all(isinstance(key, str) for key in value)
                and all(isinstance(val, Config) for val in value.values())
            ):
                raise TypeError(
                    f"{key!r} config must be a Config of backend configs; got {value!r}"
                )
            if missing := {x for x in value if x not in backend_info}:
                missing = ", ".join(map(repr, sorted(missing)))
                raise ValueError(f"Unknown backend when setting {key!r}: {missing}")
        elif key in {"cache_converted_graphs", "fallback_to_nx"}:
            if not isinstance(value, bool):
                raise TypeError(f"{key!r} config must be True or False; got {value!r}")
        elif key == "warnings_to_ignore":
            if not (isinstance(value, set) and all(isinstance(x, str) for x in value)):
                raise TypeError(
                    f"{key!r} config must be a set of warning names; got {value!r}"
                )
            known_warnings = {"cache"}
            if missing := {x for x in value if x not in known_warnings}:
                missing = ", ".join(map(repr, sorted(missing)))
                raise ValueError(
                    f"Unknown warning when setting {key!r}: {missing}. Valid entries: "
                    + ", ".join(sorted(known_warnings))
                )
        return value
