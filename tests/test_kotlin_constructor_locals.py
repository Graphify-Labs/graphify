"""Bounded Kotlin constructor-local member inference (#1965 / #1699).

This is intentionally a semantic contract suite.  It only drives the public
``extract`` API, so the cache and resolver implementation remain replaceable.
The supported result is one direct ``val r = Type(); r.member(true|false)``
shape, not Kotlin type inference in general.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from graphify.extract import extract


def _extract(
    tmp_path: Path,
    files: dict[str, str],
    *,
    cache_name: str = ".cache",
    absolute_inputs: bool = False,
    extra_inputs: tuple[str, ...] = (),
    resolution_context_nodes=None,
):
    for relative, source in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    paths = [tmp_path / relative for relative in files]
    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        inputs = paths if absolute_inputs else [path.relative_to(tmp_path) for path in paths]
        if extra_inputs:
            inputs.extend(
                tmp_path / extra if absolute_inputs else Path(extra)
                for extra in extra_inputs
            )
        return extract(
            inputs,
            cache_root=tmp_path / cache_name,
            root=tmp_path,
            parallel=False,
            resolution_context_nodes=resolution_context_nodes,
        )
    finally:
        os.chdir(old_cwd)


def _node_id(result, label: str) -> str:
    matches = [node["id"] for node in result["nodes"] if node["label"] == label]
    assert len(matches) == 1, (label, matches)
    return matches[0]


def _callable_id(result, name: str) -> str:
    matches = [
        node["id"]
        for node in result["nodes"]
        if node["label"] in {f"{name}()", f".{name}()"}
    ]
    assert len(matches) == 1, (name, matches)
    return matches[0]


def _member_id(result, owner: str, member: str) -> str:
    owner_id = _node_id(result, owner)
    matches = [
        edge["target"]
        for edge in result["edges"]
        if edge["relation"] == "method"
        and edge["source"] == owner_id
        and next(node for node in result["nodes"] if node["id"] == edge["target"])["label"]
        == f".{member}()"
    ]
    assert len(matches) == 1, (owner, member, matches)
    return matches[0]


def _call(result, caller: str, owner: str, member: str):
    caller_id = _callable_id(result, caller)
    target_id = _member_id(result, owner, member)
    matches = [
        edge
        for edge in result["edges"]
        if edge["relation"] == "calls"
        and edge["source"] == caller_id
        and edge["target"] == target_id
    ]
    assert len(matches) == 1, (caller, owner, member, matches)
    return matches[0]


def _calls_from_at(result, caller: str, line: int):
    caller_id = _callable_id(result, caller)
    return [
        edge
        for edge in result["edges"]
        if edge["relation"] == "calls"
        and edge["source"] == caller_id
        and edge.get("source_location") == f"L{line}"
    ]


def _semantic_projection(result):
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return sorted(
        (
            labels[edge["source"]],
            labels[edge["target"]],
            edge.get("source_location"),
            edge.get("confidence"),
            edge.get("confidence_score"),
        )
        for edge in result["edges"]
        if edge["relation"] == "calls"
        and edge.get("confidence") == "INFERRED"
    )


def _portable_graph_projection(result):
    return {
        "nodes": sorted(
            (node["id"], node["label"], node.get("source_file"))
            for node in result["nodes"]
        ),
        "edges": sorted(
            (
                edge["source"],
                edge["target"],
                edge["relation"],
                edge.get("source_file"),
            )
            for edge in result["edges"]
        ),
    }


def _assert_portable_source_paths(result):
    for item in (*result["nodes"], *result["edges"]):
        source_file = item.get("source_file")
        if source_file:
            assert not Path(source_file).is_absolute(), source_file
            assert "\\" not in source_file, source_file


_LITERAL_ISSUE_FIXTURE = {
    "ChatFragment.kt": """package demo

class ChatFragment {
    private val input = InputView()

    fun getInputView(): InputView {
        return input
    }

    fun onPanelOpen() {
        getInputView().updateKeyboardShow(true)
    }

    fun onPanelClose() {
        input.updateKeyboardShow(false)
    }

    fun onPanelToggle() {
        val v = getInputView()
        v.updateKeyboardShow(true)
    }
}
""",
    "InputView.kt": """package demo

class InputView {
    fun updateKeyboardShow(show: Boolean) {
        val visible = show
    }
}
""",
    "LocalVarCtor.kt": """package demo

class LocalVarCtorPage {
    fun open() {
        val view = InputView()
        view.updateKeyboardShow(true)
    }
}
""",
}


def test_literal_issue_constructor_local_is_the_only_new_typed_receiver_edge_and_is_cache_portable(tmp_path):
    """The supplied issue fixture has four shapes; this accepts exactly shape 3."""
    relative_cold = _extract(tmp_path / "relative", _LITERAL_ISSUE_FIXTURE)
    relative_warm = _extract(tmp_path / "relative", _LITERAL_ISSUE_FIXTURE)
    absolute_cold = _extract(
        tmp_path / "absolute", _LITERAL_ISSUE_FIXTURE, absolute_inputs=True
    )

    for result in (relative_cold, relative_warm, absolute_cold):
        assert result["_kotlin_constructor_local_complete"] is True
        edge = _call(result, "open", "InputView", "updateKeyboardShow")
        assert edge["confidence"] == "INFERRED"
        assert edge["confidence_score"] == pytest.approx(0.85)

        target = _member_id(result, "InputView", "updateKeyboardShow")
        sources = {
            edge["source"]
            for edge in result["edges"]
            if edge["relation"] == "calls" and edge["target"] == target
        }
        assert sources == {_callable_id(result, "open")}

    assert _semantic_projection(relative_cold) == _semantic_projection(relative_warm)
    assert _semantic_projection(relative_cold) == _semantic_projection(absolute_cold)
    _assert_portable_source_paths(relative_cold)
    _assert_portable_source_paths(absolute_cold)
    assert _portable_graph_projection(relative_cold) == _portable_graph_projection(
        absolute_cold
    )


def test_direct_final_method_supports_capitalized_local_and_ignores_same_file_member_collision(tmp_path):
    result = _extract(tmp_path, {
        "All.kt": """package evidence

class Gateway {
    fun publish(enabled: Boolean) { }
}

final class Session {
    fun publish(enabled: Boolean) { }

    fun invoke() {
        val Device = Gateway()
        Device.publish(false)
    }
}
""",
    })

    assert result["_kotlin_constructor_local_complete"] is True
    edge = _call(result, "invoke", "Gateway", "publish")
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == pytest.approx(0.85)
    assert _member_id(result, "Session", "publish") != edge["target"]


def test_top_level_constructor_local_does_not_depend_on_issue_specific_names(tmp_path):
    result = _extract(tmp_path, {
        "Provider.kt": """package renamed

class Dial {
    fun rotate(clockwise: Boolean) { }
}
""",
        "Use.kt": """package renamed

fun refresh() {
    val needle = Dial()
    needle.rotate(true)
}
""",
    })

    assert result["_kotlin_constructor_local_complete"] is True
    edge = _call(result, "refresh", "Dial", "rotate")
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == pytest.approx(0.85)


def test_legacy_kotlin_cache_without_constructor_facts_is_reextracted(tmp_path):
    files = {
        "Provider.kt": """package refreshed

class Gauge {
    fun setActive(active: Boolean) { }
}
""",
        "Caller.kt": """package refreshed

fun rebuild() {
    val gauge = Gauge()
    gauge.setActive(true)
}
""",
    }
    root = tmp_path / "legacy"
    _extract(root, files)
    entries = sorted((root / ".cache").glob("**/ast/**/*.json"))
    assert len(entries) == len(files)
    for entry in entries:
        payload = json.loads(entry.read_text(encoding="utf-8"))
        payload.pop("_kotlin_constructor_local_schema", None)
        payload.pop("kotlin_constructor_locals", None)
        entry.write_text(json.dumps(payload), encoding="utf-8")

    result = _extract(root, files)
    assert result["_kotlin_constructor_local_complete"] is True
    edge = _call(result, "rebuild", "Gauge", "setActive")
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == pytest.approx(0.85)
    for entry in entries:
        payload = json.loads(entry.read_text(encoding="utf-8"))
        assert payload["_kotlin_constructor_local_schema"] == 1
        assert isinstance(payload["kotlin_constructor_locals"], dict)


@pytest.mark.parametrize(
    ("case", "extra_files", "extra_inputs"),
    [
        ("parse_error", {"Broken.kt": "package matrix\nclass Broken {\n"}, ()),
        ("missing_zero_node", {}, ("Missing.kt",)),
    ],
)
def test_incomplete_selected_kotlin_batch_abstains(case, extra_files, extra_inputs, tmp_path):
    files = {
        **_ordinary_files(_emitter()),
        **extra_files,
    }
    result = _extract(tmp_path / case, files, extra_inputs=extra_inputs)
    assert result["_kotlin_constructor_local_complete"] is False
    member_line = files["Caller.kt"].splitlines().index("    item.toggle(true)") + 1
    assert not _calls_from_at(result, "execute", member_line)


def test_kotlin_context_outside_selected_batch_marks_proof_incomplete(tmp_path):
    root = tmp_path / "context"
    context = _extract(root, {"Outside.kt": "package matrix\n\nclass Outside\n"})
    files = _ordinary_files(_emitter())
    result = _extract(root, files, resolution_context_nodes=context["nodes"])

    assert result["_kotlin_constructor_local_complete"] is False
    member_line = files["Caller.kt"].splitlines().index("    item.toggle(true)") + 1
    assert not _calls_from_at(result, "execute", member_line)


def _ordinary_files(provider: str, use: str = "val item = Emitter()\n    item.toggle(true)"):
    return {
        "Provider.kt": "package matrix\n\n" + provider + "\n",
        "Caller.kt": "package matrix\n\nfun execute() {\n    " + use + "\n}\n",
    }


def _emitter(member: str = "fun toggle(flag: Boolean) { }"):
    return "class Emitter {\n    " + member + "\n}"


@pytest.mark.parametrize(
    ("case", "files"),
    [
        (
            "factory_shadow",
            _ordinary_files(
                _emitter() + "\n"
                "fun Emitter(): Emitter = Emitter()"
            ),
        ),
        (
            "value_shadow",
            _ordinary_files(
                _emitter() + "\n"
                "val Emitter: () -> Emitter = { Emitter() }"
            ),
        ),
        (
            "parameter_shadow",
            {
                "Provider.kt": "package matrix\n\n" + _emitter() + "\n",
                "Caller.kt": """package matrix

fun execute(Emitter: () -> Emitter) {
    val item = Emitter()
    item.toggle(true)
}
""",
            },
        ),
        (
            "local_class_shadow",
            {
                "Provider.kt": "package matrix\n\n" + _emitter() + "\n",
                "Caller.kt": """package matrix

fun execute() {
    class Emitter {
        fun toggle(flag: Boolean) { }
    }
    val item = Emitter()
    item.toggle(true)
}
""",
            },
        ),
        (
            "imports_are_excluded",
            {
                "Provider.kt": "package matrix\n\n" + _emitter() + "\n",
                "Caller.kt": """package matrix

import kotlin.io.println

fun execute() {
    val item = Emitter()
    item.toggle(true)
}
""",
            },
        ),
        (
            "typealias_is_excluded",
            _ordinary_files(
                _emitter() + "\n"
                "typealias Alias = Emitter",
                "val item = Alias()\n    item.toggle(true)",
            ),
        ),
        (
            "typed_binding_is_excluded",
            _ordinary_files(
                _emitter(),
                "val item: Emitter = Emitter()\n    item.toggle(true)",
            ),
        ),
        (
            "default_package_is_excluded",
            {
                "Provider.kt": _emitter() + "\n",
                "Caller.kt": """fun execute() {
    val item = Emitter()
    item.toggle(true)
}
""",
            },
        ),
        (
            "nested_provider_is_excluded",
            _ordinary_files("""class Box {
    class Emitter {
        fun toggle(flag: Boolean) { }
    }
}"""),
        ),
        (
            "inheritance_is_excluded",
            _ordinary_files(
                "open class Base\nclass Emitter : Base() {\n    fun toggle(flag: Boolean) { }\n}"
            ),
        ),
        (
            "generic_provider_is_excluded",
            _ordinary_files("class Emitter<T> {\n    fun toggle(flag: Boolean) { }\n}"),
        ),
        (
            "nonpublic_provider_is_excluded",
            _ordinary_files("private class Emitter {\n    fun toggle(flag: Boolean) { }\n}"),
        ),
        (
            "secondary_constructor_is_excluded",
            _ordinary_files(
                "class Emitter {\n    constructor()\n    constructor(value: Int)\n    fun toggle(flag: Boolean) { }\n}"
            ),
        ),
        (
            "companion_is_excluded",
            _ordinary_files(
                "class Emitter {\n    companion object { }\n    fun toggle(flag: Boolean) { }\n}"
            ),
        ),
        (
            "extension_wins_when_member_is_inapplicable",
            _ordinary_files(
                _emitter("fun toggle(text: String) { }") + "\n"
                "fun Emitter.toggle(flag: Boolean) { }"
            ),
        ),
        (
            "overloads_are_excluded",
            _ordinary_files(
                _emitter("fun toggle(flag: Boolean) { }\n    fun toggle(text: String) { }")
            ),
        ),
        (
            "default_target_parameter_is_excluded",
            _ordinary_files(_emitter("fun toggle(flag: Boolean = true) { }")),
        ),
        (
            "vararg_target_parameter_is_excluded",
            _ordinary_files(_emitter("fun toggle(vararg flag: Boolean) { }")),
        ),
        (
            "generic_target_is_excluded",
            _ordinary_files(_emitter("fun <T> toggle(flag: Boolean) { }")),
        ),
        (
            "package_boolean_is_not_builtin_boolean",
            _ordinary_files(
                "class Boolean\n" + _emitter()
            ),
        ),
        (
            "nested_boolean_is_not_builtin_boolean",
            _ordinary_files(
                "class Emitter {\n    class Boolean\n    fun toggle(flag: Boolean) { }\n}"
            ),
        ),
        (
            "recognized_rejection_cannot_use_capitalized_object_fallback",
            _ordinary_files(
                _emitter("fun toggle(text: String) { }") + "\n"
                """object Device {
    fun toggle(flag: Boolean) { }
}""",
                "val Device = Emitter()\n    Device.toggle(true)",
            ),
        ),
    ],
    ids=lambda case: case,
)
def test_constructor_local_semantic_boundaries_abstain(tmp_path, case, files):
    result = _extract(tmp_path / case, files)
    if case not in {"factory_shadow", "value_shadow"}:
        assert result["_kotlin_constructor_local_complete"] is True, case
    member_line = files["Caller.kt"].splitlines().index(
        next(line for line in files["Caller.kt"].splitlines() if ".toggle(" in line)
    ) + 1
    assert not _calls_from_at(result, "execute", member_line), case
