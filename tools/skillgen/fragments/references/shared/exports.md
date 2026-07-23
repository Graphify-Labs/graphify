# graphify reference: extra exports and benchmark

Every exporter opens an immutable native generation. No intermediate graph file is produced.

### Step 6b - Wiki (only if --wiki flag)

```bash
graphify export wiki graphify-out/graph.helix --out graphify-out/wiki
```

### Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag)

```bash
graphify export neo4j graphify-out/graph.helix --out graphify-out/cypher.txt
```

### Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag)

```bash
graphify export falkordb graphify-out/graph.helix --out graphify-out/cypher.txt
```

### Step 7b - SVG export (only if --svg flag)

```bash
graphify export svg graphify-out/graph.helix --out graphify-out/graph.svg
```

### Step 7c - GraphML export (only if --graphml flag)

```bash
graphify export graphml graphify-out/graph.helix --out graphify-out/graph.graphml
```

### Step 7d - MCP server (only if --mcp flag)

```bash
python3 -m graphify.serve graphify-out/graph.helix
python3 -m graphify.serve graphify-out/graph.helix --transport http --port 8080
```

### Step 8 - Token reduction benchmark (only if total_words > 5000)

```bash
graphify benchmark --graph graphify-out/graph.helix
```

Report generation, open, query, traversal, clustering, centrality, export, disk, RSS, and concurrent-reader measurements when running qualification benchmarks.
