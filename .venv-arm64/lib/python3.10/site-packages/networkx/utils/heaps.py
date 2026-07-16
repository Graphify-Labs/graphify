"""
Min-heaps.
"""

from heapq import heappop, heappush
from itertools import count

import networkx as nx

__all__ = ["MinHeap", "PairingHeap", "BinaryHeap"]


class MinHeap:
    """Base class for min-heaps.

    A MinHeap stores a collection of key-value pairs ordered by their values.
    It supports querying the minimum pair, inserting a new pair, decreasing the
    value in an existing pair and deleting the minimum pair.
    """

    class _Item:
        """Used by subclassess to represent a key-value pair."""

        __slots__ = ("key", "value")

        def __init__(self, key, value):
            self.key = key
            self.value = value

        def __repr__(self):
            return repr((self.key, self.value))

    def __init__(self):
        """Initialize a new min-heap."""
        self._dict = {}

    def min(self):
        """Query the minimum key-value pair.

        Returns
        -------
        key, value : tuple
            The key-value pair with the minimum value in the heap.

        Raises
        ------
        NetworkXError
            If the heap is empty.
        """
        raise NotImplementedError

    def pop(self):
        """Delete the minimum pair in the heap.

        Returns
        -------
        key, value : tuple
            The key-value pair with the minimum value in the heap.

        Raises
        ------
        NetworkXError
            If the heap is empty.
        """
        raise NotImplementedError

    def get(self, key, default=None):
        """Returns the value associated with a key.

        Parameters
        ----------
        key : hashable object
            The key to be looked up.

        default : object
            Default value to return if the key is not present in the heap.
            Default value: None.

        Returns
        -------
        value : object.
            The value associated with the key.
        """
        raise NotImplementedError

    def insert(self, key, value, allow_increase=False):
        """Insert a new key-value pair or modify the value in an existing
        pair.

        Parameters
        ----------
        key : hashable object
            The key.

        value : object comparable with existing values.
            The value.

        allow_increase : bool
            Whether the value is allowed to increase. If False, attempts to
            increase an existing value have no effect. Default value: False.

        Returns
        -------
        decreased : bool
            True if a pair is inserted or the existing value is decreased.
        """
        raise NotImplementedError

    def __nonzero__(self):
        """Returns whether the heap if empty."""
        return bool(self._dict)

    def __bool__(self):
        """Returns whether the heap if empty."""
        return bool(self._dict)

    def __len__(self):
        """Returns the number of key-value pairs in the heap."""
        return len(self._dict)

    def __contains__(self, key):
        """Returns whether a key exists in the heap.

        Parameters
        ----------
        key : any hashable object.
            The key to be looked up.
        """
        return key in self._dict


class PairingHeap(MinHeap):
    """A pairing heap."""

    class _Node(MinHeap._Item):
        """A node in a pairing heap.

        A tree in a pairing heap is stored using the left-child, right-sibling
        representation.
        """

        __slots__ = ("left", "next", "prev", "parent")

        def __init__(self, key, value):
            super().__init__(key, value)
            # The leftmost child.
            self.left = None
            # The next sibling.
            self.next = None
            # The previous sibling.
            self.prev = None
            # The parent.
            self.parent = None

    def __init__(self):
        """Initialize a pairing heap."""
        super().__init__()
        self._root = None

    def min(self):
        if self._root is None:
            raise nx.NetworkXError("heap is empty.")
        return (self._root.key, self._root.value)

    def pop(self):
        if self._root is None:
            raise nx.NetworkXError("heap is empty.")
        min_node = self._root
        self._root = self._merge_children(self._root)
        del self._dict[min_node.key]
        return (min_node.key, min_node.value)

    def get(self, key, default=None):
        node = self._dict.get(key)
        return node.value if node is not None else default

    def insert(self, key, value, allow_increase=False):
        node = self._dict.get(key)
        root = self._root
        if node is not None:
            if value < node.value:
                node.value = value
                if node is not root and value < node.parent.value:
                    self._cut(node)
                    self._root = self._link(root, node)
                return True
            elif allow_increase and value > node.value:
                node.value = value
                child = self._merge_children(node)
                # Nonstandard step: Link the merged subtree with the root. See
                # below for the standard step.
                if child is not None:
                    self._root = self._link(self._root, child)
                # Standard step: Perform a decrease followed by a pop as if the
                # value were the smallest in the heap. Then insert the new
                # value into the heap.
                # if node is not root:
                #     self._cut(node)
                #     if child is not None:
                #         root = self._link(root, child)
                #     self._root = self._link(root, node)
                # else:
                #     self._root = (self._link(node, child)
                #                   if child is not None else node)
            return False
        else:
            # Insert a new key.
            node = self._Node(key, value)
            self._dict[key] = node
            self._root = self._link(root, node) if root is not None else node
            return True

    def _link(self, root, other):
        """Link two nodes, making the one with the smaller value the parent of
        the other.
        """
        if other.value < root.value:
            root, other = other, root
        next = root.left
        other.next = next
        if next is not None:
            next.prev = other
        other.prev = None
        root.left = other
        other.parent = root
        return root

    def _merge_children(self, root):
        """Merge the subtrees of the root using the standard two-pass method.
        The resulting subtree is detached from the root.
        """
        node = root.left
        root.left = None
        if node is not None:
            link = self._link
            # Pass 1: Merge pairs of consecutive subtrees from left to right.
            # At the end of the pass, only the prev pointers of the resulting
            # subtrees have meaningful values. The other pointers will be fixed
            # in pass 2.
            prev = None
            while True:
                next = node.next
                if next is None:
                    node.prev = prev
                    break
                next_next = next.next
                node = link(node, next)
                node.prev = prev
                prev = node
                if next_next is None:
                    break
                node = next_next
            # Pass 2: Successively merge the subtrees produced by pass 1 from
            # right to left with the rightmost one.
            prev = node.prev
            while prev is not None:
                prev_prev = prev.prev
                node = link(prev, node)
                prev = prev_prev
            # Now node can become the new root. Its has no parent nor siblings.
            node.prev = None
            node.next = None
            node.parent = None
        return node

    def _cut(self, node):
        """Cut a node from its parent."""
        prev = node.prev
        next = node.next
        if prev is not None:
            prev.next = next
        else:
            node.parent.left = next
        node.prev = None
        if next is not None:
            next.prev = prev
            node.next = None
        node.parent = None


class BinaryHeap(MinHeap):
    """A binary heap."""

    def __init__(self):
        """Initialize a binary heap."""
        super().__init__()
        self._heap = []
        self._count = count()

    def min(self):
        dict = self._dict
        if not dict:
            raise nx.NetworkXError("heap is empty")
        heap = self._heap
        pop = heappop
        # Repeatedly remove stale key-value pairs until a up-to-date one is
        # met.
        while True:
            value, _, key = heap[0]
            if key in dict and value == dict[key]:
                break
            pop(heap)
        return (key, value)

    def pop(self):
        dict = self._dict
        if not dict:
            raise nx.NetworkXError("heap is empty")
        heap = self._heap
        pop = heappop
        # Repeatedly remove stale key-value pairs until a up-to-date one is
        # met.
        while True:
            value, _, key = heap[0]
            pop(heap)
            if key in dict and value == dict[key]:
                break
        del dict[key]
        return (key, value)

    def get(self, key, default=None):
        return self._dict.get(key, default)

    def insert(self, key, value, allow_increase=False):
        dict = self._dict
        if key in dict:
            old_value = dict[key]
            if value < old_value or (allow_increase and value > old_value):
                # Since there is no way to efficiently obtain the location of a
                # key-value pair in the heap, insert a new pair even if ones
                # with the same key may already be present. Deem the old ones
                # as stale and skip them when the minimum pair is queried.
                dict[key] = value
                heappush(self._heap, (value, next(self._count), key))
                return value < old_value
            return False
        else:
            dict[key] = value
            heappush(self._heap, (value, next(self._count), key))
            return True
