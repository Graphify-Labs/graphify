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


# ── `use A\B\C as D`: the alias must not mint a second identity (#3421) ───────

def _imports_from(result: dict, source_fragment: str) -> list[dict]:
    return [
        e for e in result["edges"]
        if e["relation"] == "imports"
        and source_fragment in e.get("source", "").lower()
    ]


def test_php_aliased_external_import_shares_target_with_plain_import(tmp_path: Path):
    """The reported repro: two files importing GuzzleHttp\\Client, one aliased.

    The import edge target was derived from the last segment of the imported
    name, so the aliased file's edge landed on a bare `client` that nothing else
    used — `GuzzleHttp\\Client` became two nodes and neither file was reachable
    from the other's traversal (#3421).
    """
    a = _write(
        tmp_path / "src/A.php",
        "<?php\nnamespace App;\n"
        "use GuzzleHttp\\Client;\n"
        "class A { public function __construct(private Client $c) {} }\n",
    )
    b = _write(
        tmp_path / "src/B.php",
        "<?php\nnamespace App;\n"
        "use GuzzleHttp\\Client as HttpClient;\n"
        "class B { public function __construct(private HttpClient $c) {} }\n",
    )
    result = extract([a, b], cache_root=tmp_path)

    plain = _imports_from(result, "src_a")
    aliased = _imports_from(result, "src_b")
    assert len(plain) == 1 and len(aliased) == 1
    assert aliased[0]["target"] == plain[0]["target"], (
        "an alias is a file-local binding; it must not give the imported class a "
        "second identity"
    )
    tgt = _node_by_id(result, aliased[0]["target"])
    assert tgt is not None and tgt.get("label") == "GuzzleHttp\\Client"
    # The bare-name node the alias used to strand is gone entirely.
    assert _node_by_id(result, "client") is None


def test_php_aliased_import_of_internal_class_resolves_to_definition(tmp_path: Path):
    """An aliased `use` of a class in the same project points at that class's
    own node, not at a bare-name stub."""
    user = _write(
        tmp_path / "src/Models/User.php",
        "<?php\nnamespace App\\Models;\nclass User {}\n",
    )
    b = _write(
        tmp_path / "src/B.php",
        "<?php\nnamespace App;\n"
        "use App\\Models\\User as Member;\n"
        "class B { public function __construct(private Member $u) {} }\n",
    )
    result = extract([user, b], cache_root=tmp_path)

    user_id = _class_defs(result, "User")[0]["id"]
    aliased = _imports_from(result, "src_b")
    assert len(aliased) == 1
    assert aliased[0]["target"] == user_id


def test_php_two_aliased_imports_of_same_bare_name_stay_distinct(tmp_path: Path):
    """The symptom on the reporter's Laravel project: aliasing exists precisely
    to disambiguate two classes sharing a simple name, and both edges collapsed
    onto one dangling bare id (`session`, 44 edges)."""
    session = _write(
        tmp_path / "src/Models/Session.php",
        "<?php\nnamespace App\\Models;\nclass Session {}\n",
    )
    ctrl = _write(
        tmp_path / "src/Http/Controller.php",
        "<?php\nnamespace App\\Http;\n"
        "use App\\Models\\Session as LocalSession;\n"
        "use Shopify\\Auth\\Session as ShopifySession;\n"
        "class Controller { public function run(LocalSession $a, ShopifySession $b) {} }\n",
    )
    result = extract([session, ctrl], cache_root=tmp_path)

    node_ids = {n["id"] for n in result["nodes"]}
    imports = _imports_from(result, "src_http_controller")
    targets = {e["target"] for e in imports}
    assert len(targets) == 2, f"the two aliases collapsed onto one target: {targets}"
    assert not targets - node_ids, f"dangling import endpoint(s): {targets - node_ids}"

    internal_id = _class_defs(result, "Session")[0]["id"]
    assert internal_id in targets
    external = (targets - {internal_id}).pop()
    assert _node_by_id(result, external)["label"] == "Shopify\\Auth\\Session"


def test_php_aliased_group_use_resolves(tmp_path: Path):
    """`use Ns\\{A, Sub\\B as C}` — the alias sits inside a group clause, whose
    FQN is the group prefix plus the clause's own path."""
    ctrl = _write(
        tmp_path / "src/C.php",
        "<?php\nnamespace App;\n"
        "use GuzzleHttp\\{Client, Psr7\\Request as Req};\n"
        "class C { public function go(Client $a, Req $b) {} }\n",
    )
    result = extract([ctrl], cache_root=tmp_path)

    labels = {
        _node_by_id(result, e["target"])["label"]
        for e in _imports_from(result, "src_c")
    }
    assert labels == {"GuzzleHttp\\Client", "GuzzleHttp\\Psr7\\Request"}


def test_php_aliased_function_and_const_imports_keep_bare_name(tmp_path: Path):
    """`use function`/`use const` are symbol imports, not class imports, so
    their alias is deliberately NOT used: the imported name's last segment stays
    the bare name the unique-label rewire matches on."""
    helper = _write(
        tmp_path / "src/Helpers.php",
        "<?php\nnamespace App\\Helpers;\nfunction slug(string $s): string { return $s; }\n",
    )
    user = _write(
        tmp_path / "src/U.php",
        "<?php\nnamespace App;\n"
        "use function App\\Helpers\\slug as s;\n"
        "use const App\\Config\\VERSION as V;\n"
        "class U { public function go() { return s('x'); } }\n",
    )
    result = extract([helper, user], cache_root=tmp_path)

    targets = {e["target"] for e in _imports_from(result, "src_u")}
    assert "version" in targets, f"const import lost its bare name: {targets}"
    slug_node = next(
        (n for n in result["nodes"]
         if n.get("label") == "slug()" and n.get("source_file")), None)
    assert slug_node is not None
    assert slug_node["id"] in targets or "slug" in targets
