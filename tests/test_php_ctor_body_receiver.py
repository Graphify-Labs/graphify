"""Receiver typing from a constructor-BODY assignment of a typed param (#38).

The pre-promotion Laravel idiom declares the property untyped (its type living
only in a `@var` docblock) and assigns it in the constructor body from a typed
constructor parameter::

    /** @var ChargeCustomerService */
    protected $chargeCustomerService;
    public function __construct(ChargeCustomerService $chargeCustomerService) {
        $this->chargeCustomerService = $chargeCustomerService;
    }

The measured case is `app/Services/Billing/BalanceCustomerAccountService.php:14-20`
of api.lawnstarter.com @ `d2d4bed7ae`, whose `handle()` minted no `calls` edge to
`ChargeCustomerService::handle()`. The parameter's signature is the evidence —
the docblock is NOT read, and a property whose only type is a docblock stays
unbound (locked by `test_docblock_alone_still_emits_no_edge`).

The refusal discipline mirrors the local-variable one (#4): a property whose
constructor-body binding is not provably single-typed is POISONED — left out of
the receiver table entirely — rather than bound to a guess.

Every test goes through the public `extract()` seam, and every positive case
carries a decoy class with an identically named method that must get no edge.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _calls(tmp_path: Path, files: dict[str, str]):
    """Extract ``files`` (name -> source) and return ({(src, tgt): edge}, result)."""
    paths = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    result = extract(paths, cache_root=tmp_path / "graphify-out")
    calls = {
        (edge["source"], edge["target"]): edge
        for edge in result["edges"]
        if edge.get("relation") == "calls"
    }
    return calls, result


def _find(result: dict, label: str, id_contains: str) -> str:
    return next(
        node["id"]
        for node in result["nodes"]
        if node.get("label") == label and id_contains in node["id"]
    )


# Shared service + decoy: both define `search()`, so a bare method-name match
# cannot tell them apart — only the receiver's bound type can.
_SERVICE = "<?php\nnamespace App\\Services;\nclass LeadHunterService {\n    public function search(array $filters): array { return []; }\n}\n"
_DECOY = "<?php\nnamespace App\\Audit;\nclass AuditLog {\n    public function search(array $filters): array { return []; }\n}\n"
_CORPUS = {
    "app/Services/LeadHunterService.php": _SERVICE,
    "app/Audit/AuditLog.php": _DECOY,
}


def _controller(members: str, uses: str = "use App\\Services\\LeadHunterService;\n") -> str:
    """A controller class whose `index()` calls `$this->leadHunter->search([])`."""
    return (
        "<?php\n"
        "namespace App\\Http\\Controllers;\n"
        f"{uses}"
        "class LeadController {\n"
        f"{members}"
        "    public function index(): array {\n"
        "        return $this->leadHunter->search([]);\n"
        "    }\n"
        "}\n"
    )


def _no_search_edge(calls: dict, caller: str) -> bool:
    return not any(src == caller and "search" in tgt.lower() for src, tgt in calls)


# ── The measured case (#38) ───────────────────────────────────────────────────

def test_docblock_typed_property_assigned_in_ctor_body_resolves(tmp_path: Path):
    """The exact shape of BalanceCustomerAccountService.php:14-20: untyped
    property + `@var` docblock + ctor-body assignment from a typed param."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    /** @var LeadHunterService */\n"
            "    protected $leadHunter;\n"
            "\n"
            "    public function __construct(\n"
            "        LeadHunterService $leadHunter\n"
            "    ) {\n"
            "        $this->leadHunter = $leadHunter;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    assert (index, service_search) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls
    edge = calls[(index, service_search)]
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.8
    assert edge["context"] == "call"


def test_property_with_no_docblock_at_all_resolves(tmp_path: Path):
    """The docblock is decoration, not evidence: the parameter's type is what
    binds, so the same code without any docblock resolves identically."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $leadHunter) {\n"
            "        $this->leadHunter = $leadHunter;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_property_never_declared_at_all_resolves(tmp_path: Path):
    """A dynamic property (assigned but never declared) binds the same way —
    the assignment is the only declaration PHP needs."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    public function __construct(LeadHunterService $leadHunter) {\n"
            "        $this->leadHunter = $leadHunter;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_property_and_param_names_may_differ(tmp_path: Path):
    """The property name comes from the assignment's LEFT side, the type from
    its right — the two names need not agree."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_same_namespace_param_type_resolves_without_a_use_import(tmp_path: Path):
    """The measured case names its collaborator with no `use` line: it lives in
    the caller's own namespace. The namespace-aware binding (#22) applies to a
    ctor-body-bound receiver exactly as it does to a declared one."""
    calls, r = _calls(tmp_path, {
        "app/Services/LeadHunterService.php": _SERVICE,
        "app/Audit/AuditLog.php": _DECOY,
        "app/Services/LeadFinder.php": (
            "<?php\n"
            "namespace App\\Services;\n"
            "class LeadFinder {\n"
            "    /** @var LeadHunterService */\n"
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $leadHunter) {\n"
            "        $this->leadHunter = $leadHunter;\n"
            "    }\n"
            "    public function find(): array {\n"
            "        return $this->leadHunter->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    find = _find(r, ".find()", "leadfinder")
    assert (find, _find(r, ".search()", "leadhunterservice")) in calls
    assert (find, _find(r, ".search()", "auditlog")) not in calls


def test_qualified_param_type_resolves(tmp_path: Path):
    """A param type written out fully qualified binds the same way."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(\\App\\Services\\LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n",
            uses="",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_nullable_param_type_resolves(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(?LeadHunterService $leadHunter) {\n"
            "        $this->leadHunter = $leadHunter;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_promoted_param_may_also_type_a_second_property(tmp_path: Path):
    """A promoted param is a typed variable in the constructor's scope too, so
    aliasing it onto another property binds that property as well."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(private LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_the_constructor_body_itself_can_use_the_binding(tmp_path: Path):
    """The table is built before resolution, so a call in the constructor body
    resolves against a property the same body binds."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Services\\LeadHunterService;\n"
            "class LeadController {\n"
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $leadHunter) {\n"
            "        $this->leadHunter = $leadHunter;\n"
            "        $this->leadHunter->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    ctor = _find(r, ".__construct()", "leadcontroller")
    assert (ctor, _find(r, ".search()", "leadhunterservice")) in calls
    assert (ctor, _find(r, ".search()", "auditlog")) not in calls


def test_two_classes_in_one_file_bind_their_own_constructors(tmp_path: Path):
    """The binding is class-scoped: the same property name assigned from a
    different type in each class resolves to its own class's parameter."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Audit\\AuditLog;\n"
            "use App\\Services\\LeadHunterService;\n"
            "class LeadController {\n"
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
            "    public function index(): array {\n"
            "        return $this->leadHunter->search([]);\n"
            "    }\n"
            "}\n"
            "class AuditController {\n"
            "    protected $leadHunter;\n"
            "    public function __construct(AuditLog $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
            "    public function index(): array {\n"
            "        return $this->leadHunter->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    lead_index = _find(r, ".index()", "leadcontroller")
    audit_index = _find(r, ".index()", "auditcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    decoy_search = _find(r, ".search()", "audit_auditlog")
    assert (lead_index, service_search) in calls
    assert (lead_index, decoy_search) not in calls
    assert (audit_index, decoy_search) in calls
    assert (audit_index, service_search) not in calls


# ── Hard scope limit: docblocks are NOT read ─────────────────────────────────

def test_docblock_alone_still_emits_no_edge(tmp_path: Path):
    """`@var` docblocks stay out of scope (#38): with no constructor assignment
    to corroborate it, a docblock-only property types no receiver."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    /** @var LeadHunterService */\n"
            "    protected $leadHunter;\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index), "a docblock is not evidence — no edge"


def test_docblock_does_not_override_the_assigned_type(tmp_path: Path):
    """When the docblock and the assigned parameter disagree, the SIGNATURE
    wins — proof the docblock is never parsed."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    /** @var \\App\\Audit\\AuditLog */\n"
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $leadHunter) {\n"
            "        $this->leadHunter = $leadHunter;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


# ── Refusals: the binding must be provably single-typed ───────────────────────

def test_second_assignment_of_a_different_type_poisons_the_property(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc, AuditLog $log) {\n"
            "        $this->leadHunter = $svc;\n"
            "        $this->leadHunter = $log;\n"
            "    }\n",
            uses="use App\\Audit\\AuditLog;\nuse App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index), \
        "two conflicting parameter types poison the property — no edge to EITHER"


def test_second_assignment_of_an_untypable_value_poisons_the_property(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "        $this->leadHunter = app('lead.hunter');\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index), \
        "a container resolve names no type — the property is poisoned"


def test_assignment_from_an_untyped_param_emits_no_edge(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct($leadHunter) {\n"
            "        $this->leadHunter = $leadHunter;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_assignment_from_a_union_typed_param_emits_no_edge(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService|AuditLog $leadHunter) {\n"
            "        $this->leadHunter = $leadHunter;\n"
            "    }\n",
            uses="use App\\Audit\\AuditLog;\nuse App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index), "a union names several classes — refuse"


def test_assignment_from_a_local_new_emits_no_edge(tmp_path: Path):
    """Scope limit: only a typed constructor PARAMETER binds. A local built in
    the body is not a parameter, and it poisons rather than binds."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct() {\n"
            "        $svc = new LeadHunterService();\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_assignment_from_an_inline_new_emits_no_edge(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct() {\n"
            "        $this->leadHunter = new LeadHunterService();\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_param_rebound_in_the_body_poisons_the_property(tmp_path: Path):
    """The parameter's own binding must survive the body: a rebind to an
    untypable value makes the name — and so the property — unresolvable."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $svc = $other;\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_param_rebound_to_another_class_poisons_the_property(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $svc = new AuditLog();\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n",
            uses="use App\\Audit\\AuditLog;\nuse App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_closure_param_shadowing_the_ctor_param_poisons_the_property(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $fn = function (AuditLog $svc) { return $svc; };\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n",
            uses="use App\\Audit\\AuditLog;\nuse App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_assignment_inside_a_closure_emits_no_edge(tmp_path: Path):
    """A deferred write is not a constructor binding: the closure may run never,
    later, or more than once."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->boot = function () use ($svc) { $this->leadHunter = $svc; };\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_assignment_inside_a_closure_poisons_a_good_binding(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "        $this->boot = function () { $this->leadHunter = null; };\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_augmented_assignment_poisons_the_property(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "        $this->leadHunter ??= $svc;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_reference_assignment_poisons_the_property(tmp_path: Path):
    """`$this->prop = &$svc` aliases the property to the variable's storage, so
    a later rebind of that variable changes the property's type too.

    Two statements on purpose: `$this->prop = &$svc` alone is a
    `reference_assignment_expression`, which binds nothing whether or not the
    refusal exists, so a one-statement fixture could not tell POISONED from
    never-bound. The plain assignment first makes the refusal observable.
    """
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "        $this->leadHunter = &$svc;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_list_destructuring_target_poisons_the_property(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "        [$this->leadHunter, $rest] = $pair;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_foreach_target_poisons_the_property(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "        foreach ($rows as $this->leadHunter) {}\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_assignment_in_a_non_constructor_method_emits_no_edge(tmp_path: Path):
    """Scope limit: the CONSTRUCTOR body is the binding site. A setter runs at
    an unknown time and may be called with anything."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function setHunter(LeadHunterService $leadHunter): void {\n"
            "        $this->leadHunter = $leadHunter;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_interface_typed_param_assigned_to_a_property_binds_the_interface(tmp_path: Path):
    """A ctor-body-bound receiver typed with an INTERFACE binds to the
    interface's own method (#53), not to a same-short-named implementation.

    #5/#12 refused this outright, back when an interface minted no definition
    node and the only thing a receiver could land on was a stranger class. Post
    #47/#53 the contract has its own `search()` node and the `use` names it
    unambiguously — `App\\Services\\LeadHunterService` is a DIFFERENT type that
    the controller never imported, and it stays unbound, which is the whole
    point the original refusal was protecting."""
    calls, r = _calls(tmp_path, {
        "app/Contracts/LeadHunterService.php": (
            "<?php\n"
            "namespace App\\Contracts;\n"
            "interface LeadHunterService {\n"
            "    public function search(array $filters): array;\n"
            "}\n"
        ),
        "app/Services/LeadHunterService.php": _SERVICE,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $leadHunter) {\n"
            "        $this->leadHunter = $leadHunter;\n"
            "    }\n",
            uses="use App\\Contracts\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "contracts_leadhunterservice")) in calls, \
        "the imported contract is the receiver's declared type"
    assert (index, _find(r, ".search()", "services_leadhunterservice")) not in calls, \
        "an interface names no implementation — never guess one"


def test_out_of_corpus_param_type_emits_no_edge(tmp_path: Path):
    """A `use`-claimed name that names no in-corpus class is decided and never
    falls back to the short-name index (#16)."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $leadHunter) {\n"
            "        $this->leadHunter = $leadHunter;\n"
            "    }\n",
            uses="use Vendor\\Sdk\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


# ── The refusal is property-scoped, not constructor-scoped ────────────────────
#
# A property is not a local: any method of the class can rewrite it, and unlike a
# natively typed property (which PHP fatals on an incompatible write) an untyped
# one carries no runtime guarantee. So "poison on reassignment" is judged over
# the whole CLASS — a write anywhere outside the constructor is the same category
# of deferred write as a closure's, and refuses the constructor's binding.

def test_setter_reassigning_to_another_type_poisons_the_property(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
            "    public function setHunter(AuditLog $log): void {\n"
            "        $this->leadHunter = $log;\n"
            "    }\n",
            uses="use App\\Audit\\AuditLog;\nuse App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index), \
        "a setter rewrites the property to another class — the ctor binding is not " \
        "what the property provably holds at the call site"


def test_setter_assigning_an_untypable_value_poisons_the_property(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
            "    public function boot(): void {\n"
            "        $this->leadHunter = app('lead.hunter');\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_setter_assigning_the_same_type_also_refuses(tmp_path: Path):
    """Deliberately conservative: refusal is unconditional on the write, not
    conditional on the written type. A same-typed setter is provably harmless,
    so this costs a little recall — the trade the refusal discipline chooses.
    Documented as intended behavior so a future reader does not read it as a bug.
    """
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
            "    public function setHunter(LeadHunterService $svc): void {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_a_setter_that_leaves_the_property_alone_keeps_the_binding(tmp_path: Path):
    """Control for the class-wide sweep: it must refuse only the properties a
    method actually WRITES, not every property of a class that has setters."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    protected $other;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
            "    public function setOther(AuditLog $log): void {\n"
            "        $this->other = $log;\n"
            "        $log->search([]);\n"
            "    }\n"
            "    public function read(): array {\n"
            "        return $this->leadHunter->search([]);\n"
            "    }\n",
            uses="use App\\Audit\\AuditLog;\nuse App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    read = _find(r, ".read()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    assert (index, service_search) in calls
    assert (read, service_search) in calls
    assert (index, _find(r, ".search()", "audit_auditlog")) not in calls


def test_non_constructor_augmented_assignment_poisons_the_property(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
            "    public function boot(): void {\n"
            "        $this->leadHunter ??= null;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_non_constructor_list_destructuring_poisons_the_property(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
            "    public function boot(array $pair): void {\n"
            "        [$this->leadHunter, $rest] = $pair;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_non_constructor_foreach_target_poisons_the_property(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
            "    public function boot(array $rows): void {\n"
            "        foreach ($rows as $this->leadHunter) {}\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_non_constructor_reference_assignment_poisons_the_property(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
            "    public function boot(LeadHunterService $other): void {\n"
            "        $this->leadHunter = &$other;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_write_inside_a_closure_in_another_method_poisons_the_property(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
            "    public function boot(): void {\n"
            "        $this->defer(function () { $this->leadHunter = null; });\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_a_write_to_another_objects_property_does_not_poison(tmp_path: Path):
    """`$other->leadHunter = …` writes a DIFFERENT object's property."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
            "    public function copyTo(LeadController $other): void {\n"
            "        $other->leadHunter = null;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_a_write_in_an_anonymous_class_does_not_poison_the_outer_class(tmp_path: Path):
    """An anonymous class's `$this` is its OWN instance, so a write to a
    same-named property inside one says nothing about the outer class's."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
            "    public function make(): object {\n"
            "        return new class {\n"
            "            public $leadHunter;\n"
            "            public function boot(): void { $this->leadHunter = null; }\n"
            "        };\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_a_write_in_another_class_does_not_poison(tmp_path: Path):
    """The sweep is class-scoped: a same-named property written by a DIFFERENT
    class in the same file leaves this class's binding alone."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Services\\LeadHunterService;\n"
            "class LeadController {\n"
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
            "    public function index(): array {\n"
            "        return $this->leadHunter->search([]);\n"
            "    }\n"
            "}\n"
            "class OtherController {\n"
            "    protected $leadHunter;\n"
            "    public function reset(): void {\n"
            "        $this->leadHunter = null;\n"
            "    }\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls


def test_declared_typed_property_survives_a_setter(tmp_path: Path):
    """The class-wide sweep must not reach the DECLARED path: PHP enforces a
    native property type on every write, so a setter cannot retype it."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected LeadHunterService $leadHunter;\n"
            "    public function setHunter(LeadHunterService $svc): void {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_promoted_property_survives_a_setter(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    public function __construct(protected LeadHunterService $leadHunter) {}\n"
            "    public function setHunter(LeadHunterService $svc): void {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


# ── Precedence: a real annotation always outranks the assignment ──────────────

def test_declared_property_type_outranks_the_ctor_assignment(tmp_path: Path):
    """A natively typed property is the author's stated contract; the ctor-body
    assignment only fills a GAP."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected AuditLog $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n",
            uses="use App\\Audit\\AuditLog;\nuse App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "auditlog")) in calls
    assert (index, _find(r, ".search()", "leadhunterservice")) not in calls


def test_union_typed_property_declaration_stays_refused(tmp_path: Path):
    """A union annotation is a PRESENT-but-unresolved binding (#9), not a gap:
    the ctor assignment must not resolve it."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    protected LeadHunterService|AuditLog $leadHunter;\n"
            "    public function __construct(LeadHunterService $svc) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n",
            uses="use App\\Audit\\AuditLog;\nuse App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert _no_search_edge(calls, index)


def test_promoted_param_outranks_a_conflicting_ctor_assignment(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    public function __construct(\n"
            "        protected AuditLog $leadHunter,\n"
            "        LeadHunterService $svc\n"
            "    ) {\n"
            "        $this->leadHunter = $svc;\n"
            "    }\n",
            uses="use App\\Audit\\AuditLog;\nuse App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "auditlog")) in calls
    assert (index, _find(r, ".search()", "leadhunterservice")) not in calls


# ── Regressions: the two already-covered sibling forms keep working ───────────

def test_regression_promoted_param_receiver_still_resolves(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    public function __construct(protected readonly LeadHunterService $leadHunter) {}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_regression_typed_property_receiver_still_resolves(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "    private LeadHunterService $leadHunter;\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_regression_typed_method_param_receiver_still_resolves(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Services\\LeadHunterService;\n"
            "class LeadController {\n"
            "    protected $leadHunter;\n"
            "    public function __construct(LeadHunterService $leadHunter) {\n"
            "        $this->leadHunter = $leadHunter;\n"
            "    }\n"
            "    public function handle(LeadHunterService $svc): array {\n"
            "        return $svc->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    handle = _find(r, ".handle()", "leadcontroller")
    assert (handle, _find(r, ".search()", "leadhunterservice")) in calls
    assert (handle, _find(r, ".search()", "auditlog")) not in calls
