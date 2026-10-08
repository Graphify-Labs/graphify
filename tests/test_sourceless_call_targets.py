"""Regression tests for unresolved external call targets (#3156)."""

from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import extract


def _nodes(result: dict) -> dict[str, dict]:
    return {node["id"]: node for node in result["nodes"]}


def _labelled_edges(result: dict, nodes: dict[str, dict], label: str) -> list[dict]:
    return [
        edge
        for edge in result["edges"]
        if nodes.get(edge.get("target"), {}).get("label") == label
    ]


def _calls(result: dict) -> set[tuple[str, str, str]]:
    """(caller label, target label, target source_file) for every `calls` edge."""
    nodes = _nodes(result)
    out = set()
    for edge in result["edges"]:
        if edge.get("relation") != "calls":
            continue
        target = nodes.get(edge["target"], {})
        out.add((
            nodes.get(edge["source"], {}).get("label", ""),
            target.get("label", ""),
            str(target.get("source_file") or "").replace("\\", "/"),
        ))
    return out


def _extract_tree(tmp_path: Path, files: dict[str, str]) -> dict:
    paths = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    return extract(paths, cache_root=tmp_path, root=tmp_path)


def test_sourceless_external_call_target_is_not_emitted(tmp_path: Path):
    """A type-reference stub must not become a project-wide calls hub."""
    typed = tmp_path / "typed.py"
    typed.write_text(
        "from fastapi import HTTPException\n"
        "\n"
        "def typed_error() -> HTTPException:\n"
        "    return HTTPException(status_code=400)\n",
        encoding="utf-8",
    )
    caller = tmp_path / "caller.py"
    caller.write_text(
        "def bare_error():\n"
        "    return HTTPException(status_code=401)\n",
        encoding="utf-8",
    )

    result = extract([typed, caller], cache_root=tmp_path, root=tmp_path)
    nodes = _nodes(result)
    external = [node for node in nodes.values() if node.get("label") == "HTTPException"]

    assert len(external) == 1
    assert external[0].get("source_file") == ""
    references = _labelled_edges(result, nodes, "HTTPException")
    assert any(edge.get("context") == "return_type" for edge in references)
    assert not any(edge.get("relation") == "calls" for edge in references)


def test_source_backed_exception_call_is_preserved(tmp_path: Path):
    """A project-defined exception with the same name remains a real call target."""
    definitions = tmp_path / "exceptions.py"
    definitions.write_text(
        "class HTTPException(Exception):\n"
        "    pass\n",
        encoding="utf-8",
    )
    caller = tmp_path / "api.py"
    caller.write_text(
        "from exceptions import HTTPException\n"
        "\n"
        "def raise_error():\n"
        "    return HTTPException()\n",
        encoding="utf-8",
    )

    result = extract([definitions, caller], cache_root=tmp_path, root=tmp_path)
    nodes = _nodes(result)
    calls = _labelled_edges(result, nodes, "HTTPException")

    assert any(
        edge.get("relation") == "calls"
        and nodes[edge["target"]].get("source_file") == "exceptions.py"
        for edge in calls
    ), calls


def test_constructor_call_survives_same_file_annotation_stub(tmp_path: Path):
    """#3888: an annotation mints a sourceless stub for the imported class, and
    the constructor call in the same file must still reach the real definition
    through cross-file resolution instead of being dropped with the stub."""
    pkg = tmp_path / "app" / "engines"
    (pkg / "transcript").mkdir(parents=True)
    parser = pkg / "transcript" / "__init__.py"
    parser.write_text("class Parser:\n    pass\n", encoding="utf-8")
    engine = pkg / "__init__.py"
    engine.write_text(
        "from typing import Optional\n"
        "from app.engines.transcript import Parser\n"
        "\n"
        "\n"
        "class Engine:\n"
        "    def detect(self):\n"
        "        return Parser()\n"
        "\n"
        "    def get_parser(self) -> Optional[Parser]:\n"
        "        return None\n",
        encoding="utf-8",
    )

    result = extract([parser, engine], cache_root=tmp_path, root=tmp_path)

    assert (".detect()", "Parser", "app/engines/transcript/__init__.py") in _calls(result)


def test_csharp_new_survives_generic_arg_stub_without_binding_members(tmp_path: Path):
    """#3888, C# shape: `List<Widget>` stubs `Widget` in the file, so `new Widget()`
    was lost. Recovering it must not let `new List<int>()` bind to an enum
    member that happens to be called `List`."""
    files = {
        "Lib/Widget.cs": "namespace Demo\n{\n    public class Widget\n    {\n    }\n}\n",
        "Lib/Kinds.cs": "namespace Demo\n{\n    public enum ViewKind { List, Grid }\n}\n",
        "App/Factory.cs": (
            "using System.Collections.Generic;\n"
            "\n"
            "namespace Demo\n"
            "{\n"
            "    public class Registry\n"
            "    {\n"
            "        public List<Widget> Items;\n"
            "    }\n"
            "\n"
            "    public class Factory\n"
            "    {\n"
            "        public object MakeA() { return new Widget(); }\n"
            "\n"
            "        public object MakeList() { return new List<int>(); }\n"
            "    }\n"
            "}\n"
        ),
        "App/Plain.cs": (
            "namespace Demo\n"
            "{\n"
            "    public class Plain\n"
            "    {\n"
            "        public object Make() { return new Widget(); }\n"
            "    }\n"
            "}\n"
        ),
    }
    calls = _calls(_extract_tree(tmp_path, files))

    assert (".Make()", "Widget", "Lib/Widget.cs") in calls
    assert (".MakeA()", "Widget", "Lib/Widget.cs") in calls
    assert not any(caller == ".MakeList()" for caller, _, _ in calls), calls


@pytest.mark.parametrize(
    "files",
    [
        pytest.param(
            {
                "other/Client.java": "package other;\npublic class Client {}\n",
                "app/A.java": (
                    "package app;\n"
                    "import com.lib.Client;\n"
                    "\n"
                    "public class A {\n"
                    "    public Client make() { return new Client(); }\n"
                    "}\n"
                ),
            },
            id="java-import-from-another-package",
        ),
        pytest.param(
            {
                "Other/List.cs": "namespace Other\n{\n    public class List { }\n}\n",
                "App/A.cs": (
                    "using System.Collections.Generic;\n"
                    "\n"
                    "namespace App\n"
                    "{\n"
                    "    public class A\n"
                    "    {\n"
                    "        public List<int> Items;\n"
                    "        public object Make() { return new List<int>(); }\n"
                    "    }\n"
                    "}\n"
                ),
            },
            id="csharp-namespace-not-in-scope",
        ),
    ],
)
def test_stub_rescued_call_needs_import_or_scope_evidence(tmp_path: Path, files: dict[str, str]):
    """#3888 review: the file annotates the type and imports it from elsewhere,
    so a same-named class in an unrelated package/namespace is not the target.
    Before the stub rescue these calls had no edge; they must not gain a wrong one."""
    calls = _calls(_extract_tree(tmp_path, files))

    assert not any(caller in (".make()", ".Make()") for caller, _, _ in calls), calls


def test_csharp_stub_rescued_call_follows_using(tmp_path: Path):
    """The same C# shape with `using Other;` in scope does bind to `Other.List`."""
    files = {
        "Other/List.cs": "namespace Other\n{\n    public class List { }\n}\n",
        "App/A.cs": (
            "using Other;\n"
            "\n"
            "namespace App\n"
            "{\n"
            "    public class A\n"
            "    {\n"
            "        public List Items;\n"
            "        public object Make() { return new List(); }\n"
            "    }\n"
            "}\n"
        ),
    }
    calls = _calls(_extract_tree(tmp_path, files))

    assert (".Make()", "List", "Other/List.cs") in calls
