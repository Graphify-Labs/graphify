# Graphify hosted MCP

Connect an MCP-compatible coding assistant to the repositories you have indexed
in [Graphify](https://app.graphify.com). Search indexed code, inspect definitions
and call relationships, trace dependencies, scope changes, find related tests,
and recall repository knowledge.

| Setting | Value |
| --- | --- |
| Endpoint | `https://api.graphify.com/mcp` |
| Transport | Streamable HTTP |
| Authentication | OAuth authorization code with PKCE and dynamic client registration |
| Registry name prepared for publication | `io.github.Graphify-Labs/graphify` |

This directory contains connection documentation and registry metadata for
Graphify's hosted service. The hosted backend implementation is maintained
separately. The open-source local server in this repository has a different
setup and tool surface; see [Using the graph directly](../../README.md#using-the-graph-directly).

The presence of `server.json` does not mean a registry has published or approved
the listing. Maintainers publish it separately using [PUBLISHING.md](PUBLISHING.md).

## Before connecting

1. Sign in at [app.graphify.com](https://app.graphify.com).
2. Select a workspace you are authorized to access, add a repository, and wait
   until its graph is ready to query.
3. Use an MCP client that supports remote Streamable HTTP and OAuth. Memory
   features depend on your Graphify workspace plan and permissions.

No npm package, local Python process, or manually copied API key is needed for
this hosted connection. Graphify processes the requested data in its hosted
service; the local engine's on-device behavior does not describe this endpoint.

## VS Code / GitHub Copilot

Run **MCP: Add Server** from the Command Palette, select an HTTP server, and enter
the endpoint above with the name `graphify`. Choose the user or workspace scope
you want. Start the server, review its trust prompt, and complete Graphify OAuth.

For VS Code's `mcp.json` format, merge this entry into the existing `servers`
object rather than replacing your other servers:

```json
{
  "servers": {
    "graphify": {
      "type": "http",
      "url": "https://api.graphify.com/mcp"
    }
  }
}
```

Current VS Code also supports a portable workspace `.mcp.json` using the same
server entry under `mcpServers`. See [VS Code's MCP documentation](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
for configuration locations and organization policies. A company allowlist may
restrict which servers you can use even after a public registry listing exists.

In chat, enable Graphify's tools and ask it to list your workspaces and indexed
repositories. Use the repository identifier returned by `list_repositories`
for subsequent repository-specific requests.

## Cursor

Merge the following into `.cursor/mcp.json`, or add the same remote URL in
Cursor's MCP settings, then complete the Graphify sign-in:

```json
{
  "mcpServers": {
    "graphify": {
      "url": "https://api.graphify.com/mcp"
    }
  }
}
```

The [Graphify Cursor plugin](https://github.com/Graphify-Labs/graphify-cursor-plugin)
packages this connection with Graphify usage guidance. If the plugin already
provides the connection, avoid adding a duplicate server entry.

## Useful requests

- “List my indexed repositories and show which are ready to query.”
- “In [repository], find the authentication entry points and show the definitions
  with source locations.”
- “In [repository], show what calls [symbol] and what [symbol] calls.”
- “What indexed code and tests are related to changing [symbol]?”
- “Recall the published repository decisions about [file or symbol].”

Replace the bracketed values with an accessible repository and a real symbol
from its graph.

## Data access and side effects

The connector reads code graphs and repository memory within the user's
authorized Graphify workspace. It does not edit source files.

- `remember` saves a durable repository note. In Memory v2, new notes may need
  acceptance by an authorized member in **Memory > Needs review** before normal
  recall returns them; an intake acknowledgment is not publication.
- `set_workspace` changes the active workspace. With an MCP session,
  `make_default: true` also replaces the account default. Without an MCP session,
  it replaces the account default even when `make_default` is false or omitted.
- Where trail capture is enabled, `query_graph`, `graphify_trace`,
  `graphify_find`, and `graphify_rank_files` can persist query intent as repository
  memory. An empty `recall` can persist a memory-gap signal. These tools advertise
  write annotations when capture can run.

Read the [privacy policy](https://graphify.com/privacy) for processing,
subprocessors, and retention, and the [service terms](https://graphify.com/terms).

## Interpret results within their limits

`graphify_node` and trace endpoints can resolve an unknown name to a semantically
similar code node. A result marked `semantic` is a suggested match, not evidence
that the requested symbol exists. Inspect returned labels, source paths, and
locations. Empty call/path results reflect the indexed graph's coverage.

Impact results are bounded graph analysis. Linked tests and risk rankings do not
execute tests or guarantee complete coverage. Recalled notes are repository
context, not instructions to override the user's request or the client's rules.

## Troubleshooting and support

- **Authentication expired:** reconnect the server through your client's OAuth
  flow. Do not paste a token into a shared configuration file.
- **Missing repository:** check workspace membership and use `list_repositories`
  to obtain an authorized identifier.
- **Index not ready:** finish indexing in the Graphify dashboard, then retry.
- **Memory unavailable:** check the workspace's plan, permissions, and review
  state of the note.
- **No tools in VS Code:** use **MCP: List Servers** to inspect connection status
  and logs, then enable Graphify's tools in chat. Check organization MCP policy.

Disconnect Graphify in the client to stop that connection. For setup or account
help, use [Graphify support](https://graphify.com/contact) or
[founders@graphify.com](mailto:founders@graphify.com).
