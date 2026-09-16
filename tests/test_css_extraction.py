from __future__ import annotations

from pathlib import Path

from graphify.extract import extract, _file_node_id


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_css_import_resolves_to_target_file(tmp_path: Path):
    """A stylesheet's @import reaches the file it names, not a dangling stub."""
    target = _write(tmp_path / "styles/tokens.css", ":root { --brand: #123456; }\n")
    importer = _write(tmp_path / "styles/app.css", '@import "./tokens.css";\n')

    result = extract([target, importer], cache_root=tmp_path)

    import_edges = {
        (edge["source"], edge["target"])
        for edge in result["edges"]
        if edge["relation"] == "imports"
    }
    expected = (
        _file_node_id(Path("styles/app.css")),
        _file_node_id(Path("styles/tokens.css")),
    )
    assert expected in import_edges
