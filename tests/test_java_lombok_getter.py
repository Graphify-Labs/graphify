"""Lombok ``@Getter`` getters are callable members (#5148).

Lombok writes ``getX()``/``isX()`` at compile time, so the source has no
declaration for them. A chain such as ``Model.getInstance().work()`` was typed
step by step from declared return types and stopped at the missing getter.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import extract


def _graph(tmp_path: Path, files: dict[str, str]):
    paths = []
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        paths.append(p)
    r = extract(paths, cache_root=tmp_path / "graphify-out")
    label = {n["id"]: n["label"] for n in r["nodes"]}
    calls = {
        (label.get(e["source"]), label.get(e["target"]))
        for e in r["edges"]
        if e["relation"] == "calls"
    }
    return r, calls


MODEL = (
    "import lombok.Getter;\n"
    "public class Model {\n"
    "    @Getter\n"
    "    private static final Model Instance = new Model();\n"
    "    public void work() {}\n"
    "}\n"
)
CALLER = "public class Caller { void run() { Model.getInstance().work(); } }\n"


def test_static_getter_chain_reaches_the_member(tmp_path: Path):
    _, calls = _graph(tmp_path, {"src/Model.java": MODEL, "src/Caller.java": CALLER})
    assert {(".run()", ".work()"), (".run()", ".getInstance()")} <= calls


def test_generated_getter_looks_like_a_hand_written_one(tmp_path: Path):
    r, _ = _graph(tmp_path, {"Model.java": MODEL})
    g = next(n for n in r["nodes"] if n["label"] == ".getInstance()")
    assert g["_java_ret"] == "Model"
    assert g["metadata"]["arity"] == 0
    assert g["metadata"]["lombok"] == "Getter"
    assert any(e["relation"] == "method" and e["target"] == g["id"] for e in r["edges"])


@pytest.mark.parametrize("decl, getters", [
    ("boolean active;", {".isActive()"}),
    ("boolean isReady;", {".isReady()"}),
    ("Boolean flag;", {".getFlag()"}),
    ("String uRL;", {".getURL()"}),
    ("int a, b;", {".getA()", ".getB()"}),
])
def test_getter_name_follows_lombok(tmp_path: Path, decl: str, getters: set[str]):
    src = f"import lombok.Getter;\nclass T {{ @Getter private {decl} }}\n"
    r, _ = _graph(tmp_path, {"T.java": src})
    assert getters <= {n["label"] for n in r["nodes"]}


def test_class_level_getter_skips_static_fields(tmp_path: Path):
    src = (
        "import lombok.Getter;\n@Getter\nclass W {\n"
        "  private static int sCount;\n  private int count;\n}\n"
    )
    r, _ = _graph(tmp_path, {"W.java": src})
    labels = {n["label"] for n in r["nodes"]}
    assert ".getCount()" in labels
    assert ".getSCount()" not in labels


@pytest.mark.parametrize("src", [
    "import lombok.*;\nclass T { @Getter(AccessLevel.NONE) private int x; }\n",
    "@interface Getter {}\nclass T { @Getter private int x; }\n",
    "import lombok.Getter;\nclass T { @Getter private int x; int getX() { return 1; } }\n",
], ids=["access-none", "not-lombok", "hand-written"])
def test_no_extra_getter_node(tmp_path: Path, src: str):
    r, _ = _graph(tmp_path, {"T.java": src})
    assert [n["label"] for n in r["nodes"]].count(".getX()") <= 1
    assert not any((n.get("metadata") or {}).get("lombok") for n in r["nodes"])
