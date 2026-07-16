"""Filter factories to hide or show sets of nodes and edges.

These filters return the function used when creating `SubGraph`.
"""

__all__ = [
    "no_filter",
    "hide_nodes",
    "hide_edges",
    "hide_multiedges",
    "hide_diedges",
    "hide_multidiedges",
    "show_nodes",
    "show_edges",
    "show_multiedges",
    "show_diedges",
    "show_multidiedges",
]


def no_filter(*items):
    """Returns a filter function that always evaluates to True."""
    return True


def hide_nodes(nodes):
    """Returns a filter function that hides specific nodes."""
    nodes = set(nodes)
    return lambda node: node not in nodes


def hide_diedges(edges):
    """Returns a filter function that hides specific directed edges."""
    edges = {(u, v) for u, v in edges}
    return lambda u, v: (u, v) not in edges


def hide_edges(edges):
    """Returns a filter function that hides specific undirected edges."""
    alledges = set(edges) | {(v, u) for (u, v) in edges}
    return lambda u, v: (u, v) not in alledges


def hide_multidiedges(edges):
    """Returns a filter function that hides specific multi-directed edges."""
    edges = {(u, v, k) for u, v, k in edges}
    return lambda u, v, k: (u, v, k) not in edges


def hide_multiedges(edges):
    """Returns a filter function that hides specific multi-undirected edges."""
    alledges = set(edges) | {(v, u, k) for (u, v, k) in edges}
    return lambda u, v, k: (u, v, k) not in alledges


# write show_nodes as a class to make SubGraph pickleable
class show_nodes:
    """Filter class to show specific nodes.

    Attach the set of nodes as an attribute to speed up this commonly used filter

    Note that another allowed attribute for filters is to store the number of nodes
    on the filter as attribute `length` (used in `__len__`). It is a user
    responsibility to ensure this attribute is accurate if present.
    """

    def __init__(self, nodes):
        self.nodes = set(nodes)

    def __call__(self, node):
        return node in self.nodes


def show_diedges(edges):
    """Returns a filter function that shows specific directed edges."""
    edges = {(u, v) for u, v in edges}
    return lambda u, v: (u, v) in edges


def show_edges(edges):
    """Returns a filter function that shows specific undirected edges."""
    alledges = set(edges) | {(v, u) for (u, v) in edges}
    return lambda u, v: (u, v) in alledges


def show_multidiedges(edges):
    """Returns a filter function that shows specific multi-directed edges."""
    edges = {(u, v, k) for u, v, k in edges}
    return lambda u, v, k: (u, v, k) in edges


def show_multiedges(edges):
    """Returns a filter function that shows specific multi-undirected edges."""
    alledges = set(edges) | {(v, u, k) for (u, v, k) in edges}
    return lambda u, v, k: (u, v, k) in alledges
