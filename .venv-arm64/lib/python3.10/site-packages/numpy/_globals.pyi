__all__ = ["_CopyMode", "_NoValue"]

import enum
from typing import Final, final

@final
class _CopyMode(enum.Enum):
    ALWAYS = True
    NEVER = False
    IF_NEEDED = 2

    def __bool__(self, /) -> bool: ...

@final
class _NoValueType: ...

_NoValue: Final[_NoValueType] = ...
