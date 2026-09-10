"""PHP `use`-import capture (#19).

Every assertion goes through a public extract seam. These are metadata-shape
tests: at capture time the `imports` edges themselves (their targets) must stay
exactly as they were — only `target_fqn` / `alias` / `use_kind` are new. Since
#48 the *resolver* re-points class imports off that captured FQN, so the
capture-invariant test uses the single-file `extract_php()` seam.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract, extract_php


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _import_facts(result: dict) -> set[tuple[str | None, str | None, str | None]]:
    """(target_fqn, alias, use_kind) for every `imports` edge in the graph."""
    facts = set()
    for e in result["edges"]:
        if e.get("relation") != "imports":
            continue
        md = e.get("metadata") or {}
        facts.add((md.get("target_fqn"), md.get("alias"), md.get("use_kind")))
    return facts


def _labels(result: dict) -> set[str]:
    return {n.get("label") for n in result["nodes"]}


def test_php_plain_use_captures_target_fqn(tmp_path: Path):
    f = _write(
        tmp_path / "app/Http/I.php",
        "<?php\nnamespace App\\Http;\nuse A\\B\\C;\nclass I {}\n",
    )
    result = extract([f], cache_root=tmp_path)

    imports = [e for e in result["edges"] if e.get("relation") == "imports"]
    assert len(imports) == 1, imports
    md = imports[0].get("metadata") or {}
    assert md.get("target_fqn") == "A\\B\\C", md
    assert md.get("use_kind") == "class", md
    assert "alias" not in md, md


def test_php_aliased_use_captures_alias_and_target_fqn(tmp_path: Path):
    f = _write(
        tmp_path / "app/Http/I.php",
        "<?php\nnamespace App\\Http;\nuse A\\B\\C as D;\nclass I {}\n",
    )
    result = extract([f], cache_root=tmp_path)

    assert _import_facts(result) == {("A\\B\\C", "D", "class")}


def test_php_group_use_captures_each_member_fqn(tmp_path: Path):
    f = _write(
        tmp_path / "app/Http/I.php",
        "<?php\nnamespace App\\Http;\nuse A\\{B, C};\nclass I {}\n",
    )
    result = extract([f], cache_root=tmp_path)

    assert _import_facts(result) == {
        ("A\\B", None, "class"),
        ("A\\C", None, "class"),
    }


def test_php_aliased_group_use_puts_the_alias_on_the_right_member(tmp_path: Path):
    f = _write(
        tmp_path / "app/Http/I.php",
        "<?php\nnamespace App\\Http;\nuse A\\{B, C as X};\nclass I {}\n",
    )
    result = extract([f], cache_root=tmp_path)

    assert _import_facts(result) == {
        ("A\\B", None, "class"),
        ("A\\C", "X", "class"),
    }


def test_php_leading_backslash_use_is_normalized(tmp_path: Path):
    f = _write(
        tmp_path / "app/Http/I.php",
        "<?php\nnamespace App\\Http;\nuse \\Rooted\\Thing;\nclass I {}\n",
    )
    result = extract([f], cache_root=tmp_path)

    assert _import_facts(result) == {("Rooted\\Thing", None, "class")}


def test_php_use_function_and_const_do_not_enter_the_class_name_map(tmp_path: Path):
    # `Base` is the control: a plain `use` DOES claim the short name, so the
    # supertype reference is re-pointed onto the FQN-labeled external stub.
    # `Render`/`Limit` come in via `use function` / `use const`, which must not
    # claim a class name — their supertype references stay on the bare stub.
    f = _write(
        tmp_path / "app/Http/I.php",
        "<?php\nnamespace App\\Http;\n"
        "use function Vendor\\Sdk\\Render;\n"
        "use const Vendor\\Sdk\\Limit;\n"
        "use Vendor\\Sdk\\Base;\n"
        "class I extends Render implements Limit {}\n"
        "class J extends Base {}\n",
    )
    result = extract([f], cache_root=tmp_path)

    assert _import_facts(result) == {
        ("Vendor\\Sdk\\Render", None, "function"),
        ("Vendor\\Sdk\\Limit", None, "const"),
        ("Vendor\\Sdk\\Base", None, "class"),
    }

    labels = _labels(result)
    assert "Vendor\\Sdk\\Base" in labels, labels
    assert "Vendor\\Sdk\\Render" not in labels, labels
    assert "Vendor\\Sdk\\Limit" not in labels, labels
    assert {"Render", "Limit"} <= labels, labels


def test_php_trait_use_inside_a_class_body_is_not_an_import(tmp_path: Path):
    f = _write(
        tmp_path / "app/Http/I.php",
        "<?php\nnamespace App\\Http;\n"
        "use A\\B\\C;\n"
        "class I {\n    use Tr;\n}\n",
    )
    result = extract([f], cache_root=tmp_path)

    # The file-level `use` is the only import; the trait mixin is not one.
    assert _import_facts(result) == {("A\\B\\C", None, "class")}
    assert any(e.get("relation") == "mixes_in" for e in result["edges"]), result["edges"]


def test_php_import_edge_targets_are_unchanged_by_metadata_capture(tmp_path: Path):
    # Regression guard: capturing the FQN must not re-point the edge. At capture
    # time the targets stay keyed on the imported short name exactly as before —
    # re-pointing is the resolver's job (see the companion test below).
    f = _write(
        tmp_path / "lib.php",
        "<?php\nuse A\\B\\C;\nuse A\\B\\C2 as D;\nuse A\\{B2, C3 as X};\n"
        "use function Vendor\\Sdk\\Render;\nclass I {}\n",
    )
    result = extract_php(f)

    targets = sorted(
        e["target"] for e in result["edges"] if e.get("relation") == "imports"
    )
    assert targets == ["b2", "c", "c2", "c3", "render"], targets


def test_php_class_imports_are_repointed_onto_their_target_fqn(tmp_path: Path):
    # #48: the resolver re-points class `imports` edges from their own
    # `target_fqn`. None of these FQNs exist in the corpus, so each parks on its
    # own FQN-labeled external stub instead of dangling on a bare short name
    # that the legacy rewire could collapse onto an unrelated class.
    # `use function` targets are not types and are left alone.
    f = _write(
        tmp_path / "lib.php",
        "<?php\nuse A\\B\\C;\nuse A\\B\\C2 as D;\nuse A\\{B2, C3 as X};\n"
        "use function Vendor\\Sdk\\Render;\nclass I {}\n",
    )
    result = extract([f], cache_root=tmp_path)

    targets = sorted(
        e["target"] for e in result["edges"] if e.get("relation") == "imports"
    )
    assert targets == ["a_b2", "a_b_c", "a_b_c2", "a_c3", "render"], targets
    assert {"A\\B\\C", "A\\B\\C2", "A\\B2", "A\\C3"} <= _labels(result), _labels(result)
