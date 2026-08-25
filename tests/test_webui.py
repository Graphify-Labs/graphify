from pathlib import Path
from graphify.extract import extract

def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path

def test_webui_css(tmp_path):
    f = _write(tmp_path / "styles.css", ".a .b { color: var(--t) }")
    res = extract([f])
    
    labels = {n["label"] for n in res.get("nodes", [])}
    assert ".a" in labels
    assert ".b" in labels
    assert "--t" in labels
    
    edges = {(e["source"], e["target"], e["relation"]) for e in res.get("edges", [])}
    
    a_id = next(n["id"] for n in res["nodes"] if n["label"] == ".a")
    t_id = next(n["id"] for n in res["nodes"] if n["label"] == "--t")
    
    assert (a_id, t_id, "uses_token") in edges

def test_webui_html(tmp_path):
    f = _write(tmp_path / "index.html", '<div id="x" class="a b">')
    res = extract([f])
    
    labels = {n["label"] for n in res.get("nodes", [])}
    assert "#x" in labels
    assert ".a" in labels
    assert ".b" in labels

def test_webui_shared_nodes(tmp_path):
    f_css = _write(tmp_path / "styles.css", ".my-class { }")
    f_html = _write(tmp_path / "index.html", '<div class="my-class"></div>')
    res = extract([f_css, f_html])
    
    my_class_nodes = [n for n in res.get("nodes", []) if n["label"] == ".my-class"]
    assert len(my_class_nodes) >= 2, "Should have been extracted from both files"
    
    # Check that they share the exact same ID so they merge in the final graph
    ids = {n["id"] for n in my_class_nodes}
    assert len(ids) == 1, "Should be deduplicated into one node ID"

def test_webui_js_touches_ui(tmp_path):
    f_js = _write(tmp_path / "app.js", "\nfunction init() {\n    document.querySelector('.my-class');\n}")
    res = extract([f_js])
    
    labels = {n["label"] for n in res.get("nodes", [])}
    assert ".my-class" in labels
    
    fn_node = next(n for n in res["nodes"] if n["label"] == "init()")
    cls_node = next(n for n in res["nodes"] if n["label"] == ".my-class")
    
    edges = {(e["source"], e["target"], e["relation"]) for e in res.get("edges", [])}
    assert (fn_node["id"], cls_node["id"], "touches_ui") in edges
