"""Go predeclared functions must not bind to same-named user symbols.

`_LANGUAGE_BUILTIN_GLOBALS` covered JS/TS, Python and Swift (#726, #2147) but
not Go, while `graphify/extractors/go.py` already consults it when resolving a
callee. Because the Go resolver looks the callee up by bare name, an unexported
method that happens to share a builtin's name absorbed every builtin call in
the repository — the same phantom-edge shape those issues fixed for other
languages.

Observed on a real 8.9k-node Go codebase: a `func (h *metricHistory)
append(...)` method collected 330 phantom inbound `calls` edges from every
`append(slice, x)` in the project, which in turn invented twelve
database-layer -> service-layer edges (a layering violation that does not
exist in the source).
"""
import pytest

from graphify.extract import extract


def _nodes_by_file(result, suffix):
    return [n for n in result["nodes"] if str(n.get("source_file", "")).endswith(suffix)]


def _extract_go(tmp_path):
    return extract(sorted(tmp_path.glob("*.go")), cache_root=tmp_path, parallel=False)


@pytest.fixture
def builtin_shadow_repo(tmp_path):
    """A method named `append` in one file, builtin `append` calls in another."""
    (tmp_path / "history.go").write_text(
        "package main\n"
        "\n"
        "type metricHistory struct {\n"
        "\tsamples []int\n"
        "}\n"
        "\n"
        "func (h *metricHistory) append(v int) {\n"
        "\th.samples = append(h.samples, v)\n"
        "}\n"
    )
    (tmp_path / "worker.go").write_text(
        "package main\n"
        "\n"
        "func collect(values []int) []int {\n"
        "\tout := []int{}\n"
        "\tfor _, v := range values {\n"
        "\t\tout = append(out, v)\n"
        "\t}\n"
        "\treturn out\n"
        "}\n"
    )
    return tmp_path


def test_builtin_append_does_not_bind_to_user_method(builtin_shadow_repo):
    """A builtin `append` call must not create an edge to the user's method."""
    result = _extract_go(builtin_shadow_repo)
    method_ids = {
        n["id"] for n in _nodes_by_file(result, "history.go")
        if (n.get("label") or "").strip(".()") == "append"
    }
    assert method_ids, "the user's append method must still be extracted as a node"

    worker_ids = {n["id"] for n in _nodes_by_file(result, "worker.go")}
    phantom = [
        e for e in result["edges"]
        if e.get("target") in method_ids and e.get("source") in worker_ids
    ]
    assert phantom == [], (
        f"builtin append() in worker.go bound to the user method in history.go: {phantom}"
    )


def test_user_method_node_survives_the_filter(builtin_shadow_repo):
    """Filtering call targets must not delete the same-named user symbol."""
    result = _extract_go(builtin_shadow_repo)
    labels = {(n.get("label") or "").strip(".()") for n in _nodes_by_file(result, "history.go")}
    assert "append" in labels, (
        f"the user's append method disappeared from the graph; labels were {sorted(labels)}"
    )


def test_non_builtin_cross_file_call_still_resolves(tmp_path):
    """The guard is a no-op for genuine user symbols.

    Uses a plain package-level call: the Go resolver deliberately skips
    receiver method calls (`s.logger.Log()`) for lack of import evidence, so
    that shape would not prove anything about this filter.
    """
    (tmp_path / "engine.go").write_text(
        "package main\n"
        "\n"
        "func process(v int) int {\n"
        "\treturn v * 2\n"
        "}\n"
    )
    (tmp_path / "runner.go").write_text(
        "package main\n"
        "\n"
        "func run(v int) int {\n"
        "\treturn process(v)\n"
        "}\n"
    )
    result = _extract_go(tmp_path)
    target_ids = {
        n["id"] for n in _nodes_by_file(result, "engine.go")
        if (n.get("label") or "").strip(".()") == "process"
    }
    runner_ids = {n["id"] for n in _nodes_by_file(result, "runner.go")}
    resolved = [
        e for e in result["edges"]
        if e.get("target") in target_ids and e.get("source") in runner_ids
    ]
    assert resolved, "a genuine cross-file method call must still resolve"
