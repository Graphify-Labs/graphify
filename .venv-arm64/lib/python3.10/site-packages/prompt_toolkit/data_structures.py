from __future__ import annotations

from typing import NamedTuple

__all__ = [
    "Point",
    "Size",
]


class Point(NamedTuple):
    x: int
    y: int


class Size(NamedTuple):
    rows: int
    columns: int
