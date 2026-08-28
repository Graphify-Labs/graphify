---
name: graphify
description: "Use for codebase and architecture questions when graphify-out/ exists, and for building or updating a Graphify knowledge graph from a project."
---

# Graphify for AdaL

Use Graphify as the project map before broad raw-file exploration.

## Existing graph: query first

If `graphify-out/graph.json` exists and the user asks how the project works,
start with the smallest relevant command:

```bash
graphify query "<question>"
graphify explain "<concept>"
graphify path "<source>" "<target>"
```

Use raw search and file reads after the graph has identified the relevant
components, or when exact source lines are needed for implementation or
debugging. Use `GRAPH_REPORT.md` only for broad architecture review.

## Build a graph

If Graphify is not installed, install it with:

```bash
uv tool install graphifyy
```

For a code repository, build the structural graph without an API key:

```bash
graphify extract <path> --code-only
```

For a mixed corpus containing documents, papers, or images, `graphify extract`
can use a configured semantic backend. Check `graphify extract --help`; do not
ask the user to add an API key unless they explicitly want semantic extraction.

Graphify writes its outputs under `graphify-out/`, including `graph.json` and
`GRAPH_REPORT.md`.

## Keep the graph current

After code changes, refresh the graph:

```bash
graphify update .
```

For automatic AST-only refreshes after commits:

```bash
graphify hook install
```

## AdaL integration

`graphify adal install` installs this skill, adds Graphify guidance to the
project's `AGENTS.md`, and registers AdaL `PreToolUse` guards in
`~/.adal/settings.json`. The guards nudge broad search and source reads toward
the graph without changing unrelated AdaL settings.

Strict mode blocks only the first raw source read in a session, then falls back
to a nudge:

```bash
graphify adal install --strict
```

Project-scoped installation writes `.adal/skills/graphify/SKILL.md` and
`AGENTS.md` without changing user-level hook settings:

```bash
graphify adal install --project
```

Remove the corresponding integration with:

```bash
graphify adal uninstall
graphify adal uninstall --project
```

## Guardrails

- Do not invent relationships that are absent from Graphify output.
- Cite `source_file` and `source_location` when Graphify returns them.
- Do not rebuild an existing graph for a question that `query`, `explain`, or
  `path` can answer.
- Run `graphify update .` after modifying code when the graph should remain
  current.
