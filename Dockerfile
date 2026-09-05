# graphify MCP server as a shared HTTP service (issue #1, #1143).
# Works with both Docker and Podman.
#
# Recommended: use the Makefile or docker-compose.yaml instead of bare commands.
#   make build          # build the image
#   make index          # index the current directory (uses graphify CLI)
#   make up             # start the MCP HTTP server
#
# Manual build:
#   docker build -t graphify .       # Docker
#   podman build -t graphify .       # Podman
#
# Run MCP HTTP server (default):
#   docker run -p 8080:8080 -v "$(pwd)/graphify-out:/data:ro" \
#       -e GRAPHIFY_API_KEY="$SECRET" graphify \
#       /data/graph.json --transport http --host 0.0.0.0
#
# Code-only index (override entrypoint to graphify CLI):
#   docker run --rm --entrypoint graphify \
#       -v "$(pwd):/src:ro" -v "$(pwd)/graphify-out:/data/graphify-out" graphify \
#       extract /src --code-only --output /data
#
# Builds from source so the image includes the Streamable HTTP transport even
# before it lands on PyPI. The graph.json is mounted at runtime (-v), never
# baked into the image.
FROM python:3.12-slim

WORKDIR /app
COPY . /app

# The [mcp] extra pulls mcp + starlette + uvicorn, which the HTTP transport needs.
# Pin mcp<2.0.0: mcp 2.0.0 removed mcp.types.AnyUrl which graphify.serve imports,
# and introduced pyjwt[crypto] -> cryptography (Rust) which crashes with SIGILL on
# some ARM64 container runtimes.  mcp 1.x avoids both issues.
RUN pip install --no-cache-dir ".[mcp]" \
 && pip install --no-cache-dir "mcp<2.0.0" \
 && pip install --no-cache-dir "cryptography>=41,<42"

# Run as a non-root user — the server is network-exposed.
RUN useradd --create-home --uid 10001 graphify
USER graphify

EXPOSE 8080

ENTRYPOINT ["graphify-mcp"]
CMD ["/data/graph.json", "--transport", "http", "--host", "0.0.0.0", "--port", "8080"]
