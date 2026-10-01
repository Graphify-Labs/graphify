# Publish the hosted Graphify MCP listing

This manifest describes `https://api.graphify.com/mcp` only. It does not publish
the local `graphifyy` package. Publication is a separate maintainer action; there
is no workflow that publishes on merge or tag creation.

## Identity and metadata

- Registry identity: `io.github.Graphify-Labs/graphify`.
- Initial hosted listing version: `0.1.0`. Maintain this independently of the
  local Python package's release series; use a new version for later registry
  metadata releases.
- GitHub organization authentication requires a **Graphify-Labs Owner**. Ordinary
  membership does not grant this namespace. The CLI's interactive login avoids
  manually copying a GitHub token.
- The optional `repository` field is intentionally absent: the schema defines it
  as the server implementation's source, and the hosted backend is not published
  in this repository. The public connection guide can be supplied to GitHub
  reviewers as documentation without claiming it is backend source.
- The icon URL is pinned to an existing public commit containing the selected
  Graphify logo. No upload or new website deployment is needed.
- `_meta` contains publisher-provided support/privacy/authentication details.
  Consumers may ignore these extensions; clients discover OAuth through the
  server's standard discovery endpoints.

Sources: [remote servers](https://modelcontextprotocol.io/registry/remote-servers),
[authentication](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/authentication.mdx),
[server.json schema](https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json).

## Validate without publishing

From this repository's root:

```bash
curl --fail-with-body --silent --show-error --max-time 45 \
  -H 'Content-Type: application/json' \
  --data-binary @integrations/hosted-mcp/server.json \
  https://registry.modelcontextprotocol.io/v0.1/validate
```

Expect `{"valid":true,"issues":[]}`. HTTP success alone is insufficient: inspect
`valid` and any reported issues. This endpoint validates public metadata without
creating a registry entry. `mcp-publisher validate` is documented as another
option, but the tested 1.8.1 binary returned `Unknown command: validate`; the API
above worked.

Before publishing, check that the endpoint responds with OAuth discovery,
authenticate in a supported client, and exercise repository discovery and a
known symbol lookup in a populated workspace. These functional checks are
distinct from manifest validation.

## Publish when approved

Install the official publisher through Homebrew:

```bash
brew install mcp-publisher
```

From the repository root, have a Graphify-Labs Owner authenticate and publish:

```bash
mcp-publisher login github
mcp-publisher publish integrations/hosted-mcp/server.json
```

Complete the device flow using the intended Owner account. Keep generated
tokens out of source control. If the organization namespace is unavailable,
confirm the account role and org OAuth policy; do not silently publish under a
personal namespace.

Verify the exact name, version, endpoint, and active/latest metadata in the
registry response:

```bash
curl --fail-with-body --silent --show-error --max-time 30 \
  'https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.Graphify-Labs%2Fgraphify&version=latest'
```

Keep the publication response and verify the actual entry before announcing it.
A registry listing is discoverability metadata, not a security endorsement.

## GitHub MCP Registry inclusion

GitHub's published guidance says to publish to the official MCP Registry first,
then request inclusion from **partnerships@github.com**. See
[GitHub's publishing guide](https://github.blog/ai-and-ml/generative-ai/how-to-find-install-and-manage-mcp-servers-with-the-github-mcp-registry/).
That guidance is dated October 2025; no newer first-party self-service submission
route was verified during preparation. Do not promise automatic inclusion or a
review deadline.

Send the verified official entry, endpoint, public guide, logo, support contact,
OAuth setup, and concrete use cases. Explain that this repo hosts the connection
guide while the hosted implementation is maintained separately. GitHub may ask
for further materials during review. Verify the listing at
[github.com/mcp](https://github.com/mcp) and in VS Code's `@mcp` gallery after
acceptance.

GitHub's MCP Registry is separate from GitHub Marketplace app/action listings;
no Marketplace billing integration is needed for this MCP submission route.
