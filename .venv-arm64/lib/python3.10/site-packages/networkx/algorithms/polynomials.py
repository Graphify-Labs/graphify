"""Provides algorithms supporting the computation of graph polynomials.

Graph polynomials are polynomial-valued graph invariants that encode a wide
variety of structural information. Examples include the Tutte polynomial,
chromatic polynomial, characteristic polynomial, and matching polynomial. An
extensive treatment is provided in [1]_.

For a simple example, the `~sympy.matrices.matrices.MatrixDeterminant.charpoly`
method can be used to compute the characteristic polynomial from the adjacency
matrix of a graph. Consider the complete graph ``K_4``:

>>> import sympy
>>> x = sympy.Symbol("x")
>>> G = nx.complete_graph(4)
>>> A = nx.to_numpy_array(G, dtype=int)
>>> M = sympy.SparseMatrix(A)
>>> M.charpoly(x).as_expr()
x**4 - 6*x**2 - 8*x - 3


.. [1] Y. Shi, M. Dehmer, X. Li, I. Gutman,
   "Graph Polynomials"
"""

from collections import deque

import networkx as nx
from networkx.utils import not_implemented_for

__all__ = ["tutte_polynomial", "chromatic_polynomial"]


@not_implemented_for("directed")
@nx._dispatchable
def tutte_polynomial(G):
    r"""Returns the Tutte polynomial of `G`

    This function computes the Tutte polynomial via an iterative version of
    the deletion-contraction algorithm.

    The Tutte polynomial `T_G(x, y)` is a fundamental graph polynomial invariant in
    two variables. It encodes a wide array of information related to the
    edge-connectivity of a graph; "Many problems about graphs can be reduced to
    problems of finding and evaluating the Tutte polynomial at certain values" [1]_.
    In fact, every deletion-contraction-expressible feature of a graph is a
    specialization of the Tutte polynomial [2]_ (see Notes for examples).

    There are several equivalent definitions; here are three:

    Def 1 (rank-nullity expansion): For `G` an undirected graph, `n(G)` the
    number of vertices of `G`, `E` the edge set of `G`, `V` the vertex set of
    `G`, and `c(A)` the number of connected components of the graph with vertex
    set `V` and edge set `A` [3]_:

    .. math::

        T_G(x, y) = \sum_{A \in E} (x-1)^{c(A) - c(E)} (y-1)^{c(A) + |A| - n(G)}

    Def 2 (spanning tree expansion): Let `G` be an undirected graph, `T` a spanning
    tree of `G`, and `E` the edge set of `G`. Let `E` have an arbitrary strict
    linear order `L`. Let `B_e` be the unique minimal nonempty edge cut of
    $E \setminus T \cup {e}$. An edge `e` is internally active with respect to
    `T` and `L` if `e` is the least edge in `B_e` according to the linear order
    `L`. The internal activity of `T` (denoted `i(T)`) is the number of edges
    in $E \setminus T$ that are internally active with respect to `T` and `L`.
    Let `P_e` be the unique path in $T \cup {e}$ whose source and target vertex
    are the same. An edge `e` is externally active with respect to `T` and `L`
    if `e` is the least edge in `P_e` according to the linear order `L`. The
    external activity of `T` (denoted `e(T)`) is the number of edges in
    $E \setminus T$ that are externally active with respect to `T` and `L`.
    Then [4]_ [5]_:

    .. math::

        T_G(x, y) = \sum_{T \text{ a spanning tree of } G} x^{i(T)} y^{e(T)}

    Def 3 (deletion-contraction recurrence): For `G` an undirected graph, `G-e`
    the graph obtained from `G` by deleting edge `e`, `G/e` the graph obtained
    from `G` by contracting edge `e`, `k(G)` the number of cut-edges of `G`,
    and `l(G)` the number of self-loops of `G`:

    .. math::
        T_G(x, y) = \begin{cases}
    	   x^{k(G)} y^{l(G)}, & \text{if all edges are cut-edges or self-loops} \\
           T_{G-e}(x, y) + T_{G/e}(x, y), & \text{otherwise, for an arbitrary edge $e$ not a cut-edge or loop}
        \end{cases}

    Parameters
    ----------
    G : NetworkX graph

    Returns
    -------
    instance of `sympy.core.add.Add`
        A Sympy expression representing the Tutte polynomial for `G`.

    Examples
    --------
    >>> C = nx.cycle_graph(5)
    >>> nx.tutte_polynomial(C)
    x**4 + x**3 + x**2 + x + y

    >>> D = nx.diamond_graph()
    >>> nx.tutte_polynomial(D)
    x**3 + 2*x**2 + 2*x*y + x + y**2 + y

    Notes
    -----
    Some specializations of the Tutte polynomial:

    - `T_G(1, 1)` counts the number of spanning trees of `G`
    - `T_G(1, 2)` counts the number of connected spanning subgraphs of `G`
    - `T_G(2, 1)` counts the number of spanning forests in `G`
    - `T_G(0, 2)` counts the number of strong orientations of `G`
    - `T_G(2, 0)` counts the number of acyclic orientations of `G`

    Edge contraction is defined and deletion-contraction is introduced in [6]_.
    Combinatorial meaning of the coefficients is introduced in [7]_.
    Universality, properties, and applications are discussed in [8]_.

    Practically, up-front computation of the Tutte polynomial may be useful when
    users wish to repeatedly calculate edge-connectivity-related information
    about one or more graphs.

    References
    ----------
    .. [1] M. Brandt,
       "The Tutte Polynomial."
       Talking About Combinatorial Objects Seminar, 2015
       https://math.berkeley.edu/~brandtm/talks/tutte.pdf
    .. [2] A. Björklund, T. Husfeldt, P. Kaski, M. Koivisto,
       "Computing the Tutte polynomial in vertex-exponential time"
       49th Annual IEEE Symposium on Foundations of Computer Science, 2008
       https://ieeexplore.ieee.org/abstract/document/4691000
    .. [3] Y. Shi, M. Dehmer, X. Li, I. Gutman,
       "Graph Polynomials," p. 14
    .. [4] Y. Shi, M. Dehmer, X. Li, I. Gutman,
       "Graph Polynomials," p. 46
    .. [5] A. Nešetril, J. Goodall,
       "Graph invariants, homomorphisms, and the Tutte polynomial"
       https://iuuk.mff.cuni.cz/~andrew/Tutte.pdf
    .. [6] D. B. West,
       "Introduction to Graph Theory," p. 84
    .. [7] G. Coutinho,
       "A brief introduction to the Tutte polynomial"
       Structural Analysis of Complex Networks, 2011
       https://homepages.dcc.ufmg.br/~gabriel/seminars/coutinho_tuttepolynomial_seminar.pdf
    .. [8] J. A. Ellis-Monaghan, C. Merino,
       "Graph polynomials and their applications I: The Tutte polynomial"
       Structural Analysis of Complex Networks, 2011
       https://arxiv.org/pdf/0803.3079.pdf
    """
    import sympy

    x = sympy.Symbol("x")
    y = sympy.Symbol("y")
    stack = deque()
    stack.append(nx.MultiGraph(G))

    polynomial = 0
    while stack:
        G = stack.pop()
        bridges = set(nx.bridges(G))

        e = None
        for i in G.edges:
            if (i[0], i[1]) not in bridges and i[0] != i[1]:
                e = i
                break
        if not e:
            loops = list(nx.selfloop_edges(G, keys=True))
            polynomial += x ** len(bridges) * y ** len(loops)
        else:
            # deletion-contraction
            C = nx.contracted_edge(G, e, self_loops=True)
            C.remove_edge(e[0], e[0])
            G.remove_edge(*e)
            stack.append(G)
            stack.append(C)
    return sympy.simplify(polynomial)


@not_implemented_for("directed")
@nx._dispatchable
def chromatic_polynomial(G):
    r"""Returns the chromatic polynomial of `G`

    This function computes the chromatic polynomial via an iterative version of
    the deletion-contraction algorithm.

    The chromatic polynomial `X_G(x)` is a fundamental graph polynomial
    invariant in one variable. Evaluating `X_G(k)` for an natural number `k`
    enumerates the proper k-colorings of `G`.

    There are several equivalent definitions; here are three:

    Def 1 (explicit formula):
    For `G` an undirected graph, `c(G)` the number of connected components of
    `G`, `E` the edge set of `G`, and `G(S)` the spanning subgraph of `G` with
    edge set `S` [1]_:

    .. math::

        X_G(x) = \sum_{S \subseteq E} (-1)^{|S|} x^{c(G(S))}


    Def 2 (interpolating polynomial):
    For `G` an undirected graph, `n(G)` the number of vertices of `G`, `k_0 = 0`,
    and `k_i` the number of distinct ways to color the vertices of `G` with `i`
    unique colors (for `i` a natural number at most `n(G)`), `X_G(x)` is the
    unique Lagrange interpolating polynomial of degree `n(G)` through the points
    `(0, k_0), (1, k_1), \dots, (n(G), k_{n(G)})` [2]_.


    Def 3 (chromatic recurrence):
    For `G` an undirected graph, `G-e` the graph obtained from `G` by deleting
    edge `e`, `G/e` the graph obtained from `G` by contracting edge `e`, `n(G)`
    the number of vertices of `G`, and `e(G)` the number of edges of `G` [3]_:

    .. math::
        X_G(x) = \begin{cases}
    	   x^{n(G)}, & \text{if $e(G)=0$} \\
           X_{G-e}(x) - X_{G/e}(x), & \text{otherwise, for an arbitrary edge $e$}
        \end{cases}

    This formulation is also known as the Fundamental Reduction Theorem [4]_.


    Parameters
    ----------
    G : NetworkX graph

    Returns
    -------
    instance of `sympy.core.add.Add`
        A Sympy expression representing the chromatic polynomial for `G`.

    Examples
    --------
    >>> C = nx.cycle_graph(5)
    >>> nx.chromatic_polynomial(C)
    x**5 - 5*x**4 + 10*x**3 - 10*x**2 + 4*x

    >>> G = nx.complete_graph(4)
    >>> nx.chromatic_polynomial(G)
    x**4 - 6*x**3 + 11*x**2 - 6*x

    Notes
    -----
    Interpretation of the coefficients is discussed in [5]_. Several special
    cases are listed in [2]_.

    The chromatic polynomial is a specialization of the Tutte polynomial; in
    particular, ``X_G(x) = T_G(x, 0)`` [6]_.

    The chromatic polynomial may take negative arguments, though evaluations
    may not have chromatic interpretations. For instance, ``X_G(-1)`` enumerates
    the acyclic orientations of `G` [7]_.

    References
    ----------
    .. [1] D. B. West,
       "Introduction to Graph Theory," p. 222
    .. [2] E. W. Weisstein
       "Chromatic Polynomial"
       MathWorld--A Wolfram Web Resource
       https://mathworld.wolfram.com/ChromaticPolynomial.html
    .. [3] D. B. West,
       "Introduction to Graph Theory," p. 221
    .. [4] J. Zhang, J. Goodall,
       "An Introduction to Chromatic Polynomials"
       https://math.mit.edu/~apost/courses/18.204_2018/Julie_Zhang_paper.pdf
    .. [5] R. C. Read,
       "An Introduction to Chromatic Polynomials"
       Journal of Combinatorial Theory, 1968
       https://math.berkeley.edu/~mrklug/ReadChromatic.pdf
    .. [6] W. T. Tutte,
       "Graph-polynomials"
       Advances in Applied Mathematics, 2004
       https://www.sciencedirect.com/science/article/pii/S0196885803000411
    .. [7] R. P. Stanley,
       "Acyclic orientations of graphs"
       Discrete Mathematics, 2006
       https://math.mit.edu/~rstan/pubs/pubfiles/18.pdf
    """
    import sympy

    x = sympy.Symbol("x")
    stack = deque()
    stack.append(nx.MultiGraph(G, contraction_idx=0))

    polynomial = 0
    while stack:
        G = stack.pop()
        edges = list(G.edges)
        if not edges:
            polynomial += (-1) ** G.graph["contraction_idx"] * x ** len(G)
        else:
            e = edges[0]
            C = nx.contracted_edge(G, e, self_loops=True)
            C.graph["contraction_idx"] = G.graph["contraction_idx"] + 1
            C.remove_edge(e[0], e[0])
            G.remove_edge(*e)
            stack.append(G)
            stack.append(C)
    return polynomial
