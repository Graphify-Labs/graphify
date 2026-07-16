"""Generates graphs resembling the Internet Autonomous System network"""

import networkx as nx
from networkx.utils import py_random_state

__all__ = ["random_internet_as_graph"]


def uniform_int_from_avg(a, m, seed):
    """Pick a random integer with uniform probability.

    Returns a random integer uniformly taken from a distribution with
    minimum value 'a' and average value 'm', X~U(a,b), E[X]=m, X in N where
    b = 2*m - a.

    Notes
    -----
    p = (b-floor(b))/2
    X = X1 + X2; X1~U(a,floor(b)), X2~B(p)
    E[X] = E[X1] + E[X2] = (floor(b)+a)/2 + (b-floor(b))/2 = (b+a)/2 = m
    """

    from math import floor

    assert m >= a
    b = 2 * m - a
    p = (b - floor(b)) / 2
    X1 = round(seed.random() * (floor(b) - a) + a)
    if seed.random() < p:
        X2 = 1
    else:
        X2 = 0
    return X1 + X2


def choose_pref_attach(degs, seed):
    """Pick a random value, with a probability given by its weight.

    Returns a random choice among degs keys, each of which has a
    probability proportional to the corresponding dictionary value.

    Parameters
    ----------
    degs: dictionary
        It contains the possible values (keys) and the corresponding
        probabilities (values)
    seed: random state

    Returns
    -------
    v: object
        A key of degs or None if degs is empty
    """

    if len(degs) == 0:
        return None
    s = sum(degs.values())
    if s == 0:
        return seed.choice(list(degs.keys()))
    v = seed.random() * s

    nodes = list(degs.keys())
    i = 0
    acc = degs[nodes[i]]
    while v > acc:
        i += 1
        acc += degs[nodes[i]]
    return nodes[i]


class AS_graph_generator:
    """Generates random internet AS graphs."""

    def __init__(self, n, seed):
        """Initializes variables. Immediate numbers are taken from [1].

        Parameters
        ----------
        n: integer
            Number of graph nodes
        seed: random state
            Indicator of random number generation state.
            See :ref:`Randomness<randomness>`.

        Returns
        -------
        GG: AS_graph_generator object

        References
        ----------
        [1] A. Elmokashfi, A. Kvalbein and C. Dovrolis, "On the Scalability of
        BGP: The Role of Topology Growth," in IEEE Journal on Selected Areas
        in Communications, vol. 28, no. 8, pp. 1250-1261, October 2010.
        """

        self.seed = seed
        self.n_t = min(n, round(self.seed.random() * 2 + 4))  # num of T nodes
        self.n_m = round(0.15 * n)  # number of M nodes
        self.n_cp = round(0.05 * n)  # number of CP nodes
        self.n_c = max(0, n - self.n_t - self.n_m - self.n_cp)  # number of C nodes

        self.d_m = 2 + (2.5 * n) / 10000  # average multihoming degree for M nodes
        self.d_cp = 2 + (1.5 * n) / 10000  # avg multihoming degree for CP nodes
        self.d_c = 1 + (5 * n) / 100000  # average multihoming degree for C nodes

        self.p_m_m = 1 + (2 * n) / 10000  # avg num of peer edges between M and M
        self.p_cp_m = 0.2 + (2 * n) / 10000  # avg num of peer edges between CP, M
        self.p_cp_cp = 0.05 + (2 * n) / 100000  # avg num of peer edges btwn CP, CP

        self.t_m = 0.375  # probability M's provider is T
        self.t_cp = 0.375  # probability CP's provider is T
        self.t_c = 0.125  # probability C's provider is T

    def t_graph(self):
        """Generates the core mesh network of tier one nodes of a AS graph.

        Returns
        -------
        G: Networkx Graph
            Core network
        """

        self.G = nx.Graph()
        for i in range(self.n_t):
            self.G.add_node(i, type="T")
            for r in self.regions:
                self.regions[r].add(i)
            for j in self.G.nodes():
                if i != j:
                    self.add_edge(i, j, "peer")
            self.customers[i] = set()
            self.providers[i] = set()
        return self.G

    def add_edge(self, i, j, kind):
        if kind == "transit":
            customer = str(i)
        else:
            customer = "none"
        self.G.add_edge(i, j, type=kind, customer=customer)

    def choose_peer_pref_attach(self, node_list):
        """Pick a node with a probability weighted by its peer degree.

        Pick a node from node_list with preferential attachment
        computed only on their peer degree
        """

        d = {}
        for n in node_list:
            d[n] = self.G.nodes[n]["peers"]
        return choose_pref_attach(d, self.seed)

    def choose_node_pref_attach(self, node_list):
        """Pick a node with a probability weighted by its degree.

        Pick a node from node_list with preferential attachment
        computed on their degree
        """

        degs = dict(self.G.degree(node_list))
        return choose_pref_attach(degs, self.seed)

    def add_customer(self, i, j):
        """Keep the dictionaries 'customers' and 'providers' consistent."""

        self.customers[j].add(i)
        self.providers[i].add(j)
        for z in self.providers[j]:
            self.customers[z].add(i)
            self.providers[i].add(z)

    def add_node(self, i, kind, reg2prob, avg_deg, t_edge_prob):
        """Add a node and its customer transit edges to the graph.

        Parameters
        ----------
        i: object
            Identifier of the new node
        kind: string
            Type of the new node. Options are: 'M' for middle node, 'CP' for
            content provider and 'C' for customer.
        reg2prob: float
            Probability the new node can be in two different regions.
        avg_deg: float
            Average number of transit nodes of which node i is customer.
        t_edge_prob: float
            Probability node i establish a customer transit edge with a tier
            one (T) node

        Returns
        -------
        i: object
            Identifier of the new node
        """

        regs = 1  # regions in which node resides
        if self.seed.random() < reg2prob:  # node is in two regions
            regs = 2
        node_options = set()

        self.G.add_node(i, type=kind, peers=0)
        self.customers[i] = set()
        self.providers[i] = set()
        self.nodes[kind].add(i)
        for r in self.seed.sample(list(self.regions), regs):
            node_options = node_options.union(self.regions[r])
            self.regions[r].add(i)

        edge_num = uniform_int_from_avg(1, avg_deg, self.seed)

        t_options = node_options.intersection(self.nodes["T"])
        m_options = node_options.intersection(self.nodes["M"])
        if i in m_options:
            m_options.remove(i)
        d = 0
        while d < edge_num and (len(t_options) > 0 or len(m_options) > 0):
            if len(m_options) == 0 or (
                len(t_options) > 0 and self.seed.random() < t_edge_prob
            ):  # add edge to a T node
                j = self.choose_node_pref_attach(t_options)
                t_options.remove(j)
            else:
                j = self.choose_node_pref_attach(m_options)
                m_options.remove(j)
            self.add_edge(i, j, "transit")
            self.add_customer(i, j)
            d += 1

        return i

    def add_m_peering_link(self, m, to_kind):
        """Add a peering link between two middle tier (M) nodes.

        Target node j is drawn considering a preferential attachment based on
        other M node peering degree.

        Parameters
        ----------
        m: object
            Node identifier
        to_kind: string
            type for target node j (must be always M)

        Returns
        -------
        success: boolean
        """

        # candidates are of type 'M' and are not customers of m
        node_options = self.nodes["M"].difference(self.customers[m])
        # candidates are not providers of m
        node_options = node_options.difference(self.providers[m])
        # remove self
        if m in node_options:
            node_options.remove(m)

        # remove candidates we are already connected to
        for j in self.G.neighbors(m):
            if j in node_options:
                node_options.remove(j)

        if len(node_options) > 0:
            j = self.choose_peer_pref_attach(node_options)
            self.add_edge(m, j, "peer")
            self.G.nodes[m]["peers"] += 1
            self.G.nodes[j]["peers"] += 1
            return True
        else:
            return False

    def add_cp_peering_link(self, cp, to_kind):
        """Add a peering link to a content provider (CP) node.

        Target node j can be CP or M and it is drawn uniformly among the nodes
        belonging to the same region as cp.

        Parameters
        ----------
        cp: object
            Node identifier
        to_kind: string
            type for target node j (must be M or CP)

        Returns
        -------
        success: boolean
        """

        node_options = set()
        for r in self.regions:  # options include nodes in the same region(s)
            if cp in self.regions[r]:
                node_options = node_options.union(self.regions[r])

        # options are restricted to the indicated kind ('M' or 'CP')
        node_options = self.nodes[to_kind].intersection(node_options)

        # remove self
        if cp in node_options:
            node_options.remove(cp)

        # remove nodes that are cp's providers
        node_options = node_options.difference(self.providers[cp])

        # remove nodes we are already connected to
        for j in self.G.neighbors(cp):
            if j in node_options:
                node_options.remove(j)

        if len(node_options) > 0:
            j = self.seed.sample(list(node_options), 1)[0]
            self.add_edge(cp, j, "peer")
            self.G.nodes[cp]["peers"] += 1
            self.G.nodes[j]["peers"] += 1
            return True
        else:
            return False

    def graph_regions(self, rn):
        """Initializes AS network regions.

        Parameters
        ----------
        rn: integer
            Number of regions
        """

        self.regions = {}
        for i in range(rn):
            self.regions["REG" + str(i)] = set()

    def add_peering_links(self, from_kind, to_kind):
        """Utility function to add peering links among node groups."""
        peer_link_method = None
        if from_kind == "M":
            peer_link_method = self.add_m_peering_link
            m = self.p_m_m
        if from_kind == "CP":
            peer_link_method = self.add_cp_peering_link
            if to_kind == "M":
                m = self.p_cp_m
            else:
                m = self.p_cp_cp

        for i in self.nodes[from_kind]:
            num = uniform_int_from_avg(0, m, self.seed)
            for _ in range(num):
                peer_link_method(i, to_kind)

    def generate(self):
        """Generates a random AS network graph as described in [1].

        Returns
        -------
        G: Graph object

        Notes
        -----
        The process steps are the following: first we create the core network
        of tier one nodes, then we add the middle tier (M), the content
        provider (CP) and the customer (C) nodes along with their transit edges
        (link i,j means i is customer of j). Finally we add peering links
        between M nodes, between M and CP nodes and between CP node couples.
        For a detailed description of the algorithm, please refer to [1].

        References
        ----------
        [1] A. Elmokashfi, A. Kvalbein and C. Dovrolis, "On the Scalability of
        BGP: The Role of Topology Growth," in IEEE Journal on Selected Areas
        in Communications, vol. 28, no. 8, pp. 1250-1261, October 2010.
        """

        self.graph_regions(5)
        self.customers = {}
        self.providers = {}
        self.nodes = {"T": set(), "M": set(), "CP": set(), "C": set()}

        self.t_graph()
        self.nodes["T"] = set(self.G.nodes())

        i = len(self.nodes["T"])
        for _ in range(self.n_m):
            self.nodes["M"].add(self.add_node(i, "M", 0.2, self.d_m, self.t_m))
            i += 1
        for _ in range(self.n_cp):
            self.nodes["CP"].add(self.add_node(i, "CP", 0.05, self.d_cp, self.t_cp))
            i += 1
        for _ in range(self.n_c):
            self.nodes["C"].add(self.add_node(i, "C", 0, self.d_c, self.t_c))
            i += 1

        self.add_peering_links("M", "M")
        self.add_peering_links("CP", "M")
        self.add_peering_links("CP", "CP")

        return self.G


@py_random_state(1)
@nx._dispatchable(graphs=None, returns_graph=True)
def random_internet_as_graph(n, seed=None):
    """Generates a random undirected graph resembling the Internet AS network

    Parameters
    ----------
    n: integer in [1000, 10000]
        Number of graph nodes
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    G: Networkx Graph object
        A randomly generated undirected graph

    Notes
    -----
    This algorithm returns an undirected graph resembling the Internet
    Autonomous System (AS) network, it uses the approach by Elmokashfi et al.
    [1]_ and it grants the properties described in the related paper [1]_.

    Each node models an autonomous system, with an attribute 'type' specifying
    its kind; tier-1 (T), mid-level (M), customer (C) or content-provider (CP).
    Each edge models an ADV communication link (hence, bidirectional) with
    attributes:

      - type: transit|peer, the kind of commercial agreement between nodes;
      - customer: <node id>, the identifier of the node acting as customer
        ('none' if type is peer).

    References
    ----------
    .. [1] A. Elmokashfi, A. Kvalbein and C. Dovrolis, "On the Scalability of
       BGP: The Role of Topology Growth," in IEEE Journal on Selected Areas
       in Communications, vol. 28, no. 8, pp. 1250-1261, October 2010.
    """

    GG = AS_graph_generator(n, seed)
    G = GG.generate()
    return G
