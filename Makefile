# Makefile — build and run graphify via Docker or Podman (issue #1)
#
# Auto-detects docker; falls back to podman.
# Override: make RUNTIME=podman build

RUNTIME ?= $(shell command -v docker 2>/dev/null || command -v podman 2>/dev/null)
COMPOSE  := $(RUNTIME) compose

# Directory to index (override with: make index SRC=/path/to/project)
SRC ?= $(CURDIR)

.PHONY: pull build up down index logs

## Pull the pre-built image from GHCR (fastest path — no local build needed)
pull:
	$(COMPOSE) pull

## Build the graphify image locally from source
build:
	$(COMPOSE) build

## Pull from GHCR if available, otherwise build locally, then start the MCP server
## Set GRAPHIFY_API_KEY in your shell before running.
up:
	$(COMPOSE) pull mcp 2>/dev/null || $(COMPOSE) build mcp
	$(COMPOSE) up mcp

## Stop the MCP HTTP server
down:
	$(COMPOSE) down

## Index SRC into ./graphify-out/graph.json (code-only, no API key needed)
## For full semantic extraction pass your key: make index ANTHROPIC_API_KEY=sk-...
## Usage: make index  OR  make index SRC=/path/to/project
index:
	mkdir -p ./graphify-out
	$(COMPOSE) --profile cli pull graphify 2>/dev/null || $(COMPOSE) --profile cli build graphify
	$(COMPOSE) --profile cli run --rm \
		-v "$(SRC):/src:ro" \
		$(if $(ANTHROPIC_API_KEY),-e ANTHROPIC_API_KEY=$(ANTHROPIC_API_KEY)) \
		$(if $(OPENAI_API_KEY),-e OPENAI_API_KEY=$(OPENAI_API_KEY)) \
		$(if $(GEMINI_API_KEY),-e GEMINI_API_KEY=$(GEMINI_API_KEY)) \
		graphify extract /src --code-only --output /data

## Tail MCP server logs
logs:
	$(COMPOSE) logs -f mcp
