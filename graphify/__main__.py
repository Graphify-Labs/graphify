*** Begin Patch
*** Update File: graphify/__main__.py
@@
-        from graphify.serve import _find_node
+        from graphify.serve import _find_node, _score_nodes
@@
-        matches = _find_node(G, label)
-        if not matches:
-            print(f"No node matching '{label}' found.")
-            sys.exit(0)
-        nid = matches[0]
+        # Prefer an exact node-id match (explicit deterministic bypass of fuzzy
+        # resolution). This mirrors the user's workaround: passing an exact node
+        # id should always resolve deterministically to that node.
+        if label in G:
+            nid = label
+        else:
+            # Use the same scorer as `path` for consistent resolution across CLI
+            # commands. `_score_nodes` returns a sorted list (score, node_id).
+            scored = _score_nodes(G, [t.lower() for t in label.split()])
+            if not scored:
+                print(f"No node matching '{label}' found.")
+                sys.exit(0)
+            # Ambiguity detection: if multiple nodes share the top score, list
+            # them instead of silently choosing one. This prevents explain from
+            # returning an apparently authoritative explanation that was actually
+            # a coin-flip among tied candidates (issue #1969).
+            top_score = scored[0][0]
+            top_matches = [s for s in scored if abs(s[0] - top_score) < 1e-12]
+            if len(top_matches) > 1:
+                print(
+                    f"'{label}' is ambiguous: {len(top_matches)} nodes matched with tied score {top_score}. Use a more specific label or the exact node ID.",
+                    file=sys.stderr,
+                )
+                for score, mid in top_matches[:20]:
+                    d = G.nodes[mid]
+                    print(
+                        f"  {mid}: {d.get('label','')} ({d.get('source_file','')}) degree={G.degree(mid)}",
+                        file=sys.stderr,
+                    )
+                # Exit non-zero so calling scripts know the result was ambiguous.
+                sys.exit(2)
+            nid = scored[0][1]
*** End Patch
