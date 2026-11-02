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


# Shapes tree-sitter-swift misparses: error recovery then lifts a type's members
# to the top level, or wraps the type's header in a bogus alias. Which shapes
# misparse depends on the grammar version: 0.7.2 trips on an `#if` inside a
# type body, 0.7.4 parses that but trips on a freestanding `#warning`/macro
# expansion there.
MISPARSED = {
    "lifted-member": "class DS {\n    #if os(iOS)\n    typealias Titles = (Int) -> [String]?\n"
                     "    #endif\n    func titles() -> Int { 1 }\n}\n",
    "wrapped-header": "class DS<S: P>:\n    NSObject,\n    Q\n{\n    typealias Item = S.Item\n\n"
                      "    #if os(iOS)\n    typealias Titles = (Int) -> [String]?\n    #endif\n\n"
                      "    func titles(for _: Int) -> [String]? { nil }\n}\n",
    "warning-directive": "class DS {\n    #warning(\"todo\")\n    typealias Titles = (Int) -> [String]?\n"
                         "    func titles() -> Int { 1 }\n}\n",
    "macro-expansion": "struct DS {\n    #externalMacro(module: \"M\", type: \"T\")\n"
                       "    typealias Titles = (Int) -> [String]?\n    func titles() -> Int { 1 }\n}\n",
}


def test_some_misparse_fixture_still_misparses():
    """The misparse tests below check nothing once the grammar parses every
    fixture cleanly; if this fails, add a shape the installed grammar trips on."""
    import tree_sitter
    import tree_sitter_swift

    parser = tree_sitter.Parser(tree_sitter.Language(tree_sitter_swift.language()))
    assert any(parser.parse(src.encode()).root_node.has_error for src in MISPARSED.values())


@pytest.mark.parametrize("case", sorted(MISPARSED))
def test_a_member_alias_in_a_misparsed_type_is_not_a_node(tmp_path: Path, case: str):
    result = _extract(tmp_path, {"a.swift": MISPARSED[case]})
    assert not _sourced(result, "Titles")
    assert not _sourced(result, "Item")


@pytest.mark.parametrize("case", sorted(MISPARSED))
def test_a_file_scope_alias_after_a_misparsed_type_is_still_a_node(tmp_path: Path, case: str):
    src = MISPARSED[case] + "typealias Top = Int\n"
    result = _extract(tmp_path, {"a.swift": src})
    nodes = _sourced(result, "Top")
    assert len(nodes) == 1 and nodes[0]["source_location"] == f"L{src.count(chr(10))}"


def test_an_alias_named_after_the_file_extension_keeps_its_own_node(tmp_path: Path):
    """`typealias Swift` in `Box.swift` spells the file's own id (`box_swift`).
    It must still be its own node, contained by the file, and a reference to it
    must land on it, not on the file node or a stub (#4854)."""
    result = _extract(tmp_path, {"Box.swift": "typealias Swift = Int\n\nstruct Holder {\n    var v: Swift\n}\n"})
    file_ids = {n["id"] for n in result["nodes"] if n["label"] == "Box.swift"}
    alias = [n for n in _sourced(result, "Swift") if n["id"] not in file_ids]
    assert len(alias) == 1, result["nodes"]
    assert any(e["relation"] == "contains" and e["target"] == alias[0]["id"]
               and e["source"] in file_ids for e in result["edges"])
    assert _ref_targets(result, "Holder") == {"Swift": "Box.swift"}


def test_an_alias_and_a_type_differing_only_in_case_stay_two_nodes(tmp_path: Path):
    """`typealias string` and `struct String` are two declarations, so the alias
    must not merge into the struct (it would if it registered as a "type")."""
    result = _extract(tmp_path, {"Box.swift": "typealias string = [Character]\nstruct String {}\n"})
    assert len(_sourced(result, "string")) == 1
    assert len(_sourced(result, "String")) == 1
