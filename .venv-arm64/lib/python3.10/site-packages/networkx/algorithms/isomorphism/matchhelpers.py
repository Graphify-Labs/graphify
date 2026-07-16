"""Functions which help end users define customize node_match and
edge_match functions to use during isomorphism checks.
"""

import math
import types
from itertools import permutations

__all__ = [
    "categorical_node_match",
    "categorical_edge_match",
    "categorical_multiedge_match",
    "numerical_node_match",
    "numerical_edge_match",
    "numerical_multiedge_match",
    "generic_node_match",
    "generic_edge_match",
    "generic_multiedge_match",
]


def copyfunc(f, name=None):
    """Returns a deepcopy of a function."""
    return types.FunctionType(
        f.__code__, f.__globals__, name or f.__name__, f.__defaults__, f.__closure__
    )


def allclose(x, y, rtol=1.0000000000000001e-05, atol=1e-08):
    """Returns True if x and y are sufficiently close, elementwise.

    Parameters
    ----------
    rtol : float
        The relative error tolerance.
    atol : float
        The absolute error tolerance.

    """
    # assume finite weights, see numpy.allclose() for reference
    return all(math.isclose(xi, yi, rel_tol=rtol, abs_tol=atol) for xi, yi in zip(x, y))


categorical_doc = """
Returns a comparison function for a categorical node attribute.

The value(s) of the attr(s) must be hashable and comparable via the ==
operator since they are placed into a set([]) object.  If the sets from
G1 and G2 are the same, then the constructed function returns True.

Parameters
----------
attr : string | list
    The categorical node attribute to compare, or a list of categorical
    node attributes to compare.
default : value | list
    The default value for the categorical node attribute, or a list of
    default values for the categorical node attributes.

Returns
-------
match : function
    The customized, categorical `node_match` function.

Examples
--------
>>> import networkx.algorithms.isomorphism as iso
>>> nm = iso.categorical_node_match("size", 1)
>>> nm = iso.categorical_node_match(["color", "size"], ["red", 2])

"""


def categorical_node_match(attr, default):
    if isinstance(attr, str):

        def match(data1, data2):
            return data1.get(attr, default) == data2.get(attr, default)

    else:
        attrs = list(zip(attr, default))  # Python 3

        def match(data1, data2):
            return all(data1.get(attr, d) == data2.get(attr, d) for attr, d in attrs)

    return match


categorical_edge_match = copyfunc(categorical_node_match, "categorical_edge_match")


def categorical_multiedge_match(attr, default):
    if isinstance(attr, str):

        def match(datasets1, datasets2):
            values1 = {data.get(attr, default) for data in datasets1.values()}
            values2 = {data.get(attr, default) for data in datasets2.values()}
            return values1 == values2

    else:
        attrs = list(zip(attr, default))  # Python 3

        def match(datasets1, datasets2):
            values1 = set()
            for data1 in datasets1.values():
                x = tuple(data1.get(attr, d) for attr, d in attrs)
                values1.add(x)
            values2 = set()
            for data2 in datasets2.values():
                x = tuple(data2.get(attr, d) for attr, d in attrs)
                values2.add(x)
            return values1 == values2

    return match


# Docstrings for categorical functions.
categorical_node_match.__doc__ = categorical_doc
categorical_edge_match.__doc__ = categorical_doc.replace("node", "edge")
tmpdoc = categorical_doc.replace("node", "edge")
tmpdoc = tmpdoc.replace("categorical_edge_match", "categorical_multiedge_match")
categorical_multiedge_match.__doc__ = tmpdoc


numerical_doc = """
Returns a comparison function for a numerical node attribute.

The value(s) of the attr(s) must be numerical and sortable.  If the
sorted list of values from G1 and G2 are the same within some
tolerance, then the constructed function returns True.

Parameters
----------
attr : string | list
    The numerical node attribute to compare, or a list of numerical
    node attributes to compare.
default : value | list
    The default value for the numerical node attribute, or a list of
    default values for the numerical node attributes.
rtol : float
    The relative error tolerance.
atol : float
    The absolute error tolerance.

Returns
-------
match : function
    The customized, numerical `node_match` function.

Examples
--------
>>> import networkx.algorithms.isomorphism as iso
>>> nm = iso.numerical_node_match("weight", 1.0)
>>> nm = iso.numerical_node_match(["weight", "linewidth"], [0.25, 0.5])

"""


def numerical_node_match(attr, default, rtol=1.0000000000000001e-05, atol=1e-08):
    if isinstance(attr, str):

        def match(data1, data2):
            return math.isclose(
                data1.get(attr, default),
                data2.get(attr, default),
                rel_tol=rtol,
                abs_tol=atol,
            )

    else:
        attrs = list(zip(attr, default))  # Python 3

        def match(data1, data2):
            values1 = [data1.get(attr, d) for attr, d in attrs]
            values2 = [data2.get(attr, d) for attr, d in attrs]
            return allclose(values1, values2, rtol=rtol, atol=atol)

    return match


numerical_edge_match = copyfunc(numerical_node_match, "numerical_edge_match")


def numerical_multiedge_match(attr, default, rtol=1.0000000000000001e-05, atol=1e-08):
    if isinstance(attr, str):

        def match(datasets1, datasets2):
            values1 = sorted(data.get(attr, default) for data in datasets1.values())
            values2 = sorted(data.get(attr, default) for data in datasets2.values())
            return allclose(values1, values2, rtol=rtol, atol=atol)

    else:
        attrs = list(zip(attr, default))  # Python 3

        def match(datasets1, datasets2):
            values1 = []
            for data1 in datasets1.values():
                x = tuple(data1.get(attr, d) for attr, d in attrs)
                values1.append(x)
            values2 = []
            for data2 in datasets2.values():
                x = tuple(data2.get(attr, d) for attr, d in attrs)
                values2.append(x)
            values1.sort()
            values2.sort()
            for xi, yi in zip(values1, values2):
                if not allclose(xi, yi, rtol=rtol, atol=atol):
                    return False
            else:
                return True

    return match


# Docstrings for numerical functions.
numerical_node_match.__doc__ = numerical_doc
numerical_edge_match.__doc__ = numerical_doc.replace("node", "edge")
tmpdoc = numerical_doc.replace("node", "edge")
tmpdoc = tmpdoc.replace("numerical_edge_match", "numerical_multiedge_match")
numerical_multiedge_match.__doc__ = tmpdoc


generic_doc = """
Returns a comparison function for a generic attribute.

The value(s) of the attr(s) are compared using the specified
operators. If all the attributes are equal, then the constructed
function returns True.

Parameters
----------
attr : string | list
    The node attribute to compare, or a list of node attributes
    to compare.
default : value | list
    The default value for the node attribute, or a list of
    default values for the node attributes.
op : callable | list
    The operator to use when comparing attribute values, or a list
    of operators to use when comparing values for each attribute.

Returns
-------
match : function
    The customized, generic `node_match` function.

Examples
--------
>>> from operator import eq
>>> from math import isclose
>>> from networkx.algorithms.isomorphism import generic_node_match
>>> nm = generic_node_match("weight", 1.0, isclose)
>>> nm = generic_node_match("color", "red", eq)
>>> nm = generic_node_match(["weight", "color"], [1.0, "red"], [isclose, eq])

"""


def generic_node_match(attr, default, op):
    if isinstance(attr, str):

        def match(data1, data2):
            return op(data1.get(attr, default), data2.get(attr, default))

    else:
        attrs = list(zip(attr, default, op))  # Python 3

        def match(data1, data2):
            for attr, d, operator in attrs:
                if not operator(data1.get(attr, d), data2.get(attr, d)):
                    return False
            else:
                return True

    return match


generic_edge_match = copyfunc(generic_node_match, "generic_edge_match")


def generic_multiedge_match(attr, default, op):
    """Returns a comparison function for a generic attribute.

    The value(s) of the attr(s) are compared using the specified
    operators. If all the attributes are equal, then the constructed
    function returns True. Potentially, the constructed edge_match
    function can be slow since it must verify that no isomorphism
    exists between the multiedges before it returns False.

    Parameters
    ----------
    attr : string | list
        The edge attribute to compare, or a list of node attributes
        to compare.
    default : value | list
        The default value for the edge attribute, or a list of
        default values for the edgeattributes.
    op : callable | list
        The operator to use when comparing attribute values, or a list
        of operators to use when comparing values for each attribute.

    Returns
    -------
    match : function
        The customized, generic `edge_match` function.

    Examples
    --------
    >>> from operator import eq
    >>> from math import isclose
    >>> from networkx.algorithms.isomorphism import generic_node_match
    >>> nm = generic_node_match("weight", 1.0, isclose)
    >>> nm = generic_node_match("color", "red", eq)
    >>> nm = generic_node_match(["weight", "color"], [1.0, "red"], [isclose, eq])

    """

    # This is slow, but generic.
    # We must test every possible isomorphism between the edges.
    if isinstance(attr, str):
        attr = [attr]
        default = [default]
        op = [op]
    attrs = list(zip(attr, default))  # Python 3

    def match(datasets1, datasets2):
        values1 = []
        for data1 in datasets1.values():
            x = tuple(data1.get(attr, d) for attr, d in attrs)
            values1.append(x)
        values2 = []
        for data2 in datasets2.values():
            x = tuple(data2.get(attr, d) for attr, d in attrs)
            values2.append(x)
        for vals2 in permutations(values2):
            for xi, yi in zip(values1, vals2):
                if not all(map(lambda x, y, z: z(x, y), xi, yi, op)):
                    # This is not an isomorphism, go to next permutation.
                    break
            else:
                # Then we found an isomorphism.
                return True
        else:
            # Then there are no isomorphisms between the multiedges.
            return False

    return match


# Docstrings for numerical functions.
generic_node_match.__doc__ = generic_doc
generic_edge_match.__doc__ = generic_doc.replace("node", "edge")
