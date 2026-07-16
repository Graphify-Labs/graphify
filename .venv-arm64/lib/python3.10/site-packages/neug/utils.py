#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2020 Alibaba Group Holding Limited. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from typing import Final


def readable(mode: str) -> str:
    """Convert mode to a readable string."""
    if mode in ["r", "read", "read-only", "read_only"]:
        return "read-only"
    elif mode in ["w", "rw", "write", "readwrite", "read-write", "read_write"]:
        return "read-write"
    else:
        raise ValueError(
            f"Invalid mode: {mode}. Must be one of 'r', 'read', 'w', 'rw', 'write', 'readwrite'."
        )


valid_access_modes: Final = ["read", "r", "insert", "i", "update", "u", "schema", "s"]


def is_access_mode_valid(mode: str) -> bool:
    """Check if the access mode is valid."""
    return mode in valid_access_modes
