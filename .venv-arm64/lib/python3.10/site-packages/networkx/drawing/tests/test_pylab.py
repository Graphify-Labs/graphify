"""Unit tests for matplotlib drawing functions."""

import itertools
import os
import warnings

import pytest

mpl = pytest.importorskip("matplotlib")
np = pytest.importorskip("numpy")
mpl.use("PS")
plt = pytest.importorskip("matplotlib.pyplot")
plt.rcParams["text.usetex"] = False


import networkx as nx

barbell = nx.barbell_graph(4, 6)


def test_draw():
    try:
        functions = [
            nx.draw_circular,
            nx.draw_kamada_kawai,
            nx.draw_planar,
            nx.draw_random,
            nx.draw_spectral,
            nx.draw_spring,
            nx.draw_shell,
        ]
        options = [{"node_color": "black", "node_size": 100, "width": 3}]
        for function, option in itertools.product(functions, options):
            function(barbell, **option)
            plt.savefig("test.ps")
    except ModuleNotFoundError:  # draw_kamada_kawai requires scipy
        pass
    finally:
        try:
            os.unlink("test.ps")
        except OSError:
            pass


def test_draw_shell_nlist():
    try:
        nlist = [list(range(4)), list(range(4, 10)), list(range(10, 14))]
        nx.draw_shell(barbell, nlist=nlist)
        plt.savefig("test.ps")
    finally:
        try:
            os.unlink("test.ps")
        except OSError:
            pass


def test_edge_colormap():
    colors = range(barbell.number_of_edges())
    nx.draw_spring(
        barbell, edge_color=colors, width=4, edge_cmap=plt.cm.Blues, with_labels=True
    )
    # plt.show()


def test_arrows():
    nx.draw_spring(barbell.to_directed())
    # plt.show()


@pytest.mark.parametrize(
    ("edge_color", "expected"),
    (
        (None, "black"),  # Default
        ("r", "red"),  # Non-default color string
        (["r"], "red"),  # Single non-default color in a list
        ((1.0, 1.0, 0.0), "yellow"),  # single color as rgb tuple
        ([(1.0, 1.0, 0.0)], "yellow"),  # single color as rgb tuple in list
        ((0, 1, 0, 1), "lime"),  # single color as rgba tuple
        ([(0, 1, 0, 1)], "lime"),  # single color as rgba tuple in list
        ("#0000ff", "blue"),  # single color hex code
        (["#0000ff"], "blue"),  # hex code in list
    ),
)
@pytest.mark.parametrize("edgelist", (None, [(0, 1)]))
def test_single_edge_color_undirected(edge_color, expected, edgelist):
    """Tests ways of specifying all edges have a single color for edges
    drawn with a LineCollection"""

    G = nx.path_graph(3)
    drawn_edges = nx.draw_networkx_edges(
        G, pos=nx.random_layout(G), edgelist=edgelist, edge_color=edge_color
    )
    assert mpl.colors.same_color(drawn_edges.get_color(), expected)


@pytest.mark.parametrize(
    ("edge_color", "expected"),
    (
        (None, "black"),  # Default
        ("r", "red"),  # Non-default color string
        (["r"], "red"),  # Single non-default color in a list
        ((1.0, 1.0, 0.0), "yellow"),  # single color as rgb tuple
        ([(1.0, 1.0, 0.0)], "yellow"),  # single color as rgb tuple in list
        ((0, 1, 0, 1), "lime"),  # single color as rgba tuple
        ([(0, 1, 0, 1)], "lime"),  # single color as rgba tuple in list
        ("#0000ff", "blue"),  # single color hex code
        (["#0000ff"], "blue"),  # hex code in list
    ),
)
@pytest.mark.parametrize("edgelist", (None, [(0, 1)]))
def test_single_edge_color_directed(edge_color, expected, edgelist):
    """Tests ways of specifying all edges have a single color for edges drawn
    with FancyArrowPatches"""

    G = nx.path_graph(3, create_using=nx.DiGraph)
    drawn_edges = nx.draw_networkx_edges(
        G, pos=nx.random_layout(G), edgelist=edgelist, edge_color=edge_color
    )
    for fap in drawn_edges:
        assert mpl.colors.same_color(fap.get_edgecolor(), expected)


def test_edge_color_tuple_interpretation():
    """If edge_color is a sequence with the same length as edgelist, then each
    value in edge_color is mapped onto each edge via colormap."""
    G = nx.path_graph(6, create_using=nx.DiGraph)
    pos = {n: (n, n) for n in range(len(G))}

    # num edges != 3 or 4 --> edge_color interpreted as rgb(a)
    for ec in ((0, 0, 1), (0, 0, 1, 1)):
        # More than 4 edges
        drawn_edges = nx.draw_networkx_edges(G, pos, edge_color=ec)
        for fap in drawn_edges:
            assert mpl.colors.same_color(fap.get_edgecolor(), ec)
        # Fewer than 3 edges
        drawn_edges = nx.draw_networkx_edges(
            G, pos, edgelist=[(0, 1), (1, 2)], edge_color=ec
        )
        for fap in drawn_edges:
            assert mpl.colors.same_color(fap.get_edgecolor(), ec)

    # num edges == 3, len(edge_color) == 4: interpreted as rgba
    drawn_edges = nx.draw_networkx_edges(
        G, pos, edgelist=[(0, 1), (1, 2), (2, 3)], edge_color=(0, 0, 1, 1)
    )
    for fap in drawn_edges:
        assert mpl.colors.same_color(fap.get_edgecolor(), "blue")

    # num edges == 4, len(edge_color) == 3: interpreted as rgb
    drawn_edges = nx.draw_networkx_edges(
        G, pos, edgelist=[(0, 1), (1, 2), (2, 3), (3, 4)], edge_color=(0, 0, 1)
    )
    for fap in drawn_edges:
        assert mpl.colors.same_color(fap.get_edgecolor(), "blue")

    # num edges == len(edge_color) == 3: interpreted with cmap, *not* as rgb
    drawn_edges = nx.draw_networkx_edges(
        G, pos, edgelist=[(0, 1), (1, 2), (2, 3)], edge_color=(0, 0, 1)
    )
    assert mpl.colors.same_color(
        drawn_edges[0].get_edgecolor(), drawn_edges[1].get_edgecolor()
    )
    for fap in drawn_edges:
        assert not mpl.colors.same_color(fap.get_edgecolor(), "blue")

    # num edges == len(edge_color) == 4: interpreted with cmap, *not* as rgba
    drawn_edges = nx.draw_networkx_edges(
        G, pos, edgelist=[(0, 1), (1, 2), (2, 3), (3, 4)], edge_color=(0, 0, 1, 1)
    )
    assert mpl.colors.same_color(
        drawn_edges[0].get_edgecolor(), drawn_edges[1].get_edgecolor()
    )
    assert mpl.colors.same_color(
        drawn_edges[2].get_edgecolor(), drawn_edges[3].get_edgecolor()
    )
    for fap in drawn_edges:
        assert not mpl.colors.same_color(fap.get_edgecolor(), "blue")


def test_fewer_edge_colors_than_num_edges_directed():
    """Test that the edge colors are cycled when there are fewer specified
    colors than edges."""
    G = barbell.to_directed()
    pos = nx.random_layout(barbell)
    edgecolors = ("r", "g", "b")
    drawn_edges = nx.draw_networkx_edges(G, pos, edge_color=edgecolors)
    for fap, expected in zip(drawn_edges, itertools.cycle(edgecolors)):
        assert mpl.colors.same_color(fap.get_edgecolor(), expected)


def test_more_edge_colors_than_num_edges_directed():
    """Test that extra edge colors are ignored when there are more specified
    colors than edges."""
    G = nx.path_graph(4, create_using=nx.DiGraph)  # 3 edges
    pos = nx.random_layout(barbell)
    edgecolors = ("r", "g", "b", "c")  # 4 edge colors
    drawn_edges = nx.draw_networkx_edges(G, pos, edge_color=edgecolors)
    for fap, expected in zip(drawn_edges, edgecolors[:-1]):
        assert mpl.colors.same_color(fap.get_edgecolor(), expected)


def test_edge_color_string_with_global_alpha_undirected():
    edge_collection = nx.draw_networkx_edges(
        barbell,
        pos=nx.random_layout(barbell),
        edgelist=[(0, 1), (1, 2)],
        edge_color="purple",
        alpha=0.2,
    )
    ec = edge_collection.get_color().squeeze()  # as rgba tuple
    assert len(edge_collection.get_paths()) == 2
    assert mpl.colors.same_color(ec[:-1], "purple")
    assert ec[-1] == 0.2


def test_edge_color_string_with_global_alpha_directed():
    drawn_edges = nx.draw_networkx_edges(
        barbell.to_directed(),
        pos=nx.random_layout(barbell),
        edgelist=[(0, 1), (1, 2)],
        edge_color="purple",
        alpha=0.2,
    )
    assert len(drawn_edges) == 2
    for fap in drawn_edges:
        ec = fap.get_edgecolor()  # As rgba tuple
        assert mpl.colors.same_color(ec[:-1], "purple")
        assert ec[-1] == 0.2


@pytest.mark.parametrize("graph_type", (nx.Graph, nx.DiGraph))
def test_edge_width_default_value(graph_type):
    """Test the default linewidth for edges drawn either via LineCollection or
    FancyArrowPatches."""
    G = nx.path_graph(2, create_using=graph_type)
    pos = {n: (n, n) for n in range(len(G))}
    drawn_edges = nx.draw_networkx_edges(G, pos)
    if isinstance(drawn_edges, list):  # directed case: list of FancyArrowPatch
        drawn_edges = drawn_edges[0]
    assert drawn_edges.get_linewidth() == 1


@pytest.mark.parametrize(
    ("edgewidth", "expected"),
    (
        (3, 3),  # single-value, non-default
        ([3], 3),  # Single value as a list
    ),
)
def test_edge_width_single_value_undirected(edgewidth, expected):
    G = nx.path_graph(4)
    pos = {n: (n, n) for n in range(len(G))}
    drawn_edges = nx.draw_networkx_edges(G, pos, width=edgewidth)
    assert len(drawn_edges.get_paths()) == 3
    assert drawn_edges.get_linewidth() == expected


@pytest.mark.parametrize(
    ("edgewidth", "expected"),
    (
        (3, 3),  # single-value, non-default
        ([3], 3),  # Single value as a list
    ),
)
def test_edge_width_single_value_directed(edgewidth, expected):
    G = nx.path_graph(4, create_using=nx.DiGraph)
    pos = {n: (n, n) for n in range(len(G))}
    drawn_edges = nx.draw_networkx_edges(G, pos, width=edgewidth)
    assert len(drawn_edges) == 3
    for fap in drawn_edges:
        assert fap.get_linewidth() == expected


@pytest.mark.parametrize(
    "edgelist",
    (
        [(0, 1), (1, 2), (2, 3)],  # one width specification per edge
        None,  #  fewer widths than edges - widths cycle
        [(0, 1), (1, 2)],  # More widths than edges - unused widths ignored
    ),
)
def test_edge_width_sequence(edgelist):
    G = barbell.to_directed()
    pos = nx.random_layout(G)
    widths = (0.5, 2.0, 12.0)
    drawn_edges = nx.draw_networkx_edges(G, pos, edgelist=edgelist, width=widths)
    for fap, expected_width in zip(drawn_edges, itertools.cycle(widths)):
        assert fap.get_linewidth() == expected_width


def test_edge_color_with_edge_vmin_vmax():
    """Test that edge_vmin and edge_vmax properly set the dynamic range of the
    color map when num edges == len(edge_colors)."""
    G = nx.path_graph(3, create_using=nx.DiGraph)
    pos = nx.random_layout(G)
    # Extract colors from the original (unscaled) colormap
    drawn_edges = nx.draw_networkx_edges(G, pos, edge_color=[0, 1.0])
    orig_colors = [e.get_edgecolor() for e in drawn_edges]
    # Colors from scaled colormap
    drawn_edges = nx.draw_networkx_edges(
        G, pos, edge_color=[0.2, 0.8], edge_vmin=0.2, edge_vmax=0.8
    )
    scaled_colors = [e.get_edgecolor() for e in drawn_edges]
    assert mpl.colors.same_color(orig_colors, scaled_colors)


def test_directed_edges_linestyle_default():
    """Test default linestyle for edges drawn with FancyArrowPatches."""
    G = nx.path_graph(4, create_using=nx.DiGraph)  # Graph with 3 edges
    pos = {n: (n, n) for n in range(len(G))}

    # edge with default style
    drawn_edges = nx.draw_networkx_edges(G, pos)
    assert len(drawn_edges) == 3
    for fap in drawn_edges:
        assert fap.get_linestyle() == "solid"


@pytest.mark.parametrize(
    "style",
    (
        "dashed",  # edge with string style
        "--",  # edge with simplified string style
        (1, (1, 1)),  # edge with (offset, onoffseq) style
    ),
)
def test_directed_edges_linestyle_single_value(style):
    """Tests support for specifying linestyles with a single value to be applied to
    all edges in ``draw_networkx_edges`` for FancyArrowPatch outputs
    (e.g. directed edges)."""

    G = nx.path_graph(4, create_using=nx.DiGraph)  # Graph with 3 edges
    pos = {n: (n, n) for n in range(len(G))}

    drawn_edges = nx.draw_networkx_edges(G, pos, style=style)
    assert len(drawn_edges) == 3
    for fap in drawn_edges:
        assert fap.get_linestyle() == style


@pytest.mark.parametrize(
    "style_seq",
    (
        ["dashed"],  # edge with string style in list
        ["--"],  # edge with simplified string style in list
        [(1, (1, 1))],  # edge with (offset, onoffseq) style in list
        ["--", "-", ":"],  # edges with styles for each edge
        ["--", "-"],  # edges with fewer styles than edges (styles cycle)
        ["--", "-", ":", "-."],  # edges with more styles than edges (extra unused)
    ),
)
def test_directed_edges_linestyle_sequence(style_seq):
    """Tests support for specifying linestyles with sequences in
    ``draw_networkx_edges`` for FancyArrowPatch outputs (e.g. directed edges)."""

    G = nx.path_graph(4, create_using=nx.DiGraph)  # Graph with 3 edges
    pos = {n: (n, n) for n in range(len(G))}

    drawn_edges = nx.draw_networkx_edges(G, pos, style=style_seq)
    assert len(drawn_edges) == 3
    for fap, style in zip(drawn_edges, itertools.cycle(style_seq)):
        assert fap.get_linestyle() == style


def test_return_types():
    from matplotlib.collections import LineCollection, PathCollection
    from matplotlib.patches import FancyArrowPatch

    G = nx.cubical_graph(nx.Graph)
    dG = nx.cubical_graph(nx.DiGraph)
    pos = nx.spring_layout(G)
    dpos = nx.spring_layout(dG)
    # nodes
    nodes = nx.draw_networkx_nodes(G, pos)
    assert isinstance(nodes, PathCollection)
    # edges
    edges = nx.draw_networkx_edges(dG, dpos, arrows=True)
    assert isinstance(edges, list)
    if len(edges) > 0:
        assert isinstance(edges[0], FancyArrowPatch)
    edges = nx.draw_networkx_edges(dG, dpos, arrows=False)
    assert isinstance(edges, LineCollection)
    edges = nx.draw_networkx_edges(G, dpos, arrows=None)
    assert isinstance(edges, LineCollection)
    edges = nx.draw_networkx_edges(dG, pos, arrows=None)
    assert isinstance(edges, list)
    if len(edges) > 0:
        assert isinstance(edges[0], FancyArrowPatch)


def test_labels_and_colors():
    G = nx.cubical_graph()
    pos = nx.spring_layout(G)  # positions for all nodes
    # nodes
    nx.draw_networkx_nodes(
        G, pos, nodelist=[0, 1, 2, 3], node_color="r", node_size=500, alpha=0.75
    )
    nx.draw_networkx_nodes(
        G,
        pos,
        nodelist=[4, 5, 6, 7],
        node_color="b",
        node_size=500,
        alpha=[0.25, 0.5, 0.75, 1.0],
    )
    # edges
    nx.draw_networkx_edges(G, pos, width=1.0, alpha=0.5)
    nx.draw_networkx_edges(
        G,
        pos,
        edgelist=[(0, 1), (1, 2), (2, 3), (3, 0)],
        width=8,
        alpha=0.5,
        edge_color="r",
    )
    nx.draw_networkx_edges(
        G,
        pos,
        edgelist=[(4, 5), (5, 6), (6, 7), (7, 4)],
        width=8,
        alpha=0.5,
        edge_color="b",
    )
    nx.draw_networkx_edges(
        G,
        pos,
        edgelist=[(4, 5), (5, 6), (6, 7), (7, 4)],
        arrows=True,
        min_source_margin=0.5,
        min_target_margin=0.75,
        width=8,
        edge_color="b",
    )
    # some math labels
    labels = {}
    labels[0] = r"$a$"
    labels[1] = r"$b$"
    labels[2] = r"$c$"
    labels[3] = r"$d$"
    labels[4] = r"$\alpha$"
    labels[5] = r"$\beta$"
    labels[6] = r"$\gamma$"
    labels[7] = r"$\delta$"
    colors = {n: "k" if n % 2 == 0 else "r" for n in range(8)}
    nx.draw_networkx_labels(G, pos, labels, font_size=16)
    nx.draw_networkx_labels(G, pos, labels, font_size=16, font_color=colors)
    nx.draw_networkx_edge_labels(G, pos, edge_labels=None, rotate=False)
    nx.draw_networkx_edge_labels(G, pos, edge_labels={(4, 5): "4-5"})
    # plt.show()


@pytest.mark.mpl_image_compare
def test_house_with_colors():
    G = nx.house_graph()
    # explicitly set positions
    fig, ax = plt.subplots()
    pos = {0: (0, 0), 1: (1, 0), 2: (0, 1), 3: (1, 1), 4: (0.5, 2.0)}

    # Plot nodes with different properties for the "wall" and "roof" nodes
    nx.draw_networkx_nodes(
        G,
        pos,
        node_size=3000,
        nodelist=[0, 1, 2, 3],
        node_color="tab:blue",
    )
    nx.draw_networkx_nodes(
        G, pos, node_size=2000, nodelist=[4], node_color="tab:orange"
    )
    nx.draw_networkx_edges(G, pos, alpha=0.5, width=6)
    # Customize axes
    ax.margins(0.11)
    plt.tight_layout()
    plt.axis("off")
    return fig


def test_axes():
    fig, ax = plt.subplots()
    nx.draw(barbell, ax=ax)
    nx.draw_networkx_edge_labels(barbell, nx.circular_layout(barbell), ax=ax)


def test_empty_graph():
    G = nx.Graph()
    nx.draw(G)


def test_draw_empty_nodes_return_values():
    # See Issue #3833
    import matplotlib.collections  # call as mpl.collections

    G = nx.Graph([(1, 2), (2, 3)])
    DG = nx.DiGraph([(1, 2), (2, 3)])
    pos = nx.circular_layout(G)
    assert isinstance(
        nx.draw_networkx_nodes(G, pos, nodelist=[]), mpl.collections.PathCollection
    )
    assert isinstance(
        nx.draw_networkx_nodes(DG, pos, nodelist=[]), mpl.collections.PathCollection
    )

    # drawing empty edges used to return an empty LineCollection or empty list.
    # Now it is always an empty list (because edges are now lists of FancyArrows)
    assert nx.draw_networkx_edges(G, pos, edgelist=[], arrows=True) == []
    assert nx.draw_networkx_edges(G, pos, edgelist=[], arrows=False) == []
    assert nx.draw_networkx_edges(DG, pos, edgelist=[], arrows=False) == []
    assert nx.draw_networkx_edges(DG, pos, edgelist=[], arrows=True) == []


def test_multigraph_edgelist_tuples():
    # See Issue #3295
    G = nx.path_graph(3, create_using=nx.MultiDiGraph)
    nx.draw_networkx(G, edgelist=[(0, 1, 0)])
    nx.draw_networkx(G, edgelist=[(0, 1, 0)], node_size=[10, 20, 0])


def test_alpha_iter():
    pos = nx.random_layout(barbell)
    fig = plt.figure()
    # with fewer alpha elements than nodes
    fig.add_subplot(131)  # Each test in a new axis object
    nx.draw_networkx_nodes(barbell, pos, alpha=[0.1, 0.2])
    # with equal alpha elements and nodes
    num_nodes = len(barbell.nodes)
    alpha = [x / num_nodes for x in range(num_nodes)]
    colors = range(num_nodes)
    fig.add_subplot(132)
    nx.draw_networkx_nodes(barbell, pos, node_color=colors, alpha=alpha)
    # with more alpha elements than nodes
    alpha.append(1)
    fig.add_subplot(133)
    nx.draw_networkx_nodes(barbell, pos, alpha=alpha)


def test_multiple_node_shapes():
    G = nx.path_graph(4)
    ax = plt.figure().add_subplot(111)
    nx.draw(G, node_shape=["o", "h", "s", "^"], ax=ax)
    scatters = [
        s for s in ax.get_children() if isinstance(s, mpl.collections.PathCollection)
    ]
    assert len(scatters) == 4


def test_individualized_font_attributes():
    G = nx.karate_club_graph()
    ax = plt.figure().add_subplot(111)
    nx.draw(
        G,
        ax=ax,
        font_color={n: "k" if n % 2 else "r" for n in G.nodes()},
        font_size={n: int(n / (34 / 15) + 5) for n in G.nodes()},
    )
    for n, t in zip(
        G.nodes(),
        [
            t
            for t in ax.get_children()
            if isinstance(t, mpl.text.Text) and len(t.get_text()) > 0
        ],
    ):
        expected = "black" if n % 2 else "red"

        assert mpl.colors.same_color(t.get_color(), expected)
        assert int(n / (34 / 15) + 5) == t.get_size()


def test_individualized_edge_attributes():
    G = nx.karate_club_graph()
    ax = plt.figure().add_subplot(111)
    arrowstyles = ["-|>" if (u + v) % 2 == 0 else "-[" for u, v in G.edges()]
    arrowsizes = [10 * (u % 2 + v % 2) + 10 for u, v in G.edges()]
    nx.draw(G, ax=ax, arrows=True, arrowstyle=arrowstyles, arrowsize=arrowsizes)
    arrows = [
        f for f in ax.get_children() if isinstance(f, mpl.patches.FancyArrowPatch)
    ]
    for e, a in zip(G.edges(), arrows):
        assert a.get_mutation_scale() == 10 * (e[0] % 2 + e[1] % 2) + 10
        expected = (
            mpl.patches.ArrowStyle.BracketB
            if sum(e) % 2
            else mpl.patches.ArrowStyle.CurveFilledB
        )
        assert isinstance(a.get_arrowstyle(), expected)


def test_error_invalid_kwds():
    with pytest.raises(ValueError, match="Received invalid argument"):
        nx.draw(barbell, foo="bar")


def test_draw_networkx_arrowsize_incorrect_size():
    G = nx.DiGraph([(0, 1), (0, 2), (0, 3), (1, 3)])
    arrowsize = [1, 2, 3]
    with pytest.raises(
        ValueError, match="arrowsize should have the same length as edgelist"
    ):
        nx.draw(G, arrowsize=arrowsize)


@pytest.mark.parametrize("arrowsize", (30, [10, 20, 30]))
def test_draw_edges_arrowsize(arrowsize):
    G = nx.DiGraph([(0, 1), (0, 2), (1, 2)])
    pos = {0: (0, 0), 1: (0, 1), 2: (1, 0)}
    edges = nx.draw_networkx_edges(G, pos=pos, arrowsize=arrowsize)

    arrowsize = itertools.repeat(arrowsize) if isinstance(arrowsize, int) else arrowsize

    for fap, expected in zip(edges, arrowsize):
        assert isinstance(fap, mpl.patches.FancyArrowPatch)
        assert fap.get_mutation_scale() == expected


@pytest.mark.parametrize("arrowstyle", ("-|>", ["-|>", "-[", "<|-|>"]))
def test_draw_edges_arrowstyle(arrowstyle):
    G = nx.DiGraph([(0, 1), (0, 2), (1, 2)])
    pos = {0: (0, 0), 1: (0, 1), 2: (1, 0)}
    edges = nx.draw_networkx_edges(G, pos=pos, arrowstyle=arrowstyle)

    arrowstyle = (
        itertools.repeat(arrowstyle) if isinstance(arrowstyle, str) else arrowstyle
    )

    arrow_objects = {
        "-|>": mpl.patches.ArrowStyle.CurveFilledB,
        "-[": mpl.patches.ArrowStyle.BracketB,
        "<|-|>": mpl.patches.ArrowStyle.CurveFilledAB,
    }

    for fap, expected in zip(edges, arrowstyle):
        assert isinstance(fap, mpl.patches.FancyArrowPatch)
        assert isinstance(fap.get_arrowstyle(), arrow_objects[expected])


def test_np_edgelist():
    # see issue #4129
    nx.draw_networkx(barbell, edgelist=np.array([(0, 2), (0, 3)]))


def test_draw_nodes_missing_node_from_position():
    G = nx.path_graph(3)
    pos = {0: (0, 0), 1: (1, 1)}  # No position for node 2
    with pytest.raises(nx.NetworkXError, match="has no position"):
        nx.draw_networkx_nodes(G, pos)


# NOTE: parametrizing on marker to test both branches of internal
# nx.draw_networkx_edges.to_marker_edge function
@pytest.mark.parametrize("node_shape", ("o", "s"))
def test_draw_edges_min_source_target_margins(node_shape):
    """Test that there is a wider gap between the node and the start of an
    incident edge when min_source_margin is specified.

    This test checks that the use of min_{source/target}_margin kwargs result
    in shorter (more padding) between the edges and source and target nodes.
    As a crude visual example, let 's' and 't' represent source and target
    nodes, respectively:

       Default:
       s-----------------------------t

       With margins:
       s   -----------------------   t

    """
    # Create a single axis object to get consistent pixel coords across
    # multiple draws
    fig, ax = plt.subplots()
    G = nx.DiGraph([(0, 1)])
    pos = {0: (0, 0), 1: (1, 0)}  # horizontal layout
    # Get leftmost and rightmost points of the FancyArrowPatch object
    # representing the edge between nodes 0 and 1 (in pixel coordinates)
    default_patch = nx.draw_networkx_edges(G, pos, ax=ax, node_shape=node_shape)[0]
    default_extent = default_patch.get_extents().corners()[::2, 0]
    # Now, do the same but with "padding" for the source and target via the
    # min_{source/target}_margin kwargs
    padded_patch = nx.draw_networkx_edges(
        G,
        pos,
        ax=ax,
        node_shape=node_shape,
        min_source_margin=100,
        min_target_margin=100,
    )[0]
    padded_extent = padded_patch.get_extents().corners()[::2, 0]

    # With padding, the left-most extent of the edge should be further to the
    # right
    assert padded_extent[0] > default_extent[0]
    # And the rightmost extent of the edge, further to the left
    assert padded_extent[1] < default_extent[1]


# NOTE: parametrizing on marker to test both branches of internal
# nx.draw_networkx_edges.to_marker_edge function
@pytest.mark.parametrize("node_shape", ("o", "s"))
def test_draw_edges_min_source_target_margins_individual(node_shape):
    """Test that there is a wider gap between the node and the start of an
    incident edge when min_source_margin is specified.

    This test checks that the use of min_{source/target}_margin kwargs result
    in shorter (more padding) between the edges and source and target nodes.
    As a crude visual example, let 's' and 't' represent source and target
    nodes, respectively:

       Default:
       s-----------------------------t

       With margins:
       s   -----------------------   t

    """
    # Create a single axis object to get consistent pixel coords across
    # multiple draws
    fig, ax = plt.subplots()
    G = nx.DiGraph([(0, 1), (1, 2)])
    pos = {0: (0, 0), 1: (1, 0), 2: (2, 0)}  # horizontal layout
    # Get leftmost and rightmost points of the FancyArrowPatch object
    # representing the edge between nodes 0 and 1 (in pixel coordinates)
    default_patch = nx.draw_networkx_edges(G, pos, ax=ax, node_shape=node_shape)
    default_extent = [d.get_extents().corners()[::2, 0] for d in default_patch]
    # Now, do the same but with "padding" for the source and target via the
    # min_{source/target}_margin kwargs
    padded_patch = nx.draw_networkx_edges(
        G,
        pos,
        ax=ax,
        node_shape=node_shape,
        min_source_margin=[98, 102],
        min_target_margin=[98, 102],
    )
    padded_extent = [p.get_extents().corners()[::2, 0] for p in padded_patch]
    for d, p in zip(default_extent, padded_extent):
        print(f"{p=}, {d=}")
        # With padding, the left-most extent of the edge should be further to the
        # right
        assert p[0] > d[0]
        # And the rightmost extent of the edge, further to the left
        assert p[1] < d[1]


def test_nonzero_selfloop_with_single_node():
    """Ensure that selfloop extent is non-zero when there is only one node."""
    # Create explicit axis object for test
    fig, ax = plt.subplots()
    # Graph with single node + self loop
    G = nx.DiGraph()
    G.add_node(0)
    G.add_edge(0, 0)
    # Draw
    patch = nx.draw_networkx_edges(G, {0: (0, 0)})[0]
    # The resulting patch must have non-zero extent
    bbox = patch.get_extents()
    assert bbox.width > 0 and bbox.height > 0
    # Cleanup
    plt.delaxes(ax)
    plt.close()


def test_nonzero_selfloop_with_single_edge_in_edgelist():
    """Ensure that selfloop extent is non-zero when only a single edge is
    specified in the edgelist.
    """
    # Create explicit axis object for test
    fig, ax = plt.subplots()
    # Graph with selfloop
    G = nx.path_graph(2, create_using=nx.DiGraph)
    G.add_edge(1, 1)
    pos = {n: (n, n) for n in G.nodes}
    # Draw only the selfloop edge via the `edgelist` kwarg
    patch = nx.draw_networkx_edges(G, pos, edgelist=[(1, 1)])[0]
    # The resulting patch must have non-zero extent
    bbox = patch.get_extents()
    assert bbox.width > 0 and bbox.height > 0
    # Cleanup
    plt.delaxes(ax)
    plt.close()


def test_apply_alpha():
    """Test apply_alpha when there is a mismatch between the number of
    supplied colors and elements.
    """
    nodelist = [0, 1, 2]
    colorlist = ["r", "g", "b"]
    alpha = 0.5
    rgba_colors = nx.drawing.nx_pylab.apply_alpha(colorlist, alpha, nodelist)
    assert all(rgba_colors[:, -1] == alpha)


def test_draw_edges_toggling_with_arrows_kwarg():
    """
    The `arrows` keyword argument is used as a 3-way switch to select which
    type of object to use for drawing edges:
      - ``arrows=None`` -> default (FancyArrowPatches for directed, else LineCollection)
      - ``arrows=True`` -> FancyArrowPatches
      - ``arrows=False`` -> LineCollection
    """
    import matplotlib.collections
    import matplotlib.patches

    UG = nx.path_graph(3)
    DG = nx.path_graph(3, create_using=nx.DiGraph)
    pos = {n: (n, n) for n in UG}

    # Use FancyArrowPatches when arrows=True, regardless of graph type
    for G in (UG, DG):
        edges = nx.draw_networkx_edges(G, pos, arrows=True)
        assert len(edges) == len(G.edges)
        assert isinstance(edges[0], mpl.patches.FancyArrowPatch)

    # Use LineCollection when arrows=False, regardless of graph type
    for G in (UG, DG):
        edges = nx.draw_networkx_edges(G, pos, arrows=False)
        assert isinstance(edges, mpl.collections.LineCollection)

    # Default behavior when arrows=None: FAPs for directed, LC's for undirected
    edges = nx.draw_networkx_edges(UG, pos)
    assert isinstance(edges, mpl.collections.LineCollection)
    edges = nx.draw_networkx_edges(DG, pos)
    assert len(edges) == len(G.edges)
    assert isinstance(edges[0], mpl.patches.FancyArrowPatch)


@pytest.mark.parametrize("drawing_func", (nx.draw, nx.draw_networkx))
def test_draw_networkx_arrows_default_undirected(drawing_func):
    import matplotlib.collections

    G = nx.path_graph(3)
    fig, ax = plt.subplots()
    drawing_func(G, ax=ax)
    assert any(isinstance(c, mpl.collections.LineCollection) for c in ax.collections)
    assert not ax.patches
    plt.delaxes(ax)
    plt.close()


@pytest.mark.parametrize("drawing_func", (nx.draw, nx.draw_networkx))
def test_draw_networkx_arrows_default_directed(drawing_func):
    import matplotlib.collections

    G = nx.path_graph(3, create_using=nx.DiGraph)
    fig, ax = plt.subplots()
    drawing_func(G, ax=ax)
    assert not any(
        isinstance(c, mpl.collections.LineCollection) for c in ax.collections
    )
    assert ax.patches
    plt.delaxes(ax)
    plt.close()


def test_edgelist_kwarg_not_ignored():
    # See gh-4994
    G = nx.path_graph(3)
    G.add_edge(0, 0)
    fig, ax = plt.subplots()
    nx.draw(G, edgelist=[(0, 1), (1, 2)], ax=ax)  # Exclude self-loop from edgelist
    assert not ax.patches
    plt.delaxes(ax)
    plt.close()


@pytest.mark.parametrize(
    ("G", "expected_n_edges"),
    ([nx.DiGraph(), 2], [nx.MultiGraph(), 4], [nx.MultiDiGraph(), 4]),
)
def test_draw_networkx_edges_multiedge_connectionstyle(G, expected_n_edges):
    """Draws edges correctly for 3 types of graphs and checks for valid length"""
    for i, (u, v) in enumerate([(0, 1), (0, 1), (0, 1), (0, 2)]):
        G.add_edge(u, v, weight=round(i / 3, 2))
    pos = {n: (n, n) for n in G}
    # Raises on insufficient connectionstyle length
    for conn_style in [
        "arc3,rad=0.1",
        ["arc3,rad=0.1", "arc3,rad=0.1"],
        ["arc3,rad=0.1", "arc3,rad=0.1", "arc3,rad=0.2"],
    ]:
        nx.draw_networkx_edges(G, pos, connectionstyle=conn_style)
        arrows = nx.draw_networkx_edges(G, pos, connectionstyle=conn_style)
        assert len(arrows) == expected_n_edges


@pytest.mark.parametrize(
    ("G", "expected_n_edges"),
    ([nx.DiGraph(), 2], [nx.MultiGraph(), 4], [nx.MultiDiGraph(), 4]),
)
def test_draw_networkx_edge_labels_multiedge_connectionstyle(G, expected_n_edges):
    """Draws labels correctly for 3 types of graphs and checks for valid length and class names"""
    for i, (u, v) in enumerate([(0, 1), (0, 1), (0, 1), (0, 2)]):
        G.add_edge(u, v, weight=round(i / 3, 2))
    pos = {n: (n, n) for n in G}
    # Raises on insufficient connectionstyle length
    arrows = nx.draw_networkx_edges(
        G, pos, connectionstyle=["arc3,rad=0.1", "arc3,rad=0.1", "arc3,rad=0.1"]
    )
    for conn_style in [
        "arc3,rad=0.1",
        ["arc3,rad=0.1", "arc3,rad=0.2"],
        ["arc3,rad=0.1", "arc3,rad=0.1", "arc3,rad=0.1"],
    ]:
        text_items = nx.draw_networkx_edge_labels(G, pos, connectionstyle=conn_style)
        assert len(text_items) == expected_n_edges
        for ti in text_items.values():
            assert ti.__class__.__name__ == "CurvedArrowText"


def test_draw_networkx_edge_label_multiedge():
    G = nx.MultiGraph()
    G.add_edge(0, 1, weight=10)
    G.add_edge(0, 1, weight=20)
    edge_labels = nx.get_edge_attributes(G, "weight")  # Includes edge keys
    pos = {n: (n, n) for n in G}
    text_items = nx.draw_networkx_edge_labels(
        G,
        pos,
        edge_labels=edge_labels,
        connectionstyle=["arc3,rad=0.1", "arc3,rad=0.2"],
    )
    assert len(text_items) == 2


def test_draw_networkx_edge_label_empty_dict():
    """Regression test for draw_networkx_edge_labels with empty dict. See
    gh-5372."""
    G = nx.path_graph(3)
    pos = {n: (n, n) for n in G.nodes}
    assert nx.draw_networkx_edge_labels(G, pos, edge_labels={}) == {}


def test_draw_networkx_edges_undirected_selfloop_colors():
    """When an edgelist is supplied along with a sequence of colors, check that
    the self-loops have the correct colors."""
    fig, ax = plt.subplots()
    # Edge list and corresponding colors
    edgelist = [(1, 3), (1, 2), (2, 3), (1, 1), (3, 3), (2, 2)]
    edge_colors = ["pink", "cyan", "black", "red", "blue", "green"]

    G = nx.Graph(edgelist)
    pos = {n: (n, n) for n in G.nodes}
    nx.draw_networkx_edges(G, pos, ax=ax, edgelist=edgelist, edge_color=edge_colors)

    # Verify that there are three fancy arrow patches (1 per self loop)
    assert len(ax.patches) == 3

    # These are points that should be contained in the self loops. For example,
    # sl_points[0] will be (1, 1.1), which is inside the "path" of the first
    # self-loop but outside the others
    sl_points = np.array(edgelist[-3:]) + np.array([0, 0.1])

    # Check that the mapping between self-loop locations and their colors is
    # correct
    for fap, clr, slp in zip(ax.patches, edge_colors[-3:], sl_points):
        assert fap.get_path().contains_point(slp)
        assert mpl.colors.same_color(fap.get_edgecolor(), clr)
    plt.delaxes(ax)
    plt.close()


@pytest.mark.parametrize(
    "fap_only_kwarg",  # Non-default values for kwargs that only apply to FAPs
    (
        {"arrowstyle": "-"},
        {"arrowsize": 20},
        {"connectionstyle": "arc3,rad=0.2"},
        {"min_source_margin": 10},
        {"min_target_margin": 10},
    ),
)
def test_user_warnings_for_unused_edge_drawing_kwargs(fap_only_kwarg):
    """Users should get a warning when they specify a non-default value for
    one of the kwargs that applies only to edges drawn with FancyArrowPatches,
    but FancyArrowPatches aren't being used under the hood."""
    G = nx.path_graph(3)
    pos = {n: (n, n) for n in G}
    fig, ax = plt.subplots()
    # By default, an undirected graph will use LineCollection to represent
    # the edges
    kwarg_name = list(fap_only_kwarg.keys())[0]
    with pytest.warns(
        UserWarning, match=f"\n\nThe {kwarg_name} keyword argument is not applicable"
    ):
        nx.draw_networkx_edges(G, pos, ax=ax, **fap_only_kwarg)
    # FancyArrowPatches are always used when `arrows=True` is specified.
    # Check that warnings are *not* raised in this case
    with warnings.catch_warnings():
        # Escalate warnings -> errors so tests fail if warnings are raised
        warnings.simplefilter("error")
        nx.draw_networkx_edges(G, pos, ax=ax, arrows=True, **fap_only_kwarg)

    plt.delaxes(ax)
    plt.close()


@pytest.mark.parametrize("draw_fn", (nx.draw, nx.draw_circular))
def test_no_warning_on_default_draw_arrowstyle(draw_fn):
    # See gh-7284
    fig, ax = plt.subplots()
    G = nx.cycle_graph(5)
    with warnings.catch_warnings(record=True) as w:
        draw_fn(G, ax=ax)
    assert len(w) == 0

    plt.delaxes(ax)
    plt.close()


@pytest.mark.parametrize("hide_ticks", [False, True])
@pytest.mark.parametrize(
    "method",
    [
        nx.draw_networkx,
        nx.draw_networkx_edge_labels,
        nx.draw_networkx_edges,
        nx.draw_networkx_labels,
        nx.draw_networkx_nodes,
    ],
)
def test_hide_ticks(method, hide_ticks):
    G = nx.path_graph(3)
    pos = {n: (n, n) for n in G.nodes}
    _, ax = plt.subplots()
    method(G, pos=pos, ax=ax, hide_ticks=hide_ticks)
    for axis in [ax.xaxis, ax.yaxis]:
        assert bool(axis.get_ticklabels()) != hide_ticks

    plt.delaxes(ax)
    plt.close()
