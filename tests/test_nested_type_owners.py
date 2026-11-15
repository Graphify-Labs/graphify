"""Distinct enclosing owners must not collapse same-named declarations (#5185)."""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import extract


CASES = [
    ("java", "class OWNER {\n static class Builder {\n void setEnabled(boolean v) {}\n }\n}\n"),
    ("cs", "class OWNER {\n public class Builder {\n public void setEnabled(bool v) {}\n }\n}\n"),
    ("cpp", "struct OWNER {\n struct Builder {\n void setEnabled(bool v) {}\n };\n};\n"),
    ("kt", "class OWNER {\n class Builder {\n fun setEnabled(v: Boolean) {}\n }\n}\n"),
    ("scala", "class OWNER {\n class Builder {\n def setEnabled(v: Boolean): Unit = {}\n }\n}\n"),
    ("swift", "class OWNER {\n class Builder {\n func setEnabled(_ v: Bool) {}\n }\n}\n"),
    ("ts", "namespace OWNER {\n export class Builder {\n setEnabled(v: boolean): void {}\n }\n}\n"),
]


@pytest.mark.parametrize("suffix,template", CASES, ids=[case[0] for case in CASES])
@pytest.mark.parametrize("reverse", [False, True])
def test_same_named_nested_types_preserve_both_owners(
    tmp_path: Path, suffix: str, template: str, reverse: bool,
):
    owners = ["Left", "Right"]
    if reverse:
        owners.reverse()
    path = tmp_path / f"Types.{suffix}"
    path.write_text("".join(template.replace("OWNER", owner) for owner in owners), encoding="utf-8")
    previous_ids = None
    for _ in range(2):
        result = extract([path], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
        assert not result["failed_sources"]
        assert not result["skipped_sources"]
        builders = [n for n in result["nodes"] if n.get("source_file") and n["label"] == "Builder"]
        methods = [n for n in result["nodes"] if n.get("source_file") and n["label"] == ".setEnabled()"]
        assert len({n["id"] for n in builders}) == 2
        assert len({n["id"] for n in methods}) == 2
        assert len({n["source_location"] for n in builders}) == 2
        assert len({n["source_location"] for n in methods}) == 2
        member_edges = {
            (e["source"], e["target"]) for e in result["edges"]
            if e["relation"] == "method" and e["target"] in {n["id"] for n in methods}
        }
        assert {source for source, _ in member_edges} == {n["id"] for n in builders}
        assert len(member_edges) == 2
        if suffix != "ts":
            outer_ids = {n["id"] for n in result["nodes"] if n["label"] in owners}
            ownership = {
                (e["source"], e["target"]) for e in result["edges"]
                if e["relation"] == "contains" and e["source"] in outer_ids
                and e["target"] in {n["id"] for n in builders}
            }
            assert len(ownership) == 2
            assert len({target for _, target in ownership}) == 2
        ids = {n["id"] for n in builders + methods}
        if previous_ids is not None:
            assert ids == previous_ids
        previous_ids = ids


def test_nested_csharp_case_and_underscore_members_remain_distinct(tmp_path: Path):
    path = tmp_path / "Types.cs"
    path.write_text(
        "class Outer { class Builder { void Put() {} void _Put() {} } }\n",
        encoding="utf-8",
    )
    result = extract([path], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    members = [n for n in result["nodes"] if n["label"] in {".Put()", "._Put()"}]
    assert len({n["id"] for n in members}) == 2
    assert {n["label"] for n in members} == {".Put()", "._Put()"}
