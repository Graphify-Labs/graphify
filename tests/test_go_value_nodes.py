"""Go package-level constants and variables must be nodes with inbound edges.

The Go extractor dispatched on four node types: function_declaration,
method_declaration, type_declaration and import_declaration. Go's grammar
also has const_declaration and var_declaration, so a package-level
constant never became a node, and reading one was not recorded as a
relation.

Observed on a 59-file Go codebase, using fifteen constants each read in
exactly one function: none of the fifteen constants was a node, while all
fifteen of the reading functions were. Asked "which function uses X", the
graph held the answer and offered no way in - every query returned "No
matching nodes found".

Three of those fifteen were read from a sibling file, which a per-file
extractor cannot bind. Those go through raw_value_refs and
_bind_cross_file_value_refs, the same split raw_calls already uses.
"""
import pytest

from graphify.extract import extract


def _extract_go(tmp_path):
    return extract(sorted(tmp_path.glob("*.go")), cache_root=tmp_path, parallel=False)


def _node_by_label(result, label):
    for n in result["nodes"]:
        if (n.get("label") or "").strip(".()") == label:
            return n
    return None


def _has_edge(result, src_label, tgt_label, relation):
    src = _node_by_label(result, src_label)
    tgt = _node_by_label(result, tgt_label)
    if src is None or tgt is None:
        return False
    return any(
        e.get("source") == src["id"]
        and e.get("target") == tgt["id"]
        and e.get("relation") == relation
        for e in result["edges"]
    )


@pytest.fixture
def same_file(tmp_path):
    (tmp_path / "sandbox.go").write_text(
        "package runtime\n"
        "\n"
        "const (\n"
        "\tsandboxProviderFD = 3\n"
        "\tmaxOutput         = 4096\n"
        ")\n"
        "\n"
        "var defaultTimeout = 30\n"
        "\n"
        "func bubblewrapArguments() []string {\n"
        "\t_ = sandboxProviderFD\n"
        "\treturn nil\n"
        "}\n"
    )
    return _extract_go(tmp_path)


def test_constants_become_nodes(same_file):
    for name in ("sandboxProviderFD", "maxOutput"):
        node = _node_by_label(same_file, name)
        assert node is not None, f"{name} is not a node"
        assert node.get("value_kind") == "const"


def test_package_variables_become_nodes(same_file):
    node = _node_by_label(same_file, "defaultTimeout")
    assert node is not None
    assert node.get("value_kind") == "var"


def test_reading_a_constant_is_an_edge(same_file):
    assert _has_edge(same_file, "bubblewrapArguments", "sandboxProviderFD", "references")


def test_unused_constant_has_no_reader(same_file):
    # maxOutput is declared and never read. A node, but nothing points at
    # it: the pass must not invent an edge for every name it walks past.
    assert not _has_edge(same_file, "bubblewrapArguments", "maxOutput", "references")


def test_constant_read_from_a_sibling_file(tmp_path):
    (tmp_path / "sandbox.go").write_text(
        "package runtime\n"
        "\n"
        "const sandboxProviderFD = 3\n"
    )
    (tmp_path / "plan.go").write_text(
        "package runtime\n"
        "\n"
        "func bubblewrapArguments() int {\n"
        "\treturn sandboxProviderFD\n"
        "}\n"
    )
    result = _extract_go(tmp_path)
    assert _has_edge(result, "bubblewrapArguments", "sandboxProviderFD", "references")


def test_local_variable_does_not_bind_to_a_constant(tmp_path):
    # A local shadowing a package constant of another file must not wire
    # the reader to it. The cross-file pass binds by name, so the guard
    # is that only declared package-level values are candidates.
    (tmp_path / "a.go").write_text(
        "package runtime\n"
        "\n"
        "func caller() int {\n"
        "\tnotAConstant := 7\n"
        "\treturn notAConstant\n"
        "}\n"
    )
    result = _extract_go(tmp_path)
    assert _node_by_label(result, "notAConstant") is None
