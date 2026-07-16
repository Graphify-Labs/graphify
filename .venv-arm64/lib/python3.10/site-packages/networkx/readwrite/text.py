"""
Text-based visual representations of graphs
"""

import sys
import warnings
from collections import defaultdict

import networkx as nx
from networkx.utils import open_file

__all__ = ["generate_network_text", "write_network_text"]


class BaseGlyphs:
    @classmethod
    def as_dict(cls):
        return {
            a: getattr(cls, a)
            for a in dir(cls)
            if not a.startswith("_") and a != "as_dict"
        }


class AsciiBaseGlyphs(BaseGlyphs):
    empty: str = "+"
    newtree_last: str = "+-- "
    newtree_mid: str = "+-- "
    endof_forest: str = "    "
    within_forest: str = ":   "
    within_tree: str = "|   "


class AsciiDirectedGlyphs(AsciiBaseGlyphs):
    last: str = "L-> "
    mid: str = "|-> "
    backedge: str = "<-"
    vertical_edge: str = "!"


class AsciiUndirectedGlyphs(AsciiBaseGlyphs):
    last: str = "L-- "
    mid: str = "|-- "
    backedge: str = "-"
    vertical_edge: str = "|"


class UtfBaseGlyphs(BaseGlyphs):
    # Notes on available box and arrow characters
    # https://en.wikipedia.org/wiki/Box-drawing_character
    # https://stackoverflow.com/questions/2701192/triangle-arrow
    empty: str = "╙"
    newtree_last: str = "╙── "
    newtree_mid: str = "╟── "
    endof_forest: str = "    "
    within_forest: str = "╎   "
    within_tree: str = "│   "


class UtfDirectedGlyphs(UtfBaseGlyphs):
    last: str = "└─╼ "
    mid: str = "├─╼ "
    backedge: str = "╾"
    vertical_edge: str = "╽"


class UtfUndirectedGlyphs(UtfBaseGlyphs):
    last: str = "└── "
    mid: str = "├── "
    backedge: str = "─"
    vertical_edge: str = "│"


def generate_network_text(
    graph,
    with_labels=True,
    sources=None,
    max_depth=None,
    ascii_only=False,
    vertical_chains=False,
):
    """Generate lines in the "network text" format

    This works via a depth-first traversal of the graph and writing a line for
    each unique node encountered. Non-tree edges are written to the right of
    each node, and connection to a non-tree edge is indicated with an ellipsis.
    This representation works best when the input graph is a forest, but any
    graph can be represented.

    This notation is original to networkx, although it is simple enough that it
    may be known in existing literature. See #5602 for details. The procedure
    is summarized as follows:

    1. Given a set of source nodes (which can be specified, or automatically
    discovered via finding the (strongly) connected components and choosing one
    node with minimum degree from each), we traverse the graph in depth first
    order.

    2. Each reachable node will be printed exactly once on it's own line.

    3. Edges are indicated in one of four ways:

        a. a parent "L-style" connection on the upper left. This corresponds to
        a traversal in the directed DFS tree.

        b. a backref "<-style" connection shown directly on the right. For
        directed graphs, these are drawn for any incoming edges to a node that
        is not a parent edge. For undirected graphs, these are drawn for only
        the non-parent edges that have already been represented (The edges that
        have not been represented will be handled in the recursive case).

        c. a child "L-style" connection on the lower right. Drawing of the
        children are handled recursively.

        d. if ``vertical_chains`` is true, and a parent node only has one child
        a "vertical-style" edge is drawn between them.

    4. The children of each node (wrt the directed DFS tree) are drawn
    underneath and to the right of it. In the case that a child node has already
    been drawn the connection is replaced with an ellipsis ("...") to indicate
    that there is one or more connections represented elsewhere.

    5. If a maximum depth is specified, an edge to nodes past this maximum
    depth will be represented by an ellipsis.

    6. If a node has a truthy "collapse" value, then we do not traverse past
    that node.

    Parameters
    ----------
    graph : nx.DiGraph | nx.Graph
        Graph to represent

    with_labels : bool | str
        If True will use the "label" attribute of a node to display if it
        exists otherwise it will use the node value itself. If given as a
        string, then that attribute name will be used instead of "label".
        Defaults to True.

    sources : List
        Specifies which nodes to start traversal from. Note: nodes that are not
        reachable from one of these sources may not be shown. If unspecified,
        the minimal set of nodes needed to reach all others will be used.

    max_depth : int | None
        The maximum depth to traverse before stopping. Defaults to None.

    ascii_only : Boolean
        If True only ASCII characters are used to construct the visualization

    vertical_chains : Boolean
        If True, chains of nodes will be drawn vertically when possible.

    Yields
    ------
    str : a line of generated text

    Examples
    --------
    >>> graph = nx.path_graph(10)
    >>> graph.add_node("A")
    >>> graph.add_node("B")
    >>> graph.add_node("C")
    >>> graph.add_node("D")
    >>> graph.add_edge(9, "A")
    >>> graph.add_edge(9, "B")
    >>> graph.add_edge(9, "C")
    >>> graph.add_edge("C", "D")
    >>> graph.add_edge("C", "E")
    >>> graph.add_edge("C", "F")
    >>> nx.write_network_text(graph)
    ╙── 0
        └── 1
            └── 2
                └── 3
                    └── 4
                        └── 5
                            └── 6
                                └── 7
                                    └── 8
                                        └── 9
                                            ├── A
                                            ├── B
                                            └── C
                                                ├── D
                                                ├── E
                                                └── F
    >>> nx.write_network_text(graph, vertical_chains=True)
    ╙── 0
        │
        1
        │
        2
        │
        3
        │
        4
        │
        5
        │
        6
        │
        7
        │
        8
        │
        9
        ├── A
        ├── B
        └── C
            ├── D
            ├── E
            └── F
    """
    from typing import Any, NamedTuple

    class StackFrame(NamedTuple):
        parent: Any
        node: Any
        indents: list
        this_islast: bool
        this_vertical: bool

    collapse_attr = "collapse"

    is_directed = graph.is_directed()

    if is_directed:
        glyphs = AsciiDirectedGlyphs if ascii_only else UtfDirectedGlyphs
        succ = graph.succ
        pred = graph.pred
    else:
        glyphs = AsciiUndirectedGlyphs if ascii_only else UtfUndirectedGlyphs
        succ = graph.adj
        pred = graph.adj

    if isinstance(with_labels, str):
        label_attr = with_labels
    elif with_labels:
        label_attr = "label"
    else:
        label_attr = None

    if max_depth == 0:
        yield glyphs.empty + " ..."
    elif len(graph.nodes) == 0:
        yield glyphs.empty
    else:
        # If the nodes to traverse are unspecified, find the minimal set of
        # nodes that will reach the entire graph
        if sources is None:
            sources = _find_sources(graph)

        # Populate the stack with each:
        # 1. parent node in the DFS tree (or None for root nodes),
        # 2. the current node in the DFS tree
        # 2. a list of indentations indicating depth
        # 3. a flag indicating if the node is the final one to be written.
        # Reverse the stack so sources are popped in the correct order.
        last_idx = len(sources) - 1
        stack = [
            StackFrame(None, node, [], (idx == last_idx), False)
            for idx, node in enumerate(sources)
        ][::-1]

        num_skipped_children = defaultdict(lambda: 0)
        seen_nodes = set()
        while stack:
            parent, node, indents, this_islast, this_vertical = stack.pop()

            if node is not Ellipsis:
                skip = node in seen_nodes
                if skip:
                    # Mark that we skipped a parent's child
                    num_skipped_children[parent] += 1

                if this_islast:
                    # If we reached the last child of a parent, and we skipped
                    # any of that parents children, then we should emit an
                    # ellipsis at the end after this.
                    if num_skipped_children[parent] and parent is not None:
                        # Append the ellipsis to be emitted last
                        next_islast = True
                        try_frame = StackFrame(
                            node, Ellipsis, indents, next_islast, False
                        )
                        stack.append(try_frame)

                        # Redo this frame, but not as a last object
                        next_islast = False
                        try_frame = StackFrame(
                            parent, node, indents, next_islast, this_vertical
                        )
                        stack.append(try_frame)
                        continue

                if skip:
                    continue
                seen_nodes.add(node)

            if not indents:
                # Top level items (i.e. trees in the forest) get different
                # glyphs to indicate they are not actually connected
                if this_islast:
                    this_vertical = False
                    this_prefix = indents + [glyphs.newtree_last]
                    next_prefix = indents + [glyphs.endof_forest]
                else:
                    this_prefix = indents + [glyphs.newtree_mid]
                    next_prefix = indents + [glyphs.within_forest]

            else:
                # Non-top-level items
                if this_vertical:
                    this_prefix = indents
                    next_prefix = indents
                else:
                    if this_islast:
                        this_prefix = indents + [glyphs.last]
                        next_prefix = indents + [glyphs.endof_forest]
                    else:
                        this_prefix = indents + [glyphs.mid]
                        next_prefix = indents + [glyphs.within_tree]

            if node is Ellipsis:
                label = " ..."
                suffix = ""
                children = []
            else:
                if label_attr is not None:
                    label = str(graph.nodes[node].get(label_attr, node))
                else:
                    label = str(node)

                # Determine if we want to show the children of this node.
                if collapse_attr is not None:
                    collapse = graph.nodes[node].get(collapse_attr, False)
                else:
                    collapse = False

                # Determine:
                # (1) children to traverse into after showing this node.
                # (2) parents to immediately show to the right of this node.
                if is_directed:
                    # In the directed case we must show every successor node
                    # note: it may be skipped later, but we don't have that
                    # information here.
                    children = list(succ[node])
                    # In the directed case we must show every predecessor
                    # except for parent we directly traversed from.
                    handled_parents = {parent}
                else:
                    # Showing only the unseen children results in a more
                    # concise representation for the undirected case.
                    children = [
                        child for child in succ[node] if child not in seen_nodes
                    ]

                    # In the undirected case, parents are also children, so we
                    # only need to immediately show the ones we can no longer
                    # traverse
                    handled_parents = {*children, parent}

                if max_depth is not None and len(indents) == max_depth - 1:
                    # Use ellipsis to indicate we have reached maximum depth
                    if children:
                        children = [Ellipsis]
                    handled_parents = {parent}

                if collapse:
                    # Collapsing a node is the same as reaching maximum depth
                    if children:
                        children = [Ellipsis]
                    handled_parents = {parent}

                # The other parents are other predecessors of this node that
                # are not handled elsewhere.
                other_parents = [p for p in pred[node] if p not in handled_parents]
                if other_parents:
                    if label_attr is not None:
                        other_parents_labels = ", ".join(
                            [
                                str(graph.nodes[p].get(label_attr, p))
                                for p in other_parents
                            ]
                        )
                    else:
                        other_parents_labels = ", ".join(
                            [str(p) for p in other_parents]
                        )
                    suffix = " ".join(["", glyphs.backedge, other_parents_labels])
                else:
                    suffix = ""

            # Emit the line for this node, this will be called for each node
            # exactly once.
            if this_vertical:
                yield "".join(this_prefix + [glyphs.vertical_edge])

            yield "".join(this_prefix + [label, suffix])

            if vertical_chains:
                if is_directed:
                    num_children = len(set(children))
                else:
                    num_children = len(set(children) - {parent})
                # The next node can be drawn vertically if it is the only
                # remaining child of this node.
                next_is_vertical = num_children == 1
            else:
                next_is_vertical = False

            # Push children on the stack in reverse order so they are popped in
            # the original order.
            for idx, child in enumerate(children[::-1]):
                next_islast = idx == 0
                try_frame = StackFrame(
                    node, child, next_prefix, next_islast, next_is_vertical
                )
                stack.append(try_frame)


@open_file(1, "w")
def write_network_text(
    graph,
    path=None,
    with_labels=True,
    sources=None,
    max_depth=None,
    ascii_only=False,
    end="\n",
    vertical_chains=False,
):
    """Creates a nice text representation of a graph

    This works via a depth-first traversal of the graph and writing a line for
    each unique node encountered. Non-tree edges are written to the right of
    each node, and connection to a non-tree edge is indicated with an ellipsis.
    This representation works best when the input graph is a forest, but any
    graph can be represented.

    Parameters
    ----------
    graph : nx.DiGraph | nx.Graph
        Graph to represent

    path : string or file or callable or None
       Filename or file handle for data output.
       if a function, then it will be called for each generated line.
       if None, this will default to "sys.stdout.write"

    with_labels : bool | str
        If True will use the "label" attribute of a node to display if it
        exists otherwise it will use the node value itself. If given as a
        string, then that attribute name will be used instead of "label".
        Defaults to True.

    sources : List
        Specifies which nodes to start traversal from. Note: nodes that are not
        reachable from one of these sources may not be shown. If unspecified,
        the minimal set of nodes needed to reach all others will be used.

    max_depth : int | None
        The maximum depth to traverse before stopping. Defaults to None.

    ascii_only : Boolean
        If True only ASCII characters are used to construct the visualization

    end : string
        The line ending character

    vertical_chains : Boolean
        If True, chains of nodes will be drawn vertically when possible.

    Examples
    --------
    >>> graph = nx.balanced_tree(r=2, h=2, create_using=nx.DiGraph)
    >>> nx.write_network_text(graph)
    ╙── 0
        ├─╼ 1
        │   ├─╼ 3
        │   └─╼ 4
        └─╼ 2
            ├─╼ 5
            └─╼ 6

    >>> # A near tree with one non-tree edge
    >>> graph.add_edge(5, 1)
    >>> nx.write_network_text(graph)
    ╙── 0
        ├─╼ 1 ╾ 5
        │   ├─╼ 3
        │   └─╼ 4
        └─╼ 2
            ├─╼ 5
            │   └─╼  ...
            └─╼ 6

    >>> graph = nx.cycle_graph(5)
    >>> nx.write_network_text(graph)
    ╙── 0
        ├── 1
        │   └── 2
        │       └── 3
        │           └── 4 ─ 0
        └──  ...

    >>> graph = nx.cycle_graph(5, nx.DiGraph)
    >>> nx.write_network_text(graph, vertical_chains=True)
    ╙── 0 ╾ 4
        ╽
        1
        ╽
        2
        ╽
        3
        ╽
        4
        └─╼  ...

    >>> nx.write_network_text(graph, vertical_chains=True, ascii_only=True)
    +-- 0 <- 4
        !
        1
        !
        2
        !
        3
        !
        4
        L->  ...

    >>> graph = nx.generators.barbell_graph(4, 2)
    >>> nx.write_network_text(graph, vertical_chains=False)
    ╙── 4
        ├── 5
        │   └── 6
        │       ├── 7
        │       │   ├── 8 ─ 6
        │       │   │   └── 9 ─ 6, 7
        │       │   └──  ...
        │       └──  ...
        └── 3
            ├── 0
            │   ├── 1 ─ 3
            │   │   └── 2 ─ 0, 3
            │   └──  ...
            └──  ...
    >>> nx.write_network_text(graph, vertical_chains=True)
    ╙── 4
        ├── 5
        │   │
        │   6
        │   ├── 7
        │   │   ├── 8 ─ 6
        │   │   │   │
        │   │   │   9 ─ 6, 7
        │   │   └──  ...
        │   └──  ...
        └── 3
            ├── 0
            │   ├── 1 ─ 3
            │   │   │
            │   │   2 ─ 0, 3
            │   └──  ...
            └──  ...

    >>> graph = nx.complete_graph(5, create_using=nx.Graph)
    >>> nx.write_network_text(graph)
    ╙── 0
        ├── 1
        │   ├── 2 ─ 0
        │   │   ├── 3 ─ 0, 1
        │   │   │   └── 4 ─ 0, 1, 2
        │   │   └──  ...
        │   └──  ...
        └──  ...

    >>> graph = nx.complete_graph(3, create_using=nx.DiGraph)
    >>> nx.write_network_text(graph)
    ╙── 0 ╾ 1, 2
        ├─╼ 1 ╾ 2
        │   ├─╼ 2 ╾ 0
        │   │   └─╼  ...
        │   └─╼  ...
        └─╼  ...
    """
    if path is None:
        # The path is unspecified, write to stdout
        _write = sys.stdout.write
    elif hasattr(path, "write"):
        # The path is already an open file
        _write = path.write
    elif callable(path):
        # The path is a custom callable
        _write = path
    else:
        raise TypeError(type(path))

    for line in generate_network_text(
        graph,
        with_labels=with_labels,
        sources=sources,
        max_depth=max_depth,
        ascii_only=ascii_only,
        vertical_chains=vertical_chains,
    ):
        _write(line + end)


def _find_sources(graph):
    """
    Determine a minimal set of nodes such that the entire graph is reachable
    """
    # For each connected part of the graph, choose at least
    # one node as a starting point, preferably without a parent
    if graph.is_directed():
        # Choose one node from each SCC with minimum in_degree
        sccs = list(nx.strongly_connected_components(graph))
        # condensing the SCCs forms a dag, the nodes in this graph with
        # 0 in-degree correspond to the SCCs from which the minimum set
        # of nodes from which all other nodes can be reached.
        scc_graph = nx.condensation(graph, sccs)
        supernode_to_nodes = {sn: [] for sn in scc_graph.nodes()}
        # Note: the order of mapping differs between pypy and cpython
        # so we have to loop over graph nodes for consistency
        mapping = scc_graph.graph["mapping"]
        for n in graph.nodes:
            sn = mapping[n]
            supernode_to_nodes[sn].append(n)
        sources = []
        for sn in scc_graph.nodes():
            if scc_graph.in_degree[sn] == 0:
                scc = supernode_to_nodes[sn]
                node = min(scc, key=lambda n: graph.in_degree[n])
                sources.append(node)
    else:
        # For undirected graph, the entire graph will be reachable as
        # long as we consider one node from every connected component
        sources = [
            min(cc, key=lambda n: graph.degree[n])
            for cc in nx.connected_components(graph)
        ]
        sources = sorted(sources, key=lambda n: graph.degree[n])
    return sources


def _parse_network_text(lines):
    """Reconstructs a graph from a network text representation.

    This is mainly used for testing.  Network text is for display, not
    serialization, as such this cannot parse all network text representations
    because node labels can be ambiguous with the glyphs and indentation used
    to represent edge structure. Additionally, there is no way to determine if
    disconnected graphs were originally directed or undirected.

    Parameters
    ----------
    lines : list or iterator of strings
        Input data in network text format

    Returns
    -------
    G: NetworkX graph
        The graph corresponding to the lines in network text format.
    """
    from itertools import chain
    from typing import Any, NamedTuple, Union

    class ParseStackFrame(NamedTuple):
        node: Any
        indent: int
        has_vertical_child: int | None

    initial_line_iter = iter(lines)

    is_ascii = None
    is_directed = None

    ##############
    # Initial Pass
    ##############

    # Do an initial pass over the lines to determine what type of graph it is.
    # Remember what these lines were, so we can reiterate over them in the
    # parsing pass.
    initial_lines = []
    try:
        first_line = next(initial_line_iter)
    except StopIteration:
        ...
    else:
        initial_lines.append(first_line)
        # The first character indicates if it is an ASCII or UTF graph
        first_char = first_line[0]
        if first_char in {
            UtfBaseGlyphs.empty,
            UtfBaseGlyphs.newtree_mid[0],
            UtfBaseGlyphs.newtree_last[0],
        }:
            is_ascii = False
        elif first_char in {
            AsciiBaseGlyphs.empty,
            AsciiBaseGlyphs.newtree_mid[0],
            AsciiBaseGlyphs.newtree_last[0],
        }:
            is_ascii = True
        else:
            raise AssertionError(f"Unexpected first character: {first_char}")

    if is_ascii:
        directed_glyphs = AsciiDirectedGlyphs.as_dict()
        undirected_glyphs = AsciiUndirectedGlyphs.as_dict()
    else:
        directed_glyphs = UtfDirectedGlyphs.as_dict()
        undirected_glyphs = UtfUndirectedGlyphs.as_dict()

    # For both directed / undirected glyphs, determine which glyphs never
    # appear as substrings in the other undirected / directed glyphs.  Glyphs
    # with this property unambiguously indicates if a graph is directed /
    # undirected.
    directed_items = set(directed_glyphs.values())
    undirected_items = set(undirected_glyphs.values())
    unambiguous_directed_items = []
    for item in directed_items:
        other_items = undirected_items
        other_supersets = [other for other in other_items if item in other]
        if not other_supersets:
            unambiguous_directed_items.append(item)
    unambiguous_undirected_items = []
    for item in undirected_items:
        other_items = directed_items
        other_supersets = [other for other in other_items if item in other]
        if not other_supersets:
            unambiguous_undirected_items.append(item)

    for line in initial_line_iter:
        initial_lines.append(line)
        if any(item in line for item in unambiguous_undirected_items):
            is_directed = False
            break
        elif any(item in line for item in unambiguous_directed_items):
            is_directed = True
            break

    if is_directed is None:
        # Not enough information to determine, choose undirected by default
        is_directed = False

    glyphs = directed_glyphs if is_directed else undirected_glyphs

    # the backedge symbol by itself can be ambiguous, but with spaces around it
    # becomes unambiguous.
    backedge_symbol = " " + glyphs["backedge"] + " "

    # Reconstruct an iterator over all of the lines.
    parsing_line_iter = chain(initial_lines, initial_line_iter)

    ##############
    # Parsing Pass
    ##############

    edges = []
    nodes = []
    is_empty = None

    noparent = object()  # sentinel value

    # keep a stack of previous nodes that could be parents of subsequent nodes
    stack = [ParseStackFrame(noparent, -1, None)]

    for line in parsing_line_iter:
        if line == glyphs["empty"]:
            # If the line is the empty glyph, we are done.
            # There shouldn't be anything else after this.
            is_empty = True
            continue

        if backedge_symbol in line:
            # This line has one or more backedges, separate those out
            node_part, backedge_part = line.split(backedge_symbol)
            backedge_nodes = [u.strip() for u in backedge_part.split(", ")]
            # Now the node can be parsed
            node_part = node_part.rstrip()
            prefix, node = node_part.rsplit(" ", 1)
            node = node.strip()
            # Add the backedges to the edge list
            edges.extend([(u, node) for u in backedge_nodes])
        else:
            # No backedge, the tail of this line is the node
            prefix, node = line.rsplit(" ", 1)
            node = node.strip()

        prev = stack.pop()

        if node in glyphs["vertical_edge"]:
            # Previous node is still the previous node, but we know it will
            # have exactly one child, which will need to have its nesting level
            # adjusted.
            modified_prev = ParseStackFrame(
                prev.node,
                prev.indent,
                True,
            )
            stack.append(modified_prev)
            continue

        # The length of the string before the node characters give us a hint
        # about our nesting level. The only case where this doesn't work is
        # when there are vertical chains, which is handled explicitly.
        indent = len(prefix)
        curr = ParseStackFrame(node, indent, None)

        if prev.has_vertical_child:
            # In this case we know prev must be the parent of our current line,
            # so we don't have to search the stack. (which is good because the
            # indentation check wouldn't work in this case).
            ...
        else:
            # If the previous node nesting-level is greater than the current
            # nodes nesting-level than the previous node was the end of a path,
            # and is not our parent. We can safely pop nodes off the stack
            # until we find one with a comparable nesting-level, which is our
            # parent.
            while curr.indent <= prev.indent:
                prev = stack.pop()

        if node == "...":
            # The current previous node is no longer a valid parent,
            # keep it popped from the stack.
            stack.append(prev)
        else:
            # The previous and current nodes may still be parents, so add them
            # back onto the stack.
            stack.append(prev)
            stack.append(curr)

            # Add the node and the edge to its parent to the node / edge lists.
            nodes.append(curr.node)
            if prev.node is not noparent:
                edges.append((prev.node, curr.node))

    if is_empty:
        # Sanity check
        assert len(nodes) == 0

    # Reconstruct the graph
    cls = nx.DiGraph if is_directed else nx.Graph
    new = cls()
    new.add_nodes_from(nodes)
    new.add_edges_from(edges)
    return new
