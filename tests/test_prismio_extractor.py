"""Extraction coverage for Prismio (.psm)."""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract
from graphify.extractors.prismio import _code_view, extract_prismio


def _project(tmp_path: Path, files: dict[str, str]) -> list[Path]:
    # build.ums marks the project root so import resolution never walks out of tmp_path.
    (tmp_path / "build.ums").write_text("", encoding="utf-8")
    paths = []
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return paths


def _labels(result: dict) -> dict[str, str]:
    return {node["id"]: node["label"] for node in result["nodes"]}


def _edges(result: dict, relation: str) -> set[tuple[str | None, str | None]]:
    labels = _labels(result)
    return {
        (labels.get(e["source"], e["source"]), labels.get(e["target"], e["target"]))
        for e in result["edges"]
        if e["relation"] == relation
    }


def test_code_view_blanks_comments_and_strings_but_keeps_offsets_and_interpolation():
    source = (
        'let a = "fn fake(" // fn also_fake(\n'
        "/* nested /* fn nope() */ still comment */\n"
        'let b = """multi\nfn nope2()\n"""\n'
        'let c = "x ${real(1)} y \\${notcode(2)}"\n'
        "let d = 'it'\n"
    )
    view = _code_view(source)
    assert len(view) == len(source)
    assert view.count("\n") == source.count("\n")
    assert "fake" not in view and "also_fake" not in view
    assert "nope" not in view and "nope2" not in view
    assert "notcode" not in view
    assert "real(1)" in view


def test_declarations_methods_and_calls(tmp_path):
    (path,) = _project(tmp_path, {"main.psm": """\
// fn commented() {}
struct Point { x: Int, y: Int }

enum Shape<T> {
    Dot,
    Box(T, Int)
}

trait Ord {
    fn cmp(self, other: Self) -> Int
}

impl Ord for Point {
    fn cmp(self, other: Self) -> Int { return self.weight() - other.weight() }
    fn weight(self) -> Int { return self.x + self.y }
}

public fn helper(a: Int, b: Int) -> Int where Int: Ord {
    return a + b
}

fn main() -> Int {
    println("calls helper(1, 2) only in a string")
    return helper(1, 2)
}
extern fn c_exit(code: Int) -> Int produce(free)
let LIMIT = 3
"""})

    result = extract([path], cache_root=tmp_path)
    labels = {node["label"] for node in result["nodes"]}
    assert {"main.psm", "Point", "Shape", "Ord", "Dot", "Box", "helper()", "main()",
            "c_exit()", ".cmp()", ".weight()", "impl Ord for Point", "LIMIT"} <= labels
    kinds = {n["label"]: n["metadata"]["kind"] for n in result["nodes"] if n.get("metadata")}
    assert kinds["Point"] == "struct" and kinds["Shape"] == "enum" and kinds["Ord"] == "trait"
    assert kinds["Dot"] == "variant" and kinds["c_exit()"] == "extern_function"
    assert "commented()" not in labels

    calls = _edges(result, "calls")
    assert ("main()", "helper()") in calls
    assert (".cmp()", ".weight()") in calls  # self.weight() inside the same impl
    assert ("impl Ord for Point", "Ord") in _edges(result, "implements")
    assert ("impl Ord for Point", "Point") in _edges(result, "references")
    assert ("impl Ord for Point", ".cmp()") in _edges(result, "method")


def test_overloaded_free_functions_are_not_guessed(tmp_path):
    (path,) = _project(tmp_path, {"over.psm": """\
fn show(value: Int) -> String { return "" }
fn show(value: String) -> String { return value }
fn run() { show(1) }
"""})
    result = extract([path], cache_root=tmp_path)
    assert not {pair for pair in _edges(result, "calls") if pair[0] == "run()"}


def test_imports_resolve_by_walking_up_and_cover_every_form(tmp_path):
    paths = _project(tmp_path, {
        "src/app/main.psm": """\
import util.strings
import util.strings.trim as t
import {a, b as bb} from util
import * from extra
import extra.*
""",
        "src/util/strings.psm": "fn trim(s: String) -> String { return s }\n",
        "src/util/a.psm": "fn fa() {}\n",
        "src/util/b.psm": "fn fb() {}\n",
        "src/extra/one.psm": "fn one() {}\n",
        "src/extra/two.psm": "fn two() {}\n",
    })
    result = extract(paths, cache_root=tmp_path)
    by_id = {n["id"]: n for n in result["nodes"]}
    targets = {
        Path(by_id[e["target"]]["source_file"]).name
        for e in result["edges"]
        if e["relation"] == "imports_from"
        and e["target"] in by_id
        and Path(by_id[e["source"]]["source_file"]).name == "main.psm"
    }
    assert targets == {"strings.psm", "a.psm", "b.psm", "one.psm", "two.psm"}


def test_unresolvable_imports_and_builtin_types_leave_no_stubs(tmp_path):
    (path,) = _project(tmp_path, {"lonely.psm": """\
import std.io
trait Show { fn show(self) -> String }
impl Show for Int { fn show(self) -> String { return "" } }
"""})
    result = extract([path], cache_root=tmp_path)
    assert not [e for e in result["edges"] if e["relation"] == "imports_from"]
    assert all(node.get("source_file") for node in result["nodes"])
    # `Int` has no declaration, so only the trait binds.
    assert ("impl Show for Int", "Show") in _edges(result, "implements")
    assert ("impl Show for Int", "Int") not in _edges(result, "references")


def test_impl_in_another_file_binds_to_imported_type_and_trait(tmp_path):
    paths = _project(tmp_path, {
        "model.psm": "struct Point { x: Int }\ntrait Show { fn show(self) -> String }\n",
        "impls.psm": """\
import model

impl Show for Point {
    fn show(self) -> String { return "" }
}
""",
    })
    result = extract(paths, cache_root=tmp_path)
    assert ("impl Show for Point", "Show") in _edges(result, "implements")
    assert ("impl Show for Point", "Point") in _edges(result, "references")


def test_cross_file_call_resolves_through_the_shared_pass(tmp_path):
    paths = _project(tmp_path, {
        "lib.psm": "public fn double(n: Int) -> Int { return n * 2 }\n",
        "app.psm": "import lib\nfn run() -> Int { return double(4) }\n",
    })
    result = extract(paths, cache_root=tmp_path)
    assert ("run()", "double()") in _edges(result, "calls")


def test_ids_are_deterministic_and_distinguish_overloads(tmp_path):
    (path,) = _project(tmp_path, {"o.psm": """\
fn f(a: Int) {}
fn f(a: String) {}
"""})
    first = extract_prismio(path)
    second = extract_prismio(path)
    ids = [n["id"] for n in first["nodes"] if n["label"] == "f()"]
    assert len(ids) == 2 and len(set(ids)) == 2
    assert first == second


def test_overloads_that_differ_only_by_punctuation_get_distinct_nodes(tmp_path):
    (path,) = _project(tmp_path, {"o.psm": """\
fn show(value: Int) {}
fn show(value: Int?) {}
fn show(value: Vec<Int>) {}
fn show(value: Vec<String>) {}
"""})
    result = extract_prismio(path)
    ids = [n["id"] for n in result["nodes"] if n["label"] == "show()"]
    assert len(ids) == 4 and len(set(ids)) == 4


def test_signatures_fields_payloads_and_bounds_become_type_references(tmp_path):
    (path,) = _project(tmp_path, {"t.psm": """\
struct Point { x: Int }
struct Line { start: Point, end: Point }
trait Show { fn show(self) -> String }
enum Shape<T> { Dot, Wrapped(Point), Boxed(T) }
fn measure<T: Show>(a: Point, b: Vec<Line>) -> Shape<Point> where T: Show { return Shape.Dot }
fn make() -> Point { return Point { x: 1 } }
"""})
    result = extract([path], cache_root=tmp_path)
    references = _edges(result, "references")
    assert ("Line", "Point") in references
    assert ("Shape", "Point") in references
    assert ("measure()", "Point") in references
    assert ("measure()", "Show") in references  # a bound is a reference to the trait
    assert ("make()", "Point") in references  # `Point { .. }` literal and the return type
    # `T` is a generic parameter, never a type to look up; `Vec`/`Int` are not declared here.
    assert not {pair for pair in references if pair[1] in {"T", "Vec", "Int"}}
    assert all(node.get("source_file") for node in result["nodes"])


def test_receiver_typed_method_calls_bind_across_files(tmp_path):
    paths = _project(tmp_path, {
        "shapes.psm": """\
struct Point { x: Int }
impl Point {
    fn scaled(self, by: Int) -> Point { return self }
    fn origin() -> Point { return Point { x: 0 } }
}
fn norm(p: Point) -> Int { return p.x }
""",
        "use.psm": """\
import shapes

fn byParameter(p: Point) -> Point { return p.scaled(2) }
fn byAnnotation() -> Point { let q: Point = Point { x: 1 }
    return q.scaled(2) }
fn byConstruction() -> Point { let r = Point { x: 1 }
    return r.scaled(3) }
fn ufcs(p: Point) -> Int { return p.norm() }
fn qualified() -> Point { return Point.origin() }
fn unknown(items: Vec<Point>) -> Point { return items.first().scaled(2) }
""",
    })
    result = extract(paths, cache_root=tmp_path)
    calls = _edges(result, "calls")
    assert ("byParameter()", ".scaled()") in calls
    assert ("byAnnotation()", ".scaled()") in calls
    assert ("byConstruction()", ".scaled()") in calls
    assert ("ufcs()", "norm()") in calls  # recv.f() reaches a free function taking the type first
    assert ("qualified()", ".origin()") in calls
    # The receiver of `.scaled()` in `unknown` is a call result, so its type is not guessed.
    assert not {pair for pair in calls if pair[0] == "unknown()" and pair[1] == ".scaled()"}
    qualified = next(
        e for e in result["edges"]
        if e["relation"] == "calls" and _labels(result)[e["source"]] == "qualified()"
    )
    inferred = next(
        e for e in result["edges"]
        if e["relation"] == "calls" and _labels(result)[e["source"]] == "byParameter()"
    )
    assert qualified["confidence"] == "EXTRACTED" and inferred["confidence"] == "INFERRED"


def test_member_calls_are_not_bound_without_visibility_or_with_ambiguity(tmp_path):
    paths = _project(tmp_path, {
        "a.psm": "struct Box { n: Int }\nimpl Box { fn open(self) -> Int { return 1 } }\n",
        "b.psm": "import a\nstruct Crate { n: Int }\n",
        "c.psm": "import b\nfn run(x: Box) -> Int { return x.open() }\n",  # a.psm is not imported by c
        "d.psm": """\
struct Pair { n: Int }
trait One { fn pick(self) -> Int }
trait Two { fn pick(self) -> Int }
impl One for Pair { fn pick(self) -> Int { return 1 } }
impl Two for Pair { fn pick(self) -> Int { return 2 } }
fn go(p: Pair) -> Int { return p.pick() }
""",
    })
    result = extract(paths, cache_root=tmp_path)
    calls = _edges(result, "calls")
    assert ("run()", ".open()") not in calls  # imports are not transitive
    assert ("go()", ".pick()") not in calls  # two equally good candidates: no guess


def test_sample_fixture_goes_through_the_normal_extract_path():
    fixture = Path(__file__).parent / "fixtures" / "new_languages" / "sample.psm"
    result = extract([fixture], cache_root=fixture.parent)
    labels = {n["label"] for n in result["nodes"]}
    assert {"Point", "Shape", "Area", "Circle", "describe()", "measure()", ".scaled()",
            ".isOrigin()", "impl Area for Point", "impl Point"} <= labels
    assert "hidden()" not in labels
    assert len([n for n in result["nodes"] if n["label"] == "describe()"]) == 2
    edges_by_relation = {rel: _edges(result, rel) for rel in ("calls", "implements", "references")}
    assert ("measure()", ".area()") not in edges_by_relation["calls"]  # `T` is generic: not guessed
    assert ("main()", "describe()") not in edges_by_relation["calls"]  # overloaded: not guessed
    assert ("impl Area for Point", "Area") in edges_by_relation["implements"]
    assert ("main()", "Point") in edges_by_relation["references"]
    assert ("main()", ".scaled()") in edges_by_relation["calls"]  # p = Point { .. } types the receiver


def test_malformed_and_truncated_source_never_raises(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "new_languages" / "sample.psm"
    text = fixture.read_text(encoding="utf-8")
    path = tmp_path / "broken.psm"
    for cut in range(0, len(text), 5):
        for mutated in (text[:cut], text[:cut] + '"', text[:cut] + "/*", text[:cut] + "{(<"):
            path.write_text(mutated, encoding="utf-8")
            result = extract_prismio(path)
            assert isinstance(result["nodes"], list) and "error" not in result


def test_a_generic_parameter_shadows_a_declared_type_of_the_same_name(tmp_path):
    (path,) = _project(tmp_path, {"g.psm": """\
struct Item { n: Int }
fn keep<Item>(x: Item) -> Item { return x }
fn real(x: Item) -> Item { return x }
"""})
    result = extract([path], cache_root=tmp_path)
    references = _edges(result, "references")
    assert ("keep()", "Item") not in references  # `Item` here is the type parameter
    assert ("real()", "Item") in references
