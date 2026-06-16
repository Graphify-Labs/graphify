"""Platform installer base classes and protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class PlatformInstaller(Protocol):
    """Protocol for platform installers."""

    @property
    def name(self) -> str:
        """Platform name (e.g., 'claude', 'cursor')."""
        ...

    def install(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        """Install graphify for this platform."""
        ...

    def uninstall(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        """Uninstall graphify from this platform."""
        ...


class BasePlatformInstaller(ABC):
    """Base class for platform installers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Platform name."""
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
