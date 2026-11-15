"""Anonymous Rust constants must not replace their owning file node."""

from graphify.build import build_from_json
from graphify.extract import extract


def test_anonymous_constants_preserve_file_identity(tmp_path):
    source = tmp_path / "codec.rs"
    source.write_text(
        "pub const WIDTH: usize = 8;\n"
        "const _: () = assert!(WIDTH == 8);\n"
        "const _: () = ();\n"
        "static READY: bool = true;\n"
        "pub fn encode() {}\n",
        encoding="utf-8",
    )
    extracted = extract([source], root=tmp_path, cache_root=tmp_path / "cache")
    graph = build_from_json(extracted, root=tmp_path, directed=False)

    assert len({node["id"] for node in extracted["nodes"]}) == len(extracted["nodes"])
    labels = {data["label"] for _, data in graph.nodes(data=True)}
    assert {"codec.rs", "WIDTH", "READY", "encode()"} <= labels
    assert "_" not in labels
    assert all(source != target for source, target in graph.edges())
