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

The fix is Go-local (`_GO_PREDECLARED_FUNCS`) and applies only to bare-identifier
callees. The last two tests here are the reason: putting these names in the
shared set instead would kill in-file Rust `Type::new()` edges (`new` normalizes
to the same token) and drop genuine Go `h.append(v)` selector calls.
"""
import pytest

from graphify.extract import extract


def _nodes_by_file(result, suffix):
    return [n for n in result["nodes"] if str(n.get("source_file", "")).endswith(suffix)]


def _label(node):
    return (node.get("label") or "").strip(".()")


def _edges_between(result, source_ids, target_ids):
    return [
        e for e in result["edges"]
        if e.get("source") in source_ids and e.get("target") in target_ids
    ]


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


def test_builtin_append_does_not_bind_in_file(tmp_path):
    """Same-file binding needs the guard too, not just the cross-file pass.

    `walk_calls` resolves a bare callee against the file's own label index
    first, so a sibling function in the SAME file as the shadowing method binds
    without ever reaching `raw_calls`. Gating only the cross-file pass would
    leave this edge behind.
    """
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
        "\n"
        "func widen(xs []int) []int {\n"
        "\treturn append(xs, 0)\n"
        "}\n"
    )
    result = _extract_go(tmp_path)
    method_ids = {n["id"] for n in _nodes_by_file(result, "history.go") if _label(n) == "append"}
    widen_ids = {n["id"] for n in _nodes_by_file(result, "history.go") if _label(n) == "widen"}
    assert method_ids and widen_ids, "both symbols must still be extracted as nodes"

    phantom = _edges_between(result, widen_ids, method_ids)
    assert phantom == [], f"builtin append() in widen() bound to the method: {phantom}"


def test_go_selector_call_to_shadowing_method_survives(tmp_path):
    """`h.append(v)` is a real method call — the filter must not reach it.

    The callee is a `selector_expression`, not a bare identifier. Filtering by
    name alone (the shared-set approach) drops this genuine edge.
    """
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
        "\n"
        "func record(h *metricHistory, v int) {\n"
        "\th.append(v)\n"
        "}\n"
    )
    result = _extract_go(tmp_path)
    method_ids = {n["id"] for n in _nodes_by_file(result, "history.go") if _label(n) == "append"}
    record_ids = {n["id"] for n in _nodes_by_file(result, "history.go") if _label(n) == "record"}
    assert method_ids and record_ids, "both symbols must still be extracted as nodes"

    resolved = _edges_between(result, record_ids, method_ids)
    assert resolved, "a genuine h.append(v) selector call must still resolve"


def test_rust_in_file_type_new_edge_survives(tmp_path):
    """Cross-language guard: `new` must stay resolvable in Rust.

    Rust normalizes `Widget::new(3)` to the bare token `new`, and the
    builtin check wraps the in-file EXTRACTED branch as well as `raw_calls`.
    Adding Go's predeclared names to the shared `_LANGUAGE_BUILTIN_GLOBALS`
    therefore erased every in-file `Type::new()` edge in a Rust codebase —
    which is why `_GO_PREDECLARED_FUNCS` is Go-local. Rust keeps its own
    `_RUST_TRAIT_METHOD_BLOCKLIST`, deliberately applied to the cross-file
    branch only.
    """
    (tmp_path / "lib.rs").write_text(
        "pub struct Widget { n: i32 }\n"
        "\n"
        "impl Widget {\n"
        "    pub fn new(n: i32) -> Widget { Widget { n } }\n"
        "}\n"
        "\n"
        "pub fn build() -> Widget {\n"
        "    Widget::new(3)\n"
        "}\n"
    )
    result = extract(sorted(tmp_path.glob("*.rs")), cache_root=tmp_path, parallel=False)
    new_ids = {n["id"] for n in _nodes_by_file(result, "lib.rs") if _label(n) == "new"}
    build_ids = {n["id"] for n in _nodes_by_file(result, "lib.rs") if _label(n) == "build"}
    assert new_ids and build_ids, "both symbols must still be extracted as nodes"

    resolved = _edges_between(result, build_ids, new_ids)
    assert resolved, "an in-file Rust Type::new() call must still resolve"
