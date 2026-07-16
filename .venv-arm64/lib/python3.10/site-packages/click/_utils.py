from __future__ import annotations

import enum
import typing as t


class Sentinel(enum.Enum):
    """Enum used to define sentinel values.

    .. seealso::

        `PEP 661 - Sentinel Values <https://peps.python.org/pep-0661/>`_.
    """

    UNSET = object()
    FLAG_NEEDS_VALUE = object()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}.{self.name}"


UNSET: t.Literal[Sentinel.UNSET] = Sentinel.UNSET
"""Sentinel used to indicate that a value is not set."""

FLAG_NEEDS_VALUE: t.Literal[Sentinel.FLAG_NEEDS_VALUE] = Sentinel.FLAG_NEEDS_VALUE
"""Sentinel used to indicate an option was passed as a flag without a
value but is not a flag option.

``Option.consume_value`` uses this to prompt or use the ``flag_value``.
"""

T_UNSET: t.TypeAlias = t.Literal[Sentinel.UNSET]
"""Type hint for the :data:`UNSET` sentinel value."""

T_FLAG_NEEDS_VALUE: t.TypeAlias = t.Literal[Sentinel.FLAG_NEEDS_VALUE]
"""Type hint for the :data:`FLAG_NEEDS_VALUE` sentinel value."""
