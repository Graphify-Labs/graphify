"""TypeScript import types must not become runtime dependencies (#4992)."""
import pytest

from graphify.extract import extract_js


@pytest.mark.parametrize("suffix", [".ts", ".tsx", ".mts", ".cts"])
@pytest.mark.parametrize("source", [
    "export function accept(page: import('@playwright/test').Page): void {}",
    "function f(): import('@playwright/test').Page { throw 1; }",
    "type Page = import('@playwright/test').Page;",
    "type Module = typeof import('@playwright/test');",
    "interface Options { page: import('@playwright/test').Page }",
    "function f<T extends import('@playwright/test').Page>() {}",
    "function f<T = import('@playwright/test').Page>() {}",
    "function f() { const page: import('@playwright/test').Page = undefined; }",
    "f<import('@playwright/test').Page>();\nfunction after() {}",
    "f<typeof import('@playwright/test')>();\nfunction after() {}",
])
def test_type_import_does_not_emit_runtime_edge_or_package_path(tmp_path, suffix, source):
    path = tmp_path / f"example{suffix}"
    path.write_text(source, encoding="utf-8")

    result = extract_js(path)

    assert "error" not in result
    assert not any(edge["relation"] == "dynamic_import" or edge.get("deferred")
                   for edge in result["edges"])
    assert not any(node.get("source_file") == "@playwright/test"
                   for node in result["nodes"])
    if "function after" in source:
        assert any(node["label"] == "after()" for node in result["nodes"])


@pytest.mark.parametrize("suffix", [".ts", ".tsx", ".mts", ".cts"])
@pytest.mark.parametrize("prefix", ["", "// caf\u00e9\r\n", "\ufeff// caf\u00e9\r\n"])
def test_runtime_import_survives_type_import_of_same_package(tmp_path, suffix, prefix):
    path = tmp_path / f"example{suffix}"
    source = (prefix
              + "export function load(page: import('@playwright/test').Page) {\r\n"
              + "  return import('@playwright/test');\r\n"
              + "}\r\n")
    path.write_bytes(source.encode("utf-8"))

    result = extract_js(path)

    assert "error" not in result
    runtime_edges = [edge for edge in result["edges"]
                     if edge["relation"] == "dynamic_import" or edge.get("deferred")]
    assert runtime_edges
    assert any(edge.get("deferred") and edge.get("source_location")
               == ("L2" if not prefix else "L3") for edge in runtime_edges)


@pytest.mark.parametrize("suffix", [".js", ".ts", ".tsx"])
def test_runtime_comparison_import_is_not_a_type_import(tmp_path, suffix):
    path = tmp_path / f"example{suffix}"
    path.write_text('const x = a < b, import("runtime") > (d);\n', encoding="utf-8")

    result = extract_js(path)

    assert "error" not in result
    assert any(edge["relation"] == "dynamic_import" or edge.get("deferred")
               for edge in result["edges"])
