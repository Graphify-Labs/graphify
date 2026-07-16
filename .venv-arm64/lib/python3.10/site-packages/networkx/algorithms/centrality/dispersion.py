from itertools import combinations

import networkx as nx

__all__ = ["dispersion"]


@nx._dispatchable
def dispersion(G, u=None, v=None, normalized=True, alpha=1.0, b=0.0, c=0.0):
    r"""Calculate dispersion between `u` and `v` in `G`.

    A link between two actors (`u` and `v`) has a high dispersion when their
    mutual ties (`s` and `t`) are not well connected with each other.

    Parameters
    ----------
    G : graph
        A NetworkX graph.
    u : node, optional
        The source for the dispersion score (e.g. ego node of the network).
    v : node, optional
        The target of the dispersion score if specified.
    normalized : bool
        If True (default) normalize by the embeddedness of the nodes (u and v).
    alpha, b, c : float
        Parameters for the normalization procedure. When `normalized` is True,
        the dispersion value is normalized by::

            result = ((dispersion + b) ** alpha) / (embeddedness + c)

        as long as the denominator is nonzero.

    Returns
    -------
    nodes : dictionary
        If u (v) is specified, returns a dictionary of nodes with dispersion
        score for all "target" ("source") nodes. If neither u nor v is
        specified, returns a dictionary of dictionaries for all nodes 'u' in the
        graph with a dispersion score for each node 'v'.

    Notes
    -----
    This implementation follows Lars Backstrom and Jon Kleinberg [1]_. Typical
    usage would be to run dispersion on the ego network $G_u$ if $u$ were
    specified.  Running :func:`dispersion` with neither $u$ nor $v$ specified
    can take some time to complete.

    References
    ----------
    .. [1] Romantic Partnerships and the Dispersion of Social Ties:
        A Network Analysis of Relationship Status on Facebook.
        Lars Backstrom, Jon Kleinberg.
        https://arxiv.org/pdf/1310.6753v1.pdf

    """

    def _dispersion(G_u, u, v):
        """dispersion for all nodes 'v' in a ego network G_u of node 'u'"""
        u_nbrs = set(G_u[u])
        ST = {n for n in G_u[v] if n in u_nbrs}
        set_uv = {u, v}
        # all possible ties of connections that u and b share
        possib = combinations(ST, 2)
        total = 0
        for s, t in possib:
            # neighbors of s that are in G_u, not including u and v
            nbrs_s = u_nbrs.intersection(G_u[s]) - set_uv
            # s and t are not directly connected
            if t not in nbrs_s:
                # s and t do not share a connection
                if nbrs_s.isdisjoint(G_u[t]):
                    # tick for disp(u, v)
                    total += 1
        # neighbors that u and v share
        embeddedness = len(ST)

        dispersion_val = total
        if normalized:
            dispersion_val = (total + b) ** alpha
            if embeddedness + c != 0:
                dispersion_val /= embeddedness + c

        return dispersion_val

    if u is None:
        # v and u are not specified
        if v is None:
            results = {n: {} for n in G}
            for u in G:
                for v in G[u]:
                    results[u][v] = _dispersion(G, u, v)
        # u is not specified, but v is
        else:
            results = dict.fromkeys(G[v], {})
            for u in G[v]:
                results[u] = _dispersion(G, v, u)
    else:
        # u is specified with no target v
        if v is None:
            results = dict.fromkeys(G[u], {})
            for v in G[u]:
                results[v] = _dispersion(G, u, v)
        # both u and v are specified
        else:
            results = _dispersion(G, u, v)

    return results
