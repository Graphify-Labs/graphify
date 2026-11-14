# Graphify for Kimi

This directory contains the source of a personal hosted Kimi plugin for the official Graphify MCP server. It connects Kimi to repositories indexed in a Graphify workspace over Streamable HTTP with OAuth; no API key or local Graphify installation is stored in the plugin.

## What it includes

- `kimi.plugin.json` — the hosted MCP connection and plugin metadata.
- `skills/graphify-code-graph/SKILL.md` — query selection, evidence, and safety guidance.
- `locales/zh-CN.json` — the required Chinese localization for the English manifest.

## Use after publication

1. Open Kimi's plugin page, then **Custom → Created by me**.
2. Install **Graphify** and complete Graphify's browser OAuth authorization.
3. Make sure the selected workspace contains at least one repository with **Indexed** status.
4. Ask Kimi to list the repositories available through Graphify, then run a scoped code query.

Publishing does not install the plugin, and installing it does not complete OAuth authorization by itself.

## Boundaries

Hosted Graphify answers from the latest indexed graph, not from uncommitted local files. Its MCP tools do not edit code or run tests. The plugin asks for confirmation before changing the active workspace or saving repository memory.

For product setup and troubleshooting, see [Graphify MCP](https://docs.graphify.com/platform/graphify-mcp).
