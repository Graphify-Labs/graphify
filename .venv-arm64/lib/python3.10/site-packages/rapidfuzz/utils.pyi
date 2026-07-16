# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Max Bachmann

from __future__ import annotations

from collections.abc import Hashable, Sequence
from typing import TypeVar

_StringType = TypeVar("_StringType", bound=Sequence[Hashable])

def default_process(sentence: _StringType) -> _StringType: ...
