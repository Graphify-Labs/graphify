from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _node_by_id(result: dict, nid: str) -> dict | None:
    return next((n for n in result["nodes"] if n.get("id") == nid), None)


def _class_defs(result: dict, label: str) -> list[dict]:
    return [
        n for n in result["nodes"]
        if n.get("label") == label and n.get("source_file")
    ]


def test_php_external_namespaced_base_does_not_collapse_onto_internal_class(tmp_path: Path):
    # #1923: `App\Models\Page` (internal) and `Filament\Pages\Page` (external,
    # via `use`) share the simple name `Page`. The bare-name rewire must NOT
    # collapse the external supertype reference onto the only internal `Page`.
    model = _write(
        tmp_path / "app/Models/Page.php",
        "<?php\nnamespace App\\Models;\nclass Page extends Model {}\n",
    )
    page = _write(
        tmp_path / "app/Filament/Pages/ManageSiteSettings.php",
        "<?php\nnamespace App\\Filament\\Pages;\n"
        "use Filament\\Pages\\Page;\n"
        "class ManageSiteSettings extends Page {}\n",
    )
    result = extract([model, page], cache_root=tmp_path)

    # Exactly one internal `Page` definition, and it is App\Models\Page.
    page_defs = _class_defs(result, "Page")
    assert len(page_defs) == 1
    internal_page_id = page_defs[0]["id"]
    assert "Models" in page_defs[0]["source_file"]

    inherits = [
        e for e in result["edges"]
        if e["relation"] == "inherits" and "managesitesettings" in e.get("source", "").lower()
    ]
    assert inherits, "expected an inherits edge from ManageSiteSettings"
    for e in inherits:
        assert e["target"] != internal_page_id, (
            "inherits wrongly collapsed onto the internal App\\Models\\Page (#1923)"
        )
        tgt = _node_by_id(result, e["target"])
        # It must point at a distinct, FQN-labeled external stub.
        assert tgt is not None and not tgt.get("source_file")
        assert tgt.get("label") == "Filament\\Pages\\Page"

    # The file-level import edge must not target the internal Page either.
    imports = [
        e for e in result["edges"]
        if e["relation"] == "imports" and "managesitesettings" in e.get("source", "").lower()
    ]
    for e in imports:
        assert e["target"] != internal_page_id


def test_php_ambiguous_base_disambiguated_by_use(tmp_path: Path):
    # Two internal same-named `Page` classes; a `use` picks the right one.
    _write(
        tmp_path / "app/Models/Page.php",
        "<?php\nnamespace App\\Models;\nclass Page {}\n",
    )
    _write(
        tmp_path / "app/Cms/Page.php",
        "<?php\nnamespace App\\Cms;\nclass Page {}\n",
    )
    editor = _write(
        tmp_path / "app/Cms/Editor.php",
        "<?php\nnamespace App\\Cms;\n"
        "use App\\Cms\\Page;\n"
        "class Editor extends Page {}\n",
    )
    result = extract(
        [tmp_path / "app/Models/Page.php", tmp_path / "app/Cms/Page.php", editor],
        cache_root=tmp_path,
    )

    inherits = [
        e for e in result["edges"]
        if e["relation"] == "inherits" and "editor" in e.get("source", "").lower()
    ]
    assert len(inherits) == 1
    tgt = _node_by_id(result, inherits[0]["target"])
    assert tgt is not None and tgt.get("source_file")
    assert "Cms" in tgt["source_file"] and "Models" not in tgt["source_file"]


def test_php_use_alias_resolves(tmp_path: Path):
    _write(
        tmp_path / "src/Foo/Bar.php",
        "<?php\nnamespace Foo;\nclass Bar {}\n",
    )
    x = _write(
        tmp_path / "src/App/X.php",
        "<?php\nnamespace App;\n"
        "use Foo\\Bar as Baz;\n"
        "class X extends Baz {}\n",
    )
    result = extract([tmp_path / "src/Foo/Bar.php", x], cache_root=tmp_path)

    inherits = [
        e for e in result["edges"]
        if e["relation"] == "inherits" and "_x" in e.get("source", "").lower()
    ]
    assert inherits
    tgt = _node_by_id(result, inherits[0]["target"])
    assert tgt is not None and tgt.get("source_file")
    assert "Foo" in tgt["source_file"]


def test_php_fully_qualified_base_resolves(tmp_path: Path):
    _write(
        tmp_path / "app/Models/Page.php",
        "<?php\nnamespace App\\Models;\nclass Page {}\n",
    )
    y = _write(
        tmp_path / "app/Http/Y.php",
        "<?php\nnamespace App\\Http;\n"
        "class Y extends \\App\\Models\\Page {}\n",
    )
    result = extract([tmp_path / "app/Models/Page.php", y], cache_root=tmp_path)

    inherits = [
        e for e in result["edges"]
        if e["relation"] == "inherits" and "_y" in e.get("source", "").lower()
    ]
    assert inherits
    tgt = _node_by_id(result, inherits[0]["target"])
    assert tgt is not None and tgt.get("source_file")
    assert "Models" in tgt["source_file"]


def test_php_plain_no_namespace_inheritance_preserved(tmp_path: Path):
    # Guards the legacy unique-label rewire path: no namespaces anywhere.
    base = _write(tmp_path / "src/Base.php", "<?php\nclass Base {}\n")
    child = _write(tmp_path / "src/Child.php", "<?php\nclass Child extends Base {}\n")
    result = extract([base, child], cache_root=tmp_path)

    inherits = [e for e in result["edges"] if e["relation"] == "inherits"]
    assert inherits
    tgt = _node_by_id(result, inherits[0]["target"])
    assert tgt is not None and tgt.get("source_file"), (
        "no-namespace inheritance must still resolve to the real Base def"
    )
    assert tgt.get("label") == "Base"
