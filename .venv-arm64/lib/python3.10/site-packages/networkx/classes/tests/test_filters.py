import pytest

import networkx as nx


class TestFilterFactory:
    def test_no_filter(self):
        nf = nx.filters.no_filter
        assert nf()
        assert nf(1)
        assert nf(2, 1)

    def test_hide_nodes(self):
        f = nx.classes.filters.hide_nodes([1, 2, 3])
        assert not f(1)
        assert not f(2)
        assert not f(3)
        assert f(4)
        assert f(0)
        assert f("a")
        pytest.raises(TypeError, f, 1, 2)
        pytest.raises(TypeError, f)

    def test_show_nodes(self):
        f = nx.classes.filters.show_nodes([1, 2, 3])
        assert f(1)
        assert f(2)
        assert f(3)
        assert not f(4)
        assert not f(0)
        assert not f("a")
        pytest.raises(TypeError, f, 1, 2)
        pytest.raises(TypeError, f)

    def test_hide_edges(self):
        factory = nx.classes.filters.hide_edges
        f = factory([(1, 2), (3, 4)])
        assert not f(1, 2)
        assert not f(3, 4)
        assert not f(4, 3)
        assert f(2, 3)
        assert f(0, -1)
        assert f("a", "b")
        pytest.raises(TypeError, f, 1, 2, 3)
        pytest.raises(TypeError, f, 1)
        pytest.raises(TypeError, f)
        pytest.raises(TypeError, factory, [1, 2, 3])
        pytest.raises(ValueError, factory, [(1, 2, 3)])

    def test_show_edges(self):
        factory = nx.classes.filters.show_edges
        f = factory([(1, 2), (3, 4)])
        assert f(1, 2)
        assert f(3, 4)
        assert f(4, 3)
        assert not f(2, 3)
        assert not f(0, -1)
        assert not f("a", "b")
        pytest.raises(TypeError, f, 1, 2, 3)
        pytest.raises(TypeError, f, 1)
        pytest.raises(TypeError, f)
        pytest.raises(TypeError, factory, [1, 2, 3])
        pytest.raises(ValueError, factory, [(1, 2, 3)])

    def test_hide_diedges(self):
        factory = nx.classes.filters.hide_diedges
        f = factory([(1, 2), (3, 4)])
        assert not f(1, 2)
        assert not f(3, 4)
        assert f(4, 3)
        assert f(2, 3)
        assert f(0, -1)
        assert f("a", "b")
        pytest.raises(TypeError, f, 1, 2, 3)
        pytest.raises(TypeError, f, 1)
        pytest.raises(TypeError, f)
        pytest.raises(TypeError, factory, [1, 2, 3])
        pytest.raises(ValueError, factory, [(1, 2, 3)])

    def test_show_diedges(self):
        factory = nx.classes.filters.show_diedges
        f = factory([(1, 2), (3, 4)])
        assert f(1, 2)
        assert f(3, 4)
        assert not f(4, 3)
        assert not f(2, 3)
        assert not f(0, -1)
        assert not f("a", "b")
        pytest.raises(TypeError, f, 1, 2, 3)
        pytest.raises(TypeError, f, 1)
        pytest.raises(TypeError, f)
        pytest.raises(TypeError, factory, [1, 2, 3])
        pytest.raises(ValueError, factory, [(1, 2, 3)])

    def test_hide_multiedges(self):
        factory = nx.classes.filters.hide_multiedges
        f = factory([(1, 2, 0), (3, 4, 1), (1, 2, 1)])
        assert not f(1, 2, 0)
        assert not f(1, 2, 1)
        assert f(1, 2, 2)
        assert f(3, 4, 0)
        assert not f(3, 4, 1)
        assert not f(4, 3, 1)
        assert f(4, 3, 0)
        assert f(2, 3, 0)
        assert f(0, -1, 0)
        assert f("a", "b", 0)
        pytest.raises(TypeError, f, 1, 2, 3, 4)
        pytest.raises(TypeError, f, 1, 2)
        pytest.raises(TypeError, f, 1)
        pytest.raises(TypeError, f)
        pytest.raises(TypeError, factory, [1, 2, 3])
        pytest.raises(ValueError, factory, [(1, 2)])
        pytest.raises(ValueError, factory, [(1, 2, 3, 4)])

    def test_show_multiedges(self):
        factory = nx.classes.filters.show_multiedges
        f = factory([(1, 2, 0), (3, 4, 1), (1, 2, 1)])
        assert f(1, 2, 0)
        assert f(1, 2, 1)
        assert not f(1, 2, 2)
        assert not f(3, 4, 0)
        assert f(3, 4, 1)
        assert f(4, 3, 1)
        assert not f(4, 3, 0)
        assert not f(2, 3, 0)
        assert not f(0, -1, 0)
        assert not f("a", "b", 0)
        pytest.raises(TypeError, f, 1, 2, 3, 4)
        pytest.raises(TypeError, f, 1, 2)
        pytest.raises(TypeError, f, 1)
        pytest.raises(TypeError, f)
        pytest.raises(TypeError, factory, [1, 2, 3])
        pytest.raises(ValueError, factory, [(1, 2)])
        pytest.raises(ValueError, factory, [(1, 2, 3, 4)])

    def test_hide_multidiedges(self):
        factory = nx.classes.filters.hide_multidiedges
        f = factory([(1, 2, 0), (3, 4, 1), (1, 2, 1)])
        assert not f(1, 2, 0)
        assert not f(1, 2, 1)
        assert f(1, 2, 2)
        assert f(3, 4, 0)
        assert not f(3, 4, 1)
        assert f(4, 3, 1)
        assert f(4, 3, 0)
        assert f(2, 3, 0)
        assert f(0, -1, 0)
        assert f("a", "b", 0)
        pytest.raises(TypeError, f, 1, 2, 3, 4)
        pytest.raises(TypeError, f, 1, 2)
        pytest.raises(TypeError, f, 1)
        pytest.raises(TypeError, f)
        pytest.raises(TypeError, factory, [1, 2, 3])
        pytest.raises(ValueError, factory, [(1, 2)])
        pytest.raises(ValueError, factory, [(1, 2, 3, 4)])

    def test_show_multidiedges(self):
        factory = nx.classes.filters.show_multidiedges
        f = factory([(1, 2, 0), (3, 4, 1), (1, 2, 1)])
        assert f(1, 2, 0)
        assert f(1, 2, 1)
        assert not f(1, 2, 2)
        assert not f(3, 4, 0)
        assert f(3, 4, 1)
        assert not f(4, 3, 1)
        assert not f(4, 3, 0)
        assert not f(2, 3, 0)
        assert not f(0, -1, 0)
        assert not f("a", "b", 0)
        pytest.raises(TypeError, f, 1, 2, 3, 4)
        pytest.raises(TypeError, f, 1, 2)
        pytest.raises(TypeError, f, 1)
        pytest.raises(TypeError, f)
        pytest.raises(TypeError, factory, [1, 2, 3])
        pytest.raises(ValueError, factory, [(1, 2)])
        pytest.raises(ValueError, factory, [(1, 2, 3, 4)])
