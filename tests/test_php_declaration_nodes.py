"""PHP `interface` / `trait` / `enum` declarations mint canonical nodes (#47, RC1 of #46).

`_PHP_CONFIG.class_types` used to hold only `class_declaration`, so no node was
ever minted for a PHP interface, trait or enum. Every resolution pass that could
canonicalize an edge then had nothing to land on: the implements edge kept a bare
sourceless stub, `Foo::CONST` fan-in fragmented across per-file stubs, and
`imports`/parameter-type `references` parked on the file node (or, when the file
name differs from the type name, on a sourceless FQN-labeled stub).

The control experiment in #46 is the shape these tests pin: change
`interface FooRepository` to `class FooRepository` and every one of those edges
canonicalizes onto the single declaration node. Interfaces, traits and enums must
behave the same way.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _defs(result: dict, label: str) -> list[dict]:
    """Sourced (declaration) nodes carrying `label`."""
    return [n for n in result["nodes"] if n.get("label") == label and n.get("source_file")]


def _one_def(result: dict, label: str) -> dict:
    defs = _defs(result, label)
    assert len(defs) == 1, f"expected exactly one sourced `{label}` node, got {len(defs)}"
    return defs[0]


def _node_by_id(result: dict, nid: str) -> dict | None:
    return next((n for n in result["nodes"] if n.get("id") == nid), None)


def _edges(result: dict, relation: str) -> list[dict]:
    return [e for e in result["edges"] if e.get("relation") == relation]


def _repro_corpus(tmp_path: Path) -> list[Path]:
    """The 7-file minimal repro from #46, verbatim in shape."""
    return [
        _write(
            tmp_path / "app/Repo/FooRepository.php",
            "<?php\n\nnamespace App\\Repo;\n\n"
            "interface FooRepository\n{\n"
            "    public const BAR = 'bar';\n\n"
            "    public function find(int $id): mixed;\n}\n",
        ),
        _write(
            tmp_path / "app/Repo/DbFooRepository.php",
            "<?php\n\nnamespace App\\Repo;\n\n"
            "class DbFooRepository implements FooRepository\n{\n"
            "    public function find(int $id): mixed\n    {\n        return null;\n    }\n}\n",
        ),
        _write(
            tmp_path / "app/Uses/Consumer.php",
            "<?php\n\nnamespace App\\Uses;\n\nuse App\\Repo\\FooRepository;\n\n"
            "class Consumer\n{\n"
            "    public function __construct(FooRepository $repo)\n    {\n"
            "        $this->repo = $repo;\n    }\n\n"
            "    public function tag(): string\n    {\n        return FooRepository::BAR;\n    }\n}\n",
        ),
        _write(
            tmp_path / "app/Uses/Consumer2.php",
            "<?php\n\nnamespace App\\Uses;\n\nuse App\\Repo\\FooRepository;\n\n"
            "class Consumer2\n{\n"
            "    public function __construct(FooRepository $repo)\n    {\n"
            "        $this->repo = $repo;\n    }\n\n"
            "    public function tag(): string\n    {\n        return FooRepository::BAR;\n    }\n}\n",
        ),
        _write(
            tmp_path / "app/Repo/Extras.php",
            "<?php\n\nnamespace App\\Repo;\n\n"
            "trait Loggable\n{\n    public function log(string $m): void {}\n}\n\n"
            "enum Status: string\n{\n    case Active = 'active';\n}\n",
        ),
        _write(
            tmp_path / "app/Uses/Consumer3.php",
            "<?php\n\nnamespace App\\Uses;\n\nuse App\\Repo\\Loggable;\nuse App\\Repo\\Status;\n\n"
            "class Consumer3\n{\n    use Loggable;\n\n"
            "    public function s(): string\n    {\n        return Status::Active->value;\n    }\n}\n",
        ),
        _write(
            tmp_path / "app/Uses/OnlyImport.php",
            "<?php\n\nnamespace App\\Uses;\n\nuse App\\Repo\\DbFooRepository;\n\n"
            "class OnlyImport\n{\n"
            "    public function name(): string\n    {\n        return DbFooRepository::class;\n    }\n}\n",
        ),
    ]


def test_php_interface_declaration_is_the_canonical_edge_target(tmp_path: Path):
    # #47 criterion 1: `interface FooRepository` mints a sourced declaration node,
    # and implements / imports / references / references_constant all land on it —
    # matching the `class FooRepository` control from #46.
    result = extract(_repro_corpus(tmp_path), cache_root=tmp_path)

    iface = _one_def(result, "FooRepository")
    assert iface["source_file"].endswith("app/Repo/FooRepository.php")
    iface_id = iface["id"]

    # The interface's own method hangs off the interface, not the file.
    assert any(
        e["source"] == iface_id and e["relation"] == "method"
        for e in result["edges"]
    ), "interface method should attach to the interface node"

    implements = _edges(result, "implements")
    assert implements, "expected an implements edge from DbFooRepository"
    for e in implements:
        assert e["target"] == iface_id

    for relation in ("imports", "references", "references_constant"):
        landed = [
            e for e in _edges(result, relation)
            if (_node_by_id(result, e["target"]) or {}).get("label") in
            ("FooRepository", "App\\Repo\\FooRepository")
            or e["target"] == iface_id
        ]
        assert landed, f"expected at least one {relation} edge aimed at FooRepository"
        for e in landed:
            assert e["target"] == iface_id, (
                f"{relation} edge did not canonicalize onto the interface node: "
                f"{e['source']} --> {e['target']}"
            )

    # Cascade A / B: no sourceless FooRepository stub survives anywhere.
    stubs = [
        n for n in result["nodes"]
        if not n.get("source_file") and "foorepository" in n.get("id", "").lower()
    ]
    assert stubs == [], f"sourceless FooRepository stubs survived: {[n['id'] for n in stubs]}"

    # The loops above filter candidates by looking their target's LABEL up in the
    # node set, so an edge left pointing at a bare `foorepository` with no node at
    # all resolves to no label, drops out of `landed`, and is never checked. Close
    # that blind spot separately: a FooRepository edge target that names no node is
    # a regression whatever else canonicalized correctly.
    #
    # Matched on the id's last segment, not as a substring: the bare Cascade A id
    # (`foorepository`) and the Cascade B per-file salts (`<file>_php_foorepository`)
    # both end in it, while `dbfoorepository` — a different type, and the repro's
    # one legitimately dangling target until RC2 (#48) lands — does not.
    node_ids = {n["id"] for n in result["nodes"]}
    dangling = sorted(
        {
            e["target"] for e in result["edges"]
            if str(e.get("target", "")).lower().rsplit("_", 1)[-1] == "foorepository"
            and e["target"] not in node_ids
        }
    )
    assert dangling == [], f"FooRepository edge targets with no node: {dangling}"


def test_php_trait_and_enum_declared_in_a_differently_named_file(tmp_path: Path):
    # #47 criterion 2: `trait Loggable` and `enum Status` live in `Extras.php`
    # (filename != type name), so the id-collision accident that lets a class's
    # edges land on its file node cannot save them. Both need real nodes.
    result = extract(_repro_corpus(tmp_path), cache_root=tmp_path)

    loggable = _one_def(result, "Loggable")
    status = _one_def(result, "Status")
    assert loggable["source_file"].endswith("app/Repo/Extras.php")
    assert status["source_file"].endswith("app/Repo/Extras.php")

    mixes_in = _edges(result, "mixes_in")
    assert mixes_in, "expected a mixes_in edge from Consumer3"
    for e in mixes_in:
        assert e["target"] == loggable["id"]

    imports_by_target = {e["target"] for e in _edges(result, "imports")}
    assert loggable["id"] in imports_by_target, "trait import did not land on the trait node"

    # The trait's edges used to park on a sourceless `App\Repo\Loggable` FQN stub,
    # because `Extras.php` cannot absorb them by the id-collision accident that
    # saves a PSR-4-named class. No such stub may survive.
    assert not [
        n for n in result["nodes"]
        if not n.get("source_file") and n.get("label") in ("App\\Repo\\Loggable", "Loggable", "Status")
    ]

    # `enum Status` is imported by Consumer3 but only used as `Status::Active`, so
    # nothing mints a stub node for it. RC1 (#47) supplies the sourced node with
    # the FQN, and RC2 (#48) resolves the edge from its own `target_fqn` metadata
    # instead of a stub label — with both landed, the import canonicalizes onto
    # the enum's declaration node.
    enum_import = next(
        e for e in _edges(result, "imports")
        if (e.get("metadata") or {}).get("target_fqn") == "App\\Repo\\Status"
    )
    assert enum_import["target"] == status["id"], (
        "the enum's imports edge must land on the sourced declaration node "
        "now that RC1 (#47) and RC2 (#48) are both present"
    )


def test_php_enum_body_members_and_clauses(tmp_path: Path):
    # An enum's body is an `enum_declaration_list`, not the `declaration_list`
    # every other PHP declaration uses. Its methods, its `implements` clause and
    # its trait `use` must all be picked up regardless (#47 enum caveat).
    contract = _write(
        tmp_path / "app/Contracts/HasLabel.php",
        "<?php\nnamespace App\\Contracts;\ninterface HasLabel { public function label(): string; }\n",
    )
    trait = _write(
        tmp_path / "app/Support/Describes.php",
        "<?php\nnamespace App\\Support;\ntrait Describes { public function describe(): string { return ''; } }\n",
    )
    enum = _write(
        tmp_path / "app/Enums/Status.php",
        "<?php\nnamespace App\\Enums;\n"
        "use App\\Contracts\\HasLabel;\nuse App\\Support\\Describes;\n"
        "enum Status: string implements HasLabel\n{\n"
        "    use Describes;\n\n"
        "    case Active = 'active';\n\n"
        "    public function label(): string { return $this->value; }\n}\n",
    )
    result = extract([contract, trait, enum], cache_root=tmp_path)

    status = _one_def(result, "Status")
    has_label = _one_def(result, "HasLabel")
    describes = _one_def(result, "Describes")

    methods = [e for e in _edges(result, "method") if e["source"] == status["id"]]
    assert [
        (_node_by_id(result, e["target"]) or {}).get("label") for e in methods
    ] == [".label()"], "enum method did not attach to the enum node"

    assert [e["target"] for e in _edges(result, "implements")] == [has_label["id"]]
    assert [e["target"] for e in _edges(result, "mixes_in")] == [describes["id"]]


def test_php_interface_extends_qualified_interface_resolves(tmp_path: Path):
    # #47 criterion 4: the `_resolve_php_type_references` raw-scan only recognised
    # `class_declaration`, so an interface's `extends` clause was never recorded.
    # `interface Reader extends Sub\Repo` would then fall through to the
    # same-namespace guess and bind to the WRONG `Repo`.
    outer = _write(
        tmp_path / "app/Contracts/Repo.php",
        "<?php\nnamespace App\\Contracts;\ninterface Repo {}\n",
    )
    inner = _write(
        tmp_path / "app/Contracts/Sub/Repo.php",
        "<?php\nnamespace App\\Contracts\\Sub;\ninterface Repo {}\n",
    )
    reader = _write(
        tmp_path / "app/Contracts/Reader.php",
        "<?php\nnamespace App\\Contracts;\ninterface Reader extends Sub\\Repo {}\n",
    )
    result = extract([outer, inner, reader], cache_root=tmp_path)

    repos = _defs(result, "Repo")
    assert len(repos) == 2, "both interfaces must mint declaration nodes"
    by_dir = {("Sub" in n["source_file"]): n["id"] for n in repos}
    inherits = [
        e for e in _edges(result, "inherits")
        if "reader" in e.get("source", "").lower()
    ]
    assert inherits, "expected an inherits edge from Reader"
    for e in inherits:
        assert e["target"] == by_dir[True], (
            "interface-extends-interface resolved to the wrong Repo "
            "(raw-scan did not learn interface_declaration)"
        )


def test_php_enum_uses_qualified_trait_resolves(tmp_path: Path):
    # The twin of the test above, through an enum body instead of an interface
    # `extends`. The raw-scan reads trait `use` out of the declaration's body, and
    # an enum's body is an `enum_declaration_list` — so scanning only
    # `declaration_list` (`resolution.py:2707`) records no raw text for
    # `use Sub\Describes;`, and the same-namespace fallback then binds the rival
    # `App\Enums\Describes` silently.
    rival = _write(
        tmp_path / "app/Enums/Describes.php",
        "<?php\nnamespace App\\Enums;\ntrait Describes { public function d(): string { return 'rival'; } }\n",
    )
    real = _write(
        tmp_path / "app/Enums/Sub/Describes.php",
        "<?php\nnamespace App\\Enums\\Sub;\ntrait Describes { public function d(): string { return 'real'; } }\n",
    )
    enum = _write(
        tmp_path / "app/Enums/Status.php",
        "<?php\nnamespace App\\Enums;\n"
        "enum Status: string\n{\n"
        "    use Sub\\Describes;\n\n"
        "    case Active = 'active';\n}\n",
    )
    result = extract([rival, real, enum], cache_root=tmp_path)

    traits = _defs(result, "Describes")
    assert len(traits) == 2, "both traits must mint declaration nodes"
    by_dir = {("Sub" in n["source_file"]): n["id"] for n in traits}
    mixes_in = _edges(result, "mixes_in")
    assert mixes_in, "expected a mixes_in edge from Status"
    for e in mixes_in:
        assert e["target"] == by_dir[True], (
            "enum trait `use` resolved to the wrong Describes "
            "(raw-scan did not learn enum_declaration_list)"
        )
