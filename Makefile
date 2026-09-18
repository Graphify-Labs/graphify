# Makefile — build and run graphify via Docker or Podman (issue #1)
#
# Auto-detects docker; falls back to podman.
# Override: make RUNTIME=podman build

RUNTIME ?= $(shell command -v docker 2>/dev/null || command -v podman 2>/dev/null)
COMPOSE  := $(RUNTIME) compose

# Directory to index (override with: make index SRC=/path/to/project)
SRC ?= $(CURDIR)

# ANSI colors
BOLD   := \033[1m
CYAN   := \033[36m
GREEN  := \033[32m
YELLOW := \033[33m
DIM    := \033[2m
RESET  := \033[0m

.PHONY: help pull build up down index logs
.DEFAULT_GOAL := help

## Show this help message
help:
	@printf "\n$(BOLD)$(CYAN)graphify$(RESET) — containerized knowledge graph for your codebase\n"
	@printf "$(DIM)Runtime: $(RUNTIME)$(RESET)\n\n"
	@printf "$(BOLD)$(GREEN)Quick start$(RESET)\n"
	@printf "  $(CYAN)make pull$(RESET)   then   $(CYAN)make index$(RESET)   then   $(CYAN)GRAPHIFY_API_KEY=secret make up$(RESET)\n\n"
	@printf "$(BOLD)$(GREEN)Targets$(RESET)\n"
	@printf "  $(BOLD)$(YELLOW)%-10s$(RESET)  %s\n" "pull"  "Pull pre-built image from GHCR (no local build needed)"
	@printf "  $(BOLD)$(YELLOW)%-10s$(RESET)  %s\n" "build" "Build image locally from source"
	@printf "  $(BOLD)$(YELLOW)%-10s$(RESET)  %s\n" "index" "Index SRC dir into ./graphify-out/graph.json (code-only)"
	@printf "  $(BOLD)$(YELLOW)%-10s$(RESET)  %s\n" "up"    "Start the MCP HTTP server (pull or build first)"
	@printf "  $(BOLD)$(YELLOW)%-10s$(RESET)  %s\n" "down"  "Stop the MCP HTTP server"
	@printf "  $(BOLD)$(YELLOW)%-10s$(RESET)  %s\n" "logs"  "Tail MCP server logs"
	@printf "\n$(BOLD)$(GREEN)Variables$(RESET)\n"
	@printf "  $(CYAN)SRC$(RESET)               Directory to index           $(DIM)(default: \$$PWD)$(RESET)\n"
	@printf "  $(CYAN)RUNTIME$(RESET)           docker or podman             $(DIM)(default: auto-detect)$(RESET)\n"
	@printf "  $(CYAN)GRAPHIFY_API_KEY$(RESET)  Bearer token for MCP server  $(DIM)(required for \`make up\`)$(RESET)\n"
	@printf "  $(CYAN)GRAPHIFY_PORT$(RESET)     Host port for MCP server     $(DIM)(default: 8080)$(RESET)\n"
	@printf "  $(CYAN)GRAPHIFY_IMAGE$(RESET)    Override GHCR image          $(DIM)(default: ghcr.io/slmingol/graphify:latest)$(RESET)\n"
	@printf "  $(CYAN)ANTHROPIC_API_KEY$(RESET) LLM key for semantic index   $(DIM)(optional)$(RESET)\n"
	@printf "\n$(BOLD)$(GREEN)Examples$(RESET)\n"
	@printf "  $(DIM)# Index a different project$(RESET)\n"
	@printf "  make index SRC=/path/to/project\n\n"
	@printf "  $(DIM)# Semantic extraction with Claude$(RESET)\n"
	@printf "  make index ANTHROPIC_API_KEY=sk-...\n\n"
	@printf "  $(DIM)# Use podman explicitly$(RESET)\n"
	@printf "  make RUNTIME=podman up\n\n"

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
