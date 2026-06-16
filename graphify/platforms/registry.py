"""Platform registry - maps platform names to installers."""

from __future__ import annotations

from pathlib import Path
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
        raise ValueError(f"Unknown platform: {name}. Available: {', '.join(get_all_platforms())}")
    return _REGISTRY[name]()


def get_all_platforms() -> list[str]:
    """Get all registered platform names."""
    return list(_REGISTRY.keys())


def is_registered(name: str) -> bool:
    """Check if a platform is registered."""
    return name in _REGISTRY
