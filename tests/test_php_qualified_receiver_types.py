"""PHP qualified receiver types (#20).

The extractor used to flatten every written PHP type annotation to its short
name, so `private \\Vendor\\Sdk\\Client $c;` was indistinguishable from
`private Client $c;` — the compounding half of the #16 false-edge bug. This
ticket threads the WRITTEN qualified form alongside the short name for the four
annotation positions that type a receiver (properties, constructor-promoted
params, ordinary params and `new`-bound locals) and stamps it on the raw-call
fact as `receiver_type_qualified`.

Nothing consults the new field yet — the decisive refusal is #21 — so the
resolution tests here are PARITY tests: the short name still drives every edge,
bit for bit. The fact-shape tests use the per-file `extract_php` seam (the same
one `tests/test_ruby_resolution.py` uses for receiver-type facts), because the
raw-call facts are the extractor's output and never reach `{nodes, edges}`.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract, extract_php


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _facts(tmp_path: Path, body: str) -> list[dict]:
    """Raw-call facts of one PHP file (the callee is never defined in it, so
    every member call stays unresolved and reaches `raw_calls`)."""
    path = _write(tmp_path / "app/Http/Controllers/LeadController.php", body)
    return extract_php(path).get("raw_calls", [])


def _fact(facts: list[dict], receiver: str) -> dict:
    matches = [f for f in facts if f.get("receiver") == receiver]
    assert len(matches) == 1, facts
    return matches[0]


def _class(members: str) -> str:
    return (
        "<?php\n"
        "namespace App\\Http\\Controllers;\n"
        "class LeadController {\n"
        f"{members}"
        "}\n"
    )


# ── fact shape: the written qualified name survives ───────────────────────────


def test_qualified_property_stamps_short_and_qualified(tmp_path: Path):
    """The #16 repro shape: an out-of-corpus FQN annotation. The short name is
    what it always was; the written name is now evidence #21 can refuse on."""
    facts = _facts(tmp_path, _class(
        "    private \\Vendor\\Sdk\\Client $c;\n"
        "    public function go(): int { return $this->c->send(); }\n"
    ))

    fact = _fact(facts, "this.c")
    assert fact["callee"] == "send"
    assert fact["receiver_type"] == "Client"
    assert fact["receiver_type_qualified"] == "\\Vendor\\Sdk\\Client"


def test_qualified_promoted_param_stamps_short_and_qualified(tmp_path: Path):
    facts = _facts(tmp_path, _class(
        "    public function __construct(private \\App\\Services\\LeadHunterService $svc) {}\n"
        "    public function index(): array { return $this->svc->search([]); }\n"
    ))

    fact = _fact(facts, "this.svc")
    assert fact["receiver_type"] == "LeadHunterService"
    assert fact["receiver_type_qualified"] == "\\App\\Services\\LeadHunterService"


def test_qualified_param_stamps_short_and_qualified(tmp_path: Path):
    facts = _facts(tmp_path, _class(
        "    public function handle(\\App\\Services\\LeadHunterService $svc): array {\n"
        "        return $svc->search([]);\n"
        "    }\n"
    ))

    fact = _fact(facts, "svc")
    assert fact["receiver_type"] == "LeadHunterService"
    assert fact["receiver_type_qualified"] == "\\App\\Services\\LeadHunterService"


def test_qualified_local_new_stamps_short_and_qualified(tmp_path: Path):
    facts = _facts(tmp_path, _class(
        "    public function index(): array {\n"
        "        $svc = new \\App\\Services\\LeadHunterService();\n"
        "        return $svc->search([]);\n"
        "    }\n"
    ))

    fact = _fact(facts, "svc")
    assert fact["receiver_type"] == "LeadHunterService"
    assert fact["receiver_type_qualified"] == "\\App\\Services\\LeadHunterService"


def test_nullable_qualified_property_stamps_qualified(tmp_path: Path):
    """`?\\A\\B` unwraps to one concrete type — the qualified form must survive
    the unwrap, not just the short name."""
    facts = _facts(tmp_path, _class(
        "    private ?\\App\\Services\\LeadHunterService $svc;\n"
        "    public function index(): array { return $this->svc->search([]); }\n"
    ))

    fact = _fact(facts, "this.svc")
    assert fact["receiver_type"] == "LeadHunterService"
    assert fact["receiver_type_qualified"] == "\\App\\Services\\LeadHunterService"


def test_namespace_relative_annotation_stamps_written_form(tmp_path: Path):
    """`Services\\X` is qualified but RELATIVE to the current namespace. The
    extractor stamps what was written; resolving it is the resolver's job."""
    facts = _facts(tmp_path, _class(
        "    public function handle(Services\\LeadHunterService $svc): array {\n"
        "        return $svc->search([]);\n"
        "    }\n"
    ))

    fact = _fact(facts, "svc")
    assert fact["receiver_type"] == "LeadHunterService"
    assert fact["receiver_type_qualified"] == "Services\\LeadHunterService"


# ── fact shape: unqualified annotations are unchanged ─────────────────────────


def test_unqualified_property_stamps_no_qualified_field(tmp_path: Path):
    facts = _facts(tmp_path, _class(
        "    private LeadHunterService $svc;\n"
        "    public function index(): array { return $this->svc->search([]); }\n"
    ))

    fact = _fact(facts, "this.svc")
    assert fact["receiver_type"] == "LeadHunterService"
    assert fact.get("receiver_type_qualified") is None


def test_unqualified_param_and_local_stamp_no_qualified_field(tmp_path: Path):
    facts = _facts(tmp_path, _class(
        "    public function handle(LeadHunterService $svc): array {\n"
        "        $other = new AuditLog();\n"
        "        return $svc->search([]) + $other->search([]);\n"
        "    }\n"
    ))

    param = _fact(facts, "svc")
    assert param["receiver_type"] == "LeadHunterService"
    assert param.get("receiver_type_qualified") is None
    local = _fact(facts, "other")
    assert local["receiver_type"] == "AuditLog"
    assert local.get("receiver_type_qualified") is None


def test_union_typed_receiver_stamps_neither_field(tmp_path: Path):
    """A multi-class annotation is a refusal (#9): it stamps no type, and the
    qualified field must not resurrect one."""
    facts = _facts(tmp_path, _class(
        "    public function handle(\\App\\A|\\App\\B $svc): array {\n"
        "        return $svc->search([]);\n"
        "    }\n"
    ))

    fact = _fact(facts, "svc")
    assert "receiver_type" not in fact
    assert "receiver_type_qualified" not in fact


def test_same_class_written_two_ways_keeps_short_name(tmp_path: Path):
    """Two `new`s naming the same SHORT name through different written forms
    used to bind that short name, and still do — the qualified evidence is
    contradictory, so it is dropped rather than poisoning the binding."""
    facts = _facts(tmp_path, _class(
        "    public function index(): array {\n"
        "        $svc = new LeadHunterService();\n"
        "        $svc = new \\App\\Services\\LeadHunterService();\n"
        "        return $svc->search([]);\n"
        "    }\n"
    ))

    fact = _fact(facts, "svc")
    assert fact["receiver_type"] == "LeadHunterService"
    assert fact.get("receiver_type_qualified") is None


# ── resolution parity through the public extract() seam ───────────────────────

_SERVICE = (
    "<?php\nnamespace App\\Services;\n"
    "class LeadHunterService {\n"
    "    public function search(array $filters): array { return []; }\n"
    "}\n"
)
# Decoy: same method name, different class — only the receiver's type tells
# them apart, so a bare-name match would light it up.
_DECOY = (
    "<?php\nnamespace App\\Audit;\n"
    "class AuditLog {\n"
    "    public function search(array $filters): array { return []; }\n"
    "}\n"
)


def _extract(tmp_path: Path, files: dict[str, str]):
    paths = [_write(tmp_path / name, body) for name, body in files.items()]
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


def test_qualified_annotation_still_resolves_by_short_name(tmp_path: Path):
    """Parity: threading the qualified form changes no edge. The written FQN
    names the in-corpus class here, and the resolution is exactly today's —
    INFERRED 0.8 off the short name, decoy untouched."""
    calls, r = _extract(tmp_path, {
        "app/Services/LeadHunterService.php": _SERVICE,
        "app/Audit/AuditLog.php": _DECOY,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "class LeadController {\n"
            "    private \\App\\Services\\LeadHunterService $svc;\n"
            "    public function index(): array { return $this->svc->search([]); }\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    assert (index, service_search) in calls
    assert (index, _find(r, ".search()", "auditlog")) not in calls
    edge = calls[(index, service_search)]
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.8
