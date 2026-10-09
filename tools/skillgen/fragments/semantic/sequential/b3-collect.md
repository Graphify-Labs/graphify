Once every chunk has been extracted, check each chunk file:
- Check that `graphify-out/.graphify_chunk_NN.json` exists on disk — this is the success signal
- If the file exists and contains valid JSON with `nodes` and `edges`, include it and save to cache
- If the file is missing, that chunk was never written — print a warning: "chunk N missing from disk — re-extract it before merging." Do not silently skip.
- If a chunk file holds invalid JSON, print a warning and rename it to `graphify-out/.graphify_chunk_NN.json.invalid` (kept for inspection) so the merge below skips that chunk - do not abort

If more than half the chunks failed or are missing, stop and tell the user to re-run the semantic extraction.

Merge all chunk files into `.graphify_semantic_new.json`. In-session extraction reports no per-chunk token counts, so each chunk JSON keeps its placeholder zeros. Then run:
