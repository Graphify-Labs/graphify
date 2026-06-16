# Graphify Modular Reorganization Plan

**Status:** Draft  
**Created:** 2026-06-16  
**Branch:** v8  
**Goal:** Transform graphify from a flat codebase into a modular, plugin-friendly architecture

---

## Executive Summary

Graphify has grown into a powerful tool with 36 language extractors, 15+ platform integrations, and multiple LLM backends. The current flat structure makes it hard to:
- Add new language support without touching a 12,000-line file
- Add new platforms without editing a 4,700-line CLI
- Maintain clear boundaries between core, integrations, and platform-specific code
- Enable external plugins (extractors, backends, platforms)

This plan reorganizes the codebase into a clean modular structure over 6 phases while maintaining 100% backward compatibility.

---

## Current State Analysis

### File Statistics

| File | Lines | Purpose | Problem |
|------|-------|---------|---------|
| `extract.py` | 12,390 | All 36 language extractors | Monolithic, hard to extend |
| `__main__.py` | 4,717 | CLI + all platform installers | Mixed concerns |
| `llm.py` | 2,167 | LLM orchestration + all backends | Backend code mixed |
| `detect.py` | 1,426 | File discovery | Acceptable |
| `export.py` | 1,516 | Output formats | Multiple formats mixed |
| `serve.py` | 1,319 | MCP server | Acceptable |
| `callflow_html.py` | 2,020 | Mermaid diagrams | Large but focused |

### Dependency Graph (Simplified)

```
__main__.py
    ├── extract.py (imports tree-sitter grammars)
    ├── build.py
    ├── cluster.py
    ├── analyze.py
    ├── report.py
    ├── export.py
    ├── llm.py
    ├── serve.py
    └── [platform-specific code mixed in __main__]

extract.py
    ├── cache.py
    └── [36 language extractor functions]
```

### What Works Well

- Functional, stateless pipeline design
- Clear module boundaries documented in ARCHITECTURE.md
- Comprehensive test suite (90+ test files)
- Lazy imports in `__init__.py` for fast CLI startup
- Good separation: detect → extract → build → cluster → analyze → report → export

### What Needs Improvement

- **extract.py is a monolith** - 44 extractor functions in one file
- **__main__.py does too much** - CLI + platform installers + command dispatch
- **llm.py mixes concerns** - orchestration + all backend implementations
- **No plugin architecture** - cannot add extractors/backends without modifying core
- **Platform code scattered** - 13 skill files + installer logic in __main__.py

---

## Target Architecture

```
graphify/
├── __init__.py                    # Public API re-exports (backward compatible)
├── __main__.py                    # Thin CLI entrypoint (~100 lines)
│
├── core/                          # Core pipeline (zero external deps beyond tree-sitter)
│   ├── __init__.py
│   ├── detect.py                  # File discovery & filtering
│   ├── build.py                   # Graph assembly from extractions
│   ├── cluster.py                 # Community detection
│   ├── analyze.py                 # God nodes, surprises, questions
│   ├── report.py                  # GRAPH_REPORT.md generation
│   ├── validate.py                # Extraction schema validation
│   └── security.py                # URL/path sanitization
│
├── extractors/                    # Language extractors (plugin architecture)
│   ├── __init__.py                # Auto-discovers all extractors
│   ├── base.py                    # Base extractor class + Extractor protocol
│   ├── registry.py                # Extension → extractor mapping
│   ├── _utils.py                  # Shared extraction utilities
│   ├── _file_node.py              # File-level node ID generation
│   │
│   ├── python.py                  # extract_python()
│   ├── javascript.py              # extract_js()
│   ├── typescript.py              # extract_ts(), extract_tsx()
│   ├── jsx.py                     # extract_jsx()
│   ├── go.py                      # extract_go()
│   ├── rust.py                    # extract_rust()
│   ├── java.py                    # extract_java()
│   ├── groovy.py                  # extract_groovy()
│   ├── c.py                       # extract_c()
│   ├── cpp.py                     # extract_cpp()
│   ├── ruby.py                    # extract_ruby()
│   ├── csharp.py                  # extract_csharp()
│   ├── apex.py                    # extract_apex()
│   ├── kotlin.py                  # extract_kotlin()
│   ├── scala.py                   # extract_scala()
│   ├── php.py                     # extract_php()
│   ├── blade.py                   # extract_blade()
│   ├── dart.py                    # extract_dart()
│   ├── verilog.py                 # extract_verilog()
│   ├── sql.py                     # extract_sql()
│   ├── lua.py                     # extract_lua()
│   ├── swift.py                   # extract_swift()
│   ├── julia.py                   # extract_julia()
│   ├── fortran.py                 # extract_fortran()
│   ├── zig.py                     # extract_zig()
│   ├── powershell.py              # extract_powershell()
│   ├── objc.py                    # extract_objc()
│   ├── elixir.py                  # extract_elixir()
│   ├── markdown.py                # extract_markdown()
│   ├── pascal.py                  # extract_pascal()
│   ├── bash.py                    # extract_bash()
│   ├── json_ast.py                # extract_json() - JSON as AST
│   ├── vue.py                     # extract_vue()
│   ├── svelte.py                  # extract_svelte()
│   ├── astro.py                   # extract_astro()
│   ├── terraform.py               # extract_terraform() / extract_hcl()
│   ├── dm.py                      # extract_dm() - BYOND DreamMaker
│   └── dotnet.py                  # extract_csproj(), extract_fsproj(), etc.
│
├── backends/                      # LLM backends for semantic extraction
│   ├── __init__.py
│   ├── base.py                    # Backend protocol
│   ├── registry.py                # Name → backend mapping
│   ├── anthropic.py               # Claude API
│   ├── openai.py                  # OpenAI + compatible endpoints
│   ├── gemini.py                  # Google Gemini
│   ├── ollama.py                  # Local Ollama
│   ├── bedrock.py                 # AWS Bedrock
│   ├── azure.py                   # Azure OpenAI
│   ├── kimi.py                    # Moonshot (China)
│   ├── deepseek.py                # DeepSeek
│   └── claude_cli.py              # Claude Code CLI passthrough
│
├── llm/                           # LLM orchestration
│   ├── __init__.py
│   ├── chunking.py                # Token budget chunking
│   ├── prompts.py                 # System prompts for extraction
│   ├── dedup.py                   # LLM-based entity dedup
│   └── executor.py                # Parallel LLM call orchestration
│
├── platforms/                     # AI assistant integrations
│   ├── __init__.py
│   ├── base.py                    # Platform installer protocol
│   ├── registry.py                # Platform name → installer mapping
│   ├── claude.py                  # Claude Code
│   ├── codex.py                   # OpenAI Codex
│   ├── cursor.py                  # Cursor IDE
│   ├── gemini.py                  # Gemini CLI
│   ├── kilo.py                    # Kilo Code
│   ├── vscode.py                  # VS Code Copilot
│   ├── aider.py                   # Aider
│   ├── amp.py                     # Amp
│   ├── claw.py                    # OpenClaw
│   ├── droid.py                   # Factory Droid
│   ├── trae.py                    # Trae
│   ├── kiro.py                    # Kiro IDE/CLI
│   ├── pi.py                      # Pi coding agent
│   ├── devin.py                   # Devin CLI
│   ├── antigravity.py             # Google Antigravity
│   ├── copilot.py                 # GitHub Copilot CLI
│   ├── opencode.py                # OpenCode
│   ├── codebuddy.py               # CodeBuddy
│   ├── hermes.py                  # Hermes
│   └── kimi_platform.py           # Kimi Code platform
│
├── skills/                        # Skill templates (packaged data - existing)
│   ├── claude/references/
│   ├── codex/references/
│   └── ...
│
├── always_on/                     # Always-on instruction blocks (existing)
│   ├── claude-md.md
│   ├── agents-md.md
│   └── ...
│
├── export/                        # Output formats
│   ├── __init__.py
│   ├── json_graph.py              # to_json()
│   ├── html.py                    # to_html(), graph.html generation
│   ├── svg.py                     # to_svg()
│   ├── callflow_html.py           # Mermaid architecture diagrams
│   ├── tree_html.py               # Tree visualization
│   ├── obsidian.py                # Obsidian vault export
│   ├── wiki.py                    # Markdown wiki generation
│   ├── neo4j.py                   # Cypher export for Neo4j
│   ├── falkordb.py                # FalkorDB export
│   └── graphml.py                 # Gephi/yEd export
│
├── integrations/                  # External system connectors
│   ├── __init__.py
│   ├── mcp_server.py              # MCP stdio/HTTP server (from serve.py)
│   ├── postgres.py                # PostgreSQL introspection
│   ├── cargo.py                   # Cargo workspace introspection
│   ├── google_workspace.py        # Google Docs/Sheets (existing)
│   ├── scip.py                    # SCIP index ingestion
│   └── mcp_ingest.py              # MCP config extraction (existing)
│
├── cli/                           # CLI commands
│   ├── __init__.py
│   ├── main.py                    # ArgumentParser setup, main dispatch
│   ├── install.py                 # install/uninstall commands
│   ├── extract_cmd.py             # extract command
│   ├── query.py                   # query/path/explain commands
│   ├── export_cmd.py              # export command
│   ├── hooks_cmd.py               # hook install/uninstall
│   ├── prs.py                     # PR dashboard
│   ├── global_graph_cmd.py        # global graph commands
│   ├── watch_cmd.py               # watch command
│   ├── merge.py                   # merge-graphs command
│   └── utils.py                   # CLI utilities (banner, etc.)
│
├── utils/                         # Shared utilities
│   ├── __init__.py
│   ├── minhash.py                 # LSH dedup (existing _minhash.py)
│   ├── symbol_resolution.py       # Cross-file symbol linking (existing)
│   ├── diagnostics.py             # MultiDiGraph readiness checks (existing)
│   ├── querylog.py                # Query logging (existing)
│   └── manifest.py                # Manifest helpers (existing)
│
├── cache.py                       # Per-file extraction cache (keep at root)
├── affected.py                    # Affected file tracking (existing)
├── benchmark.py                   # Token-reduction benchmark (existing)
└── semantic_cleanup.py            # Semantic extraction cleanup (existing)
```

---

## Migration Phases

### Phase 1: Extract Language Extractors

**Duration:** 1-2 weeks  
**Impact:** Highest - breaks up the largest monolith  
**Risk:** Medium - core functionality, extensive testing needed

#### Goals

1. Break up `extract.py` (12,390 lines) into modular `extractors/` package
2. Maintain 100% backward compatibility via re-exports
3. Enable plugin architecture for third-party extractors

#### Step-by-Step Instructions

##### Step 1.1: Create Extractor Package Structure

```bash
mkdir -p graphify/extractors
touch graphify/extractors/__init__.py
touch graphify/extractors/base.py
touch graphify/extractors/registry.py
touch graphify/extractors/_utils.py
touch graphify/extractors/_file_node.py
```

##### Step 1.2: Extract Shared Utilities

Create `graphify/extractors/_utils.py` with the following content:
- Move `_RECURSION_LIMIT` constant
- Move `_LANGUAGE_BUILTIN_GLOBALS` frozenset (lines 24-43 from extract.py)
- Move `_raise_recursion_limit()` function
- Move `_safe_extract()` function
- Move `_make_id()` function
- Move `_file_stem()` function
- Move `_file_node_id()` function

Create `graphify/extractors/_file_node.py`:
- Re-export `file_node_id`, `file_stem`, `make_id` for standalone imports

##### Step 1.3: Define Extractor Protocol

Create `graphify/extractors/base.py`:
- Define `Extractor` Protocol with `extract(path: Path) -> dict` method
- Define `BaseExtractor` abstract base class with `extensions` property
- Document the extraction output schema (nodes, edges, error)

##### Step 1.4: Create Extractor Registry

Create `graphify/extractors/registry.py`:
- `ExtractorFunc = Callable[[Path], dict]` type alias
- `_REGISTRY: Dict[str, ExtractorFunc]` global registry
- `@register(extensions: Set[str])` decorator
- `get_extractor(path: Path) -> ExtractorFunc | None`
- `get_all_extensions() -> Set[str]`
- `extract(path: Path) -> dict` - main dispatch function

##### Step 1.5: Migrate Extractors One by One

For each language extractor, create a new file and move the function:

**Migration Order (start with simpler extractors):**

1. **json_ast.py** - `extract_json()` (~50 lines)
2. **bash.py** - `extract_bash()` (~100 lines)
3. **markdown.py** - `extract_markdown()` (~100 lines)
4. **lua.py** - `extract_lua()` (~150 lines)
5. **powershell.py** - `extract_powershell()` (~150 lines)
6. **zig.py** - `extract_zig()` (~150 lines)
7. **elixir.py** - `extract_elixir()` (~150 lines)
8. **verilog.py** - `extract_verilog()` (~150 lines)
9. **sql.py** - `extract_sql()` (~150 lines)
10. **julia.py** - `extract_julia()` (~150 lines)
11. **groovy.py** - `extract_groovy()` (~150 lines)
12. **blade.py** - `extract_blade()` (~100 lines)
13. **vue.py** - `extract_vue()` (~100 lines)
14. **svelte.py** - `extract_svelte()` (~100 lines)
15. **astro.py** - `extract_astro()` (~100 lines)
16. **fortran.py** - `extract_fortran()` (~200 lines)
17. **swift.py** - `extract_swift()` (~200 lines)
18. **objc.py** - `extract_objc()` (~200 lines)
19. **ruby.py** - `extract_ruby()` (~200 lines)
20. **go.py** - `extract_go()` (~200 lines)
21. **rust.py** - `extract_rust()` (~200 lines)
22. **kotlin.py** - `extract_kotlin()` (~200 lines)
23. **scala.py** - `extract_scala()` (~200 lines)
24. **php.py** - `extract_php()` (~200 lines)
25. **dart.py** - `extract_dart()` (~200 lines)
26. **c.py** - `extract_c()` (~200 lines)
27. **cpp.py** - `extract_cpp()` (~250 lines)
28. **csharp.py** - `extract_csharp()` (~250 lines)
29. **apex.py** - `extract_apex()` (~150 lines)
30. **java.py** - `extract_java()` (~250 lines)
31. **javascript.py** - `extract_js()` (~250 lines)
32. **jsx.py** - `extract_jsx()` (~50 lines)
33. **typescript.py** - `extract_ts()`, `extract_tsx()` (~350 lines)
34. **pascal.py** - `extract_pascal()` (~200 lines)
35. **terraform.py** - `extract_terraform()` (~150 lines)
36. **dm.py** - `extract_dm()` (~150 lines)
37. **dotnet.py** - `extract_csproj()`, etc. (~200 lines)
38. **python.py** - `extract_python()` (~300 lines) - do last as it's most complex

**For each extractor:**

```python
# Example: graphify/extractors/python.py
"""Python AST extractor using tree-sitter-python."""
from __future__ import annotations
from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

from .registry import register
from ._utils import make_id, file_node_id, safe_extract

_EXTENSIONS = {'.py', '.pyw', '.pyi'}

@register(_EXTENSIONS)
def extract_python(path: Path) -> dict:
    """Extract nodes and edges from a Python source file."""
    # Move implementation from extract.py
    ...
```

##### Step 1.6: Update Extractor Package Init

Create `graphify/extractors/__init__.py`:
- Import registry functions
- Import base classes
- Import all extractor modules (triggers @register decorators)
- Re-export utilities for backward compatibility

##### Step 1.7: Refactor Original extract.py

After migrating all extractors, reduce `extract.py` to orchestration:
- Keep `extract()` function that delegates to `extractors.extract()`
- Keep `collect_files()` function
- Add backward compatibility re-exports for all `extract_<lang>()` functions
- Keep MCP config extraction logic (or move to integrations/)

##### Step 1.8: Update Tests

```bash
mkdir -p tests/extractors
touch tests/extractors/__init__.py
```

- Move language-specific tests to `tests/extractors/`
- Update imports to use new module paths
- Keep integration tests in `tests/`

##### Step 1.9: Run Full Test Suite

```bash
uv run pytest tests/ -v
```

Fix any failures before proceeding to next phase.

##### Step 1.10: Update ARCHITECTURE.md

Add section about extractors:

```markdown
## Extractors

Language extractors live in `graphify/extractors/`. Each language has its own module
exporting an `extract_<lang>(path: Path) -> dict` function.

### Adding a new language extractor

1. Create `graphify/extractors/<lang>.py`
2. Import and use the `@register` decorator with file extensions
3. Implement `extract_<lang>(path: Path) -> dict`
4. Add tree-sitter dependency to `pyproject.toml` if needed
5. Add tests to `tests/extractors/test_<lang>.py`
```

#### Success Criteria

- [ ] All 38 extractors migrated to individual files
- [ ] `extract.py` reduced to <500 lines
- [ ] All tests pass
- [ ] Backward compatibility maintained (old imports still work)
- [ ] New extractors can be added with single file + `@register` decorator

---

### Phase 2: Split CLI from Core

**Duration:** 1 week  
**Impact:** High - separates concerns, enables parallel work  
**Risk:** Medium - CLI is heavily used

#### Goals

1. Reduce `__main__.py` from 4,717 lines to ~500 lines
2. Create `cli/` package with command-specific modules
3. Extract platform installers to `platforms/`

#### Step-by-Step Instructions

##### Step 2.1: Create CLI Package Structure

```bash
mkdir -p graphify/cli
touch graphify/cli/__init__.py
touch graphify/cli/main.py
touch graphify/cli/install.py
touch graphify/cli/extract_cmd.py
touch graphify/cli/query.py
touch graphify/cli/export_cmd.py
touch graphify/cli/hooks_cmd.py
touch graphify/cli/prs.py
touch graphify/cli/global_graph_cmd.py
touch graphify/cli/watch_cmd.py
touch graphify/cli/merge.py
touch graphify/cli/utils.py
```

##### Step 2.2: Create Platforms Package

```bash
mkdir -p graphify/platforms
touch graphify/platforms/__init__.py
touch graphify/platforms/base.py
touch graphify/platforms/registry.py
```

##### Step 2.3: Define Platform Protocol

Create `graphify/platforms/base.py`:

```python
"""Platform installer protocol."""
from abc import ABC, abstractmethod
from pathlib import Path

class PlatformInstaller(ABC):
    """Base class for platform installers."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Platform name (e.g., 'claude', 'cursor')."""
        ...
    
    @property
    def skill_file(self) -> str | None:
        """Skill filename (e.g., 'skill.md'). None if no skill file."""
        return None
    
    @abstractmethod
    def install(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        """Install graphify for this platform."""
        ...
    
    @abstractmethod
    def uninstall(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        """Uninstall graphify from this platform."""
        ...
```

##### Step 2.4: Create Platform Registry

Create `graphify/platforms/registry.py`:

```python
"""Platform registry - maps platform names to installers."""
from typing import Dict, Type
from .base import PlatformInstaller

_REGISTRY: Dict[str, Type[PlatformInstaller]] = {}

def register(name: str):
    """Decorator to register a platform installer."""
    def decorator(cls: Type[PlatformInstaller]) -> Type[PlatformInstaller]:
        _REGISTRY[name] = cls
        return cls
    return decorator

def get_installer(name: str) -> PlatformInstaller:
    """Get an installer instance by platform name."""
    if name not in _REGISTRY:
        raise ValueError(f"Unknown platform: {name}")
    return _REGISTRY[name]()

def get_all_platforms() -> list[str]:
    """Get all registered platform names."""
    return list(_REGISTRY.keys())
```

##### Step 2.5: Migrate Platform Installers

For each platform, extract installer logic from `__main__.py`:

**Platform Migration Checklist:**

| Platform | Functions to Move | Target File |
|----------|-------------------|-------------|
| claude | `install()`, `_skill_registration()` | `claude.py` |
| gemini | `gemini_install()`, `gemini_uninstall()` | `gemini.py` |
| vscode | `vscode_install()`, `vscode_uninstall()` | `vscode.py` |
| cursor | `_cursor_install()`, `_cursor_uninstall()` | `cursor.py` |
| kilo | `_kilo_install()`, `_kilo_uninstall()` | `kilo.py` |
| codex | `_install_codex_hook()`, `_uninstall_codex_hook()` | `codex.py` |
| opencode | `_install_opencode_plugin()` | `opencode.py` |
| amp | `_amp_install()`, `_amp_uninstall()` | `amp.py` |
| aider | `_agents_install()` | `aider.py` |
| claw | `_agents_install()` | `claw.py` |
| droid | `_agents_install()` | `droid.py` |
| trae | `_agents_install()` | `trae.py` |
| kiro | `_kiro_install()`, `_kiro_uninstall()` | `kiro.py` |
| pi | `_project_install()` | `pi.py` |
| devin | `_devin_rules_install()` | `devin.py` |
| antigravity | `_antigravity_install()` | `antigravity.py` |
| copilot | `_project_install()` | `copilot.py` |
| codebuddy | CodeBuddy logic | `codebuddy.py` |
| hermes | Hermes logic | `hermes.py` |
| kimi | Kimi Code logic | `kimi_platform.py` |

**Example Platform Implementation:**

```python
# graphify/platforms/claude.py
"""Claude Code platform installer."""
from pathlib import Path
from .base import PlatformInstaller
from .registry import register

@register("claude")
class ClaudeInstaller(PlatformInstaller):
    name = "claude"
    skill_file = "skill.md"
    
    def install(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        # Move logic from __main__.py install() function
        ...
    
    def uninstall(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        # Move logic from __main__.py
        ...
```

##### Step 2.6: Extract CLI Commands

Create `graphify/cli/main.py` with ArgumentParser setup:

```python
"""Main CLI entrypoint and argument parsing."""
import argparse
import sys

def main() -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(prog="graphify")
    subparsers = parser.add_subparsers(dest="command")
    
    # Import and register command modules
    from . import install, extract_cmd, query, export_cmd, hooks_cmd, prs
    
    install.add_parser(subparsers)
    extract_cmd.add_parser(subparsers)
    query.add_parser(subparsers)
    export_cmd.add_parser(subparsers)
    hooks_cmd.add_parser(subparsers)
    prs.add_parser(subparsers)
    
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)
```

##### Step 2.7: Refactor __main__.py

Reduce to thin entrypoint:

```python
#!/usr/bin/env python3
"""graphify CLI - turn any folder into a queryable knowledge graph."""
import sys
from .cli.main import main

if __name__ == "__main__":
    sys.exit(main())
```

##### Step 2.8: Run Tests

```bash
uv run pytest tests/ -v
```

#### Success Criteria

- [ ] `__main__.py` reduced to <100 lines
- [ ] All 20 platforms migrated to `platforms/`
- [ ] CLI commands split into `cli/` modules
- [ ] All tests pass
- [ ] All platform installs work as before

---

### Phase 3: Organize LLM Backends

**Duration:** 1 week  
**Impact:** Medium - makes backend selection extensible  
**Risk:** Low - well-isolated code

#### Goals

1. Split `llm.py` (2,167 lines) into `backends/` and `llm/`
2. Create Backend protocol for plugin support
3. Keep orchestration separate from implementations

#### Step-by-Step Instructions

##### Step 3.1: Create Backends Package

```bash
mkdir -p graphify/backends
touch graphify/backends/__init__.py
touch graphify/backends/base.py
touch graphify/backends/registry.py
touch graphify/backends/anthropic.py
touch graphify/backends/openai.py
touch graphify/backends/gemini.py
touch graphify/backends/ollama.py
touch graphify/backends/bedrock.py
touch graphify/backends/azure.py
touch graphify/backends/kimi.py
touch graphify/backends/deepseek.py
touch graphify/backends/claude_cli.py
```

##### Step 3.2: Define Backend Protocol

Create `graphify/backends/base.py`:

```python
"""Backend protocol for LLM providers."""
from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

@runtime_checkable
class Backend(Protocol):
    """Protocol for LLM backends."""
    
    @property
    def name(self) -> str:
        """Backend name (e.g., 'anthropic', 'openai')."""
        ...
    
    def extract(self, chunks: list[str], **kwargs) -> list[dict]:
        """Extract entities from text chunks."""
        ...
    
    def is_available(self) -> bool:
        """Check if backend is properly configured."""
        ...
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        ...
```

##### Step 3.3: Create Backend Registry

Create `graphify/backends/registry.py`:

```python
"""Backend registry - maps backend names to implementations."""
from typing import Dict, Type
from .base import Backend

_REGISTRY: Dict[str, Type[Backend]] = {}

def register(name: str):
    """Decorator to register a backend."""
    def decorator(cls: Type[Backend]) -> Type[Backend]:
        _REGISTRY[name] = cls
        return cls
    return decorator

def get_backend(name: str) -> Backend:
    """Get a backend instance by name."""
    if name not in _REGISTRY:
        raise ValueError(f"Unknown backend: {name}")
    return _REGISTRY[name]()

def get_all_backends() -> list[str]:
    """Get all registered backend names."""
    return list(_REGISTRY.keys())

def detect_backend_from_env() -> str | None:
    """Auto-detect backend from environment variables."""
    import os
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini"
    # ... etc
    return None
```

##### Step 3.4: Extract Each Backend

**Backend Migration Checklist:**

| Backend | Source Lines | Target File | Config Vars |
|---------|--------------|-------------|-------------|
| anthropic | ~200 lines | `anthropic.py` | `ANTHROPIC_API_KEY` |
| openai | ~250 lines | `openai.py` | `OPENAI_API_KEY`, `OPENAI_BASE_URL` |
| gemini | ~200 lines | `gemini.py` | `GEMINI_API_KEY`, `GOOGLE_API_KEY` |
| ollama | ~150 lines | `ollama.py` | `OLLAMA_BASE_URL` |
| bedrock | ~150 lines | `bedrock.py` | AWS credentials |
| azure | ~150 lines | `azure.py` | `AZURE_OPENAI_API_KEY` |
| kimi | ~150 lines | `kimi.py` | `MOONSHOT_API_KEY` |
| deepseek | ~100 lines | `deepseek.py` | `DEEPSEEK_API_KEY` |
| claude_cli | ~100 lines | `claude_cli.py` | (uses claude binary) |

##### Step 3.5: Create LLM Orchestration Package

```bash
mkdir -p graphify/llm
touch graphify/llm/__init__.py
touch graphify/llm/chunking.py
touch graphify/llm/prompts.py
touch graphify/llm/dedup.py
touch graphify/llm/executor.py
```

**Move to `llm/chunking.py`:**
- Token budget calculations
- File chunking logic
- `_read_files()` function

**Move to `llm/prompts.py`:**
- System prompts for extraction
- Prompt templates

**Move to `llm/dedup.py`:**
- LLM-based entity deduplication

**Move to `llm/executor.py`:**
- Parallel LLM call orchestration
- `_call_with_backoff()` logic

##### Step 3.6: Update Imports

Update all files that import from `llm.py` to use new structure.

##### Step 3.7: Run Tests

```bash
uv run pytest tests/ -v
```

#### Success Criteria

- [ ] `llm.py` split into `backends/` and `llm/`
- [ ] All 9 backends migrated
- [ ] Backend protocol defined
- [ ] Auto-detection from environment works
- [ ] All tests pass

---

### Phase 4: Group Export Formats

**Duration:** 3-4 days  
**Impact:** Medium - cleaner output handling  
**Risk:** Low - straightforward extraction

#### Goals

1. Organize `export.py` (1,516 lines) into `export/` package
2. Keep large but focused files (`callflow_html.py`, `tree_html.py`) as-is

#### Step-by-Step Instructions

##### Step 4.1: Create Export Package

```bash
mkdir -p graphify/export
touch graphify/export/__init__.py
touch graphify/export/json_graph.py
touch graphify/export/html.py
touch graphify/export/svg.py
touch graphify/export/obsidian.py
touch graphify/export/wiki.py
touch graphify/export/neo4j.py
touch graphify/export/falkordb.py
touch graphify/export/graphml.py
```

##### Step 4.2: Extract Export Functions

**Export Migration:**

| Function | Lines | Target File |
|----------|-------|-------------|
| `to_json()` | ~100 | `json_graph.py` |
| `to_html()` | ~400 | `html.py` |
| `to_svg()` | ~100 | `svg.py` |
| `to_obsidian()` | ~200 | `obsidian.py` |
| `to_wiki()` | ~150 | `wiki.py` |
| `_neo4j_cypher()` | ~100 | `neo4j.py` |
| `_falkordb_cypher()` | ~100 | `falkordb.py` |
| `to_canvas()` | ~100 | `graphml.py` |

##### Step 4.3: Move Large Files

```bash
# Keep as-is but move to export/
mv graphify/callflow_html.py graphify/export/callflow_html.py
mv graphify/tree_html.py graphify/export/tree_html.py
```

##### Step 4.4: Update Export Init

Create `graphify/export/__init__.py`:

```python
"""Output format exporters."""
from .json_graph import to_json
from .html import to_html
from .svg import to_svg
from .obsidian import to_obsidian
from .wiki import to_wiki
from .neo4j import to_neo4j_cypher
from .falkordb import to_falkordb_cypher

__all__ = [
    "to_json",
    "to_html",
    "to_svg",
    "to_obsidian",
    "to_wiki",
    "to_neo4j_cypher",
    "to_falkordb_cypher",
]
```

##### Step 4.5: Run Tests

```bash
uv run pytest tests/ -v
```

#### Success Criteria

- [ ] `export.py` split into `export/` modules
- [ ] `callflow_html.py` and `tree_html.py` moved to `export/`
- [ ] All export functions work as before
- [ ] All tests pass

---

### Phase 5: Organize Integrations

**Duration:** 3-4 days  
**Impact:** Medium - cleaner external dependencies  
**Risk:** Low - isolated code

#### Goals

1. Group external integrations into `integrations/` package
2. Split `serve.py` (1,319 lines) into MCP server + utilities

#### Step-by-Step Instructions

##### Step 5.1: Create Integrations Package

```bash
mkdir -p graphify/integrations
touch graphify/integrations/__init__.py
touch graphify/integrations/mcp_server.py
touch graphify/integrations/postgres.py
touch graphify/integrations/cargo.py
touch graphify/integrations/scip.py
```

##### Step 5.2: Move Existing Integrations

```bash
# Move existing integration files
mv graphify/google_workspace.py graphify/integrations/google_workspace.py
mv graphify/mcp_ingest.py graphify/integrations/mcp_ingest.py
mv graphify/pg_introspect.py graphify/integrations/postgres_introspect.py
mv graphify/cargo_introspect.py graphify/integrations/cargo_introspect.py
mv graphify/scip_ingest.py graphify/integrations/scip_ingest.py
```

##### Step 5.3: Split serve.py

Move MCP server logic to `integrations/mcp_server.py`:

```python
# graphify/integrations/mcp_server.py
"""MCP stdio/HTTP server for graph queries."""
from __future__ import annotations

# Move serve.py content here
# Keep only MCP-related code
# Move query logic to appropriate modules
```

##### Step 5.4: Run Tests

```bash
uv run pytest tests/ -v
```

#### Success Criteria

- [ ] All integrations in `integrations/` package
- [ ] MCP server extracted from `serve.py`
- [ ] All tests pass

---

### Phase 6: Create Core Package

**Duration:** 2-3 days  
**Impact:** Low - organizational clarity  
**Risk:** Very Low - just moving files

#### Goals

1. Group core pipeline modules into `core/` package
2. Make dependencies explicit

#### Step-by-Step Instructions

##### Step 6.1: Create Core Package

```bash
mkdir -p graphify/core
touch graphify/core/__init__.py
```

##### Step 6.2: Move Core Modules

```bash
mv graphify/detect.py graphify/core/detect.py
mv graphify/build.py graphify/core/build.py
mv graphify/cluster.py graphify/core/cluster.py
mv graphify/analyze.py graphify/core/analyze.py
mv graphify/report.py graphify/core/report.py
mv graphify/validate.py graphify/core/validate.py
mv graphify/security.py graphify/core/security.py
```

##### Step 6.3: Update Core Init

Create `graphify/core/__init__.py`:

```python
"""Core pipeline: detect → extract → build → cluster → analyze → report."""
from .detect import collect_files
from .build import build_graph, build_from_json
from .cluster import cluster, score_all
from .analyze import god_nodes, surprising_connections, suggest_questions
from .report import generate
from .validate import validate_extraction
from .security import validate_url, validate_path

__all__ = [
    "collect_files",
    "build_graph",
    "build_from_json",
    "cluster",
    "score_all",
    "god_nodes",
    "surprising_connections",
    "suggest_questions",
    "generate",
    "validate_extraction",
    "validate_url",
    "validate_path",
]
```

##### Step 6.4: Update Top-Level Init

Update `graphify/__init__.py` to re-export from new structure:

```python
"""graphify - extract · build · cluster · analyze · report."""

def __getattr__(name):
    _map = {
        # Core
        "collect_files": ("graphify.core.detect", "collect_files"),
        "build_graph": ("graphify.core.build", "build_graph"),
        "cluster": ("graphify.core.cluster", "cluster"),
        # Extractors
        "extract": ("graphify.extractors", "extract"),
        "extract_python": ("graphify.extractors.python", "extract_python"),
        # Export
        "to_json": ("graphify.export", "to_json"),
        "to_html": ("graphify.export", "to_html"),
        # ... etc
    }
    # ...
```

##### Step 6.5: Run Full Test Suite

```bash
uv run pytest tests/ -v
```

#### Success Criteria

- [ ] Core modules in `core/` package
- [ ] All imports still work via re-exports
- [ ] All tests pass
- [ ] No breaking changes

---

## Plugin Architecture (Future Enhancement)

After completing all phases, enable plugin architecture via Python entry points.

### Update pyproject.toml

```toml
[project.entry-points."graphify.extractors"]
python = "graphify.extractors.python:extract_python"
javascript = "graphify.extractors.javascript:extract_js"

[project.entry-points."graphify.backends"]
anthropic = "graphify.backends.anthropic:AnthropicBackend"
openai = "graphify.backends.openai:OpenAIBackend"

[project.entry-points."graphify.platforms"]
claude = "graphify.platforms.claude:ClaudeInstaller"
cursor = "graphify.platforms.cursor:CursorInstaller"
```

### External Plugin Example

Third-party packages can then register new extractors:

```python
# in my-custom-extractor package setup.py
[project.entry-points."graphify.extractors"]
mylang = "my_extractor:extract_mylang"
```

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing imports | Medium | High | Re-export everything from `__init__.py` |
| Test suite failures | Medium | High | Run full suite after each phase |
| Merge conflicts with upstream | High | Medium | Work on feature branch, rebase often |
| Performance regression | Low | Medium | Benchmark before/after each phase |
| Missing edge cases | Medium | Medium | Comprehensive test coverage per phase |

---

## Rollback Plan

If any phase causes major issues:

1. **Stop immediately** - don't proceed to next phase
2. **Revert to last passing commit** - `git reset --hard HEAD`
3. **Fix issues in isolation** - create test branch for debugging
4. **Re-run tests** before merging fix
5. **Document the issue** for future reference

---

## Timeline

| Week | Phase | Deliverables |
|------|-------|--------------|
| 1-2 | Phase 1 | Extractors package, all languages migrated |
| 3 | Phase 2 | CLI split, platforms extracted |
| 4 | Phase 3 | Backends + LLM orchestration separated |
| 5 | Phase 4 | Export formats organized |
| 6 | Phase 5 | Integrations grouped |
| 7 | Phase 6 | Core package created, final cleanup |
| 8 | Buffer | Testing, documentation, release prep |

---

## Success Metrics

After completing all phases:

| Metric | Before | After |
|--------|--------|-------|
| Largest file | 12,390 lines (`extract.py`) | <500 lines |
| Monolithic modules | 3 (`extract.py`, `__main__.py`, `llm.py`) | 0 |
| New extractor complexity | Edit 12K line file | Add single file |
| New backend complexity | Edit 2K line file | Add single file |
| New platform complexity | Edit 5K line file | Add single file |
| Test organization | Flat | Mirrors src structure |
| Plugin support | None | Entry points enabled |

---

## Next Steps

1. **Review this plan** with team/maintainers
2. **Create feature branch**: `git checkout -b refactor/modular-structure`
3. **Start Phase 1** - extract language extractors
4. **Commit after each step** for easy rollback
5. **Run tests continuously** throughout

Ready to begin Phase 1?


