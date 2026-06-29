from __future__ import annotations

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


@pytest.fixture(autouse=True)
def isolate_graphify_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Keep developer-wide ~/.graphify credentials from changing backend tests."""
    monkeypatch.setenv("GRAPHIFY_CREDENTIALS_PATH", str(tmp_path / "credentials.json"))

@pytest.fixture(autouse=True)
def isolate_git_global_config(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Keep developer-wide git config (for example core.hooksPath) out of tests."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
