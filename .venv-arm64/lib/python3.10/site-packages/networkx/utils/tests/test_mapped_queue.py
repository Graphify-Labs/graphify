import pytest

from networkx.utils.mapped_queue import MappedQueue, _HeapElement


def test_HeapElement_gtlt():
    bar = _HeapElement(1.1, "a")
    foo = _HeapElement(1, "b")
    assert foo < bar
    assert bar > foo
    assert foo < 1.1
    assert 1 < bar


def test_HeapElement_gtlt_tied_priority():
    bar = _HeapElement(1, "a")
    foo = _HeapElement(1, "b")
    assert foo > bar
    assert bar < foo


def test_HeapElement_eq():
    bar = _HeapElement(1.1, "a")
    foo = _HeapElement(1, "a")
    assert foo == bar
    assert bar == foo
    assert foo == "a"


def test_HeapElement_iter():
    foo = _HeapElement(1, "a")
    bar = _HeapElement(1.1, (3, 2, 1))
    assert list(foo) == [1, "a"]
    assert list(bar) == [1.1, 3, 2, 1]


def test_HeapElement_getitem():
    foo = _HeapElement(1, "a")
    bar = _HeapElement(1.1, (3, 2, 1))
    assert foo[1] == "a"
    assert foo[0] == 1
    assert bar[0] == 1.1
    assert bar[2] == 2
    assert bar[3] == 1
    pytest.raises(IndexError, bar.__getitem__, 4)
    pytest.raises(IndexError, foo.__getitem__, 2)


class TestMappedQueue:
    def setup_method(self):
        pass

    def _check_map(self, q):
        assert q.position == {elt: pos for pos, elt in enumerate(q.heap)}

    def _make_mapped_queue(self, h):
        q = MappedQueue()
        q.heap = h
        q.position = {elt: pos for pos, elt in enumerate(h)}
        return q

    def test_heapify(self):
        h = [5, 4, 3, 2, 1, 0]
        q = self._make_mapped_queue(h)
        q._heapify()
        self._check_map(q)

    def test_init(self):
        h = [5, 4, 3, 2, 1, 0]
        q = MappedQueue(h)
        self._check_map(q)

    def test_incomparable(self):
        h = [5, 4, "a", 2, 1, 0]
        pytest.raises(TypeError, MappedQueue, h)

    def test_len(self):
        h = [5, 4, 3, 2, 1, 0]
        q = MappedQueue(h)
        self._check_map(q)
        assert len(q) == 6

    def test_siftup_leaf(self):
        h = [2]
        h_sifted = [2]
        q = self._make_mapped_queue(h)
        q._siftup(0)
        assert q.heap == h_sifted
        self._check_map(q)

    def test_siftup_one_child(self):
        h = [2, 0]
        h_sifted = [0, 2]
        q = self._make_mapped_queue(h)
        q._siftup(0)
        assert q.heap == h_sifted
        self._check_map(q)

    def test_siftup_left_child(self):
        h = [2, 0, 1]
        h_sifted = [0, 2, 1]
        q = self._make_mapped_queue(h)
        q._siftup(0)
        assert q.heap == h_sifted
        self._check_map(q)

    def test_siftup_right_child(self):
        h = [2, 1, 0]
        h_sifted = [0, 1, 2]
        q = self._make_mapped_queue(h)
        q._siftup(0)
        assert q.heap == h_sifted
        self._check_map(q)

    def test_siftup_multiple(self):
        h = [0, 1, 2, 4, 3, 5, 6]
        h_sifted = [0, 1, 2, 4, 3, 5, 6]
        q = self._make_mapped_queue(h)
        q._siftup(0)
        assert q.heap == h_sifted
        self._check_map(q)

    def test_siftdown_leaf(self):
        h = [2]
        h_sifted = [2]
        q = self._make_mapped_queue(h)
        q._siftdown(0, 0)
        assert q.heap == h_sifted
        self._check_map(q)

    def test_siftdown_single(self):
        h = [1, 0]
        h_sifted = [0, 1]
        q = self._make_mapped_queue(h)
        q._siftdown(0, len(h) - 1)
        assert q.heap == h_sifted
        self._check_map(q)

    def test_siftdown_multiple(self):
        h = [1, 2, 3, 4, 5, 6, 7, 0]
        h_sifted = [0, 1, 3, 2, 5, 6, 7, 4]
        q = self._make_mapped_queue(h)
        q._siftdown(0, len(h) - 1)
        assert q.heap == h_sifted
        self._check_map(q)

    def test_push(self):
        to_push = [6, 1, 4, 3, 2, 5, 0]
        h_sifted = [0, 2, 1, 6, 3, 5, 4]
        q = MappedQueue()
        for elt in to_push:
            q.push(elt)
        assert q.heap == h_sifted
        self._check_map(q)

    def test_push_duplicate(self):
        to_push = [2, 1, 0]
        h_sifted = [0, 2, 1]
        q = MappedQueue()
        for elt in to_push:
            inserted = q.push(elt)
            assert inserted
        assert q.heap == h_sifted
        self._check_map(q)
        inserted = q.push(1)
        assert not inserted

    def test_pop(self):
        h = [3, 4, 6, 0, 1, 2, 5]
        h_sorted = sorted(h)
        q = self._make_mapped_queue(h)
        q._heapify()
        popped = [q.pop() for _ in range(len(h))]
        assert popped == h_sorted
        self._check_map(q)

    def test_remove_leaf(self):
        h = [0, 2, 1, 6, 3, 5, 4]
        h_removed = [0, 2, 1, 6, 4, 5]
        q = self._make_mapped_queue(h)
        removed = q.remove(3)
        assert q.heap == h_removed

    def test_remove_root(self):
        h = [0, 2, 1, 6, 3, 5, 4]
        h_removed = [1, 2, 4, 6, 3, 5]
        q = self._make_mapped_queue(h)
        removed = q.remove(0)
        assert q.heap == h_removed

    def test_update_leaf(self):
        h = [0, 20, 10, 60, 30, 50, 40]
        h_updated = [0, 15, 10, 60, 20, 50, 40]
        q = self._make_mapped_queue(h)
        removed = q.update(30, 15)
        assert q.heap == h_updated

    def test_update_root(self):
        h = [0, 20, 10, 60, 30, 50, 40]
        h_updated = [10, 20, 35, 60, 30, 50, 40]
        q = self._make_mapped_queue(h)
        removed = q.update(0, 35)
        assert q.heap == h_updated


class TestMappedDict(TestMappedQueue):
    def _make_mapped_queue(self, h):
        priority_dict = {elt: elt for elt in h}
        return MappedQueue(priority_dict)

    def test_init(self):
        d = {5: 0, 4: 1, "a": 2, 2: 3, 1: 4}
        q = MappedQueue(d)
        assert q.position == d

    def test_ties(self):
        d = {5: 0, 4: 1, 3: 2, 2: 3, 1: 4}
        q = MappedQueue(d)
        assert q.position == {elt: pos for pos, elt in enumerate(q.heap)}

    def test_pop(self):
        d = {5: 0, 4: 1, 3: 2, 2: 3, 1: 4}
        q = MappedQueue(d)
        assert q.pop() == _HeapElement(0, 5)
        assert q.position == {elt: pos for pos, elt in enumerate(q.heap)}

    def test_empty_pop(self):
        q = MappedQueue()
        pytest.raises(IndexError, q.pop)

    def test_incomparable_ties(self):
        d = {5: 0, 4: 0, "a": 0, 2: 0, 1: 0}
        pytest.raises(TypeError, MappedQueue, d)

    def test_push(self):
        to_push = [6, 1, 4, 3, 2, 5, 0]
        h_sifted = [0, 2, 1, 6, 3, 5, 4]
        q = MappedQueue()
        for elt in to_push:
            q.push(elt, priority=elt)
        assert q.heap == h_sifted
        self._check_map(q)

    def test_push_duplicate(self):
        to_push = [2, 1, 0]
        h_sifted = [0, 2, 1]
        q = MappedQueue()
        for elt in to_push:
            inserted = q.push(elt, priority=elt)
            assert inserted
        assert q.heap == h_sifted
        self._check_map(q)
        inserted = q.push(1, priority=1)
        assert not inserted

    def test_update_leaf(self):
        h = [0, 20, 10, 60, 30, 50, 40]
        h_updated = [0, 15, 10, 60, 20, 50, 40]
        q = self._make_mapped_queue(h)
        removed = q.update(30, 15, priority=15)
        assert q.heap == h_updated

    def test_update_root(self):
        h = [0, 20, 10, 60, 30, 50, 40]
        h_updated = [10, 20, 35, 60, 30, 50, 40]
        q = self._make_mapped_queue(h)
        removed = q.update(0, 35, priority=35)
        assert q.heap == h_updated
