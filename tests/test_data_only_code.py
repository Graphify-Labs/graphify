"""Data-shaped JavaScript must not look like complete structural coverage."""
import json

import pytest

from graphify.build import build_from_json
from graphify.extract import extract
from graphify.report import generate


DATA_FORMS = [
    "const BANK = [{question: 'why?', answer: 'because'}];",
    "var BANK = [1, 2];",
    "window.BANK = [1, 2];",
    "module.exports = [1, 2];",
    "export default [1, 2];",
    "export const BANK = [1, 2];",
    "const namespace = {BANK: [1, 2]};",
]


def report_for(result):
    graph = build_from_json(json.loads(json.dumps(result)))
    return generate(graph, {}, {}, {}, [], [], {"total_files": 1, "total_words": 0}, {}, ".")


@pytest.mark.parametrize("source", DATA_FORMS)
def test_data_forms_are_visible_in_extraction_and_persisted_report(tmp_path, source):
    p = tmp_path / "bank.js"
    p.write_text(source, encoding="utf-8")
    result = extract([p], root=tmp_path, cache_root=tmp_path, parallel=False)
    file_node = next(n for n in result["nodes"] if n["label"] == "bank.js")
    assert file_node["_no_structural_symbols"] is True
    assert file_node["_source_bytes"] == len(source.encode("utf-8"))
    assert result["failed_sources"] == []
    report = report_for(result)
    assert "## Files without structural symbols" in report
    assert "bank.js" in report and f"{len(source)} bytes" in report
    assert "may contain data" in report
    assert "not extracted by AST" in report


@pytest.mark.parametrize("source", [
    "function foo() {}", "class Foo {}", "const foo = () => 1;",
    "import {foo} from './foo';", "const BANK = loadData();",
    "export {foo} from './foo';", "const obj = {foo() {return 1;}};",
])
def test_structural_js_is_not_reported_as_data_only(tmp_path, source):
    p = tmp_path / "code.js"
    p.write_text(source)
    result = extract([p], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not any(n.get("_no_structural_symbols") for n in result["nodes"])
    assert "## Files without structural symbols" not in report_for(result)


def test_report_bounds_list_and_orders_by_size(tmp_path):
    paths = []
    for i in range(8):
        p = tmp_path / f"bank{i}.js"
        p.write_text("window.BANK = [" + ",".join(["1"] * (i + 1)) + "];" )
        paths.append(p)
    r = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    section = report_for(r).split("## Files without structural symbols", 1)[1].split("## ", 1)[0]
    assert "8 JavaScript" in section
    assert section.count(" bytes") == 5
    assert section.index("bank7.js") < section.index("bank6.js")
    assert "3 more" in section


def test_syntax_errors_are_not_classified_as_data_only(tmp_path):
    p = tmp_path / "broken.js"
    p.write_text("function foo( {")
    r = extract([p], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not any(n.get("_no_structural_symbols") for n in r["nodes"])


@pytest.mark.parametrize("extension", [".js", ".jsx", ".mjs", ".cjs"])
def test_byte_sizes_are_utf8_and_report_survives_source_removal(tmp_path, extension):
    p = tmp_path / ("bank" + extension)
    source = 'window.BANK = ["caf' + chr(233) + '"];'
    p.write_text(source, encoding="utf-8")
    r = extract([p], root=tmp_path, cache_root=tmp_path, parallel=False)
    expected = len(source.encode("utf-8"))
    assert next(n for n in r["nodes"] if n.get("_no_structural_symbols"))["_source_bytes"] == expected
    p.unlink()
    assert f"{expected} bytes" in report_for(r)


def test_incremental_replacement_removes_old_coverage_notice(tmp_path):
    from graphify.build import merge_raw_extraction
    p = tmp_path / "bank.js"
    p.write_text("window.BANK = [1];")
    old = extract([p], root=tmp_path, cache_root=tmp_path, parallel=False)
    p.write_text("function answer() {return 42;}")
    fresh = extract([p], root=tmp_path, cache_root=tmp_path, parallel=False)
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(old), encoding="utf-8")
    combined = merge_raw_extraction(fresh, graph_path, root=str(tmp_path))
    assert "## Files without structural symbols" not in report_for(combined)


def test_report_preserves_backticks_in_source_filename(tmp_path):
    p = tmp_path / "bank`draft.js"
    source = "window.BANK = [1];"
    p.write_text(source, encoding="utf-8")
    r = extract([p], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert "- `` bank`draft.js ``" in report_for(r)


@pytest.mark.parametrize("source", ["", " \n\t"])
def test_empty_js_does_not_add_coverage_noise(tmp_path, source):
    p = tmp_path / "empty.js"
    p.write_text(source, encoding="utf-8")
    r = extract([p], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not any(n.get("_no_structural_symbols") for n in r["nodes"])


@pytest.mark.parametrize("encoding", ["utf-16", "cp1252"])
def test_encoded_data_keeps_upstream_decoding_and_disk_size(tmp_path, encoding):
    p = tmp_path / "bank.js"
    raw = 'window.BANK = ["café"];'.encode(encoding)
    p.write_bytes(raw)
    r = extract([p], root=tmp_path, cache_root=tmp_path, parallel=False)
    file_node = next(n for n in r["nodes"] if n.get("_no_structural_symbols"))
    assert file_node["_source_bytes"] == len(raw)
    assert not r.get("failed_sources")
