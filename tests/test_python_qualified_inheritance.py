"""Regression coverage for qualified Python class bases."""

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _node_id(result: dict, label: str, source_file: str) -> str:
    matches = [
        node["id"]
        for node in result["nodes"]
        if node.get("label") == label and node.get("source_file") == source_file
    ]
    assert len(matches) == 1
    return matches[0]


def test_module_qualified_base_inherits_from_the_imported_class(tmp_path: Path) -> None:
    base = _write(tmp_path / "base.py", "class BaseClass:\n    pass\n")
    child = _write(
        tmp_path / "child.py",
        "import base as Module\n\nclass Child(Module.BaseClass):\n    pass\n",
    )

    result = extract([base, child], cache_root=tmp_path, root=tmp_path)

    child_id = _node_id(result, "Child", "child.py")
    base_id = _node_id(result, "BaseClass", "base.py")
    assert any(
        edge["source"] == child_id and edge["target"] == base_id and edge["relation"] == "inherits"
        for edge in result["edges"]
    )


def test_module_qualified_base_does_not_bind_an_unrelated_local_class(tmp_path: Path) -> None:
    local = _write(tmp_path / "local.py", "class BaseClass:\n    pass\n")
    child = _write(
        tmp_path / "child.py",
        "import external as Module\n\nclass Child(Module.BaseClass):\n    pass\n",
    )

    result = extract([local, child], cache_root=tmp_path, root=tmp_path)

    child_id = _node_id(result, "Child", "child.py")
    local_base_id = _node_id(result, "BaseClass", "local.py")
    assert not any(
        edge["source"] == child_id
        and edge["target"] == local_base_id
        and edge["relation"] == "inherits"
        for edge in result["edges"]
    )
