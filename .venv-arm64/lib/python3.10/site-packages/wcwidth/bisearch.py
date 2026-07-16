"""Binary search function for Unicode interval tables."""

from __future__ import annotations


def bisearch(ucs: int, table: tuple[tuple[int, int], ...]) -> int:
    """
    Binary search in interval table.

    :param ucs: Ordinal value of unicode character.
    :param table: Tuple of starting and ending ranges of ordinal values, in form of ``((start, end),
        ...)``.
    :returns: 1 if ordinal value ucs is found within lookup table, else 0.
    """
    lbound = 0
    ubound = len(table) - 1

    if ucs < table[0][0] or ucs > table[ubound][1]:
        return 0

    while ubound >= lbound:
        mid = (lbound + ubound) // 2
        if ucs > table[mid][1]:
            lbound = mid + 1
        elif ucs < table[mid][0]:
            ubound = mid - 1
        else:
            return 1

    return 0
