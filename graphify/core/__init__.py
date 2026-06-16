"""Core pipeline for graphify.

Provides the main processing pipeline:
detect → extract → build → cluster → analyze → report
"""

# Re-export from original modules for backward compatibility
from ..detect import collect_files
from ..build import build_graph, build_from_json
from ..cluster import cluster, score_all
from ..analyze import god_nodes, surprising_connections, suggest_questions
from ..report import generate
from ..validate import validate_extraction
from ..security import validate_url, validate_path

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
