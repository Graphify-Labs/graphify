"""Optional language-server semantic evidence for Graphify graphs.

Graphify's native AST extraction remains the always-available baseline.  This
package adds bounded, local evidence from supported language servers. Providers
never replace or weaken native extraction.
"""

from .contracts import ProviderKind, ProviderRun, ProviderSpec, ProviderStatus
from .registry import ProviderRegistry, builtin_registry

__all__ = [
    "ProviderRegistry",
    "ProviderKind",
    "ProviderRun",
    "ProviderSpec",
    "ProviderStatus",
    "builtin_registry",
]
