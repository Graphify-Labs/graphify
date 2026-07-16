from collections.abc import Sequence
from typing import SupportsIndex, TypeAlias

_Shape: TypeAlias = tuple[int, ...]

# Anything that can be coerced to a shape tuple
_ShapeLike: TypeAlias = SupportsIndex | Sequence[SupportsIndex]
