"""#4334: a forward-referenced class named after its file must not swallow the file node."""
from pathlib import Path

from graphify.extract import extract

WIDGET = """from __future__ import annotations

class Helper:
    def make(self, w: Widget) -> None:
        w.draw()

class Widget:
    def draw(self):
        return 1
"""

APP = """from widget import Widget

def use(w: Widget):
    w.draw()
"""


def _extract(tmp_path: Path, files: dict[str, str]):
    paths = []
    for name, src in files.items():
        p = tmp_path / name
        p.write_text(src)
        paths.append(p)
    result = extract(paths, cache_root=tmp_path, root=tmp_path, parallel=False)
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    edges = {(labels.get(e["source"]), e["relation"], labels.get(e["target"])) for e in result["edges"]}
    return result, labels, edges


def _check(result, labels, edges):
    file_nodes = [n for n in result["nodes"] if n["label"] == "widget.py"]
    assert len(file_nodes) == 1, labels
    assert ("widget.py", "contains", "Widget") in edges
    assert ("widget.py", "contains", "Helper") in edges
    assert ("Widget", "contains", "Widget") not in edges
    assert ("Widget", "contains", "Helper") not in edges
    assert (".make()", "calls", ".draw()") in edges


def test_forward_ref_keeps_file_node_single_file(tmp_path):
    _check(*_extract(tmp_path, {"widget.py": WIDGET}))


def test_forward_ref_keeps_file_node_with_importer(tmp_path):
    result, labels, edges = _extract(tmp_path, {"widget.py": WIDGET, "app.py": APP})
    _check(result, labels, edges)
    assert ("app.py", "imports_from", "widget.py") in edges
    assert ("app.py", "imports_from", "Widget") not in edges


def test_imported_same_name_in_subdirectory_keeps_cross_file_rewire(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    result, labels, edges = _extract(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/base.py": "class Widget:\n    def draw(self):\n        return 1\n",
        "pkg/widget.py": "from .base import Widget\n\ndef use(w: Widget):\n    w.draw()\n",
    })
    ids = {n["id"] for n in result["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in result["edges"])
    base_widget = next(n["id"] for n in result["nodes"]
                       if n["label"] == "Widget" and n["source_file"].endswith("base.py"))
    use = next(n["id"] for n in result["nodes"] if n["label"] == "use()")
    assert any(e["source"] == use and e["target"] == base_widget for e in result["edges"])
    assert [n for n in result["nodes"] if n["label"] == "Widget"] == [
        n for n in result["nodes"] if n["id"] == base_widget
    ]


def test_same_named_function_is_not_a_type_reference_target(tmp_path):
    src = "class Helper:\n    def make(self, w: Widget) -> None:\n        w.draw()\n\ndef widget():\n    return 1\n"
    result, labels, edges = _extract(tmp_path, {"widget.py": src})
    assert (".make()", "references", "widget()") not in edges
    assert (".make()", "uses", "widget()") not in edges
