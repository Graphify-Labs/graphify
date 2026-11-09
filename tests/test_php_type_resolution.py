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


def test_php_aliased_import_edge_shares_target_with_plain_import(tmp_path: Path):
    """#3421: an `imports` edge for an aliased `use` clause always targeted
    the bare imported class name (the last segment of the qualified name),
    completely ignoring the alias. A file with a PLAIN `use GuzzleHttp\\Client;`
    and a file with an ALIASED `use GuzzleHttp\\Client as HttpClient;` both
    minted a stub keyed by "Client", so the resolver's alias -> FQN lookup
    (keyed by "httpclient" for the aliased file) missed and the aliased
    file's edge stayed stuck, unresolved, on the bare stub -- while the
    plain file's edge correctly resolved to the external FQN stub. Two
    files importing the SAME external class ended up with TWO different
    import targets, splitting the class identity (the exact real-world
    case an alias exists for: disambiguating two same-named classes from
    different namespaces)."""
    a = _write(
        tmp_path / "src/A.php",
        "<?php\nnamespace App;\n"
        "use GuzzleHttp\\Client;\n"
        "class A { public function __construct(private Client $client) {} }\n",
    )
    b = _write(
        tmp_path / "src/B.php",
        "<?php\nnamespace App;\n"
        "use GuzzleHttp\\Client as HttpClient;\n"
        "class B { public function __construct(private HttpClient $client) {} }\n",
    )
    result = extract([a, b], cache_root=tmp_path)

    imports = {
        e["source"]: e["target"]
        for e in result["edges"]
        if e["relation"] == "imports"
    }
    src_a_id = next(n["id"] for n in result["nodes"] if n.get("label") == "A.php")
    src_b_id = next(n["id"] for n in result["nodes"] if n.get("label") == "B.php")
    assert src_a_id in imports and src_b_id in imports
    assert imports[src_a_id] == imports[src_b_id], (
        f"plain and aliased imports of the same class split into different "
        f"targets: {imports}"
    )
    tgt = _node_by_id(result, imports[src_a_id])
    assert tgt is not None and tgt.get("label") == "GuzzleHttp\\Client"


def test_php_distinct_aliases_for_same_named_classes_do_not_collapse(tmp_path: Path):
    """The reason an alias exists at all: disambiguating two DIFFERENT
    classes that share a bare name (App\\Models\\Session vs
    Shopify\\Auth\\Session). Fixing #3421 by preferring the alias for an
    import edge's target must not go too far the other way and collapse
    genuinely different classes onto one node just because they were both
    imported under an alias."""
    a = _write(
        tmp_path / "src/A.php",
        "<?php\nnamespace App;\n"
        "use App\\Models\\Session as ModelSession;\n"
        "use Shopify\\Auth\\Session as ShopifySession;\n"
        "class A {\n"
        "    public function __construct(private ModelSession $m, private ShopifySession $s) {}\n"
        "}\n",
    )
    result = extract([a], cache_root=tmp_path)

    imports = {e["target"] for e in result["edges"] if e["relation"] == "imports"}
    labels = {_node_by_id(result, t).get("label") for t in imports}
    assert "App\\Models\\Session" in labels
    assert "Shopify\\Auth\\Session" in labels
    assert len(imports) == 2, f"distinct aliased classes collapsed onto one target: {imports}"


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
