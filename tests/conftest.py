from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

_ANALYZE_WARNING_FILTERS = (
    "ignore:Tensorflow not installed; ParametricUMAP will be unavailable:ImportWarning:umap",
    "ignore:Please import `random` from the `scipy\\.sparse` namespace.*:"
    "DeprecationWarning:hyppo\\.independence\\.hhg",
    "ignore:The keyword argument 'nopython=False' was supplied.*:Warning:numba\\.core\\.decorators",
)


def pytest_collection_modifyitems(items: list[Any]) -> None:
    for item in items:
        if item.path.name != "test_analyze.py":
            continue
        for warning_filter in _ANALYZE_WARNING_FILTERS:
            item.add_marker(pytest.mark.filterwarnings(warning_filter))


@pytest.fixture
def package_root() -> Path:
    """Absolute path to the graphify package source root.

    Used by bundled_skills tests to assert that BundledSkill.source_subpath
    entries point at real files (independent of `importlib.resources` which
    only sees installed packages).
    """
    import graphify
    return Path(graphify.__file__).parent.resolve()
