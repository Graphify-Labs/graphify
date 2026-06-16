"""HTML export utilities."""
from __future__ import annotations


def _html_styles() -> str:
    """Return CSS styles for HTML export."""
    return """
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif; }
.node { fill: #6366f1; stroke: #4f46e5; stroke-width: 2px; }
.edge { stroke: #94a3b8; stroke-width: 1.5px; }
.label { font-size: 12px; fill: #1e293b; }
</style>
"""


def _viz_node_limit() -> int:
    """Return max nodes for visualization."""
    return 500
