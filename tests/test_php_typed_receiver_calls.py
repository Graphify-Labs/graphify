"""A typed PHP receiver's call never falls back to the enclosing class's method.

`$this->branchService->create()` inside `BranchController` used to bind to
`BranchController::create` because the shared engine resolved the bare method name
against the caller's own file before the receiver's declared type was consulted. A
typed receiver now resolves only through its own class (and in-corpus ancestors and
traits); when that class declares no such method (inherited from a vendor base class), the
call gets no edge at all. `$this->m()` keeps resolving to the class's own method.
"""
from __future__ import annotations

import importlib.util

import pytest

from graphify.extract import extract

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("tree_sitter_php") is None,
    reason="tree_sitter_php not installed",
)

SERVICE = "<?php\nclass BranchService {\n    public function create(): void {}\n}\n"


def _edges(tmp_path, files: dict[str, str]) -> set[tuple[str, str]]:
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    result = extract([tmp_path / n for n in files],
                     cache_root=tmp_path / "graphify-out", parallel=False)
    by_id = {n["id"]: n for n in result["nodes"]}
    owner = {e["target"]: by_id[e["source"]]["label"]
             for e in result["edges"] if e["relation"] == "method"}
    return {
        (f"{owner.get(e['source'], '')}{by_id[e['source']]['label'].lstrip('.')}",
         f"{owner.get(e['target'], '')}{by_id[e['target']]['label'].lstrip('.')}")
        for e in result["edges"] if e["relation"] == "calls"
    }


def _controller(body: str, header: str = "") -> str:
    return f"<?php\nclass BranchController {{\n{header}{body}}}\n"


STORE_VIA_PROP = ("    public function store(): void { $this->branchService->create(); }\n"
                  "    public function create(): void {}\n")


def test_a_promoted_property_binds_to_the_service_not_the_controller(tmp_path):
    edges = _edges(tmp_path, {
        "BranchService.php": SERVICE,
        "BranchController.php": _controller(
            STORE_VIA_PROP,
            "    public function __construct(private BranchService $branchService) {}\n"),
    })
    assert ("BranchControllerstore()", "BranchServicecreate()") in edges, edges
    assert ("BranchControllerstore()", "BranchControllercreate()") not in edges, edges


def test_a_typed_property_binds_to_the_service_not_the_controller(tmp_path):
    edges = _edges(tmp_path, {
        "BranchService.php": SERVICE,
        "BranchController.php": _controller(
            STORE_VIA_PROP, "    protected BranchService $branchService;\n"),
    })
    assert ("BranchControllerstore()", "BranchServicecreate()") in edges, edges
    assert ("BranchControllerstore()", "BranchControllercreate()") not in edges, edges


def test_a_typed_parameter_binds_to_the_service_not_the_controller(tmp_path):
    edges = _edges(tmp_path, {
        "BranchService.php": SERVICE,
        "BranchController.php": _controller(
            "    public function store(BranchService $svc): void { $svc->create(); }\n"
            "    public function create(): void {}\n"),
    })
    assert ("BranchControllerstore()", "BranchServicecreate()") in edges, edges
    assert ("BranchControllerstore()", "BranchControllercreate()") not in edges, edges


def test_a_model_calling_an_inherited_vendor_method_gets_no_edge(tmp_path):
    # `Branch` declares no `update` (its vendor/ base class does): the call must
    # not fall back to the controller's own `update`.
    edges = _edges(tmp_path, {
        "Branch.php": "<?php\nclass Branch extends Model {\n"
                      "    public function label(): void {}\n}\n",
        "BranchController.php": _controller(
            "    public function store(Branch $branch): void { $branch->update(); }\n"
            "    public function update(Branch $branch): void { $branch->archive(); }\n"
            "    public function archive(): void {}\n"),
    })
    targets = {t for s, t in edges if s.startswith("BranchController")}
    assert targets == set(), edges


def test_an_inherited_in_corpus_method_resolves_to_the_ancestor(tmp_path):
    edges = _edges(tmp_path, {
        "Base.php": "<?php\nclass BaseService {\n    public function create(): void {}\n}\n",
        "BranchService.php": "<?php\nclass BranchService extends BaseService {}\n",
        "BranchController.php": _controller(
            "    public function store(BranchService $svc): void { $svc->create(); }\n"
            "    public function create(): void {}\n"),
    })
    assert ("BranchControllerstore()", "BaseServicecreate()") in edges, edges
    assert ("BranchControllerstore()", "BranchControllercreate()") not in edges, edges


def test_a_trait_method_resolves_through_the_using_class(tmp_path):
    edges = _edges(tmp_path, {
        "Creates.php": "<?php\ntrait Creates {\n    public function create(): void {}\n}\n",
        "BranchService.php": "<?php\nclass BranchService {\n    use Creates;\n}\n",
        "BranchController.php": _controller(
            "    public function store(BranchService $svc): void { $svc->create(); }\n"
            "    public function create(): void {}\n"),
    })
    assert ("BranchControllerstore()", "Createscreate()") in edges, edges
    assert ("BranchControllerstore()", "BranchControllercreate()") not in edges, edges


def test_this_calls_still_resolve_to_the_own_method(tmp_path):
    edges = _edges(tmp_path, {
        "BranchController.php": _controller(
            "    public function store(): void { $this->create(); }\n"
            "    public function create(): void {}\n"),
    })
    assert ("BranchControllerstore()", "BranchControllercreate()") in edges, edges


def test_an_unknown_receiver_does_not_fall_back_to_the_own_method(tmp_path):
    edges = _edges(tmp_path, {
        "BranchController.php": _controller(
            "    public function store($x): void { $x->create(); $this->a()->create(); }\n"
            "    public function create(): void {}\n"
            "    public function a() { return 1; }\n"),
    })
    assert ("BranchControllerstore()", "BranchControllercreate()") not in edges, edges
