"""Swift/Foundation/SwiftUI builtins must not become god nodes or bind to user symbols.

#2147: `_LANGUAGE_BUILTIN_GLOBALS` and `_BUILTIN_NOISE_LABELS` covered only
JS/TS and Python, so on Swift codebases framework types (`Foundation`,
`NSLock`, `View`, `Data`, `Sendable`, ...) ranked as god nodes and the Swift
member-call resolver could bind a builtin-typed receiver (`let d: Data`) to a
same-named user symbol in another file — the same phantom-edge shape #1726
fixed for TypeScript.
"""
import networkx as nx
import pytest

from graphify.analyze import god_nodes
from graphify.extract import extract


def _labels_by_id(r):
    return {n["id"]: n.get("label") for n in r["nodes"]}


@pytest.mark.parametrize("builtin_label", [
    "Foundation", "SwiftUI", "NSLock", "Data", "View", "Sendable", "Codable",
    "DispatchQueue", "Color",
])
def test_god_nodes_excludes_swift_builtin_labels(builtin_label: str) -> None:
    """Swift framework symbols must be filtered from god_nodes output.

    Constructs a graph where the builtin-labelled node has the highest degree
    (the #2147 report shape: `Foundation` at 105 edges, `NSLock` at 102) and a
    real project abstraction has lower degree. The builtin must be excluded and
    the project symbol kept.

    Args:
        builtin_label: The Swift/Foundation/SwiftUI label to test (parametrized).
    """
    G = nx.Graph()
    G.add_node(
        "real_node",
        label="AudioStreamer",
        source_file="Sources/AudioStreamer.swift",
        file_type="code",
        source_location="L1",
    )
    G.add_node(
        "builtin_node",
        label=builtin_label,
        source_file="",
        file_type="code",
        source_location="",
    )
    for i in range(20):
        peer = f"user_type_{i}"
        G.add_node(
            peer,
            label=f"Feature{i}",
            source_file=f"Sources/Feature{i}.swift",
            file_type="code",
            source_location="L1",
        )
        G.add_edge(
            peer,
            "builtin_node",
            relation="references",
            confidence="EXTRACTED",
            source_file=f"Sources/Feature{i}.swift",
            weight=1.0,
        )
    G.add_edge(
        "real_node",
        "user_type_0",
        relation="calls",
        confidence="EXTRACTED",
        source_file="Sources/AudioStreamer.swift",
        weight=1.0,
    )

    result = god_nodes(G, top_n=10)
    result_ids = [r["id"] for r in result]

    assert "builtin_node" not in result_ids, (
        f"god_nodes() should filter Swift builtin '{builtin_label}' "
        f"but it appeared in the result: {result}"
    )
    assert "real_node" in result_ids, (
        f"god_nodes() should include project symbol 'AudioStreamer' "
        f"but it was absent: {result}"
    )


def test_swift_builtin_receiver_does_not_bind_to_user_symbol(tmp_path):
    # #2147 (same shape as #1726 for TS): a receiver typed with a builtin
    # (`let payload: Data`) must not have its member calls bound to a user type
    # that happens to be named `Data` in another file.
    (tmp_path / "Model.swift").write_text(
        "class Data {\n"
        "    func append(_ s: String) {}\n"
        "}\n")
    (tmp_path / "Uploader.swift").write_text(
        "class Uploader {\n"
        "    let payload: Data = Data()\n"
        "    func send() {\n"
        "        payload.append(\"x\")\n"
        "    }\n"
        "}\n")
    r = extract(sorted(tmp_path.glob("*.swift")), cache_root=tmp_path, parallel=False)
    lbl = _labels_by_id(r)
    by_id = {n["id"]: n for n in r["nodes"]}
    data_ids = [n["id"] for n in r["nodes"]
                if n.get("label") == "Data"
                and str(n.get("source_file", "")).endswith("Model.swift")]
    assert data_ids, "the user class Data must still exist as a node"
    for e in r["edges"]:
        if e.get("target") in data_ids and e.get("relation") in ("calls", "references") \
                and e.get("context") == "call":
            src_sf = str(by_id.get(e["source"], {}).get("source_file", ""))
            assert not src_sf.endswith("Uploader.swift"), (
                f"builtin-typed receiver bound to user Data: "
                f"{lbl.get(e['source'])!r} -> Data ({e})"
            )


def test_swift_user_receiver_type_still_resolves(tmp_path):
    # Guard must be a no-op for genuine user types: a member call on a
    # user-typed property still resolves cross-file (#1356 inference table).
    (tmp_path / "Engine.swift").write_text(
        "class AudioEngine {\n"
        "    func play() {}\n"
        "}\n")
    (tmp_path / "Player.swift").write_text(
        "class Player {\n"
        "    let engine: AudioEngine = AudioEngine()\n"
        "    func start() {\n"
        "        engine.play()\n"
        "    }\n"
        "}\n")
    r = extract(sorted(tmp_path.glob("*.swift")), cache_root=tmp_path, parallel=False)
    lbl = _labels_by_id(r)
    resolved = {
        (lbl.get(e["source"]), lbl.get(e["target"]))
        for e in r["edges"]
        if e.get("context") == "call" and "play" in str(lbl.get(e.get("target"), "")).lower()
    }
    assert resolved, "user-typed member call must still resolve cross-file"
