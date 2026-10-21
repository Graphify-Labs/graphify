"""PHP enum-case / class-constant accesses (`Status::Active`) must produce edges.

Enums were extracted (enum node + `case_of` edge per case) but every USE of a
case was invisible: `Status::Active`, `Status::Active->label()` and
`match ($x) { Status::Draft => .. }` parse as `class_constant_access_expression`,
and the only handling resolved the scope against labels of the *same file*.
`Status::from()/tryFrom()/cases()` are implicit enum statics with no method
node, so the static-call resolver found nothing to bind either.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from graphify.extract import extract

ENUM = (
    "<?php\nnamespace App;\nenum Status: string {\n"
    "    case Active = 'a';\n    case Draft = 'd';\n"
    "    public function label(): string { return 'x'; }\n}\n"
)


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    r = extract([tmp_path / n for n in files], cache_root=Path(tempfile.mkdtemp()),
                root=tmp_path, parallel=False)
    labels = {n["id"]: n["label"] for n in r["nodes"]}
    return r, labels


def _edges(r, labels, relation):
    return {
        (labels[e["source"]], labels[e["target"]]): e
        for e in r["edges"] if e["relation"] == relation
    }


def test_cross_file_case_access_links_to_the_case_node(tmp_path):
    r, labels = _extract(tmp_path, {
        "Status.php": ENUM,
        "Gate.php": (
            "<?php\nnamespace App;\nclass Gate {\n"
            "    public function a() { return Status::Active; }\n"
            "    public function b($s) { return $s === Status::Draft; }\n"
            "    public function c() { return Status::Active->label(); }\n"
            "    public function d($s) { return match ($s) { Status::Draft => 1, default => 2 }; }\n}\n"),
    })
    refs = _edges(r, labels, "references_constant")
    assert refs[(".a()", "Active")]["confidence"] == "EXTRACTED"
    assert (".b()", "Draft") in refs
    assert (".c()", "Active") in refs
    assert (".d()", "Draft") in refs
    # exact case node, not the enum
    assert (".a()", "Status") not in refs


def test_case_match_is_case_sensitive_and_never_guessed(tmp_path):
    r, labels = _extract(tmp_path, {
        "Status.php": ENUM,
        "Gate.php": (
            "<?php\nnamespace App;\nclass Gate {\n"
            "    public function a() { return Status::ACTIVE; }\n}\n"),
    })
    refs = _edges(r, labels, "references_constant")
    assert (".a()", "Active") not in refs


def test_self_case_access_inside_the_enum(tmp_path):
    r, labels = _extract(tmp_path, {
        "Status.php": (
            "<?php\nnamespace App;\nenum Status: string {\n"
            "    case Active = 'a';\n"
            "    public function isActive(): bool { return $this === self::Active; }\n}\n"),
    })
    assert (".isActive()", "Active") in _edges(r, labels, "references_constant")


def test_plain_class_constant_links_to_the_class(tmp_path):
    r, labels = _extract(tmp_path, {
        "Consts.php": "<?php\nnamespace App;\nclass Consts { const FOO = 1; }\n",
        "Use.php": (
            "<?php\nnamespace App;\nclass Use1 {\n"
            "    public function a() { return Consts::FOO; }\n}\n"),
    })
    assert (".a()", "Consts") in _edges(r, labels, "references_constant")


def test_unresolved_scope_yields_no_edge(tmp_path):
    r, labels = _extract(tmp_path, {
        "Use.php": (
            "<?php\nnamespace App;\nclass Use1 {\n"
            "    public function a() { return Missing::FOO . Missing::class; }\n}\n"),
    })
    assert not _edges(r, labels, "references_constant")


def test_enum_from_tryfrom_cases_link_to_the_enum(tmp_path):
    r, labels = _extract(tmp_path, {
        "Status.php": ENUM,
        "Gate.php": (
            "<?php\nnamespace App;\nclass Gate {\n"
            "    public function a($v) { return Status::from($v); }\n"
            "    public function b($v) { return Status::tryFrom($v); }\n"
            "    public function c() { return Status::cases(); }\n}\n"),
    })
    calls = _edges(r, labels, "calls")
    for caller in (".a()", ".b()", ".c()"):
        assert calls[(caller, "Status")]["confidence"] == "EXTRACTED"


def test_user_defined_from_method_still_wins(tmp_path):
    r, labels = _extract(tmp_path, {
        "Mode.php": (
            "<?php\nnamespace App;\nenum Mode {\n    case A;\n"
            "    public static function from(string $x): self { return self::A; }\n}\n"),
        "Gate.php": (
            "<?php\nnamespace App;\nclass Gate {\n"
            "    public function a($v) { return Mode::from($v); }\n}\n"),
    })
    calls = _edges(r, labels, "calls")
    assert (".a()", ".from()") in calls
    assert (".a()", "Mode") not in calls


def test_constant_access_on_the_own_class_keeps_the_method_edge_in_the_graph(tmp_path):
    # The built graph keeps ONE edge per undirected node pair. `self::LIMIT` (and
    # `Svc::LIMIT`) inside a method of Svc links the method to its own class, the
    # same pair as the class's `method` edge; the structural edge must survive.
    from graphify.build import build_from_json, edge_data

    r, labels = _extract(tmp_path, {
        "Svc.php": (
            "<?php\nnamespace App;\nclass Svc {\n    const LIMIT = 3;\n"
            "    public function run() { return self::LIMIT + Svc::LIMIT; }\n}\n"),
    })
    ids = {label: nid for nid, label in labels.items()}
    assert (".run()", "Svc") in _edges(r, labels, "references_constant")
    G = build_from_json(r)
    assert edge_data(G, ids["Svc"], ids[".run()"])["relation"] == "method"
