# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Max Bachmann
from __future__ import annotations

__all__ = ["AVX2", "SSE2", "supports"]

try:
    from rapidfuzz._feature_detector_cpp import AVX2, SSE2, supports
except ImportError:
    SSE2 = 1
    AVX2 = 2

    def supports(features):
        _ = features
        return False
