"""Go receiver-typed member-call resolution (#3368).

`p.cfg.Format()` and `fmt.Println()` are the same AST shape in Go — a
selector-expression call — so a member call through a typed parameter,
receiver, or struct field reached `raw_calls` with nothing to resolve it: the
shared cross-file pass drops every member call unconditionally, and Go had no
language-specific resolver to answer it instead.

`resolve_go_member_calls` walks the receiver's dotted chain through two
tables the extractor builds (`go_local_types`, `go_struct_fields`), each
holding only a bare, same-package declared type. A package-qualified type, an
inferred local-variable type, and interface dispatch (Go has no `implements`
keyword) are explicitly out of scope — see `graphify/go_resolution.py`.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=Path(tempfile.mkdtemp()))
    finally:
        os.chdir(old)
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    return calls, r


def _find(r, label, id_contains):
    return next(n["id"] for n in r["nodes"] if n["label"] == label and id_contains in n["id"])


def test_typed_parameter_receiver_gets_a_calls_edge(tmp_path):
    calls, r = _extract(tmp_path, {
        "pkg/eval.go": (
            "package pkg\n"
            "func Eval(limiter *Limiter) bool {\n"
            "\tlimiter.Allow()\n"
            "\treturn true\n"
            "}\n"
        ),
        "pkg/limiter.go": (
            "package pkg\n"
            "type Limiter struct{}\n"
            "func (l *Limiter) Allow() bool { return true }\n"
        ),
    })
    assert (_find(r, "Eval()", "pkg"), _find(r, ".Allow()", "pkg")) in calls


def test_struct_field_receiver_resolves_across_files_over_an_ambiguous_name(tmp_path):
    # "Format" is declared on two different types in the corpus, so the naive
    # same-file bare-name fallback the engine already has cannot (and must
    # not) answer this: only the field's declared type picks the right one.
    calls, r = _extract(tmp_path, {
        "pkg/profiler.go": (
            "package pkg\n"
            "type profiler struct { cfg *Config }\n"
            "func (p *profiler) Run() { p.cfg.Format() }\n"
        ),
        "pkg/config.go": (
            "package pkg\n"
            "type Config struct { Dir string }\n"
            "func (c *Config) Format() string { return c.Dir }\n"
        ),
        "pkg/other.go": (
            "package pkg\n"
            "type Report struct{}\n"
            "func (r *Report) Format() string { return \"report\" }\n"
        ),
    })
    assert calls == {(_find(r, ".Run()", "pkg_profiler"), _find(r, ".Format()", "pkg_config"))}


def test_edge_is_inferred_at_the_strong_inference_tier(tmp_path):
    _, r = _extract(tmp_path, {
        "pkg/a.go": (
            "package pkg\n"
            "type A struct { b *B }\n"
            "func (a *A) Run() { a.b.Leaf() }\n"
        ),
        "pkg/b.go": "package pkg\ntype B struct{}\nfunc (b *B) Leaf() {}\n",
    })
    edge = next(e for e in r["edges"] if e["relation"] == "calls" and e["context"] == "call"
                and e["confidence"] == "INFERRED")
    assert edge["confidence_score"] == 0.85


def test_three_segment_chain_resolves(tmp_path):
    calls, r = _extract(tmp_path, {
        "pkg/a.go": (
            "package pkg\n"
            "type A struct { b *B }\n"
            "func (a *A) Run() { a.b.inner.Leaf() }\n"
        ),
        "pkg/b.go": "package pkg\ntype B struct { inner *Inner }\n",
        "pkg/inner.go": "package pkg\ntype Inner struct{}\nfunc (i *Inner) Leaf() {}\n",
    })
    assert (_find(r, ".Run()", "pkg_a"), _find(r, ".Leaf()", "pkg_inner")) in calls


def test_package_qualified_field_type_is_left_unresolved(tmp_path):
    # Out of scope by design: `redis_rate.Limiter` needs the cross-package
    # qualified-type machinery, not this table (see go_resolution.py).
    calls, _ = _extract(tmp_path, {
        "pkg/eval.go": (
            "package pkg\n"
            "import \"redis_rate\"\n"
            "func Eval(limiter *redis_rate.Limiter) bool {\n"
            "\tlimiter.Allow()\n"
            "\treturn true\n"
            "}\n"
        ),
    })
    assert not calls


def test_generic_field_typed_by_its_own_type_parameter_is_not_chased(tmp_path):
    # `Box[T]`'s field `val T` must not be recorded as a struct to walk into;
    # T is a type parameter, not a type with methods.
    calls, _ = _extract(tmp_path, {
        "pkg/box.go": (
            "package pkg\n"
            "type Box[T any] struct { val T }\n"
            "func (b *Box[T]) Get() T { return b.val }\n"
            "func (b *Box[T]) Use() { b.val.Anything() }\n"
        ),
    })
    assert not calls


def test_undeclared_field_on_the_receiver_produces_no_edge(tmp_path):
    calls, _ = _extract(tmp_path, {
        "pkg/a.go": (
            "package pkg\n"
            "type A struct{}\n"
            "func (a *A) Run() { a.missing.Leaf() }\n"
        ),
        "pkg/b.go": "package pkg\ntype B struct{}\nfunc (b *B) Leaf() {}\n",
    })
    assert not calls


def test_an_existing_edge_is_not_duplicated(tmp_path):
    from graphify.go_resolution import resolve_go_member_calls

    nodes = [
        {"id": "a", "label": "A", "source_file": "a.go"},
        {"id": "b", "label": "B", "source_file": "b.go"},
        {"id": "a_run", "label": ".Run()", "source_file": "a.go"},
        {"id": "b_leaf", "label": ".Leaf()", "source_file": "b.go"},
    ]
    edges = [
        {"source": "b", "target": "b_leaf", "relation": "method"},
        {"source": "a_run", "target": "b_leaf", "relation": "calls"},
    ]
    per_file = [{
        "go_local_types": {"a_run": {"a": "a", "b": "b"}},
        "go_struct_fields": {},
        "raw_calls": [{
            "caller_nid": "a_run", "callee": "Leaf", "is_member_call": True,
            "language": "go", "member_receiver": "b",
            "source_file": "a.go", "source_location": "L1",
        }],
    }]
    resolve_go_member_calls(per_file, nodes, edges)
    assert sum(1 for e in edges if e["relation"] == "calls") == 1


def test_a_non_go_corpus_is_untouched(tmp_path):
    calls, _ = _extract(tmp_path, {
        "pkg/a.py": "class A:\n    def run(self):\n        pass\n",
    })
    assert not calls
