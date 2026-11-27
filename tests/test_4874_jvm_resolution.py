"""#4874: Java/Kotlin references must reach the declaration node, not a file or stub.

The fixture is the issue's four-file project. The tests split the contract into
the three reported failures plus controls that must keep passing:

  * Kotlin imports a Java class used only in a static call.
  * Java imports and extends a Kotlin class.
  * Kotlin calls a static Java method through that class.
  * `affected` must reach both language sides through the class node.
  * A Java/Kotlin import with a local definition must not be marked external.
  * An external import must not bind to a same-named local class.
  * Two same-named classes in different packages must be disambiguated by import.
  * A JVM call must not bind to a non-JVM definition.
"""
from __future__ import annotations

from pathlib import Path

from graphify.affected import affected_nodes, resolve_seed
from graphify.build import build_from_json
from graphify.extract import extract


PKG = {
    "Logger.java": """\
package com.example.util;
public class Logger { public static void info(String m) { System.out.println(m); } }
""",
    "BaseScreen.kt": """\
package com.example.ui
open class BaseScreen { fun show() {} }
""",
    "JavaUser.java": """\
package com.example.app;
import com.example.util.Logger;
import com.example.ui.BaseScreen;
public class JavaUser extends BaseScreen { public void run() { Logger.info("java"); } }
""",
    "KotlinUser.kt": """\
package com.example.app
import com.example.util.Logger
import com.example.ui.BaseScreen
class KotlinUser : BaseScreen() { fun run() { Logger.info("kotlin") } }
""",
}


def _write(root: Path, name: str, text: str) -> Path:
    path = root / "src" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _extract(root: Path, files: dict[str, str]) -> dict:
    paths = [_write(root, name, text) for name, text in files.items()]
    return extract(paths, root=root, cache_root=root / "cache", parallel=False)


def _node(result: dict, label: str, suffix: str) -> dict:
    matches = [
        n for n in result["nodes"]
        if n.get("label") == label
        and str(n.get("source_file", "")).replace("\\", "/").endswith(suffix)
    ]
    assert len(matches) == 1, (label, suffix, matches)
    return matches[0]


def _edges(result: dict, relation: str) -> list[dict]:
    return [e for e in result["edges"] if e.get("relation") == relation]


def _edge(result: dict, source: str, relation: str, target: str) -> dict | None:
    for edge in _edges(result, relation):
        if edge.get("source") == source and edge.get("target") == target:
            return edge
    return None


def _sourceless_ids(result: dict) -> set[str]:
    return {n["id"] for n in result["nodes"] if not n.get("source_file")}


def _affected_labels(result: dict, seed: str, depth: int = 2) -> set[str]:
    graph = build_from_json(result, directed=True)
    seed_id = resolve_seed(graph, seed)
    assert seed_id is not None, f"seed {seed!r} did not resolve"
    hits = affected_nodes(graph, seed_id, depth=depth)
    return {str(graph.nodes[hit.node_id].get("label", hit.node_id)) for hit in hits}


def test_kotlin_import_of_java_class_targets_the_class_node(tmp_path: Path) -> None:
    result = _extract(tmp_path, PKG)
    kotlin_file = _node(result, "KotlinUser.kt", "KotlinUser.kt")
    logger_class = _node(result, "Logger", "Logger.java")
    logger_file = _node(result, "Logger.java", "Logger.java")

    assert _edge(result, kotlin_file["id"], "imports", logger_class["id"]), (
        "Kotlin's import of Logger must reach the Logger class node"
    )
    assert logger_class["id"] != logger_file["id"]


def test_java_import_and_inheritance_of_kotlin_class_target_the_class_node(tmp_path: Path) -> None:
    result = _extract(tmp_path, PKG)
    java_file = _node(result, "JavaUser.java", "JavaUser.java")
    java_class = _node(result, "JavaUser", "JavaUser.java")
    base_class = _node(result, "BaseScreen", "BaseScreen.kt")

    assert _edge(result, java_file["id"], "imports", base_class["id"]), (
        "Java's import of BaseScreen must reach the Kotlin class node"
    )
    assert _edge(result, java_class["id"], "inherits", base_class["id"]), (
        "JavaUser extends BaseScreen must reach the Kotlin class node"
    )
    assert not any(
        e.get("target") in _sourceless_ids(result)
        for e in _edges(result, "imports")
        if e.get("source") == java_file["id"]
    ), "the Java import must not be parked on a source-less FQN stub"


def test_kotlin_member_call_reaches_the_java_method(tmp_path: Path) -> None:
    result = _extract(tmp_path, PKG)
    kotlin_run = _node(result, ".run()", "KotlinUser.kt")
    logger_info = _node(result, ".info()", "Logger.java")

    assert _edge(result, kotlin_run["id"], "calls", logger_info["id"]), (
        "KotlinUser.run() must call Logger.info() across the JVM language boundary"
    )


def test_affected_reaches_dependents_in_both_languages(tmp_path: Path) -> None:
    result = _extract(tmp_path, PKG)

    logger_hits = _affected_labels(result, "Logger", depth=2)
    assert {"JavaUser.java", "KotlinUser.kt"} <= logger_hits, logger_hits

    base_hits = _affected_labels(result, "BaseScreen", depth=2)
    assert {"JavaUser.java", "KotlinUser.kt"} <= base_hits, base_hits


def test_existing_kotlin_subclass_of_java_base_is_unchanged(tmp_path: Path) -> None:
    files = {
        "Base.java": "package models;\npublic class Base {}\n",
        "Child.kt": "package app\nimport models.Base\nclass Child : Base()\n",
    }
    result = _extract(tmp_path, files)
    child = _node(result, "Child", "Child.kt")
    base = _node(result, "Base", "Base.java")
    assert _edge(result, child["id"], "inherits", base["id"])


def test_java_to_kotlin_import_without_inheritance_targets_class(tmp_path: Path) -> None:
    files = {
        "Widget.kt": "package ui\nclass Widget\n",
        "Use.java": (
            "package app;\n"
            "import ui.Widget;\n"
            "public class Use { Widget field; }\n"
        ),
    }
    result = _extract(tmp_path, files)
    use_file = _node(result, "Use.java", "Use.java")
    widget = _node(result, "Widget", "Widget.kt")
    assert _edge(result, use_file["id"], "imports", widget["id"])


def test_external_java_import_does_not_bind_to_a_local_same_name_class(tmp_path: Path) -> None:
    files = {
        "Component.java": "package local;\npublic class Component {}\n",
        "Use.java": (
            "package app;\n"
            "import org.springframework.stereotype.Component;\n"
            "public class Use { Component field; }\n"
        ),
    }
    result = _extract(tmp_path, files)
    local = _node(result, "Component", "Component.java")
    use_file = _node(result, "Use.java", "Use.java")
    assert not _edge(result, use_file["id"], "imports", local["id"]), (
        "an explicit external import must not collapse onto a local same-named class"
    )


def test_same_simple_name_in_two_packages_uses_the_import_package(tmp_path: Path) -> None:
    files = {
        "a/Logger.java": "package a;\npublic class Logger {}\n",
        "b/Logger.java": "package b;\npublic class Logger {}\n",
        "Use.kt": (
            "package app\n"
            "import b.Logger\n"
            "class Use { fun f() { Logger.info() } }\n"
        ),
    }
    result = _extract(tmp_path, files)
    kotlin_file = _node(result, "Use.kt", "Use.kt")
    logger_a = _node(result, "Logger", "a/Logger.java")
    logger_b = _node(result, "Logger", "b/Logger.java")
    assert _edge(result, kotlin_file["id"], "imports", logger_b["id"])
    assert not _edge(result, kotlin_file["id"], "imports", logger_a["id"])


def test_jvm_call_does_not_bind_to_a_non_jvm_type(tmp_path: Path) -> None:
    files = {
        "logger.py": "class Logger:\n    def info(self):\n        return None\n",
        "Use.kt": "package app\nclass Use { fun f() { Logger.info() } }\n",
    }
    result = _extract(tmp_path, files)
    kotlin_run = _node(result, ".f()", "Use.kt")
    python_info = [n for n in result["nodes"] if n.get("label") == ".info()"]
    assert python_info, "fixture must contain the Python method node"
    assert not _edge(result, kotlin_run["id"], "calls", python_info[0]["id"])
