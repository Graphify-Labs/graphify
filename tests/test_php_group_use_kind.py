"""Group-form `use function` / `use const` must not claim class names (#26).

tree-sitter-php puts the `function` / `const` keyword on the *clause* for the
plain form (`use function A\\f;`) but on the *declaration* for the group form
(`use function A\\{f, g};`). `_resolve_php_type_references` only ever inspected
the clause, so group-form members wrongly entered the per-file class-name map
and re-pointed supertype references onto an FQN-labeled external stub.

Every assertion goes through the public `extract()` seam, with the semantically
equivalent plain form as the side-by-side control.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _node_by_id(result: dict, nid: str) -> dict | None:
    return next((n for n in result["nodes"] if n.get("id") == nid), None)


def _labels(result: dict) -> set[str]:
    return {n.get("label") for n in result["nodes"]}


def _targets(result: dict, relation: str, source_substr: str) -> list[dict]:
    """Target nodes of every `relation` edge coming out of a matching source."""
    return [
        _node_by_id(result, e["target"])
        for e in result["edges"]
        if e.get("relation") == relation
        and source_substr in e.get("source", "").lower()
    ]


def test_php_group_use_function_behaves_like_the_plain_form(tmp_path: Path):
    # `use function Vendor\Sdk\{Render};` imports a *function*, so `Render` in a
    # class position is not an explicitly imported class name. The braced form
    # must land exactly where the unbraced control lands: on the bare stub the
    # legacy unique-label rewire owns, never on an FQN-labeled external stub.
    group = _write(
        tmp_path / "app/A/UsesGroup.php",
        "<?php\nnamespace App\\A;\n"
        "use function Vendor\\Sdk\\{Render};\n"
        "class UsesGroup extends Render {}\n",
    )
    plain = _write(
        tmp_path / "app/B/UsesPlain.php",
        "<?php\nnamespace App\\B;\n"
        "use function Vendor\\Sdk\\Render;\n"
        "class UsesPlain extends Render {}\n",
    )
    result = extract([group, plain], cache_root=tmp_path)

    group_bases = _targets(result, "inherits", "usesgroup")
    plain_bases = _targets(result, "inherits", "usesplain")
    assert len(group_bases) == 1 and len(plain_bases) == 1, (group_bases, plain_bases)
    assert group_bases[0] is not None and plain_bases[0] is not None
    assert group_bases[0]["label"] == "Render", group_bases[0]
    assert group_bases[0]["id"] == plain_bases[0]["id"], (group_bases, plain_bases)

    # The `imports` edges agree too, and no FQN-labeled class stub was minted
    # for a name the files only ever imported as a function.
    group_imports = _targets(result, "imports", "usesgroup")
    plain_imports = _targets(result, "imports", "usesplain")
    assert [n["id"] for n in group_imports] == [n["id"] for n in plain_imports], (
        group_imports,
        plain_imports,
    )
    assert "Vendor\\Sdk\\Render" not in _labels(result), sorted(_labels(result))


def test_php_group_use_const_behaves_like_the_plain_form(tmp_path: Path):
    group = _write(
        tmp_path / "app/A/UsesConstGroup.php",
        "<?php\nnamespace App\\A;\n"
        "use const Vendor\\Sdk\\{LIMIT};\n"
        "class UsesConstGroup extends LIMIT {}\n",
    )
    plain = _write(
        tmp_path / "app/B/UsesConstPlain.php",
        "<?php\nnamespace App\\B;\n"
        "use const Vendor\\Sdk\\LIMIT;\n"
        "class UsesConstPlain extends LIMIT {}\n",
    )
    result = extract([group, plain], cache_root=tmp_path)

    group_bases = _targets(result, "inherits", "usesconstgroup")
    plain_bases = _targets(result, "inherits", "usesconstplain")
    assert len(group_bases) == 1 and len(plain_bases) == 1, (group_bases, plain_bases)
    assert group_bases[0] is not None and plain_bases[0] is not None
    assert group_bases[0]["label"] == "LIMIT", group_bases[0]
    assert group_bases[0]["id"] == plain_bases[0]["id"], (group_bases, plain_bases)
    assert "Vendor\\Sdk\\LIMIT" not in _labels(result), sorted(_labels(result))


def test_php_group_use_function_with_multiple_members(tmp_path: Path):
    # Both members of `use function A\{f, g};` are rejected, not just the first.
    group = _write(
        tmp_path / "app/A/Uses.php",
        "<?php\nnamespace App\\A;\n"
        "use function Vendor\\Sdk\\{Render, Compile};\n"
        "class UsesFirst extends Render {}\n"
        "class UsesSecond extends Compile {}\n",
    )
    result = extract([group], cache_root=tmp_path)

    labels = _labels(result)
    assert "Vendor\\Sdk\\Render" not in labels, sorted(labels)
    assert "Vendor\\Sdk\\Compile" not in labels, sorted(labels)
    assert {"Render", "Compile"} <= labels, sorted(labels)


def test_php_group_use_class_still_claims_the_short_name(tmp_path: Path):
    # Guard against over-subtraction: a *class* group use (no keyword) must keep
    # claiming its members. `App\Cms\Page` is the import; `App\Models\Page` is
    # the decoy the bare-name rewire would otherwise collapse onto.
    _write(
        tmp_path / "app/Cms/Page.php",
        "<?php\nnamespace App\\Cms;\nclass Page {}\n",
    )
    decoy = _write(
        tmp_path / "app/Models/Page.php",
        "<?php\nnamespace App\\Models;\nclass Page {}\n",
    )
    editor = _write(
        tmp_path / "app/Edit/Editor.php",
        "<?php\nnamespace App\\Edit;\n"
        "use App\\Cms\\{Page};\n"
        "class Editor extends Page {}\n",
    )
    result = extract(
        [tmp_path / "app/Cms/Page.php", decoy, editor],
        cache_root=tmp_path,
    )

    bases = _targets(result, "inherits", "editor")
    assert len(bases) == 1 and bases[0] is not None, bases
    assert "Cms" in bases[0].get("source_file", ""), bases[0]

    decoy_ids = {
        n["id"] for n in result["nodes"]
        if n.get("label") == "Page" and "Models" in (n.get("source_file") or "")
    }
    assert decoy_ids, result["nodes"]
    assert not [
        e for e in result["edges"]
        if e.get("relation") == "inherits" and e.get("target") in decoy_ids
    ], "the decoy App\\Models\\Page must get no inherits edge"
