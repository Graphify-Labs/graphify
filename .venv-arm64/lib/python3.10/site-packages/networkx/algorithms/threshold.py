"""
Threshold Graphs - Creation, manipulation and identification.
"""

from math import sqrt

import networkx as nx
from networkx.utils import py_random_state

__all__ = ["is_threshold_graph", "find_threshold_graph"]


@nx._dispatchable
def is_threshold_graph(G):
    """
    Returns `True` if `G` is a threshold graph.

    Parameters
    ----------
    G : NetworkX graph instance
        An instance of `Graph`, `DiGraph`, `MultiGraph` or `MultiDiGraph`

    Returns
    -------
    bool
        `True` if `G` is a threshold graph, `False` otherwise.

    Examples
    --------
    >>> from networkx.algorithms.threshold import is_threshold_graph
    >>> G = nx.path_graph(3)
    >>> is_threshold_graph(G)
    True
    >>> G = nx.barbell_graph(3, 3)
    >>> is_threshold_graph(G)
    False

    References
    ----------
    .. [1] Threshold graphs: https://en.wikipedia.org/wiki/Threshold_graph
    """
    return is_threshold_sequence([d for n, d in G.degree()])


def is_threshold_sequence(degree_sequence):
    """
    Returns True if the sequence is a threshold degree sequence.

    Uses the property that a threshold graph must be constructed by
    adding either dominating or isolated nodes. Thus, it can be
    deconstructed iteratively by removing a node of degree zero or a
    node that connects to the remaining nodes.  If this deconstruction
    fails then the sequence is not a threshold sequence.
    """
    ds = degree_sequence[:]  # get a copy so we don't destroy original
    ds.sort()
    while ds:
        if ds[0] == 0:  # if isolated node
            ds.pop(0)  # remove it
            continue
        if ds[-1] != len(ds) - 1:  # is the largest degree node dominating?
            return False  # no, not a threshold degree sequence
        ds.pop()  # yes, largest is the dominating node
        ds = [d - 1 for d in ds]  # remove it and decrement all degrees
    return True


def creation_sequence(degree_sequence, with_labels=False, compact=False):
    """
    Determines the creation sequence for the given threshold degree sequence.

    The creation sequence is a list of single characters 'd'
    or 'i': 'd' for dominating or 'i' for isolated vertices.
    Dominating vertices are connected to all vertices present when it
    is added.  The first node added is by convention 'd'.
    This list can be converted to a string if desired using "".join(cs)

    If with_labels==True:
    Returns a list of 2-tuples containing the vertex number
    and a character 'd' or 'i' which describes the type of vertex.

    If compact==True:
    Returns the creation sequence in a compact form that is the number
    of 'i's and 'd's alternating.
    Examples:
    [1,2,2,3] represents d,i,i,d,d,i,i,i
    [3,1,2] represents d,d,d,i,d,d

    Notice that the first number is the first vertex to be used for
    construction and so is always 'd'.

    with_labels and compact cannot both be True.

    Returns None if the sequence is not a threshold sequence
    """
    if with_labels and compact:
        raise ValueError("compact sequences cannot be labeled")

    # make an indexed copy
    if isinstance(degree_sequence, dict):  # labeled degree sequence
        ds = [[degree, label] for (label, degree) in degree_sequence.items()]
    else:
        ds = [[d, i] for i, d in enumerate(degree_sequence)]
    ds.sort()
    cs = []  # creation sequence
    while ds:
        if ds[0][0] == 0:  # isolated node
            (d, v) = ds.pop(0)
            if len(ds) > 0:  # make sure we start with a d
                cs.insert(0, (v, "i"))
            else:
                cs.insert(0, (v, "d"))
            continue
        if ds[-1][0] != len(ds) - 1:  # Not dominating node
            return None  # not a threshold degree sequence
        (d, v) = ds.pop()
        cs.insert(0, (v, "d"))
        ds = [[d[0] - 1, d[1]] for d in ds]  # decrement due to removing node

    if with_labels:
        return cs
    if compact:
        return make_compact(cs)
    return [v[1] for v in cs]  # not labeled


def make_compact(creation_sequence):
    """
    Returns the creation sequence in a compact form
    that is the number of 'i's and 'd's alternating.

    Examples
    --------
    >>> from networkx.algorithms.threshold import make_compact
    >>> make_compact(["d", "i", "i", "d", "d", "i", "i", "i"])
    [1, 2, 2, 3]
    >>> make_compact(["d", "d", "d", "i", "d", "d"])
    [3, 1, 2]

    Notice that the first number is the first vertex
    to be used for construction and so is always 'd'.

    Labeled creation sequences lose their labels in the
    compact representation.

    >>> make_compact([3, 1, 2])
    [3, 1, 2]
    """
    first = creation_sequence[0]
    if isinstance(first, str):  # creation sequence
        cs = creation_sequence[:]
    elif isinstance(first, tuple):  # labeled creation sequence
        cs = [s[1] for s in creation_sequence]
    elif isinstance(first, int):  # compact creation sequence
        return creation_sequence
    else:
        raise TypeError("Not a valid creation sequence type")

    ccs = []
    count = 1  # count the run lengths of d's or i's.
    for i in range(1, len(cs)):
        if cs[i] == cs[i - 1]:
            count += 1
        else:
            ccs.append(count)
            count = 1
    ccs.append(count)  # don't forget the last one
    return ccs


def uncompact(creation_sequence):
    """
    Converts a compact creation sequence for a threshold
    graph to a standard creation sequence (unlabeled).
    If the creation_sequence is already standard, return it.
    See creation_sequence.
    """
    first = creation_sequence[0]
    if isinstance(first, str):  # creation sequence
        return creation_sequence
    elif isinstance(first, tuple):  # labeled creation sequence
        return creation_sequence
    elif isinstance(first, int):  # compact creation sequence
        ccscopy = creation_sequence[:]
    else:
        raise TypeError("Not a valid creation sequence type")
    cs = []
    while ccscopy:
        cs.extend(ccscopy.pop(0) * ["d"])
        if ccscopy:
            cs.extend(ccscopy.pop(0) * ["i"])
    return cs


def creation_sequence_to_weights(creation_sequence):
    """
    Returns a list of node weights which create the threshold
    graph designated by the creation sequence.  The weights
    are scaled so that the threshold is 1.0.  The order of the
    nodes is the same as that in the creation sequence.
    """
    # Turn input sequence into a labeled creation sequence
    first = creation_sequence[0]
    if isinstance(first, str):  # creation sequence
        if isinstance(creation_sequence, list):
            wseq = creation_sequence[:]
        else:
            wseq = list(creation_sequence)  # string like 'ddidid'
    elif isinstance(first, tuple):  # labeled creation sequence
        wseq = [v[1] for v in creation_sequence]
    elif isinstance(first, int):  # compact creation sequence
        wseq = uncompact(creation_sequence)
    else:
        raise TypeError("Not a valid creation sequence type")
    # pass through twice--first backwards
    wseq.reverse()
    w = 0
    prev = "i"
    for j, s in enumerate(wseq):
        if s == "i":
            wseq[j] = w
            prev = s
        elif prev == "i":
            prev = s
            w += 1
    wseq.reverse()  # now pass through forwards
    for j, s in enumerate(wseq):
        if s == "d":
            wseq[j] = w
            prev = s
        elif prev == "d":
            prev = s
            w += 1
    # Now scale weights
    if prev == "d":
        w += 1
    wscale = 1 / w
    return [ww * wscale for ww in wseq]
    # return wseq


def weights_to_creation_sequence(
    weights, threshold=1, with_labels=False, compact=False
):
    """
    Returns a creation sequence for a threshold graph
    determined by the weights and threshold given as input.
    If the sum of two node weights is greater than the
    threshold value, an edge is created between these nodes.

    The creation sequence is a list of single characters 'd'
    or 'i': 'd' for dominating or 'i' for isolated vertices.
    Dominating vertices are connected to all vertices present
    when it is added.  The first node added is by convention 'd'.

    If with_labels==True:
    Returns a list of 2-tuples containing the vertex number
    and a character 'd' or 'i' which describes the type of vertex.

    If compact==True:
    Returns the creation sequence in a compact form that is the number
    of 'i's and 'd's alternating.
    Examples:
    [1,2,2,3] represents d,i,i,d,d,i,i,i
    [3,1,2] represents d,d,d,i,d,d

    Notice that the first number is the first vertex to be used for
    construction and so is always 'd'.

    with_labels and compact cannot both be True.
    """
    if with_labels and compact:
        raise ValueError("compact sequences cannot be labeled")

    # make an indexed copy
    if isinstance(weights, dict):  # labeled weights
        wseq = [[w, label] for (label, w) in weights.items()]
    else:
        wseq = [[w, i] for i, w in enumerate(weights)]
    wseq.sort()
    cs = []  # creation sequence
    cutoff = threshold - wseq[-1][0]
    while wseq:
        if wseq[0][0] < cutoff:  # isolated node
            (w, label) = wseq.pop(0)
            cs.append((label, "i"))
        else:
            (w, label) = wseq.pop()
            cs.append((label, "d"))
            cutoff = threshold - wseq[-1][0]
        if len(wseq) == 1:  # make sure we start with a d
            (w, label) = wseq.pop()
            cs.append((label, "d"))
    # put in correct order
    cs.reverse()

    if with_labels:
        return cs
    if compact:
        return make_compact(cs)
    return [v[1] for v in cs]  # not labeled


# Manipulating NetworkX.Graphs in context of threshold graphs
@nx._dispatchable(graphs=None, returns_graph=True)
def threshold_graph(creation_sequence, create_using=None):
    """
    Create a threshold graph from the creation sequence or compact
    creation_sequence.

    The input sequence can be a

    creation sequence (e.g. ['d','i','d','d','d','i'])
    labeled creation sequence (e.g. [(0,'d'),(2,'d'),(1,'i')])
    compact creation sequence (e.g. [2,1,1,2,0])

    Use cs=creation_sequence(degree_sequence,labeled=True)
    to convert a degree sequence to a creation sequence.

    Returns None if the sequence is not valid
    """
    # Turn input sequence into a labeled creation sequence
    first = creation_sequence[0]
    if isinstance(first, str):  # creation sequence
        ci = list(enumerate(creation_sequence))
    elif isinstance(first, tuple):  # labeled creation sequence
        ci = creation_sequence[:]
    elif isinstance(first, int):  # compact creation sequence
        cs = uncompact(creation_sequence)
        ci = list(enumerate(cs))
    else:
        print("not a valid creation sequence type")
        return None

    G = nx.empty_graph(0, create_using)
    if G.is_directed():
        raise nx.NetworkXError("Directed Graph not supported")

    G.name = "Threshold Graph"

    # add nodes and edges
    # if type is 'i' just add nodea
    # if type is a d connect to everything previous
    while ci:
        (v, node_type) = ci.pop(0)
        if node_type == "d":  # dominating type, connect to all existing nodes
            # We use `for u in list(G):` instead of
            # `for u in G:` because we edit the graph `G` in
            # the loop. Hence using an iterator will result in
            # `RuntimeError: dictionary changed size during iteration`
            for u in list(G):
                G.add_edge(v, u)
        G.add_node(v)
    return G


@nx._dispatchable
def find_alternating_4_cycle(G):
    """
    Returns False if there aren't any alternating 4 cycles.
    Otherwise returns the cycle as [a,b,c,d] where (a,b)
    and (c,d) are edges and (a,c) and (b,d) are not.
    """
    for u, v in G.edges():
        for w in G.nodes():
            if not G.has_edge(u, w) and u != w:
                for x in G.neighbors(w):
                    if not G.has_edge(v, x) and v != x:
                        return [u, v, w, x]
    return False


@nx._dispatchable(returns_graph=True)
def find_threshold_graph(G, create_using=None):
    """
    Returns a threshold subgraph that is close to largest in `G`.

    The threshold graph will contain the largest degree node in G.

    Parameters
    ----------
    G : NetworkX graph instance
        An instance of `Graph`, or `MultiDiGraph`
    create_using : NetworkX graph class or `None` (default), optional
        Type of graph to use when constructing the threshold graph.
        If `None`, infer the appropriate graph type from the input.

    Returns
    -------
    graph :
        A graph instance representing the threshold graph

    Examples
    --------
    >>> from networkx.algorithms.threshold import find_threshold_graph
    >>> G = nx.barbell_graph(3, 3)
    >>> T = find_threshold_graph(G)
    >>> T.nodes  # may vary
    NodeView((7, 8, 5, 6))

    References
    ----------
    .. [1] Threshold graphs: https://en.wikipedia.org/wiki/Threshold_graph
    """
    return threshold_graph(find_creation_sequence(G), create_using)


@nx._dispatchable
def find_creation_sequence(G):
    """
    Find a threshold subgraph that is close to largest in G.
    Returns the labeled creation sequence of that threshold graph.
    """
    cs = []
    # get a local pointer to the working part of the graph
    H = G
    while H.order() > 0:
        # get new degree sequence on subgraph
        dsdict = dict(H.degree())
        ds = [(d, v) for v, d in dsdict.items()]
        ds.sort()
        # Update threshold graph nodes
        if ds[-1][0] == 0:  # all are isolated
            cs.extend(zip(dsdict, ["i"] * (len(ds) - 1) + ["d"]))
            break  # Done!
        # pull off isolated nodes
        while ds[0][0] == 0:
            (d, iso) = ds.pop(0)
            cs.append((iso, "i"))
        # find new biggest node
        (d, bigv) = ds.pop()
        # add edges of star to t_g
        cs.append((bigv, "d"))
        # form subgraph of neighbors of big node
        H = H.subgraph(H.neighbors(bigv))
    cs.reverse()
    return cs


# Properties of Threshold Graphs
def triangles(creation_sequence):
    """
    Compute number of triangles in the threshold graph with the
    given creation sequence.
    """
    # shortcut algorithm that doesn't require computing number
    # of triangles at each node.
    cs = creation_sequence  # alias
    dr = cs.count("d")  # number of d's in sequence
    ntri = dr * (dr - 1) * (dr - 2) / 6  # number of triangles in clique of nd d's
    # now add dr choose 2 triangles for every 'i' in sequence where
    # dr is the number of d's to the right of the current i
    for i, typ in enumerate(cs):
        if typ == "i":
            ntri += dr * (dr - 1) / 2
        else:
            dr -= 1
    return ntri


def triangle_sequence(creation_sequence):
    """
    Return triangle sequence for the given threshold graph creation sequence.

    """
    cs = creation_sequence
    seq = []
    dr = cs.count("d")  # number of d's to the right of the current pos
    dcur = (dr - 1) * (dr - 2) // 2  # number of triangles through a node of clique dr
    irun = 0  # number of i's in the last run
    drun = 0  # number of d's in the last run
    for i, sym in enumerate(cs):
        if sym == "d":
            drun += 1
            tri = dcur + (dr - 1) * irun  # new triangles at this d
        else:  # cs[i]="i":
            if prevsym == "d":  # new string of i's
                dcur += (dr - 1) * irun  # accumulate shared shortest paths
                irun = 0  # reset i run counter
                dr -= drun  # reduce number of d's to right
                drun = 0  # reset d run counter
            irun += 1
            tri = dr * (dr - 1) // 2  # new triangles at this i
        seq.append(tri)
        prevsym = sym
    return seq


def cluster_sequence(creation_sequence):
    """
    Return cluster sequence for the given threshold graph creation sequence.
    """
    triseq = triangle_sequence(creation_sequence)
    degseq = degree_sequence(creation_sequence)
    cseq = []
    for i, deg in enumerate(degseq):
        tri = triseq[i]
        if deg <= 1:  # isolated vertex or single pair gets cc 0
            cseq.append(0)
            continue
        max_size = (deg * (deg - 1)) // 2
        cseq.append(tri / max_size)
    return cseq


def degree_sequence(creation_sequence):
    """
    Return degree sequence for the threshold graph with the given
    creation sequence
    """
    cs = creation_sequence  # alias
    seq = []
    rd = cs.count("d")  # number of d to the right
    for i, sym in enumerate(cs):
        if sym == "d":
            rd -= 1
            seq.append(rd + i)
        else:
            seq.append(rd)
    return seq


def density(creation_sequence):
    """
    Return the density of the graph with this creation_sequence.
    The density is the fraction of possible edges present.
    """
    N = len(creation_sequence)
    two_size = sum(degree_sequence(creation_sequence))
    two_possible = N * (N - 1)
    den = two_size / two_possible
    return den


def degree_correlation(creation_sequence):
    """
    Return the degree-degree correlation over all edges.
    """
    cs = creation_sequence
    s1 = 0  # deg_i*deg_j
    s2 = 0  # deg_i^2+deg_j^2
    s3 = 0  # deg_i+deg_j
    m = 0  # number of edges
    rd = cs.count("d")  # number of d nodes to the right
    rdi = [i for i, sym in enumerate(cs) if sym == "d"]  # index of "d"s
    ds = degree_sequence(cs)
    for i, sym in enumerate(cs):
        if sym == "d":
            if i != rdi[0]:
                print("Logic error in degree_correlation", i, rdi)
                raise ValueError
            rdi.pop(0)
        degi = ds[i]
        for dj in rdi:
            degj = ds[dj]
            s1 += degj * degi
            s2 += degi**2 + degj**2
            s3 += degi + degj
            m += 1
    denom = 2 * m * s2 - s3 * s3
    numer = 4 * m * s1 - s3 * s3
    if denom == 0:
        if numer == 0:
            return 1
        raise ValueError(f"Zero Denominator but Numerator is {numer}")
    return numer / denom


def shortest_path(creation_sequence, u, v):
    """
    Find the shortest path between u and v in a
    threshold graph G with the given creation_sequence.

    For an unlabeled creation_sequence, the vertices
    u and v must be integers in (0,len(sequence)) referring
    to the position of the desired vertices in the sequence.

    For a labeled creation_sequence, u and v are labels of vertices.

    Use cs=creation_sequence(degree_sequence,with_labels=True)
    to convert a degree sequence to a creation sequence.

    Returns a list of vertices from u to v.
    Example: if they are neighbors, it returns [u,v]
    """
    # Turn input sequence into a labeled creation sequence
    first = creation_sequence[0]
    if isinstance(first, str):  # creation sequence
        cs = [(i, creation_sequence[i]) for i in range(len(creation_sequence))]
    elif isinstance(first, tuple):  # labeled creation sequence
        cs = creation_sequence[:]
    elif isinstance(first, int):  # compact creation sequence
        ci = uncompact(creation_sequence)
        cs = [(i, ci[i]) for i in range(len(ci))]
    else:
        raise TypeError("Not a valid creation sequence type")

    verts = [s[0] for s in cs]
    if v not in verts:
        raise ValueError(f"Vertex {v} not in graph from creation_sequence")
    if u not in verts:
        raise ValueError(f"Vertex {u} not in graph from creation_sequence")
    # Done checking
    if u == v:
        return [u]

    uindex = verts.index(u)
    vindex = verts.index(v)
    bigind = max(uindex, vindex)
    if cs[bigind][1] == "d":
        return [u, v]
    # must be that cs[bigind][1]=='i'
    cs = cs[bigind:]
    while cs:
        vert = cs.pop()
        if vert[1] == "d":
            return [u, vert[0], v]
    # All after u are type 'i' so no connection
    return -1


def shortest_path_length(creation_sequence, i):
    """
    Return the shortest path length from indicated node to
    every other node for the threshold graph with the given
    creation sequence.
    Node is indicated by index i in creation_sequence unless
    creation_sequence is labeled in which case, i is taken to
    be the label of the node.

    Paths lengths in threshold graphs are at most 2.
    Length to unreachable nodes is set to -1.
    """
    # Turn input sequence into a labeled creation sequence
    first = creation_sequence[0]
    if isinstance(first, str):  # creation sequence
        if isinstance(creation_sequence, list):
            cs = creation_sequence[:]
        else:
            cs = list(creation_sequence)
    elif isinstance(first, tuple):  # labeled creation sequence
        cs = [v[1] for v in creation_sequence]
        i = [v[0] for v in creation_sequence].index(i)
    elif isinstance(first, int):  # compact creation sequence
        cs = uncompact(creation_sequence)
    else:
        raise TypeError("Not a valid creation sequence type")

    # Compute
    N = len(cs)
    spl = [2] * N  # length 2 to every node
    spl[i] = 0  # except self which is 0
    # 1 for all d's to the right
    for j in range(i + 1, N):
        if cs[j] == "d":
            spl[j] = 1
    if cs[i] == "d":  # 1 for all nodes to the left
        for j in range(i):
            spl[j] = 1
    # and -1 for any trailing i to indicate unreachable
    for j in range(N - 1, 0, -1):
        if cs[j] == "d":
            break
        spl[j] = -1
    return spl


def betweenness_sequence(creation_sequence, normalized=True):
    """
    Return betweenness for the threshold graph with the given creation
    sequence.  The result is unscaled.  To scale the values
    to the interval [0,1] divide by (n-1)*(n-2).
    """
    cs = creation_sequence
    seq = []  # betweenness
    lastchar = "d"  # first node is always a 'd'
    dr = float(cs.count("d"))  # number of d's to the right of current pos
    irun = 0  # number of i's in the last run
    drun = 0  # number of d's in the last run
    dlast = 0.0  # betweenness of last d
    for i, c in enumerate(cs):
        if c == "d":  # cs[i]=="d":
            # betweenness = amt shared with earlier d's and i's
            #             + new isolated nodes covered
            #             + new paths to all previous nodes
            b = dlast + (irun - 1) * irun / dr + 2 * irun * (i - drun - irun) / dr
            drun += 1  # update counter
        else:  # cs[i]="i":
            if lastchar == "d":  # if this is a new run of i's
                dlast = b  # accumulate betweenness
                dr -= drun  # update number of d's to the right
                drun = 0  # reset d counter
                irun = 0  # reset i counter
            b = 0  # isolated nodes have zero betweenness
            irun += 1  # add another i to the run
        seq.append(float(b))
        lastchar = c

    # normalize by the number of possible shortest paths
    if normalized:
        order = len(cs)
        scale = 1.0 / ((order - 1) * (order - 2))
        seq = [s * scale for s in seq]

    return seq


def eigenvectors(creation_sequence):
    """
    Return a 2-tuple of Laplacian eigenvalues and eigenvectors
    for the threshold network with creation_sequence.
    The first value is a list of eigenvalues.
    The second value is a list of eigenvectors.
    The lists are in the same order so corresponding eigenvectors
    and eigenvalues are in the same position in the two lists.

    Notice that the order of the eigenvalues returned by eigenvalues(cs)
    may not correspond to the order of these eigenvectors.
    """
    ccs = make_compact(creation_sequence)
    N = sum(ccs)
    vec = [0] * N
    val = vec[:]
    # get number of type d nodes to the right (all for first node)
    dr = sum(ccs[::2])

    nn = ccs[0]
    vec[0] = [1.0 / sqrt(N)] * N
    val[0] = 0
    e = dr
    dr -= nn
    type_d = True
    i = 1
    dd = 1
    while dd < nn:
        scale = 1.0 / sqrt(dd * dd + i)
        vec[i] = i * [-scale] + [dd * scale] + [0] * (N - i - 1)
        val[i] = e
        i += 1
        dd += 1
    if len(ccs) == 1:
        return (val, vec)
    for nn in ccs[1:]:
        scale = 1.0 / sqrt(nn * i * (i + nn))
        vec[i] = i * [-nn * scale] + nn * [i * scale] + [0] * (N - i - nn)
        # find eigenvalue
        type_d = not type_d
        if type_d:
            e = i + dr
            dr -= nn
        else:
            e = dr
        val[i] = e
        st = i
        i += 1
        dd = 1
        while dd < nn:
            scale = 1.0 / sqrt(i - st + dd * dd)
            vec[i] = [0] * st + (i - st) * [-scale] + [dd * scale] + [0] * (N - i - 1)
            val[i] = e
            i += 1
            dd += 1
    return (val, vec)


def spectral_projection(u, eigenpairs):
    """
    Returns the coefficients of each eigenvector
    in a projection of the vector u onto the normalized
    eigenvectors which are contained in eigenpairs.

    eigenpairs should be a list of two objects.  The
    first is a list of eigenvalues and the second a list
    of eigenvectors.  The eigenvectors should be lists.

    There's not a lot of error checking on lengths of
    arrays, etc. so be careful.
    """
    coeff = []
    evect = eigenpairs[1]
    for ev in evect:
        c = sum(evv * uv for (evv, uv) in zip(ev, u))
        coeff.append(c)
    return coeff


def eigenvalues(creation_sequence):
    """
    Return sequence of eigenvalues of the Laplacian of the threshold
    graph for the given creation_sequence.

    Based on the Ferrer's diagram method.  The spectrum is integral
    and is the conjugate of the degree sequence.

    See::

      @Article{degree-merris-1994,
       author = {Russel Merris},
       title = {Degree maximal graphs are Laplacian integral},
       journal = {Linear Algebra Appl.},
       year = {1994},
       volume = {199},
       pages = {381--389},
      }

    """
    degseq = degree_sequence(creation_sequence)
    degseq.sort()
    eiglist = []  # zero is always one eigenvalue
    eig = 0
    row = len(degseq)
    bigdeg = degseq.pop()
    while row:
        if bigdeg < row:
            eiglist.append(eig)
            row -= 1
        else:
            eig += 1
            if degseq:
                bigdeg = degseq.pop()
            else:
                bigdeg = 0
    return eiglist


# Threshold graph creation routines


@py_random_state(2)
def random_threshold_sequence(n, p, seed=None):
    """
    Create a random threshold sequence of size n.
    A creation sequence is built by randomly choosing d's with
    probability p and i's with probability 1-p.

    s=nx.random_threshold_sequence(10,0.5)

    returns a threshold sequence of length 10 with equal
    probably of an i or a d at each position.

    A "random" threshold graph can be built with

    G=nx.threshold_graph(s)

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.
    """
    if not (0 <= p <= 1):
        raise ValueError("p must be in [0,1]")

    cs = ["d"]  # threshold sequences always start with a d
    for i in range(1, n):
        if seed.random() < p:
            cs.append("d")
        else:
            cs.append("i")
    return cs


# maybe *_d_threshold_sequence routines should
# be (or be called from) a single routine with a more descriptive name
# and a keyword parameter?
def right_d_threshold_sequence(n, m):
    """
    Create a skewed threshold graph with a given number
    of vertices (n) and a given number of edges (m).

    The routine returns an unlabeled creation sequence
    for the threshold graph.

    FIXME: describe algorithm

    """
    cs = ["d"] + ["i"] * (n - 1)  # create sequence with n insolated nodes

    #  m <n : not enough edges, make disconnected
    if m < n:
        cs[m] = "d"
        return cs

    # too many edges
    if m > n * (n - 1) / 2:
        raise ValueError("Too many edges for this many nodes.")

    # connected case m >n-1
    ind = n - 1
    sum = n - 1
    while sum < m:
        cs[ind] = "d"
        ind -= 1
        sum += ind
    ind = m - (sum - ind)
    cs[ind] = "d"
    return cs


def left_d_threshold_sequence(n, m):
    """
    Create a skewed threshold graph with a given number
    of vertices (n) and a given number of edges (m).

    The routine returns an unlabeled creation sequence
    for the threshold graph.

    FIXME: describe algorithm

    """
    cs = ["d"] + ["i"] * (n - 1)  # create sequence with n insolated nodes

    #  m <n : not enough edges, make disconnected
    if m < n:
        cs[m] = "d"
        return cs

    # too many edges
    if m > n * (n - 1) / 2:
        raise ValueError("Too many edges for this many nodes.")

    # Connected case when M>N-1
    cs[n - 1] = "d"
    sum = n - 1
    ind = 1
    while sum < m:
        cs[ind] = "d"
        sum += ind
        ind += 1
    if sum > m:  # be sure not to change the first vertex
        cs[sum - m] = "i"
    return cs


@py_random_state(3)
def swap_d(cs, p_split=1.0, p_combine=1.0, seed=None):
    """
    Perform a "swap" operation on a threshold sequence.

    The swap preserves the number of nodes and edges
    in the graph for the given sequence.
    The resulting sequence is still a threshold sequence.

    Perform one split and one combine operation on the
    'd's of a creation sequence for a threshold graph.
    This operation maintains the number of nodes and edges
    in the graph, but shifts the edges from node to node
    maintaining the threshold quality of the graph.

    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.
    """
    # preprocess the creation sequence
    dlist = [i for (i, node_type) in enumerate(cs[1:-1]) if node_type == "d"]
    # split
    if seed.random() < p_split:
        choice = seed.choice(dlist)
        split_to = seed.choice(range(choice))
        flip_side = choice - split_to
        if split_to != flip_side and cs[split_to] == "i" and cs[flip_side] == "i":
            cs[choice] = "i"
            cs[split_to] = "d"
            cs[flip_side] = "d"
            dlist.remove(choice)
            # don't add or combine may reverse this action
            # dlist.extend([split_to,flip_side])
    #            print >>sys.stderr,"split at %s to %s and %s"%(choice,split_to,flip_side)
    # combine
    if seed.random() < p_combine and dlist:
        first_choice = seed.choice(dlist)
        second_choice = seed.choice(dlist)
        target = first_choice + second_choice
        if target >= len(cs) or cs[target] == "d" or first_choice == second_choice:
            return cs
        # OK to combine
        cs[first_choice] = "i"
        cs[second_choice] = "i"
        cs[target] = "d"
    #        print >>sys.stderr,"combine %s and %s to make %s."%(first_choice,second_choice,target)

    return cs
