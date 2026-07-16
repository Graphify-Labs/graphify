from pytest import approx

from networkx import is_connected, neighbors
from networkx.generators.internet_as_graphs import random_internet_as_graph


class TestInternetASTopology:
    @classmethod
    def setup_class(cls):
        cls.n = 1000
        cls.seed = 42
        cls.G = random_internet_as_graph(cls.n, cls.seed)
        cls.T = []
        cls.M = []
        cls.C = []
        cls.CP = []
        cls.customers = {}
        cls.providers = {}

        for i in cls.G.nodes():
            if cls.G.nodes[i]["type"] == "T":
                cls.T.append(i)
            elif cls.G.nodes[i]["type"] == "M":
                cls.M.append(i)
            elif cls.G.nodes[i]["type"] == "C":
                cls.C.append(i)
            elif cls.G.nodes[i]["type"] == "CP":
                cls.CP.append(i)
            else:
                raise ValueError("Inconsistent data in the graph node attributes")
            cls.set_customers(i)
            cls.set_providers(i)

    @classmethod
    def set_customers(cls, i):
        if i not in cls.customers:
            cls.customers[i] = set()
            for j in neighbors(cls.G, i):
                e = cls.G.edges[(i, j)]
                if e["type"] == "transit":
                    customer = int(e["customer"])
                    if j == customer:
                        cls.set_customers(j)
                        cls.customers[i] = cls.customers[i].union(cls.customers[j])
                        cls.customers[i].add(j)
                    elif i != customer:
                        raise ValueError(
                            "Inconsistent data in the graph edge attributes"
                        )

    @classmethod
    def set_providers(cls, i):
        if i not in cls.providers:
            cls.providers[i] = set()
            for j in neighbors(cls.G, i):
                e = cls.G.edges[(i, j)]
                if e["type"] == "transit":
                    customer = int(e["customer"])
                    if i == customer:
                        cls.set_providers(j)
                        cls.providers[i] = cls.providers[i].union(cls.providers[j])
                        cls.providers[i].add(j)
                    elif j != customer:
                        raise ValueError(
                            "Inconsistent data in the graph edge attributes"
                        )

    def test_wrong_input(self):
        G = random_internet_as_graph(0)
        assert len(G.nodes()) == 0

        G = random_internet_as_graph(-1)
        assert len(G.nodes()) == 0

        G = random_internet_as_graph(1)
        assert len(G.nodes()) == 1

    def test_node_numbers(self):
        assert len(self.G.nodes()) == self.n
        assert len(self.T) < 7
        assert len(self.M) == round(self.n * 0.15)
        assert len(self.CP) == round(self.n * 0.05)
        numb = self.n - len(self.T) - len(self.M) - len(self.CP)
        assert len(self.C) == numb

    def test_connectivity(self):
        assert is_connected(self.G)

    def test_relationships(self):
        # T nodes are not customers of anyone
        for i in self.T:
            assert len(self.providers[i]) == 0

        # C nodes are not providers of anyone
        for i in self.C:
            assert len(self.customers[i]) == 0

        # CP nodes are not providers of anyone
        for i in self.CP:
            assert len(self.customers[i]) == 0

        # test whether there is a customer-provider loop
        for i in self.G.nodes():
            assert len(self.customers[i].intersection(self.providers[i])) == 0

        # test whether there is a peering with a customer or provider
        for i, j in self.G.edges():
            if self.G.edges[(i, j)]["type"] == "peer":
                assert j not in self.customers[i]
                assert i not in self.customers[j]
                assert j not in self.providers[i]
                assert i not in self.providers[j]

    def test_degree_values(self):
        d_m = 0  # multihoming degree for M nodes
        d_cp = 0  # multihoming degree for CP nodes
        d_c = 0  # multihoming degree for C nodes
        p_m_m = 0  # avg number of peering edges between M and M
        p_cp_m = 0  # avg number of peering edges between CP and M
        p_cp_cp = 0  # avg number of peering edges between CP and CP
        t_m = 0  # probability M's provider is T
        t_cp = 0  # probability CP's provider is T
        t_c = 0  # probability C's provider is T

        for i, j in self.G.edges():
            e = self.G.edges[(i, j)]
            if e["type"] == "transit":
                cust = int(e["customer"])
                if i == cust:
                    prov = j
                elif j == cust:
                    prov = i
                else:
                    raise ValueError("Inconsistent data in the graph edge attributes")
                if cust in self.M:
                    d_m += 1
                    if self.G.nodes[prov]["type"] == "T":
                        t_m += 1
                elif cust in self.C:
                    d_c += 1
                    if self.G.nodes[prov]["type"] == "T":
                        t_c += 1
                elif cust in self.CP:
                    d_cp += 1
                    if self.G.nodes[prov]["type"] == "T":
                        t_cp += 1
                else:
                    raise ValueError("Inconsistent data in the graph edge attributes")
            elif e["type"] == "peer":
                if self.G.nodes[i]["type"] == "M" and self.G.nodes[j]["type"] == "M":
                    p_m_m += 1
                if self.G.nodes[i]["type"] == "CP" and self.G.nodes[j]["type"] == "CP":
                    p_cp_cp += 1
                if (
                    self.G.nodes[i]["type"] == "M"
                    and self.G.nodes[j]["type"] == "CP"
                    or self.G.nodes[i]["type"] == "CP"
                    and self.G.nodes[j]["type"] == "M"
                ):
                    p_cp_m += 1
            else:
                raise ValueError("Unexpected data in the graph edge attributes")

        assert d_m / len(self.M) == approx((2 + (2.5 * self.n) / 10000), abs=1e-0)
        assert d_cp / len(self.CP) == approx((2 + (1.5 * self.n) / 10000), abs=1e-0)
        assert d_c / len(self.C) == approx((1 + (5 * self.n) / 100000), abs=1e-0)

        assert p_m_m / len(self.M) == approx((1 + (2 * self.n) / 10000), abs=1e-0)
        assert p_cp_m / len(self.CP) == approx((0.2 + (2 * self.n) / 10000), abs=1e-0)
        assert p_cp_cp / len(self.CP) == approx(
            (0.05 + (2 * self.n) / 100000), abs=1e-0
        )

        assert t_m / d_m == approx(0.375, abs=1e-1)
        assert t_cp / d_cp == approx(0.375, abs=1e-1)
        assert t_c / d_c == approx(0.125, abs=1e-1)
