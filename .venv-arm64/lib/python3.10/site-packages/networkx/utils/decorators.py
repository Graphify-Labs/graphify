import bz2
import collections
import gzip
import inspect
import itertools
import re
import warnings
from collections import defaultdict
from contextlib import contextmanager
from functools import wraps
from inspect import Parameter, signature
from os.path import splitext
from pathlib import Path

import networkx as nx
from networkx.utils import create_py_random_state, create_random_state

__all__ = [
    "not_implemented_for",
    "open_file",
    "nodes_or_number",
    "np_random_state",
    "py_random_state",
    "argmap",
]


def not_implemented_for(*graph_types):
    """Decorator to mark algorithms as not implemented

    Parameters
    ----------
    graph_types : container of strings
        Entries must be one of "directed", "undirected", "multigraph", or "graph".

    Returns
    -------
    _require : function
        The decorated function.

    Raises
    ------
    NetworkXNotImplemented
    If any of the packages cannot be imported

    Notes
    -----
    Multiple types are joined logically with "and".
    For "or" use multiple @not_implemented_for() lines.

    Examples
    --------
    Decorate functions like this::

       @not_implemented_for("directed")
       def sp_function(G):
           pass


       # rule out MultiDiGraph
       @not_implemented_for("directed", "multigraph")
       def sp_np_function(G):
           pass


       # rule out all except DiGraph
       @not_implemented_for("undirected")
       @not_implemented_for("multigraph")
       def sp_np_function(G):
           pass
    """
    if ("directed" in graph_types) and ("undirected" in graph_types):
        raise ValueError("Function not implemented on directed AND undirected graphs?")
    if ("multigraph" in graph_types) and ("graph" in graph_types):
        raise ValueError("Function not implemented on graph AND multigraphs?")
    if not set(graph_types) < {"directed", "undirected", "multigraph", "graph"}:
        raise KeyError(
            "use one or more of directed, undirected, multigraph, graph.  "
            f"You used {graph_types}"
        )

    # 3-way logic: True if "directed" input, False if "undirected" input, else None
    dval = ("directed" in graph_types) or "undirected" not in graph_types and None
    mval = ("multigraph" in graph_types) or "graph" not in graph_types and None
    errmsg = f"not implemented for {' '.join(graph_types)} type"

    def _not_implemented_for(g):
        if (mval is None or mval == g.is_multigraph()) and (
            dval is None or dval == g.is_directed()
        ):
            raise nx.NetworkXNotImplemented(errmsg)

        return g

    return argmap(_not_implemented_for, 0)


# To handle new extensions, define a function accepting a `path` and `mode`.
# Then add the extension to _dispatch_dict.
fopeners = {
    ".gz": gzip.open,
    ".gzip": gzip.open,
    ".bz2": bz2.BZ2File,
}
_dispatch_dict = defaultdict(lambda: open, **fopeners)


def open_file(path_arg, mode="r"):
    """Decorator to ensure clean opening and closing of files.

    Parameters
    ----------
    path_arg : string or int
        Name or index of the argument that is a path.

    mode : str
        String for opening mode.

    Returns
    -------
    _open_file : function
        Function which cleanly executes the io.

    Examples
    --------
    Decorate functions like this::

       @open_file(0, "r")
       def read_function(pathname):
           pass


       @open_file(1, "w")
       def write_function(G, pathname):
           pass


       @open_file(1, "w")
       def write_function(G, pathname="graph.dot"):
           pass


       @open_file("pathname", "w")
       def write_function(G, pathname="graph.dot"):
           pass


       @open_file("path", "w+")
       def another_function(arg, **kwargs):
           path = kwargs["path"]
           pass

    Notes
    -----
    Note that this decorator solves the problem when a path argument is
    specified as a string, but it does not handle the situation when the
    function wants to accept a default of None (and then handle it).

    Here is an example of how to handle this case::

      @open_file("path")
      def some_function(arg1, arg2, path=None):
          if path is None:
              fobj = tempfile.NamedTemporaryFile(delete=False)
          else:
              # `path` could have been a string or file object or something
              # similar. In any event, the decorator has given us a file object
              # and it will close it for us, if it should.
              fobj = path

          try:
              fobj.write("blah")
          finally:
              if path is None:
                  fobj.close()

    Normally, we'd want to use "with" to ensure that fobj gets closed.
    However, the decorator will make `path` a file object for us,
    and using "with" would undesirably close that file object.
    Instead, we use a try block, as shown above.
    When we exit the function, fobj will be closed, if it should be, by the decorator.
    """

    def _open_file(path):
        # Now we have the path_arg. There are two types of input to consider:
        #   1) string representing a path that should be opened
        #   2) an already opened file object
        if isinstance(path, str):
            ext = splitext(path)[1]
        elif isinstance(path, Path):
            # path is a pathlib reference to a filename
            ext = path.suffix
            path = str(path)
        else:
            # could be None, or a file handle, in which case the algorithm will deal with it
            return path, lambda: None

        fobj = _dispatch_dict[ext](path, mode=mode)
        return fobj, lambda: fobj.close()

    return argmap(_open_file, path_arg, try_finally=True)


def nodes_or_number(which_args):
    """Decorator to allow number of nodes or container of nodes.

    With this decorator, the specified argument can be either a number or a container
    of nodes. If it is a number, the nodes used are `range(n)`.
    This allows `nx.complete_graph(50)` in place of `nx.complete_graph(list(range(50)))`.
    And it also allows `nx.complete_graph(any_list_of_nodes)`.

    Parameters
    ----------
    which_args : string or int or sequence of strings or ints
        If string, the name of the argument to be treated.
        If int, the index of the argument to be treated.
        If more than one node argument is allowed, can be a list of locations.

    Returns
    -------
    _nodes_or_numbers : function
        Function which replaces int args with ranges.

    Examples
    --------
    Decorate functions like this::

       @nodes_or_number("nodes")
       def empty_graph(nodes):
           # nodes is converted to a list of nodes

       @nodes_or_number(0)
       def empty_graph(nodes):
           # nodes is converted to a list of nodes

       @nodes_or_number(["m1", "m2"])
       def grid_2d_graph(m1, m2, periodic=False):
           # m1 and m2 are each converted to a list of nodes

       @nodes_or_number([0, 1])
       def grid_2d_graph(m1, m2, periodic=False):
           # m1 and m2 are each converted to a list of nodes

       @nodes_or_number(1)
       def full_rary_tree(r, n)
           # presumably r is a number. It is not handled by this decorator.
           # n is converted to a list of nodes
    """

    def _nodes_or_number(n):
        try:
            nodes = list(range(n))
        except TypeError:
            nodes = tuple(n)
        else:
            if n < 0:
                raise nx.NetworkXError(f"Negative number of nodes not valid: {n}")
        return (n, nodes)

    try:
        iter_wa = iter(which_args)
    except TypeError:
        iter_wa = (which_args,)

    return argmap(_nodes_or_number, *iter_wa)


def np_random_state(random_state_argument):
    """Decorator to generate a numpy RandomState or Generator instance.

    The decorator processes the argument indicated by `random_state_argument`
    using :func:`nx.utils.create_random_state`.
    The argument value can be a seed (integer), or a `numpy.random.RandomState`
    or `numpy.random.RandomState` instance or (`None` or `numpy.random`).
    The latter two options use the global random number generator for `numpy.random`.

    The returned instance is a `numpy.random.RandomState` or `numpy.random.Generator`.

    Parameters
    ----------
    random_state_argument : string or int
        The name or index of the argument to be converted
        to a `numpy.random.RandomState` instance.

    Returns
    -------
    _random_state : function
        Function whose random_state keyword argument is a RandomState instance.

    Examples
    --------
    Decorate functions like this::

       @np_random_state("seed")
       def random_float(seed=None):
           return seed.rand()


       @np_random_state(0)
       def random_float(rng=None):
           return rng.rand()


       @np_random_state(1)
       def random_array(dims, random_state=1):
           return random_state.rand(*dims)

    See Also
    --------
    py_random_state
    """
    return argmap(create_random_state, random_state_argument)


def py_random_state(random_state_argument):
    """Decorator to generate a random.Random instance (or equiv).

    This decorator processes `random_state_argument` using
    :func:`nx.utils.create_py_random_state`.
    The input value can be a seed (integer), or a random number generator::

        If int, return a random.Random instance set with seed=int.
        If random.Random instance, return it.
        If None or the `random` package, return the global random number
        generator used by `random`.
        If np.random package, or the default numpy RandomState instance,
        return the default numpy random number generator wrapped in a
        `PythonRandomViaNumpyBits`  class.
        If np.random.Generator instance, return it wrapped in a
        `PythonRandomViaNumpyBits`  class.

        # Legacy options
        If np.random.RandomState instance, return it wrapped in a
        `PythonRandomInterface` class.
        If a `PythonRandomInterface` instance, return it

    Parameters
    ----------
    random_state_argument : string or int
        The name of the argument or the index of the argument in args that is
        to be converted to the random.Random instance or numpy.random.RandomState
        instance that mimics basic methods of random.Random.

    Returns
    -------
    _random_state : function
        Function whose random_state_argument is converted to a Random instance.

    Examples
    --------
    Decorate functions like this::

       @py_random_state("random_state")
       def random_float(random_state=None):
           return random_state.rand()


       @py_random_state(0)
       def random_float(rng=None):
           return rng.rand()


       @py_random_state(1)
       def random_array(dims, seed=12345):
           return seed.rand(*dims)

    See Also
    --------
    np_random_state
    """

    return argmap(create_py_random_state, random_state_argument)


class argmap:
    """A decorator to apply a map to arguments before calling the function

    This class provides a decorator that maps (transforms) arguments of the function
    before the function is called. Thus for example, we have similar code
    in many functions to determine whether an argument is the number of nodes
    to be created, or a list of nodes to be handled. The decorator provides
    the code to accept either -- transforming the indicated argument into a
    list of nodes before the actual function is called.

    This decorator class allows us to process single or multiple arguments.
    The arguments to be processed can be specified by string, naming the argument,
    or by index, specifying the item in the args list.

    Parameters
    ----------
    func : callable
        The function to apply to arguments

    *args : iterable of (int, str or tuple)
        A list of parameters, specified either as strings (their names), ints
        (numerical indices) or tuples, which may contain ints, strings, and
        (recursively) tuples. Each indicates which parameters the decorator
        should map. Tuples indicate that the map function takes (and returns)
        multiple parameters in the same order and nested structure as indicated
        here.

    try_finally : bool (default: False)
        When True, wrap the function call in a try-finally block with code
        for the finally block created by `func`. This is used when the map
        function constructs an object (like a file handle) that requires
        post-processing (like closing).

        Note: try_finally decorators cannot be used to decorate generator
        functions.

    Examples
    --------
    Most of these examples use `@argmap(...)` to apply the decorator to
    the function defined on the next line.
    In the NetworkX codebase however, `argmap` is used within a function to
    construct a decorator. That is, the decorator defines a mapping function
    and then uses `argmap` to build and return a decorated function.
    A simple example is a decorator that specifies which currency to report money.
    The decorator (named `convert_to`) would be used like::

        @convert_to("US_Dollars", "income")
        def show_me_the_money(name, income):
            print(f"{name} : {income}")

    And the code to create the decorator might be::

        def convert_to(currency, which_arg):
            def _convert(amount):
                if amount.currency != currency:
                    amount = amount.to_currency(currency)
                return amount

            return argmap(_convert, which_arg)

    Despite this common idiom for argmap, most of the following examples
    use the `@argmap(...)` idiom to save space.

    Here's an example use of argmap to sum the elements of two of the functions
    arguments. The decorated function::

        @argmap(sum, "xlist", "zlist")
        def foo(xlist, y, zlist):
            return xlist - y + zlist

    is syntactic sugar for::

        def foo(xlist, y, zlist):
            x = sum(xlist)
            z = sum(zlist)
            return x - y + z

    and is equivalent to (using argument indexes)::

        @argmap(sum, "xlist", 2)
        def foo(xlist, y, zlist):
            return xlist - y + zlist

    or::

        @argmap(sum, "zlist", 0)
        def foo(xlist, y, zlist):
            return xlist - y + zlist

    Transforming functions can be applied to multiple arguments, such as::

        def swap(x, y):
            return y, x

        # the 2-tuple tells argmap that the map `swap` has 2 inputs/outputs.
        @argmap(swap, ("a", "b")):
        def foo(a, b, c):
            return a / b * c

    is equivalent to::

        def foo(a, b, c):
            a, b = swap(a, b)
            return a / b * c

    More generally, the applied arguments can be nested tuples of strings or ints.
    The syntax `@argmap(some_func, ("a", ("b", "c")))` would expect `some_func` to
    accept 2 inputs with the second expected to be a 2-tuple. It should then return
    2 outputs with the second a 2-tuple. The returns values would replace input "a"
    "b" and "c" respectively. Similarly for `@argmap(some_func, (0, ("b", 2)))`.

    Also, note that an index larger than the number of named parameters is allowed
    for variadic functions. For example::

        def double(a):
            return 2 * a


        @argmap(double, 3)
        def overflow(a, *args):
            return a, args


        print(overflow(1, 2, 3, 4, 5, 6))  # output is 1, (2, 3, 8, 5, 6)

    **Try Finally**

    Additionally, this `argmap` class can be used to create a decorator that
    initiates a try...finally block. The decorator must be written to return
    both the transformed argument and a closing function.
    This feature was included to enable the `open_file` decorator which might
    need to close the file or not depending on whether it had to open that file.
    This feature uses the keyword-only `try_finally` argument to `@argmap`.

    For example this map opens a file and then makes sure it is closed::

        def open_file(fn):
            f = open(fn)
            return f, lambda: f.close()

    The decorator applies that to the function `foo`::

        @argmap(open_file, "file", try_finally=True)
        def foo(file):
            print(file.read())

    is syntactic sugar for::

        def foo(file):
            file, close_file = open_file(file)
            try:
                print(file.read())
            finally:
                close_file()

    and is equivalent to (using indexes)::

        @argmap(open_file, 0, try_finally=True)
        def foo(file):
            print(file.read())

    Here's an example of the try_finally feature used to create a decorator::

        def my_closing_decorator(which_arg):
            def _opener(path):
                if path is None:
                    path = open(path)
                    fclose = path.close
                else:
                    # assume `path` handles the closing
                    fclose = lambda: None
                return path, fclose

            return argmap(_opener, which_arg, try_finally=True)

    which can then be used as::

        @my_closing_decorator("file")
        def fancy_reader(file=None):
            # this code doesn't need to worry about closing the file
            print(file.read())

    Decorators with try_finally = True cannot be used with generator functions,
    because the `finally` block is evaluated before the generator is exhausted::

        @argmap(open_file, "file", try_finally=True)
        def file_to_lines(file):
            for line in file.readlines():
                yield line

    is equivalent to::

        def file_to_lines_wrapped(file):
            for line in file.readlines():
                yield line


        def file_to_lines_wrapper(file):
            try:
                file = open_file(file)
                return file_to_lines_wrapped(file)
            finally:
                file.close()

    which behaves similarly to::

        def file_to_lines_whoops(file):
            file = open_file(file)
            file.close()
            for line in file.readlines():
                yield line

    because the `finally` block of `file_to_lines_wrapper` is executed before
    the caller has a chance to exhaust the iterator.

    Notes
    -----
    An object of this class is callable and intended to be used when
    defining a decorator. Generally, a decorator takes a function as input
    and constructs a function as output. Specifically, an `argmap` object
    returns the input function decorated/wrapped so that specified arguments
    are mapped (transformed) to new values before the decorated function is called.

    As an overview, the argmap object returns a new function with all the
    dunder values of the original function (like `__doc__`, `__name__`, etc).
    Code for this decorated function is built based on the original function's
    signature. It starts by mapping the input arguments to potentially new
    values. Then it calls the decorated function with these new values in place
    of the indicated arguments that have been mapped. The return value of the
    original function is then returned. This new function is the function that
    is actually called by the user.

    Three additional features are provided.
        1) The code is lazily compiled. That is, the new function is returned
        as an object without the code compiled, but with all information
        needed so it can be compiled upon it's first invocation. This saves
        time on import at the cost of additional time on the first call of
        the function. Subsequent calls are then just as fast as normal.

        2) If the "try_finally" keyword-only argument is True, a try block
        follows each mapped argument, matched on the other side of the wrapped
        call, by a finally block closing that mapping.  We expect func to return
        a 2-tuple: the mapped value and a function to be called in the finally
        clause.  This feature was included so the `open_file` decorator could
        provide a file handle to the decorated function and close the file handle
        after the function call. It even keeps track of whether to close the file
        handle or not based on whether it had to open the file or the input was
        already open. So, the decorated function does not need to include any
        code to open or close files.

        3) The maps applied can process multiple arguments. For example,
        you could swap two arguments using a mapping, or transform
        them to their sum and their difference. This was included to allow
        a decorator in the `quality.py` module that checks that an input
        `partition` is a valid partition of the nodes of the input graph `G`.
        In this example, the map has inputs `(G, partition)`. After checking
        for a valid partition, the map either raises an exception or leaves
        the inputs unchanged. Thus many functions that make this check can
        use the decorator rather than copy the checking code into each function.
        More complicated nested argument structures are described below.

    The remaining notes describe the code structure and methods for this
    class in broad terms to aid in understanding how to use it.

    Instantiating an `argmap` object simply stores the mapping function and
    the input identifiers of which arguments to map. The resulting decorator
    is ready to use this map to decorate any function. Calling that object
    (`argmap.__call__`, but usually done via `@my_decorator`) a lazily
    compiled thin wrapper of the decorated function is constructed,
    wrapped with the necessary function dunder attributes like `__doc__`
    and `__name__`. That thinly wrapped function is returned as the
    decorated function. When that decorated function is called, the thin
    wrapper of code calls `argmap._lazy_compile` which compiles the decorated
    function (using `argmap.compile`) and replaces the code of the thin
    wrapper with the newly compiled code. This saves the compilation step
    every import of networkx, at the cost of compiling upon the first call
    to the decorated function.

    When the decorated function is compiled, the code is recursively assembled
    using the `argmap.assemble` method. The recursive nature is needed in
    case of nested decorators. The result of the assembly is a number of
    useful objects.

      sig : the function signature of the original decorated function as
          constructed by :func:`argmap.signature`. This is constructed
          using `inspect.signature` but enhanced with attribute
          strings `sig_def` and `sig_call`, and other information
          specific to mapping arguments of this function.
          This information is used to construct a string of code defining
          the new decorated function.

      wrapped_name : a unique internally used name constructed by argmap
          for the decorated function.

      functions : a dict of the functions used inside the code of this
          decorated function, to be used as `globals` in `exec`.
          This dict is recursively updated to allow for nested decorating.

      mapblock : code (as a list of strings) to map the incoming argument
          values to their mapped values.

      finallys : code (as a list of strings) to provide the possibly nested
          set of finally clauses if needed.

      mutable_args : a bool indicating whether the `sig.args` tuple should be
          converted to a list so mutation can occur.

    After this recursive assembly process, the `argmap.compile` method
    constructs code (as strings) to convert the tuple `sig.args` to a list
    if needed. It joins the defining code with appropriate indents and
    compiles the result.  Finally, this code is evaluated and the original
    wrapper's implementation is replaced with the compiled version (see
    `argmap._lazy_compile` for more details).

    Other `argmap` methods include `_name` and `_count` which allow internally
    generated names to be unique within a python session.
    The methods `_flatten` and `_indent` process the nested lists of strings
    into properly indented python code ready to be compiled.

    More complicated nested tuples of arguments also allowed though
    usually not used. For the simple 2 argument case, the argmap
    input ("a", "b") implies the mapping function will take 2 arguments
    and return a 2-tuple of mapped values. A more complicated example
    with argmap input `("a", ("b", "c"))` requires the mapping function
    take 2 inputs, with the second being a 2-tuple. It then must output
    the 3 mapped values in the same nested structure `(newa, (newb, newc))`.
    This level of generality is not often needed, but was convenient
    to implement when handling the multiple arguments.

    See Also
    --------
    not_implemented_for
    open_file
    nodes_or_number
    py_random_state
    networkx.algorithms.community.quality.require_partition

    """

    def __init__(self, func, *args, try_finally=False):
        self._func = func
        self._args = args
        self._finally = try_finally

    @staticmethod
    def _lazy_compile(func):
        """Compile the source of a wrapped function

        Assemble and compile the decorated function, and intrusively replace its
        code with the compiled version's.  The thinly wrapped function becomes
        the decorated function.

        Parameters
        ----------
        func : callable
            A function returned by argmap.__call__ which is in the process
            of being called for the first time.

        Returns
        -------
        func : callable
            The same function, with a new __code__ object.

        Notes
        -----
        It was observed in NetworkX issue #4732 [1] that the import time of
        NetworkX was significantly bloated by the use of decorators: over half
        of the import time was being spent decorating functions.  This was
        somewhat improved by a change made to the `decorator` library, at the
        cost of a relatively heavy-weight call to `inspect.Signature.bind`
        for each call to the decorated function.

        The workaround we arrived at is to do minimal work at the time of
        decoration.  When the decorated function is called for the first time,
        we compile a function with the same function signature as the wrapped
        function.  The resulting decorated function is faster than one made by
        the `decorator` library, so that the overhead of the first call is
        'paid off' after a small number of calls.

        References
        ----------

        [1] https://github.com/networkx/networkx/issues/4732

        """
        real_func = func.__argmap__.compile(func.__wrapped__)
        func.__code__ = real_func.__code__
        func.__globals__.update(real_func.__globals__)
        func.__dict__.update(real_func.__dict__)
        return func

    def __call__(self, f):
        """Construct a lazily decorated wrapper of f.

        The decorated function will be compiled when it is called for the first time,
        and it will replace its own __code__ object so subsequent calls are fast.

        Parameters
        ----------
        f : callable
            A function to be decorated.

        Returns
        -------
        func : callable
            The decorated function.

        See Also
        --------
        argmap._lazy_compile
        """

        def func(*args, __wrapper=None, **kwargs):
            return argmap._lazy_compile(__wrapper)(*args, **kwargs)

        # standard function-wrapping stuff
        func.__name__ = f.__name__
        func.__doc__ = f.__doc__
        func.__defaults__ = f.__defaults__
        func.__kwdefaults__.update(f.__kwdefaults__ or {})
        func.__module__ = f.__module__
        func.__qualname__ = f.__qualname__
        func.__dict__.update(f.__dict__)
        func.__wrapped__ = f

        # now that we've wrapped f, we may have picked up some __dict__ or
        # __kwdefaults__ items that were set by a previous argmap.  Thus, we set
        # these values after those update() calls.

        # If we attempt to access func from within itself, that happens through
        # a closure -- which trips an error when we replace func.__code__.  The
        # standard workaround for functions which can't see themselves is to use
        # a Y-combinator, as we do here.
        func.__kwdefaults__["_argmap__wrapper"] = func

        # this self-reference is here because functools.wraps preserves
        # everything in __dict__, and we don't want to mistake a non-argmap
        # wrapper for an argmap wrapper
        func.__self__ = func

        # this is used to variously call self.assemble and self.compile
        func.__argmap__ = self

        if hasattr(f, "__argmap__"):
            func.__is_generator = f.__is_generator
        else:
            func.__is_generator = inspect.isgeneratorfunction(f)

        if self._finally and func.__is_generator:
            raise nx.NetworkXError("argmap cannot decorate generators with try_finally")

        return func

    __count = 0

    @classmethod
    def _count(cls):
        """Maintain a globally-unique identifier for function names and "file" names

        Note that this counter is a class method reporting a class variable
        so the count is unique within a Python session. It could differ from
        session to session for a specific decorator depending on the order
        that the decorators are created. But that doesn't disrupt `argmap`.

        This is used in two places: to construct unique variable names
        in the `_name` method and to construct unique fictitious filenames
        in the `_compile` method.

        Returns
        -------
        count : int
            An integer unique to this Python session (simply counts from zero)
        """
        cls.__count += 1
        return cls.__count

    _bad_chars = re.compile("[^a-zA-Z0-9_]")

    @classmethod
    def _name(cls, f):
        """Mangle the name of a function to be unique but somewhat human-readable

        The names are unique within a Python session and set using `_count`.

        Parameters
        ----------
        f : str or object

        Returns
        -------
        name : str
            The mangled version of `f.__name__` (if `f.__name__` exists) or `f`

        """
        f = f.__name__ if hasattr(f, "__name__") else f
        fname = re.sub(cls._bad_chars, "_", f)
        return f"argmap_{fname}_{cls._count()}"

    def compile(self, f):
        """Compile the decorated function.

        Called once for a given decorated function -- collects the code from all
        argmap decorators in the stack, and compiles the decorated function.

        Much of the work done here uses the `assemble` method to allow recursive
        treatment of multiple argmap decorators on a single decorated function.
        That flattens the argmap decorators, collects the source code to construct
        a single decorated function, then compiles/executes/returns that function.

        The source code for the decorated function is stored as an attribute
        `_code` on the function object itself.

        Note that Python's `compile` function requires a filename, but this
        code is constructed without a file, so a fictitious filename is used
        to describe where the function comes from. The name is something like:
        "argmap compilation 4".

        Parameters
        ----------
        f : callable
            The function to be decorated

        Returns
        -------
        func : callable
            The decorated file

        """
        sig, wrapped_name, functions, mapblock, finallys, mutable_args = self.assemble(
            f
        )

        call = f"{sig.call_sig.format(wrapped_name)}#"
        mut_args = f"{sig.args} = list({sig.args})" if mutable_args else ""
        body = argmap._indent(sig.def_sig, mut_args, mapblock, call, finallys)
        code = "\n".join(body)

        locl = {}
        globl = dict(functions.values())
        filename = f"{self.__class__} compilation {self._count()}"
        compiled = compile(code, filename, "exec")
        exec(compiled, globl, locl)
        func = locl[sig.name]
        func._code = code
        return func

    def assemble(self, f):
        """Collects components of the source for the decorated function wrapping f.

        If `f` has multiple argmap decorators, we recursively assemble the stack of
        decorators into a single flattened function.

        This method is part of the `compile` method's process yet separated
        from that method to allow recursive processing. The outputs are
        strings, dictionaries and lists that collect needed info to
        flatten any nested argmap-decoration.

        Parameters
        ----------
        f : callable
            The function to be decorated.  If f is argmapped, we assemble it.

        Returns
        -------
        sig : argmap.Signature
            The function signature as an `argmap.Signature` object.
        wrapped_name : str
            The mangled name used to represent the wrapped function in the code
            being assembled.
        functions : dict
            A dictionary mapping id(g) -> (mangled_name(g), g) for functions g
            referred to in the code being assembled. These need to be present
            in the ``globals`` scope of ``exec`` when defining the decorated
            function.
        mapblock : list of lists and/or strings
            Code that implements mapping of parameters including any try blocks
            if needed. This code will precede the decorated function call.
        finallys : list of lists and/or strings
            Code that implements the finally blocks to post-process the
            arguments (usually close any files if needed) after the
            decorated function is called.
        mutable_args : bool
            True if the decorator needs to modify positional arguments
            via their indices. The compile method then turns the argument
            tuple into a list so that the arguments can be modified.
        """

        # first, we check if f is already argmapped -- if that's the case,
        # build up the function recursively.
        # > mapblock is generally a list of function calls of the sort
        #     arg = func(arg)
        # in addition to some try-blocks if needed.
        # > finallys is a recursive list of finally blocks of the sort
        #         finally:
        #             close_func_1()
        #     finally:
        #         close_func_2()
        # > functions is a dict of functions used in the scope of our decorated
        # function. It will be used to construct globals used in compilation.
        # We make functions[id(f)] = name_of_f, f to ensure that a given
        # function is stored and named exactly once even if called by
        # nested decorators.
        if hasattr(f, "__argmap__") and f.__self__ is f:
            (
                sig,
                wrapped_name,
                functions,
                mapblock,
                finallys,
                mutable_args,
            ) = f.__argmap__.assemble(f.__wrapped__)
            functions = dict(functions)  # shallow-copy just in case
        else:
            sig = self.signature(f)
            wrapped_name = self._name(f)
            mapblock, finallys = [], []
            functions = {id(f): (wrapped_name, f)}
            mutable_args = False

        if id(self._func) in functions:
            fname, _ = functions[id(self._func)]
        else:
            fname, _ = functions[id(self._func)] = self._name(self._func), self._func

        # this is a bit complicated -- we can call functions with a variety of
        # nested arguments, so long as their input and output are tuples with
        # the same nested structure. e.g. ("a", "b") maps arguments a and b.
        # A more complicated nesting like (0, (3, 4)) maps arguments 0, 3, 4
        # expecting the mapping to output new values in the same nested shape.
        # The ability to argmap multiple arguments was necessary for
        # the decorator `nx.algorithms.community.quality.require_partition`, and
        # while we're not taking full advantage of the ability to handle
        # multiply-nested tuples, it was convenient to implement this in
        # generality because the recursive call to `get_name` is necessary in
        # any case.
        applied = set()

        def get_name(arg, first=True):
            nonlocal mutable_args
            if isinstance(arg, tuple):
                name = ", ".join(get_name(x, False) for x in arg)
                return name if first else f"({name})"
            if arg in applied:
                raise nx.NetworkXError(f"argument {arg} is specified multiple times")
            applied.add(arg)
            if arg in sig.names:
                return sig.names[arg]
            elif isinstance(arg, str):
                if sig.kwargs is None:
                    raise nx.NetworkXError(
                        f"name {arg} is not a named parameter and this function doesn't have kwargs"
                    )
                return f"{sig.kwargs}[{arg!r}]"
            else:
                if sig.args is None:
                    raise nx.NetworkXError(
                        f"index {arg} not a parameter index and this function doesn't have args"
                    )
                mutable_args = True
                return f"{sig.args}[{arg - sig.n_positional}]"

        if self._finally:
            # here's where we handle try_finally decorators.  Such a decorator
            # returns a mapped argument and a function to be called in a
            # finally block.  This feature was required by the open_file
            # decorator.  The below generates the code
            #
            # name, final = func(name)                   #<--append to mapblock
            # try:                                       #<--append to mapblock
            #     ... more argmapping and try blocks
            #     return WRAPPED_FUNCTION(...)
            #     ... more finally blocks
            # finally:                                   #<--prepend to finallys
            #     final()                                #<--prepend to finallys
            #
            for a in self._args:
                name = get_name(a)
                final = self._name(name)
                mapblock.append(f"{name}, {final} = {fname}({name})")
                mapblock.append("try:")
                finallys = ["finally:", f"{final}()#", "#", finallys]
        else:
            mapblock.extend(
                f"{name} = {fname}({name})" for name in map(get_name, self._args)
            )

        return sig, wrapped_name, functions, mapblock, finallys, mutable_args

    @classmethod
    def signature(cls, f):
        r"""Construct a Signature object describing `f`

        Compute a Signature so that we can write a function wrapping f with
        the same signature and call-type.

        Parameters
        ----------
        f : callable
            A function to be decorated

        Returns
        -------
        sig : argmap.Signature
            The Signature of f

        Notes
        -----
        The Signature is a namedtuple with names:

            name : a unique version of the name of the decorated function
            signature : the inspect.signature of the decorated function
            def_sig : a string used as code to define the new function
            call_sig : a string used as code to call the decorated function
            names : a dict keyed by argument name and index to the argument's name
            n_positional : the number of positional arguments in the signature
            args : the name of the VAR_POSITIONAL argument if any, i.e. \*theseargs
            kwargs : the name of the VAR_KEYWORDS argument if any, i.e. \*\*kwargs

        These named attributes of the signature are used in `assemble` and `compile`
        to construct a string of source code for the decorated function.

        """
        sig = inspect.signature(f, follow_wrapped=False)
        def_sig = []
        call_sig = []
        names = {}

        kind = None
        args = None
        kwargs = None
        npos = 0
        for i, param in enumerate(sig.parameters.values()):
            # parameters can be position-only, keyword-or-position, keyword-only
            # in any combination, but only in the order as above.  we do edge
            # detection to add the appropriate punctuation
            prev = kind
            kind = param.kind
            if prev == param.POSITIONAL_ONLY != kind:
                # the last token was position-only, but this one isn't
                def_sig.append("/")
            if (
                param.VAR_POSITIONAL
                != prev
                != param.KEYWORD_ONLY
                == kind
                != param.VAR_POSITIONAL
            ):
                # param is the first keyword-only arg and isn't starred
                def_sig.append("*")

            # star arguments as appropriate
            if kind == param.VAR_POSITIONAL:
                name = "*" + param.name
                args = param.name
                count = 0
            elif kind == param.VAR_KEYWORD:
                name = "**" + param.name
                kwargs = param.name
                count = 0
            else:
                names[i] = names[param.name] = param.name
                name = param.name
                count = 1

            # assign to keyword-only args in the function call
            if kind == param.KEYWORD_ONLY:
                call_sig.append(f"{name} = {name}")
            else:
                npos += count
                call_sig.append(name)

            def_sig.append(name)

        fname = cls._name(f)
        def_sig = f'def {fname}({", ".join(def_sig)}):'

        call_sig = f"return {{}}({', '.join(call_sig)})"

        return cls.Signature(fname, sig, def_sig, call_sig, names, npos, args, kwargs)

    Signature = collections.namedtuple(
        "Signature",
        [
            "name",
            "signature",
            "def_sig",
            "call_sig",
            "names",
            "n_positional",
            "args",
            "kwargs",
        ],
    )

    @staticmethod
    def _flatten(nestlist, visited):
        """flattens a recursive list of lists that doesn't have cyclic references

        Parameters
        ----------
        nestlist : iterable
            A recursive list of objects to be flattened into a single iterable

        visited : set
            A set of object ids which have been walked -- initialize with an
            empty set

        Yields
        ------
        Non-list objects contained in nestlist

        """
        for thing in nestlist:
            if isinstance(thing, list):
                if id(thing) in visited:
                    raise ValueError("A cycle was found in nestlist.  Be a tree.")
                else:
                    visited.add(id(thing))
                yield from argmap._flatten(thing, visited)
            else:
                yield thing

    _tabs = " " * 64

    @staticmethod
    def _indent(*lines):
        """Indent list of code lines to make executable Python code

        Indents a tree-recursive list of strings, following the rule that one
        space is added to the tab after a line that ends in a colon, and one is
        removed after a line that ends in an hashmark.

        Parameters
        ----------
        *lines : lists and/or strings
            A recursive list of strings to be assembled into properly indented
            code.

        Returns
        -------
        code : str

        Examples
        --------

            argmap._indent(*["try:", "try:", "pass#", "finally:", "pass#", "#",
                             "finally:", "pass#"])

        renders to

            '''try:
             try:
              pass#
             finally:
              pass#
             #
            finally:
             pass#'''
        """
        depth = 0
        for line in argmap._flatten(lines, set()):
            yield f"{argmap._tabs[:depth]}{line}"
            depth += (line[-1:] == ":") - (line[-1:] == "#")
