# Pairing graphify with session memory

graphify answers one half of what an agent needs to know about a project: what the code is. Structure, relationships, communities, god nodes. It is deterministic AST analysis, so it deliberately stores nothing about what happened while you worked.

The other half is temporal: why a change was made, what was decided or tried in past sessions, which bug was fixed where and how. That belongs to a session memory layer. [agentmemory](https://github.com/rohitg00/agentmemory) is one such layer: it captures observations from agent sessions via lifecycle hooks and MCP, and recalls them across sessions.

Run both and your agent can answer both kinds of question:

| Question | Answered by |
|---|---|
| "How does auth connect to the middleware?" | graphify (`query_graph`, `shortest_path`) |
| "What does this module depend on?" | graphify (`get_neighbors`) |
| "Why was this retry added?" | session memory (`memory_recall`) |
| "What did we decide about the cache last week?" | session memory (`memory_recall`) |
| "What changed in this area recently, and why?" | both: structure from graphify, history from memory |

## Running both MCP servers

Register the two servers side by side. Example for a `mcpServers`-style client config:

```json
{
  "mcpServers": {
    "graphify": {
      "command": "python",
      "args": ["-m", "graphify.serve", "graphify-out/graph.json"]
    },
    "agentmemory": {
      "command": "npx",
      "args": ["-y", "@agentmemory/mcp"]
    }
  }
}
```

agentmemory also has its own installer (`npx agentmemory connect <agent>`) that wires the same config plus agent lifecycle hooks where the agent supports them.

## What graphify does when it gets a temporal question

`query_graph` and `graphify query` detect clearly temporal questions ("why was this added", "what changed last week", "who introduced this") and append a one-line note saying the graph stores no session history and that a session memory layer answers those, so the agent hands off instead of retrying the graph. The detection is a deterministic regex; structural questions never trigger it.

The always-on instruction files that `graphify install` writes carry the same split, so agents route structure questions to the graph and history questions to memory tools without being asked.

## Experiential god-node weighting (optional)

Structural degree says what the code is wired to, not what the developer actually works on. A file with 50 imports is a structural hub; a file debugged across three sessions is an experiential one. With a memory layer running, graphify can blend the two:

```bash
GRAPHIFY_SESSION_WEIGHTS=1 graphify update .
```

The report's god-node ranking then weighs each node by `degree * (1 + ln(1 + observations))` using per-file session history from the memory layer, and annotates worked-on nodes with their session and observation counts. Strictly opt-in: without the variable graphify makes no network calls, and if the memory server is unreachable the report falls back to pure structural ranking.

The reverse direction also works: agentmemory imports `graphify-out/graph.json` into its own knowledge graph (`POST /agentmemory/graph/import-graphify`), carrying the EXTRACTED/INFERRED confidence tags over as edge weights, so memory recall sees codebase structure the developer never touched in a session.

## Division of labor

- graphify: deterministic, rebuildable from source at any time, no record of sessions. Safe to delete and regenerate.
- Session memory: append-only observations of real work. Not derivable from source, so it is the part worth backing up.

Keep using `graphify update .` after edits as usual. The pairing changes nothing about how the graph is built.
