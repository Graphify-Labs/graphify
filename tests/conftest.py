from __future__ import annotations

import os
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


@pytest.fixture(autouse=True, scope="session")
def _isolate_graphify_query_log():
    """Keep the test suite out of the developer's real query log.

    CLI-level tests (test_explain_cli.py and friends) call
    graphify.__main__.main() directly, which appends one real record per
    invocation to ~/.cache/graphify-queries.log (or $GRAPHIFY_QUERY_LOG) —
    querylog.py has no test-awareness. Disabling logging for the whole test
    session, rather than backing up and restoring the log file around the
    run, avoids a crash-safety gap: if the test process is killed mid-run
    (Ctrl-C, a CI timeout, OOM), a restore step might never fire and the
    developer's real log would be left clobbered or missing. Disabling never
    touches the file at all, so there's nothing to restore.
    """
    prior = os.environ.get("GRAPHIFY_QUERY_LOG_DISABLE")
    os.environ["GRAPHIFY_QUERY_LOG_DISABLE"] = "1"
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop("GRAPHIFY_QUERY_LOG_DISABLE", None)
        else:
            os.environ["GRAPHIFY_QUERY_LOG_DISABLE"] = prior
