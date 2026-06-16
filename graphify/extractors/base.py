"""Base extractor class and protocol definition."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Extractor(Protocol):
    """Protocol for language extractors.

    Any object with a `extract(path: Path) -> dict` method is a valid extractor.
    """

    def extract(self, path: Path) -> dict: ...


class BaseExtractor(ABC):
    """Base class for extractors with common utilities."""

    @property
    @abstractmethod
    def extensions(self) -> set[str]:
        """File extensions this extractor handles (e.g., {'.py', '.pyw'})."""
        ...

    @abstractmethod
    def extract(self, path: Path) -> dict:
        """Extract nodes and edges from a source file.

        Returns:
            dict with keys:
                - nodes: list[dict] - each with id, label, source_file, source_location
                - edges: list[dict] - each with source, target, relation, confidence
                - error: str | None - error message if extraction failed
        """
        ...
