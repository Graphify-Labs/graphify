"""C# type arguments on `new Foo<Bar>()` must produce `references[generic_arg]` edges.

The call-site fix in #2911 covered `Do<T>()` and `services.AddScoped<ISvc, Impl>()`, both of
which reach the type-argument list through an invocation's `function` field.
`object_creation_expression` keeps the constructed type in its `type` field instead, so that
branch never saw a type-argument list and every argument was dropped: `new Wrapper<Widget>()`
linked `Wrapper` and lost `Widget` entirely.

The shapes below are the ones that go missing in practice -- a generic wrapper built around a
collaborator (test doubles, lazy factories, typed caches) and a generic collection built from
a literal. In each case the wrapper is present in the source only as a construction, so the
dropped argument is the only edge that records the dependency at all.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from graphify.extract import extract


def _graph(tmp_path: Path, files: dict[str, str]) -> dict:
    paths = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
        paths.append(path)
    return extract(paths, cache_root=tmp_path)


def _generic_arg_targets(graph, *, from_label: str) -> set[str]:
    """Labels reached by `references[generic_arg]` edges out of `from_label`."""
    nodes = {n["id"]: n for n in graph["nodes"]}
    out = set()
    for edge in graph["edges"]:
        if edge.get("relation") != "references":
            continue
        if edge.get("context") != "generic_arg":
            continue
        source = nodes.get(edge.get("source"), {})
        if source.get("label") != from_label:
            continue
        target = nodes.get(edge.get("target"), {})
        if target.get("label"):
            out.add(target["label"])
    return out


CORPUS = {
    "Widget.cs": """
        namespace App.Data;
        public class Widget { public int Id { get; set; } }
        public interface IGadget { void Go(); }
        public class Wrapper<T> { }
        public class Bag<T> { }
        public class Pair<TFirst, TSecond> { }
    """,
    "Consumer.cs": """
        namespace App.Use;
        using App.Data;

        public class Consumer
        {
            public void WrapsAnInterface() { var w = new Wrapper<IGadget>(); }
            public void WrapsAClass() { var w = new Wrapper<Widget>(); }
            public void BuildsACollection() { var b = new Bag<Widget>(); }
            public void TwoArguments() { var p = new Pair<Widget, IGadget>(); }
            public void Nested() { var n = new Wrapper<Bag<Widget>>(); }
            public void Qualified() { var q = new App.Data.Wrapper<Widget>(); }
            public void WithInitializer() { var w = new Wrapper<Widget> { }; }
        }
    """,
}


def test_object_creation_links_a_generic_interface_argument(tmp_path):
    graph = _graph(tmp_path, CORPUS)
    assert "IGadget" in _generic_arg_targets(graph, from_label=".WrapsAnInterface()")


def test_object_creation_links_a_generic_class_argument(tmp_path):
    graph = _graph(tmp_path, CORPUS)
    assert "Widget" in _generic_arg_targets(graph, from_label=".WrapsAClass()")


def test_object_creation_links_a_collection_element_type(tmp_path):
    graph = _graph(tmp_path, CORPUS)
    assert "Widget" in _generic_arg_targets(graph, from_label=".BuildsACollection()")


def test_object_creation_links_every_argument_of_a_two_parameter_type(tmp_path):
    graph = _graph(tmp_path, CORPUS)
    targets = _generic_arg_targets(graph, from_label=".TwoArguments()")
    assert {"Widget", "IGadget"} <= targets


def test_object_creation_links_a_nested_type_argument(tmp_path):
    """`new Wrapper<Bag<Widget>>()` should reach the innermost argument too."""
    graph = _graph(tmp_path, CORPUS)
    targets = _generic_arg_targets(graph, from_label=".Nested()")
    assert "Widget" in targets


def test_object_creation_links_arguments_on_a_namespace_qualified_type(tmp_path):
    graph = _graph(tmp_path, CORPUS)
    assert "Widget" in _generic_arg_targets(graph, from_label=".Qualified()")


def test_object_creation_with_an_initializer_still_links_arguments(tmp_path):
    """The object-initializer form parses with an extra child; arguments still count."""
    graph = _graph(tmp_path, CORPUS)
    assert "Widget" in _generic_arg_targets(graph, from_label=".WithInitializer()")


def test_constructed_type_itself_is_still_linked(tmp_path):
    """The pre-existing `calls` edge to the constructed type must survive."""
    graph = _graph(tmp_path, CORPUS)
    nodes = {n["id"]: n for n in graph["nodes"]}
    labels = set()
    for edge in graph["edges"]:
        source = nodes.get(edge.get("source"), {})
        if source.get("label") == ".WrapsAClass()":
            target = nodes.get(edge.get("target"), {})
            if target.get("label"):
                labels.add(target["label"])
    assert "Wrapper" in labels


def test_a_type_parameter_is_not_linked_as_a_type(tmp_path):
    """`new Wrapper<T>()` inside a generic method names a parameter, not a real type."""
    graph = _graph(tmp_path, {
        "Widget.cs": CORPUS["Widget.cs"],
        "Generic.cs": """
            namespace App.Use;
            using App.Data;

            public class Factory
            {
                public Wrapper<T> Make<T>() { return new Wrapper<T>(); }
            }
        """,
    })
    assert "T" not in _generic_arg_targets(graph, from_label=".Make()")
