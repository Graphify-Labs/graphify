"""Regression coverage for import-aware Python inheritance resolution (#2736)."""

from __future__ import annotations

from pathlib import Path

from graphify.build import build_from_json
from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _real_node(result: dict, label: str, source_suffix: str | None = None) -> dict:
    matches = [
        node
        for node in result["nodes"]
        if node.get("label") == label
        and node.get("source_file")
        and (
            source_suffix is None
            or str(node.get("source_file", "")).endswith(source_suffix)
        )
    ]
    assert len(matches) == 1, [
        (node.get("id"), node.get("source_file"))
        for node in result["nodes"]
        if node.get("label") == label
    ]
    return matches[0]


def _edge(result: dict, source: str, target: str, relation: str) -> list[dict]:
    return [
        edge
        for edge in result["edges"]
        if edge.get("source") == source
        and edge.get("target") == target
        and edge.get("relation") == relation
    ]


def test_cross_file_inheritance_survives_final_graph_build(tmp_path: Path) -> None:
    base = _write(tmp_path / "module_a.py", "class BaseDriver:\n    pass\n")
    child = _write(
        tmp_path / "module_b.py",
        "from module_a import BaseDriver\n\n\n"
        "class ChildDriver(BaseDriver):\n    pass\n",
    )

    result = extract(
        [base, child], cache_root=tmp_path, root=tmp_path, parallel=False
    )
    base_node = _real_node(result, "BaseDriver", "module_a.py")
    child_node = _real_node(result, "ChildDriver", "module_b.py")

    inheritance = _edge(result, child_node["id"], base_node["id"], "inherits")
    assert len(inheritance) == 1
    assert inheritance[0]["confidence"] == "EXTRACTED"
    assert inheritance[0]["source_location"] == "L4"
    assert not _edge(result, child_node["id"], base_node["id"], "uses")
    assert not [
        node
        for node in result["nodes"]
        if node.get("label") == "BaseDriver" and not node.get("source_file")
    ]

    graph = build_from_json(result, root=tmp_path)
    built = graph.get_edge_data(child_node["id"], base_node["id"])
    assert built is not None
    assert built["relation"] == "inherits"
    assert built["confidence"] == "EXTRACTED"
    assert built["source_location"] == "L4"


def test_aliased_import_resolves_to_canonical_base_without_ghost(tmp_path: Path) -> None:
    base = _write(tmp_path / "module_a.py", "class BaseDriver:\n    pass\n")
    child = _write(
        tmp_path / "module_b.py",
        "from module_a import BaseDriver as ImportedBase\n\n\n"
        "class ChildDriver(ImportedBase):\n    pass\n",
    )

    result = extract(
        [base, child], cache_root=tmp_path, root=tmp_path, parallel=False
    )
    base_node = _real_node(result, "BaseDriver", "module_a.py")
    child_node = _real_node(result, "ChildDriver", "module_b.py")

    inheritance = _edge(result, child_node["id"], base_node["id"], "inherits")
    assert len(inheritance) == 1
    assert inheritance[0]["source_location"] == "L4"
    assert not [
        node for node in result["nodes"] if node.get("label") == "ImportedBase"
    ]
    assert not [
        edge
        for edge in result["edges"]
        if edge.get("source") == child_node["id"]
        and edge.get("relation") == "uses"
        and edge.get("target") == base_node["id"]
    ]


def test_duplicate_base_names_follow_the_exact_import(tmp_path: Path) -> None:
    wrong = _write(
        tmp_path / "pkg_a" / "base.py", "class SharedBase:\n    pass\n"
    )
    right = _write(
        tmp_path / "pkg_b" / "base.py", "class SharedBase:\n    pass\n"
    )
    child = _write(
        tmp_path / "consumer.py",
        "from pkg_b.base import SharedBase\n\n\n"
        "class Concrete(SharedBase):\n    pass\n",
    )

    result = extract(
        [wrong, right, child], cache_root=tmp_path, root=tmp_path, parallel=False
    )
    wrong_node = _real_node(result, "SharedBase", "pkg_a/base.py")
    right_node = _real_node(result, "SharedBase", "pkg_b/base.py")
    child_node = _real_node(result, "Concrete", "consumer.py")

    assert len(_edge(result, child_node["id"], right_node["id"], "inherits")) == 1
    assert not _edge(result, child_node["id"], wrong_node["id"], "inherits")
    assert not _edge(result, child_node["id"], wrong_node["id"], "uses")
    assert not [
        node
        for node in result["nodes"]
        if node.get("label") == "SharedBase" and not node.get("source_file")
    ]


def test_same_named_non_base_import_keeps_inferred_use(tmp_path: Path) -> None:
    inherited = _write(tmp_path / "inherited.py", "class Base:\n    pass\n")
    used = _write(tmp_path / "used.py", "class Base:\n    pass\n")
    child = _write(
        tmp_path / "child.py",
        "from inherited import Base\n"
        "from used import Base as OtherBase\n\n"
        "class Child(Base):\n"
        "    dependency: OtherBase\n",
    )

    result = extract(
        [inherited, used, child], cache_root=tmp_path, root=tmp_path, parallel=False
    )
    inherited_node = _real_node(result, "Base", "inherited.py")
    used_node = _real_node(result, "Base", "used.py")
    child_node = _real_node(result, "Child", "child.py")

    assert len(_edge(result, child_node["id"], inherited_node["id"], "inherits")) == 1
    assert not _edge(result, child_node["id"], inherited_node["id"], "uses")
    uses = _edge(result, child_node["id"], used_node["id"], "uses")
    assert len(uses) == 1
    assert uses[0]["source_location"] == "L2"


def test_inheritance_follows_relative_alias_through_package_reexport(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    init = _write(
        package / "__init__.py",
        "from .base import BaseDriver as PublicBase\n",
    )
    base = _write(package / "base.py", "class BaseDriver:\n    pass\n")
    child = _write(
        tmp_path / "consumer.py",
        "from pkg import PublicBase as ImportedBase\n\n\n"
        "class ChildDriver(ImportedBase):\n    pass\n",
    )

    result = extract(
        [init, base, child], cache_root=tmp_path, root=tmp_path, parallel=False
    )
    base_node = _real_node(result, "BaseDriver", "pkg/base.py")
    child_node = _real_node(result, "ChildDriver", "consumer.py")

    assert len(_edge(result, child_node["id"], base_node["id"], "inherits")) == 1
    assert not [
        node
        for node in result["nodes"]
        if node.get("label") == "ImportedBase" and not node.get("source_file")
    ]


def test_module_qualified_generic_base_resolves_through_import_alias(
    tmp_path: Path,
) -> None:
    base = _write(
        tmp_path / "pkg" / "base.py", "class SharedBase:\n    pass\n"
    )
    child = _write(
        tmp_path / "consumer.py",
        "import pkg.base as model\n\n\n"
        "class Concrete(model.SharedBase[int]):\n    pass\n",
    )

    result = extract(
        [base, child], cache_root=tmp_path, root=tmp_path, parallel=False
    )
    base_node = _real_node(result, "SharedBase", "pkg/base.py")
    child_node = _real_node(result, "Concrete", "consumer.py")

    inheritance = _edge(result, child_node["id"], base_node["id"], "inherits")
    assert len(inheritance) == 1
    assert inheritance[0]["source_location"] == "L4"
    assert not [
        node
        for node in result["nodes"]
        if node.get("label") == "model.SharedBase" and not node.get("source_file")
    ]


def test_incremental_child_resolves_base_from_unchanged_context(tmp_path: Path) -> None:
    base = _write(tmp_path / "base.py", "class Base:\n    pass\n")
    child = _write(
        tmp_path / "child.py",
        "from base import Base\n\n\nclass Child(Base):\n    pass\n",
    )
    full = extract(
        [base, child], cache_root=tmp_path, root=tmp_path, parallel=False
    )
    base_node = _real_node(full, "Base", "base.py")

    changed = extract(
        [child],
        cache_root=tmp_path,
        root=tmp_path,
        parallel=False,
        resolution_context_nodes=full["nodes"],
        resolution_context_edges=full["edges"],
    )
    child_node = _real_node(changed, "Child", "child.py")

    inheritance = _edge(changed, child_node["id"], base_node["id"], "inherits")
    assert len(inheritance) == 1
    assert inheritance[0]["confidence"] == "EXTRACTED"
    assert not any(node.get("id") == base_node["id"] for node in changed["nodes"])


def test_ambiguous_unimported_base_is_not_guessed(tmp_path: Path) -> None:
    first = _write(tmp_path / "a.py", "class Base:\n    pass\n")
    second = _write(tmp_path / "b.py", "class Base:\n    pass\n")
    child = _write(tmp_path / "child.py", "class Child(Base):\n    pass\n")

    result = extract(
        [first, second, child], cache_root=tmp_path, root=tmp_path, parallel=False
    )
    child_node = _real_node(result, "Child", "child.py")
    real_base_ids = {
        node["id"]
        for node in result["nodes"]
        if node.get("label") == "Base" and node.get("source_file")
    }

    assert len(real_base_ids) == 2
    assert not [
        edge
        for edge in result["edges"]
        if edge.get("source") == child_node["id"]
        and edge.get("relation") == "inherits"
        and edge.get("target") in real_base_ids
    ]


def test_conditional_imports_with_distinct_origins_are_not_guessed(
    tmp_path: Path,
) -> None:
    first = _write(tmp_path / "a.py", "class Base:\n    pass\n")
    second = _write(tmp_path / "b.py", "class Base:\n    pass\n")
    child = _write(
        tmp_path / "child.py",
        "try:\n"
        "    from a import Base\n"
        "except ImportError:\n"
        "    from b import Base\n\n\n"
        "class Child(Base):\n    pass\n",
    )

    result = extract(
        [first, second, child], cache_root=tmp_path, root=tmp_path, parallel=False
    )
    child_node = _real_node(result, "Child", "child.py")
    real_base_ids = {
        node["id"]
        for node in result["nodes"]
        if node.get("label") == "Base" and node.get("source_file")
    }

    assert not [
        edge
        for edge in result["edges"]
        if edge.get("source") == child_node["id"]
        and edge.get("target") in real_base_ids
        and edge.get("relation") in {"inherits", "uses"}
    ]
