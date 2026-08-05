"""PHP receiver-typed member-call resolution (#1682, tracer bullet).

PHP ``member_call_expression`` nodes carry the receiver and the callee name, but
the extractor used to read only the bare name.  A ``$this->prop->method()`` call
must select the method owned by the property's DECLARED type; receivers whose
type is untyped, union-typed or ambiguous stay unlinked rather than minting a
false call edge.

Every test goes through the public ``extract()`` seam, and every positive case
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
# cannot tell them apart — only the receiver's declared type can.
_SERVICE = "<?php\nnamespace App\\Services;\nclass LeadHunterService {\n    public function search(array $filters): array { return []; }\n}\n"
_DECOY = "<?php\nnamespace App\\Audit;\nclass AuditLog {\n    public function search(array $filters): array { return []; }\n}\n"
_CORPUS = {
    "app/Services/LeadHunterService.php": _SERVICE,
    "app/Audit/AuditLog.php": _DECOY,
}


def test_promoted_param_this_prop_call_resolves(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Services\\LeadHunterService;\n"
            "class LeadController {\n"
            "    public function __construct(protected LeadHunterService $leadHunter) {}\n"
            "    public function index(): array {\n"
            "        return $this->leadHunter->search(['status' => 'open']);\n"
            "    }\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    decoy_search = _find(r, ".search()", "auditlog")
    assert (index, service_search) in calls
    assert (index, decoy_search) not in calls
    edge = calls[(index, service_search)]
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.8
    assert edge["context"] == "call"


def test_typed_property_call_resolves(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Services\\LeadHunterService;\n"
            "class LeadController {\n"
            "    private LeadHunterService $leadHunter;\n"
            "    public function index(): array {\n"
            "        return $this->leadHunter->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_property_declared_after_the_caller_still_resolves(tmp_path: Path):
    """The type table is complete before resolution — declaration order is free."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Services\\LeadHunterService;\n"
            "class LeadController {\n"
            "    public function index(): array {\n"
            "        return $this->leadHunter->search([]);\n"
            "    }\n"
            "    private LeadHunterService $leadHunter;\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_method_name_match_is_case_insensitive(tmp_path: Path):
    """PHP method names are case-insensitive, so `SEARCH()` still binds."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Services\\LeadHunterService;\n"
            "class LeadController {\n"
            "    private LeadHunterService $leadHunter;\n"
            "    public function index(): array {\n"
            "        return $this->leadHunter->SEARCH([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_nullsafe_member_call_resolves(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Services\\LeadHunterService;\n"
            "class LeadController {\n"
            "    private LeadHunterService $leadHunter;\n"
            "    public function index(): array {\n"
            "        return $this->leadHunter?->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    assert (index, service_search) in calls
    assert calls[(index, service_search)]["confidence"] == "INFERRED"
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_nullable_typed_property_unwraps_and_resolves(tmp_path: Path):
    """`?Foo` is still concretely Foo — the nullable wrapper is unwrapped."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Services\\LeadHunterService;\n"
            "class LeadController {\n"
            "    private ?LeadHunterService $leadHunter;\n"
            "    public function index(): array {\n"
            "        return $this->leadHunter->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_untyped_property_emits_no_edge(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "class LeadController {\n"
            "    protected $leadHunter;\n"
            "    public function index(): array {\n"
            "        return $this->leadHunter->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert not any(src == index and "search" in tgt.lower() for src, tgt in calls), \
        "an untyped receiver must not be guessed onto a same-named method"


def test_union_typed_property_emits_no_edge(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Audit\\AuditLog;\n"
            "use App\\Services\\LeadHunterService;\n"
            "class LeadController {\n"
            "    protected LeadHunterService|AuditLog $leadHunter;\n"
            "    public function index(): array {\n"
            "        return $this->leadHunter->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert not any(src == index and "search" in tgt.lower() for src, tgt in calls), \
        "a union-typed receiver has no single concrete type — refuse"


def test_self_typed_property_emits_no_edge(tmp_path: Path):
    """`self`/`static`/`parent` are not concrete class names in the type table."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "class LeadController {\n"
            "    protected self $leadHunter;\n"
            "    public function index(): array {\n"
            "        return $this->leadHunter->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert not any(src == index and "search" in tgt.lower() for src, tgt in calls)


def test_duplicate_class_name_emits_no_edge(tmp_path: Path):
    """Two `LeadHunterService` definitions: the single-definition guard refuses."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "legacy/Services/LeadHunterService.php": (
            "<?php\nnamespace Legacy\\Services;\n"
            "class LeadHunterService {\n"
            "    public function search(array $filters): array { return []; }\n"
            "}\n"
        ),
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Services\\LeadHunterService;\n"
            "class LeadController {\n"
            "    private LeadHunterService $leadHunter;\n"
            "    public function index(): array {\n"
            "        return $this->leadHunter->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert not any(src == index and "search" in tgt.lower() for src, tgt in calls), \
        "an ambiguous short class name must not resolve to either definition"


def test_unknown_method_has_no_fallback_edge(tmp_path: Path):
    """The receiver's type is known but has no such method — refuse entirely."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Services\\LeadHunterService;\n"
            "class LeadController {\n"
            "    private LeadHunterService $leadHunter;\n"
            "    public function index(): array {\n"
            "        return $this->leadHunter->missingMethod();\n"
            "    }\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service = _find(r, "LeadHunterService", "app_services_leadhunterservice_leadhunterservice")
    assert not any(src == index for src, _tgt in calls), \
        "an unknown method on a typed receiver must not fall back to any edge"
    assert not any(
        e.get("relation") == "references"
        and e.get("source") == index
        and e.get("target") == service
        for e in r["edges"]
    ), "no `references` consolation edge either — refuse, don't guess"


def test_this_self_call_still_extracted(tmp_path: Path):
    """Plain `$this->method()` keeps today's same-file bare-name edge."""
    calls, r = _calls(tmp_path, {
        "app/Http/ApiClient.php": (
            "<?php\n"
            "namespace App\\Http;\n"
            "class ApiClient {\n"
            "    public function get(string $path): string {\n"
            "        return $this->fetch($path);\n"
            "    }\n"
            "    private function fetch(string $path): string { return $path; }\n"
            "}\n"
        ),
    })

    get = _find(r, ".get()", "apiclient")
    fetch = _find(r, ".fetch()", "apiclient")
    assert (get, fetch) in calls


def test_untyped_receiver_keeps_same_file_edge(tmp_path: Path):
    """Deferral is gated on a stamped receiver type: an untyped receiver keeps
    the in-file bare-name match it produced before this feature."""
    calls, r = _calls(tmp_path, {
        "app/Http/ApiClient.php": (
            "<?php\n"
            "namespace App\\Http;\n"
            "class ApiClient {\n"
            "    protected $helper;\n"
            "    public function get(string $path): string {\n"
            "        return $this->helper->fetch($path);\n"
            "    }\n"
            "    private function fetch(string $path): string { return $path; }\n"
            "}\n"
        ),
    })

    get = _find(r, ".get()", "apiclient")
    fetch = _find(r, ".fetch()", "apiclient")
    assert (get, fetch) in calls


def test_static_call_edge_unchanged(tmp_path: Path):
    """`Class::method()` still targets the CLASS node, as before this feature."""
    calls, r = _calls(tmp_path, {
        "app/Context/SucursalContext.php": (
            "<?php\nnamespace App\\Context;\n"
            "class SucursalContext {\n"
            "    public static function id(): int { return 1; }\n"
            "}\n"
        ),
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Context\\SucursalContext;\n"
            "class LeadController {\n"
            "    public function index(): int {\n"
            "        return SucursalContext::id();\n"
            "    }\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    context_class = _find(r, "SucursalContext", "app_context_sucursalcontext_sucursalcontext")
    assert (index, context_class) in calls


# ── Inline instantiation receivers: `(new Service())->method()` (#3) ──────────
#
# The source names the class outright, so the receiver needs no type table. The
# edge is EXTRACTED only when the written qualified name CORROBORATES the
# resolved node (its namespace segments match the node's file path, PSR-4
# style); a bare name carries no such evidence and stays INFERRED.


def _controller(body: str, uses: str = "") -> str:
    return (
        "<?php\n"
        "namespace App\\Http\\Controllers;\n"
        f"{uses}"
        "class LeadController {\n"
        "    public function index(): array {\n"
        f"        {body}\n"
        "    }\n"
        "}\n"
    )


def test_inline_new_qualified_name_resolves_extracted(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "return (new \\App\\Services\\LeadHunterService())->search([]);"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    assert (index, service_search) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls
    edge = calls[(index, service_search)]
    assert edge["confidence"] == "EXTRACTED"
    assert edge["confidence_score"] == 1.0


def test_inline_new_bare_name_resolves_inferred(tmp_path: Path):
    """A bare `new Service()` names no namespace — nothing corroborates it."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "return (new LeadHunterService())->search([]);",
            uses="use App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    assert (index, service_search) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls
    edge = calls[(index, service_search)]
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.8


def test_inline_new_without_ctor_parens_resolves(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "return (new \\App\\Services\\LeadHunterService)->search([]);"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    assert (index, service_search) in calls
    assert calls[(index, service_search)]["confidence"] == "EXTRACTED"
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_inline_new_non_corroborating_namespace_downgrades(tmp_path: Path):
    """`\\Legacy\\...\\LeadHunterService` resolves by short name to the only
    definition in the corpus, but the written namespace does not match that
    node's path — so the edge is emitted as INFERRED, not EXTRACTED."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "return (new \\Legacy\\Services\\LeadHunterService())->search([]);"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    assert (index, service_search) in calls
    edge = calls[(index, service_search)]
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.8


def test_inline_new_beats_same_file_same_named_method(tmp_path: Path):
    """The named class wins over an identically named method in the caller's
    own file — the bare-name match must not shadow an explicit `new`."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "class LeadController {\n"
            "    public function index(): array {\n"
            "        return (new \\App\\Services\\LeadHunterService())->search([]);\n"
            "    }\n"
            "    public function search(array $filters): array { return []; }\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "leadcontroller")) not in calls


def test_inline_new_self_emits_no_edge(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "return (new self())->search([]);"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert not any(src == index and "search" in tgt.lower() for src, tgt in calls), \
        "`new self()` needs inheritance context the raw-call facts lack — refuse"


def test_inline_new_static_emits_no_edge(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "return (new static())->search([]);"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert not any(src == index and "search" in tgt.lower() for src, tgt in calls)


def test_anonymous_class_inline_new_emits_no_edge(tmp_path: Path):
    """`new class { ... }` has no class name at all — nothing to resolve, and
    no guess onto a same-named method elsewhere in the corpus."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "return (new class { public function search(array $f): array "
            "{ return []; } })->search([]);"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) not in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_bare_new_statement_without_call_emits_no_edge(tmp_path: Path):
    """`new Service();` on its own is not a call — still out of scope."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "new \\App\\Services\\LeadHunterService();\n        return [];"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert not any(src == index for src, _tgt in calls)


def test_inline_new_unknown_method_emits_no_edge(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "return (new \\App\\Services\\LeadHunterService())->missingMethod();"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert not any(src == index for src, _tgt in calls), \
        "the named class has no such method — refuse, don't fall back"


# ── Typed locals and typed params, with scope poisoning (#4) ─────────────────
#
# A method-scoped receiver layer types `$var->m()` from `$var = new T()` locals
# and natively typed parameters. Raw calls carry no lexical scope, so any name
# whose binding is not provably single-typed is POISONED: a non-`new` rebind, a
# conflicting `new`, a closure/arrow-fn parameter, a foreach target, or a
# list-destructuring element. Anonymous-class bodies are a different scope
# entirely and bind nothing in the enclosing method.


def test_local_new_var_call_resolves(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "$svc = new LeadHunterService();\n"
            "        return $svc->search([]);",
            uses="use App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    assert (index, service_search) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls
    edge = calls[(index, service_search)]
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.8


def test_local_new_qualified_var_call_resolves_inferred(tmp_path: Path):
    """A local binding stays INFERRED even when the `new` is fully qualified —
    FQN corroboration is scoped to the inline-new receiver form (#3)."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "$svc = new \\App\\Services\\LeadHunterService();\n"
            "        return $svc->search([]);"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    assert (index, service_search) in calls
    assert calls[(index, service_search)]["confidence"] == "INFERRED"
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_typed_param_receiver_resolves(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Services\\LeadHunterService;\n"
            "class LeadController {\n"
            "    public function handle(LeadHunterService $svc): array {\n"
            "        return $svc->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    handle = _find(r, ".handle()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    assert (handle, service_search) in calls
    assert (handle, _find(r, ".search()", "auditlog")) not in calls
    assert calls[(handle, service_search)]["confidence"] == "INFERRED"


def test_nullable_typed_param_receiver_resolves(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Services\\LeadHunterService;\n"
            "class LeadController {\n"
            "    public function handle(?LeadHunterService $svc): array {\n"
            "        return $svc->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    handle = _find(r, ".handle()", "leadcontroller")
    assert (handle, _find(r, ".search()", "leadhunterservice")) in calls
    assert (handle, _find(r, ".search()", "auditlog")) not in calls


def test_locals_resolve_per_method_independently(tmp_path: Path):
    """The receiver layer is method-scoped: the same local name bound to two
    different classes in two methods resolves to its own binding in each."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Audit\\AuditLog;\n"
            "use App\\Services\\LeadHunterService;\n"
            "class LeadController {\n"
            "    public function index(): array {\n"
            "        $svc = new LeadHunterService();\n"
            "        return $svc->search([]);\n"
            "    }\n"
            "    public function audit(): array {\n"
            "        $svc = new AuditLog();\n"
            "        return $svc->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    audit = _find(r, ".audit()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    decoy_search = _find(r, ".search()", "auditlog")
    assert (index, service_search) in calls
    assert (index, decoy_search) not in calls
    assert (audit, decoy_search) in calls
    assert (audit, service_search) not in calls


def test_non_new_reassignment_poisons_local(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "$svc = new LeadHunterService();\n"
            "        $svc = $other;\n"
            "        return $svc->search([]);",
            uses="use App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert not any(src == index and "search" in tgt.lower() for src, tgt in calls), \
        "a rebind to an untypable value poisons the name"


def test_conflicting_new_types_poison_local(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "$svc = new LeadHunterService();\n"
            "        $svc = new AuditLog();\n"
            "        return $svc->search([]);",
            uses="use App\\Audit\\AuditLog;\nuse App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert not any(src == index and "search" in tgt.lower() for src, tgt in calls), \
        "two conflicting `new` types poison the name — no edge to EITHER class"


def test_augmented_assignment_poisons_local(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "$svc = new LeadHunterService();\n"
            "        $svc ??= new AuditLog();\n"
            "        return $svc->search([]);",
            uses="use App\\Audit\\AuditLog;\nuse App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert not any(src == index and "search" in tgt.lower() for src, tgt in calls)


def test_closure_param_shadow_poisons_outer_name(tmp_path: Path):
    """Calls inside a closure are attributed to the enclosing method, so a
    closure parameter that shadows an outer name makes BOTH unresolvable."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "$svc = new LeadHunterService();\n"
            "        $fn = function (AuditLog $svc) { return $svc->search([]); };\n"
            "        return $svc->search([]);",
            uses="use App\\Audit\\AuditLog;\nuse App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) not in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_arrow_fn_param_shadow_poisons_outer_name(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "$svc = new LeadHunterService();\n"
            "        $fn = fn(AuditLog $svc) => $svc->search([]);\n"
            "        return $svc->search([]);",
            uses="use App\\Audit\\AuditLog;\nuse App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) not in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_foreach_target_shadow_poisons_outer_name(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "$svc = new LeadHunterService();\n"
            "        foreach ($rows as $svc) { $svc->search([]); }\n"
            "        return [];",
            uses="use App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert not any(src == index and "search" in tgt.lower() for src, tgt in calls), \
        "a foreach target rebinds the name to an unknown element type"


def test_list_destructuring_poisons_outer_name(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "$svc = new LeadHunterService();\n"
            "        [$svc, $rest] = $pair;\n"
            "        return $svc->search([]);",
            uses="use App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert not any(src == index and "search" in tgt.lower() for src, tgt in calls)


def test_global_statement_poisons_local(tmp_path: Path):
    """`global $svc;` makes the name an alias of the GLOBAL slot — the local
    `new` is discarded, so the type learned from it is stale (#13)."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "$svc = new LeadHunterService();\n"
            "        global $svc;\n"
            "        return $svc->search([]);",
            uses="use App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert not any(src == index and "search" in tgt.lower() for src, tgt in calls), \
        "at runtime $svc is the global, never the locally constructed service"


def test_static_statement_poisons_local(tmp_path: Path):
    """`static $svc;` rebinds the name to the function-static slot, which starts
    out null and survives across calls."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "$svc = new LeadHunterService();\n"
            "        static $svc;\n"
            "        return $svc->search([]);",
            uses="use App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert not any(src == index and "search" in tgt.lower() for src, tgt in calls)


def test_global_statement_poisons_regardless_of_order(tmp_path: Path):
    """Poisoning is order-independent: the raw calls carry no statement order,
    so a `global` BEFORE the `new` must refuse just the same."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "global $svc;\n"
            "        $svc = new LeadHunterService();\n"
            "        return $svc->search([]);",
            uses="use App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert not any(src == index and "search" in tgt.lower() for src, tgt in calls)


def test_multi_name_global_poisons_every_listed_name(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "$svc = new LeadHunterService();\n"
            "        $log = new AuditLog();\n"
            "        global $log, $svc;\n"
            "        $svc->search([]);\n"
            "        return $log->search([]);",
            uses="use App\\Audit\\AuditLog;\nuse App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) not in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_multi_name_static_with_initializer_poisons_every_listed_name(tmp_path: Path):
    """`static $x = 1, $svc;` declares two names; the constant initializer names
    no variable, so exactly the declared ones are poisoned."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "$svc = new LeadHunterService();\n"
            "        $log = new AuditLog();\n"
            "        static $x = 1, $log, $svc;\n"
            "        $svc->search([]);\n"
            "        return $log->search([]);",
            uses="use App\\Audit\\AuditLog;\nuse App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) not in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_global_statement_naming_another_variable_keeps_the_binding(tmp_path: Path):
    """The poison is name-targeted, not statement-targeted: `global $other;`
    says nothing about `$svc`, whose `new` still types it."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "$svc = new LeadHunterService();\n"
            "        global $other;\n"
            "        return $svc->search([]);",
            uses="use App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_static_statement_naming_another_variable_keeps_the_binding(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "$svc = new LeadHunterService();\n"
            "        static $conn = null;\n"
            "        return $svc->search([]);",
            uses="use App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_new_inside_anonymous_class_does_not_bind_enclosing_name(tmp_path: Path):
    """An anonymous-class body is its own scope — its `new` must not type a
    same-named variable in the method that contains the literal."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "$anon = new class {\n"
            "            public function q(): void { $svc = new \\App\\Services\\LeadHunterService(); }\n"
            "        };\n"
            "        return $svc->search([]);"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) not in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls


def test_chained_receiver_emits_no_edge(tmp_path: Path):
    """`$a->b()->c()`: the outer receiver is a call result, not a typed name."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Report/Formatter.php": (
            "<?php\nnamespace App\\Report;\n"
            "class Formatter {\n"
            "    public function format(array $rows): string { return ''; }\n"
            "}\n"
        ),
        "app/Http/Controllers/LeadController.php": _controller(
            "$svc = new LeadHunterService();\n"
            "        return $svc->search([])->format([]);",
            uses="use App\\Services\\LeadHunterService;\n",
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    assert (index, _find(r, ".search()", "leadhunterservice")) in calls, \
        "the INNER call still resolves through the typed local"
    assert (index, _find(r, ".format()", "formatter")) not in calls, \
        "the chained call's receiver has no known type"


def test_untyped_param_emits_no_edge(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "class LeadController {\n"
            "    public function handle($svc): array {\n"
            "        return $svc->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    handle = _find(r, ".handle()", "leadcontroller")
    assert not any(src == handle and "search" in tgt.lower() for src, tgt in calls)


def test_union_typed_param_emits_no_edge(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Audit\\AuditLog;\n"
            "use App\\Services\\LeadHunterService;\n"
            "class LeadController {\n"
            "    public function handle(LeadHunterService|AuditLog $svc): array {\n"
            "        return $svc->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    handle = _find(r, ".handle()", "leadcontroller")
    assert not any(src == handle and "search" in tgt.lower() for src, tgt in calls)


def test_self_typed_param_emits_no_edge(tmp_path: Path):
    """`self`/`static` parse as a plain `named_type` in parameter position, so
    the non-concrete name set is what refuses them (probe-verified)."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "class LeadController {\n"
            "    public function handle(self $svc): array {\n"
            "        return $svc->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    handle = _find(r, ".handle()", "leadcontroller")
    assert not any(src == handle and "search" in tgt.lower() for src, tgt in calls)


def test_variadic_typed_param_emits_no_edge(tmp_path: Path):
    """`Service ...$svcs` binds an ARRAY of Service, not a Service."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "use App\\Services\\LeadHunterService;\n"
            "class LeadController {\n"
            "    public function handle(LeadHunterService ...$svcs): array {\n"
            "        return $svcs->search([]);\n"
            "    }\n"
            "}\n"
        ),
    })

    handle = _find(r, ".handle()", "leadcontroller")
    assert not any(src == handle and "search" in tgt.lower() for src, tgt in calls)


# ── Interface-typed receivers are refused (#5) ───────────────────────────────
#
# PHP `interface_declaration` mints no definition node, so an interface-typed
# receiver normally resolves to nothing by accident. The dangerous case is
# Laravel's Contracts convention: `App\Contracts\Notifier` (interface) next to
# an unrelated `App\Support\Notifier` (class). The short-name lookup would find
# exactly one definition — the wrong one — and satisfy the ambiguity guard.
# Implementations are never guessed, and neither is a same-named stranger.

_IFACE_CORPUS = {
    "app/Contracts/Notifier.php": (
        "<?php\nnamespace App\\Contracts;\n"
        "interface Notifier {\n    public function notify(string $m): void;\n}\n"
    ),
    "app/Support/Notifier.php": (
        "<?php\nnamespace App\\Support;\n"
        "class Notifier {\n    public function notify(string $m): void {}\n}\n"
    ),
    "app/Services/MailNotifier.php": (
        "<?php\nnamespace App\\Services;\n"
        "use App\\Contracts\\Notifier;\n"
        "class MailNotifier implements Notifier {\n"
        "    public function notify(string $m): void {}\n}\n"
    ),
}


def _notified(calls, caller: str) -> bool:
    return any(src == caller and "notify" in tgt.lower() for src, tgt in calls)


def test_interface_typed_property_does_not_guess_implementation(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_IFACE_CORPUS,
        "app/Http/Dispatcher.php": (
            "<?php\n"
            "namespace App\\Http;\n"
            "use App\\Contracts\\Notifier;\n"
            "class Dispatcher {\n"
            "    private Notifier $notifier;\n"
            "    public function go(): void { $this->notifier->notify('x'); }\n"
            "}\n"
        ),
    })

    go = _find(r, ".go()", "dispatcher")
    assert (go, _find(r, ".notify()", "mailnotifier")) not in calls, \
        "an interface names a contract, not an implementation — never guess"
    assert not _notified(calls, go)


def test_interface_short_name_collision_emits_no_edge(tmp_path: Path):
    """`App\\Contracts\\Notifier` (interface) and `App\\Support\\Notifier`
    (unrelated class): exactly one DEFINITION exists, so the ambiguity guard
    alone would happily bind the call to the stranger."""
    calls, r = _calls(tmp_path, {
        **_IFACE_CORPUS,
        "app/Http/Dispatcher.php": (
            "<?php\n"
            "namespace App\\Http;\n"
            "use App\\Contracts\\Notifier;\n"
            "class Dispatcher {\n"
            "    private Notifier $notifier;\n"
            "    public function go(): void { $this->notifier->notify('x'); }\n"
            "}\n"
        ),
    })

    go = _find(r, ".go()", "dispatcher")
    assert (go, _find(r, ".notify()", "support_notifier")) not in calls, \
        "the same-short-named class is not the interface the receiver declares"
    assert not _notified(calls, go)


def test_interface_refusal_is_case_insensitive(tmp_path: Path):
    """PHP type names are case-insensitive: `notifier` IS `Notifier`."""
    calls, r = _calls(tmp_path, {
        **_IFACE_CORPUS,
        "app/Http/Dispatcher.php": (
            "<?php\n"
            "namespace App\\Http;\n"
            "use App\\Contracts\\Notifier;\n"
            "class Dispatcher {\n"
            "    private notifier $notifier;\n"
            "    public function go(): void { $this->notifier->notify('x'); }\n"
            "}\n"
        ),
    })

    go = _find(r, ".go()", "dispatcher")
    assert not _notified(calls, go)


def test_interface_typed_param_emits_no_edge(tmp_path: Path):
    """The typed-parameter receiver path (#4) refuses interfaces too."""
    calls, r = _calls(tmp_path, {
        **_IFACE_CORPUS,
        "app/Http/Dispatcher.php": (
            "<?php\n"
            "namespace App\\Http;\n"
            "use App\\Contracts\\Notifier;\n"
            "class Dispatcher {\n"
            "    public function go(Notifier $n): void { $n->notify('x'); }\n"
            "}\n"
        ),
    })

    go = _find(r, ".go()", "dispatcher")
    assert (go, _find(r, ".notify()", "support_notifier")) not in calls
    assert not _notified(calls, go)


def test_interface_inline_new_emits_no_edge(tmp_path: Path):
    """The inline-new receiver path (#3) refuses interfaces too — an interface
    cannot be instantiated, so such a receiver must never bind a stranger."""
    calls, r = _calls(tmp_path, {
        **_IFACE_CORPUS,
        "app/Http/Dispatcher.php": (
            "<?php\n"
            "namespace App\\Http;\n"
            "class Dispatcher {\n"
            "    public function go(): void {\n"
            "        (new \\App\\Contracts\\Notifier())->notify('x');\n"
            "    }\n"
            "}\n"
        ),
    })

    go = _find(r, ".go()", "dispatcher")
    assert (go, _find(r, ".notify()", "support_notifier")) not in calls
    assert not _notified(calls, go)


def test_interface_typed_local_new_emits_no_edge(tmp_path: Path):
    """The typed-local receiver path (#4) refuses interfaces too."""
    calls, r = _calls(tmp_path, {
        **_IFACE_CORPUS,
        "app/Http/Dispatcher.php": (
            "<?php\n"
            "namespace App\\Http;\n"
            "use App\\Contracts\\Notifier;\n"
            "class Dispatcher {\n"
            "    public function go(): void {\n"
            "        $n = new Notifier();\n"
            "        $n->notify('x');\n"
            "    }\n"
            "}\n"
        ),
    })

    go = _find(r, ".go()", "dispatcher")
    assert (go, _find(r, ".notify()", "support_notifier")) not in calls
    assert not _notified(calls, go)


def test_class_receiver_still_resolves_when_an_interface_exists(tmp_path: Path):
    """The refusal is name-scoped: a CLASS-typed receiver still resolves, and
    the same-named interface elsewhere in the corpus changes nothing."""
    calls, r = _calls(tmp_path, {
        **_IFACE_CORPUS,
        "app/Audit/AuditTrail.php": (
            "<?php\nnamespace App\\Audit;\n"
            "class AuditTrail {\n    public function notify(string $m): void {}\n}\n"
        ),
        "app/Http/Dispatcher.php": (
            "<?php\n"
            "namespace App\\Http;\n"
            "use App\\Services\\MailNotifier;\n"
            "class Dispatcher {\n"
            "    private MailNotifier $notifier;\n"
            "    public function go(): void { $this->notifier->notify('x'); }\n"
            "}\n"
        ),
    })

    go = _find(r, ".go()", "dispatcher")
    assert (go, _find(r, ".notify()", "mailnotifier")) in calls
    assert (go, _find(r, ".notify()", "audittrail")) not in calls
    assert (go, _find(r, ".notify()", "support_notifier")) not in calls


# ── Enum- and trait-typed receivers are refused (#12) ────────────────────────
#
# `enum_declaration` and `trait_declaration` mint no definition node either, so
# they leak exactly like interfaces did before #5: `App\Enums\Status` (enum)
# beside an unrelated `App\Legacy\Status` (class) leaves ONE definition under
# that short name, and the single-definition guard binds the stranger. The
# Laravel shape is an enum mirroring a model. Enums and traits are added to the
# refusal pre-scan only — they still mint no nodes, so an enum's own methods
# stay unresolvable as call targets (a deliberate recall gap, not a wrong edge).

_ENUM_CORPUS = {
    "app/Enums/Status.php": (
        "<?php\nnamespace App\\Enums;\n"
        "enum Status: string {\n"
        "    case Active = 'a';\n"
        "    public function label(): string { return 'ENUM'; }\n}\n"
    ),
    "app/Legacy/Status.php": (
        "<?php\nnamespace App\\Legacy;\n"
        "class Status {\n    public function label(): string { return 'WRONG'; }\n}\n"
    ),
}


def _labelled(calls, caller: str) -> bool:
    return any(src == caller and "label" in tgt.lower() for src, tgt in calls)


def _runner(body: str) -> str:
    return (
        "<?php\n"
        "namespace App;\n"
        "use App\\Enums\\Status;\n"
        "class Runner {\n"
        f"{body}\n"
        "}\n"
    )


def test_enum_typed_property_emits_no_edge(tmp_path: Path):
    """`private Status $status;` where Status is an enum: the same-short-named
    `App\\Legacy\\Status` class is a total stranger, never the receiver."""
    calls, r = _calls(tmp_path, {
        **_ENUM_CORPUS,
        "app/Runner.php": _runner(
            "    private Status $status;\n"
            "    public function go(): void { $this->status->label(); }"
        ),
    })

    go = _find(r, ".go()", "runner")
    assert (go, _find(r, ".label()", "legacy_status")) not in calls
    assert not _labelled(calls, go)


def test_enum_promoted_ctor_param_emits_no_edge(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_ENUM_CORPUS,
        "app/Runner.php": _runner(
            "    public function __construct(private Status $status) {}\n"
            "    public function go(): void { $this->status->label(); }"
        ),
    })

    go = _find(r, ".go()", "runner")
    assert (go, _find(r, ".label()", "legacy_status")) not in calls
    assert not _labelled(calls, go)


def test_enum_typed_param_emits_no_edge(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_ENUM_CORPUS,
        "app/Runner.php": _runner(
            "    public function go(Status $s): void { $s->label(); }"
        ),
    })

    go = _find(r, ".go()", "runner")
    assert (go, _find(r, ".label()", "legacy_status")) not in calls
    assert not _labelled(calls, go)


def test_enum_fqn_typed_property_emits_no_edge(tmp_path: Path):
    """The sharpest form: the source names `\\App\\Enums\\Status` outright, so
    binding `App\\Legacy\\Status` contradicts the written type."""
    calls, r = _calls(tmp_path, {
        **_ENUM_CORPUS,
        "app/Runner.php": _runner(
            "    private \\App\\Enums\\Status $status;\n"
            "    public function go(): void { $this->status->label(); }"
        ),
    })

    go = _find(r, ".go()", "runner")
    assert (go, _find(r, ".label()", "legacy_status")) not in calls
    assert not _labelled(calls, go)


def test_enum_typed_local_new_emits_no_edge(tmp_path: Path):
    """The typed-local receiver path (#4) refuses enums too."""
    calls, r = _calls(tmp_path, {
        **_ENUM_CORPUS,
        "app/Runner.php": _runner(
            "    public function go(): void {\n"
            "        $s = new Status();\n"
            "        $s->label();\n"
            "    }"
        ),
    })

    go = _find(r, ".go()", "runner")
    assert (go, _find(r, ".label()", "legacy_status")) not in calls
    assert not _labelled(calls, go)


def test_enum_inline_new_emits_no_edge(tmp_path: Path):
    """The inline-new receiver path (#3) refuses enums too — an enum cannot be
    instantiated, so such a receiver must never bind a stranger."""
    calls, r = _calls(tmp_path, {
        **_ENUM_CORPUS,
        "app/Runner.php": _runner(
            "    public function go(): void {\n"
            "        (new \\App\\Enums\\Status())->label();\n"
            "    }"
        ),
    })

    go = _find(r, ".go()", "runner")
    assert (go, _find(r, ".label()", "legacy_status")) not in calls
    assert not _labelled(calls, go)


def test_enum_refusal_is_case_insensitive(tmp_path: Path):
    """PHP type names are case-insensitive: `status` IS `Status`."""
    calls, r = _calls(tmp_path, {
        **_ENUM_CORPUS,
        "app/Runner.php": _runner(
            "    private status $status;\n"
            "    public function go(): void { $this->status->label(); }"
        ),
    })

    go = _find(r, ".go()", "runner")
    assert not _labelled(calls, go)


def test_enum_without_a_colliding_class_emits_no_edge(tmp_path: Path):
    """Control: an enum mints no definition node, so its methods are not call
    targets at all. The collision above supplies the only candidate — this
    documents the (deliberate) recall gap that leaves."""
    calls, r = _calls(tmp_path, {
        "app/Enums/Status.php": _ENUM_CORPUS["app/Enums/Status.php"],
        "app/Runner.php": _runner(
            "    private Status $status;\n"
            "    public function go(): void { $this->status->label(); }"
        ),
    })

    go = _find(r, ".go()", "runner")
    assert not _labelled(calls, go)


def test_trait_typed_receiver_emits_no_edge(tmp_path: Path):
    """A trait is not a type, so a trait-typed receiver is already broken PHP —
    but it must still refuse rather than bind the same-short-named class."""
    calls, r = _calls(tmp_path, {
        "app/Support/Cache.php": (
            "<?php\nnamespace App\\Support;\n"
            "trait Cache {\n    public function flush(): void {}\n}\n"
        ),
        "app/Legacy/Cache.php": (
            "<?php\nnamespace App\\Legacy;\n"
            "class Cache {\n    public function flush(): void {}\n}\n"
        ),
        "app/Runner.php": (
            "<?php\nnamespace App;\n"
            "use App\\Support\\Cache;\n"
            "class Runner {\n"
            "    private Cache $cache;\n"
            "    public function go(): void { $this->cache->flush(); }\n"
            "}\n"
        ),
    })

    go = _find(r, ".go()", "runner")
    assert (go, _find(r, ".flush()", "legacy_cache")) not in calls
    assert not any(src == go and "flush" in tgt.lower() for src, tgt in calls)


def test_class_receiver_still_resolves_when_an_enum_exists(tmp_path: Path):
    """The refusal is name-scoped: a CLASS-typed receiver still resolves with an
    unrelated enum (and a same-named-method decoy class) in the corpus."""
    calls, r = _calls(tmp_path, {
        "app/Enums/Status.php": _ENUM_CORPUS["app/Enums/Status.php"],
        "app/Models/Lead.php": (
            "<?php\nnamespace App\\Models;\n"
            "class Lead {\n    public function label(): string { return 'L'; }\n}\n"
        ),
        "app/Audit/AuditTrail.php": (
            "<?php\nnamespace App\\Audit;\n"
            "class AuditTrail {\n    public function label(): string { return 'A'; }\n}\n"
        ),
        "app/Runner.php": (
            "<?php\nnamespace App;\n"
            "use App\\Models\\Lead;\n"
            "class Runner {\n"
            "    private Lead $lead;\n"
            "    public function go(): void { $this->lead->label(); }\n"
            "}\n"
        ),
    })

    go = _find(r, ".go()", "runner")
    assert (go, _find(r, ".label()", "lead")) in calls
    assert (go, _find(r, ".label()", "audittrail")) not in calls
