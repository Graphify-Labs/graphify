"""Views of core data structures such as nested Mappings (e.g. dict-of-dicts).
These ``Views`` often restrict element access, with either the entire view or
layers of nested mappings being read-only.
"""

from collections.abc import Mapping

__all__ = [
    "AtlasView",
    "AdjacencyView",
    "MultiAdjacencyView",
    "UnionAtlas",
    "UnionAdjacency",
    "UnionMultiInner",
    "UnionMultiAdjacency",
    "FilterAtlas",
    "FilterAdjacency",
    "FilterMultiInner",
    "FilterMultiAdjacency",
]


class AtlasView(Mapping):
    """An AtlasView is a Read-only Mapping of Mappings.

    It is a View into a dict-of-dict data structure.
    The inner level of dict is read-write. But the
    outer level is read-only.

    See Also
    ========
    AdjacencyView: View into dict-of-dict-of-dict
    MultiAdjacencyView: View into dict-of-dict-of-dict-of-dict
    """

    __slots__ = ("_atlas",)

    def __getstate__(self):
        return {"_atlas": self._atlas}

    def __setstate__(self, state):
        self._atlas = state["_atlas"]

    def __init__(self, d):
        self._atlas = d

    def __len__(self):
        return len(self._atlas)

    def __iter__(self):
        return iter(self._atlas)

    def __getitem__(self, key):
        return self._atlas[key]

    def copy(self):
        return {n: self[n].copy() for n in self._atlas}

    def __str__(self):
        return str(self._atlas)  # {nbr: self[nbr] for nbr in self})

    def __repr__(self):
        return f"{self.__class__.__name__}({self._atlas!r})"


class AdjacencyView(AtlasView):
    """An AdjacencyView is a Read-only Map of Maps of Maps.

    It is a View into a dict-of-dict-of-dict data structure.
    The inner level of dict is read-write. But the
    outer levels are read-only.

    See Also
    ========
    AtlasView: View into dict-of-dict
    MultiAdjacencyView: View into dict-of-dict-of-dict-of-dict
    """

    __slots__ = ()  # Still uses AtlasView slots names _atlas

    def __getitem__(self, name):
        return AtlasView(self._atlas[name])

    def copy(self):
        return {n: self[n].copy() for n in self._atlas}


class MultiAdjacencyView(AdjacencyView):
    """An MultiAdjacencyView is a Read-only Map of Maps of Maps of Maps.

    It is a View into a dict-of-dict-of-dict-of-dict data structure.
    The inner level of dict is read-write. But the
    outer levels are read-only.

    See Also
    ========
    AtlasView: View into dict-of-dict
    AdjacencyView: View into dict-of-dict-of-dict
    """

    __slots__ = ()  # Still uses AtlasView slots names _atlas

    def __getitem__(self, name):
        return AdjacencyView(self._atlas[name])

    def copy(self):
        return {n: self[n].copy() for n in self._atlas}


class UnionAtlas(Mapping):
    """A read-only union of two atlases (dict-of-dict).

    The two dict-of-dicts represent the inner dict of
    an Adjacency:  `G.succ[node]` and `G.pred[node]`.
    The inner level of dict of both hold attribute key:value
    pairs and is read-write. But the outer level is read-only.

    See Also
    ========
    UnionAdjacency: View into dict-of-dict-of-dict
    UnionMultiAdjacency: View into dict-of-dict-of-dict-of-dict
    """

    __slots__ = ("_succ", "_pred")

    def __getstate__(self):
        return {"_succ": self._succ, "_pred": self._pred}

    def __setstate__(self, state):
        self._succ = state["_succ"]
        self._pred = state["_pred"]

    def __init__(self, succ, pred):
        self._succ = succ
        self._pred = pred

    def __len__(self):
        return len(self._succ.keys() | self._pred.keys())

    def __iter__(self):
        return iter(set(self._succ.keys()) | set(self._pred.keys()))

    def __getitem__(self, key):
        try:
            return self._succ[key]
        except KeyError:
            return self._pred[key]

    def copy(self):
        result = {nbr: dd.copy() for nbr, dd in self._succ.items()}
        for nbr, dd in self._pred.items():
            if nbr in result:
                result[nbr].update(dd)
            else:
                result[nbr] = dd.copy()
        return result

    def __str__(self):
        return str({nbr: self[nbr] for nbr in self})

    def __repr__(self):
        return f"{self.__class__.__name__}({self._succ!r}, {self._pred!r})"


class UnionAdjacency(Mapping):
    """A read-only union of dict Adjacencies as a Map of Maps of Maps.

    The two input dict-of-dict-of-dicts represent the union of
    `G.succ` and `G.pred`. Return values are UnionAtlas
    The inner level of dict is read-write. But the
    middle and outer levels are read-only.

    succ : a dict-of-dict-of-dict {node: nbrdict}
    pred : a dict-of-dict-of-dict {node: nbrdict}
    The keys for the two dicts should be the same

    See Also
    ========
    UnionAtlas: View into dict-of-dict
    UnionMultiAdjacency: View into dict-of-dict-of-dict-of-dict
    """

    __slots__ = ("_succ", "_pred")

    def __getstate__(self):
        return {"_succ": self._succ, "_pred": self._pred}

    def __setstate__(self, state):
        self._succ = state["_succ"]
        self._pred = state["_pred"]

    def __init__(self, succ, pred):
        # keys must be the same for two input dicts
        assert len(set(succ.keys()) ^ set(pred.keys())) == 0
        self._succ = succ
        self._pred = pred

    def __len__(self):
        return len(self._succ)  # length of each dict should be the same

    def __iter__(self):
        return iter(self._succ)

    def __getitem__(self, nbr):
        return UnionAtlas(self._succ[nbr], self._pred[nbr])

    def copy(self):
        return {n: self[n].copy() for n in self._succ}

    def __str__(self):
        return str({nbr: self[nbr] for nbr in self})

    def __repr__(self):
        return f"{self.__class__.__name__}({self._succ!r}, {self._pred!r})"


class UnionMultiInner(UnionAtlas):
    """A read-only union of two inner dicts of MultiAdjacencies.

    The two input dict-of-dict-of-dicts represent the union of
    `G.succ[node]` and `G.pred[node]` for MultiDiGraphs.
    Return values are UnionAtlas.
    The inner level of dict is read-write. But the outer levels are read-only.

    See Also
    ========
    UnionAtlas: View into dict-of-dict
    UnionAdjacency:  View into dict-of-dict-of-dict
    UnionMultiAdjacency:  View into dict-of-dict-of-dict-of-dict
    """

    __slots__ = ()  # Still uses UnionAtlas slots names _succ, _pred

    def __getitem__(self, node):
        in_succ = node in self._succ
        in_pred = node in self._pred
        if in_succ:
            if in_pred:
                return UnionAtlas(self._succ[node], self._pred[node])
            return UnionAtlas(self._succ[node], {})
        return UnionAtlas({}, self._pred[node])

    def copy(self):
        nodes = set(self._succ.keys()) | set(self._pred.keys())
        return {n: self[n].copy() for n in nodes}


class UnionMultiAdjacency(UnionAdjacency):
    """A read-only union of two dict MultiAdjacencies.

    The two input dict-of-dict-of-dict-of-dicts represent the union of
    `G.succ` and `G.pred` for MultiDiGraphs. Return values are UnionAdjacency.
    The inner level of dict is read-write. But the outer levels are read-only.

    See Also
    ========
    UnionAtlas:  View into dict-of-dict
    UnionMultiInner:  View into dict-of-dict-of-dict
    """

    __slots__ = ()  # Still uses UnionAdjacency slots names _succ, _pred

    def __getitem__(self, node):
        return UnionMultiInner(self._succ[node], self._pred[node])


class FilterAtlas(Mapping):  # nodedict, nbrdict, keydict
    """A read-only Mapping of Mappings with filtering criteria for nodes.

    It is a view into a dict-of-dict data structure, and it selects only
    nodes that meet the criteria defined by ``NODE_OK``.

    See Also
    ========
    FilterAdjacency
    FilterMultiInner
    FilterMultiAdjacency
    """

    def __init__(self, d, NODE_OK):
        self._atlas = d
        self.NODE_OK = NODE_OK

    def __len__(self):
        # check whether NODE_OK stores the number of nodes as `length`
        # or the nodes themselves as a set `nodes`. If not, count the nodes.
        if hasattr(self.NODE_OK, "length"):
            return self.NODE_OK.length
        if hasattr(self.NODE_OK, "nodes"):
            return len(self.NODE_OK.nodes & self._atlas.keys())
        return sum(1 for n in self._atlas if self.NODE_OK(n))

    def __iter__(self):
        try:  # check that NODE_OK has attr 'nodes'
            node_ok_shorter = 2 * len(self.NODE_OK.nodes) < len(self._atlas)
        except AttributeError:
            node_ok_shorter = False
        if node_ok_shorter:
            return (n for n in self.NODE_OK.nodes if n in self._atlas)
        return (n for n in self._atlas if self.NODE_OK(n))

    def __getitem__(self, key):
        if key in self._atlas and self.NODE_OK(key):
            return self._atlas[key]
        raise KeyError(f"Key {key} not found")

    def __str__(self):
        return str({nbr: self[nbr] for nbr in self})

    def __repr__(self):
        return f"{self.__class__.__name__}({self._atlas!r}, {self.NODE_OK!r})"


class FilterAdjacency(Mapping):  # edgedict
    """A read-only Mapping of Mappings with filtering criteria for nodes and edges.

    It is a view into a dict-of-dict-of-dict data structure, and it selects nodes
    and edges that satisfy specific criteria defined by ``NODE_OK`` and ``EDGE_OK``,
    respectively.

    See Also
    ========
    FilterAtlas
    FilterMultiInner
    FilterMultiAdjacency
    """

    def __init__(self, d, NODE_OK, EDGE_OK):
        self._atlas = d
        self.NODE_OK = NODE_OK
        self.EDGE_OK = EDGE_OK

    def __len__(self):
        # check whether NODE_OK stores the number of nodes as `length`
        # or the nodes themselves as a set `nodes`. If not, count the nodes.
        if hasattr(self.NODE_OK, "length"):
            return self.NODE_OK.length
        if hasattr(self.NODE_OK, "nodes"):
            return len(self.NODE_OK.nodes & self._atlas.keys())
        return sum(1 for n in self._atlas if self.NODE_OK(n))

    def __iter__(self):
        try:  # check that NODE_OK has attr 'nodes'
            node_ok_shorter = 2 * len(self.NODE_OK.nodes) < len(self._atlas)
        except AttributeError:
            node_ok_shorter = False
        if node_ok_shorter:
            return (n for n in self.NODE_OK.nodes if n in self._atlas)
        return (n for n in self._atlas if self.NODE_OK(n))

    def __getitem__(self, node):
        if node in self._atlas and self.NODE_OK(node):

            def new_node_ok(nbr):
                return self.NODE_OK(nbr) and self.EDGE_OK(node, nbr)

            return FilterAtlas(self._atlas[node], new_node_ok)
        raise KeyError(f"Key {node} not found")

    def __str__(self):
        return str({nbr: self[nbr] for nbr in self})

    def __repr__(self):
        name = self.__class__.__name__
        return f"{name}({self._atlas!r}, {self.NODE_OK!r}, {self.EDGE_OK!r})"


class FilterMultiInner(FilterAdjacency):  # muliedge_seconddict
    """A read-only Mapping of Mappings with filtering criteria for nodes and edges.

    It is a view into a dict-of-dict-of-dict-of-dict data structure, and it selects nodes
    and edges that meet specific criteria defined by ``NODE_OK`` and ``EDGE_OK``.

    See Also
    ========
    FilterAtlas
    FilterAdjacency
    FilterMultiAdjacency
    """

    def __iter__(self):
        try:  # check that NODE_OK has attr 'nodes'
            node_ok_shorter = 2 * len(self.NODE_OK.nodes) < len(self._atlas)
        except AttributeError:
            node_ok_shorter = False
        if node_ok_shorter:
            my_nodes = (n for n in self.NODE_OK.nodes if n in self._atlas)
        else:
            my_nodes = (n for n in self._atlas if self.NODE_OK(n))
        for n in my_nodes:
            some_keys_ok = False
            for key in self._atlas[n]:
                if self.EDGE_OK(n, key):
                    some_keys_ok = True
                    break
            if some_keys_ok is True:
                yield n

    def __getitem__(self, nbr):
        if nbr in self._atlas and self.NODE_OK(nbr):

            def new_node_ok(key):
                return self.EDGE_OK(nbr, key)

            return FilterAtlas(self._atlas[nbr], new_node_ok)
        raise KeyError(f"Key {nbr} not found")


class FilterMultiAdjacency(FilterAdjacency):  # multiedgedict
    """A read-only Mapping of Mappings with filtering criteria
    for nodes and edges.

    It is a view into a dict-of-dict-of-dict-of-dict data structure,
    and it selects nodes and edges that satisfy specific criteria
    defined by ``NODE_OK`` and ``EDGE_OK``, respectively.

    See Also
    ========
    FilterAtlas
    FilterAdjacency
    FilterMultiInner
    """

    def __getitem__(self, node):
        if node in self._atlas and self.NODE_OK(node):

            def edge_ok(nbr, key):
                return self.NODE_OK(nbr) and self.EDGE_OK(node, nbr, key)

            return FilterMultiInner(self._atlas[node], self.NODE_OK, edge_ok)
        raise KeyError(f"Key {node} not found")
