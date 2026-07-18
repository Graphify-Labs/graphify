"""Contract and loader for Graphify's pinned Helix Python SDK + native payload."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import importlib
import importlib.metadata
from pathlib import Path
from types import ModuleType
from typing import Any


HELIX_REPOSITORY = "https://github.com/HelixDB/helix-db"
HELIX_PYTHON_VERSION = "0.2.0b1"
HELIX_EMBEDDED_DISTRIBUTION = "helix-db-embedded"
HELIX_EMBEDDED_VERSION = "0.2.0b1"
NATIVE_MODULE_NAME = "helixdb"
NATIVE_PAYLOAD_NAME = "helixdb_uniffi"
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
    uniffi_attrs: frozenset[str]


_REQUIRED = _NativeSurface(
    helixdb_attrs=frozenset(
        {
            "Client",
            "Disk",
            "IndexSpec",
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
    uniffi_attrs=frozenset(
        {
            "HelixDb",
            "NativeGraphLoadSpec",
            "NativeGraphKind",
            "NativeExternalId",
            "NativeEdgeId",
            "NativeTraversalDirection",
            "NativeBetweennessOptions",
            "NativeTraversalOptions",
            "graph_from_query_response",
        }
    ),
)


@lru_cache(maxsize=1)
def load_native_module() -> ModuleType:
    """Load and validate the pinned Helix SDK plus embedded native payload."""
    try:
        module = importlib.import_module(NATIVE_MODULE_NAME)
    except Exception as exc:
        raise NativeBackendUnavailable(
            f"{NATIVE_MODULE_NAME} is required for embedded Helix storage: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    version = getattr(module, "__version__", None)
    if version is None:
        try:
            version = importlib.metadata.version("helix-db")
        except importlib.metadata.PackageNotFoundError:
            version = None
    if version != HELIX_PYTHON_VERSION:
        raise NativeBackendUnavailable(
            "embedded Helix SDK version mismatch: "
            f"expected {HELIX_PYTHON_VERSION}, got {version!r}"
        )

    missing = sorted(name for name in _REQUIRED.helixdb_attrs if not hasattr(module, name))
    if missing:
        raise NativeBackendUnavailable(
            f"{NATIVE_MODULE_NAME} is missing required embedded SDK APIs: "
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
    try:
        payload = importlib.import_module(NATIVE_PAYLOAD_NAME)
    except Exception as exc:
        raise NativeBackendUnavailable(
            "native embedded Helix payload is unavailable: "
            f"{type(exc).__name__}: {exc}. "
            f"Install {HELIX_EMBEDDED_DISTRIBUTION}=={HELIX_EMBEDDED_VERSION}."
        ) from exc
    native_missing = sorted(
        name for name in _REQUIRED.uniffi_attrs if not hasattr(payload, name)
    )
    if native_missing:
        raise NativeBackendUnavailable(
            "native Helix payload does not implement graphify-native-graph: "
            + ", ".join(native_missing)
        )
    return module


def native_backend_info() -> NativeBackendInfo:
    module = load_native_module()
    version = getattr(module, "__version__", None)
    if version is None:
        version = importlib.metadata.version("helix-db")
    return NativeBackendInfo(
        module=module.__name__,
        version=version,
        embedded_version=importlib.metadata.version(HELIX_EMBEDDED_DISTRIBUTION),
    )


def open_embedded_client(path: str | Path, *, read_only: bool = False) -> Any:
    """Open the official in-process, on-disk Helix client at ``path``."""
    module = load_native_module()
    root = Path(path)
    if read_only:
        if not root.is_dir():
            raise FileNotFoundError(f"embedded Helix store not found: {root}")
    else:
        root.mkdir(parents=True, exist_ok=True)
    source = module.Disk(str(root.resolve()), _DATABASE_NAME)
    if read_only:
        return module.Client.embedded_reader(source)
    return module.Client.embedded(source)


__all__ = [
    "HELIX_REPOSITORY",
    "HELIX_PYTHON_VERSION",
    "HELIX_EMBEDDED_DISTRIBUTION",
    "HELIX_EMBEDDED_VERSION",
    "NATIVE_MODULE_NAME",
    "NATIVE_PAYLOAD_NAME",
    "NativeBackendInfo",
    "NativeBackendUnavailable",
    "load_native_module",
    "native_backend_info",
    "open_embedded_client",
]
