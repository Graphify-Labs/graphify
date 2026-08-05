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
