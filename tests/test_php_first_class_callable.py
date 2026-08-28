"""PHP 8.1 first-class callables emit ``indirect_call``, not ``calls`` (#15).

``$obj->method(...)`` creates a ``Closure`` — the method is *named*, not invoked,
so control flow does not transfer at that line.  The repo already models
"named but not invoked" as the distinct ``indirect_call`` relation, and PHP only
leaked into ``calls`` because the 8.1 grammar reuses ``member_call_expression``
for first-class-callable syntax.

Discriminator (probe-verified on the pinned tree-sitter-php 0.24.1): the
``arguments`` node of ``m(...)`` has exactly one named child, of type
``variadic_placeholder``.  ``m()``, ``m(1)`` and ``m(...$args)`` do not.

Target resolution and the refuse-don't-guess rules are UNCHANGED — only the
relation moves.  Every positive test carries a decoy class with an identically
named method that must get no edge.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _edges(tmp_path: Path, files: dict[str, str]):
    """Extract ``files`` (name -> source) and return ({(src, tgt, rel): edge}, result)."""
    paths = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    result = extract(paths, cache_root=tmp_path / "graphify-out")
    edges = {
        (edge["source"], edge["target"], edge.get("relation")): edge
        for edge in result["edges"]
        if edge.get("relation") in ("calls", "indirect_call")
    }
    return edges, result


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


def _controller(body: str) -> str:
    return (
        "<?php\n"
        "namespace App\\Http\\Controllers;\n"
        "use App\\Services\\LeadHunterService;\n"
        "class LeadController {\n"
        "    public function __construct(protected LeadHunterService $leadHunter) {}\n"
        "    public function index(): mixed {\n"
        f"        {body}\n"
        "    }\n"
        "}\n"
    )


def test_first_class_callable_on_typed_property_emits_indirect_call(tmp_path: Path):
    edges, r = _edges(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "return $this->leadHunter->search(...);"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    decoy_search = _find(r, ".search()", "auditlog")

    assert (index, service_search, "indirect_call") in edges
    assert (index, service_search, "calls") not in edges
    assert (index, decoy_search, "indirect_call") not in edges
    assert (index, decoy_search, "calls") not in edges
    # Target resolution is unchanged: same receiver typing, same confidence as
    # the ordinary `$this->leadHunter->search([])` call would get.
    edge = edges[(index, service_search, "indirect_call")]
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.8


def test_nullsafe_first_class_callable_emits_indirect_call(tmp_path: Path):
    edges, r = _edges(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "return $this->leadHunter?->search(...);"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    decoy_search = _find(r, ".search()", "auditlog")

    assert (index, service_search, "indirect_call") in edges
    assert (index, service_search, "calls") not in edges
    assert (index, decoy_search, "indirect_call") not in edges
    assert (index, decoy_search, "calls") not in edges


def test_first_class_callable_on_this_emits_indirect_call(tmp_path: Path):
    """`$this->helper(...)` resolves in-file, so it must re-tag on that path too."""
    edges, r = _edges(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "class LeadController {\n"
            "    public function index(): mixed {\n"
            "        return $this->normalise(...);\n"
            "    }\n"
            "    public function normalise(array $row): array { return $row; }\n"
            "}\n"
        ),
        # Decoy: a same-named method in another class must not pick up the edge.
        "app/Audit/Normaliser.php": (
            "<?php\n"
            "namespace App\\Audit;\n"
            "class Normaliser {\n"
            "    public function normalise(array $row): array { return $row; }\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    own = _find(r, ".normalise()", "leadcontroller")
    decoy = _find(r, ".normalise()", "normaliser")

    assert (index, own, "indirect_call") in edges
    assert (index, own, "calls") not in edges
    assert (index, decoy, "indirect_call") not in edges
    assert (index, decoy, "calls") not in edges


def test_ordinary_member_call_still_emits_calls(tmp_path: Path):
    """Regression guard: an ordinary invocation keeps `calls` at unchanged confidence."""
    edges, r = _edges(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "return $this->leadHunter->search(['status' => 'open']);"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")

    assert (index, service_search, "calls") in edges
    assert (index, service_search, "indirect_call") not in edges
    edge = edges[(index, service_search, "calls")]
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.8
    assert edge["context"] == "call"


def test_ordinary_this_call_still_emits_calls(tmp_path: Path):
    """Regression guard for the in-file path: `$this->normalise()` stays EXTRACTED `calls`."""
    edges, r = _edges(tmp_path, {
        "app/Http/Controllers/LeadController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "class LeadController {\n"
            "    public function index(): mixed {\n"
            "        return $this->normalise([]);\n"
            "    }\n"
            "    public function normalise(array $row): array { return $row; }\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    own = _find(r, ".normalise()", "leadcontroller")

    assert (index, own, "calls") in edges
    assert (index, own, "indirect_call") not in edges
    assert edges[(index, own, "calls")]["confidence"] == "EXTRACTED"


def test_spread_argument_is_not_a_first_class_callable(tmp_path: Path):
    """`search(...$args)` IS an invocation — only a bare `...` placeholder re-tags."""
    edges, r = _edges(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "$args = []; return $this->leadHunter->search(...$args);"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")

    assert (index, service_search, "calls") in edges
    assert (index, service_search, "indirect_call") not in edges


def test_direct_call_wins_over_first_class_callable_to_the_same_method(tmp_path: Path):
    """Both forms in one caller: the real invocation keeps the pair (existing
    indirect-dispatch precedence), regardless of which appears first."""
    edges, r = _edges(tmp_path, {
        **_CORPUS,
        "app/Http/Controllers/LeadController.php": _controller(
            "$f = $this->leadHunter->search(...);\n"
            "        return $this->leadHunter->search([]);"
        ),
        "app/Http/Controllers/TeamController.php": (
            "<?php\n"
            "namespace App\\Http\\Controllers;\n"
            "class TeamController {\n"
            "    public function index(): mixed {\n"
            "        $f = $this->normalise(...);\n"
            "        return $this->normalise([]);\n"
            "    }\n"
            "    public function normalise(array $row): array { return $row; }\n"
            "}\n"
        ),
    })

    index = _find(r, ".index()", "leadcontroller")
    service_search = _find(r, ".search()", "leadhunterservice")
    assert (index, service_search, "calls") in edges
    assert (index, service_search, "indirect_call") not in edges

    team_index = _find(r, ".index()", "teamcontroller")
    own = _find(r, ".normalise()", "teamcontroller")
    assert (team_index, own, "calls") in edges
    assert (team_index, own, "indirect_call") not in edges
