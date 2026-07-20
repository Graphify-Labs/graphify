"""Validated public-SDK boundary for Graphify's embedded Helix runtime."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import importlib.metadata
from pathlib import Path
from typing import Any

import helixdb


HELIX_PACKAGE_INDEX = "https://pypi.org/project/helix-db/0.2.0b3/"
HELIX_PYTHON_VERSION = "0.2.0b3"
HELIX_EMBEDDED_DISTRIBUTION = "helix-db-embedded"
HELIX_EMBEDDED_VERSION = "0.2.0b3"
_DATABASE_NAME = "graphify"


class NativeBackendUnavailable(RuntimeError):
    """Raised when the pinned embedded Helix SDK cannot be loaded safely."""


@dataclass(frozen=True)
class NativeBackendInfo:
    module: str
    version: str | None
    embedded_version: str


@dataclass(frozen=True)
class _NativeSurface:
    helixdb_attrs: frozenset[str]


_REQUIRED = _NativeSurface(
    helixdb_attrs=frozenset(
        {
            "Client",
            "Disk",
            "NodeRef",
            "ShortestPathDirection",
            "SourcePredicate",
            "g",
            "read_batch",
            "write_batch",
            "GraphSelection",
            "GraphMetadataSelection",
            "IdentitySelection",
            "GraphEdgeId",
            "LeidenOptions",
            "NativeGraph",
        }
    ),
)


@lru_cache(maxsize=1)
def validate_native_backend() -> None:
    """Validate the statically imported public SDK and matching embedded wheel."""
    try:
        version = importlib.metadata.version("helix-db")
    except importlib.metadata.PackageNotFoundError:
        version = None
    if version != HELIX_PYTHON_VERSION:
        raise NativeBackendUnavailable(
            "embedded Helix SDK version mismatch: "
            f"expected {HELIX_PYTHON_VERSION}, got {version!r}"
        )

    missing = sorted(name for name in _REQUIRED.helixdb_attrs if not hasattr(helixdb, name))
    if missing:
        raise NativeBackendUnavailable(
            "helixdb is missing required public embedded SDK APIs: "
            f"{', '.join(missing)}"
        )
    try:
        embedded_version = importlib.metadata.version(HELIX_EMBEDDED_DISTRIBUTION)
    except importlib.metadata.PackageNotFoundError as exc:
        raise NativeBackendUnavailable(
            f"{HELIX_EMBEDDED_DISTRIBUTION}=={HELIX_EMBEDDED_VERSION} is required "
            "for embedded Helix storage"
        ) from exc
    if embedded_version != HELIX_EMBEDDED_VERSION:
        raise NativeBackendUnavailable(
            "embedded Helix payload version mismatch: "
            f"expected {HELIX_EMBEDDED_VERSION}, got {embedded_version!r}"
        )


def native_backend_info() -> NativeBackendInfo:
    validate_native_backend()
    return NativeBackendInfo(
        module=helixdb.__name__,
        version=importlib.metadata.version("helix-db"),
        embedded_version=importlib.metadata.version(HELIX_EMBEDDED_DISTRIBUTION),
    )


def open_embedded_client(path: str | Path, *, read_only: bool = False) -> Any:
    """Open the official in-process, on-disk Helix client at ``path``."""
    validate_native_backend()
    root = Path(path)
    if read_only:
        if not root.is_dir():
            raise FileNotFoundError(f"embedded Helix store not found: {root}")
    else:
        root.mkdir(parents=True, exist_ok=True)
    source = helixdb.Disk(str(root.resolve()), _DATABASE_NAME)
    if read_only:
        return helixdb.Client.embedded_reader(source)
    return helixdb.Client.embedded(source)


__all__ = [
    "HELIX_PACKAGE_INDEX",
    "HELIX_PYTHON_VERSION",
    "HELIX_EMBEDDED_DISTRIBUTION",
    "HELIX_EMBEDDED_VERSION",
    "NativeBackendInfo",
    "NativeBackendUnavailable",
    "native_backend_info",
    "open_embedded_client",
    "validate_native_backend",
]
