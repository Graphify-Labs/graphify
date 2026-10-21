"""A file-scope Swift `typealias` is a type node in its declaring file.

The Swift extractor emitted no node for `typealias Handler = (Int) -> Void`, so
every field, parameter or return typed with the alias, even in the declaring
file, resolved to a sourceless stub. A file-scope alias now gets a node with a
`contains` edge from its file, the same id a top-level type would get.

Not declarations here, on purpose: a member alias (`typealias Element = Int`
in a type, protocol or extension), which witnesses an associated type in many
types, and a function-local one. A same-name re-export
(`typealias Field = Core.Field`) denotes the original type, so it gets no
node either.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_swift")

from graphify.extract import extract


def _extract(tmp_path: Path, files: dict[str, str]) -> dict:
    for name, src in files.items():
        (tmp_path / name).write_text(src, encoding="utf-8")
    paths = sorted(tmp_path / name for name in files)
    return extract(paths, root=tmp_path, cache_root=tmp_path / "graphify-out", parallel=False)


def _sourced(result: dict, label: str) -> list[dict]:
    return [n for n in result["nodes"] if n["label"] == label and n.get("source_file")]


def _ref_targets(result: dict, source_label: str) -> dict[str, str]:
    nodes = {n["id"]: n for n in result["nodes"]}
    out = {}
    for e in result["edges"]:
        if e["relation"] == "references" and nodes[e["source"]]["label"] == source_label:
            target = nodes[e["target"]]
            out[target["label"]] = Path(target.get("source_file") or "").name or "SOURCELESS"
    return out


ALIASES = """\
typealias Handler = (Int) -> Void
public typealias JSON = [String: Any]
typealias Pair<T> = (T, T)
@available(iOS 13, *)
typealias Token = String

struct Box {
    var h: Handler
    func run(j: JSON) -> Pair<Int> { return (1, 1) }
}
"""


def test_file_scope_aliases_are_sourced_nodes_on_their_lines(tmp_path: Path):
    result = _extract(tmp_path, {"a.swift": ALIASES})
    # An attribute is part of the declaration, as for an attributed struct.
    for label, line in (("Handler", "L1"), ("JSON", "L2"), ("Pair", "L3"), ("Token", "L4")):
        nodes = _sourced(result, label)
        assert len(nodes) == 1, (label, nodes)
        assert nodes[0]["source_location"] == line
        assert Path(nodes[0]["source_file"]).name == "a.swift"


def test_the_file_contains_each_alias(tmp_path: Path):
    result = _extract(tmp_path, {"a.swift": ALIASES})
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    contained = {labels[e["target"]] for e in result["edges"]
                 if e["relation"] == "contains" and labels[e["source"]] == "a.swift"}
    assert {"Handler", "JSON", "Pair", "Token"} <= contained


def test_references_in_the_declaring_file_land_on_the_alias(tmp_path: Path):
    result = _extract(tmp_path, {"a.swift": ALIASES})
    assert _ref_targets(result, "Box")["Handler"] == "a.swift"
    run = _ref_targets(result, ".run()")
    assert run["JSON"] == "a.swift"
    assert run["Pair"] == "a.swift"


def test_a_reference_from_another_file_is_rewired_onto_the_alias(tmp_path: Path):
    result = _extract(tmp_path, {"a.swift": ALIASES, "b.swift": "func use(h: Handler) {}\n"})
    assert _ref_targets(result, "use()")["Handler"] == "a.swift"


def test_a_conditional_alias_pair_is_one_node(tmp_path: Path):
    src = ("#if os(iOS)\npublic typealias Color = UIColor\n#else\n"
           "public typealias Color = NSColor\n#endif\n")
    result = _extract(tmp_path, {"a.swift": src})
    nodes = _sourced(result, "Color")
    assert len(nodes) == 1 and nodes[0]["source_location"] == "L2"


def test_member_and_local_aliases_are_not_nodes(tmp_path: Path):
    src = """\
struct Box { typealias Element = Int }
protocol P { associatedtype Item; typealias Alias = Item }
extension Box { typealias Index = Int }
func f() { typealias Local = Int }
"""
    result = _extract(tmp_path, {"a.swift": src})
    for label in ("Element", "Alias", "Index", "Local"):
        assert not _sourced(result, label), label


def test_a_same_name_re_export_is_not_a_node(tmp_path: Path):
    src = """\
typealias Field = Core.Field
typealias Entry = Core.Field<Int>
typealias Other = Core.Entry
"""
    result = _extract(tmp_path, {"a.swift": src})
    assert not _sourced(result, "Field")
    assert len(_sourced(result, "Entry")) == 1
    assert len(_sourced(result, "Other")) == 1


# tree-sitter-swift misparses an `#if` inside a type body; error recovery then
# lifts members to the top level, or wraps the type's header in a bogus alias.
MISPARSED = {
    "lifted-member": "class DS {\n    #if os(iOS)\n    typealias Titles = (Int) -> [String]?\n"
                     "    #endif\n    func titles() -> Int { 1 }\n}\n",
    "wrapped-header": "class DS<S: P>:\n    NSObject,\n    Q\n{\n    typealias Item = S.Item\n\n"
                      "    #if os(iOS)\n    typealias Titles = (Int) -> [String]?\n    #endif\n\n"
                      "    func titles(for _: Int) -> [String]? { nil }\n}\n",
}


@pytest.mark.parametrize("case", sorted(MISPARSED))
def test_a_member_alias_in_a_misparsed_type_is_not_a_node(tmp_path: Path, case: str):
    result = _extract(tmp_path, {"a.swift": MISPARSED[case]})
    assert not _sourced(result, "Titles")
    assert not _sourced(result, "Item")


def test_a_file_scope_alias_after_a_misparsed_type_is_still_a_node(tmp_path: Path):
    src = MISPARSED["lifted-member"] + "typealias Top = Int\n"
    result = _extract(tmp_path, {"a.swift": src})
    nodes = _sourced(result, "Top")
    assert len(nodes) == 1 and nodes[0]["source_location"] == "L7"
