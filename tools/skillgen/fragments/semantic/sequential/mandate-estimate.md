**Extract the chunks yourself, sequentially, in this session.** Take one chunk at a time: read its files, apply the extraction prompt, and write that chunk's JSON file before starting the next chunk.

Before extracting, print a timing estimate:
- Load `total_words` and file counts from `graphify-out/.graphify_detect.json`
- Estimate chunks needed: `ceil(uncached_non_code_files / 22)` (chunk size is 20-25)
- Estimate time: ~45s per chunk (chunks run one after another, so total ≈ 45s × chunks)
- Print: "Semantic extraction: ~N files → X chunks, estimated ~Ys"
