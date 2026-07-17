*** Begin Patch
*** Update File: graphify/serve.py
@@
 def _find_node(G: nx.Graph, label: str) -> list[str]:
@@
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
+
*** End Patch