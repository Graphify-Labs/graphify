"""A call written inside a Rust macro's arguments (`println!("{}", f(x))`) is a call.

Tree-sitter keeps macro arguments as raw tokens, so these calls used to produce no
edge at all and `explain` showed the callee with no callers.
"""

from graphify.extract import extract


def _calls(tmp_path, files: dict[str, str]) -> set[tuple[str, str, str]]:
    paths = []
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    result = extract(paths, root=tmp_path, cache_root=tmp_path / "cache")
    label = {node["id"]: node["label"] for node in result["nodes"]}
    return {
        (label.get(edge["source"], ""), label.get(edge["target"], ""), edge["confidence"])
        for edge in result["edges"]
        if edge["relation"] == "calls"
    }


def test_call_inside_macro_arguments_links_in_file(tmp_path):
    calls = _calls(tmp_path, {"lib.rs": (
        "fn width() -> usize { 3 }\n"
        "fn height() -> usize { 4 }\n"
        "fn report() { println!(\"{} {}\", width(), height()); }\n"
        "fn check() { assert_eq!(width(), 3); }\n"
        "fn many() -> Vec<usize> { vec![width(), 1] }\n"
    )})
    assert ("report()", "width()", "INFERRED") in calls
    assert ("report()", "height()", "INFERRED") in calls
    assert ("check()", "width()", "INFERRED") in calls
    assert ("many()", "width()", "INFERRED") in calls


def test_nested_token_trees_are_scanned(tmp_path):
    calls = _calls(tmp_path, {"lib.rs": (
        "fn inner() -> u8 { 1 }\n"
        "fn outer() { println!(\"{:?}\", (Some(inner()), [inner()])); }\n"
    )})
    assert ("outer()", "inner()", "INFERRED") in calls


def test_call_inside_macro_reaches_a_function_imported_from_another_file(tmp_path):
    calls = _calls(tmp_path, {
        "src/formatter.rs": "pub fn format_line() -> String { String::new() }\n",
        "src/main.rs": (
            "mod formatter;\n"
            "use crate::formatter::format_line;\n"
            "fn main() { println!(\"{}\", format_line()); }\n"
        ),
    })
    assert any(src == "main()" and tgt == "format_line()" for src, tgt, _ in calls)


def test_method_path_and_constructor_tokens_are_not_bare_calls(tmp_path):
    calls = _calls(tmp_path, {"lib.rs": (
        "struct Wrap(u8);\n"
        "fn len() -> usize { 0 }\n"
        "fn new() -> u8 { 0 }\n"
        "fn show(v: Vec<u8>) { println!(\"{} {} {:?}\", v.len(), Vec::<u8>::new().len(), Wrap(1).0); }\n"
    )})
    assert not any(src == "show()" for src, _, _ in calls)


def test_nested_macro_name_is_not_a_call(tmp_path):
    calls = _calls(tmp_path, {"lib.rs": (
        "fn format() -> String { String::new() }\n"
        "fn show() { println!(\"{}\", format!(\"x\")); }\n"
    )})
    assert ("show()", "format()", "INFERRED") not in calls


def test_macro_rules_body_is_not_scanned(tmp_path):
    calls = _calls(tmp_path, {"lib.rs": (
        "fn helper() {}\n"
        "macro_rules! twice { ($e:expr) => { helper(); helper(); }; }\n"
        "fn idle() {}\n"
    )})
    assert not any(tgt == "helper()" for _, tgt, _ in calls)


def test_a_parsed_call_keeps_extracted_when_the_macro_comes_first(tmp_path):
    calls = _calls(tmp_path, {"lib.rs": (
        "fn compute(x: u8) -> u8 { x }\n"
        "fn run() { println!(\"{}\", compute(1)); let _y = compute(2); }\n"
    )})
    assert ("run()", "compute()", "EXTRACTED") in calls
    assert ("run()", "compute()", "INFERRED") not in calls


def test_dsl_macros_are_not_scanned(tmp_path):
    calls = _calls(tmp_path, {"lib.rs": (
        "fn users() {}\n"
        "fn name() {}\n"
        "table! { users (id) { id -> Int4, } }\n"
        "fn gen() { quote! { #name(1) }; html! { <div>{ users() }</div> }; }\n"
    )})
    assert not any(tgt in ("users()", "name()") for _, tgt, _ in calls)


def test_a_path_qualified_log_macro_is_scanned(tmp_path):
    calls = _calls(tmp_path, {"lib.rs": (
        "fn state() -> u8 { 0 }\n"
        "fn tick() { log::info!(\"{}\", state()); }\n"
    )})
    assert ("tick()", "state()", "INFERRED") in calls
