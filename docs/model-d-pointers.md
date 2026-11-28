# Optional Model D pointers over MCP

Graphify can accept externally selected source locations as starting points for
its existing structural traversal. This is an opt-in bridge for Model D and
other external rankers; it does not embed a routing model in Graphify.

## Enable the interface

Set the environment variable on the process that starts the local Graphify MCP
server:

```bash
GRAPHIFY_MODEL_D_POINTERS=1 graphify-mcp graphify-out/graph.json
```

The default is off. When disabled, `query_graph` does not advertise the
`model_d_pointers` input and rejects requests that attempt to use it.

## Send pointers

When enabled, add `model_d_pointers` to a normal `query_graph` request:

```json
{
  "question": "Where is request validation handled?",
  "model_d_pointers": [
    {"path": "src/api/validation.py", "line": 84},
    {"path": "src/api/routes.py", "line": 31}
  ],
  "depth": 2,
  "token_budget": 2000
}
```

Each entry contains:
- `path`: a repository-relative or absolute source-file path.
- `line`: a one-based line number supplied by the external ranker.

The interface accepts 1–32 locations. Paths are limited to 1,024 characters;
line numbers must be positive integers. Duplicate path/line pairs are removed.

Graphify resolves each path against the selected graph's project root and uses
it as an explicit starting seed for the existing query traversal. The supplied
line is preserved in the response as a location hint. The current graph schema
does not model arbitrary source lines as independent nodes, so the line number
does not change the graph seed within a file. The agent should still inspect the
current source at the indicated line before drawing conclusions.

## Boundaries

- Graphify receives pointers; it does not run Model D or implement its routing
  law.
- Pointers are retrieval hints, not answers. Graphify still returns the current
  structural neighborhood, and the agent must read current source.
- No answer text or pointer history is persisted by this interface.
- If a path cannot be resolved, Graphify's existing explicit-seed behavior
  reports it rather than guessing another location.
- Omitting `model_d_pointers` preserves the existing `query_graph` behavior.

The feature flag is intended for local MCP deployments and controlled pilots.
