"""Integrations with external systems.

Provides connectors for MCP, databases, cloud services, etc.
"""

# Re-export from original modules for backward compatibility
from ..cargo_introspect import extract_cargo_workspace
from ..google_workspace import extract_google_docs
from ..mcp_ingest import extract_mcp_config
from ..scip_ingest import extract_scip_index

__all__ = [
    "extract_cargo_workspace",
    "extract_google_docs",
    "extract_mcp_config",
    "extract_scip_index",
]
