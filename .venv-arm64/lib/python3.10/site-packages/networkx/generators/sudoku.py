"""Generator for Sudoku graphs

This module gives a generator for n-Sudoku graphs. It can be used to develop
algorithms for solving or generating Sudoku puzzles.

A completed Sudoku grid is a 9x9 array of integers between 1 and 9, with no
number appearing twice in the same row, column, or 3x3 box.

+---------+---------+---------+
| | 8 6 4 | | 3 7 1 | | 2 5 9 |
| | 3 2 5 | | 8 4 9 | | 7 6 1 |
| | 9 7 1 | | 2 6 5 | | 8 4 3 |
+---------+---------+---------+
| | 4 3 6 | | 1 9 2 | | 5 8 7 |
| | 1 9 8 | | 6 5 7 | | 4 3 2 |
| | 2 5 7 | | 4 8 3 | | 9 1 6 |
+---------+---------+---------+
| | 6 8 9 | | 7 3 4 | | 1 2 5 |
| | 7 1 3 | | 5 2 8 | | 6 9 4 |
| | 5 4 2 | | 9 1 6 | | 3 7 8 |
+---------+---------+---------+


The Sudoku graph is an undirected graph with 81 vertices, corresponding to
the cells of a Sudoku grid. It is a regular graph of degree 20. Two distinct
vertices are adjacent if and only if the corresponding cells belong to the
same row, column, or box. A completed Sudoku grid corresponds to a vertex
coloring of the Sudoku graph with nine colors.

More generally, the n-Sudoku graph is a graph with n^4 vertices, corresponding
to the cells of an n^2 by n^2 grid. Two distinct vertices are adjacent if and
only if they belong to the same row, column, or n by n box.

References
----------
.. [1] Herzberg, A. M., & Murty, M. R. (2007). Sudoku squares and chromatic
    polynomials. Notices of the AMS, 54(6), 708-717.
.. [2] Sander, Torsten (2009), "Sudoku graphs are integral",
    Electronic Journal of Combinatorics, 16 (1): Note 25, 7pp, MR 2529816
.. [3] Wikipedia contributors. "Glossary of Sudoku." Wikipedia, The Free
    Encyclopedia, 3 Dec. 2019. Web. 22 Dec. 2019.
"""

import networkx as nx
from networkx.exception import NetworkXError

__all__ = ["sudoku_graph"]


@nx._dispatchable(graphs=None, returns_graph=True)
def sudoku_graph(n=3):
    """Returns the n-Sudoku graph. The default value of n is 3.

    The n-Sudoku graph is a graph with n^4 vertices, corresponding to the
    cells of an n^2 by n^2 grid. Two distinct vertices are adjacent if and
    only if they belong to the same row, column, or n-by-n box.

    Parameters
    ----------
    n: integer
       The order of the Sudoku graph, equal to the square root of the
       number of rows. The default is 3.

    Returns
    -------
    NetworkX graph
        The n-Sudoku graph Sud(n).

    Examples
    --------
    >>> G = nx.sudoku_graph()
    >>> G.number_of_nodes()
    81
    >>> G.number_of_edges()
    810
    >>> sorted(G.neighbors(42))
    [6, 15, 24, 33, 34, 35, 36, 37, 38, 39, 40, 41, 43, 44, 51, 52, 53, 60, 69, 78]
    >>> G = nx.sudoku_graph(2)
    >>> G.number_of_nodes()
    16
    >>> G.number_of_edges()
    56

    References
    ----------
    .. [1] Herzberg, A. M., & Murty, M. R. (2007). Sudoku squares and chromatic
       polynomials. Notices of the AMS, 54(6), 708-717.
    .. [2] Sander, Torsten (2009), "Sudoku graphs are integral",
       Electronic Journal of Combinatorics, 16 (1): Note 25, 7pp, MR 2529816
    .. [3] Wikipedia contributors. "Glossary of Sudoku." Wikipedia, The Free
       Encyclopedia, 3 Dec. 2019. Web. 22 Dec. 2019.
    """

    if n < 0:
        raise NetworkXError("The order must be greater than or equal to zero.")

    n2 = n * n
    n3 = n2 * n
    n4 = n3 * n

    # Construct an empty graph with n^4 nodes
    G = nx.empty_graph(n4)

    # A Sudoku graph of order 0 or 1 has no edges
    if n < 2:
        return G

    # Add edges for cells in the same row
    for row_no in range(n2):
        row_start = row_no * n2
        for j in range(1, n2):
            for i in range(j):
                G.add_edge(row_start + i, row_start + j)

    # Add edges for cells in the same column
    for col_no in range(n2):
        for j in range(col_no, n4, n2):
            for i in range(col_no, j, n2):
                G.add_edge(i, j)

    # Add edges for cells in the same box
    for band_no in range(n):
        for stack_no in range(n):
            box_start = n3 * band_no + n * stack_no
            for j in range(1, n2):
                for i in range(j):
                    u = box_start + (i % n) + n2 * (i // n)
                    v = box_start + (j % n) + n2 * (j // n)
                    G.add_edge(u, v)

    return G
