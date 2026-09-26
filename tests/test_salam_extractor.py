"""Extraction coverage for Salam (.salam) source, English and Persian."""
from __future__ import annotations

from pathlib import Path

from graphify.detect import CODE_EXTENSIONS, classify_file, FileType
from graphify.extract import extract, extract_salam
from graphify.extractors import LANGUAGE_EXTRACTORS

FIXTURES = Path(__file__).parent / "fixtures"


def _labels(result: dict) -> dict[str, str]:
    return {node["id"]: node["label"] for node in result["nodes"]}


def _edges(result: dict, relation: str, context: str | None = None) -> set[tuple[str, str]]:
    labels = _labels(result)
    return {
        (labels.get(e["source"], e["source"]), labels.get(e["target"], e["target"]))
        for e in result["edges"]
        if e["relation"] == relation and (context is None or e.get("context") == context)
    }


def _kinds(result: dict) -> dict[str, str]:
    return {n["label"]: n["metadata"]["kind"] for n in result["nodes"] if n.get("metadata")}


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_registry_and_detection():
    assert LANGUAGE_EXTRACTORS["salam"] is extract_salam
    assert ".salam" in CODE_EXTENSIONS
    assert classify_file(Path("app.salam")) == FileType.CODE


def test_english_declarations():
    result = extract_salam(FIXTURES / "sample.salam")
    kinds = _kinds(result)
    assert kinds["scale()"] == "function"
    assert kinds["classify()"] == "function"
    assert kinds["main()"] == "function"
    assert kinds["Circle"] == "struct"
    assert kinds["Shape"] == "interface"
    assert kinds["Kind"] == "enum"
    assert kinds["Id"] == "type_alias"
    assert kinds["MAX_SIDES"] == "constant"
    assert kinds["sqrt()"] == "extern_function"
    assert kinds["printf()"] == "extern_function"
    assert kinds["m (native library)"] == "native_library"
    assert kinds["impl Shape on int"] == "impl"
    assert kinds["shapes (package)"] == "package"

    methods = _edges(result, "method")
    assert {("Circle", ".area()"), ("Circle", ".name()"), ("Circle", ".describe()")} <= methods
    assert ("Shape", ".area()") in methods
    assert ("impl Shape on int", ".name()") in methods

    enum = next(n for n in result["nodes"] if n["label"] == "Kind")
    assert enum["metadata"]["members"] == ["Round", "Square", "Triangle"]


def test_english_edges():
    result = extract_salam(FIXTURES / "sample.salam")
    calls = _edges(result, "calls")
    assert (".describe()", ".name()") in calls
    assert ("main()", ".describe()") in calls
    assert ("main()", "scale()") in calls
    assert ("main()", "classify()") in calls
    refs = _edges(result, "references")
    assert ("Circle", "Kind") in refs
    assert ("scale()", "Circle") in refs
    assert ("main()", "Circle") in refs
    assert ("impl Shape on int", "Shape") in _edges(result, "implements")
    assert ("sample.salam", "m (native library)") in _edges(result, "links")


def test_annotations_become_aliases():
    result = extract_salam(FIXTURES / "sample.salam")
    circle = next(n for n in result["nodes"] if n["label"] == "Circle")
    assert circle["metadata"]["aliases"] == {"en": "Circle", "fa": "دایره"}


def test_persian_keywords_old_and_new(tmp_path):
    fa = extract_salam(FIXTURES / "sample_fa.salam")
    kinds = _kinds(fa)
    assert kinds["نقطه"] == "struct"
    assert kinds["جمع()"] == "function"
    assert kinds["آغازین()"] == "function"
    assert ("نقطه", ".مجموع()") in _edges(fa, "method")
    assert ("آغازین()", "جمع()") in _edges(fa, "calls")

    new = _write(
        tmp_path,
        "new.salam",
        "روال جمع(الف: صحیح, ب: صحیح): صحیح:\n"
        "    برگشت الف + ب\n"
        "پایان\n"
        "\n"
        "روال ریشه:\n"
        "    تکرار 0 تا 100 هر 10 با i:\n"
        "        اگر i > 50:\n"
        "            سرچاپ جمع(i, 1)\n"
        "        پایان\n"
        "    پایان\n"
        "پایان\n"
        "\n"
        "جداشمار رنگ: قرمز, آبی پایان\n"
        "گونه شناسه = صحیح\n",
    )
    result = extract_salam(new)
    kinds = _kinds(result)
    assert kinds["ریشه()"] == "function"
    assert kinds["رنگ"] == "enum"
    assert kinds["شناسه"] == "type_alias"
    assert ("ریشه()", "جمع()") in _edges(result, "calls")
    contained = _edges(result, "contains")
    assert ("new.salam", "ریشه()") in contained


def test_block_nesting_keeps_later_definitions_top_level(tmp_path):
    source = _write(
        tmp_path,
        "blocks.salam",
        "func first(n: int): int:\n"
        "    if n < 0:\n"
        "        ret 0\n"
        "    else if n == 0:\n"
        "        ret 1\n"
        "    else:\n"
        "        ret 2\n"
        "    end\n"
        "end\n"
        "\n"
        "func second(word: str): int:\n"
        "    r := match word:\n"
        '        "a": ret 1 end\n'
        '        "b": ret 2 end\n'
        "        else: ret 3 end\n"
        "    end\n"
        "    cb := (x: int): y := x + 1 ret y end\n"
        "    ret r\n"
        "end\n"
        "\n"
        "struct V:\n"
        "    pub x: int = 0\n"
        "    pub func operator +(o: V): V: ret V { x = this.x + o.x } end\n"
        "end\n"
        "\n"
        "func third: end\n",
    )
    result = extract_salam(source)
    contained = _edges(result, "contains")
    for name in ("first()", "second()", "V", "third()"):
        assert ("blocks.salam", name) in contained, name
    assert ("V", ".operator+()") in _edges(result, "method")


def test_multiword_names_and_overloads(tmp_path):
    source = _write(
        tmp_path,
        "words.salam",
        "func make counter(): int: ret 0 end\n"
        "func add(a: int): int: ret a end\n"
        "func add(a: int, b: int): int: ret a + b end\n"
        "func main:\n"
        "    c := make counter()\n"
        "    println add(1, 2), add(1)\n"
        "end\n",
    )
    result = extract_salam(source)
    labels = [n["label"] for n in result["nodes"]]
    assert "make counter()" in labels
    assert labels.count("add()") == 2
    calls = _edges(result, "calls")
    assert ("main()", "make counter()") in calls
    assert ("main()", "add()") in calls
    ids = [n["id"] for n in result["nodes"]]
    assert len(ids) == len(set(ids))


def test_layout_blocks_and_components(tmp_path):
    source = _write(
        tmp_path,
        "page.salam",
        "component Card(title):\n"
        "    box: class = \"card\" heading: content = title end end\n"
        "end\n"
        "\n"
        "layout:\n"
        "    title = \"Demo\"\n"
        "    Card: title = \"Hi\" end\n"
        "    input: id = \"n\" border inline end = \"1px\" end\n"
        "end\n"
        "\n"
        "func after: end\n",
    )
    result = extract_salam(source)
    kinds = _kinds(result)
    assert kinds["Card"] == "component"
    assert kinds["layout"] == "layout"
    assert ("page.salam", "after()") in _edges(result, "contains")
    assert ("layout", "Card") in _edges(result, "references")


def test_cross_file_calls_types_and_persian_aliases(tmp_path):
    _write(
        tmp_path,
        "std/mathx/mathx.salam",
        '@fa "ریاضی"\n'
        "package mathx\n"
        "\n"
        '@en "Square"\n'
        '@fa "مربع"\n'
        "pub func Square(x: int): int:\n"
        "    ret x * x\n"
        "end\n",
    )
    _write(
        tmp_path,
        "app/shapes.salam",
        "interface Shape:\n"
        "    func area(): f64\n"
        "end\n"
        "\n"
        "pub struct Circle:\n"
        "    pub r: f64 = 0.0\n"
        "    pub func describe(): str: ret \"c\" end\n"
        "end\n",
    )
    _write(
        tmp_path,
        "app/main.salam",
        "import mathx\n"
        "\n"
        "impl Shape on Circle:\n"
        "    func area(): f64: ret 1.0 end\n"
        "end\n"
        "\n"
        "func main:\n"
        "    println mathx.Square(3)\n"
        "    mut c := Circle { r = 1.0 }\n"
        "    println c.describe()\n"
        "end\n",
    )
    _write(
        tmp_path,
        "app/fa.salam",
        "فراخوانی ریاضی\n"
        "\n"
        "روال ریشه:\n"
        "    چاپ ریاضی.مربع(3)\n"
        "پایان\n",
    )
    paths = sorted(tmp_path.rglob("*.salam"))
    result = extract(paths, cache_root=tmp_path)

    calls = _edges(result, "calls")
    assert ("main()", "Square()") in calls
    assert ("ریشه()", "Square()") in calls
    assert ("main()", ".describe()") in calls
    assert ("impl Shape on Circle", "Shape") in _edges(result, "implements")
    assert ("impl Shape on Circle", "Circle") in _edges(result, "references")
    imports = _edges(result, "imports_from")
    assert ("main.salam", "mathx (package)") in imports
    assert ("fa.salam", "mathx (package)") in imports

    package_call = next(
        e for e in result["edges"] if e.get("context") == "package_call"
    )
    assert package_call["confidence"] == "EXTRACTED"


def test_string_import_binds_alias_to_file(tmp_path):
    _write(tmp_path, "lib.salam", "pub func Twice(x: int): int: ret x * 2 end\n")
    _write(
        tmp_path,
        "main.salam",
        'import u "lib.salam"\n\nfunc main:\n    println u.Twice(4)\nend\n',
    )
    result = extract(sorted(tmp_path.glob("*.salam")), cache_root=tmp_path)
    assert ("main()", "Twice()") in _edges(result, "calls")
    assert ("main.salam", "lib.salam") in _edges(result, "imports_from")


def test_unresolved_references_leave_no_schema_errors(tmp_path):
    from graphify.validate import validate_extraction

    _write(
        tmp_path,
        "solo.salam",
        "import str\npackage util\n\nstruct Box:\n    pub m: sync.Mutex = sync.Mutex {}\nend\n",
    )
    result = extract([tmp_path / "solo.salam"], cache_root=tmp_path)
    errors = [e for e in validate_extraction(result) if "does not match any node id" not in e]
    assert errors == []


def test_unreadable_file_reports_error(tmp_path):
    result = extract_salam(tmp_path / "missing.salam")
    assert result["nodes"] == [] and "error" in result
