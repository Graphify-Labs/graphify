"""Regression tests for type-reference primitive filtering (PR #1332 review).

Behaviour contract:
  * Python primitive / library type names that appear only in annotations
    (return_type / parameter_type / field / generic_arg / base) are NOT
    materialized as graph nodes — they are noise hubs, not domain concepts.
  * A real, user-defined type whose NAME collides with a primitive/library type
    in some *other* language must still be materialized, and its edges resolve.
  * The filter is scoped per language: a name that is a primitive in Python
    (`Tensor`, `Module`) is a legitimate user-defined type name in Rust/Julia/Go,
    so a single flat global list applied to every extractor mis-drops real types
    (the over-filtering #1332 review flagged). Languages that already filter
    their own predeclared types at the collector (Go `_GO_PREDECLARED_TYPES`,
    Rust `primitive_type`, Python `_PYTHON_ANNOTATION_NOISE`) keep doing so.
"""
from __future__ import annotations

from graphify.extract import extract_python, extract_go, extract_rust, extract_julia


def _labels(r) -> list[str]:
    return [n["label"] for n in r["nodes"]]


def _norm(label: str) -> str:
    return label.strip("()").lstrip(".")


def _edge_pairs(r, relation, context=None) -> set[tuple[str, str]]:
    """(normalized source label, normalized target label) for matching edges.

    The target label resolves from the node list, so a *suppressed* target
    degrades to its raw id — an assertion of ``(src, "Type")`` therefore only
    holds when the target node was actually materialized.
    """
    id_to_label = {n["id"]: _norm(n["label"]) for n in r["nodes"]}
    pairs = set()
    for e in r["edges"]:
        if e.get("relation") != relation:
            continue
        if context is not None and e.get("context") != context:
            continue
        pairs.add((id_to_label.get(e["source"], e["source"]),
                   id_to_label.get(e["target"], e["target"])))
    return pairs


# ── Python: primitives dropped, real same-named user types kept ───────────────

def test_python_primitive_type_refs_not_materialized(tmp_path):
    p = tmp_path / "net.py"
    p.write_text(
        "from torch import Tensor, nn\n"
        "from numpy import ndarray\n"
        "class Net(nn.Module):\n"
        "    def forward(self, x: Tensor) -> Tensor:\n"
        "        return x\n"
        "    def to_np(self) -> ndarray:\n"
        "        return x\n"
        "def count() -> int:\n"
        "    return 0\n",
        encoding="utf-8",
    )
    labels = _labels(extract_python(p))
    assert "Net" in labels
    assert any("forward" in l for l in labels)
    assert any("count" in l for l in labels)
    for noise in ("Tensor", "ndarray", "int", "Module", "nn"):
        assert noise not in labels, f"{noise!r} leaked as a node"


def test_python_user_type_named_like_primitive_is_kept(tmp_path):
    """A user class literally named like a Python/PyTorch type (`Dataset`) must
    stay a node and keep its inheritance edge."""
    p = tmp_path / "model.py"
    p.write_text(
        "class Dataset:\n"
        "    pass\n"
        "class ImageData(Dataset):\n"
        "    pass\n"
        "def make() -> Dataset:\n"
        "    return Dataset()\n",
        encoding="utf-8",
    )
    r = extract_python(p)
    assert "Dataset" in _labels(r), "real user type Dataset was dropped"
    assert ("ImageData", "Dataset") in _edge_pairs(r, "inherits")


# ── Cross-language over-filtering: foreign primitive names must NOT filter ─────

def test_rust_type_named_like_js_global_not_overfiltered(tmp_path):
    """`Response` is a JS built-in but an ordinary Rust type. A flat global
    primitive list mis-dropped it from Rust type references (#1332)."""
    p = tmp_path / "handler.rs"
    p.write_text("fn handle() -> Response {\n    todo!()\n}\n", encoding="utf-8")
    r = extract_rust(p)
    assert "Response" in _labels(r), "Rust `Response` over-filtered as a node"
    assert ("handle", "Response") in _edge_pairs(r, "references", "return_type")


def test_rust_keeps_user_type_and_still_filters_native_primitive(tmp_path):
    p = tmp_path / "lib.rs"
    p.write_text(
        "struct Module {\n    id: u32,\n}\nfn build() -> Module {\n    todo!()\n}\n",
        encoding="utf-8",
    )
    r = extract_rust(p)
    labels = _labels(r)
    assert "Module" in labels
    assert ("build", "Module") in _edge_pairs(r, "references", "return_type")
    # u32 is a genuine Rust primitive, filtered by the Rust collector, not a node.
    assert "u32" not in labels


def test_julia_struct_named_like_foreign_primitive_is_kept(tmp_path):
    """A Julia struct named `Dataset`/`Module` must not be dropped by a
    Python/PyTorch-flavoured primitive list."""
    p = tmp_path / "types.jl"
    p.write_text(
        "struct Dataset\n    n::Int\nend\n\nstruct Wrapper\n    d::Dataset\nend\n",
        encoding="utf-8",
    )
    labels = _labels(extract_julia(p))
    assert "Dataset" in labels, "Julia user struct Dataset was over-filtered"
    assert "Wrapper" in labels


# ── Go: already correct via _GO_PREDECLARED_TYPES (comment #1) ─────────────────

def test_go_primitive_type_refs_not_materialized(tmp_path):
    p = tmp_path / "svc.go"
    p.write_text(
        "package svc\n"
        "type Service struct{}\n"
        "func (s *Service) Save() error { return nil }\n"
        "func (s *Service) Count() int { return 0 }\n"
        "func (s *Service) Name() string { return \"\" }\n",
        encoding="utf-8",
    )
    labels = _labels(extract_go(p))
    assert "Service" in labels
    for noise in ("error", "int", "string"):
        assert noise not in labels, f"Go primitive {noise!r} leaked as a node"


def test_go_user_type_named_like_primitive_is_kept(tmp_path):
    """`Set` collides with Python's typing.Set, but is an ordinary Go type."""
    p = tmp_path / "container.go"
    p.write_text(
        "package container\ntype Set struct{}\nfunc New() Set { return Set{} }\n",
        encoding="utf-8",
    )
    r = extract_go(p)
    assert "Set" in _labels(r), "Go user type Set was dropped"
    assert ("New", "Set") in _edge_pairs(r, "references", "return_type")
