"""Apache AGE as an alternative retrieval backend for `graphify query`,
`path`, and `explain` (docs/AGE_PLAN.md Phase 6, optional/lower-priority
now that review/quality agents query AGE directly): fetch a whole graph
from a live AGE instance into NetworkX, then hand it to the exact same
scoring/formatting code the file backend uses. Cypher never reimplements
scoring -- this module's only job is producing an nx.Graph shaped like
build()'s output, so behavior downstream is identical regardless of
where the graph came from.

Fetches the *entire* named graph rather than a server-side-filtered
candidate subgraph, deliberately: scoring/formatting already assumes an
in-memory NetworkX graph (BFS/DFS with a token budget), so filtering
would mean either reimplementing that logic in Cypher (explicitly out of
scope) or fetching the candidates first anyway. Same cost profile as
loading a large graph.json today.
"""
from __future__ import annotations

import json

import networkx as nx


def parse_agtype_objects(raw: str) -> list[tuple[dict, str | None]]:
    """docs/AGE_SCHEMA.md's pinned parser: AGE returns a vertex/edge/path
    as ``{...}::vertex`` / ``{...}::edge`` / ``[...]::path`` text, not
    plain JSON -- ``json.loads`` and a naive regex both fail on the
    nested ``"properties"`` object. Depth-aware splitting handles it.

    Returns ``[(parsed_object, 'vertex' | 'edge' | None), ...]`` in the
    order objects appear in ``raw``.

    The brace scanner is string-aware: a ``{`` or ``}`` inside a JSON
    string value (e.g. a ``label`` property holding ``{ "intra": ... }``
    or a JS template literal ``${x}``) must not move the nesting depth,
    or the top-level object boundaries are misdetected and the parse
    collapses to nothing.
    """
    results: list[tuple[dict, str | None]] = []
    depth, start = 0, None
    in_str, escaped = False, False
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if in_str:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start is not None:
                obj = json.loads(raw[start:i + 1])
                j = i + 1
                kind = None
                if raw[j:j + 2] == "::":
                    k = j + 2
                    while k < n and raw[k].isalpha():
                        k += 1
                    kind = raw[j + 2:k]
                results.append((obj, kind))
                start = None
        i += 1
    return results


def _agtype_scalar(raw):
    return json.loads(raw) if isinstance(raw, str) else raw


def fetch_graph_from_age(conninfo: str, graph_name: str) -> nx.MultiGraph:
    """Fetch an AGE graph into an ``nx.MultiGraph``: every node's full
    property set as attrs (whatever ``push_to_age()`` actually wrote --
    lean or full, whichever was pushed), every edge stamped with
    ``_src``/``_tgt`` (an undirected ``nx.Graph`` loses direction
    otherwise -- see the same idiom in ``graphify/build.py``,
    ``graphify/analyze.py``, ``graphify/exporters/graphdb.py``) plus its
    own scalar properties.

    A MultiGraph so a genuine parallel edge between the same pair (two
    different relation types) is never silently dropped -- callers that
    want a plain ``Graph`` (matching `query`'s file-backend loading,
    which already collapses same-pair duplicates) can convert via
    ``nx.Graph(fetched)``; callers that need parallel edges preserved
    (`path`/`explain`, via ``graphify.build.edge_data``/``edge_datas``,
    which already tolerate both graph types) can use it directly.

    Requires: pip install "graphifyy[age]" (psycopg[binary]).
    """
    try:
        import psycopg
        from psycopg import sql
    except ImportError as e:
        raise ImportError(
            'psycopg not installed. Run: pip install "graphifyy[age]"'
        ) from e

    G = nx.MultiGraph()
    conn = psycopg.connect(conninfo)
    try:
        with conn.cursor() as cur:
            cur.execute("LOAD 'age';")
            cur.execute('SET search_path = ag_catalog, "$user", public;')

            cur.execute(
                sql.SQL(
                    "SELECT * FROM cypher({graph}, $$ MATCH (n) RETURN n $$) AS (n agtype);"
                ).format(graph=sql.Literal(graph_name))
            )
            for (raw,) in cur.fetchall():
                text = raw if isinstance(raw, str) else json.dumps(raw)
                (vertex, _kind), = parse_agtype_objects(text)
                props = dict(vertex.get("properties", {}))
                node_id = props.pop("id", None)
                if node_id is None:
                    continue
                G.add_node(node_id, **props)

            cur.execute(
                sql.SQL(
                    "SELECT * FROM cypher({graph}, $$ "
                    "  MATCH (a)-[r]->(b) RETURN a.id, r, b.id "
                    "$$) AS (src agtype, r agtype, tgt agtype);"
                ).format(graph=sql.Literal(graph_name))
            )
            for src_raw, r_raw, tgt_raw in cur.fetchall():
                src_id = _agtype_scalar(src_raw)
                tgt_id = _agtype_scalar(tgt_raw)
                r_text = r_raw if isinstance(r_raw, str) else json.dumps(r_raw)
                (edge_obj, _kind), = parse_agtype_objects(r_text)
                props = dict(edge_obj.get("properties", {}))
                props["_src"] = src_id
                props["_tgt"] = tgt_id
                G.add_edge(src_id, tgt_id, **props)
    finally:
        conn.close()
    return G
