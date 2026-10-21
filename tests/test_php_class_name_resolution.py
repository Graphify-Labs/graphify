"""PHP class names written in source must resolve by PHP's own name-resolution
rules, and ``Foo::class`` must produce an edge to the real declaration.

Before the fix, a ``Foo::class`` (or any ``Foo::BAR``) class-constant access only
linked when ``Foo`` was declared in the SAME file, so ``belongsTo(Client::class)``,
casts, route tuples and container bindings produced no edge. A leading-backslash
FQCN (``\\App\\Models\\X``) lost its namespace, and ``self``/``static`` in a type
position became a sourceless ``self`` stub instead of the enclosing class.

Every case has a same-named decoy class in another namespace, so a bare-name
coincidence cannot satisfy an assertion.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path: Path, files: dict[str, str]) -> dict:
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return extract(
        [tmp_path / n for n in files],
        cache_root=Path(tempfile.mkdtemp()),
        root=tmp_path,
        parallel=False,
    )


def _node(result: dict, label: str, file_name: str) -> dict:
    found = [
        n for n in result["nodes"]
        if n.get("label") == label and (n.get("source_file") or "").endswith(file_name)
    ]
    assert len(found) == 1, f"expected one {label!r} in {file_name}, got {found}"
    return found[0]


def _edges(result: dict, src: str, relation: str) -> list[dict]:
    return [e for e in result["edges"] if e["source"] == src and e["relation"] == relation]


_CLIENT = "<?php\nnamespace App\\Models;\nclass Client {}\n"
# Same simple name, different namespace: never the right answer below.
_DECOY = "<?php\nnamespace Vendor\\Other;\nclass Client {}\n"


def test_use_imported_class_constant_links_real_class(tmp_path):
    r = _extract(tmp_path, {
        "app/Models/Client.php": _CLIENT,
        "vendor/Other/Client.php": _DECOY,
        "app/Services/Svc.php": (
            "<?php\nnamespace App\\Services;\nuse App\\Models\\Client;\n"
            "class Svc {\n    public function run() { return [Client::class, 'index']; }\n}\n"),
    })
    run = _node(r, ".run()", "Svc.php")
    edges = _edges(r, run["id"], "references_constant")
    assert [e["target"] for e in edges] == [_node(r, "Client", "app/Models/Client.php")["id"]]
    assert edges[0]["confidence"] == "EXTRACTED"


def test_aliased_use_class_constant_links_real_class(tmp_path):
    r = _extract(tmp_path, {
        "app/Models/Client.php": _CLIENT,
        "vendor/Other/Client.php": _DECOY,
        "app/Services/Svc.php": (
            "<?php\nnamespace App\\Services;\nuse App\\Models\\Client as Customer;\n"
            "class Svc {\n    public function run() { return Customer::class; }\n}\n"),
    })
    run = _node(r, ".run()", "Svc.php")
    edges = _edges(r, run["id"], "references_constant")
    assert [e["target"] for e in edges] == [_node(r, "Client", "app/Models/Client.php")["id"]]


def test_same_namespace_class_constant_needs_no_use(tmp_path):
    r = _extract(tmp_path, {
        "app/Models/Client.php": _CLIENT,
        "vendor/Other/Client.php": _DECOY,
        "app/Models/Branch.php": (
            "<?php\nnamespace App\\Models;\nclass Branch {\n"
            "    public function client() { return $this->belongsTo(Client::class); }\n}\n"),
    })
    method = _node(r, ".client()", "Branch.php")
    edges = _edges(r, method["id"], "references_constant")
    assert [e["target"] for e in edges] == [_node(r, "Client", "app/Models/Client.php")["id"]]
    assert edges[0]["confidence"] == "EXTRACTED"


def test_leading_backslash_class_constant_and_type_hint(tmp_path):
    r = _extract(tmp_path, {
        "app/Models/Client.php": _CLIENT,
        "vendor/Other/Client.php": _DECOY,
        # Svc lives in App\Services and has no `use`: only the written FQCN
        # can reach App\Models\Client.
        "app/Services/Svc.php": (
            "<?php\nnamespace App\\Services;\nclass Svc {\n"
            "    public function run(\\App\\Models\\Client $c) {\n"
            "        return \\App\\Models\\Client::class;\n    }\n}\n"),
    })
    run = _node(r, ".run()", "Svc.php")
    real = _node(r, "Client", "app/Models/Client.php")["id"]
    assert [e["target"] for e in _edges(r, run["id"], "references_constant")] == [real]
    typed = [e for e in _edges(r, run["id"], "references") if e.get("context") == "parameter_type"]
    assert [e["target"] for e in typed] == [real]


def test_class_constant_in_property_default_and_array_arg(tmp_path):
    r = _extract(tmp_path, {
        "app/Models/Status.php": "<?php\nnamespace App\\Models;\nenum Status: string { case A = 'a'; }\n",
        "app/Models/Client.php": _CLIENT,
        "app/Models/Branch.php": (
            "<?php\nnamespace App\\Models;\nclass Branch {\n"
            "    protected $casts = ['status' => Status::class];\n"
            "    public function clients() { return $this->hasMany(Client::class); }\n}\n"),
    })
    branch = _node(r, "Branch", "Branch.php")
    clients = _node(r, ".clients()", "Branch.php")
    assert [e["target"] for e in _edges(r, branch["id"], "references_constant")] == [
        _node(r, "Status", "app/Models/Status.php")["id"]]
    assert [e["target"] for e in _edges(r, clients["id"], "references_constant")] == [
        _node(r, "Client", "app/Models/Client.php")["id"]]


def test_vendor_class_constant_makes_no_per_file_stub(tmp_path):
    # `Model` is imported from outside the corpus: the existing external-stub
    # convention applies (one FQN-labelled, sourceless node shared across files,
    # as for inherits/type hints). `Missing` has no declaration and no import:
    # nothing is guessed, so no edge and no node.
    r = _extract(tmp_path, {
        "app/Models/Model.php": "<?php\nnamespace App\\Models;\nclass Model {}\n",
        "app/Services/Svc.php": (
            "<?php\nnamespace App\\Services;\nuse Vendor\\Orm\\Model;\n"
            "class Svc {\n    public function run() { return [Model::class, Missing::class]; }\n}\n"),
    })
    run = _node(r, ".run()", "Svc.php")
    edges = _edges(r, run["id"], "references_constant")
    assert len(edges) == 1
    target = next(n for n in r["nodes"] if n["id"] == edges[0]["target"])
    assert target["label"] == "Vendor\\Orm\\Model"
    assert not target.get("source_file")
    # Never collapsed onto the unrelated internal App\Models\Model.
    assert target["id"] != _node(r, "Model", "app/Models/Model.php")["id"]
    assert not [n for n in r["nodes"] if n.get("label") == "Missing"]
    assert not [n for n in r["nodes"] if "svc_php" in n["id"] and not n.get("source_file")]


def test_self_and_static_resolve_to_enclosing_class(tmp_path):
    r = _extract(tmp_path, {
        "app/Models/Branch.php": (
            "<?php\nnamespace App\\Models;\nclass Branch {\n"
            "    public function me(self $x): static { return $this->hasMany(self::class); }\n"
            "    public function other() { return static::class; }\n}\n"),
    })
    branch = _node(r, "Branch", "Branch.php")["id"]
    me = _node(r, ".me()", "Branch.php")
    other = _node(r, ".other()", "Branch.php")
    assert [e["target"] for e in _edges(r, me["id"], "references_constant")] == [branch]
    assert [e["target"] for e in _edges(r, other["id"], "references_constant")] == [branch]
    refs = {e["target"] for e in _edges(r, me["id"], "references")}
    assert refs == {branch}
    assert not [n for n in r["nodes"] if n.get("label", "").lower() in ("self", "static")]


def test_top_level_and_closure_class_constants_attach_to_file_and_method(tmp_path):
    r = _extract(tmp_path, {
        "app/Models/Client.php": _CLIENT,
        "vendor/Other/Client.php": _DECOY,
        "routes/web.php": (
            "<?php\nuse App\\Models\\Client;\n"
            "Route::get('/', [Client::class, 'index']);\n"),
        "app/Services/Svc.php": (
            "<?php\nnamespace App\\Services;\nuse App\\Models\\Client;\n"
            "class Svc {\n    public function run($xs) { return array_map(fn($x) => Client::class, $xs); }\n}\n"),
    })
    real = _node(r, "Client", "app/Models/Client.php")["id"]
    routes = _node(r, "web.php", "routes/web.php")
    assert [e["target"] for e in _edges(r, routes["id"], "references_constant")] == [real]
    # The arrow function is its own node; its reference is owned by it.
    nodes = {n["id"]: n for n in r["nodes"]}
    in_svc = [
        e for e in r["edges"]
        if e["relation"] == "references_constant" and e["source_file"].endswith("Svc.php")
    ]
    assert [e["target"] for e in in_svc] == [real]
    assert nodes[in_svc[0]["source"]]["label"].startswith("{closure")


def test_incremental_build_resolves_against_unchanged_declarations(tmp_path):
    files = {
        "app/Models/Client.php": _CLIENT,
        "vendor/Other/Client.php": _DECOY,
        "app/Services/Svc.php": (
            "<?php\nnamespace App\\Services;\nuse App\\Models\\Client;\n"
            "class Svc {\n    public function run() { return Client::class; }\n}\n"),
    }
    full = _extract(tmp_path, files)
    context = [
        n for n in full["nodes"]
        if n.get("source_file") and not n["source_file"].endswith("Svc.php")
    ]
    assert any(n["label"] == "Client" for n in context)
    r = extract(
        [tmp_path / "app/Services/Svc.php"],
        cache_root=Path(tempfile.mkdtemp()),
        root=tmp_path,
        parallel=False,
        resolution_context_nodes=context,
    )
    run = _node(r, ".run()", "Svc.php")
    assert [e["target"] for e in _edges(r, run["id"], "references_constant")] == [
        _node(full, "Client", "app/Models/Client.php")["id"]]


def test_references_constant_does_not_replace_structural_edges_in_the_graph(tmp_path):
    # The built graph keeps ONE edge per undirected node pair. A method naming its
    # own class (`self::class`, `Svc::class`) and a bootstrap file that both `use`s
    # and `::class`-references a class share a pair with the `method` and `imports`
    # edges; the structural edge must survive, or the method leaves its class.
    from graphify.build import build_from_json, edge_data

    r = _extract(tmp_path, {
        "app/Models/Client.php": _CLIENT,
        "app/Services/Svc.php": (
            "<?php\nnamespace App\\Services;\nclass Svc {\n"
            "    public function run() { return [self::class, Svc::class]; }\n}\n"),
        "routes/web.php": (
            "<?php\nuse App\\Models\\Client;\nRoute::get('/', [Client::class, 'index']);\n"),
    })
    G = build_from_json(r)
    svc = _node(r, "Svc", "Svc.php")["id"]
    run = _node(r, ".run()", "Svc.php")["id"]
    assert edge_data(G, svc, run)["relation"] == "method"
    web = _node(r, "web.php", "routes/web.php")["id"]
    client = _node(r, "Client", "app/Models/Client.php")["id"]
    assert edge_data(G, web, client)["relation"] == "imports"
