def _find_node(G: nx.Graph, label: str) -> list[str]:
    """Return node IDs whose label or ID matches the search term (diacritic-insensitive).

    Results are ordered by precedence: exact source-file path match first, then
    exact (label/ID) match, then prefix match, then substring match. Node-ID exact
    matches are grouped with label exact matches.
    """
    term = " ".join(_search_tokens(label))
    if not term:
        return []

    # Punctuation-preserving normalized query.
    norm_query = _strip_diacritics(str(label)).lower().strip()

    source_exact: list[str] = []
    exact: list[str] = []
    prefix: list[str] = []
    substring: list[str] = []

    # Trigram prefilter (graph-iteration order preserved so exact/prefix/substring
    # ordering — and thus matches[0] — is byte-identical to the full scan).
    candidate_ids = _trigram_candidates(G, [term, norm_query])
    node_iter = (
        G.nodes(data=True) if candidate_ids is None
        else ((nid, G.nodes[nid]) for nid in candidate_ids)
    )

    for nid, d in node_iter:
        norm_label = d.get("norm_label") or _strip_diacritics(d.get("label") or "").lower()
        bare_label = norm_label.rstrip("()")
        label_tokens = " ".join(_search_tokens(d.get("label") or ""))
        source_tokens = " ".join(_search_tokens(d.get("source_file") or ""))
        nid_lower = nid.lower()

        if term == source_tokens:
            source_exact.append(nid)
        elif (
            term == norm_label
            or term == bare_label
            or term == label_tokens
            or term == nid_lower
            or norm_query == norm_label
            or norm_query == bare_label
        ):
            exact.append(nid)
        elif (
            norm_label.startswith(term)
            or bare_label.startswith(term)
            or label_tokens.startswith(term)
            or nid_lower.startswith(term)
            or norm_label.startswith(norm_query)
            or bare_label.startswith(norm_query)
        ):
            prefix.append(nid)
        elif (
            term in norm_label
            or term in label_tokens
            or norm_query in norm_label
        ):
            substring.append(nid)

    # Patch: prioritize a single source-located node that matches filename
    if source_exact:
        query_basename = _strip_diacritics(Path(label).name).lower()
        preferred = [
            nid
            for nid in source_exact
            if str(G.nodes[nid].get("source_location", "")) == "L1"
            and _strip_diacritics(str(G.nodes[nid].get("label") or "")).lower()
            == query_basename
        ]
        if len(preferred) == 1:
            source_exact = preferred + [nid for nid in source_exact if nid != preferred[0]]

    return source_exact + exact + prefix + substring