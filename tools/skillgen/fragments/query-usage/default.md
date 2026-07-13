/graphify query "<question-argv>"                     # pass the question as one data argument; never interpolate shell text
/graphify query "<question-argv>" --dfs               # trace a specific chain with staged retrieval
/graphify query "<question-argv>" --budget 1500       # bound deterministic traversal and final output
/graphify query 'community:"Main Runtime" target flow' # scope to a named community (quote spaces)
/graphify query 'god:"Auth Gateway" request flow'      # scope to a named god node
/graphify query "include:memory prior decision"        # explicitly include saved Q&A in retrieval
/graphify path "src/auth.py::AuthModule" "Database"   # qualify an ambiguous label with its source file
/graphify explain "src/model.py::SwinTransformer"      # explain one source-qualified node
