"""Small, stable contracts shared by semantic provider plugins."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class ProviderKind(str, Enum):
    """Evidence class emitted by a provider run."""

    SEMANTIC = "semantic"


class ProviderStatus(str, Enum):
    """A provider outcome that never silently erases the AST baseline."""

    COMPLETED = "completed"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass(frozen=True)
class ProviderSpec:
    """Trusted execution and language metadata for one provider plugin.

    ``command`` is an argv tuple, not a shell command.  Custom manifests are an
    operator-trusted boundary because they choose an executable.
    """

    name: str
    languages: tuple[str, ...]
    extensions: tuple[str, ...]
    command: tuple[str, ...]
    binary_env: str
    project_markers: tuple[str, ...] = ()
    initialization_options: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name or not self.command or not self.command[0]:
            raise ValueError("provider name and command are required")
        if not self.languages or not self.extensions:
            raise ValueError("provider languages and extensions are required")
        if any(not suffix.startswith(".") for suffix in self.extensions):
            raise ValueError("provider extensions must begin with '.'")


@dataclass
class ProviderRun:
    """Graphify-compatible evidence fragment plus explicit bounded status."""

    provider: str
    status: ProviderStatus
    provider_kind: ProviderKind = ProviderKind.SEMANTIC
    version: str = "unknown"
    run_id: str = field(default_factory=lambda: f"provider-{uuid4().hex}")
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    files_considered: int = 0
    files_processed: int = 0
    requests: int = 0
    relationship_requests: int = 0
    reason_code: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["status"] = self.status.value
        result["provider_kind"] = self.provider_kind.value
        return result
