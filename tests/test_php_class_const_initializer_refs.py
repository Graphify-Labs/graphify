"""#4648 — PHP `Scope::MEMBER` accesses in class-level initializers (const
values, property defaults, parameter defaults incl. promoted constructor
properties) must emit a `references_constant` edge, not be dropped because the
call-graph pass only walks function bodies."""
from __future__ import annotations

import tempfile
from pathlib import Path

from graphify.extract import extract


def _const_refs(tmp_path, php: str) -> set[tuple[str, str]]:
    p = tmp_path / "Perms.php"
    p.write_text(php, encoding="utf-8")
    r = extract([p], cache_root=Path(tempfile.mkdtemp()), root=tmp_path, parallel=False)
    labels = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (labels[e["source"]], labels[e["target"]])
        for e in r["edges"]
        if e["relation"] == "references_constant"
    }


_ENUM = "enum Role {\n    case Viewer;\n    case Admin;\n}\n"


def test_const_value_scope_member_is_referenced(tmp_path):
    """A class constant whose value reads an enum case."""
    refs = _const_refs(
        tmp_path,
        "<?php\nnamespace App;\n" + _ENUM +
        "class Catalog {\n    private const array MAP = ['posts.read' => Role::Viewer];\n}\n",
    )
    assert ("Catalog", "Role") in refs, refs


def test_property_default_scope_member_is_referenced(tmp_path):
    """A property default reading an enum case."""
    refs = _const_refs(
        tmp_path,
        "<?php\nnamespace App;\n" + _ENUM +
        "class Settings {\n    private Role $fallback = Role::Viewer;\n}\n",
    )
    assert ("Settings", "Role") in refs, refs


def test_parameter_default_scope_member_is_referenced(tmp_path):
    """A plain parameter default reading an enum case."""
    refs = _const_refs(
        tmp_path,
        "<?php\nnamespace App;\n" + _ENUM +
        "class Service {\n    public function run(Role $r = Role::Viewer) {}\n}\n",
    )
    assert ("Service", "Role") in refs, refs


def test_promoted_constructor_parameter_default_is_referenced(tmp_path):
    """A promoted constructor property default reading an enum case."""
    refs = _const_refs(
        tmp_path,
        "<?php\nnamespace App;\n" + _ENUM +
        "class Guard {\n    public function __construct(private Role $default = Role::Viewer) {}\n}\n",
    )
    assert ("Guard", "Role") in refs, refs


def test_method_body_reference_still_works(tmp_path):
    """Regression guard: the method-body access keeps its existing edge."""
    refs = _const_refs(
        tmp_path,
        "<?php\nnamespace App;\n" + _ENUM +
        "class Check {\n    public function pick(): Role { return Role::Viewer; }\n}\n",
    )
    assert any(src == ".pick()" and tgt == "Role" for src, tgt in refs), refs
