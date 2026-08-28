from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _node_by_id(result: dict, nid: str) -> dict | None:
    return next((n for n in result["nodes"] if n.get("id") == nid), None)


def _imports_from(result: dict, needle: str) -> list[dict]:
    return [
        e for e in result["edges"]
        if e["relation"] == "imports" and needle in e.get("source_file", "")
    ]


def test_php_import_only_used_as_class_const_lands_on_the_real_class(tmp_path: Path):
    # #48 (RC2 of #46): `use App\Repo\DbFooRepository;` used only via `::class`
    # mints no stub node for the imported name, so the repoint pass used to skip
    # the edge (no `stub_label` entry) and the bare target dangled — even though
    # the real class node exists in the corpus. The edge's own `target_fqn`
    # metadata is enough to resolve it.
    repo = _write(
        tmp_path / "app/Repo/DbFooRepository.php",
        "<?php\nnamespace App\\Repo;\nclass DbFooRepository {}\n",
    )
    only_import = _write(
        tmp_path / "app/Uses/OnlyImport.php",
        "<?php\nnamespace App\\Uses;\n"
        "use App\\Repo\\DbFooRepository;\n"
        "class OnlyImport {\n"
        "    public function name(): string { return DbFooRepository::class; }\n"
        "}\n",
    )
    result = extract([repo, only_import], cache_root=tmp_path)

    real = next(
        n for n in result["nodes"]
        if n.get("label") == "DbFooRepository" and n.get("source_file")
    )

    imports = _imports_from(result, "OnlyImport.php")
    assert len(imports) == 1, "expected exactly one imports edge from OnlyImport.php"
    edge = imports[0]
    assert edge["target"] == real["id"], (
        "imports edge still dangles on the bare short name instead of the real class node"
    )
    assert _node_by_id(result, edge["target"]) is not None


def test_php_unresolvable_import_parks_on_fqn_stub_not_a_same_short_name_class(tmp_path: Path):
    # #48 guard: resolving from `target_fqn` must never bare-match a *different*
    # type that happens to share the short name. `Vendor\Pkg\Page` is external,
    # so the edge parks on an FQN-labeled sourceless stub, never on App\Models\Page.
    page = _write(
        tmp_path / "app/Models/Page.php",
        "<?php\nnamespace App\\Models;\nclass Page {}\n",
    )
    consumer = _write(
        tmp_path / "app/Uses/Renderer.php",
        "<?php\nnamespace App\\Uses;\n"
        "use Vendor\\Pkg\\Page;\n"
        "class Renderer {\n"
        "    public function name(): string { return Page::class; }\n"
        "}\n",
    )
    result = extract([page, consumer], cache_root=tmp_path)

    internal = next(
        n for n in result["nodes"]
        if n.get("label") == "Page" and n.get("source_file")
    )

    imports = _imports_from(result, "Renderer.php")
    assert len(imports) == 1
    edge = imports[0]
    assert edge["target"] != internal["id"], (
        "external import wrongly merged onto the same-short-name internal class"
    )
    tgt = _node_by_id(result, edge["target"])
    assert tgt is not None, "unresolvable import must park on a node, not dangle"
    assert not tgt.get("source_file")
    assert tgt.get("label") == "Vendor\\Pkg\\Page"


def test_php_aliased_import_resolves_through_the_edge_fqn(tmp_path: Path):
    # The alias spelling never matches the edge's bare target id, so the pre-#48
    # path could only guess `<referencing namespace>\<short name>`. The edge's
    # own `target_fqn` carries the truth.
    repo = _write(
        tmp_path / "app/Repo/DbFooRepository.php",
        "<?php\nnamespace App\\Repo;\nclass DbFooRepository {}\n",
    )
    consumer = _write(
        tmp_path / "app/Uses/Aliased.php",
        "<?php\nnamespace App\\Uses;\n"
        "use App\\Repo\\DbFooRepository as Db;\n"
        "class Aliased {\n"
        "    public function name(): string { return Db::class; }\n"
        "}\n",
    )
    result = extract([repo, consumer], cache_root=tmp_path)

    real = next(
        n for n in result["nodes"]
        if n.get("label") == "DbFooRepository" and n.get("source_file")
    )
    imports = _imports_from(result, "Aliased.php")
    assert len(imports) == 1
    assert imports[0]["target"] == real["id"]


def test_php_import_repoint_never_prunes_an_unrelated_node_sharing_the_short_name(tmp_path: Path):
    # #48 guard: before the fix, `repointed_from` could only ever collect ids
    # that `stub_label` had just resolved, i.e. sourceless stubs. Resolving an
    # import off its metadata means the vacated target may be a bare
    # `_make_id(<short name>)` that no node of ours ever owned — and that id can
    # collide with a real, sourced, edgeless node (`Page.md` -> id `page`). The
    # orphan prune must not delete it just because an unrelated `use` line
    # mentioned the same short name.
    doc = _write(tmp_path / "Page.md", "Some prose about pages.\n")
    consumer = _write(
        tmp_path / "app/U.php",
        "<?php\nnamespace App;\n"
        "use Vendor\\Pkg\\Page;\n"
        "class U {\n"
        "    public function n(): string { return Page::class; }\n"
        "}\n",
    )
    result = extract([doc, consumer], cache_root=tmp_path)

    ids = {n.get("id") for n in result["nodes"]}
    assert "page" in ids, (
        "the unrelated Page.md node was pruned by the imports repoint"
    )
    # …and the import still got its own external stub.
    assert "vendor_pkg_page" in ids, ids


def test_php_use_function_import_is_not_resolved_as_a_type(tmp_path: Path):
    # `use function` / `use const` targets are not class FQNs: they must not be
    # fed through the type-resolution map (nor invent an external *type* stub
    # that shadows a real class of the same short name).
    helpers = _write(
        tmp_path / "app/Support/helpers.php",
        "<?php\nnamespace App\\Support;\nfunction render() { return 1; }\n",
    )
    consumer = _write(
        tmp_path / "app/Uses/FnUser.php",
        "<?php\nnamespace App\\Uses;\n"
        "use function App\\Support\\render;\n"
        "class FnUser {\n"
        "    public function go(): int { return render(); }\n"
        "}\n",
    )
    result = extract([helpers, consumer], cache_root=tmp_path)

    imports = _imports_from(result, "FnUser.php")
    assert len(imports) == 1
    edge = imports[0]
    assert edge.get("metadata", {}).get("use_kind") == "function"
    tgt = _node_by_id(result, edge["target"])
    # Either it stayed on its bare short-name target (possibly dangling, as
    # before #48) or it resolved to the function itself — but never to a
    # sourceless stub labeled with the *class*-resolution FQN of another file.
    if tgt is not None:
        assert tgt.get("source_file"), (
            "a `use function` import must not be parked on a synthesized type stub"
        )
