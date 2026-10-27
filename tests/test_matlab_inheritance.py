"""The pure repository-source MATLAB inheritance contract (issue #4)."""
from copy import deepcopy

import pytest

from graphify.extractors.resolution import _matlab_inheritance_edges


def _class(source, name, *, namespace="", bases=(), repo=None):
    common = {"file_type": "code", "source_file": source}
    if repo is not None:
        common["repo"] = repo
    prefix = f"{repo}::" if repo is not None else ""
    return [
        {
            **common,
            "id": f"{prefix}{source}:file",
            "label": source,
            "metadata": {
                "language": "matlab",
                "kind": "matlab_file",
                "namespace": namespace,
                "matlab_file_kind": "class",
                "matlab_primary_name": name,
            },
        },
        {
            **common,
            "id": f"{prefix}{source}:class:{name}",
            "label": name,
            "source_location": "L1",
            "metadata": {
                "language": "matlab",
                "kind": "matlab_class",
                "namespace": namespace,
                "scope_chain": [],
                "matlab_superclasses": [
                    {"name": base, "source_location": f"L{row}"}
                    for row, base in enumerate(bases, start=2)
                ],
            },
        },
    ]


def test_exact_source_matches_preserve_written_bases_and_input_records():
    nodes = (
        _class("src/Child.m", "Child", bases=("tools.io.Base", "Sibling", "handle"))
        + _class("lib/+tools/+io/Base.m", "Base", namespace="tools.io")
        + _class("src/Sibling.m", "Sibling")
    )
    original = deepcopy(nodes)

    assert _matlab_inheritance_edges(nodes) == [
        {
            "source": "src/Child.m:class:Child",
            "target": "lib/+tools/+io/Base.m:class:Base",
            "relation": "inherits",
            "confidence": "EXTRACTED",
            "source_file": "src/Child.m",
            "source_location": "L2",
            "weight": 1.0,
        },
        {
            "source": "src/Child.m:class:Child",
            "target": "src/Sibling.m:class:Sibling",
            "relation": "inherits",
            "confidence": "EXTRACTED",
            "source_file": "src/Child.m",
            "source_location": "L3",
            "weight": 1.0,
        },
    ]
    assert nodes == original


@pytest.mark.parametrize(
    ("child_path", "child_namespace", "base_path", "base_namespace", "written"),
    [
        ("Child.m", "", "elsewhere/Base.m", "", "Base"),
        ("Child.m", "", "+pkg/Base.m", "pkg", "Base"),
        ("+pkg/Child.m", "pkg", "+pkg/Base.m", "pkg", "Base"),
        ("Child.m", "", "+pkg/Base.m", "pkg", "pkg.base"),
        ("Child.m", "", "+pkg/Base.m", "pkg", "Pkg.Base"),
        ("Child.m", "", "base.m", "", "Base"),
        ("Child.m", "", "private/+pkg/Base.m", "pkg", "pkg.Base"),
        ("Child.m", "", "+pkg/@Base/Base.m", "", "pkg.Base"),
        ("@Child/Child.m", "", "+pkg/Base.m", "pkg", "pkg.Base"),
        ("private/Child.m", "", "+pkg/Base.m", "pkg", "pkg.Base"),
        ("Child.m", "", "+outer/ordinary/+pkg/Base.m", "pkg", "outer.pkg.Base"),
        ("Child.m", "", "+bad-name/Base.m", "bad-name", "bad-name.Base"),
        ("Child.m", "", "Base.M", "", "Base"),
    ],
)
def test_only_exact_namespace_or_unpacked_sibling_matches(
    child_path, child_namespace, base_path, base_namespace, written
):
    nodes = _class(child_path, "Child", namespace=child_namespace, bases=(written,))
    nodes += _class(base_path, "Base", namespace=base_namespace)
    assert _matlab_inheritance_edges(nodes) == []


def test_namespace_chain_stops_at_ordinary_directory():
    nodes = _class("Child.m", "Child", bases=("pkg.Base",))
    nodes += _class("+outer/ordinary/+pkg/Base.m", "Base", namespace="pkg")
    edges = _matlab_inheritance_edges(nodes)
    assert [(edge["source"], edge["target"]) for edge in edges] == [
        ("Child.m:class:Child", "+outer/ordinary/+pkg/Base.m:class:Base")
    ]


def test_duplicate_package_roots_and_class_declarations_are_ambiguous():
    nodes = _class("Child.m", "Child", bases=("pkg.Base", "Sibling"))
    nodes += _class("one/+pkg/Base.m", "Base", namespace="pkg")
    nodes += _class("two/+pkg/Base.m", "Base", namespace="pkg")
    nodes += _class("Sibling.m", "Sibling")
    duplicate = deepcopy(nodes[-1])
    duplicate["id"] += ":L10"
    duplicate["source_location"] = "L10"
    nodes.append(duplicate)
    assert _matlab_inheritance_edges(nodes) == []


@pytest.mark.parametrize(
    ("record", "field", "value"),
    [
        (0, "matlab_file_kind", "script"),
        (0, "matlab_primary_name", "Other"),
        (0, "namespace", "other"),
        (1, "namespace", "other"),
        (1, "scope_chain", ["Owner"]),
        (1, "scope_chain", None),
        (1, "language", "objc"),
    ],
)
def test_uncertain_primary_class_context_is_not_a_target(record, field, value):
    child = _class("Child.m", "Child", bases=("pkg.Base",))
    base = _class("+pkg/Base.m", "Base", namespace="pkg")
    base[record]["metadata"][field] = value
    assert _matlab_inheritance_edges(child + base) == []


def test_missing_file_context_and_filename_declaration_mismatch_fail_closed():
    child = _class("Child.m", "Child", bases=("Base",))
    base = _class("Base.m", "Base")
    assert _matlab_inheritance_edges(child + base[1:]) == []
    assert _matlab_inheritance_edges(child + _class("Base.m", "Other")) == []
    assert _matlab_inheritance_edges(child + _class("Other.m", "Base")) == []


def test_malformed_duplicate_package_root_cannot_make_another_root_unique():
    nodes = _class("Child.m", "Child", bases=("pkg.Base",))
    nodes += _class("one/+pkg/Base.m", "Base", namespace="pkg")
    nodes += _class("two/+pkg/Base.m", "Wrong", namespace="pkg")
    assert _matlab_inheritance_edges(nodes) == []


def test_self_inheritance_and_unsupported_or_external_references_stay_metadata():
    nodes = _class(
        "+pkg/Child.m", "Child", namespace="pkg",
        bases=("pkg.Child", "handle", "matlab.mixin.Copyable", "pkg.Base(x)", "pkg..Base", " pkg.Base"),
    )
    nodes[-1]["metadata"]["matlab_superclasses"].extend([
        {"raw": "pkg.Base{T}", "source_location": "L9"},
        {"name": "pkg.Base", "source_location": None},
        {"name": "pkg.Base", "source_location": "L0"},
        {"name": None, "source_location": "L12"},
        None,
    ])
    nodes += _class("+pkg/Base.m", "Base", namespace="pkg")
    original = deepcopy(nodes)
    assert _matlab_inheritance_edges(nodes) == []
    assert nodes == original


def test_external_spelling_can_match_a_real_eligible_repository_class():
    nodes = _class("Child.m", "Child", bases=("handle", "matlab.mixin.Copyable"))
    nodes += _class("handle.m", "handle")
    nodes += _class("+matlab/+mixin/Copyable.m", "Copyable", namespace="matlab.mixin")
    assert [edge["target"] for edge in _matlab_inheritance_edges(nodes)] == [
        "handle.m:class:handle", "+matlab/+mixin/Copyable.m:class:Copyable",
    ]


def test_repository_tags_partition_identical_source_paths_and_namespaces():
    nodes = []
    for repo in (None, "one", "two"):
        nodes += _class("Child.m", "Child", bases=("pkg.Base", "Base"), repo=repo)
        nodes += _class("+pkg/Base.m", "Base", namespace="pkg", repo=repo)
        nodes += _class("Base.m", "Base", repo=repo)
    edges = _matlab_inheritance_edges(nodes)
    assert {(edge["source"], edge["target"]) for edge in edges} == {
        ("Child.m:class:Child", "+pkg/Base.m:class:Base"),
        ("Child.m:class:Child", "Base.m:class:Base"),
        ("one::Child.m:class:Child", "one::+pkg/Base.m:class:Base"),
        ("one::Child.m:class:Child", "one::Base.m:class:Base"),
        ("two::Child.m:class:Child", "two::+pkg/Base.m:class:Base"),
        ("two::Child.m:class:Child", "two::Base.m:class:Base"),
    }
    assert _matlab_inheritance_edges(list(reversed(nodes))) == edges
    assert _matlab_inheritance_edges(nodes[3:] + nodes[:3]) == edges


def test_foreign_repository_and_untagged_candidates_cannot_fill_missing_bases():
    nodes = _class("Child.m", "Child", bases=("pkg.Base", "Base"), repo="child")
    nodes += _class("+pkg/Base.m", "Base", namespace="pkg", repo="foreign")
    nodes += _class("Base.m", "Base")
    assert _matlab_inheritance_edges(nodes) == []


def test_nonsource_nodes_cannot_supply_class_targets():
    child = _class("Child.m", "Child", bases=("Base",))
    for field, value in (
        ("external", True), ("file_type", "document"), ("id", None),
        ("metadata.kind", "matlab_function"),
    ):
        base = _class("Base.m", "Base")
        if field == "metadata.kind":
            base[-1]["metadata"]["kind"] = value
        else:
            base[-1][field] = value
        assert _matlab_inheritance_edges(child + base) == []


def test_non_file_nodes_cannot_establish_source_context():
    child = _class("Child.m", "Child", bases=("Base",))
    base = _class("Base.m", "Base")
    base[0]["metadata"]["kind"] = "matlab_class"
    assert _matlab_inheritance_edges(child + base) == []


