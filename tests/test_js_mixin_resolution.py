"""Tests for Phase 9D: Applying JS/TS mixin factory facts to symbol resolution."""
from __future__ import annotations

from pathlib import Path
import pytest

from graphify.extract import _file_stem, _make_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _nid(rel_path: str, *syms: str) -> str:
    stem = _file_stem(Path(rel_path))
    return _make_id(stem, *syms)


# --- Test 1: Basic factory application ---

def test_basic_factory_application(tmp_path):
    """1. Basic factory application: Applied mixes in returned class, returned class inherits Root."""
    f = _write(
        tmp_path / "src" / "a.js",
        """
class Root {}
function mixin(Base) {
    return class extends Base {};
}
const Applied = mixin(Root);
""",
    )
    result = extract([f], cache_root=tmp_path)

    applied_nid = _nid("src/a.js", "Applied")
    returned_class_nid = _nid("src/a.js", "mixin", "mixin@class")
    root_nid = _nid("src/a.js", "Root")

    assert any(
        e["source"] == applied_nid and e["target"] == returned_class_nid and e["relation"] == "mixes_in"
        for e in result["edges"]
    )
    assert any(
        e["source"] == returned_class_nid and e["target"] == root_nid and e["relation"] == "inherits"
        for e in result["edges"]
    )


# --- Test 2: Dynamic heritage application ---

def test_dynamic_heritage_application(tmp_path):
    """2. Dynamic heritage application: Child mixes in returned class, returned class inherits Root."""
    f = _write(
        tmp_path / "src" / "a.js",
        """
class Root {}
function mixin(Base) {
    return class extends Base {};
}
class Child extends mixin(Root) {}
""",
    )
    result = extract([f], cache_root=tmp_path)

    child_nid = _nid("src/a.js", "Child")
    returned_class_nid = _nid("src/a.js", "mixin", "mixin@class")
    root_nid = _nid("src/a.js", "Root")

    assert any(
        e["source"] == child_nid and e["target"] == returned_class_nid and e["relation"] == "mixes_in"
        for e in result["edges"]
    )
    assert any(
        e["source"] == returned_class_nid and e["target"] == root_nid and e["relation"] == "inherits"
        for e in result["edges"]
    )


# --- Test 3: Non-first base parameter ---

def test_non_first_base_parameter(tmp_path):
    """3. Non-first base parameter: Root at index 1 is selected as the base."""
    f = _write(
        tmp_path / "src" / "a.js",
        """
class ConfigValue {}
class Root {}
function mixin(Config, Base) {
    return class extends Base {};
}
const Applied = mixin(ConfigValue, Root);
""",
    )
    result = extract([f], cache_root=tmp_path)

    applied_nid = _nid("src/a.js", "Applied")
    returned_class_nid = _nid("src/a.js", "mixin", "mixin@class")
    root_nid = _nid("src/a.js", "Root")
    config_nid = _nid("src/a.js", "ConfigValue")

    assert any(
        e["source"] == applied_nid and e["target"] == returned_class_nid and e["relation"] == "mixes_in"
        for e in result["edges"]
    )
    assert any(
        e["source"] == returned_class_nid and e["target"] == root_nid and e["relation"] == "inherits"
        for e in result["edges"]
    )
    # mixin@class should NOT inherit from ConfigValue
    assert not any(
        e["source"] == returned_class_nid and e["target"] == config_nid and e["relation"] == "inherits"
        for e in result["edges"]
    )


# --- Test 4: Multiple applications ---

def test_multiple_applications(tmp_path):
    """4. Multiple applications: A -> mixin@class and B -> mixin@class without cross-wiring."""
    f = _write(
        tmp_path / "src" / "a.js",
        """
class RootA {}
class RootB {}
function mixin(Base) {
    return class extends Base {};
}
const A = mixin(RootA);
const B = mixin(RootB);
""",
    )
    result = extract([f], cache_root=tmp_path)

    a_nid = _nid("src/a.js", "A")
    b_nid = _nid("src/a.js", "B")
    returned_class_nid = _nid("src/a.js", "mixin", "mixin@class")
    root_a_nid = _nid("src/a.js", "RootA")
    root_b_nid = _nid("src/a.js", "RootB")

    # Both mix in the factory class
    assert any(e["source"] == a_nid and e["target"] == returned_class_nid and e["relation"] == "mixes_in" for e in result["edges"])
    assert any(e["source"] == b_nid and e["target"] == returned_class_nid and e["relation"] == "mixes_in" for e in result["edges"])

    # Factory class inherits both bases
    assert any(e["source"] == returned_class_nid and e["target"] == root_a_nid and e["relation"] == "inherits" for e in result["edges"])
    assert any(e["source"] == returned_class_nid and e["target"] == root_b_nid and e["relation"] == "inherits" for e in result["edges"])


# --- Test 5: Multiple factories ---

def test_multiple_factories(tmp_path):
    """5. Multiple factories: each application resolves to its own returned class."""
    f = _write(
        tmp_path / "src" / "a.js",
        """
class Root {}
function mixinA(Base) {
    return class extends Base {};
}
function mixinB(Base) {
    return class extends Base {};
}
const A = mixinA(Root);
const B = mixinB(Root);
""",
    )
    result = extract([f], cache_root=tmp_path)

    a_nid = _nid("src/a.js", "A")
    b_nid = _nid("src/a.js", "B")
    ret_a_nid = _nid("src/a.js", "mixinA", "mixinA@class")
    ret_b_nid = _nid("src/a.js", "mixinB", "mixinB@class")

    assert any(e["source"] == a_nid and e["target"] == ret_a_nid and e["relation"] == "mixes_in" for e in result["edges"])
    assert not any(e["source"] == a_nid and e["target"] == ret_b_nid for e in result["edges"])

    assert any(e["source"] == b_nid and e["target"] == ret_b_nid and e["relation"] == "mixes_in" for e in result["edges"])
    assert not any(e["source"] == b_nid and e["target"] == ret_a_nid for e in result["edges"])


# --- Test 6: TypeScript generic factory ---

def test_typescript_generic_factory(tmp_path):
    """6. TypeScript generic factory: correctly resolves mixes_in and inherits in TS."""
    f = _write(
        tmp_path / "src" / "a.ts",
        """
class Root {}
function mixin<T extends Ctor>(Base: T) {
    return class extends Base {};
}
class Child extends mixin(Root) {}
const Applied = mixin<any>(Root);
""",
    )
    result = extract([f], cache_root=tmp_path)

    child_nid = _nid("src/a.ts", "Child")
    applied_nid = _nid("src/a.ts", "Applied")
    returned_class_nid = _nid("src/a.ts", "mixin", "mixin@class")
    root_nid = _nid("src/a.ts", "Root")

    assert any(e["source"] == child_nid and e["target"] == returned_class_nid and e["relation"] == "mixes_in" for e in result["edges"])
    assert any(e["source"] == applied_nid and e["target"] == returned_class_nid and e["relation"] == "mixes_in" for e in result["edges"])
    assert any(e["source"] == returned_class_nid and e["target"] == root_nid and e["relation"] == "inherits" for e in result["edges"])


# --- Test 7: Dynamic factory argument ---

def test_dynamic_factory_argument(tmp_path):
    """7. Dynamic factory argument: mixin(getBase()) produces no fabricated semantic edge."""
    f = _write(
        tmp_path / "src" / "a.js",
        """
function getBase() { return class {}; }
function mixin(Base) {
    return class extends Base {};
}
const Applied = mixin(getBase());
""",
    )
    result = extract([f], cache_root=tmp_path)
    applied_nid = _nid("src/a.js", "Applied")

    assert not any(e["source"] == applied_nid and e["relation"] == "mixes_in" for e in result["edges"])


# --- Test 8: Dynamic factory heritage ---

def test_dynamic_factory_heritage(tmp_path):
    """8. Dynamic factory heritage: class Child extends getMixin()(Root) produces no fabricated edge."""
    f = _write(
        tmp_path / "src" / "a.js",
        """
class Root {}
function getMixin() {
    return function(Base) { return class extends Base {}; };
}
class Child extends getMixin()(Root) {}
""",
    )
    result = extract([f], cache_root=tmp_path)
    child_nid = _nid("src/a.js", "Child")

    assert not any(e["source"] == child_nid and e["relation"] in ("mixes_in", "inherits") for e in result["edges"])


# --- Test 9: Existing regression ---

def test_dynamic_base_regression(tmp_path):
    """9. Existing regression: class Child extends getBase() still does not fabricate an inherits target."""
    f = _write(
        tmp_path / "src" / "a.js",
        """
function getBase() { return class {}; }
class Child extends getBase() {}
""",
    )
    result = extract([f], cache_root=tmp_path)
    child_nid = _nid("src/a.js", "Child")

    assert not any(e["source"] == child_nid and e["relation"] in ("mixes_in", "inherits") for e in result["edges"])


# --- Test 10: Cross-file mixin factory application ---

def test_cross_file_mixin_application(tmp_path):
    """Cross-file mixin factory: factory in one file, imported and applied in another."""
    fac_file = _write(
        tmp_path / "src" / "factory.js",
        """
export function mixin(Base) {
    return class extends Base {};
}
""",
    )
    app_file = _write(
        tmp_path / "src" / "app.js",
        """
import { mixin } from './factory.js';
export class Root {}
export class Child extends mixin(Root) {}
""",
    )
    result = extract([app_file, fac_file], cache_root=tmp_path)

    child_nid = _nid("src/app.js", "Child")
    root_nid = _nid("src/app.js", "Root")
    returned_class_nid = _nid("src/factory.js", "mixin", "mixin@class")

    assert any(
        e["source"] == child_nid and e["target"] == returned_class_nid and e["relation"] == "mixes_in"
        for e in result["edges"]
    )
    assert any(
        e["source"] == returned_class_nid and e["target"] == root_nid and e["relation"] == "inherits"
        for e in result["edges"]
    )
