# SPDX-License-Identifier: MIT
# Copyright (C) 2023 Max Bachmann

from __future__ import annotations

from array import array
from collections.abc import Hashable, Sequence


def conv_sequence(s: Sequence[Hashable]) -> Sequence[Hashable]:
    if isinstance(s, str):
        return [ord(x) for x in s]

    if isinstance(s, bytes):
        return s

    if isinstance(s, array):
        if s.typecode in ("u", "w"):
            return [ord(x) for x in s]

        return s

    if s is None:
        return s

    res = []
    for elem in s:
        if isinstance(elem, str) and len(elem) == 1:
            res.append(ord(elem))
        elif isinstance(elem, int) and elem == -1:
            res.append(-1)
        else:
            res.append(hash(elem))

    return res


def conv_sequences(s1: Sequence[Hashable], s2: Sequence[Hashable]) -> tuple[Sequence[Hashable], Sequence[Hashable]]:
    if isinstance(s1, str) and isinstance(s2, str):
        return s1, s2

    if isinstance(s1, bytes) and isinstance(s2, bytes):
        return s1, s2

    return conv_sequence(s1), conv_sequence(s2)


def common_prefix(s1: Sequence[Hashable], s2: Sequence[Hashable]) -> int:
    prefix_len = 0
    for ch1, ch2 in zip(s1, s2):
        if ch1 != ch2:
            break

        prefix_len += 1

    return prefix_len


def common_suffix(s1: Sequence[Hashable], s2: Sequence[Hashable]) -> int:
    suffix_len = 0
    for ch1, ch2 in zip(reversed(s1), reversed(s2)):
        if ch1 != ch2:
            break

        suffix_len += 1

    return suffix_len


def common_affix(s1: Sequence[Hashable], s2: Sequence[Hashable]) -> tuple[int, int]:
    prefix_len = common_prefix(s1, s2)
    suffix_len = common_suffix(s1[prefix_len:], s2[prefix_len:])
    return (prefix_len, suffix_len)
