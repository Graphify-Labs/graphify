"""#4711: a decorator whose expression is a call chain keeps its edge.

tree-sitter-typescript 0.23.2 cannot parse a member access on a call in
decorator position: `@Link().toMany()`, with or without the surrounding
parentheses, becomes an ERROR plus a recovered call. Before this fix a
parenthesized decorator produced no edge at all, because `_ts_decorator_name`
returned `None` for a `parenthesized_expression`, and the recovered outermost
call was never read.

The parse error itself is upstream (0.23.2 is the newest release), so these
tests pin the extractor's recovery, not a clean parse.
"""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extract import _file_stem, _make_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _class_nid(file: str, cls: str) -> str:
    return _make_id(_file_stem(Path(file)), cls)


def _has_deco(result: dict, owner_nid: str, deco: str) -> bool:
    target = _make_id(deco)
    return any(
        e["source"] == owner_nid
        and e["target"] == target
        and e["relation"] == "references"
        and e.get("context") == "decorator"
        for e in result["edges"]
    )


def test_parenthesized_chain_with_newline_before_dot(tmp_path):
    f = _write(
        tmp_path / "src" / "c.ts",
        "export class C {\n"
        "  @(Link()\n"
        "    .toMany())\n"
        "  a: X;\n"
        "}\n",
    )
    r = extract([f], cache_root=tmp_path)
    assert _has_deco(r, _class_nid("src/c.ts", "C"), "toMany")


def test_parenthesized_chain_on_one_line(tmp_path):
    # Single-line recovery: no warning fires, but the decorator edge was still
    # dropped before the fix.
    f = _write(
        tmp_path / "src" / "c.ts",
        "export class C {\n"
        "  @(Link().toMany())\n"
        "  a: X;\n"
        "}\n",
    )
    r = extract([f], cache_root=tmp_path)
    assert _has_deco(r, _class_nid("src/c.ts", "C"), "toMany")


def test_parenthesized_identifier_receiver_parses_clean(tmp_path):
    # `@(Link\n.toMany())` has no parse error; it still lost the edge because
    # the parenthesized expression was never unwrapped.
    f = _write(
        tmp_path / "src" / "c.ts",
        "export class C {\n"
        "  @(Link\n"
        "    .toMany())\n"
        "  a: X;\n"
        "}\n",
    )
    r = extract([f], cache_root=tmp_path)
    assert _has_deco(r, _class_nid("src/c.ts", "C"), "toMany")


def test_recovered_non_call_parenthesized_expression_gets_no_edge(tmp_path):
    # `@(A, B)` is not a valid decorator expression and recovers as
    # ERROR + identifier. Naming that identifier would invent an edge.
    f = _write(
        tmp_path / "src" / "c.ts",
        "export class C {\n"
        "  @(A, B)\n"
        "  a: X;\n"
        "}\n",
    )
    r = extract([f], cache_root=tmp_path)
    assert not _has_deco(r, _class_nid("src/c.ts", "C"), "B")


def test_warning_names_the_multiline_region_not_an_earlier_recovery(tmp_path, capsys):
    body = (
        "export class A {\n"          # line 1
        "  @(Link().toMany())\n"      # line 2: single-line ERROR, recovered
        "  a: X;\n"                   # line 3
        "}\n"
        "\n"
        "export class B {\n"          # line 6
        "  @(Link()\n"                # line 7: multiline ERROR starts here
        "    .toMany())\n"            # line 8
        "  b: X;\n"                   # line 9
        "}\n"
    )
    f = _write(tmp_path / "src" / "c.ts", body)
    extract([f], cache_root=tmp_path)
    err = capsys.readouterr().err
    match = re.search(r"error region at line (\d+)", err)
    assert match, err
    assert int(match.group(1)) == 7, err
