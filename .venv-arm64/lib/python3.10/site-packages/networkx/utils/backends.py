"""
Docs for backend users
~~~~~~~~~~~~~~~~~~~~~~
NetworkX utilizes a plugin-dispatch architecture. A valid NetworkX backend
specifies `entry points
<https://packaging.python.org/en/latest/specifications/entry-points>`_, named
``networkx.backends`` and an optional ``networkx.backend_info`` when it is
installed (not imported). This allows NetworkX to dispatch (redirect) function
calls to the backend so the execution flows to the designated backend
implementation. This design enhances flexibility and integration, making
NetworkX more adaptable and efficient.

NetworkX can dispatch to backends **explicitly** (this requires changing code)
or **automatically** (this requires setting configuration or environment
variables). The best way to use a backend depends on the backend, your use
case, and whether you want to automatically convert to or from backend
graphs. Automatic conversions of graphs is always opt-in.

To explicitly dispatch to a backend, use the `backend=` keyword argument in a
dispatchable function. This will convert (and cache by default) input NetworkX
graphs to backend graphs and call the backend implementation. Another explicit
way to use a backend is to create a backend graph directly--for example,
perhaps the backend has its own functions for loading data and creating
graphs--and pass that graph to a dispatchable function, which will then call
the backend implementation without converting.

Using automatic dispatch requires setting configuration options. Every NetworkX
configuration may also be set from an environment variable and are processed at
the time networkx is imported.  The following configuration variables are
supported:

* ``nx.config.backend_priority`` (``NETWORKX_BACKEND_PRIORITY`` env var), a
  list of backends, controls dispatchable functions that don't return graphs
  such as e.g. ``nx.pagerank``. When one of these functions is called with
  NetworkX graphs as input, the dispatcher iterates over the backends listed in
  this backend_priority config and will use the first backend that implements
  this function. The input NetworkX graphs are converted (and cached by
  default) to backend graphs. Using this configuration can allow you to use the
  full flexibility of NetworkX graphs and the performance of backend
  implementations, but possible downsides are that creating NetworkX graphs,
  converting to backend graphs, and caching backend graphs may all be
  expensive.

* ``nx.config.backend_priority.algos`` (``NETWORKX_BACKEND_PRIORITY_ALGOS`` env
  var), can be used instead of ``nx.config.backend_priority``
  (``NETWORKX_BACKEND_PRIORITY`` env var) to emphasize that the setting only
  affects the dispatching of algorithm functions as described above.

* ``nx.config.backend_priority.generators``
  (``NETWORKX_BACKEND_PRIORITY_GENERATORS`` env var), a list of backends,
  controls dispatchable functions that return graphs such as
  nx.from_pandas_edgelist and nx.empty_graph. When one of these functions is
  called, the first backend listed in this backend_priority config that
  implements this function will be used and will return a backend graph. When
  this backend graph is passed to other dispatchable NetworkX functions, it
  will use the backend implementation if it exists or raise by default unless
  nx.config.fallback_to_nx is True (default is False). Using this configuration
  avoids creating NetworkX graphs, which subsequently avoids the need to
  convert to and cache backend graphs as when using
  nx.config.backend_priority.algos, but possible downsides are that the backend
  graph may not behave the same as a NetworkX graph and the backend may not
  implement all algorithms that you use, which may break your workflow.

* ``nx.config.fallback_to_nx`` (``NETWORKX_FALLBACK_TO_NX`` env var), a boolean
  (default False), controls what happens when a backend graph is passed to a
  dispatchable function that is not implemented by that backend. The default
  behavior when False is to raise. If True, then the backend graph will be
  converted (and cached by default) to a NetworkX graph and will run with the
  default NetworkX implementation. Enabling this configuration can allow
  workflows to complete if the backend does not implement all algorithms used
  by the workflow, but a possible downside is that it may require converting
  the input backend graph to a NetworkX graph, which may be expensive. If a
  backend graph is duck-type compatible as a NetworkX graph, then the backend
  may choose not to convert to a NetworkX graph and use the incoming graph
  as-is.

* ``nx.config.cache_converted_graphs`` (``NETWORKX_CACHE_CONVERTED_GRAPHS`` env
  var), a boolean (default True), controls whether graph conversions are cached
  to G.__networkx_cache__ or not. Caching can improve performance by avoiding
  repeated conversions, but it uses more memory.

.. note:: Backends *should* follow the NetworkX backend naming convention. For
   example, if a backend is named ``parallel`` and specified using
   ``backend=parallel`` or ``NETWORKX_BACKEND_PRIORITY=parallel``, the package
   installed is ``nx-parallel``, and we would use ``import nx_parallel`` if we
   were to import the backend package directly.

Backends are encouraged to document how they recommend to be used and whether
their graph types are duck-type compatible as NetworkX graphs. If backend
graphs are NetworkX-compatible and you want your workflow to automatically
"just work" with a backend--converting and caching if necessary--then use all
of the above configurations. Automatically converting graphs is opt-in, and
configuration gives the user control.

Examples:
---------

Use the ``cugraph`` backend for every algorithm function it supports. This will
allow for fall back to the default NetworkX implementations for algorithm calls
not supported by cugraph because graph generator functions are still returning
NetworkX graphs.

.. code-block:: bash

   bash> NETWORKX_BACKEND_PRIORITY=cugraph python my_networkx_script.py

Explicitly use the ``parallel`` backend for a function call.

.. code-block:: python

    nx.betweenness_centrality(G, k=10, backend="parallel")

Explicitly use the ``parallel`` backend for a function call by passing an
instance of the backend graph type to the function.

.. code-block:: python

   H = nx_parallel.ParallelGraph(G)
   nx.betweenness_centrality(H, k=10)

Explicitly use the ``parallel`` backend and pass additional backend-specific
arguments. Here, ``get_chunks`` is an argument unique to the ``parallel``
backend.

.. code-block:: python

   nx.betweenness_centrality(G, k=10, backend="parallel", get_chunks=get_chunks)

Automatically dispatch the ``cugraph`` backend for all NetworkX algorithms and
generators, and allow the backend graph object returned from generators to be
passed to NetworkX functions the backend does not support.

.. code-block:: bash

   bash> NETWORKX_BACKEND_PRIORITY_ALGOS=cugraph \\
         NETWORKX_BACKEND_PRIORITY_GENERATORS=cugraph \\
         NETWORKX_FALLBACK_TO_NX=True \\
         python my_networkx_script.py

How does this work?
-------------------

If you've looked at functions in the NetworkX codebase, you might have seen the
``@nx._dispatchable`` decorator on most of the functions. This decorator allows the NetworkX
function to dispatch to the corresponding backend function if available. When the decorated
function is called, it first checks for a backend to run the function, and if no appropriate
backend is specified or available, it runs the NetworkX version of the function.

Backend Keyword Argument
^^^^^^^^^^^^^^^^^^^^^^^^

When a decorated function is called with the ``backend`` kwarg provided, it checks
if the specified backend is installed, and loads it. Next it checks whether to convert
input graphs by first resolving the backend of each input graph by looking
for an attribute named ``__networkx_backend__`` that holds the backend name for that
graph type. If all input graphs backend matches the ``backend`` kwarg, the backend's
function is called with the original inputs. If any of the input graphs do not match
the ``backend`` kwarg, they are converted to the backend graph type before calling.
Exceptions are raised if any step is not possible, e.g. if the backend does not
implement this function.

Finding a Backend
^^^^^^^^^^^^^^^^^

When a decorated function is called without a ``backend`` kwarg, it tries to find a
dispatchable backend function.
The backend type of each input graph parameter is resolved (using the
``__networkx_backend__`` attribute) and if they all agree, that backend's function
is called if possible. Otherwise the backends listed in the config ``backend_priority``
are considered one at a time in order. If that backend supports the function and
can convert the input graphs to its backend type, that backend function is called.
Otherwise the next backend is considered.

During this process, the backends can provide helpful information to the dispatcher
via helper methods in the backend's interface. Backend methods ``can_run`` and
``should_run`` are used by the dispatcher to determine whether to use the backend
function. If the number of nodes is small, it might be faster to run the NetworkX
version of the function. This is how backends can provide info about whether to run.

Falling Back to NetworkX
^^^^^^^^^^^^^^^^^^^^^^^^

If none of the backends are appropriate, we "fall back" to the NetworkX function.
That means we resolve the backends of all input graphs and if all are NetworkX
graphs we call the NetworkX function. If any are not NetworkX graphs, we raise
an exception unless the `fallback_to_nx` config is set. If it is, we convert all
graph types to NetworkX graph types before calling the NetworkX function.

Functions that mutate the graph
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Any function decorated with the option that indicates it mutates the graph goes through
a slightly different path to automatically find backends. These functions typically
generate a graph, or add attributes or change the graph structure. The config
`backend_priority.generators` holds a list of backend names similar to the config
`backend_priority`. The process is similar for finding a matching backend. Once found,
the backend function is called and a backend graph is returned (instead of a NetworkX
graph). You can then use this backend graph in any function supported by the backend.
And you can use it for functions not supported by the backend if you set the config
`fallback_to_nx` to allow it to convert the backend graph to a NetworkX graph before
calling the function.

Optional keyword arguments
^^^^^^^^^^^^^^^^^^^^^^^^^^

Backends can add optional keyword parameters to NetworkX functions to allow you to
control aspects of the backend algorithm. Thus the function signatures can be extended
beyond the NetworkX function signature. For example, the ``parallel`` backend might
have a parameter to specify how many CPUs to use. These parameters are collected
by the dispatchable decorator code at the start of the function call and used when
calling the backend function.

Existing Backends
^^^^^^^^^^^^^^^^^

NetworkX does not know all the backends that have been created.  In fact, the
NetworkX library does not need to know that a backend exists for it to work. As
long as the backend package creates the ``entry_point``, and provides the
correct interface, it will be called when the user requests it using one of the
three approaches described above. Some backends have been working with the
NetworkX developers to ensure smooth operation.

Refer to the :doc:`/backends` section to see a list of available backends known
to work with the current stable release of NetworkX.

.. _introspect:

Introspection and Logging
-------------------------
Introspection techniques aim to demystify dispatching and backend graph conversion behaviors.

The primary way to see what the dispatch machinery is doing is by enabling logging.
This can help you verify that the backend you specified is being used.
You can enable NetworkX's backend logger to print to ``sys.stderr`` like this::

    import logging
    nxl = logging.getLogger("networkx")
    nxl.addHandler(logging.StreamHandler())
    nxl.setLevel(logging.DEBUG)

And you can disable it by running this::

    nxl.setLevel(logging.CRITICAL)

Refer to :external+python:mod:`logging` to learn more about the logging facilities in Python.

By looking at the ``.backends`` attribute, you can get the set of all currently
installed backends that implement a particular function. For example::

    >>> nx.betweenness_centrality.backends  # doctest: +SKIP
    {'parallel'}

The function docstring will also show which installed backends support it
along with any backend-specific notes and keyword arguments::

    >>> help(nx.betweenness_centrality)  # doctest: +SKIP
    ...
    Backends
    --------
    parallel : Parallel backend for NetworkX algorithms
      The parallel computation is implemented by dividing the nodes into chunks
      and computing betweenness centrality for each chunk concurrently.
    ...

The NetworkX documentation website also includes info about trusted backends of NetworkX in function references.
For example, see :func:`~networkx.algorithms.shortest_paths.weighted.all_pairs_bellman_ford_path_length`.

Introspection capabilities are currently limited, but we are working to improve them.
We plan to make it easier to answer questions such as:

- What happened (and why)?
- What *will* happen (and why)?
- Where was time spent (including conversions)?
- What is in the cache and how much memory is it using?

Transparency is essential to allow for greater understanding, debug-ability,
and customization. After all, NetworkX dispatching is extremely flexible and can
support advanced workflows with multiple backends and fine-tuned configuration,
but introspection can be helpful by describing *when* and *how* to evolve your workflow
to meet your needs. If you have suggestions for how to improve introspection, please
`let us know <https://github.com/networkx/networkx/issues/new>`_!

Docs for backend developers
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Creating a custom backend
-------------------------

1.  Defining a ``BackendInterface`` object:

    Note that the ``BackendInterface`` doesn't need to must be a class. It can be an
    instance of a class, or a module as well. You can define the following methods or
    functions in your backend's ``BackendInterface`` object.:

    1. ``convert_from_nx`` and ``convert_to_nx`` methods or functions are required for
       backend dispatching to work. The arguments to ``convert_from_nx`` are:

       - ``G`` : NetworkX Graph
       - ``edge_attrs`` : dict, optional
            Dictionary mapping edge attributes to default values if missing in ``G``.
            If None, then no edge attributes will be converted and default may be 1.
       - ``node_attrs``: dict, optional
            Dictionary mapping node attributes to default values if missing in ``G``.
            If None, then no node attributes will be converted.
       - ``preserve_edge_attrs`` : bool
            Whether to preserve all edge attributes.
       - ``preserve_node_attrs`` : bool
            Whether to preserve all node attributes.
       - ``preserve_graph_attrs`` : bool
            Whether to preserve all graph attributes.
       - ``preserve_all_attrs`` : bool
            Whether to preserve all graph, node, and edge attributes.
       - ``name`` : str
            The name of the algorithm.
       - ``graph_name`` : str
            The name of the graph argument being converted.

    2. ``can_run`` (Optional):
          If your backend only partially implements an algorithm, you can define
          a ``can_run(name, args, kwargs)`` function in your ``BackendInterface`` object that
          returns True or False indicating whether the backend can run the algorithm with
          the given arguments or not. Instead of a boolean you can also return a string
          message to inform the user why that algorithm can't be run.

    3. ``should_run`` (Optional):
          A backend may also define ``should_run(name, args, kwargs)``
          that is similar to ``can_run``, but answers whether the backend *should* be run.
          ``should_run`` is only run when performing backend graph conversions. Like
          ``can_run``, it receives the original arguments so it can decide whether it
          should be run by inspecting the arguments. ``can_run`` runs before
          ``should_run``, so ``should_run`` may assume ``can_run`` is True. If not
          implemented by the backend, ``can_run``and ``should_run`` are assumed to
          always return True if the backend implements the algorithm.

    4. ``on_start_tests`` (Optional):
          A special ``on_start_tests(items)`` function may be defined by the backend.
          It will be called with the list of NetworkX tests discovered. Each item
          is a test object that can be marked as xfail if the backend does not support
          the test using ``item.add_marker(pytest.mark.xfail(reason=...))``.

2.  Adding entry points

    To be discoverable by NetworkX, your package must register an
    `entry-point <https://packaging.python.org/en/latest/specifications/entry-points>`_
    ``networkx.backends`` in the package's metadata, with a `key pointing to your
    dispatch object <https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/#using-package-metadata>`_ .
    For example, if you are using ``setuptools`` to manage your backend package,
    you can `add the following to your pyproject.toml file <https://setuptools.pypa.io/en/latest/userguide/entry_point.html>`_::

        [project.entry-points."networkx.backends"]
        backend_name = "your_backend_interface_object"

    You can also add the ``backend_info`` entry-point. It points towards the ``get_info``
    function that returns all the backend information, which is then used to build the
    "Additional Backend Implementation" box at the end of algorithm's documentation
    page. Note that the `get_info` function shouldn't import your backend package.::

        [project.entry-points."networkx.backend_info"]
        backend_name = "your_get_info_function"

    The ``get_info`` should return a dictionary with following key-value pairs:
        - ``backend_name`` : str or None
            It is the name passed in the ``backend`` kwarg.
        - ``project`` : str or None
            The name of your backend project.
        - ``package`` : str or None
            The name of your backend package.
        - ``url`` : str or None
            This is the url to either your backend's codebase or documentation, and
            will be displayed as a hyperlink to the ``backend_name``, in the
            "Additional backend implementations" section.
        - ``short_summary`` : str or None
            One line summary of your backend which will be displayed in the
            "Additional backend implementations" section.
        - ``default_config`` : dict
            A dictionary mapping the backend config parameter names to their default values.
            This is used to automatically initialize the default configs for all the
            installed backends at the time of networkx's import.

            .. seealso:: `~networkx.utils.configs.Config`

        - ``functions`` : dict or None
            A dictionary mapping function names to a dictionary of information
            about the function. The information can include the following keys:

            - ``url`` : str or None
              The url to ``function``'s source code or documentation.
            - ``additional_docs`` : str or None
              A short description or note about the backend function's
              implementation.
            - ``additional_parameters`` : dict or None
              A dictionary mapping additional parameters headers to their
              short descriptions. For example::

                  "additional_parameters": {
                      'param1 : str, function (default = "chunks")' : "...",
                      'param2 : int' : "...",
                  }

            If any of these keys are not present, the corresponding information
            will not be displayed in the "Additional backend implementations"
            section on NetworkX docs website.

        Note that your backend's docs would only appear on the official NetworkX docs only
        if your backend is a trusted backend of NetworkX, and is present in the
        `.circleci/config.yml` and `.github/workflows/deploy-docs.yml` files in the
        NetworkX repository.

3.  Defining a Backend Graph class

    The backend must create an object with an attribute ``__networkx_backend__`` that holds
    a string with the entry point name::

        class BackendGraph:
            __networkx_backend__ = "backend_name"
            ...

    A backend graph instance may have a ``G.__networkx_cache__`` dict to enable
    caching, and care should be taken to clear the cache when appropriate.

Testing the Custom backend
--------------------------

To test your custom backend, you can run the NetworkX test suite on your backend.
This also ensures that the custom backend is compatible with NetworkX's API.
The following steps will help you run the tests:

1. Setting Backend Environment Variables:
    - ``NETWORKX_TEST_BACKEND`` : Setting this to your backend's ``backend_name`` will
      let NetworkX's dispatch machinery to automatically convert a regular NetworkX
      ``Graph``, ``DiGraph``, ``MultiGraph``, etc. to their backend equivalents, using
      ``your_backend_interface_object.convert_from_nx(G, ...)`` function.
    - ``NETWORKX_FALLBACK_TO_NX`` (default=False) : Setting this variable to `True` will
      instruct tests to use a NetworkX ``Graph`` for algorithms not implemented by your
      custom backend. Setting this to `False` will only run the tests for algorithms
      implemented by your custom backend and tests for other algorithms will ``xfail``.

2. Running Tests:
    You can invoke NetworkX tests for your custom backend with the following commands::

        NETWORKX_TEST_BACKEND=<backend_name>
        NETWORKX_FALLBACK_TO_NX=True # or False
        pytest --pyargs networkx

How tests are run?
------------------

1. While dispatching to the backend implementation the ``_convert_and_call`` function
   is used and while testing the ``_convert_and_call_for_tests`` function is used.
   Other than testing it also checks for functions that return numpy scalars, and
   for functions that return graphs it runs the backend implementation and the
   networkx implementation and then converts the backend graph into a NetworkX graph
   and then compares them, and returns the networkx graph. This can be regarded as
   (pragmatic) technical debt. We may replace these checks in the future.

2. Conversions while running tests:
    - Convert NetworkX graphs using ``<your_backend_interface_object>.convert_from_nx(G, ...)`` into
      the backend graph.
    - Pass the backend graph objects to the backend implementation of the algorithm.
    - Convert the result back to a form expected by NetworkX tests using
      ``<your_backend_interface_object>.convert_to_nx(result, ...)``.
    - For nx_loopback, the graph is copied using the dispatchable metadata

3. Dispatchable algorithms that are not implemented by the backend
   will cause a ``pytest.xfail``, when the ``NETWORKX_FALLBACK_TO_NX``
   environment variable is set to ``False``, giving some indication that
   not all tests are running, while avoiding causing an explicit failure.
"""

import inspect
import itertools
import logging
import os
import warnings
from functools import partial
from importlib.metadata import entry_points

import networkx as nx

from .configs import BackendPriorities, Config, NetworkXConfig
from .decorators import argmap

__all__ = ["_dispatchable"]

_logger = logging.getLogger(__name__)


def _do_nothing():
    """This does nothing at all, yet it helps turn `_dispatchable` into functions."""


def _get_backends(group, *, load_and_call=False):
    """
    Retrieve NetworkX ``backends`` and ``backend_info`` from the entry points.

    Parameters
    -----------
    group : str
        The entry_point to be retrieved.
    load_and_call : bool, optional
        If True, load and call the backend. Defaults to False.

    Returns
    --------
    dict
        A dictionary mapping backend names to their respective backend objects.

    Notes
    ------
    If a backend is defined more than once, a warning is issued.
    The `nx_loopback` backend is removed if it exists, as it is only available during testing.
    A warning is displayed if an error occurs while loading a backend.
    """
    items = entry_points(group=group)
    rv = {}
    for ep in items:
        if ep.name in rv:
            warnings.warn(
                f"networkx backend defined more than once: {ep.name}",
                RuntimeWarning,
                stacklevel=2,
            )
        elif load_and_call:
            try:
                rv[ep.name] = ep.load()()
            except Exception as exc:
                warnings.warn(
                    f"Error encountered when loading info for backend {ep.name}: {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )
        else:
            rv[ep.name] = ep
    rv.pop("nx_loopback", None)
    return rv


# Note: "networkx" will be in `backend_info`, but not `backends` or `config.backends`.
# It is valid to use "networkx"` as backend argument and in `config.backend_priority`.
# We may make "networkx" a "proper" backend and have it in `backends` and `config.backends`.
backends = _get_backends("networkx.backends")
backend_info = {}  # fill backend_info after networkx is imported in __init__.py

# Load and cache backends on-demand
_loaded_backends = {}  # type: ignore[var-annotated]
_registered_algorithms = {}


# Get default configuration from environment variables at import time
def _comma_sep_to_list(string):
    return [stripped for x in string.strip().split(",") if (stripped := x.strip())]


def _set_configs_from_environment():
    """Initialize ``config.backend_priority``, load backend_info and config.

    This gets default values from environment variables (see ``nx.config`` for details).
    This function is run at the very end of importing networkx. It is run at this time
    to avoid loading backend_info before the rest of networkx is imported in case a
    backend uses networkx for its backend_info (e.g. subclassing the Config class.)
    """
    # backend_info is defined above as empty dict. Fill it after import finishes.
    backend_info.update(_get_backends("networkx.backend_info", load_and_call=True))
    backend_info.update(
        (backend, {}) for backend in backends.keys() - backend_info.keys()
    )

    # set up config based on backend_info and environment
    config = NetworkXConfig(
        backend_priority=BackendPriorities(
            algos=[],
            generators=[],
        ),
        backends=Config(
            **{
                backend: (
                    cfg
                    if isinstance(cfg := info["default_config"], Config)
                    else Config(**cfg)
                )
                if "default_config" in info
                else Config()
                for backend, info in backend_info.items()
            }
        ),
        cache_converted_graphs=bool(
            os.environ.get("NETWORKX_CACHE_CONVERTED_GRAPHS", True)
        ),
        fallback_to_nx=bool(os.environ.get("NETWORKX_FALLBACK_TO_NX", False)),
        warnings_to_ignore={
            x.strip()
            for x in os.environ.get("NETWORKX_WARNINGS_TO_IGNORE", "").split(",")
            if x.strip()
        },
    )
    backend_info["networkx"] = {}
    type(config.backends).__doc__ = "All installed NetworkX backends and their configs."

    # NETWORKX_BACKEND_PRIORITY is the same as NETWORKX_BACKEND_PRIORITY_ALGOS
    priorities = {
        key[26:].lower(): val
        for key, val in os.environ.items()
        if key.startswith("NETWORKX_BACKEND_PRIORITY_")
    }
    backend_priority = config.backend_priority
    backend_priority.algos = (
        _comma_sep_to_list(priorities.pop("algos"))
        if "algos" in priorities
        else _comma_sep_to_list(
            os.environ.get(
                "NETWORKX_BACKEND_PRIORITY",
                os.environ.get("NETWORKX_AUTOMATIC_BACKENDS", ""),
            )
        )
    )
    backend_priority.generators = _comma_sep_to_list(priorities.pop("generators", ""))
    for key in sorted(priorities):
        backend_priority[key] = _comma_sep_to_list(priorities[key])

    return config


def _always_run(name, args, kwargs):
    return True


def _load_backend(backend_name):
    if backend_name in _loaded_backends:
        return _loaded_backends[backend_name]
    if backend_name not in backends:
        raise ImportError(f"'{backend_name}' backend is not installed")
    rv = _loaded_backends[backend_name] = backends[backend_name].load()
    if not hasattr(rv, "can_run"):
        rv.can_run = _always_run
    if not hasattr(rv, "should_run"):
        rv.should_run = _always_run
    return rv


class _dispatchable:
    _is_testing = False

    class _fallback_to_nx:
        """Class property that returns ``nx.config.fallback_to_nx``."""

        def __get__(self, instance, owner=None):
            warnings.warn(
                "`_dispatchable._fallback_to_nx` is deprecated and will be removed "
                "in NetworkX v3.5. Use `nx.config.fallback_to_nx` instead.",
                category=DeprecationWarning,
                stacklevel=2,
            )
            return nx.config.fallback_to_nx

    # Note that chaining `@classmethod` and `@property` was removed in Python 3.13
    _fallback_to_nx = _fallback_to_nx()  # type: ignore[assignment,misc]

    def __new__(
        cls,
        func=None,
        *,
        name=None,
        graphs="G",
        edge_attrs=None,
        node_attrs=None,
        preserve_edge_attrs=False,
        preserve_node_attrs=False,
        preserve_graph_attrs=False,
        preserve_all_attrs=False,
        mutates_input=False,
        returns_graph=False,
    ):
        """A decorator function that is used to redirect the execution of ``func``
        function to its backend implementation.

        This decorator function dispatches to
        a different backend implementation based on the input graph types, and it also
        manages all the ``backend_kwargs``. Usage can be any of the following decorator
        forms:

        - ``@_dispatchable``
        - ``@_dispatchable()``
        - ``@_dispatchable(name="override_name")``
        - ``@_dispatchable(graphs="graph_var_name")``
        - ``@_dispatchable(edge_attrs="weight")``
        - ``@_dispatchable(graphs={"G": 0, "H": 1}, edge_attrs={"weight": "default"})``
            with 0 and 1 giving the position in the signature function for graph
            objects. When ``edge_attrs`` is a dict, keys are keyword names and values
            are defaults.

        Parameters
        ----------
        func : callable, optional
            The function to be decorated. If ``func`` is not provided, returns a
            partial object that can be used to decorate a function later. If ``func``
            is provided, returns a new callable object that dispatches to a backend
            algorithm based on input graph types.

        name : str, optional
            The name of the algorithm to use for dispatching. If not provided,
            the name of ``func`` will be used. ``name`` is useful to avoid name
            conflicts, as all dispatched algorithms live in a single namespace.
            For example, ``tournament.is_strongly_connected`` had a name conflict
            with the standard ``nx.is_strongly_connected``, so we used
            ``@_dispatchable(name="tournament_is_strongly_connected")``.

        graphs : str or dict or None, default "G"
            If a string, the parameter name of the graph, which must be the first
            argument of the wrapped function. If more than one graph is required
            for the algorithm (or if the graph is not the first argument), provide
            a dict keyed to argument names with argument position as values for each
            graph argument. For example, ``@_dispatchable(graphs={"G": 0, "auxiliary?": 4})``
            indicates the 0th parameter ``G`` of the function is a required graph,
            and the 4th parameter ``auxiliary?`` is an optional graph.
            To indicate that an argument is a list of graphs, do ``"[graphs]"``.
            Use ``graphs=None``, if *no* arguments are NetworkX graphs such as for
            graph generators, readers, and conversion functions.

        edge_attrs : str or dict, optional
            ``edge_attrs`` holds information about edge attribute arguments
            and default values for those edge attributes.
            If a string, ``edge_attrs`` holds the function argument name that
            indicates a single edge attribute to include in the converted graph.
            The default value for this attribute is 1. To indicate that an argument
            is a list of attributes (all with default value 1), use e.g. ``"[attrs]"``.
            If a dict, ``edge_attrs`` holds a dict keyed by argument names, with
            values that are either the default value or, if a string, the argument
            name that indicates the default value.

        node_attrs : str or dict, optional
            Like ``edge_attrs``, but for node attributes.

        preserve_edge_attrs : bool or str or dict, optional
            For bool, whether to preserve all edge attributes.
            For str, the parameter name that may indicate (with ``True`` or a
            callable argument) whether all edge attributes should be preserved
            when converting.
            For dict of ``{graph_name: {attr: default}}``, indicate pre-determined
            edge attributes (and defaults) to preserve for input graphs.

        preserve_node_attrs : bool or str or dict, optional
            Like ``preserve_edge_attrs``, but for node attributes.

        preserve_graph_attrs : bool or set
            For bool, whether to preserve all graph attributes.
            For set, which input graph arguments to preserve graph attributes.

        preserve_all_attrs : bool
            Whether to preserve all edge, node and graph attributes.
            This overrides all the other preserve_*_attrs.

        mutates_input : bool or dict, default False
            For bool, whether the function mutates an input graph argument.
            For dict of ``{arg_name: arg_pos}``, arguments that indicate whether an
            input graph will be mutated, and ``arg_name`` may begin with ``"not "``
            to negate the logic (for example, this is used by ``copy=`` arguments).
            By default, dispatching doesn't convert input graphs to a different
            backend for functions that mutate input graphs.

        returns_graph : bool, default False
            Whether the function can return or yield a graph object. By default,
            dispatching doesn't convert input graphs to a different backend for
            functions that return graphs.
        """
        if func is None:
            return partial(
                _dispatchable,
                name=name,
                graphs=graphs,
                edge_attrs=edge_attrs,
                node_attrs=node_attrs,
                preserve_edge_attrs=preserve_edge_attrs,
                preserve_node_attrs=preserve_node_attrs,
                preserve_graph_attrs=preserve_graph_attrs,
                preserve_all_attrs=preserve_all_attrs,
                mutates_input=mutates_input,
                returns_graph=returns_graph,
            )
        if isinstance(func, str):
            raise TypeError("'name' and 'graphs' must be passed by keyword") from None
        # If name not provided, use the name of the function
        if name is None:
            name = func.__name__

        self = object.__new__(cls)

        # standard function-wrapping stuff
        # __annotations__ not used
        self.__name__ = func.__name__
        # self.__doc__ = func.__doc__  # __doc__ handled as cached property
        self.__defaults__ = func.__defaults__
        # We "magically" add `backend=` keyword argument to allow backend to be specified
        if func.__kwdefaults__:
            self.__kwdefaults__ = {**func.__kwdefaults__, "backend": None}
        else:
            self.__kwdefaults__ = {"backend": None}
        self.__module__ = func.__module__
        self.__qualname__ = func.__qualname__
        self.__dict__.update(func.__dict__)
        self.__wrapped__ = func

        # Supplement docstring with backend info; compute and cache when needed
        self._orig_doc = func.__doc__
        self._cached_doc = None

        self.orig_func = func
        self.name = name
        self.edge_attrs = edge_attrs
        self.node_attrs = node_attrs
        self.preserve_edge_attrs = preserve_edge_attrs or preserve_all_attrs
        self.preserve_node_attrs = preserve_node_attrs or preserve_all_attrs
        self.preserve_graph_attrs = preserve_graph_attrs or preserve_all_attrs
        self.mutates_input = mutates_input
        # Keep `returns_graph` private for now, b/c we may extend info on return types
        self._returns_graph = returns_graph

        if edge_attrs is not None and not isinstance(edge_attrs, str | dict):
            raise TypeError(
                f"Bad type for edge_attrs: {type(edge_attrs)}. Expected str or dict."
            ) from None
        if node_attrs is not None and not isinstance(node_attrs, str | dict):
            raise TypeError(
                f"Bad type for node_attrs: {type(node_attrs)}. Expected str or dict."
            ) from None
        if not isinstance(self.preserve_edge_attrs, bool | str | dict):
            raise TypeError(
                f"Bad type for preserve_edge_attrs: {type(self.preserve_edge_attrs)}."
                " Expected bool, str, or dict."
            ) from None
        if not isinstance(self.preserve_node_attrs, bool | str | dict):
            raise TypeError(
                f"Bad type for preserve_node_attrs: {type(self.preserve_node_attrs)}."
                " Expected bool, str, or dict."
            ) from None
        if not isinstance(self.preserve_graph_attrs, bool | set):
            raise TypeError(
                f"Bad type for preserve_graph_attrs: {type(self.preserve_graph_attrs)}."
                " Expected bool or set."
            ) from None
        if not isinstance(self.mutates_input, bool | dict):
            raise TypeError(
                f"Bad type for mutates_input: {type(self.mutates_input)}."
                " Expected bool or dict."
            ) from None
        if not isinstance(self._returns_graph, bool):
            raise TypeError(
                f"Bad type for returns_graph: {type(self._returns_graph)}."
                " Expected bool."
            ) from None

        if isinstance(graphs, str):
            graphs = {graphs: 0}
        elif graphs is None:
            pass
        elif not isinstance(graphs, dict):
            raise TypeError(
                f"Bad type for graphs: {type(graphs)}. Expected str or dict."
            ) from None
        elif len(graphs) == 0:
            raise KeyError("'graphs' must contain at least one variable name") from None

        # This dict comprehension is complicated for better performance; equivalent shown below.
        self.optional_graphs = set()
        self.list_graphs = set()
        if graphs is None:
            self.graphs = {}
        else:
            self.graphs = {
                self.optional_graphs.add(val := k[:-1]) or val
                if (last := k[-1]) == "?"
                else self.list_graphs.add(val := k[1:-1]) or val
                if last == "]"
                else k: v
                for k, v in graphs.items()
            }
        # The above is equivalent to:
        # self.optional_graphs = {k[:-1] for k in graphs if k[-1] == "?"}
        # self.list_graphs = {k[1:-1] for k in graphs if k[-1] == "]"}
        # self.graphs = {k[:-1] if k[-1] == "?" else k: v for k, v in graphs.items()}

        # Compute and cache the signature on-demand
        self._sig = None

        # Which backends implement this function?
        self.backends = {
            backend
            for backend, info in backend_info.items()
            if "functions" in info and name in info["functions"]
        }

        if name in _registered_algorithms:
            raise KeyError(
                f"Algorithm already exists in dispatch registry: {name}"
            ) from None
        # Use the magic of `argmap` to turn `self` into a function. This does result
        # in small additional overhead compared to calling `_dispatchable` directly,
        # but `argmap` has the magical property that it can stack with other `argmap`
        # decorators "for free". Being a function is better for REPRs and type-checkers.
        self = argmap(_do_nothing)(self)
        _registered_algorithms[name] = self
        return self

    @property
    def __doc__(self):
        """If the cached documentation exists, it is returned.
        Otherwise, the documentation is generated using _make_doc() method,
        cached, and then returned."""

        if (rv := self._cached_doc) is not None:
            return rv
        rv = self._cached_doc = self._make_doc()
        return rv

    @__doc__.setter
    def __doc__(self, val):
        """Sets the original documentation to the given value and resets the
        cached documentation."""

        self._orig_doc = val
        self._cached_doc = None

    @property
    def __signature__(self):
        """Return the signature of the original function, with the addition of
        the `backend` and `backend_kwargs` parameters."""

        if self._sig is None:
            sig = inspect.signature(self.orig_func)
            # `backend` is now a reserved argument used by dispatching.
            # assert "backend" not in sig.parameters
            if not any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                sig = sig.replace(
                    parameters=[
                        *sig.parameters.values(),
                        inspect.Parameter(
                            "backend", inspect.Parameter.KEYWORD_ONLY, default=None
                        ),
                        inspect.Parameter(
                            "backend_kwargs", inspect.Parameter.VAR_KEYWORD
                        ),
                    ]
                )
            else:
                *parameters, var_keyword = sig.parameters.values()
                sig = sig.replace(
                    parameters=[
                        *parameters,
                        inspect.Parameter(
                            "backend", inspect.Parameter.KEYWORD_ONLY, default=None
                        ),
                        var_keyword,
                    ]
                )
            self._sig = sig
        return self._sig

    def __call__(self, /, *args, backend=None, **kwargs):
        """Returns the result of the original function, or the backend function if
        the backend is specified and that backend implements `func`."""

        if not backends:
            # Fast path if no backends are installed
            if backend is not None and backend != "networkx":
                raise ImportError(f"'{backend}' backend is not installed")
            return self.orig_func(*args, **kwargs)

        # Use `backend_name` in this function instead of `backend`.
        # This is purely for aesthetics and to make it easier to search for this
        # variable since "backend" is used in many comments and log/error messages.
        backend_name = backend
        if backend_name is not None and backend_name not in backend_info:
            raise ImportError(f"'{backend_name}' backend is not installed")

        graphs_resolved = {}
        for gname, pos in self.graphs.items():
            if pos < len(args):
                if gname in kwargs:
                    raise TypeError(f"{self.name}() got multiple values for {gname!r}")
                graph = args[pos]
            elif gname in kwargs:
                graph = kwargs[gname]
            elif gname not in self.optional_graphs:
                raise TypeError(
                    f"{self.name}() missing required graph argument: {gname}"
                )
            else:
                continue
            if graph is None:
                if gname not in self.optional_graphs:
                    raise TypeError(
                        f"{self.name}() required graph argument {gname!r} is None; must be a graph"
                    )
            else:
                graphs_resolved[gname] = graph

        # Alternative to the above that does not check duplicated args or missing required graphs.
        # graphs_resolved = {
        #     gname: graph
        #     for gname, pos in self.graphs.items()
        #     if (graph := args[pos] if pos < len(args) else kwargs.get(gname)) is not None
        # }

        # Check if any graph comes from a backend
        if self.list_graphs:
            # Make sure we don't lose values by consuming an iterator
            args = list(args)
            for gname in self.list_graphs & graphs_resolved.keys():
                list_of_graphs = list(graphs_resolved[gname])
                graphs_resolved[gname] = list_of_graphs
                if gname in kwargs:
                    kwargs[gname] = list_of_graphs
                else:
                    args[self.graphs[gname]] = list_of_graphs

            graph_backend_names = {
                getattr(g, "__networkx_backend__", None)
                for gname, g in graphs_resolved.items()
                if gname not in self.list_graphs
            }
            for gname in self.list_graphs & graphs_resolved.keys():
                graph_backend_names.update(
                    getattr(g, "__networkx_backend__", None)
                    for g in graphs_resolved[gname]
                )
        else:
            graph_backend_names = {
                getattr(g, "__networkx_backend__", None)
                for g in graphs_resolved.values()
            }

        backend_priority = nx.config.backend_priority.get(
            self.name,
            nx.config.backend_priority.generators
            if self._returns_graph
            else nx.config.backend_priority.algos,
        )
        if self._is_testing and backend_priority and backend_name is None:
            # Special path if we are running networkx tests with a backend.
            # This even runs for (and handles) functions that mutate input graphs.
            return self._convert_and_call_for_tests(
                backend_priority[0],
                args,
                kwargs,
                fallback_to_nx=nx.config.fallback_to_nx,
            )

        graph_backend_names.discard(None)
        if backend_name is not None:
            # Must run with the given backend.
            # `can_run` only used for better log and error messages.
            # Check `mutates_input` for logging, not behavior.
            blurb = (
                "No other backends will be attempted, because the backend was "
                f"specified with the `backend='{backend_name}'` keyword argument."
            )
            extra_message = (
                f"'{backend_name}' backend raised NotImplementedError when calling "
                f"`{self.name}'. {blurb}"
            )
            if not graph_backend_names or graph_backend_names == {backend_name}:
                # All graphs are backend graphs--no need to convert!
                if self._can_backend_run(backend_name, args, kwargs):
                    return self._call_with_backend(
                        backend_name, args, kwargs, extra_message=extra_message
                    )
                if self._does_backend_have(backend_name):
                    extra = " for the given arguments"
                else:
                    extra = ""
                raise NotImplementedError(
                    f"`{self.name}' is not implemented by '{backend_name}' backend"
                    f"{extra}. {blurb}"
                )
            if self._can_convert(backend_name, graph_backend_names):
                if self._can_backend_run(backend_name, args, kwargs):
                    if self._will_call_mutate_input(args, kwargs):
                        _logger.debug(
                            "`%s' will mutate an input graph. This prevents automatic conversion "
                            "to, and use of, backends listed in `nx.config.backend_priority`. "
                            "Using backend specified by the "
                            "`backend='%s'` keyword argument. This may change behavior by not "
                            "mutating inputs.",
                            self.name,
                            backend_name,
                        )
                        mutations = []
                    else:
                        mutations = None
                    rv = self._convert_and_call(
                        backend_name,
                        graph_backend_names,
                        args,
                        kwargs,
                        extra_message=extra_message,
                        mutations=mutations,
                    )
                    if mutations:
                        for cache, key in mutations:
                            # If the call mutates inputs, then remove all inputs gotten
                            # from cache. We do this after all conversions (and call) so
                            # that a graph can be gotten from a cache multiple times.
                            cache.pop(key, None)
                    return rv
                if self._does_backend_have(backend_name):
                    extra = " for the given arguments"
                else:
                    extra = ""
                raise NotImplementedError(
                    f"`{self.name}' is not implemented by '{backend_name}' backend"
                    f"{extra}. {blurb}"
                )
            if len(graph_backend_names) == 1:
                maybe_s = ""
                graph_backend_names = f"'{next(iter(graph_backend_names))}'"
            else:
                maybe_s = "s"
            raise TypeError(
                f"`{self.name}' is unable to convert graph from backend{maybe_s} "
                f"{graph_backend_names} to '{backend_name}' backend, which was "
                f"specified with the `backend='{backend_name}'` keyword argument. "
                f"{blurb}"
            )

        if self._will_call_mutate_input(args, kwargs):
            # The current behavior for functions that mutate input graphs:
            #
            # 1. If backend is specified by `backend=` keyword, use it (done above).
            # 2. If inputs are from one backend, try to use it.
            # 3. If all input graphs are instances of `nx.Graph`, then run with the
            #    default "networkx" implementation.
            #
            # Do not automatically convert if a call will mutate inputs, because doing
            # so would change behavior. Hence, we should fail if there are multiple input
            # backends or if the input backend does not implement the function. However,
            # we offer a way for backends to circumvent this if they do not implement
            # this function: we will fall back to the default "networkx" implementation
            # without using conversions if all input graphs are subclasses of `nx.Graph`.
            blurb = (
                "conversions between backends (if configured) will not be attempted, "
                "because this may change behavior. You may specify a backend to use "
                "by passing e.g. `backend='networkx'` keyword, but this may also "
                "change behavior by not mutating inputs."
            )
            fallback_blurb = (
                "This call will mutate inputs, so fall back to 'networkx' "
                "backend (without converting) since all input graphs are "
                "instances of nx.Graph and are hopefully compatible.",
            )
            if len(graph_backend_names) == 1:
                [backend_name] = graph_backend_names
                msg_template = (
                    f"Backend '{backend_name}' does not implement `{self.name}'%s. "
                    f"This call will mutate an input, so automatic {blurb}"
                )
                # `can_run` is only used for better log and error messages
                try:
                    if self._can_backend_run(backend_name, args, kwargs):
                        return self._call_with_backend(
                            backend_name,
                            args,
                            kwargs,
                            extra_message=msg_template % " with these arguments",
                        )
                except NotImplementedError as exc:
                    if all(isinstance(g, nx.Graph) for g in graphs_resolved.values()):
                        _logger.debug(
                            "Backend '%s' raised when calling `%s': %s. %s",
                            backend_name,
                            self.name,
                            exc,
                            fallback_blurb,
                        )
                    else:
                        raise
                else:
                    if nx.config.fallback_to_nx and all(
                        # Consider dropping the `isinstance` check here to allow
                        # duck-type graphs, but let's wait for a backend to ask us.
                        isinstance(g, nx.Graph)
                        for g in graphs_resolved.values()
                    ):
                        # Log that we are falling back to networkx
                        _logger.debug(
                            "Backend '%s' can't run `%s'. %s",
                            backend_name,
                            self.name,
                            fallback_blurb,
                        )
                    else:
                        if self._does_backend_have(backend_name):
                            extra = " with these arguments"
                        else:
                            extra = ""
                        raise NotImplementedError(msg_template % extra)
            elif nx.config.fallback_to_nx and all(
                # Consider dropping the `isinstance` check here to allow
                # duck-type graphs, but let's wait for a backend to ask us.
                isinstance(g, nx.Graph)
                for g in graphs_resolved.values()
            ):
                # Log that we are falling back to networkx
                _logger.debug(
                    "`%s' was called with inputs from multiple backends: %s. %s",
                    self.name,
                    graph_backend_names,
                    fallback_blurb,
                )
            else:
                raise RuntimeError(
                    f"`{self.name}' will mutate an input, but it was called with inputs "
                    f"from multiple backends: {graph_backend_names}. Automatic {blurb}"
                )
            # At this point, no backends are available to handle the call with
            # the input graph types, but if the input graphs are compatible
            # nx.Graph instances, fall back to networkx without converting.
            return self.orig_func(*args, **kwargs)

        # We may generalize fallback configuration as e.g. `nx.config.backend_fallback`
        if nx.config.fallback_to_nx or not graph_backend_names:
            # Use "networkx" by default if there are no inputs from backends.
            # For example, graph generators should probably return NetworkX graphs
            # instead of raising NotImplementedError.
            backend_fallback = ["networkx"]
        else:
            backend_fallback = []

        # ##########################
        # # How this behaves today #
        # ##########################
        #
        # The prose below describes the implementation and a *possible* way to
        # generalize "networkx" as "just another backend". The code is structured
        # to perhaps someday support backend-to-backend conversions (including
        # simply passing objects from one backend directly to another backend;
        # the dispatch machinery does not necessarily need to perform conversions),
        # but since backend-to-backend matching is not yet supported, the following
        # code is merely a convenient way to implement dispatch behaviors that have
        # been carefully developed since NetworkX 3.0 and to include falling back
        # to the default NetworkX implementation.
        #
        # The current behavior for functions that don't mutate input graphs:
        #
        # 1. If backend is specified by `backend=` keyword, use it (done above).
        # 2. If input is from a backend other than "networkx", try to use it.
        #    - Note: if present, "networkx" graphs will be converted to the backend.
        # 3. If input is from "networkx" (or no backend), try to use backends from
        #    `backend_priority` before running with the default "networkx" implementation.
        # 4. If configured, "fall back" and run with the default "networkx" implementation.
        #
        # ################################################
        # # How this is implemented and may work someday #
        # ################################################
        #
        # Let's determine the order of backends we should try according
        # to `backend_priority`, `backend_fallback`, and input backends.
        # There are two† dimensions of priorities to consider:
        #   backend_priority > unspecified > backend_fallback
        # and
        #   backend of an input > not a backend of an input
        # These are combined to form five groups of priorities as such:
        #
        #                    input   ~input
        #                  +-------+-------+
        # backend_priority |   1   |   2   |
        #      unspecified |   3   |  N/A  | (if only 1)
        # backend_fallback |   4   |   5   |
        #                  +-------+-------+
        #
        # This matches the behaviors we developed in versions 3.0 to 3.2, it
        # ought to cover virtually all use cases we expect, and I (@eriknw) don't
        # think it can be done any simpler (although it can be generalized further
        # and made to be more complicated to capture 100% of *possible* use cases).
        # Some observations:
        #
        #   1. If an input is in `backend_priority`, it will be used before trying a
        #      backend that is higher priority in `backend_priority` and not an input.
        #   2. To prioritize converting from one backend to another even if both implement
        #      a function, list one in `backend_priority` and one in `backend_fallback`.
        #   3. To disable conversions, set `backend_priority` and `backend_fallback` to [].
        #
        # †: There is actually a third dimension of priorities:
        #        should_run == True > should_run == False
        #    Backends with `can_run == True` and `should_run == False` are tried last.
        #
        seen = set()
        group1 = []  # In backend_priority, and an input
        group2 = []  # In backend_priority, but not an input
        for name in backend_priority:
            if name in seen:
                continue
            seen.add(name)
            if name in graph_backend_names:
                group1.append(name)
            else:
                group2.append(name)
        group4 = []  # In backend_fallback, and an input
        group5 = []  # In backend_fallback, but not an input
        for name in backend_fallback:
            if name in seen:
                continue
            seen.add(name)
            if name in graph_backend_names:
                group4.append(name)
            else:
                group5.append(name)
        # An input, but not in backend_priority or backend_fallback.
        group3 = graph_backend_names - seen
        if len(group3) > 1:
            # `group3` backends are not configured for automatic conversion or fallback.
            # There are at least two issues if this group contains multiple backends:
            #
            #   1. How should we prioritize them? We have no good way to break ties.
            #      Although we could arbitrarily choose alphabetical or left-most,
            #      let's follow the Zen of Python and refuse the temptation to guess.
            #   2. We probably shouldn't automatically convert to these backends,
            #      because we are not configured to do so.
            #
            # (2) is important to allow disabling all conversions by setting both
            # `nx.config.backend_priority` and `nx.config.backend_fallback` to [].
            #
            # If there is a single backend in `group3`, then giving it priority over
            # the fallback backends is what is generally expected. For example, this
            # allows input graphs of `backend_fallback` backends (such as "networkx")
            # to be converted to, and run with, the unspecified backend.
            _logger.debug(
                "Call to `%s' has inputs from multiple backends, %s, that "
                "have no priority set in `nx.config.backend_priority`, "
                "so automatic conversions to "
                "these backends will not be attempted.",
                self.name,
                group3,
            )
            group3 = ()

        try_order = list(itertools.chain(group1, group2, group3, group4, group5))
        if len(try_order) > 1:
            # Should we consider adding an option for more verbose logging?
            # For example, we could explain the order of `try_order` in detail.
            _logger.debug(
                "Call to `%s' has inputs from %s backends, and will try to use "
                "backends in the following order: %s",
                self.name,
                graph_backend_names or "no",
                try_order,
            )
        backends_to_try_again = []
        for is_not_first, backend_name in enumerate(try_order):
            if is_not_first:
                _logger.debug("Trying next backend: '%s'", backend_name)
            try:
                if not graph_backend_names or graph_backend_names == {backend_name}:
                    if self._can_backend_run(backend_name, args, kwargs):
                        return self._call_with_backend(backend_name, args, kwargs)
                elif self._can_convert(
                    backend_name, graph_backend_names
                ) and self._can_backend_run(backend_name, args, kwargs):
                    if self._should_backend_run(backend_name, args, kwargs):
                        rv = self._convert_and_call(
                            backend_name, graph_backend_names, args, kwargs
                        )
                        if (
                            self._returns_graph
                            and graph_backend_names
                            and backend_name not in graph_backend_names
                        ):
                            # If the function has graph inputs and graph output, we try
                            # to make it so the backend of the return type will match the
                            # backend of the input types. In case this is not possible,
                            # let's tell the user that the backend of the return graph
                            # has changed. Perhaps we could try to convert back, but
                            # "fallback" backends for graph generators should typically
                            # be compatible with NetworkX graphs.
                            _logger.debug(
                                "Call to `%s' is returning a graph from a different "
                                "backend! It has inputs from %s backends, but ran with "
                                "'%s' backend and is returning graph from '%s' backend",
                                self.name,
                                graph_backend_names,
                                backend_name,
                                backend_name,
                            )
                        return rv
                    # `should_run` is False, but `can_run` is True, so try again later
                    backends_to_try_again.append(backend_name)
            except NotImplementedError as exc:
                _logger.debug(
                    "Backend '%s' raised when calling `%s': %s",
                    backend_name,
                    self.name,
                    exc,
                )

        # We are about to fail. Let's try backends with can_run=True and should_run=False.
        # This is unlikely to help today since we try to run with "networkx" before this.
        for backend_name in backends_to_try_again:
            _logger.debug(
                "Trying backend: '%s' (ignoring `should_run=False`)", backend_name
            )
            try:
                rv = self._convert_and_call(
                    backend_name, graph_backend_names, args, kwargs
                )
                if (
                    self._returns_graph
                    and graph_backend_names
                    and backend_name not in graph_backend_names
                ):
                    _logger.debug(
                        "Call to `%s' is returning a graph from a different "
                        "backend! It has inputs from %s backends, but ran with "
                        "'%s' backend and is returning graph from '%s' backend",
                        self.name,
                        graph_backend_names,
                        backend_name,
                        backend_name,
                    )
                return rv
            except NotImplementedError as exc:
                _logger.debug(
                    "Backend '%s' raised when calling `%s': %s",
                    backend_name,
                    self.name,
                    exc,
                )
        # As a final effort, we could try to convert and run with `group3` backends
        # that we discarded when `len(group3) > 1`, but let's not consider doing
        # so until there is a reasonable request for it.

        if len(unspecified_backends := graph_backend_names - seen) > 1:
            raise TypeError(
                f"Unable to convert inputs from {graph_backend_names} backends and "
                f"run `{self.name}'. NetworkX is configured to automatically convert "
                f"to {try_order} backends. To remedy this, you may enable automatic "
                f"conversion to {unspecified_backends} backends by adding them to "
                "`nx.config.backend_priority`, or you "
                "may specify a backend to use with the `backend=` keyword argument."
            )
        raise NotImplementedError(
            f"`{self.name}' is not implemented by {try_order} backends. To remedy "
            "this, you may enable automatic conversion to more backends (including "
            "'networkx') by adding them to `nx.config.backend_priority`, "
            "or you may specify a backend to use with "
            "the `backend=` keyword argument."
        )

    def _will_call_mutate_input(self, args, kwargs):
        return (mutates_input := self.mutates_input) and (
            mutates_input is True
            or any(
                # If `mutates_input` begins with "not ", then assume the argument is bool,
                # otherwise treat it as a node or edge attribute if it's not None.
                not (
                    args[arg_pos]
                    if len(args) > arg_pos
                    # This assumes that e.g. `copy=True` is the default
                    else kwargs.get(arg_name[4:], True)
                )
                if arg_name.startswith("not ")
                else (args[arg_pos] if len(args) > arg_pos else kwargs.get(arg_name))
                is not None
                for arg_name, arg_pos in mutates_input.items()
            )
        )

    def _can_convert(self, backend_name, graph_backend_names):
        # Backend-to-backend conversion not supported yet.
        # We can only convert to and from networkx.
        rv = backend_name == "networkx" or graph_backend_names.issubset(
            {"networkx", backend_name}
        )
        if not rv:
            _logger.debug(
                "Unable to convert from %s backends to '%s' backend",
                graph_backend_names,
                backend_name,
            )
        return rv

    def _does_backend_have(self, backend_name):
        """Does the specified backend have this algorithm?"""
        if backend_name == "networkx":
            return True
        # Inspect the backend; don't trust metadata used to create `self.backends`
        backend = _load_backend(backend_name)
        return hasattr(backend, self.name)

    def _can_backend_run(self, backend_name, args, kwargs):
        """Can the specified backend run this algorithm with these arguments?"""
        if backend_name == "networkx":
            return True
        backend = _load_backend(backend_name)
        # `backend.can_run` and `backend.should_run` may return strings that describe
        # why they can't or shouldn't be run.
        if not hasattr(backend, self.name):
            _logger.debug(
                "Backend '%s' does not implement `%s'", backend_name, self.name
            )
            return False
        can_run = backend.can_run(self.name, args, kwargs)
        if isinstance(can_run, str) or not can_run:
            reason = f", because: {can_run}" if isinstance(can_run, str) else ""
            _logger.debug(
                "Backend '%s' can't run `%s` with arguments: %s%s",
                backend_name,
                self.name,
                _LazyArgsRepr(self, args, kwargs),
                reason,
            )
            return False
        return True

    def _should_backend_run(self, backend_name, args, kwargs):
        """Should the specified backend run this algorithm with these arguments?

        Note that this does not check ``backend.can_run``.
        """
        # `backend.can_run` and `backend.should_run` may return strings that describe
        # why they can't or shouldn't be run.
        if backend_name == "networkx":
            return True
        backend = _load_backend(backend_name)
        should_run = backend.should_run(self.name, args, kwargs)
        if isinstance(should_run, str) or not should_run:
            reason = f", because: {should_run}" if isinstance(should_run, str) else ""
            _logger.debug(
                "Backend '%s' shouldn't run `%s` with arguments: %s%s",
                backend_name,
                self.name,
                _LazyArgsRepr(self, args, kwargs),
                reason,
            )
            return False
        return True

    def _convert_arguments(self, backend_name, args, kwargs, *, use_cache, mutations):
        """Convert graph arguments to the specified backend.

        Returns
        -------
        args tuple and kwargs dict
        """
        bound = self.__signature__.bind(*args, **kwargs)
        bound.apply_defaults()
        if not self.graphs:
            bound_kwargs = bound.kwargs
            del bound_kwargs["backend"]
            return bound.args, bound_kwargs
        if backend_name == "networkx":
            # `backend_interface.convert_from_nx` preserves everything
            preserve_edge_attrs = preserve_node_attrs = preserve_graph_attrs = True
        else:
            preserve_edge_attrs = self.preserve_edge_attrs
            preserve_node_attrs = self.preserve_node_attrs
            preserve_graph_attrs = self.preserve_graph_attrs
            edge_attrs = self.edge_attrs
            node_attrs = self.node_attrs
        # Convert graphs into backend graph-like object
        # Include the edge and/or node labels if provided to the algorithm
        if preserve_edge_attrs is False:
            # e.g. `preserve_edge_attrs=False`
            pass
        elif preserve_edge_attrs is True:
            # e.g. `preserve_edge_attrs=True`
            edge_attrs = None
        elif isinstance(preserve_edge_attrs, str):
            if bound.arguments[preserve_edge_attrs] is True or callable(
                bound.arguments[preserve_edge_attrs]
            ):
                # e.g. `preserve_edge_attrs="attr"` and `func(attr=True)`
                # e.g. `preserve_edge_attrs="attr"` and `func(attr=myfunc)`
                preserve_edge_attrs = True
                edge_attrs = None
            elif bound.arguments[preserve_edge_attrs] is False and (
                isinstance(edge_attrs, str)
                and edge_attrs == preserve_edge_attrs
                or isinstance(edge_attrs, dict)
                and preserve_edge_attrs in edge_attrs
            ):
                # e.g. `preserve_edge_attrs="attr"` and `func(attr=False)`
                # Treat `False` argument as meaning "preserve_edge_data=False"
                # and not `False` as the edge attribute to use.
                preserve_edge_attrs = False
                edge_attrs = None
            else:
                # e.g. `preserve_edge_attrs="attr"` and `func(attr="weight")`
                preserve_edge_attrs = False
        # Else: e.g. `preserve_edge_attrs={"G": {"weight": 1}}`

        if edge_attrs is None:
            # May have been set to None above b/c all attributes are preserved
            pass
        elif isinstance(edge_attrs, str):
            if edge_attrs[0] == "[":
                # e.g. `edge_attrs="[edge_attributes]"` (argument of list of attributes)
                # e.g. `func(edge_attributes=["foo", "bar"])`
                edge_attrs = {
                    edge_attr: 1 for edge_attr in bound.arguments[edge_attrs[1:-1]]
                }
            elif callable(bound.arguments[edge_attrs]):
                # e.g. `edge_attrs="weight"` and `func(weight=myfunc)`
                preserve_edge_attrs = True
                edge_attrs = None
            elif bound.arguments[edge_attrs] is not None:
                # e.g. `edge_attrs="weight"` and `func(weight="foo")` (default of 1)
                edge_attrs = {bound.arguments[edge_attrs]: 1}
            elif self.name == "to_numpy_array" and hasattr(
                bound.arguments["dtype"], "names"
            ):
                # Custom handling: attributes may be obtained from `dtype`
                edge_attrs = {
                    edge_attr: 1 for edge_attr in bound.arguments["dtype"].names
                }
            else:
                # e.g. `edge_attrs="weight"` and `func(weight=None)`
                edge_attrs = None
        else:
            # e.g. `edge_attrs={"attr": "default"}` and `func(attr="foo", default=7)`
            # e.g. `edge_attrs={"attr": 0}` and `func(attr="foo")`
            edge_attrs = {
                edge_attr: bound.arguments.get(val, 1) if isinstance(val, str) else val
                for key, val in edge_attrs.items()
                if (edge_attr := bound.arguments[key]) is not None
            }

        if preserve_node_attrs is False:
            # e.g. `preserve_node_attrs=False`
            pass
        elif preserve_node_attrs is True:
            # e.g. `preserve_node_attrs=True`
            node_attrs = None
        elif isinstance(preserve_node_attrs, str):
            if bound.arguments[preserve_node_attrs] is True or callable(
                bound.arguments[preserve_node_attrs]
            ):
                # e.g. `preserve_node_attrs="attr"` and `func(attr=True)`
                # e.g. `preserve_node_attrs="attr"` and `func(attr=myfunc)`
                preserve_node_attrs = True
                node_attrs = None
            elif bound.arguments[preserve_node_attrs] is False and (
                isinstance(node_attrs, str)
                and node_attrs == preserve_node_attrs
                or isinstance(node_attrs, dict)
                and preserve_node_attrs in node_attrs
            ):
                # e.g. `preserve_node_attrs="attr"` and `func(attr=False)`
                # Treat `False` argument as meaning "preserve_node_data=False"
                # and not `False` as the node attribute to use. Is this used?
                preserve_node_attrs = False
                node_attrs = None
            else:
                # e.g. `preserve_node_attrs="attr"` and `func(attr="weight")`
                preserve_node_attrs = False
        # Else: e.g. `preserve_node_attrs={"G": {"pos": None}}`

        if node_attrs is None:
            # May have been set to None above b/c all attributes are preserved
            pass
        elif isinstance(node_attrs, str):
            if node_attrs[0] == "[":
                # e.g. `node_attrs="[node_attributes]"` (argument of list of attributes)
                # e.g. `func(node_attributes=["foo", "bar"])`
                node_attrs = {
                    node_attr: None for node_attr in bound.arguments[node_attrs[1:-1]]
                }
            elif callable(bound.arguments[node_attrs]):
                # e.g. `node_attrs="weight"` and `func(weight=myfunc)`
                preserve_node_attrs = True
                node_attrs = None
            elif bound.arguments[node_attrs] is not None:
                # e.g. `node_attrs="weight"` and `func(weight="foo")`
                node_attrs = {bound.arguments[node_attrs]: None}
            else:
                # e.g. `node_attrs="weight"` and `func(weight=None)`
                node_attrs = None
        else:
            # e.g. `node_attrs={"attr": "default"}` and `func(attr="foo", default=7)`
            # e.g. `node_attrs={"attr": 0}` and `func(attr="foo")`
            node_attrs = {
                node_attr: bound.arguments.get(val) if isinstance(val, str) else val
                for key, val in node_attrs.items()
                if (node_attr := bound.arguments[key]) is not None
            }

        # It should be safe to assume that we either have networkx graphs or backend graphs.
        # Future work: allow conversions between backends.
        for gname in self.graphs:
            if gname in self.list_graphs:
                bound.arguments[gname] = [
                    self._convert_graph(
                        backend_name,
                        g,
                        edge_attrs=edge_attrs,
                        node_attrs=node_attrs,
                        preserve_edge_attrs=preserve_edge_attrs,
                        preserve_node_attrs=preserve_node_attrs,
                        preserve_graph_attrs=preserve_graph_attrs,
                        graph_name=gname,
                        use_cache=use_cache,
                        mutations=mutations,
                    )
                    if getattr(g, "__networkx_backend__", "networkx") != backend_name
                    else g
                    for g in bound.arguments[gname]
                ]
            else:
                graph = bound.arguments[gname]
                if graph is None:
                    if gname in self.optional_graphs:
                        continue
                    raise TypeError(
                        f"Missing required graph argument `{gname}` in {self.name} function"
                    )
                if isinstance(preserve_edge_attrs, dict):
                    preserve_edges = False
                    edges = preserve_edge_attrs.get(gname, edge_attrs)
                else:
                    preserve_edges = preserve_edge_attrs
                    edges = edge_attrs
                if isinstance(preserve_node_attrs, dict):
                    preserve_nodes = False
                    nodes = preserve_node_attrs.get(gname, node_attrs)
                else:
                    preserve_nodes = preserve_node_attrs
                    nodes = node_attrs
                if isinstance(preserve_graph_attrs, set):
                    preserve_graph = gname in preserve_graph_attrs
                else:
                    preserve_graph = preserve_graph_attrs
                if getattr(graph, "__networkx_backend__", "networkx") != backend_name:
                    bound.arguments[gname] = self._convert_graph(
                        backend_name,
                        graph,
                        edge_attrs=edges,
                        node_attrs=nodes,
                        preserve_edge_attrs=preserve_edges,
                        preserve_node_attrs=preserve_nodes,
                        preserve_graph_attrs=preserve_graph,
                        graph_name=gname,
                        use_cache=use_cache,
                        mutations=mutations,
                    )
        bound_kwargs = bound.kwargs
        del bound_kwargs["backend"]
        return bound.args, bound_kwargs

    def _convert_graph(
        self,
        backend_name,
        graph,
        *,
        edge_attrs,
        node_attrs,
        preserve_edge_attrs,
        preserve_node_attrs,
        preserve_graph_attrs,
        graph_name,
        use_cache,
        mutations,
    ):
        if (
            use_cache
            and (nx_cache := getattr(graph, "__networkx_cache__", None)) is not None
        ):
            cache = nx_cache.setdefault("backends", {}).setdefault(backend_name, {})
            key = _get_cache_key(
                edge_attrs=edge_attrs,
                node_attrs=node_attrs,
                preserve_edge_attrs=preserve_edge_attrs,
                preserve_node_attrs=preserve_node_attrs,
                preserve_graph_attrs=preserve_graph_attrs,
            )
            compat_key, rv = _get_from_cache(cache, key, mutations=mutations)
            if rv is not None:
                if "cache" not in nx.config.warnings_to_ignore:
                    warnings.warn(
                        "Note: conversions to backend graphs are saved to cache "
                        "(`G.__networkx_cache__` on the original graph) by default."
                        "\n\nThis warning means the cached graph is being used "
                        f"for the {backend_name!r} backend in the "
                        f"call to {self.name}.\n\nFor the cache to be consistent "
                        "(i.e., correct), the input graph must not have been "
                        "manually mutated since the cached graph was created. "
                        "Examples of manually mutating the graph data structures "
                        "resulting in an inconsistent cache include:\n\n"
                        "    >>> G[u][v][key] = val\n\n"
                        "and\n\n"
                        "    >>> for u, v, d in G.edges(data=True):\n"
                        "    ...     d[key] = val\n\n"
                        "Using methods such as `G.add_edge(u, v, weight=val)` "
                        "will correctly clear the cache to keep it consistent. "
                        "You may also use `G.__networkx_cache__.clear()` to "
                        "manually clear the cache, or set `G.__networkx_cache__` "
                        "to None to disable caching for G. Enable or disable caching "
                        "globally via `nx.config.cache_converted_graphs` config.\n\n"
                        "To disable this warning:\n\n"
                        '    >>> nx.config.warnings_to_ignore.add("cache")\n'
                    )
                _logger.debug(
                    "Using cached converted graph (from '%s' to '%s' backend) "
                    "in call to `%s' for '%s' argument",
                    getattr(graph, "__networkx_backend__", None),
                    backend_name,
                    self.name,
                    graph_name,
                )
                return rv

        if backend_name == "networkx":
            # Perhaps we should check that "__networkx_backend__" attribute exists
            # and return the original object if not.
            if not hasattr(graph, "__networkx_backend__"):
                _logger.debug(
                    "Unable to convert input to 'networkx' backend in call to `%s' for "
                    "'%s argument, because it is not from a backend (i.e., it does not "
                    "have `G.__networkx_backend__` attribute). Using the original "
                    "object: %s",
                    self.name,
                    graph_name,
                    graph,
                )
                # This may fail, but let it fail in the networkx function
                return graph
            backend = _load_backend(graph.__networkx_backend__)
            rv = backend.convert_to_nx(graph)
        else:
            backend = _load_backend(backend_name)
            rv = backend.convert_from_nx(
                graph,
                edge_attrs=edge_attrs,
                node_attrs=node_attrs,
                preserve_edge_attrs=preserve_edge_attrs,
                preserve_node_attrs=preserve_node_attrs,
                # Always preserve graph attrs when we are caching b/c this should be
                # cheap and may help prevent extra (unnecessary) conversions. Because
                # we do this, we don't need `preserve_graph_attrs` in the cache key.
                preserve_graph_attrs=preserve_graph_attrs or use_cache,
                name=self.name,
                graph_name=graph_name,
            )
        if use_cache and nx_cache is not None and mutations is None:
            _set_to_cache(cache, key, rv)
            _logger.debug(
                "Caching converted graph (from '%s' to '%s' backend) "
                "in call to `%s' for '%s' argument",
                getattr(graph, "__networkx_backend__", None),
                backend_name,
                self.name,
                graph_name,
            )

        return rv

    def _call_with_backend(self, backend_name, args, kwargs, *, extra_message=None):
        """Call this dispatchable function with a backend without converting inputs."""
        if backend_name == "networkx":
            return self.orig_func(*args, **kwargs)
        backend = _load_backend(backend_name)
        _logger.debug(
            "Using backend '%s' for call to `%s' with arguments: %s",
            backend_name,
            self.name,
            _LazyArgsRepr(self, args, kwargs),
        )
        try:
            return getattr(backend, self.name)(*args, **kwargs)
        except NotImplementedError as exc:
            if extra_message is not None:
                _logger.debug(
                    "Backend '%s' raised when calling `%s': %s",
                    backend_name,
                    self.name,
                    exc,
                )
                raise NotImplementedError(extra_message) from exc
            raise

    def _convert_and_call(
        self,
        backend_name,
        input_backend_names,
        args,
        kwargs,
        *,
        extra_message=None,
        mutations=None,
    ):
        """Call this dispatchable function with a backend after converting inputs.

        Parameters
        ----------
        backend_name : str
        input_backend_names : set[str]
        args : arguments tuple
        kwargs : keywords dict
        extra_message : str, optional
            Additional message to log if NotImplementedError is raised by backend.
        mutations : list, optional
            Used to clear objects gotten from cache if inputs will be mutated.
        """
        if backend_name == "networkx":
            func = self.orig_func
        else:
            backend = _load_backend(backend_name)
            func = getattr(backend, self.name)
        other_backend_names = input_backend_names - {backend_name}
        _logger.debug(
            "Converting input graphs from %s backend%s to '%s' backend for call to `%s'",
            other_backend_names
            if len(other_backend_names) > 1
            else f"'{next(iter(other_backend_names))}'",
            "s" if len(other_backend_names) > 1 else "",
            backend_name,
            self.name,
        )
        try:
            converted_args, converted_kwargs = self._convert_arguments(
                backend_name,
                args,
                kwargs,
                use_cache=nx.config.cache_converted_graphs,
                mutations=mutations,
            )
        except NotImplementedError as exc:
            # Only log the exception if we are adding an extra message
            # because we don't want to lose any information.
            _logger.debug(
                "Failed to convert graphs from %s to '%s' backend for call to `%s'"
                + ("" if extra_message is None else ": %s"),
                input_backend_names,
                backend_name,
                self.name,
                *(() if extra_message is None else (exc,)),
            )
            if extra_message is not None:
                raise NotImplementedError(extra_message) from exc
            raise
        if backend_name != "networkx":
            _logger.debug(
                "Using backend '%s' for call to `%s' with arguments: %s",
                backend_name,
                self.name,
                _LazyArgsRepr(self, converted_args, converted_kwargs),
            )
        try:
            return func(*converted_args, **converted_kwargs)
        except NotImplementedError as exc:
            if extra_message is not None:
                _logger.debug(
                    "Backend '%s' raised when calling `%s': %s",
                    backend_name,
                    self.name,
                    exc,
                )
                raise NotImplementedError(extra_message) from exc
            raise

    def _convert_and_call_for_tests(
        self, backend_name, args, kwargs, *, fallback_to_nx=False
    ):
        """Call this dispatchable function with a backend; for use with testing."""
        backend = _load_backend(backend_name)
        if not self._can_backend_run(backend_name, args, kwargs):
            if fallback_to_nx or not self.graphs:
                if fallback_to_nx:
                    _logger.debug(
                        "Falling back to use 'networkx' instead of '%s' backend "
                        "for call to `%s' with arguments: %s",
                        backend_name,
                        self.name,
                        _LazyArgsRepr(self, args, kwargs),
                    )
                return self.orig_func(*args, **kwargs)

            import pytest

            msg = f"'{self.name}' not implemented by {backend_name}"
            if hasattr(backend, self.name):
                msg += " with the given arguments"
            pytest.xfail(msg)

        from collections.abc import Iterable, Iterator, Mapping
        from copy import copy, deepcopy
        from io import BufferedReader, BytesIO, StringIO, TextIOWrapper
        from itertools import tee
        from random import Random

        import numpy as np
        from numpy.random import Generator, RandomState
        from scipy.sparse import sparray

        # We sometimes compare the backend result to the original result,
        # so we need two sets of arguments. We tee iterators and copy
        # random state so that they may be used twice.
        if not args:
            args1 = args2 = args
        else:
            args1, args2 = zip(
                *(
                    (arg, deepcopy(arg))
                    if isinstance(arg, RandomState)
                    else (arg, copy(arg))
                    if isinstance(arg, BytesIO | StringIO | Random | Generator)
                    else tee(arg)
                    if isinstance(arg, Iterator)
                    and not isinstance(arg, BufferedReader | TextIOWrapper)
                    else (arg, arg)
                    for arg in args
                )
            )
        if not kwargs:
            kwargs1 = kwargs2 = kwargs
        else:
            kwargs1, kwargs2 = zip(
                *(
                    ((k, v), (k, deepcopy(v)))
                    if isinstance(v, RandomState)
                    else ((k, v), (k, copy(v)))
                    if isinstance(v, BytesIO | StringIO | Random | Generator)
                    else ((k, (teed := tee(v))[0]), (k, teed[1]))
                    if isinstance(v, Iterator)
                    and not isinstance(v, BufferedReader | TextIOWrapper)
                    else ((k, v), (k, v))
                    for k, v in kwargs.items()
                )
            )
            kwargs1 = dict(kwargs1)
            kwargs2 = dict(kwargs2)
        try:
            converted_args, converted_kwargs = self._convert_arguments(
                backend_name, args1, kwargs1, use_cache=False, mutations=None
            )
            _logger.debug(
                "Using backend '%s' for call to `%s' with arguments: %s",
                backend_name,
                self.name,
                _LazyArgsRepr(self, converted_args, converted_kwargs),
            )
            result = getattr(backend, self.name)(*converted_args, **converted_kwargs)
        except NotImplementedError as exc:
            if fallback_to_nx:
                _logger.debug(
                    "Graph conversion failed; falling back to use 'networkx' instead "
                    "of '%s' backend for call to `%s'",
                    backend_name,
                    self.name,
                )
                return self.orig_func(*args2, **kwargs2)
            import pytest

            pytest.xfail(
                exc.args[0] if exc.args else f"{self.name} raised {type(exc).__name__}"
            )
        # Verify that `self._returns_graph` is correct. This compares the return type
        # to the type expected from `self._returns_graph`. This handles tuple and list
        # return types, but *does not* catch functions that yield graphs.
        if (
            self._returns_graph
            != (
                isinstance(result, nx.Graph)
                or hasattr(result, "__networkx_backend__")
                or isinstance(result, tuple | list)
                and any(
                    isinstance(x, nx.Graph) or hasattr(x, "__networkx_backend__")
                    for x in result
                )
            )
            and not (
                # May return Graph or None
                self.name in {"check_planarity", "check_planarity_recursive"}
                and any(x is None for x in result)
            )
            and not (
                # May return Graph or dict
                self.name in {"held_karp_ascent"}
                and any(isinstance(x, dict) for x in result)
            )
            and self.name
            not in {
                # yields graphs
                "all_triads",
                "general_k_edge_subgraphs",
                # yields graphs or arrays
                "nonisomorphic_trees",
            }
        ):
            raise RuntimeError(f"`returns_graph` is incorrect for {self.name}")

        def check_result(val, depth=0):
            if isinstance(val, np.number):
                raise RuntimeError(
                    f"{self.name} returned a numpy scalar {val} ({type(val)}, depth={depth})"
                )
            if isinstance(val, np.ndarray | sparray):
                return
            if isinstance(val, nx.Graph):
                check_result(val._node, depth=depth + 1)
                check_result(val._adj, depth=depth + 1)
                return
            if isinstance(val, Iterator):
                raise NotImplementedError
            if isinstance(val, Iterable) and not isinstance(val, str):
                for x in val:
                    check_result(x, depth=depth + 1)
            if isinstance(val, Mapping):
                for x in val.values():
                    check_result(x, depth=depth + 1)

        def check_iterator(it):
            for val in it:
                try:
                    check_result(val)
                except RuntimeError as exc:
                    raise RuntimeError(
                        f"{self.name} returned a numpy scalar {val} ({type(val)})"
                    ) from exc
                yield val

        if self.name in {"from_edgelist"}:
            # numpy scalars are explicitly given as values in some tests
            pass
        elif isinstance(result, Iterator):
            result = check_iterator(result)
        else:
            try:
                check_result(result)
            except RuntimeError as exc:
                raise RuntimeError(
                    f"{self.name} returned a numpy scalar {result} ({type(result)})"
                ) from exc
            check_result(result)

        if self.name in {
            "edmonds_karp",
            "barycenter",
            "contracted_edge",
            "contracted_nodes",
            "stochastic_graph",
            "relabel_nodes",
            "maximum_branching",
            "incremental_closeness_centrality",
            "minimal_branching",
            "minimum_spanning_arborescence",
            "recursive_simple_cycles",
            "connected_double_edge_swap",
        }:
            # Special-case algorithms that mutate input graphs
            bound = self.__signature__.bind(*converted_args, **converted_kwargs)
            bound.apply_defaults()
            bound2 = self.__signature__.bind(*args2, **kwargs2)
            bound2.apply_defaults()
            if self.name in {
                "minimal_branching",
                "minimum_spanning_arborescence",
                "recursive_simple_cycles",
                "connected_double_edge_swap",
            }:
                G1 = backend.convert_to_nx(bound.arguments["G"])
                G2 = bound2.arguments["G"]
                G2._adj = G1._adj
                if G2.is_directed():
                    G2._pred = G1._pred
                nx._clear_cache(G2)
            elif self.name == "edmonds_karp":
                R1 = backend.convert_to_nx(bound.arguments["residual"])
                R2 = bound2.arguments["residual"]
                if R1 is not None and R2 is not None:
                    for k, v in R1.edges.items():
                        R2.edges[k]["flow"] = v["flow"]
                    R2.graph.update(R1.graph)
                    nx._clear_cache(R2)
            elif self.name == "barycenter" and bound.arguments["attr"] is not None:
                G1 = backend.convert_to_nx(bound.arguments["G"])
                G2 = bound2.arguments["G"]
                attr = bound.arguments["attr"]
                for k, v in G1.nodes.items():
                    G2.nodes[k][attr] = v[attr]
                nx._clear_cache(G2)
            elif (
                self.name in {"contracted_nodes", "contracted_edge"}
                and not bound.arguments["copy"]
            ):
                # Edges and nodes changed; node "contraction" and edge "weight" attrs
                G1 = backend.convert_to_nx(bound.arguments["G"])
                G2 = bound2.arguments["G"]
                G2.__dict__.update(G1.__dict__)
                nx._clear_cache(G2)
            elif self.name == "stochastic_graph" and not bound.arguments["copy"]:
                G1 = backend.convert_to_nx(bound.arguments["G"])
                G2 = bound2.arguments["G"]
                for k, v in G1.edges.items():
                    G2.edges[k]["weight"] = v["weight"]
                nx._clear_cache(G2)
            elif (
                self.name == "relabel_nodes"
                and not bound.arguments["copy"]
                or self.name in {"incremental_closeness_centrality"}
            ):
                G1 = backend.convert_to_nx(bound.arguments["G"])
                G2 = bound2.arguments["G"]
                if G1 is G2:
                    return G2
                G2._node.clear()
                G2._node.update(G1._node)
                G2._adj.clear()
                G2._adj.update(G1._adj)
                if hasattr(G1, "_pred") and hasattr(G2, "_pred"):
                    G2._pred.clear()
                    G2._pred.update(G1._pred)
                if hasattr(G1, "_succ") and hasattr(G2, "_succ"):
                    G2._succ.clear()
                    G2._succ.update(G1._succ)
                nx._clear_cache(G2)
                if self.name == "relabel_nodes":
                    return G2
            return backend.convert_to_nx(result)

        converted_result = backend.convert_to_nx(result)
        if isinstance(converted_result, nx.Graph) and self.name not in {
            "boykov_kolmogorov",
            "preflow_push",
            "quotient_graph",
            "shortest_augmenting_path",
            "spectral_graph_forge",
            # We don't handle tempfile.NamedTemporaryFile arguments
            "read_gml",
            "read_graph6",
            "read_sparse6",
            # We don't handle io.BufferedReader or io.TextIOWrapper arguments
            "bipartite_read_edgelist",
            "read_adjlist",
            "read_edgelist",
            "read_graphml",
            "read_multiline_adjlist",
            "read_pajek",
            "from_pydot",
            "pydot_read_dot",
            "agraph_read_dot",
            # graph comparison fails b/c of nan values
            "read_gexf",
        }:
            # For graph return types (e.g. generators), we compare that results are
            # the same between the backend and networkx, then return the original
            # networkx result so the iteration order will be consistent in tests.
            G = self.orig_func(*args2, **kwargs2)
            if not nx.utils.graphs_equal(G, converted_result):
                assert G.number_of_nodes() == converted_result.number_of_nodes()
                assert G.number_of_edges() == converted_result.number_of_edges()
                assert G.graph == converted_result.graph
                assert G.nodes == converted_result.nodes
                assert G.adj == converted_result.adj
                assert type(G) is type(converted_result)
                raise AssertionError("Graphs are not equal")
            return G
        return converted_result

    def _make_doc(self):
        """Generate the backends section at the end for functions having an alternate
        backend implementation(s) using the `backend_info` entry-point."""

        if not self.backends:
            return self._orig_doc
        lines = [
            "Backends",
            "--------",
        ]
        for backend in sorted(self.backends):
            info = backend_info[backend]
            if "short_summary" in info:
                lines.append(f"{backend} : {info['short_summary']}")
            else:
                lines.append(backend)
            if "functions" not in info or self.name not in info["functions"]:
                lines.append("")
                continue

            func_info = info["functions"][self.name]

            # Renaming extra_docstring to additional_docs
            if func_docs := (
                func_info.get("additional_docs") or func_info.get("extra_docstring")
            ):
                lines.extend(
                    f"  {line}" if line else line for line in func_docs.split("\n")
                )
                add_gap = True
            else:
                add_gap = False

            # Renaming extra_parameters to additional_parameters
            if extra_parameters := (
                func_info.get("extra_parameters")
                or func_info.get("additional_parameters")
            ):
                if add_gap:
                    lines.append("")
                lines.append("  Additional parameters:")
                for param in sorted(extra_parameters):
                    lines.append(f"    {param}")
                    if desc := extra_parameters[param]:
                        lines.append(f"      {desc}")
                    lines.append("")
            else:
                lines.append("")

            if func_url := func_info.get("url"):
                lines.append(f"[`Source <{func_url}>`_]")
                lines.append("")

        lines.pop()  # Remove last empty line
        to_add = "\n    ".join(lines)
        if not self._orig_doc:
            return f"The original docstring for {self.name} was empty.\n\n    {to_add}"
        return f"{self._orig_doc.rstrip()}\n\n    {to_add}"

    def __reduce__(self):
        """Allow this object to be serialized with pickle.

        This uses the global registry `_registered_algorithms` to deserialize.
        """
        return _restore_dispatchable, (self.name,)


def _restore_dispatchable(name):
    return _registered_algorithms[name].__wrapped__


def _get_cache_key(
    *,
    edge_attrs,
    node_attrs,
    preserve_edge_attrs,
    preserve_node_attrs,
    preserve_graph_attrs,
):
    """Return key used by networkx caching given arguments for ``convert_from_nx``."""
    # edge_attrs: dict | None
    # node_attrs: dict | None
    # preserve_edge_attrs: bool (False if edge_attrs is not None)
    # preserve_node_attrs: bool (False if node_attrs is not None)
    return (
        frozenset(edge_attrs.items())
        if edge_attrs is not None
        else preserve_edge_attrs,
        frozenset(node_attrs.items())
        if node_attrs is not None
        else preserve_node_attrs,
    )


def _get_from_cache(cache, key, *, backend_name=None, mutations=None):
    """Search the networkx cache for a graph that is compatible with ``key``.

    Parameters
    ----------
    cache : dict
        If ``backend_name`` is given, then this is treated as ``G.__networkx_cache__``,
        but if ``backend_name`` is None, then this is treated as the resolved inner
        cache such as ``G.__networkx_cache__["backends"][backend_name]``.
    key : tuple
        Cache key from ``_get_cache_key``.
    backend_name : str, optional
        Name of the backend to control how ``cache`` is interpreted.
    mutations : list, optional
        Used internally to clear objects gotten from cache if inputs will be mutated.

    Returns
    -------
    tuple or None
        The key of the compatible graph found in the cache.
    graph or None
        A compatible graph or None.
    """
    if backend_name is not None:
        cache = cache.get("backends", {}).get(backend_name, {})
    if not cache:
        return None, None

    # Do a simple search for a cached graph with compatible data.
    # For example, if we need a single attribute, then it's okay
    # to use a cached graph that preserved all attributes.
    # This looks for an exact match first.
    edge_key, node_key = key
    for compat_key in itertools.product(
        (edge_key, True) if edge_key is not True else (True,),
        (node_key, True) if node_key is not True else (True,),
    ):
        if (rv := cache.get(compat_key)) is not None:
            if mutations is not None:
                # Remove this item from the cache (after all conversions) if
                # the call to this dispatchable function will mutate an input.
                mutations.append((cache, compat_key))
            return compat_key, rv
    if edge_key is not True and node_key is not True:
        # Iterate over the items in `cache` to see if any are compatible.
        # For example, if no edge attributes are needed, then a graph
        # with any edge attribute will suffice. We use the same logic
        # below (but switched) to clear unnecessary items from the cache.
        # Use `list(cache.items())` to be thread-safe.
        for (ekey, nkey), graph in list(cache.items()):
            if edge_key is False or ekey is True:
                pass  # Cache works for edge data!
            elif edge_key is True or ekey is False or not edge_key.issubset(ekey):
                continue  # Cache missing required edge data; does not work
            if node_key is False or nkey is True:
                pass  # Cache works for node data!
            elif node_key is True or nkey is False or not node_key.issubset(nkey):
                continue  # Cache missing required node data; does not work
            if mutations is not None:
                # Remove this item from the cache (after all conversions) if
                # the call to this dispatchable function will mutate an input.
                mutations.append((cache, (ekey, nkey)))
            return (ekey, nkey), graph
    return None, None


def _set_to_cache(cache, key, graph, *, backend_name=None):
    """Set a backend graph to the cache, and remove unnecessary cached items.

    Parameters
    ----------
    cache : dict
        If ``backend_name`` is given, then this is treated as ``G.__networkx_cache__``,
        but if ``backend_name`` is None, then this is treated as the resolved inner
        cache such as ``G.__networkx_cache__["backends"][backend_name]``.
    key : tuple
        Cache key from ``_get_cache_key``.
    graph : graph
    backend_name : str, optional
        Name of the backend to control how ``cache`` is interpreted.

    Returns
    -------
    dict
        The items that were removed from the cache.
    """
    if backend_name is not None:
        cache = cache.setdefault("backends", {}).setdefault(backend_name, {})
    # Remove old cached items that are no longer necessary since they
    # are dominated/subsumed/outdated by what was just calculated.
    # This uses the same logic as above, but with keys switched.
    # Also, don't update the cache here if the call will mutate an input.
    removed = {}
    edge_key, node_key = key
    cache[key] = graph  # Set at beginning to be thread-safe
    for cur_key in list(cache):
        if cur_key == key:
            continue
        ekey, nkey = cur_key
        if ekey is False or edge_key is True:
            pass
        elif ekey is True or edge_key is False or not ekey.issubset(edge_key):
            continue
        if nkey is False or node_key is True:
            pass
        elif nkey is True or node_key is False or not nkey.issubset(node_key):
            continue
        # Use pop instead of del to try to be thread-safe
        if (graph := cache.pop(cur_key, None)) is not None:
            removed[cur_key] = graph
    return removed


class _LazyArgsRepr:
    """Simple wrapper to display arguments of dispatchable functions in logging calls."""

    def __init__(self, func, args, kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.value = None

    def __repr__(self):
        if self.value is None:
            bound = self.func.__signature__.bind_partial(*self.args, **self.kwargs)
            inner = ", ".join(f"{key}={val!r}" for key, val in bound.arguments.items())
            self.value = f"({inner})"
        return self.value


if os.environ.get("_NETWORKX_BUILDING_DOCS_"):
    # When building docs with Sphinx, use the original function with the
    # dispatched __doc__, b/c Sphinx renders normal Python functions better.
    # This doesn't show e.g. `*, backend=None, **backend_kwargs` in the
    # signatures, which is probably okay. It does allow the docstring to be
    # updated based on the installed backends.
    _orig_dispatchable = _dispatchable

    def _dispatchable(func=None, **kwargs):  # type: ignore[no-redef]
        if func is None:
            return partial(_dispatchable, **kwargs)
        dispatched_func = _orig_dispatchable(func, **kwargs)
        func.__doc__ = dispatched_func.__doc__
        return func

    _dispatchable.__doc__ = _orig_dispatchable.__new__.__doc__  # type: ignore[method-assign,assignment]
    _sig = inspect.signature(_orig_dispatchable.__new__)
    _dispatchable.__signature__ = _sig.replace(  # type: ignore[method-assign,assignment]
        parameters=[v for k, v in _sig.parameters.items() if k != "cls"]
    )
