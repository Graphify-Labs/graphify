from __future__ import annotations

import pytest

from graphify.extract import extract_js


@pytest.mark.parametrize("suffix", [".js", ".ts"])
def test_named_class_expression(tmp_path, suffix):
    """Test A: Named class expression.

    const Foo = class Bar { method() {} };
    - Foo exists as a class node.
    - Foo has the class-scoped .method().
    - Bar does not become a separate class node.
    - No variable node for Foo remains.
    """
    source = tmp_path / f"named_expr{suffix}"
    source.write_text(
        """
const Foo = class Bar {
    method() {}
};
""",
        encoding="utf-8",
    )
    result = extract_js(source)
    nodes_by_label = {n["label"]: n for n in result["nodes"]}
    labels = set(nodes_by_label)

    assert "Foo" in labels
    assert "Bar" not in labels
    assert ".method()" in labels

    foo_nid = nodes_by_label["Foo"]["id"]
    method_nid = nodes_by_label[".method()"]["id"]

    # Method belongs to Foo
    method_edges = [
        e for e in result["edges"]
        if e["relation"] == "method" and e["source"] == foo_nid and e["target"] == method_nid
    ]
    assert len(method_edges) == 1

    # Exactly one Foo node exists
    assert sum(1 for n in result["nodes"] if n["label"] == "Foo") == 1


@pytest.mark.parametrize("suffix", [".js", ".ts"])
def test_anonymous_class_expression_exported(tmp_path, suffix):
    """Test B: Exported anonymous class expression.

    export const Foo = class { method() {} };
    - Foo is a class.
    - Its method belongs to Foo.
    """
    source = tmp_path / f"anon_expr{suffix}"
    source.write_text(
        """
export const Foo = class {
    method() {}
};
""",
        encoding="utf-8",
    )
    result = extract_js(source)
    nodes_by_label = {n["label"]: n for n in result["nodes"]}
    labels = set(nodes_by_label)

    assert "Foo" in labels
    assert ".method()" in labels

    foo_nid = nodes_by_label["Foo"]["id"]
    method_nid = nodes_by_label[".method()"]["id"]

    method_edges = [
        e for e in result["edges"]
        if e["relation"] == "method" and e["source"] == foo_nid and e["target"] == method_nid
    ]
    assert len(method_edges) == 1


@pytest.mark.parametrize("suffix", [".js", ".ts"])
def test_nested_class_declaration(tmp_path, suffix):
    """Test C: Nested class declaration inside function.

    function factory() {
        class Inner {
            method() {}
        }
    }
    - factory() contains Inner
    - Inner is a class
    - Inner owns .method()
    """
    source = tmp_path / f"nested_decl{suffix}"
    source.write_text(
        """
function factory() {
    class Inner {
        method() {}
    }
}
""",
        encoding="utf-8",
    )
    result = extract_js(source)
    nodes_by_label = {n["label"]: n for n in result["nodes"]}
    labels = set(nodes_by_label)

    assert "factory()" in labels
    assert "Inner" in labels
    assert ".method()" in labels

    factory_nid = nodes_by_label["factory()"]["id"]
    inner_nid = nodes_by_label["Inner"]["id"]
    method_nid = nodes_by_label[".method()"]["id"]

    # factory() contains Inner
    assert any(
        e["source"] == factory_nid and e["target"] == inner_nid and e["relation"] == "contains"
        for e in result["edges"]
    )
    # Inner owns method
    assert any(
        e["source"] == inner_nid and e["target"] == method_nid and e["relation"] == "method"
        for e in result["edges"]
    )


@pytest.mark.parametrize("suffix", [".js", ".ts"])
def test_returned_named_class(tmp_path, suffix):
    """Test D: Returned named class.

    function factory(Base) {
        return class Shared extends Base {
            method() {}
        };
    }
    - Shared exists under factory()
    - Shared owns .method()
    - No inherits edge to Base yet in Pass 1
    """
    source = tmp_path / f"ret_named{suffix}"
    source.write_text(
        """
function factory(Base) {
    return class Shared extends Base {
        method() {}
    };
}
""",
        encoding="utf-8",
    )
    result = extract_js(source)
    nodes_by_label = {n["label"]: n for n in result["nodes"]}
    labels = set(nodes_by_label)

    assert "factory()" in labels
    assert "Shared" in labels
    assert ".method()" in labels

    factory_nid = nodes_by_label["factory()"]["id"]
    shared_nid = nodes_by_label["Shared"]["id"]
    method_nid = nodes_by_label[".method()"]["id"]

    assert any(
        e["source"] == factory_nid and e["target"] == shared_nid and e["relation"] == "contains"
        for e in result["edges"]
    )
    assert any(
        e["source"] == shared_nid and e["target"] == method_nid and e["relation"] == "method"
        for e in result["edges"]
    )
    assert not any(e["relation"] == "inherits" for e in result["edges"])


@pytest.mark.parametrize("suffix", [".js", ".ts"])
def test_returned_anonymous_class(tmp_path, suffix):
    """Test E: Returned anonymous class.

    function mixin(Base) {
        return class extends Base {
            method() {}
        };
    }
    - mixin@class exists under mixin()
    - mixin@class owns .method()
    - Deterministic ID
    - No inherits edge to Base yet in Pass 1
    """
    source = tmp_path / f"ret_anon{suffix}"
    source.write_text(
        """
function mixin(Base) {
    return class extends Base {
        method() {}
    };
}
""",
        encoding="utf-8",
    )
    result = extract_js(source)
    nodes_by_label = {n["label"]: n for n in result["nodes"]}
    labels = set(nodes_by_label)

    assert "mixin()" in labels
    assert "mixin@class" in labels
    assert ".method()" in labels

    mixin_nid = nodes_by_label["mixin()"]["id"]
    class_nid = nodes_by_label["mixin@class"]["id"]
    method_nid = nodes_by_label[".method()"]["id"]

    assert any(
        e["source"] == mixin_nid and e["target"] == class_nid and e["relation"] == "contains"
        for e in result["edges"]
    )
    assert any(
        e["source"] == class_nid and e["target"] == method_nid and e["relation"] == "method"
        for e in result["edges"]
    )
    assert not any(e["relation"] == "inherits" for e in result["edges"])


def test_multiple_anonymous_returned_classes(tmp_path):
    """Multiple anonymous classes inside the same function receive distinct deterministic IDs."""
    source = tmp_path / "multi_anon.js"
    source.write_text(
        """
function makeClasses(cond) {
    if (cond) {
        return class {
            firstMethod() {}
        };
    }
    return class {
        secondMethod() {}
    };
}
""",
        encoding="utf-8",
    )
    result = extract_js(source)
    labels = {n["label"] for n in result["nodes"]}
    assert "makeClasses()" in labels
    assert "makeClasses@class" in labels
    assert ".firstMethod()" in labels
    assert ".secondMethod()" in labels
    # Second anonymous class disambiguates with line number
    assert any(l.startswith("makeClasses@class@L") for l in labels)


def test_preserve_ordinary_variables(tmp_path):
    """Ordinary variable declarations and initializers retain their normal behavior."""
    source = tmp_path / "ordinary.js"
    source.write_text(
        """
const value = 42;
export const exportedScalar = 100;
export const other = SomeClass;
export const result = createThing();
""",
        encoding="utf-8",
    )
    result = extract_js(source)
    labels = {n["label"] for n in result["nodes"]}
    assert "value" not in labels
    assert "exportedScalar" in labels
    assert "other" in labels
    assert "result" in labels
