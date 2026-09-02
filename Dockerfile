# graphify MCP server. Mount a repository containing graphify-out/graph.json.
FROM python:3.12-slim
WORKDIR /app
COPY . /app

# The [mcp] extra pulls mcp + starlette + uvicorn, which the HTTP transport needs.
RUN pip install --no-cache-dir ".[mcp]"

# Run as a non-root user because the server is network-exposed.
RUN useradd --create-home --uid 10001 graphify
USER graphify

EXPOSE 8080
ENTRYPOINT ["python", "-m", "graphify.serve"]
CMD ["--graphs-dir", "/data", "--transport", "http", "--host", "0.0.0.0", "--port", "8080"]
