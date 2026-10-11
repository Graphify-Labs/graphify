# graphify reference: GitHub clone and cross-repo merge

Load this when the user passed one or more `https://github.com/...` URLs, or named several local subfolders to merge into one graph.

### Step 0 - Clone GitHub repo(s) (only if a GitHub URL was given)

**Single repo:**
```bash
LOCAL_PATH="$HOME/graphify repos/repo"
graphify clone "https://github.com/owner/repo" --out "$LOCAL_PATH" &&
  graphify extract "$LOCAL_PATH"
# Add --branch "branch-name" to the clone command when needed.
```

**Multiple repos (cross-repo graph):**
```bash
REPO1_PATH="$HOME/graphify repos/repo1"
REPO2_PATH="$HOME/graphify repos/repo2"
# Build at each clone root; graphify extract writes graphify-out/ inside its target.
# For semantic files, configure a supported backend/API key or pass --backend <provider>.
# Use --code-only only when you intend to skip semantic extraction.
# The chain stops if cloning or extracting either repository fails.
graphify clone "https://github.com/owner/repo1" --out "$REPO1_PATH" &&
  graphify clone "https://github.com/owner/repo2" --out "$REPO2_PATH" &&
  graphify extract "$REPO1_PATH" &&
  graphify extract "$REPO2_PATH" &&
  graphify merge-graphs \
    "$REPO1_PATH/graphify-out/graph.json" \
    "$REPO2_PATH/graphify-out/graph.json" \
    --out graphify-out/cross-repo-graph.json
```

Graphify clones into `~/.graphify/repos/<owner>/<repo>` and reuses existing clones on repeat runs. Each node in the merged graph carries a `repo` attribute so you can filter by origin.

**Multiple local subfolders (monorepo or multi-service layout):**

The skill pipeline writes all intermediate and final outputs to `graphify-out/` in the current working directory. Running the skill on each subfolder separately will clobber the same output dir. Instead, use the CLI directly for each subfolder — it places `graphify-out/` *inside* the scanned path:

```bash
graphify extract ./core/     # → ./core/graphify-out/graph.json
graphify extract ./service/  # → ./service/graphify-out/graph.json
graphify extract ./platform/ # → ./platform/graphify-out/graph.json
# Add --backend gemini|kimi|openai|deepseek|claude-cli depending on which API key you have set

# Then merge at the project root:
graphify merge-graphs \
  ./core/graphify-out/graph.json \
  ./service/graphify-out/graph.json \
  ./platform/graphify-out/graph.json \
  --out graphify-out/graph.json
```

Once `graphify-out/graph.json` exists, the fast path above takes over: any codebase question runs `graphify query` directly on the merged graph — no re-extraction, no size gate.
