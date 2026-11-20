"""A same-file ``s.helper()`` call must keep its ``calls`` edge when the receiver
type is declared in a sibling file AND another package names that type (#5304).

The other package's ``alpha.Service`` reference mints a sourceless stub whose id
folds onto the declaration's own id. ``_disambiguate_colliding_node_ids`` then
salted the declaration apart from the stub, leaving the sibling file's ``method``
edges on the dead bare id, so ``_resolve_go_member_calls`` found no methods and
dropped the call.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import extract

_TYPES = "package alpha\n\ntype Service struct{}\n"
_IMPL = (
    "package alpha\n\n"
    "func (s *Service) helper() int { return 1 }\n\n"
    "func (s *Service) Run() int { return s.helper() }\n"
)
_MAIN_HEADER = 'package main\n\nimport "example.com/app/alpha"\n\n'
_OUTSIDE_REFERENCES = {
    "field": "type deps struct{ svc *alpha.Service }\n",
    "parameter": "func wire(s *alpha.Service) int { return s.Run() }\n",
    "return": "func wire() *alpha.Service { return &alpha.Service{} }\n",
}


def _build(tmp_path: Path, files: dict[str, str]) -> dict:
    (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.22\n")
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return extract(
        sorted(tmp_path.rglob("*.go")), root=tmp_path, cache_root=tmp_path / "cache", parallel=False,
    )


def _nid(result: dict, *, source_suffix: str, label: str) -> str:
    matches = [
        n["id"] for n in result["nodes"]
        if str(n.get("source_file", "")).endswith(source_suffix)
        and str(n.get("label", "")).strip(".()") == label
    ]
    assert len(matches) == 1, (source_suffix, label, matches)
    return matches[0]


@pytest.mark.parametrize("shape", sorted(_OUTSIDE_REFERENCES))
def test_sibling_file_receiver_keeps_its_call_when_another_package_names_the_type(
    tmp_path: Path, shape: str,
) -> None:
    result = _build(tmp_path, {
        "alpha/types.go": _TYPES,
        "alpha/impl.go": _IMPL,
        "cmd/main.go": _MAIN_HEADER + _OUTSIDE_REFERENCES[shape],
    })
    run = _nid(result, source_suffix="alpha/impl.go", label="Run")
    helper = _nid(result, source_suffix="alpha/impl.go", label="helper")
    calls = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}
    assert (run, helper) in calls, calls


def test_outside_reference_still_lands_on_the_declaration(tmp_path: Path) -> None:
    result = _build(tmp_path, {
        "alpha/types.go": _TYPES,
        "alpha/impl.go": _IMPL,
        "cmd/main.go": _MAIN_HEADER + _OUTSIDE_REFERENCES["field"],
    })
    service = _nid(result, source_suffix="alpha/types.go", label="Service")
    deps = _nid(result, source_suffix="cmd/main.go", label="deps")
    references = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "references"}
    assert (deps, service) in references, references
    # The declaration still owns both methods, so the type stays one node.
    method_sources = {e["source"] for e in result["edges"] if e["relation"] == "method"}
    assert method_sources == {service}, method_sources
