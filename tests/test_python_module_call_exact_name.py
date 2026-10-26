"""`module.func()` resolves to the child named exactly `func` (#1883 module arm).

The module arm looked the callee up among the module's children by a key that
drops every non-alphanumeric character and folds case, so `dataclass_schema()`
and `class DataclassSchema` share one key. Python names are case-sensitive and
`_` is significant, yet any such pair made the lookup ambiguous and the call was
dropped: every `core_schema.x_schema(...)` call in pydantic-core (each function
sits beside its `XSchema` TypedDict) got no edge. Among children that share the
folded key, the one whose name is exactly the callee now wins. A call matching
only on the folded key, with no exact name, still gets no edge.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract

_CORE = (
    "from typing import TypedDict\n\n\n"
    "class DataclassSchema(TypedDict):\n    type: str\n\n\n"
    "def dataclass_schema(cls):\n    return {'type': 'dataclass'}\n\n\n"
    "def compute_value():\n    return 1\n\n\n"
    "class ComputeValue:\n    pass\n"
)


def _calls(tmp_path: Path, caller_body: str) -> list[tuple[str, str, str]]:
    (tmp_path / "core_schema.py").write_text(_CORE, encoding="utf-8")
    (tmp_path / "caller.py").write_text(caller_body, encoding="utf-8")
    result = extract([tmp_path / "caller.py", tmp_path / "core_schema.py"], root=tmp_path,
                     cache_root=tmp_path / "graphify-out", parallel=False)
    label = {n["id"]: n["label"] for n in result["nodes"]}
    return [(label.get(e["source"], ""), label.get(e["target"], ""), e["confidence"])
            for e in result["edges"]
            if e["relation"] == "calls" and label.get(e["source"]) == "build()"]


def test_a_function_beside_a_same_key_class_resolves_by_its_exact_name(tmp_path: Path):
    calls = _calls(tmp_path, "import core_schema\n\n\ndef build():\n    return core_schema.dataclass_schema(1)\n")
    assert calls == [("build()", "dataclass_schema()", "EXTRACTED")]


def test_the_class_itself_resolves_by_its_exact_name(tmp_path: Path):
    calls = _calls(tmp_path, "import core_schema\n\n\ndef build():\n    return core_schema.DataclassSchema(type='x')\n")
    assert calls == [("build()", "DataclassSchema", "EXTRACTED")]


def test_an_aliased_module_import_resolves_the_same_way(tmp_path: Path):
    calls = _calls(tmp_path, "import core_schema as cs\n\n\ndef build():\n    return cs.dataclass_schema(1)\n")
    assert calls == [("build()", "dataclass_schema()", "EXTRACTED")]


def test_a_name_that_matches_only_after_folding_still_gets_no_edge(tmp_path: Path):
    """`computevalue` is neither `compute_value` nor `ComputeValue`: fail closed."""
    assert _calls(tmp_path, "import core_schema\n\n\ndef build():\n    return core_schema.computevalue()\n") == []


def test_a_call_never_binds_to_an_unrelated_modules_child(tmp_path: Path):
    """The receiver's own import decides the module. A same-named child of a
    DIFFERENT corpus module must never be bound: the exact-name lookup only
    re-buckets within the module the receiver already resolved to."""
    (tmp_path / "core_schema.py").write_text(_CORE, encoding="utf-8")
    (tmp_path / "other.py").write_text("def unrelated():\n    return 0\n", encoding="utf-8")
    (tmp_path / "caller.py").write_text(
        "import other\n\n\ndef build():\n    return other.dataclass_schema(1)\n",
        encoding="utf-8")
    result = extract(
        [tmp_path / "caller.py", tmp_path / "core_schema.py", tmp_path / "other.py"],
        root=tmp_path, cache_root=tmp_path / "graphify-out", parallel=False)
    label = {n["id"]: n["label"] for n in result["nodes"]}
    targets = [label.get(e["target"], "") for e in result["edges"]
               if e["relation"] == "calls" and label.get(e["source"]) == "build()"]
    # `other` has no dataclass_schema; core_schema's must NOT be hijacked.
    assert "dataclass_schema()" not in targets, targets
