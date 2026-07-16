import pytest

import networkx as nx


def test_tikz_attributes():
    G = nx.path_graph(4, create_using=nx.DiGraph)
    pos = {n: (n, n) for n in G}

    G.add_edge(0, 0)
    G.edges[(0, 0)]["label"] = "Loop"
    G.edges[(0, 0)]["label_options"] = "midway"

    G.nodes[0]["style"] = "blue"
    G.nodes[1]["style"] = "line width=3,draw"
    G.nodes[2]["style"] = "circle,draw,blue!50"
    G.nodes[3]["label"] = "Stop"
    G.edges[(0, 1)]["label"] = "1st Step"
    G.edges[(0, 1)]["label_options"] = "near end"
    G.edges[(2, 3)]["label"] = "3rd Step"
    G.edges[(2, 3)]["label_options"] = "near start"
    G.edges[(2, 3)]["style"] = "bend left,green"
    G.edges[(1, 2)]["label"] = "2nd"
    G.edges[(1, 2)]["label_options"] = "pos=0.5"
    G.edges[(1, 2)]["style"] = ">->,bend right,line width=3,green!90"

    output_tex = nx.to_latex(
        G,
        pos=pos,
        as_document=False,
        tikz_options="[scale=3]",
        node_options="style",
        edge_options="style",
        node_label="label",
        edge_label="label",
        edge_label_options="label_options",
    )
    expected_tex = r"""\begin{figure}
  \begin{tikzpicture}[scale=3]
      \draw
        (0, 0) node[blue] (0){0}
        (1, 1) node[line width=3,draw] (1){1}
        (2, 2) node[circle,draw,blue!50] (2){2}
        (3, 3) node (3){Stop};
      \begin{scope}[->]
        \draw (0) to node[near end] {1st Step} (1);
        \draw[loop,] (0) to node[midway] {Loop} (0);
        \draw[>->,bend right,line width=3,green!90] (1) to node[pos=0.5] {2nd} (2);
        \draw[bend left,green] (2) to node[near start] {3rd Step} (3);
      \end{scope}
    \end{tikzpicture}
\end{figure}"""

    assert output_tex == expected_tex
    # print(output_tex)
    # # Pretty way to assert that A.to_document() == expected_tex
    # content_same = True
    # for aa, bb in zip(expected_tex.split("\n"), output_tex.split("\n")):
    #     if aa != bb:
    #         content_same = False
    #         print(f"-{aa}|\n+{bb}|")
    # assert content_same


def test_basic_multiple_graphs():
    H1 = nx.path_graph(4)
    H2 = nx.complete_graph(4)
    H3 = nx.path_graph(8)
    H4 = nx.complete_graph(8)
    captions = [
        "Path on 4 nodes",
        "Complete graph on 4 nodes",
        "Path on 8 nodes",
        "Complete graph on 8 nodes",
    ]
    labels = ["fig2a", "fig2b", "fig2c", "fig2d"]
    latex_code = nx.to_latex(
        [H1, H2, H3, H4],
        n_rows=2,
        sub_captions=captions,
        sub_labels=labels,
    )
    # print(latex_code)
    assert "begin{document}" in latex_code
    assert "begin{figure}" in latex_code
    assert latex_code.count("begin{subfigure}") == 4
    assert latex_code.count("tikzpicture") == 8
    assert latex_code.count("[-]") == 4


def test_basic_tikz():
    expected_tex = r"""\documentclass{report}
\usepackage{tikz}
\usepackage{subcaption}

\begin{document}
\begin{figure}
  \begin{subfigure}{0.5\textwidth}
  \begin{tikzpicture}[scale=2]
      \draw[gray!90]
        (0.749, 0.702) node[red!90] (0){0}
        (1.0, -0.014) node[red!90] (1){1}
        (-0.777, -0.705) node (2){2}
        (-0.984, 0.042) node (3){3}
        (-0.028, 0.375) node[cyan!90] (4){4}
        (-0.412, 0.888) node (5){5}
        (0.448, -0.856) node (6){6}
        (0.003, -0.431) node[cyan!90] (7){7};
      \begin{scope}[->,gray!90]
        \draw (0) to (4);
        \draw (0) to (5);
        \draw (0) to (6);
        \draw (0) to (7);
        \draw (1) to (4);
        \draw (1) to (5);
        \draw (1) to (6);
        \draw (1) to (7);
        \draw (2) to (4);
        \draw (2) to (5);
        \draw (2) to (6);
        \draw (2) to (7);
        \draw (3) to (4);
        \draw (3) to (5);
        \draw (3) to (6);
        \draw (3) to (7);
      \end{scope}
    \end{tikzpicture}
    \caption{My tikz number 1 of 2}\label{tikz_1_2}
  \end{subfigure}
  \begin{subfigure}{0.5\textwidth}
  \begin{tikzpicture}[scale=2]
      \draw[gray!90]
        (0.749, 0.702) node[green!90] (0){0}
        (1.0, -0.014) node[green!90] (1){1}
        (-0.777, -0.705) node (2){2}
        (-0.984, 0.042) node (3){3}
        (-0.028, 0.375) node[purple!90] (4){4}
        (-0.412, 0.888) node (5){5}
        (0.448, -0.856) node (6){6}
        (0.003, -0.431) node[purple!90] (7){7};
      \begin{scope}[->,gray!90]
        \draw (0) to (4);
        \draw (0) to (5);
        \draw (0) to (6);
        \draw (0) to (7);
        \draw (1) to (4);
        \draw (1) to (5);
        \draw (1) to (6);
        \draw (1) to (7);
        \draw (2) to (4);
        \draw (2) to (5);
        \draw (2) to (6);
        \draw (2) to (7);
        \draw (3) to (4);
        \draw (3) to (5);
        \draw (3) to (6);
        \draw (3) to (7);
      \end{scope}
    \end{tikzpicture}
    \caption{My tikz number 2 of 2}\label{tikz_2_2}
  \end{subfigure}
  \caption{A graph generated with python and latex.}
\end{figure}
\end{document}"""

    edges = [
        (0, 4),
        (0, 5),
        (0, 6),
        (0, 7),
        (1, 4),
        (1, 5),
        (1, 6),
        (1, 7),
        (2, 4),
        (2, 5),
        (2, 6),
        (2, 7),
        (3, 4),
        (3, 5),
        (3, 6),
        (3, 7),
    ]
    G = nx.DiGraph()
    G.add_nodes_from(range(8))
    G.add_edges_from(edges)
    pos = {
        0: (0.7490296171687696, 0.702353520257394),
        1: (1.0, -0.014221357723796535),
        2: (-0.7765783344161441, -0.7054170966808919),
        3: (-0.9842690223417624, 0.04177547602465483),
        4: (-0.02768523817180917, 0.3745724439551441),
        5: (-0.41154855146767433, 0.8880106515525136),
        6: (0.44780153389148264, -0.8561492709269164),
        7: (0.0032499953371383505, -0.43092436645809945),
    }

    rc_node_color = {0: "red!90", 1: "red!90", 4: "cyan!90", 7: "cyan!90"}
    gp_node_color = {0: "green!90", 1: "green!90", 4: "purple!90", 7: "purple!90"}

    H = G.copy()
    nx.set_node_attributes(G, rc_node_color, "color")
    nx.set_node_attributes(H, gp_node_color, "color")

    sub_captions = ["My tikz number 1 of 2", "My tikz number 2 of 2"]
    sub_labels = ["tikz_1_2", "tikz_2_2"]

    output_tex = nx.to_latex(
        [G, H],
        [pos, pos],
        tikz_options="[scale=2]",
        default_node_options="gray!90",
        default_edge_options="gray!90",
        node_options="color",
        sub_captions=sub_captions,
        sub_labels=sub_labels,
        caption="A graph generated with python and latex.",
        n_rows=2,
        as_document=True,
    )

    assert output_tex == expected_tex
    # print(output_tex)
    # # Pretty way to assert that A.to_document() == expected_tex
    # content_same = True
    # for aa, bb in zip(expected_tex.split("\n"), output_tex.split("\n")):
    #     if aa != bb:
    #         content_same = False
    #         print(f"-{aa}|\n+{bb}|")
    # assert content_same


def test_exception_pos_single_graph(to_latex=nx.to_latex):
    # smoke test that pos can be a string
    G = nx.path_graph(4)
    to_latex(G, pos="pos")

    # must include all nodes
    pos = {0: (1, 2), 1: (0, 1), 2: (2, 1)}
    with pytest.raises(nx.NetworkXError):
        to_latex(G, pos)

    # must have 2 values
    pos[3] = (1, 2, 3)
    with pytest.raises(nx.NetworkXError):
        to_latex(G, pos)
    pos[3] = 2
    with pytest.raises(nx.NetworkXError):
        to_latex(G, pos)

    # check that passes with 2 values
    pos[3] = (3, 2)
    to_latex(G, pos)


def test_exception_multiple_graphs(to_latex=nx.to_latex):
    G = nx.path_graph(3)
    pos_bad = {0: (1, 2), 1: (0, 1)}
    pos_OK = {0: (1, 2), 1: (0, 1), 2: (2, 1)}
    fourG = [G, G, G, G]
    fourpos = [pos_OK, pos_OK, pos_OK, pos_OK]

    # input single dict to use for all graphs
    to_latex(fourG, pos_OK)
    with pytest.raises(nx.NetworkXError):
        to_latex(fourG, pos_bad)

    # input list of dicts to use for all graphs
    to_latex(fourG, fourpos)
    with pytest.raises(nx.NetworkXError):
        to_latex(fourG, [pos_bad, pos_bad, pos_bad, pos_bad])

    # every pos dict must include all nodes
    with pytest.raises(nx.NetworkXError):
        to_latex(fourG, [pos_OK, pos_OK, pos_bad, pos_OK])

    # test sub_captions and sub_labels (len must match Gbunch)
    with pytest.raises(nx.NetworkXError):
        to_latex(fourG, fourpos, sub_captions=["hi", "hi"])

    with pytest.raises(nx.NetworkXError):
        to_latex(fourG, fourpos, sub_labels=["hi", "hi"])

    # all pass
    to_latex(fourG, fourpos, sub_captions=["hi"] * 4, sub_labels=["lbl"] * 4)


def test_exception_multigraph():
    G = nx.path_graph(4, create_using=nx.MultiGraph)
    G.add_edge(1, 2)
    with pytest.raises(nx.NetworkXNotImplemented):
        nx.to_latex(G)
