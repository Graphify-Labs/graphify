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

from graphify.extract import _php_context_interface_entry, extract


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
    """Two `LeadHunterService` definitions and no claim on the name: the
    single-definition guard refuses. (With a `use` import naming one of them
    the declared-FQN index now binds it instead — that recall win is #22's,
    pinned in `test_php_alias_binding.py`.)"""
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


# The corroborating fact is the namespace the DEFINING FILE declares (#14).
# PSR-4 is a convention, not an invariant, so the path alone promoted two wrong
# names to EXTRACTED 1.0: one naming a class that exists nowhere in the corpus
# (declared namespace ≠ path), and one naming a different class that merely
# matched as a path tail. The path survives only as the fallback for a file
# that declares no namespace at all.


def test_declared_namespace_disagreeing_with_the_path_does_not_promote(tmp_path: Path):
    """`app/Services/LeadHunterService.php` declaring `namespace App\\Vendor;`
    means `App\\Services\\LeadHunterService` exists NOWHERE — the short name
    still resolves to the one definition, but at INFERRED, not 1.0."""
    calls, r = _calls(tmp_path, {
        "app/Services/LeadHunterService.php": (
            "<?php\nnamespace App\\Vendor;\n"
            "class LeadHunterService {\n"
            "    public function search(array $filters): array { return []; }\n}\n"
        ),
        "app/Audit/AuditLog.php": _DECOY,
        "app/Http/Controllers/LeadController.php": _controller(
            "return (new \\App\\Services\\LeadHunterService())->search([]);"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    assert (index, _find(r, ".search()", "auditlog")) not in calls
    edge = calls[(index, service_search)]
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.8


def test_truncated_root_namespace_does_not_corroborate(tmp_path: Path):
    """`\\Services\\LeadHunterService` is a ROOT-namespace class, a different
    one from `App\\Services\\LeadHunterService` — a missing `use` plus a leading
    backslash is a common bug and must not be rewarded with 1.0."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "return (new \\Services\\LeadHunterService())->search([]);"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    assert (index, _find(r, ".search()", "auditlog")) not in calls
    edge = calls[(index, service_search)]
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.8


def test_braced_namespace_block_corroborates(tmp_path: Path):
    """`namespace App\\Services { … }` declares the same fact as the statement
    form, so the whole-name match still promotes."""
    calls, r = _calls(tmp_path, {
        "app/Services/LeadHunterService.php": (
            "<?php\nnamespace App\\Services {\n"
            "    class LeadHunterService {\n"
            "        public function search(array $filters): array { return []; }\n"
            "    }\n}\n"
        ),
        "app/Audit/AuditLog.php": _DECOY,
        "app/Http/Controllers/LeadController.php": _controller(
            "return (new \\App\\Services\\LeadHunterService())->search([]);"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    assert (index, _find(r, ".search()", "auditlog")) not in calls
    assert calls[(index, service_search)]["confidence"] == "EXTRACTED"


def test_file_declaring_no_namespace_still_corroborates_by_path(tmp_path: Path):
    """A file that declares nothing leaves the PSR-4 path as the only evidence
    there is — unchanged behaviour, deliberately kept."""
    calls, r = _calls(tmp_path, {
        "app/Services/LeadHunterService.php": (
            "<?php\n"
            "class LeadHunterService {\n"
            "    public function search(array $filters): array { return []; }\n}\n"
        ),
        "app/Audit/AuditLog.php": _DECOY,
        "app/Http/Controllers/LeadController.php": _controller(
            "return (new \\App\\Services\\LeadHunterService())->search([]);"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    assert (index, _find(r, ".search()", "auditlog")) not in calls
    assert calls[(index, service_search)]["confidence"] == "EXTRACTED"


def test_written_namespace_match_is_case_insensitive(tmp_path: Path):
    """PHP namespaces are case-insensitive, so `\\app\\services\\…` names the
    same class the file declares."""
    calls, r = _calls(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "return (new \\app\\services\\LeadHunterService())->search([]);"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    assert (index, _find(r, ".search()", "auditlog")) not in calls
    assert calls[(index, service_search)]["confidence"] == "EXTRACTED"


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


# ── Interface-typed receivers bind to the interface itself (#5, #53) ─────────
#
# Pre-#47 a PHP `interface_declaration` minted NO definition node, so an
# interface-typed receiver could only ever bind a same-short-named STRANGER.
# The dangerous case is Laravel's Contracts convention: `App\Contracts\Notifier`
# (interface) next to an unrelated `App\Support\Notifier` (class) — the
# short-name lookup found exactly one definition, the wrong one, and satisfied
# the ambiguity guard. #5 answered that with a blanket refusal keyed off a
# pre-scan of every interface/enum/trait name in the corpus.
#
# Post-#47 the declaration mints a canonical sourced node and its own methods
# attach to it, so the blanket refusal is no longer what keeps the stranger out:
# the collision now presents TWO definitions under the short name and is refused
# by the single-definition guard, or decisively by `PhpNameResolver` when the
# calling file `use`-imports the name. #53 lifts it, so a receiver typed with an
# UNAMBIGUOUS interface name binds to that interface's own method. Both halves
# are pinned below: the collisions stay unbound, the unique names now bind.
# Implementations are still never guessed.

# One `Notifier` in the corpus (an interface), plus a decoy class carrying the
# same METHOD name under a different type name — a bare method-name match would
# take the decoy, only the receiver's declared type picks the interface.
_UNIQUE_IFACE_CORPUS = {
    "app/Contracts/Notifier.php": (
        "<?php\nnamespace App\\Contracts;\n"
        "interface Notifier {\n    public function send(string $m): void;\n}\n"
    ),
    "app/Audit/AuditLog.php": (
        "<?php\nnamespace App\\Audit;\n"
        "class AuditLog {\n    public function send(string $m): void {}\n}\n"
    ),
}

# The Contracts collision: TWO types answer to `Notifier`, so nothing may bind.
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


def test_unique_interface_typed_property_binds_to_the_interface_method(tmp_path: Path):
    """#53 criterion 1: `private Notifier $n` + `$this->n->send()` where the
    corpus holds exactly ONE `Notifier` — the interface — binds to the
    interface's own `send()` declaration node (post-#47 it has one)."""
    calls, r = _calls(tmp_path, {
        **_UNIQUE_IFACE_CORPUS,
        "app/Http/Dispatcher.php": (
            "<?php\n"
            "namespace App\\Http;\n"
            "use App\\Contracts\\Notifier;\n"
            "class Dispatcher {\n"
            "    private Notifier $notifier;\n"
            "    public function go(): void { $this->notifier->send('x'); }\n"
            "}\n"
        ),
    })

    go = _find(r, ".go()", "dispatcher")
    contract_send = _find(r, ".send()", "contracts_notifier")
    assert (go, contract_send) in calls, \
        "an unambiguous interface-typed receiver names the interface's method"
    assert (go, _find(r, ".send()", "auditlog")) not in calls, \
        "the same method name on an unrelated class is not the receiver's type"
    edge = calls[(go, contract_send)]
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.8
    assert edge["context"] == "call"


def test_unique_interface_binds_through_the_single_definition_guard(tmp_path: Path):
    """The same binding with NO `use` import to claim the name, so
    `PhpNameResolver` abstains and the corpus-wide short-name census decides —
    the plain single-definition guard path. Both files sit in the global
    namespace, which is what makes the unqualified annotation name the
    interface."""
    calls, r = _calls(tmp_path, {
        "app/Contracts/Notifier.php": (
            "<?php\n"
            "interface Notifier {\n    public function send(string $m): void;\n}\n"
        ),
        "app/Audit/AuditLog.php": (
            "<?php\n"
            "class AuditLog {\n    public function send(string $m): void {}\n}\n"
        ),
        "app/Http/Dispatcher.php": (
            "<?php\n"
            "class Dispatcher {\n"
            "    private Notifier $notifier;\n"
            "    public function go(): void { $this->notifier->send('x'); }\n"
            "}\n"
        ),
    })

    go = _find(r, ".go()", "dispatcher")
    assert (go, _find(r, ".send()", "contracts_notifier")) in calls
    assert (go, _find(r, ".send()", "auditlog")) not in calls


def test_interface_typed_param_binds_to_the_interface_method(tmp_path: Path):
    """The typed-parameter receiver path (#4) reaches the interface too."""
    calls, r = _calls(tmp_path, {
        **_UNIQUE_IFACE_CORPUS,
        "app/Http/Dispatcher.php": (
            "<?php\n"
            "namespace App\\Http;\n"
            "use App\\Contracts\\Notifier;\n"
            "class Dispatcher {\n"
            "    public function go(Notifier $n): void { $n->send('x'); }\n"
            "}\n"
        ),
    })

    go = _find(r, ".go()", "dispatcher")
    assert (go, _find(r, ".send()", "contracts_notifier")) in calls
    assert (go, _find(r, ".send()", "auditlog")) not in calls


def test_colliding_interface_and_class_short_name_emits_no_edge(tmp_path: Path):
    """#53 criterion 3, on the guard the lifted refusal hands the job to: with
    `App\\Contracts\\Notifier` (interface) and `App\\Support\\Notifier` (class)
    both in the corpus the short name censuses TWO definitions, so the
    single-definition guard refuses on its own. No `use` import here — the
    caller shares the interface's namespace, which is what makes the bare
    annotation name it — so `PhpNameResolver` abstains and the guard is the only
    thing standing between the receiver and the stranger. PHP itself would bind
    the interface; refusing is a recall gap, never a wrong edge."""
    calls, r = _calls(tmp_path, {
        **_IFACE_CORPUS,
        "app/Contracts/Dispatcher.php": (
            "<?php\n"
            "namespace App\\Contracts;\n"
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


def test_interface_typed_property_does_not_guess_implementation(tmp_path: Path):
    """The contract is the receiver's type; its implementations are not.

    `MailNotifier implements Notifier` is the only class that could satisfy the
    annotation at runtime, and it still gets NOTHING — an interface names a
    contract, and picking one implementation out of the corpus is the guess #5
    forbade and #53 does not reintroduce. What the receiver does bind is the
    interface's OWN `notify()` node (#47), which is where the fan-in belongs."""
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
    assert (go, _find(r, ".notify()", "contracts_notifier")) in calls


def test_interface_short_name_collision_binds_the_imported_one(tmp_path: Path):
    """`App\\Contracts\\Notifier` (interface) and `App\\Support\\Notifier`
    (unrelated class) share a short name, and the calling file's `use` says
    WHICH one it means.

    #5 could only refuse here: the interface minted no node, so the short-name
    census saw the stranger alone and would have bound it. Post-#47/#53 both
    are definitions, and the declared-FQN index (#22, extended to non-class
    declarations for #53) matches the imported FQN against the name the
    interface's own file declares — decisively, without ever consulting the
    census. The stranger is still what must not be bound."""
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
    assert (go, _find(r, ".notify()", "contracts_notifier")) in calls


def test_interface_binding_is_case_insensitive(tmp_path: Path):
    """PHP type names are case-insensitive: `notifier` IS `Notifier`, so the
    lowercase annotation reaches the same interface and still never the
    same-short-named class."""
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
    assert (go, _find(r, ".notify()", "contracts_notifier")) in calls
    assert (go, _find(r, ".notify()", "support_notifier")) not in calls


def test_interface_typed_param_binds_the_imported_interface(tmp_path: Path):
    """The typed-parameter receiver path (#4) reaches the interface too."""
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
    assert (go, _find(r, ".notify()", "contracts_notifier")) in calls
    assert (go, _find(r, ".notify()", "support_notifier")) not in calls
    assert (go, _find(r, ".notify()", "mailnotifier")) not in calls


def test_interface_inline_new_emits_no_edge(tmp_path: Path):
    """The inline-new receiver path (#3) emits nothing here, and for the reason
    that survives the lift: this file imports nothing, and an inline `new`
    carries its written namespace on `receiver_qualified` — which only feeds the
    EXTRACTED promotion, not `resolve_type_name`. So the resolver abstains, the
    short name censuses TWO `Notifier` definitions, and the single-definition
    guard refuses. `new` on an interface is invalid PHP anyway; the invariant
    worth pinning is that the same-short-named stranger is never what it binds."""
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


def test_interface_typed_local_new_binds_the_imported_interface(tmp_path: Path):
    """The typed-local receiver path (#4): `$n = new Notifier()` is broken PHP
    for an interface, but the local's declared type is still the name the file
    imported — so it binds the interface it NAMES, never the stranger the short
    name would otherwise census."""
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
    assert (go, _find(r, ".notify()", "contracts_notifier")) in calls


def test_class_receiver_still_resolves_when_an_interface_exists(tmp_path: Path):
    """Name scoping: a CLASS-typed receiver resolves to its class, and the
    same-named interface elsewhere in the corpus changes nothing."""
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


# ── Enum- and trait-typed receivers (#12, #53) ───────────────────────────────
#
# Pre-#47 `enum_declaration` and `trait_declaration` minted no definition node
# either, so they leaked exactly like interfaces did before #5: `App\Enums\Status`
# (enum) beside an unrelated `App\Legacy\Status` (class) left ONE definition under
# that short name, and the single-definition guard bound the stranger. The
# Laravel shape is an enum mirroring a model. Post-#47/#53 the collision censuses
# two definitions and is refused on that basis, while an enum's own methods ARE
# call targets — the recall gap #12 documented is closed below.

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


def test_enum_typed_property_binds_the_imported_enum(tmp_path: Path):
    """`private Status $status;` where Status is the imported enum: the
    same-short-named `App\\Legacy\\Status` class is a total stranger and never
    the receiver, while the enum's own `label()` (#47) is exactly what the
    annotation names."""
    calls, r = _calls(tmp_path, {
        **_ENUM_CORPUS,
        "app/Runner.php": _runner(
            "    private Status $status;\n"
            "    public function go(): void { $this->status->label(); }"
        ),
    })

    go = _find(r, ".go()", "runner")
    assert (go, _find(r, ".label()", "legacy_status")) not in calls
    assert (go, _find(r, ".label()", "enums_status")) in calls


def test_enum_promoted_ctor_param_binds_the_imported_enum(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_ENUM_CORPUS,
        "app/Runner.php": _runner(
            "    public function __construct(private Status $status) {}\n"
            "    public function go(): void { $this->status->label(); }"
        ),
    })

    go = _find(r, ".go()", "runner")
    assert (go, _find(r, ".label()", "legacy_status")) not in calls
    assert (go, _find(r, ".label()", "enums_status")) in calls


def test_enum_typed_param_binds_the_imported_enum(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        **_ENUM_CORPUS,
        "app/Runner.php": _runner(
            "    public function go(Status $s): void { $s->label(); }"
        ),
    })

    go = _find(r, ".go()", "runner")
    assert (go, _find(r, ".label()", "legacy_status")) not in calls
    assert (go, _find(r, ".label()", "enums_status")) in calls


def test_enum_fqn_typed_property_binds_the_written_enum(tmp_path: Path):
    """The sharpest form: the source names `\\App\\Enums\\Status` outright, so
    binding `App\\Legacy\\Status` would contradict the written type — and the
    written type is precisely what the declared-FQN index now matches."""
    calls, r = _calls(tmp_path, {
        **_ENUM_CORPUS,
        "app/Runner.php": _runner(
            "    private \\App\\Enums\\Status $status;\n"
            "    public function go(): void { $this->status->label(); }"
        ),
    })

    go = _find(r, ".go()", "runner")
    assert (go, _find(r, ".label()", "legacy_status")) not in calls
    assert (go, _find(r, ".label()", "enums_status")) in calls


def test_enum_typed_local_new_binds_the_imported_enum(tmp_path: Path):
    """The typed-local receiver path (#4): `new Status()` is broken PHP for an
    enum, but the local's declared type still names the imported enum and never
    the stranger."""
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
    assert (go, _find(r, ".label()", "enums_status")) in calls


def test_enum_inline_new_binds_the_written_enum(tmp_path: Path):
    """The inline-new receiver path (#3) contrasted with the interface one
    above: `new` on an enum is equally invalid PHP, but here the runner DOES
    `use App\\Enums\\Status`, so the claim is decided by the declared-FQN index
    rather than left to the two-candidate census. The written
    `\\App\\Enums\\Status` then corroborates the enum's declared name, which is
    what promotes the edge to EXTRACTED. The stranger stays unbound either
    way — that is the invariant #12 was protecting."""
    calls, r = _calls(tmp_path, {
        **_ENUM_CORPUS,
        "app/Runner.php": _runner(
            "    public function go(): void {\n"
            "        (new \\App\\Enums\\Status())->label();\n"
            "    }"
        ),
    })

    go = _find(r, ".go()", "runner")
    enum_label = _find(r, ".label()", "enums_status")
    assert (go, _find(r, ".label()", "legacy_status")) not in calls
    assert (go, enum_label) in calls
    assert calls[(go, enum_label)]["confidence"] == "EXTRACTED"


def test_enum_binding_is_case_insensitive(tmp_path: Path):
    """PHP type names are case-insensitive: `status` IS `Status`."""
    calls, r = _calls(tmp_path, {
        **_ENUM_CORPUS,
        "app/Runner.php": _runner(
            "    private status $status;\n"
            "    public function go(): void { $this->status->label(); }"
        ),
    })

    go = _find(r, ".go()", "runner")
    assert (go, _find(r, ".label()", "enums_status")) in calls
    assert (go, _find(r, ".label()", "legacy_status")) not in calls


def test_enum_without_a_colliding_class_binds_to_the_enum_method(tmp_path: Path):
    """#53 criterion 2: drop the colliding class and `Status` names exactly one
    type — the enum — whose `label()` hangs off its own declaration node
    (#47). The receiver binds there. This is the recall gap #12 documented,
    now closed; the decoy class proves it is the declared type doing the work
    and not a bare method-name match."""
    calls, r = _calls(tmp_path, {
        "app/Enums/Status.php": _ENUM_CORPUS["app/Enums/Status.php"],
        "app/Models/Lead.php": (
            "<?php\nnamespace App\\Models;\n"
            "class Lead {\n    public function label(): string { return 'L'; }\n}\n"
        ),
        "app/Runner.php": _runner(
            "    private Status $status;\n"
            "    public function go(): void { $this->status->label(); }"
        ),
    })

    go = _find(r, ".go()", "runner")
    enum_label = _find(r, ".label()", "enums_status")
    assert (go, enum_label) in calls, \
        "an unambiguous enum-typed receiver names the enum's own method"
    assert (go, _find(r, ".label()", "models_lead")) not in calls
    edge = calls[(go, enum_label)]
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.8


def test_trait_typed_receiver_binds_the_imported_trait(tmp_path: Path):
    """A trait is not a type, so a trait-typed receiver is already broken PHP.
    The graph follows the name the source actually writes — the imported
    `App\\Support\\Cache` trait, whose `flush()` is a real node post-#47 — and
    never the same-short-named `App\\Legacy\\Cache` class, which is what the
    #12 refusal existed to prevent."""
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
    assert (go, _find(r, ".flush()", "support_cache")) in calls


def test_class_receiver_still_resolves_when_an_enum_exists(tmp_path: Path):
    """Name scoping: a CLASS-typed receiver resolves to its class with an
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


# ── Full and incremental builds must AGREE (#11, #12, #53) ───────────────────
#
# Every test above goes through ONE full extract(), where a declaring file's
# facts reach the resolver through `per_file` — which aligns 1:1 with the files
# dispatched this run. `graphify update`/watch dispatch only the CHANGED files
# and hand the unchanged corpus back as read-only resolution context, so any
# fact that lives only in `per_file` stops applying the moment the declaring
# file is not re-extracted. That asymmetry has bitten in both directions: #11
# lost the interface REFUSAL and bound a same-short-named stranger, and #53's
# `use`-claim guard lost its DECLARED FQN and bound an in-corpus interface a
# vendor import provably does not name (`..._refuses_on_both_builds` below).
# Each test here therefore asserts the incremental verdict AND the full one.
# The context is assembled exactly as watch.py builds it from graph.json
# (watch.py:1205-1240): a FIELD SUBSET of the persisted AST nodes — id, label,
# source_file, file_type, type plus the persisted underscore markers — and the
# corpus's contains/method edges, both scoped to the files NOT being re-extracted.

_CTX_NODE_FIELDS = ("label", "source_file", "file_type", "type")
_CTX_MARKERS = ("_callable", "_callable_class", "_php_non_class_types",
                "_php_interfaces", "_php_class_fqns")


def _watch_resolution_context(result: dict, unchanged: set[str]):
    """Mirror watch.py's resolution-context assembly for the `unchanged` files."""
    nodes = []
    for node in result["nodes"]:
        if not node.get("id") or node.get("source_file") not in unchanged:
            continue
        ctx = {"id": node["id"]}
        ctx.update({field: node.get(field) for field in _CTX_NODE_FIELDS})
        ctx.update({m: node[m] for m in _CTX_MARKERS if node.get(m)})
        nodes.append(ctx)
    edges = [
        {
            "source": edge.get("source"),
            "target": edge.get("target"),
            "relation": edge.get("relation"),
            "source_file": edge.get("source_file"),
        }
        for edge in result["edges"]
        if edge.get("relation") in ("contains", "method")
        and edge.get("source_file") in unchanged
    ]
    return nodes, edges


def _full_then_incremental(tmp_path: Path, files: dict[str, str], changed: str):
    """Full-extract `files`, then re-extract ONLY `changed` (its body edited) with
    the rest supplied as watch-shaped resolution context.

    Returns ((full_calls, full_result), (inc_calls, inc_result)). Both runs share
    `cache_root`, the anchor watch passes, so node ids line up across them.
    """
    corpus = tmp_path / "corpus"
    paths = {}
    for name, body in files.items():
        path = corpus / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths[name] = path

    def _calls_of(result):
        return {
            (edge["source"], edge["target"]): edge
            for edge in result["edges"]
            if edge.get("relation") == "calls"
        }

    full = extract(list(paths.values()), cache_root=corpus)
    # Edit the caller only — an unrelated statement, so its raw_calls are re-derived
    # while every other file stays byte-identical and therefore undispatched.
    paths[changed].write_text(
        files[changed].replace("class ", "// touched\nclass ", 1), encoding="utf-8"
    )
    ctx_nodes, ctx_edges = _watch_resolution_context(
        full, unchanged=set(files) - {changed}
    )
    inc = extract(
        [paths[changed]],
        cache_root=corpus,
        resolution_context_nodes=ctx_nodes,
        resolution_context_edges=ctx_edges,
    )
    return (_calls_of(full), full), (_calls_of(inc), inc)


_INCR_DISPATCHER = "app/Http/Dispatcher.php"


def test_interface_binding_agrees_across_an_incremental_rebuild(tmp_path: Path):
    """The interface file is unchanged and therefore NOT dispatched: its
    declaration node, its `method` edge and its declared FQN all reach the
    resolver through the replay channel alone, and the verdict must match the
    full build's (#11, #53)."""
    (full_calls, full), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        **_IFACE_CORPUS,
        _INCR_DISPATCHER: (
            "<?php\n"
            "namespace App\\Http;\n"
            "use App\\Contracts\\Notifier;\n"
            "class Dispatcher {\n"
            "    private Notifier $notifier;\n"
            "    public function go(): void { $this->notifier->notify('x'); }\n"
            "}\n"
        ),
    }, changed=_INCR_DISPATCHER)

    go = _find(inc, ".go()", "dispatcher")
    contract = _find(full, ".notify()", "contracts_notifier")
    assert (go, contract) in full_calls, "full-build baseline binds the contract"
    assert (go, contract) in inc_calls, \
        "an undispatched interface file must keep its replayed binding"


def test_interface_short_name_collision_never_binds_the_stranger_incrementally(tmp_path: Path):
    """The Laravel Contracts collision across a rebuild. Whatever the resolver
    decides about the imported `App\\Contracts\\Notifier`, the unrelated
    `App\\Support\\Notifier` class is what must never receive the edge — it was
    the lone DEFINITION under that short name before #47, which is exactly how
    #11 used to bind it."""
    (full_calls, full), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        **_IFACE_CORPUS,
        _INCR_DISPATCHER: (
            "<?php\n"
            "namespace App\\Http;\n"
            "use App\\Contracts\\Notifier;\n"
            "class Dispatcher {\n"
            "    private Notifier $notifier;\n"
            "    public function go(): void { $this->notifier->notify('x'); }\n"
            "}\n"
        ),
    }, changed=_INCR_DISPATCHER)

    go = _find(inc, ".go()", "dispatcher")
    # The stranger's node lives in an unchanged file, so its id comes from the
    # full result — the incremental run returns only fresh nodes.
    stranger = _find(full, ".notify()", "support_notifier")
    assert (go, stranger) not in full_calls
    assert (go, stranger) not in inc_calls, \
        "a rebuild must not bind a contract-typed receiver to a same-named class"


def test_interface_binding_is_case_insensitive_incrementally(tmp_path: Path):
    """PHP type names are case-insensitive on the incremental path too: names
    are folded on both sides, never compared verbatim."""
    (full_calls, full), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        **_IFACE_CORPUS,
        _INCR_DISPATCHER: (
            "<?php\n"
            "namespace App\\Http;\n"
            "use App\\Contracts\\Notifier;\n"
            "class Dispatcher {\n"
            "    private notifier $notifier;\n"
            "    public function go(): void { $this->notifier->notify('x'); }\n"
            "}\n"
        ),
    }, changed=_INCR_DISPATCHER)

    go = _find(inc, ".go()", "dispatcher")
    contract = _find(full, ".notify()", "contracts_notifier")
    assert (go, contract) in full_calls
    assert (go, contract) in inc_calls
    assert (go, _find(full, ".notify()", "support_notifier")) not in inc_calls


def test_class_typed_receiver_still_resolves_incrementally(tmp_path: Path):
    """Positive control for the two tests above: binding stays name-scoped
    across a rebuild — a CLASS-typed receiver still binds into its unchanged
    file (#2437), and the decoys still get nothing."""
    (_, full), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        **_IFACE_CORPUS,
        "app/Audit/AuditTrail.php": (
            "<?php\nnamespace App\\Audit;\n"
            "class AuditTrail {\n    public function notify(string $m): void {}\n}\n"
        ),
        _INCR_DISPATCHER: (
            "<?php\n"
            "namespace App\\Http;\n"
            "use App\\Services\\MailNotifier;\n"
            "class Dispatcher {\n"
            "    private MailNotifier $notifier;\n"
            "    public function go(): void { $this->notifier->notify('x'); }\n"
            "}\n"
        ),
    }, changed=_INCR_DISPATCHER)

    go = _find(inc, ".go()", "dispatcher")
    assert (go, _find(full, ".notify()", "mailnotifier")) in inc_calls, \
        "the incremental path must still resolve a class-typed receiver"
    assert (go, _find(full, ".notify()", "audittrail")) not in inc_calls
    assert (go, _find(full, ".notify()", "support_notifier")) not in inc_calls


def _sent(calls, caller: str) -> bool:
    return any(src == caller and "send" in tgt.lower() for src, tgt in calls)


def test_vendor_import_shadowing_an_interface_refuses_on_both_builds(tmp_path: Path):
    """A `use` of a same-short-named type from OUTSIDE the corpus must refuse —
    on the incremental path as well as the full one (#16, #53).

    `use Illuminate\\Contracts\\Notifications\\Notifier;` CLAIMS the short name
    for a vendor interface the corpus does not contain, so the in-corpus
    `App\\Contracts\\Notifier` is a different type and must get no edge. That
    verdict is `PhpNameResolver`'s (#21), and it is only decisive when the
    declaration carries a declared FQN: without one the guard falls back to
    comparing the node's PSR-4 PATH, and a replayed context node's path is
    RELATIVIZED — fewer segments than the vendor FQN has — which trips the
    "not enough evidence" bail-out and binds. The full build never sees that
    (its paths are still absolute at resolver time), so full and incremental
    must be asserted TOGETHER or the hole hides in the mode `graphify update`
    actually runs in."""
    (full_calls, full), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        "app/Contracts/Notifier.php": (
            "<?php\nnamespace App\\Contracts;\n"
            "interface Notifier {\n    public function send(string $m): void;\n}\n"
        ),
        _INCR_DISPATCHER: (
            "<?php\n"
            "namespace App\\Http;\n"
            "use Illuminate\\Contracts\\Notifications\\Notifier;\n"
            "class Dispatcher {\n"
            "    private Notifier $notifier;\n"
            "    public function go(): void { $this->notifier->send('x'); }\n"
            "}\n"
        ),
    }, changed=_INCR_DISPATCHER)

    go = _find(inc, ".go()", "dispatcher")
    assert not _sent(full_calls, go), "full-build baseline must refuse the claim"
    assert not _sent(inc_calls, go), \
        "a vendor `use` must not bind the in-corpus interface on a rebuild"


def test_vendor_import_shadowing_an_enum_refuses_on_both_builds(tmp_path: Path):
    """The enum shape of the test above, same channel and same verdict."""
    (full_calls, full), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        "app/Enums/Status.php": _ENUM_CORPUS["app/Enums/Status.php"],
        _INCR_RUNNER: (
            "<?php\n"
            "namespace App\\Http;\n"
            "use Illuminate\\Contracts\\Support\\Status;\n"
            "class Runner {\n"
            "    private Status $status;\n"
            "    public function go(): void { $this->status->label(); }\n"
            "}\n"
        ),
    }, changed=_INCR_RUNNER)

    go = _find(inc, ".go()", "runner")
    assert not _labelled(full_calls, go), "full-build baseline must refuse the claim"
    assert not _labelled(inc_calls, go), \
        "a vendor `use` must not bind the in-corpus enum on a rebuild"


def test_unique_interface_binding_survives_incremental_rebuild(tmp_path: Path):
    """#53 criterion 4: the interface's file is unchanged and therefore NOT
    dispatched — its declaration node and its `method` edge reach the resolver
    only through the #2437 replay channel. The binding must be the same one the
    full build makes, or every interface edge would evaporate on the first
    `graphify update`."""
    (full_calls, full), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        **_UNIQUE_IFACE_CORPUS,
        _INCR_DISPATCHER: (
            "<?php\n"
            "namespace App\\Http;\n"
            "use App\\Contracts\\Notifier;\n"
            "class Dispatcher {\n"
            "    private Notifier $notifier;\n"
            "    public function go(): void { $this->notifier->send('x'); }\n"
            "}\n"
        ),
    }, changed=_INCR_DISPATCHER)

    go = _find(inc, ".go()", "dispatcher")
    contract_send = _find(full, ".send()", "contracts_notifier")
    assert (go, contract_send) in full_calls, "full-build baseline must bind"
    assert (go, contract_send) in inc_calls, \
        "an undispatched interface file must keep its replayed binding"
    assert (go, _find(full, ".send()", "auditlog")) not in inc_calls


# ENUM and TRAIT declarations replay over the same channel and get the same
# parity treatment (#12). Before #47 an unchanged `App\Enums\Status` file left
# `App\Legacy\Status` as the one visible definition on a rebuild — the wrong edge
# #12 had closed on the full-build path, coming straight back on the incremental
# one. Now it is the declared FQN that has to survive the replay for the two
# builds to agree; the assertions below pin both ends of that.

_INCR_RUNNER = "app/Http/Runner.php"


def _incr_enum_corpus(body: str) -> dict[str, str]:
    return {
        **_ENUM_CORPUS,
        _INCR_RUNNER: (
            "<?php\n"
            "namespace App\\Http;\n"
            "use App\\Enums\\Status;\n"
            "class Runner {\n"
            f"{body}\n"
            "}\n"
        ),
    }


def test_enum_binding_agrees_across_an_incremental_rebuild(tmp_path: Path):
    """The enum's file is unchanged and therefore NOT dispatched: its node, its
    `method` edge and its declared FQN must all still reach the resolver, so the
    rebuild agrees with the full build — and the same-short-named
    `App\\Legacy\\Status` gets nothing on either."""
    (full_calls, full), (inc_calls, inc) = _full_then_incremental(
        tmp_path,
        _incr_enum_corpus(
            "    private Status $status;\n"
            "    public function go(): void { $this->status->label(); }"
        ),
        changed=_INCR_RUNNER,
    )

    go = _find(inc, ".go()", "runner")
    stranger = _find(full, ".label()", "legacy_status")
    enum_label = _find(full, ".label()", "enums_status")
    assert (go, enum_label) in full_calls, "full-build baseline binds the enum"
    assert (go, enum_label) in inc_calls, \
        "an undispatched enum file must keep its replayed binding"
    assert (go, stranger) not in inc_calls, \
        "a rebuild must not hand the edge to App\\Legacy\\Status"


def test_enum_typed_param_binding_agrees_across_an_incremental_rebuild(tmp_path: Path):
    """The typed-parameter entry point keeps full/incremental parity too."""
    (full_calls, full), (inc_calls, inc) = _full_then_incremental(
        tmp_path,
        _incr_enum_corpus("    public function go(Status $s): void { $s->label(); }"),
        changed=_INCR_RUNNER,
    )

    go = _find(inc, ".go()", "runner")
    enum_label = _find(full, ".label()", "enums_status")
    assert (go, enum_label) in full_calls
    assert (go, enum_label) in inc_calls
    assert (go, _find(full, ".label()", "legacy_status")) not in inc_calls


def test_trait_binding_agrees_across_an_incremental_rebuild(tmp_path: Path):
    """A trait-typed receiver is broken PHP, but its verdict must not depend on
    which files a rebuild happened to dispatch: the imported trait on both
    builds, the same-short-named `App\\Legacy\\Cache` class on neither."""
    (full_calls, full), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        "app/Support/Cache.php": (
            "<?php\nnamespace App\\Support;\n"
            "trait Cache {\n    public function flush(): void {}\n}\n"
        ),
        "app/Legacy/Cache.php": (
            "<?php\nnamespace App\\Legacy;\n"
            "class Cache {\n    public function flush(): void {}\n}\n"
        ),
        _INCR_RUNNER: (
            "<?php\n"
            "namespace App\\Http;\n"
            "use App\\Support\\Cache;\n"
            "class Runner {\n"
            "    private Cache $cache;\n"
            "    public function go(): void { $this->cache->flush(); }\n"
            "}\n"
        ),
    }, changed=_INCR_RUNNER)

    go = _find(inc, ".go()", "runner")
    trait_flush = _find(full, ".flush()", "support_cache")
    assert (go, trait_flush) in full_calls
    assert (go, trait_flush) in inc_calls
    assert (go, _find(full, ".flush()", "legacy_cache")) not in inc_calls


def test_class_typed_receiver_still_resolves_incrementally_beside_an_enum(tmp_path: Path):
    """Positive control for the three above: binding stays name-scoped on the
    incremental path — a CLASS-typed receiver still binds into its unchanged
    file, with an unrelated enum and a same-named-method decoy in the corpus."""
    (_, full), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        "app/Enums/Status.php": _ENUM_CORPUS["app/Enums/Status.php"],
        "app/Models/Lead.php": (
            "<?php\nnamespace App\\Models;\n"
            "class Lead {\n    public function label(): string { return 'L'; }\n}\n"
        ),
        "app/Audit/AuditTrail.php": (
            "<?php\nnamespace App\\Audit;\n"
            "class AuditTrail {\n    public function label(): string { return 'A'; }\n}\n"
        ),
        _INCR_RUNNER: (
            "<?php\n"
            "namespace App\\Http;\n"
            "use App\\Models\\Lead;\n"
            "class Runner {\n"
            "    private Lead $lead;\n"
            "    public function go(): void { $this->lead->label(); }\n"
            "}\n"
        ),
    }, changed=_INCR_RUNNER)

    go = _find(inc, ".go()", "runner")
    assert (go, _find(full, ".label()", "models_lead")) in inc_calls, \
        "the incremental path must still resolve a class-typed receiver"
    assert (go, _find(full, ".label()", "audittrail")) not in inc_calls


def test_unique_enum_binding_survives_incremental_rebuild(tmp_path: Path):
    """#53 criterion 4 for the enum shape: the enum's file is unchanged, so its
    declaration node and its `method` edge reach the resolver only through the
    #2437 replay channel — and the binding must match the full build's."""
    (full_calls, full), (inc_calls, inc) = _full_then_incremental(tmp_path, {
        "app/Enums/Status.php": _ENUM_CORPUS["app/Enums/Status.php"],
        "app/Models/Lead.php": (
            "<?php\nnamespace App\\Models;\n"
            "class Lead {\n    public function label(): string { return 'L'; }\n}\n"
        ),
        _INCR_RUNNER: (
            "<?php\n"
            "namespace App\\Http;\n"
            "use App\\Enums\\Status;\n"
            "class Runner {\n"
            "    private Status $status;\n"
            "    public function go(): void { $this->status->label(); }\n"
            "}\n"
        ),
    }, changed=_INCR_RUNNER)

    go = _find(inc, ".go()", "runner")
    enum_label = _find(full, ".label()", "enums_status")
    assert (go, enum_label) in full_calls, "full-build baseline must bind"
    assert (go, enum_label) in inc_calls, \
        "an undispatched enum file must keep its replayed binding"
    assert (go, _find(full, ".label()", "models_lead")) not in inc_calls


def test_legacy_php_interfaces_marker_spelling_is_still_read(tmp_path: Path):
    """Cache compatibility: a graph.json written before #12 carries the names
    under `_php_interfaces`, and both spellings must keep being read back off
    the resolution context — the rename must not silently drop a channel that
    older graphs are still using.

    #53 lifted the RECEIVER REFUSAL these names used to feed, so what is pinned
    here is the channel itself: `_php_context_interface_entry` recovering the
    unchanged corpus's declared names under either spelling. Resolution now runs
    off a different marker on the same nodes — `_php_class_fqns` (#23) — which
    is why the downgraded context still binds the imported contract and still
    leaves `App\\Support\\Notifier` alone."""
    (_, full), _ = _full_then_incremental(tmp_path, {
        **_IFACE_CORPUS,
        _INCR_DISPATCHER: (
            "<?php\n"
            "namespace App\\Http;\n"
            "use App\\Contracts\\Notifier;\n"
            "class Dispatcher {\n"
            "    private Notifier $notifier;\n"
            "    public function go(): void { $this->notifier->notify('x'); }\n"
            "}\n"
        ),
    }, changed=_INCR_DISPATCHER)

    ctx_nodes, ctx_edges = _watch_resolution_context(
        full, unchanged=set(_IFACE_CORPUS)
    )
    downgraded = 0
    for node in ctx_nodes:
        names = node.pop("_php_non_class_types", None)
        if names:
            node["_php_interfaces"] = names  # the pre-#12 spelling
            downgraded += 1
    assert downgraded == 1, "exactly the interface's file node carries the names"
    assert _php_context_interface_entry(ctx_nodes) == {
        "php_non_class_types": ["Notifier"]
    }, "the pre-#12 spelling must still be recovered off the context nodes"

    caller = tmp_path / "corpus" / _INCR_DISPATCHER
    inc = extract([caller], cache_root=tmp_path / "corpus",
                  resolution_context_nodes=ctx_nodes,
                  resolution_context_edges=ctx_edges)
    inc_calls = {
        (edge["source"], edge["target"])
        for edge in inc["edges"] if edge.get("relation") == "calls"
    }

    go = _find(inc, ".go()", "dispatcher")
    assert (go, _find(full, ".notify()", "support_notifier")) not in inc_calls
    assert (go, _find(full, ".notify()", "contracts_notifier")) in inc_calls


# ── Same-file union / intersection receivers (user story 11, #9) ──────────────
#
# The separate-file negatives above pass for the wrong reason: with the decoys in
# other files, the extractor's LEGACY in-file bare-name arm never runs, so only
# the cross-file resolver is exercised.  When the candidate classes live in the
# SAME file as the call, that arm fires and binds the receiver to whichever
# same-named method the label index saw last — pure file order, stamped
# EXTRACTED.  A union or intersection annotation proves the receiver has MORE
# THAN ONE possible class, so the extractor must defer to the resolver (which
# refuses an unstamped receiver) instead.
#
# Deletion scope is deliberately limited to `A|B` / `A&B`.  The concrete-type
# policy also refuses `self`/`static`/`parent`, primitives and
# `mixed`/`object`/`iterable`/`callable`, but none of those declares MULTIPLE
# candidate classes — `self` in particular makes the in-file match likely
# correct — so they keep today's edge, exactly like a genuinely untyped receiver.

def _same_file(receiver_decl: str, *, second_class: str = "", call: str = "$this->svc") -> str:
    """One PHP file: candidate class(es) plus a Ctrl whose property is `$svc`."""
    return (
        "<?php\n"
        "namespace App;\n"
        "class Alpha { public function run(): int { return 1; } }\n"
        f"{second_class}"
        "class Ctrl {\n"
        f"    {receiver_decl}\n"
        "    public function go(): int {\n"
        f"        return {call}->run();\n"
        "    }\n"
        "}\n"
    )


_BETA = "class Beta { public function run(): int { return 2; } }\n"


def _ran(calls, go: str) -> list[str]:
    """Every ``calls`` target of ``go``. Each fixture below makes exactly one call
    (``->run()``), so the whole target list doubles as the assertion."""
    return sorted(tgt for src, tgt in calls if src == go)


def test_same_file_union_typed_property_emits_no_edge(tmp_path: Path):
    """`Alpha|Beta $svc` with BOTH candidates in the call's own file."""
    calls, r = _calls(tmp_path, {
        "app/U.php": _same_file("private Alpha|Beta $svc;", second_class=_BETA),
    })

    go = _find(r, ".go()", "ctrl")
    assert _ran(calls, go) == [], \
        "a union-typed receiver has no single class — the in-file bare-name " \
        "match would bind it to one of them by file order"


def test_same_file_intersection_typed_property_emits_no_edge(tmp_path: Path):
    """`Alpha&Beta $svc`: an intersection is named by user story 11 too, and had
    no test at all before this ticket."""
    calls, r = _calls(tmp_path, {
        "app/I.php": _same_file("private Alpha&Beta $svc;", second_class=_BETA),
    })

    go = _find(r, ".go()", "ctrl")
    assert _ran(calls, go) == []


def test_same_file_union_typed_param_emits_no_edge(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        "app/UP.php": (
            "<?php\n"
            "namespace App;\n"
            "class Alpha { public function run(): int { return 1; } }\n"
            + _BETA +
            "class Ctrl {\n"
            "    public function go(Alpha|Beta $svc): int {\n"
            "        return $svc->run();\n"
            "    }\n"
            "}\n"
        ),
    })

    go = _find(r, ".go()", "ctrl")
    assert _ran(calls, go) == []


def test_same_file_intersection_typed_param_emits_no_edge(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        "app/IP.php": (
            "<?php\n"
            "namespace App;\n"
            "class Alpha { public function run(): int { return 1; } }\n"
            + _BETA +
            "class Ctrl {\n"
            "    public function go(Alpha&Beta $svc): int {\n"
            "        return $svc->run();\n"
            "    }\n"
            "}\n"
        ),
    })

    go = _find(r, ".go()", "ctrl")
    assert _ran(calls, go) == []


def test_same_file_union_typed_promoted_param_emits_no_edge(tmp_path: Path):
    """A promoted constructor param is a typed property, reached by the same
    `this.<prop>` key — the refusal must travel that channel too."""
    calls, r = _calls(tmp_path, {
        "app/UPP.php": (
            "<?php\n"
            "namespace App;\n"
            "class Alpha { public function run(): int { return 1; } }\n"
            + _BETA +
            "class Ctrl {\n"
            "    public function __construct(private Alpha|Beta $svc) {}\n"
            "    public function go(): int {\n"
            "        return $this->svc->run();\n"
            "    }\n"
            "}\n"
        ),
    })

    go = _find(r, ".go()", "ctrl")
    assert _ran(calls, go) == []


def test_same_file_untyped_property_keeps_its_edge(tmp_path: Path):
    """Regression guard for #2's accepted deviation (user story 9): a receiver
    with NO annotation keeps today's same-file bare-name edge. Only an
    annotation that was PRESENT and refused as multi-typed defers."""
    calls, r = _calls(tmp_path, {
        "app/N.php": _same_file("protected $svc;"),
    })

    go = _find(r, ".go()", "ctrl")
    assert _ran(calls, go) == [_find(r, ".run()", "alpha")]


def test_same_file_untyped_param_keeps_its_edge(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        "app/NP.php": (
            "<?php\n"
            "namespace App;\n"
            "class Alpha { public function run(): int { return 1; } }\n"
            "class Ctrl {\n"
            "    public function go($svc): int {\n"
            "        return $svc->run();\n"
            "    }\n"
            "}\n"
        ),
    })

    go = _find(r, ".go()", "ctrl")
    assert _ran(calls, go) == [_find(r, ".run()", "alpha")]


def test_same_file_this_call_keeps_its_edge(tmp_path: Path):
    """Regression guard (user story 9): `$this->method()` never carries a
    receiver type and must stay on the in-file arm."""
    calls, r = _calls(tmp_path, {
        "app/T.php": (
            "<?php\n"
            "namespace App;\n"
            "class Ctrl {\n"
            "    public function run(): int { return 1; }\n"
            "    public function go(): int { return $this->run(); }\n"
            "}\n"
        ),
    })

    go = _find(r, ".go()", "ctrl")
    assert _ran(calls, go) == [_find(r, ".run()", "ctrl")]


def test_same_file_self_typed_property_keeps_its_edge(tmp_path: Path):
    """Deletion-scope boundary: `self` is refused by the concrete-type policy but
    declares no multiplicity, so it is NOT deferred and keeps today's edge."""
    calls, r = _calls(tmp_path, {
        "app/S.php": _same_file("protected self $svc;"),
    })

    go = _find(r, ".go()", "ctrl")
    assert _ran(calls, go) == [_find(r, ".run()", "alpha")]


def test_same_file_dnf_typed_property_emits_no_edge_and_references_its_types(tmp_path: Path):
    """PHP 8.2 disjunctive normal form (`(A&B)|C`) parses as its own node type,
    which the property scanner's type-node list did not name — so a DNF property
    reached neither the receiver table (it kept minting the bare-name edge this
    ticket removes) nor the type-reference walk (its classes went unreferenced).
    It is a union at top level, so it refuses like one, and references like one."""
    calls, r = _calls(tmp_path, {
        "app/D.php": _same_file("private (Alpha&Beta)|Beta $svc;", second_class=_BETA),
    })

    go = _find(r, ".go()", "ctrl")
    assert _ran(calls, go) == []

    refs = {
        (edge["source"], edge["target"])
        for edge in r["edges"] if edge.get("relation") == "references"
    }
    ctrl = _find(r, "Ctrl", "d_ctrl")
    assert (ctrl, _find(r, "Alpha", "d_alpha")) in refs
    assert (ctrl, _find(r, "Beta", "d_beta")) in refs
