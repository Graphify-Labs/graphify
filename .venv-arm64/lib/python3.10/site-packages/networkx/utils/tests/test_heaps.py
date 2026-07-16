import pytest

import networkx as nx
from networkx.utils import BinaryHeap, PairingHeap


class X:
    def __eq__(self, other):
        raise self is other

    def __ne__(self, other):
        raise self is not other

    def __lt__(self, other):
        raise TypeError("cannot compare")

    def __le__(self, other):
        raise TypeError("cannot compare")

    def __ge__(self, other):
        raise TypeError("cannot compare")

    def __gt__(self, other):
        raise TypeError("cannot compare")

    def __hash__(self):
        return hash(id(self))


x = X()


data = [  # min should not invent an element.
    ("min", nx.NetworkXError),
    # Popping an empty heap should fail.
    ("pop", nx.NetworkXError),
    # Getting nonexisting elements should return None.
    ("get", 0, None),
    ("get", x, None),
    ("get", None, None),
    # Inserting a new key should succeed.
    ("insert", x, 1, True),
    ("get", x, 1),
    ("min", (x, 1)),
    # min should not pop the top element.
    ("min", (x, 1)),
    # Inserting a new key of different type should succeed.
    ("insert", 1, -2.0, True),
    # int and float values should interop.
    ("min", (1, -2.0)),
    # pop removes minimum-valued element.
    ("insert", 3, -(10**100), True),
    ("insert", 4, 5, True),
    ("pop", (3, -(10**100))),
    ("pop", (1, -2.0)),
    # Decrease-insert should succeed.
    ("insert", 4, -50, True),
    ("insert", 4, -60, False, True),
    # Decrease-insert should not create duplicate keys.
    ("pop", (4, -60)),
    ("pop", (x, 1)),
    # Popping all elements should empty the heap.
    ("min", nx.NetworkXError),
    ("pop", nx.NetworkXError),
    # Non-value-changing insert should fail.
    ("insert", x, 0, True),
    ("insert", x, 0, False, False),
    ("min", (x, 0)),
    ("insert", x, 0, True, False),
    ("min", (x, 0)),
    # Failed insert should not create duplicate keys.
    ("pop", (x, 0)),
    ("pop", nx.NetworkXError),
    # Increase-insert should succeed when allowed.
    ("insert", None, 0, True),
    ("insert", 2, -1, True),
    ("min", (2, -1)),
    ("insert", 2, 1, True, False),
    ("min", (None, 0)),
    # Increase-insert should fail when disallowed.
    ("insert", None, 2, False, False),
    ("min", (None, 0)),
    # Failed increase-insert should not create duplicate keys.
    ("pop", (None, 0)),
    ("pop", (2, 1)),
    ("min", nx.NetworkXError),
    ("pop", nx.NetworkXError),
]


def _test_heap_class(cls, *args, **kwargs):
    heap = cls(*args, **kwargs)
    # Basic behavioral test
    for op in data:
        if op[-1] is not nx.NetworkXError:
            assert op[-1] == getattr(heap, op[0])(*op[1:-1])
        else:
            pytest.raises(op[-1], getattr(heap, op[0]), *op[1:-1])
    # Coverage test.
    for i in range(99, -1, -1):
        assert heap.insert(i, i)
    for i in range(50):
        assert heap.pop() == (i, i)
    for i in range(100):
        assert heap.insert(i, i) == (i < 50)
    for i in range(100):
        assert not heap.insert(i, i + 1)
    for i in range(50):
        assert heap.pop() == (i, i)
    for i in range(100):
        assert heap.insert(i, i + 1) == (i < 50)
    for i in range(49):
        assert heap.pop() == (i, i + 1)
    assert sorted([heap.pop(), heap.pop()]) == [(49, 50), (50, 50)]
    for i in range(51, 100):
        assert not heap.insert(i, i + 1, True)
    for i in range(51, 70):
        assert heap.pop() == (i, i + 1)
    for i in range(100):
        assert heap.insert(i, i)
    for i in range(100):
        assert heap.pop() == (i, i)
    pytest.raises(nx.NetworkXError, heap.pop)


def test_PairingHeap():
    _test_heap_class(PairingHeap)


def test_BinaryHeap():
    _test_heap_class(BinaryHeap)
