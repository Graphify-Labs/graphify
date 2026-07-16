"""
Miscellaneous Helpers for NetworkX.

These are not imported into the base networkx namespace but
can be accessed, for example, as

>>> import networkx
>>> networkx.utils.make_list_of_ints({1, 2, 3})
[1, 2, 3]
>>> networkx.utils.arbitrary_element({5, 1, 7})  # doctest: +SKIP
1
"""

import random
import sys
import uuid
import warnings
from collections import defaultdict, deque
from collections.abc import Iterable, Iterator, Sized
from itertools import chain, tee

import networkx as nx

__all__ = [
    "flatten",
    "make_list_of_ints",
    "dict_to_numpy_array",
    "arbitrary_element",
    "pairwise",
    "groups",
    "create_random_state",
    "create_py_random_state",
    "PythonRandomInterface",
    "PythonRandomViaNumpyBits",
    "nodes_equal",
    "edges_equal",
    "graphs_equal",
    "_clear_cache",
]


# some cookbook stuff
# used in deciding whether something is a bunch of nodes, edges, etc.
# see G.add_nodes and others in Graph Class in networkx/base.py


def flatten(obj, result=None):
    """Return flattened version of (possibly nested) iterable object."""
    if not isinstance(obj, Iterable | Sized) or isinstance(obj, str):
        return obj
    if result is None:
        result = []
    for item in obj:
        if not isinstance(item, Iterable | Sized) or isinstance(item, str):
            result.append(item)
        else:
            flatten(item, result)
    return tuple(result)


def make_list_of_ints(sequence):
    """Return list of ints from sequence of integral numbers.

    All elements of the sequence must satisfy int(element) == element
    or a ValueError is raised. Sequence is iterated through once.

    If sequence is a list, the non-int values are replaced with ints.
    So, no new list is created
    """
    if not isinstance(sequence, list):
        result = []
        for i in sequence:
            errmsg = f"sequence is not all integers: {i}"
            try:
                ii = int(i)
            except ValueError:
                raise nx.NetworkXError(errmsg) from None
            if ii != i:
                raise nx.NetworkXError(errmsg)
            result.append(ii)
        return result
    # original sequence is a list... in-place conversion to ints
    for indx, i in enumerate(sequence):
        errmsg = f"sequence is not all integers: {i}"
        if isinstance(i, int):
            continue
        try:
            ii = int(i)
        except ValueError:
            raise nx.NetworkXError(errmsg) from None
        if ii != i:
            raise nx.NetworkXError(errmsg)
        sequence[indx] = ii
    return sequence


def dict_to_numpy_array(d, mapping=None):
    """Convert a dictionary of dictionaries to a numpy array
    with optional mapping."""
    try:
        return _dict_to_numpy_array2(d, mapping)
    except (AttributeError, TypeError):
        # AttributeError is when no mapping was provided and v.keys() fails.
        # TypeError is when a mapping was provided and d[k1][k2] fails.
        return _dict_to_numpy_array1(d, mapping)


def _dict_to_numpy_array2(d, mapping=None):
    """Convert a dictionary of dictionaries to a 2d numpy array
    with optional mapping.

    """
    import numpy as np

    if mapping is None:
        s = set(d.keys())
        for k, v in d.items():
            s.update(v.keys())
        mapping = dict(zip(s, range(len(s))))
    n = len(mapping)
    a = np.zeros((n, n))
    for k1, i in mapping.items():
        for k2, j in mapping.items():
            try:
                a[i, j] = d[k1][k2]
            except KeyError:
                pass
    return a


def _dict_to_numpy_array1(d, mapping=None):
    """Convert a dictionary of numbers to a 1d numpy array with optional mapping."""
    import numpy as np

    if mapping is None:
        s = set(d.keys())
        mapping = dict(zip(s, range(len(s))))
    n = len(mapping)
    a = np.zeros(n)
    for k1, i in mapping.items():
        i = mapping[k1]
        a[i] = d[k1]
    return a


def arbitrary_element(iterable):
    """Returns an arbitrary element of `iterable` without removing it.

    This is most useful for "peeking" at an arbitrary element of a set,
    but can be used for any list, dictionary, etc., as well.

    Parameters
    ----------
    iterable : `abc.collections.Iterable` instance
        Any object that implements ``__iter__``, e.g. set, dict, list, tuple,
        etc.

    Returns
    -------
    The object that results from ``next(iter(iterable))``

    Raises
    ------
    ValueError
        If `iterable` is an iterator (because the current implementation of
        this function would consume an element from the iterator).

    Examples
    --------
    Arbitrary elements from common Iterable objects:

    >>> nx.utils.arbitrary_element([1, 2, 3])  # list
    1
    >>> nx.utils.arbitrary_element((1, 2, 3))  # tuple
    1
    >>> nx.utils.arbitrary_element({1, 2, 3})  # set
    1
    >>> d = {k: v for k, v in zip([1, 2, 3], [3, 2, 1])}
    >>> nx.utils.arbitrary_element(d)  # dict_keys
    1
    >>> nx.utils.arbitrary_element(d.values())  # dict values
    3

    `str` is also an Iterable:

    >>> nx.utils.arbitrary_element("hello")
    'h'

    :exc:`ValueError` is raised if `iterable` is an iterator:

    >>> iterator = iter([1, 2, 3])  # Iterator, *not* Iterable
    >>> nx.utils.arbitrary_element(iterator)
    Traceback (most recent call last):
        ...
    ValueError: cannot return an arbitrary item from an iterator

    Notes
    -----
    This function does not return a *random* element. If `iterable` is
    ordered, sequential calls will return the same value::

        >>> l = [1, 2, 3]
        >>> nx.utils.arbitrary_element(l)
        1
        >>> nx.utils.arbitrary_element(l)
        1

    """
    if isinstance(iterable, Iterator):
        raise ValueError("cannot return an arbitrary item from an iterator")
    # Another possible implementation is ``for x in iterable: return x``.
    return next(iter(iterable))


# Recipe from the itertools documentation.
def pairwise(iterable, cyclic=False):
    "s -> (s0, s1), (s1, s2), (s2, s3), ..."
    a, b = tee(iterable)
    first = next(b, None)
    if cyclic is True:
        return zip(a, chain(b, (first,)))
    return zip(a, b)


def groups(many_to_one):
    """Converts a many-to-one mapping into a one-to-many mapping.

    `many_to_one` must be a dictionary whose keys and values are all
    :term:`hashable`.

    The return value is a dictionary mapping values from `many_to_one`
    to sets of keys from `many_to_one` that have that value.

    Examples
    --------
    >>> from networkx.utils import groups
    >>> many_to_one = {"a": 1, "b": 1, "c": 2, "d": 3, "e": 3}
    >>> groups(many_to_one)  # doctest: +SKIP
    {1: {'a', 'b'}, 2: {'c'}, 3: {'e', 'd'}}
    """
    one_to_many = defaultdict(set)
    for v, k in many_to_one.items():
        one_to_many[k].add(v)
    return dict(one_to_many)


def create_random_state(random_state=None):
    """Returns a numpy.random.RandomState or numpy.random.Generator instance
    depending on input.

    Parameters
    ----------
    random_state : int or NumPy RandomState or Generator instance, optional (default=None)
        If int, return a numpy.random.RandomState instance set with seed=int.
        if `numpy.random.RandomState` instance, return it.
        if `numpy.random.Generator` instance, return it.
        if None or numpy.random, return the global random number generator used
        by numpy.random.
    """
    import numpy as np

    if random_state is None or random_state is np.random:
        return np.random.mtrand._rand
    if isinstance(random_state, np.random.RandomState):
        return random_state
    if isinstance(random_state, int):
        return np.random.RandomState(random_state)
    if isinstance(random_state, np.random.Generator):
        return random_state
    msg = (
        f"{random_state} cannot be used to create a numpy.random.RandomState or\n"
        "numpy.random.Generator instance"
    )
    raise ValueError(msg)


class PythonRandomViaNumpyBits(random.Random):
    """Provide the random.random algorithms using a numpy.random bit generator

    The intent is to allow people to contribute code that uses Python's random
    library, but still allow users to provide a single easily controlled random
    bit-stream for all work with NetworkX. This implementation is based on helpful
    comments and code from Robert Kern on NumPy's GitHub Issue #24458.

    This implementation supersedes that of `PythonRandomInterface` which rewrote
    methods to account for subtle differences in API between `random` and
    `numpy.random`. Instead this subclasses `random.Random` and overwrites
    the methods `random`, `getrandbits`, `getstate`, `setstate` and `seed`.
    It makes them use the rng values from an input numpy `RandomState` or `Generator`.
    Those few methods allow the rest of the `random.Random` methods to provide
    the API interface of `random.random` while using randomness generated by
    a numpy generator.
    """

    def __init__(self, rng=None):
        try:
            import numpy as np
        except ImportError:
            msg = "numpy not found, only random.random available."
            warnings.warn(msg, ImportWarning)

        if rng is None:
            self._rng = np.random.mtrand._rand
        else:
            self._rng = rng

        # Not necessary, given our overriding of gauss() below, but it's
        # in the superclass and nominally public, so initialize it here.
        self.gauss_next = None

    def random(self):
        """Get the next random number in the range 0.0 <= X < 1.0."""
        return self._rng.random()

    def getrandbits(self, k):
        """getrandbits(k) -> x.  Generates an int with k random bits."""
        if k < 0:
            raise ValueError("number of bits must be non-negative")
        numbytes = (k + 7) // 8  # bits / 8 and rounded up
        x = int.from_bytes(self._rng.bytes(numbytes), "big")
        return x >> (numbytes * 8 - k)  # trim excess bits

    def getstate(self):
        return self._rng.__getstate__()

    def setstate(self, state):
        self._rng.__setstate__(state)

    def seed(self, *args, **kwds):
        "Do nothing override method."
        raise NotImplementedError("seed() not implemented in PythonRandomViaNumpyBits")


##################################################################
class PythonRandomInterface:
    """PythonRandomInterface is included for backward compatibility
    New code should use PythonRandomViaNumpyBits instead.
    """

    def __init__(self, rng=None):
        try:
            import numpy as np
        except ImportError:
            msg = "numpy not found, only random.random available."
            warnings.warn(msg, ImportWarning)

        if rng is None:
            self._rng = np.random.mtrand._rand
        else:
            self._rng = rng

    def random(self):
        return self._rng.random()

    def uniform(self, a, b):
        return a + (b - a) * self._rng.random()

    def randrange(self, a, b=None):
        import numpy as np

        if b is None:
            a, b = 0, a
        if b > 9223372036854775807:  # from np.iinfo(np.int64).max
            tmp_rng = PythonRandomViaNumpyBits(self._rng)
            return tmp_rng.randrange(a, b)

        if isinstance(self._rng, np.random.Generator):
            return self._rng.integers(a, b)
        return self._rng.randint(a, b)

    # NOTE: the numpy implementations of `choice` don't support strings, so
    # this cannot be replaced with self._rng.choice
    def choice(self, seq):
        import numpy as np

        if isinstance(self._rng, np.random.Generator):
            idx = self._rng.integers(0, len(seq))
        else:
            idx = self._rng.randint(0, len(seq))
        return seq[idx]

    def gauss(self, mu, sigma):
        return self._rng.normal(mu, sigma)

    def shuffle(self, seq):
        return self._rng.shuffle(seq)

    #    Some methods don't match API for numpy RandomState.
    #    Commented out versions are not used by NetworkX

    def sample(self, seq, k):
        return self._rng.choice(list(seq), size=(k,), replace=False)

    def randint(self, a, b):
        import numpy as np

        if b > 9223372036854775807:  # from np.iinfo(np.int64).max
            tmp_rng = PythonRandomViaNumpyBits(self._rng)
            return tmp_rng.randint(a, b)

        if isinstance(self._rng, np.random.Generator):
            return self._rng.integers(a, b + 1)
        return self._rng.randint(a, b + 1)

    #    exponential as expovariate with 1/argument,
    def expovariate(self, scale):
        return self._rng.exponential(1 / scale)

    #    pareto as paretovariate with 1/argument,
    def paretovariate(self, shape):
        return self._rng.pareto(shape)


#    weibull as weibullvariate multiplied by beta,
#    def weibullvariate(self, alpha, beta):
#        return self._rng.weibull(alpha) * beta
#
#    def triangular(self, low, high, mode):
#        return self._rng.triangular(low, mode, high)
#
#    def choices(self, seq, weights=None, cum_weights=None, k=1):
#        return self._rng.choice(seq


def create_py_random_state(random_state=None):
    """Returns a random.Random instance depending on input.

    Parameters
    ----------
    random_state : int or random number generator or None (default=None)
        - If int, return a `random.Random` instance set with seed=int.
        - If `random.Random` instance, return it.
        - If None or the `np.random` package, return the global random number
          generator used by `np.random`.
        - If an `np.random.Generator` instance, or the `np.random` package, or
          the global numpy random number generator, then return it.
          wrapped in a `PythonRandomViaNumpyBits` class.
        - If a `PythonRandomViaNumpyBits` instance, return it.
        - If a `PythonRandomInterface` instance, return it.
        - If a `np.random.RandomState` instance and not the global numpy default,
          return it wrapped in `PythonRandomInterface` for backward bit-stream
          matching with legacy code.

    Notes
    -----
    - A diagram intending to illustrate the relationships behind our support
      for numpy random numbers is called
      `NetworkX Numpy Random Numbers <https://excalidraw.com/#room=b5303f2b03d3af7ccc6a,e5ZDIWdWWCTTsg8OqoRvPA>`_.
    - More discussion about this support also appears in
      `gh-6869#comment <https://github.com/networkx/networkx/pull/6869#issuecomment-1944799534>`_.
    - Wrappers of numpy.random number generators allow them to mimic the Python random
      number generation algorithms. For example, Python can create arbitrarily large
      random ints, and the wrappers use Numpy bit-streams with CPython's random module
      to choose arbitrarily large random integers too.
    - We provide two wrapper classes:
      `PythonRandomViaNumpyBits` is usually what you want and is always used for
      `np.Generator` instances. But for users who need to recreate random numbers
      produced in NetworkX 3.2 or earlier, we maintain the `PythonRandomInterface`
      wrapper as well. We use it only used if passed a (non-default) `np.RandomState`
      instance pre-initialized from a seed. Otherwise the newer wrapper is used.
    """
    if random_state is None or random_state is random:
        return random._inst
    if isinstance(random_state, random.Random):
        return random_state
    if isinstance(random_state, int):
        return random.Random(random_state)

    try:
        import numpy as np
    except ImportError:
        pass
    else:
        if isinstance(random_state, PythonRandomInterface | PythonRandomViaNumpyBits):
            return random_state
        if isinstance(random_state, np.random.Generator):
            return PythonRandomViaNumpyBits(random_state)
        if random_state is np.random:
            return PythonRandomViaNumpyBits(np.random.mtrand._rand)

        if isinstance(random_state, np.random.RandomState):
            if random_state is np.random.mtrand._rand:
                return PythonRandomViaNumpyBits(random_state)
            # Only need older interface if specially constructed RandomState used
            return PythonRandomInterface(random_state)

    msg = f"{random_state} cannot be used to generate a random.Random instance"
    raise ValueError(msg)


def nodes_equal(nodes1, nodes2):
    """Check if nodes are equal.

    Equality here means equal as Python objects.
    Node data must match if included.
    The order of nodes is not relevant.

    Parameters
    ----------
    nodes1, nodes2 : iterables of nodes, or (node, datadict) tuples

    Returns
    -------
    bool
        True if nodes are equal, False otherwise.
    """
    nlist1 = list(nodes1)
    nlist2 = list(nodes2)
    try:
        d1 = dict(nlist1)
        d2 = dict(nlist2)
    except (ValueError, TypeError):
        d1 = dict.fromkeys(nlist1)
        d2 = dict.fromkeys(nlist2)
    return d1 == d2


def edges_equal(edges1, edges2):
    """Check if edges are equal.

    Equality here means equal as Python objects.
    Edge data must match if included.
    The order of the edges is not relevant.

    Parameters
    ----------
    edges1, edges2 : iterables of with u, v nodes as
        edge tuples (u, v), or
        edge tuples with data dicts (u, v, d), or
        edge tuples with keys and data dicts (u, v, k, d)

    Returns
    -------
    bool
        True if edges are equal, False otherwise.
    """
    from collections import defaultdict

    d1 = defaultdict(dict)
    d2 = defaultdict(dict)
    c1 = 0
    for c1, e in enumerate(edges1):
        u, v = e[0], e[1]
        data = [e[2:]]
        if v in d1[u]:
            data = d1[u][v] + data
        d1[u][v] = data
        d1[v][u] = data
    c2 = 0
    for c2, e in enumerate(edges2):
        u, v = e[0], e[1]
        data = [e[2:]]
        if v in d2[u]:
            data = d2[u][v] + data
        d2[u][v] = data
        d2[v][u] = data
    if c1 != c2:
        return False
    # can check one direction because lengths are the same.
    for n, nbrdict in d1.items():
        for nbr, datalist in nbrdict.items():
            if n not in d2:
                return False
            if nbr not in d2[n]:
                return False
            d2datalist = d2[n][nbr]
            for data in datalist:
                if datalist.count(data) != d2datalist.count(data):
                    return False
    return True


def graphs_equal(graph1, graph2):
    """Check if graphs are equal.

    Equality here means equal as Python objects (not isomorphism).
    Node, edge and graph data must match.

    Parameters
    ----------
    graph1, graph2 : graph

    Returns
    -------
    bool
        True if graphs are equal, False otherwise.
    """
    return (
        graph1.adj == graph2.adj
        and graph1.nodes == graph2.nodes
        and graph1.graph == graph2.graph
    )


def _clear_cache(G):
    """Clear the cache of a graph (currently stores converted graphs).

    Caching is controlled via ``nx.config.cache_converted_graphs`` configuration.
    """
    if cache := getattr(G, "__networkx_cache__", None):
        cache.clear()


def check_create_using(create_using, *, directed=None, multigraph=None, default=None):
    """Assert that create_using has good properties

    This checks for desired directedness and multi-edge properties.
    It returns `create_using` unless that is `None` when it returns
    the optionally specified default value.

    Parameters
    ----------
    create_using : None, graph class or instance
        The input value of create_using for a function.
    directed : None or bool
        Whether to check `create_using.is_directed() == directed`.
        If None, do not assert directedness.
    multigraph : None or bool
        Whether to check `create_using.is_multigraph() == multigraph`.
        If None, do not assert multi-edge property.
    default : None or graph class
        The graph class to return if create_using is None.

    Returns
    -------
    create_using : graph class or instance
        The provided graph class or instance, or if None, the `default` value.

    Raises
    ------
    NetworkXError
        When `create_using` doesn't match the properties specified by `directed`
        or `multigraph` parameters.
    """
    if default is None:
        default = nx.Graph
    G = create_using if create_using is not None else default

    G_directed = G.is_directed(None) if isinstance(G, type) else G.is_directed()
    G_multigraph = G.is_multigraph(None) if isinstance(G, type) else G.is_multigraph()

    if directed is not None:
        if directed and not G_directed:
            raise nx.NetworkXError("create_using must be directed")
        if not directed and G_directed:
            raise nx.NetworkXError("create_using must not be directed")

    if multigraph is not None:
        if multigraph and not G_multigraph:
            raise nx.NetworkXError("create_using must be a multi-graph")
        if not multigraph and G_multigraph:
            raise nx.NetworkXError("create_using must not be a multi-graph")
    return G
