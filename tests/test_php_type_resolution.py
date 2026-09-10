from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import extract, extract_php
from graphify.extractors.resolution import _resolve_php_type_references


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


def test_php_import_resolves_when_target_name_prefixes_sibling_classes(tmp_path: Path):
    pivot = _write(
        tmp_path / "src/Pivot.php",
        "<?php\nnamespace App\\Entities;\nclass Pivot {}\n",
    )
    importer = _write(
        tmp_path / "src/ModelWithRelation.php",
        "<?php\nnamespace App\\Models;\n"
        "use App\\Entities\\Pivot;\n"
        "class ModelWithRelation {}\n",
    )
    siblings = [
        _write(
            tmp_path / f"src/{name}.php",
            f"<?php\nnamespace App\\Repositories;\nclass {name} {{}}\n",
        )
        for name in ("PivotRepository", "PivotRepositoryEloquent", "PivotValidator")
    ]

    result = extract([pivot, importer, *siblings], cache_root=tmp_path)
    pivot_id = _class_defs(result, "Pivot")[0]["id"]
    imports = [
        edge
        for edge in result["edges"]
        if edge["relation"] == "imports"
        and "modelwithrelation" in edge.get("source", "").lower()
    ]

    assert len(imports) == 1
    assert imports[0]["target"] == pivot_id


@pytest.mark.parametrize(
    ("kind", "symbol", "alias"),
    [
        ("function", "slug", "s"),
        ("const", "LIMIT", "L"),
    ],
    ids=["function", "const"],
)
def test_php_grouped_symbol_aliases_are_not_class_imports(
    tmp_path: Path,
    kind: str,
    symbol: str,
    alias: str,
):
    user = _write(
        tmp_path / "User.php",
        "<?php\nnamespace App;\n"
        f"use {kind} App\\Helpers\\{{{symbol} as {alias}}};\n",
    )
    local = _write(
        tmp_path / "Local.php",
        f"<?php\nnamespace App;\nclass {alias} {{}}\n",
    )
    alias_id = alias.lower()
    class_id = f"local_{alias_id}"
    per_file = [
        {
            "nodes": [{"id": "user", "label": "User.php", "source_file": "User.php"}],
            "edges": [],
        },
        {
            "nodes": [{"id": class_id, "label": alias, "source_file": "Local.php"}],
            "edges": [],
        },
    ]
    nodes = [
        {"id": "user", "label": "User.php", "source_file": "User.php"},
        {"id": class_id, "label": alias, "source_file": "Local.php"},
        {"id": alias_id, "label": alias, "source_file": ""},
    ]
    edges = [{
        "source": "user",
        "target": alias_id,
        "relation": "imports",
        "source_file": "User.php",
        "_php_symbol_import": True,
    }]

    _resolve_php_type_references(per_file, [user, local], nodes, edges)

    false_fqn = f"App\\Helpers\\{symbol}"
    assert edges[0]["target"] == alias_id
    assert false_fqn not in {node.get("label") for node in nodes}


@pytest.mark.parametrize(
    ("kind", "symbol", "class_name"),
    [
        ("function", "slug", "Slug"),
        ("const", "LIMIT", "Limit"),
    ],
    ids=["function", "const"],
)
def test_php_grouped_symbol_import_does_not_share_class_rewire(
    tmp_path: Path,
    kind: str,
    symbol: str,
    class_name: str,
):
    class_file = _write(
        tmp_path / f"{class_name}.php",
        f"<?php\nnamespace App;\nclass {class_name} {{}}\n",
    )
    user = _write(
        tmp_path / "User.php",
        "<?php\nnamespace App;\n"
        f"use {kind} Vendor\\Symbols\\{{{symbol}}};\n"
        f"class User extends {class_name} {{}}\n",
    )

    result = extract([class_file, user], cache_root=tmp_path, parallel=False)

    class_id = next(
        node["id"]
        for node in result["nodes"]
        if node.get("label") == class_name and node.get("source_file")
    )
    imports = [
        edge
        for edge in result["edges"]
        if edge["relation"] == "imports" and edge.get("source_file") == "User.php"
    ]
    inherits = [
        edge
        for edge in result["edges"]
        if edge["relation"] == "inherits" and edge.get("source_file") == "User.php"
    ]

    assert [edge["target"] for edge in imports] == [symbol.lower()]
    assert [edge["target"] for edge in inherits] == [class_id]
    assert all("_php_symbol_import" not in edge for edge in result["edges"])


def test_php_symbol_import_does_not_hide_same_named_class_import(tmp_path: Path):
    user = _write(
        tmp_path / "User.php",
        "<?php\nnamespace App;\n"
        "use Vendor\\Types\\Slug; use function Vendor\\Functions\\slug;\n",
    )

    result = extract([user], cache_root=tmp_path, parallel=False)

    import_targets = {
        edge["target"]
        for edge in result["edges"]
        if edge["relation"] == "imports"
    }
    assert import_targets == {"vendor_types_slug", "slug"}


def test_php_mixed_group_preserves_same_named_class_and_function_imports(tmp_path: Path):
    user = _write(
        tmp_path / "User.php",
        "<?php\nnamespace App;\n"
        "use Vendor\\Package\\{Thing, function Thing};\n",
    )

    result = extract([user], cache_root=tmp_path, parallel=False)

    import_targets = {
        edge["target"]
        for edge in result["edges"]
        if edge["relation"] == "imports"
    }
    assert import_targets == {"vendor_package_thing", "thing"}


def test_php_symbol_import_survives_multi_namespace_resolution_skip(tmp_path: Path):
    class_file = _write(
        tmp_path / "Slug.php",
        "<?php\nnamespace Other;\nclass Slug {}\n",
    )
    user = _write(
        tmp_path / "User.php",
        "<?php\n"
        "namespace First {\n"
        "    use function Vendor\\Symbols\\{slug};\n"
        "    class Consumer extends Slug {}\n"
        "}\n"
        "namespace Second { class User {} }\n",
    )

    result = extract([class_file, user], cache_root=tmp_path, parallel=False)

    imports = [
        edge
        for edge in result["edges"]
        if edge["relation"] == "imports" and edge.get("source_file") == "User.php"
    ]
    assert [edge["target"] for edge in imports] == ["slug"]
    assert all("_php_symbol_import" not in edge for edge in result["edges"])


def test_php_single_file_extractor_hides_symbol_import_marker(tmp_path: Path):
    user = _write(
        tmp_path / "User.php",
        "<?php\nuse function Vendor\\Symbols\\{slug};\n",
    )

    result = extract_php(user)

    assert all("_php_symbol_import" not in edge for edge in result["edges"])


@pytest.mark.parametrize(
    ("use_statement", "expected_targets"),
    [
        ("use function App\\Helpers\\{slug};", {"slug"}),
        ("use const App\\Helpers\\{LIMIT};", {"limit"}),
        ("use function App\\Helpers\\slug, App\\Helpers\\trim;", {"slug", "trim"}),
        ("use const App\\Helpers\\LIMIT, App\\Helpers\\MAX;", {"limit", "max"}),
    ],
    ids=["grouped-function", "grouped-const", "comma-function", "comma-const"],
)
def test_php_symbol_import_kind_applies_to_all_declaration_clauses(
    tmp_path: Path,
    use_statement: str,
    expected_targets: set[str],
):
    user = _write(
        tmp_path / "User.php",
        f"<?php\nnamespace App;\n{use_statement}\n",
    )

    result = extract([user], cache_root=tmp_path, parallel=False)

    import_targets = {
        edge["target"]
        for edge in result["edges"]
        if edge["relation"] == "imports"
    }
    assert import_targets == expected_targets
    assert not {
        node.get("label")
        for node in result["nodes"]
        if node.get("label", "").startswith("App\\Helpers\\")
    }


def test_php_mixed_group_keeps_only_class_import_in_use_map(tmp_path: Path):
    user = _write(
        tmp_path / "User.php",
        "<?php\nnamespace App;\n"
        "use App\\Helpers\\{Thing, function slug, const LIMIT};\n",
    )

    result = extract([user], cache_root=tmp_path, parallel=False)

    import_targets = {
        edge["target"]
        for edge in result["edges"]
        if edge["relation"] == "imports"
    }
    assert import_targets == {"app_helpers_thing", "slug", "limit"}
    assert {
        node.get("label")
        for node in result["nodes"]
        if node.get("label", "").startswith("App\\Helpers\\")
    } == {"App\\Helpers\\Thing"}
