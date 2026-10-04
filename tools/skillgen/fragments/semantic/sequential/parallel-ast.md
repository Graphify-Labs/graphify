**Run Part A (AST) first, then Part B (semantic).** AST extraction is a single shell command; start it before you begin extracting semantic chunks. Merge results in Part C as before.

Note: AST is deterministic, fast, and needs no LLM, so it never waits on the semantic chunks; running it first keeps the chunk-by-chunk semantic work as the only long step.
