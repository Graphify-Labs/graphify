from pathlib import Path

from graphify.extract import _get_extractor, extract, extract_matlab, extract_objc


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _labels(result: dict) -> dict[str, str]:
    return {str(node["id"]): str(node.get("label", "")) for node in result["nodes"]}


def _relations(result: dict, relation: str) -> list[tuple[str, str]]:
    labels = _labels(result)
    return [
        (labels.get(str(edge["source"]), ""), labels.get(str(edge["target"]), ""))
        for edge in result["edges"]
        if edge.get("relation") == relation
    ]


def test_m_extension_routes_matlab_and_objc_by_content(tmp_path: Path) -> None:
    matlab = _write(tmp_path / "solver.m", "function y = solver(x)\ny = x + 1;\nend\n")
    objc = _write(tmp_path / "Widget.m", "#import <F/F.h>\n@implementation Widget\n@end\n")

    assert _get_extractor(matlab) is extract_matlab
    assert _get_extractor(objc) is extract_objc

    result = extract([matlab], cache_root=tmp_path / ".cache", parallel=False)
    assert result["nodes"]
    assert all(node.get("language") == "matlab" for node in result["nodes"])
    assert all(node.get("language_family") == "matlab" for node in result["nodes"])


def test_matlab_cross_file_call_but_indexing_is_not_a_call(tmp_path: Path) -> None:
    helper = _write(tmp_path / "helper.m", "function y = helper(x)\ny = x + 1;\nend\n")
    main = _write(tmp_path / "main.m", "A = [1, 2];\nx = A(1);\ny = helper(1);\n")

    result = extract([helper, main], cache_root=tmp_path / ".cache", parallel=False)
    calls = _relations(result, "calls")
    assert ("main.m", "helper()") in calls
    assert all(target != "A()" for _, target in calls)


def test_matlab_class_members_inheritance_and_self_calls(tmp_path: Path) -> None:
    model = _write(
        tmp_path / "Model.m",
        """classdef Model < Base
properties (Access = private)
 value double
end
events
 Changed
end
methods
 function y = run(obj, x)
  y = obj.compute(x);
 end
 function y = compute(obj, x)
  y = x + obj.value;
 end
end
end
""",
    )
    result = extract([model], cache_root=tmp_path / ".cache", parallel=False)
    labels = set(_labels(result).values())
    assert {"Model", "value", "Changed", ".run()", ".compute()"} <= labels
    value_node = next(node for node in result["nodes"] if node.get("label") == "value")
    assert value_node.get("visibility") == "private"
    assert ("Model", "Base") in _relations(result, "inherits")
    assert (".run()", ".compute()") in _relations(result, "calls")


def test_matlab_packages_function_handles_and_unknown_call_index_ambiguity(tmp_path: Path) -> None:
    helper = _write(
        tmp_path / "+util" / "helper.m",
        "function y = helper(x)\ny = x + 1;\nend\n",
    )
    callback = _write(
        tmp_path / "callback.m",
        "function y = callback(x)\ny = x * 2;\nend\n",
    )
    main = _write(
        tmp_path / "main.m",
        "f = @callback;\na = f(1);\nb = util.helper(2);\ng = @util.helper;\nd = g(4);\nc = Unknown(3);\n",
    )
    result = extract([helper, callback, main], cache_root=tmp_path / ".cache", parallel=False)
    assert ("main.m", "helper()") in _relations(result, "calls")
    assert ("main.m", "callback()") in _relations(result, "indirect_call")
    assert ("main.m", "helper()") in _relations(result, "indirect_call")
    assert all(target != "Unknown" for _, target in _relations(result, "calls"))
    assert all(target != "Unknown" for _, target in _relations(result, "instantiates"))


def test_ignored_parameter_still_counts_toward_arity(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "select.m",
        "function y = select(x, ~, z)\ny = x + z;\nend\n",
    )
    result = extract([source], cache_root=tmp_path / ".cache", parallel=False)
    function = next(node for node in result["nodes"] if node.get("label") == "select()")
    assert function.get("arity") == 3
    assert function.get("parameter_names") == ["x", "~", "z"]


def test_matlab_private_function_does_not_resolve_outside_parent_tree(tmp_path: Path) -> None:
    private_fn = _write(
        tmp_path / "pkg" / "private" / "secret.m",
        "function y = secret(x)\ny = x;\nend\n",
    )
    outside = _write(tmp_path / "other" / "main.m", "y = secret(1);\n")
    result = extract([private_fn, outside], cache_root=tmp_path / ".cache", parallel=False)
    assert ("main.m", "secret()") not in _relations(result, "calls")


def test_matlab_constructed_local_receiver_resolves_class_method(tmp_path: Path) -> None:
    service = _write(
        tmp_path / "Service.m",
        """classdef Service
methods
 function run(obj)
 end
end
end
""",
    )
    main = _write(tmp_path / "main.m", "svc = Service();\nsvc.run();\n")
    result = extract([service, main], cache_root=tmp_path / ".cache", parallel=False)
    assert ("main.m", ".run()") in _relations(result, "calls")


def test_matlab_routing_ignores_objc_text_but_recognizes_message_only_objc(tmp_path: Path) -> None:
    handle = _write(tmp_path / "handle.m", "f = @interface;\ny = f(1);\n")
    comment = _write(tmp_path / "comment.m", "% #import is documentation, not ObjC\ny = 1;\n")
    objc = _write(tmp_path / "MessageOnly.m", "void invoke(id target) { [target run]; }\n")
    custom_objc = _write(
        tmp_path / "CustomResult.m",
        "Result *make(id observer) { [observer refresh]; return nil; }\n",
    )

    assert _get_extractor(handle) is extract_matlab
    assert _get_extractor(comment) is extract_matlab
    assert _get_extractor(objc) is extract_objc
    assert _get_extractor(custom_objc) is extract_objc


def test_function_handle_reference_is_not_a_call_but_feval_is(tmp_path: Path) -> None:
    callback = _write(
        tmp_path / "callback.m",
        "function y = callback(x)\ny = x;\nend\n",
    )
    holder = _write(tmp_path / "holder.m", "f = @callback;\n")
    referenced = extract([callback, holder], cache_root=tmp_path / ".cache-ref", parallel=False)
    assert ("holder.m", "callback()") in _relations(referenced, "references")
    assert ("holder.m", "callback()") not in _relations(referenced, "indirect_call")

    invoked = _write(tmp_path / "invoked.m", "y = feval(@callback, 1);\n")
    called = extract([callback, invoked], cache_root=tmp_path / ".cache-call", parallel=False)
    assert ("invoked.m", "callback()") in _relations(called, "indirect_call")


def test_nested_function_does_not_leak_to_top_level_sibling(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "scopes.m",
        """function y = a(x)
y = hidden(x);
function z = hidden(v)
z = v;
end
end
function y = b(x)
y = hidden(x);
end
""",
    )
    result = extract([source], cache_root=tmp_path / ".cache", parallel=False)
    calls = _relations(result, "calls")
    assert ("a()", "hidden()") in calls
    assert ("b()", "hidden()") not in calls


def test_private_function_is_visible_only_to_immediate_parent_folder(tmp_path: Path) -> None:
    private_fn = _write(
        tmp_path / "pkg" / "private" / "secret.m",
        "function y = secret(x)\ny = x;\nend\n",
    )
    sibling = _write(tmp_path / "pkg" / "inside.m", "y = secret(1);\n")
    descendant = _write(tmp_path / "pkg" / "sub" / "nested.m", "y = secret(1);\n")
    result = extract(
        [private_fn, sibling, descendant],
        cache_root=tmp_path / ".cache",
        parallel=False,
    )
    calls = _relations(result, "calls")
    assert ("inside.m", "secret()") in calls
    assert ("nested.m", "secret()") not in calls


def test_bare_call_does_not_bind_to_unrelated_class_method(tmp_path: Path) -> None:
    model = _write(
        tmp_path / "Model.m",
        """classdef Model
methods
function run(obj)
end
end
end
""",
    )
    script = _write(tmp_path / "main.m", "run();\n")
    result = extract([model, script], cache_root=tmp_path / ".cache", parallel=False)
    assert ("main.m", ".run()") not in _relations(result, "calls")


def test_static_method_first_argument_is_not_treated_as_self(tmp_path: Path) -> None:
    model = _write(
        tmp_path / "StaticModel.m",
        """classdef StaticModel
methods (Static)
function run(x)
x.helper();
end
end
methods
function helper(obj)
end
end
end
""",
    )
    result = extract([model], cache_root=tmp_path / ".cache", parallel=False)
    assert (".run()", ".helper()") not in _relations(result, "calls")


def test_uppercase_indexed_variable_is_not_inferred_as_constructor(tmp_path: Path) -> None:
    foo = _write(
        tmp_path / "Foo.m",
        """classdef Foo
methods
function run(obj)
end
end
end
""",
    )
    script = _write(
        tmp_path / "capital_index.m",
        "Foo = [1, 2];\nx = Foo(1);\nx.run();\n",
    )
    result = extract([foo, script], cache_root=tmp_path / ".cache", parallel=False)
    assert ("capital_index.m", ".run()") not in _relations(result, "calls")


def test_bound_instance_method_handle_resolves_reference_and_invocation(tmp_path: Path) -> None:
    service = _write(
        tmp_path / "Service.m",
        """classdef Service
methods
function run(obj)
end
end
end
""",
    )
    script = _write(
        tmp_path / "main.m",
        "svc = Service();\nf = @svc.run;\nf();\n",
    )
    result = extract([service, script], cache_root=tmp_path / ".cache", parallel=False)
    assert ("main.m", ".run()") in _relations(result, "references")
    assert ("main.m", ".run()") in _relations(result, "indirect_call")


def test_nested_package_qualifier_resolves_exact_function(tmp_path: Path) -> None:
    ab = _write(
        tmp_path / "+a" / "+b" / "helper.m",
        "function y = helper(x)\ny = x;\nend\n",
    )
    cd = _write(
        tmp_path / "+c" / "+d" / "helper.m",
        "function y = helper(x)\ny = x;\nend\n",
    )
    main = _write(tmp_path / "main.m", "y = a.b.helper(1);\n")
    result = extract([ab, cd, main], cache_root=tmp_path / ".cache", parallel=False)
    nodes = {str(node["id"]): node for node in result["nodes"]}
    targets = [
        nodes[str(edge["target"])]
        for edge in result["edges"]
        if edge.get("relation") == "calls"
        and nodes.get(str(edge["source"]), {}).get("label") == "main.m"
    ]
    assert len(targets) == 1
    assert targets[0].get("qualified_name") == "a.b.helper"


def test_function_scoped_import_disambiguates_package_call(tmp_path: Path) -> None:
    a = _write(
        tmp_path / "+a" / "helper.m",
        "function y = helper(x)\ny = x;\nend\n",
    )
    b = _write(
        tmp_path / "+b" / "helper.m",
        "function y = helper(x)\ny = x;\nend\n",
    )
    main = _write(
        tmp_path / "main.m",
        "function y = main(x)\nimport a.helper\ny = helper(x);\nend\n",
    )
    result = extract([a, b, main], cache_root=tmp_path / ".cache", parallel=False)
    nodes = {str(node["id"]): node for node in result["nodes"]}
    targets = [
        nodes[str(edge["target"])]
        for edge in result["edges"]
        if edge.get("relation") == "calls"
        and nodes.get(str(edge["source"]), {}).get("label") == "main()"
    ]
    assert len(targets) == 1
    assert targets[0].get("qualified_name") == "a.helper"


def test_project_function_can_shadow_builtin_and_command_form_resolves(tmp_path: Path) -> None:
    mean_fn = _write(
        tmp_path / "mean.m",
        "function y = mean(x)\ny = x;\nend\n",
    )
    foo_fn = _write(
        tmp_path / "foo.m",
        "function foo(value)\ndisp(value);\nend\n",
    )
    main = _write(tmp_path / "main.m", "x = mean(1);\nfoo bar\n")
    result = extract([mean_fn, foo_fn, main], cache_root=tmp_path / ".cache", parallel=False)
    calls = _relations(result, "calls")
    assert ("main.m", "mean()") in calls
    assert ("main.m", "foo()") in calls


def test_old_style_class_folder_uses_one_portable_class_identity(tmp_path: Path) -> None:
    run = _write(
        tmp_path / "@Widget" / "run.m",
        "function run(obj)\nend\n",
    )
    stop = _write(
        tmp_path / "@Widget" / "stop.m",
        "function stop(obj)\nend\n",
    )
    result = extract([run, stop], cache_root=tmp_path / ".cache", parallel=False)
    class_ids = {
        str(node["id"])
        for node in result["nodes"]
        if node.get("type") == "class" and node.get("label") == "Widget"
    }
    assert class_ids == {"matlab_widget"}
    assert {("Widget", ".run()"), ("Widget", ".stop()")} <= set(
        _relations(result, "method")
    )


def test_matlab_class_is_not_merged_into_same_stem_objc_header(tmp_path: Path) -> None:
    header = _write(
        tmp_path / "Foo.h",
        "@interface Foo\n- (void)nativeOnly;\n@end\n",
    )
    matlab = _write(
        tmp_path / "Foo.m",
        """classdef Foo
methods
function matlabOnly(obj)
end
end
end
""",
    )
    result = extract([header, matlab], cache_root=tmp_path / ".cache", parallel=False)
    foo_nodes = [node for node in result["nodes"] if node.get("label") == "Foo"]
    assert {node.get("language") for node in foo_nodes} == {"objective-c", "matlab"}
    assert ".matlabOnly()" in set(_labels(result).values())
    assert "-nativeOnly" in set(_labels(result).values())


def test_matlab_class_does_not_make_objc_receiver_type_ambiguous(tmp_path: Path) -> None:
    objc = _write(
        tmp_path / "Native.m",
        """@interface Widget
+ (instancetype)new;
@end
@interface Maker
- (id)make;
@end
@implementation Maker
- (id)make { return [Widget new]; }
@end
""",
    )
    matlab = _write(tmp_path / "models" / "Other.m", "classdef Widget\nend\n")
    result = extract([objc, matlab], cache_root=tmp_path / ".cache", parallel=False)
    assert ("-make", "+new") in _relations(result, "calls")


def test_matlab_sibling_does_not_block_native_header_implementation_merge(tmp_path: Path) -> None:
    header = _write(
        tmp_path / "Foo.h",
        "@interface Foo\n- (void)work;\n@end\n",
    )
    implementation = _write(
        tmp_path / "Foo.mm",
        "@implementation Foo\n- (void)work {}\n@end\n",
    )
    matlab = _write(tmp_path / "Foo.m", "classdef Foo\nend\n")
    caller = _write(
        tmp_path / "Caller.m",
        """#import "Foo.h"
@interface Caller
- (void)call;
@end
@implementation Caller
- (void)call { Foo *foo; [foo work]; }
@end
""",
    )
    result = extract(
        [header, implementation, matlab, caller],
        cache_root=tmp_path / ".cache",
        parallel=False,
    )
    assert ("-call", "-work") in _relations(result, "calls")
    foo_nodes = [node for node in result["nodes"] if node.get("label") == "Foo"]
    assert {node.get("language") for node in foo_nodes} == {"objective-c", "matlab"}
