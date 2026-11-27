from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _node_by_id(result: dict, nid: str) -> dict | None:
    return next((n for n in result["nodes"] if n.get("id") == nid), None)


def test_apex_cross_file_extends_resolves_to_real_def(tmp_path: Path):
    base = _write(
        tmp_path / "classes/DataLibrary.cls",
        "public virtual with sharing class DataLibrary {\n"
        "    public void retrieve() {}\n"
        "}\n",
    )
    sub = _write(
        tmp_path / "classes/MockDataLibrary.cls",
        "@IsTest\npublic class MockDataLibrary extends DataLibrary {}\n",
    )
    result = extract([base, sub], cache_root=tmp_path)

    extends = [e for e in result["edges"] if e["relation"] == "extends"]
    assert extends, "expected an extends edge"
    for e in extends:
        tgt = _node_by_id(result, e["target"])
        assert tgt is not None, f"extends target {e['target']} is not a node"
        assert Path(tgt["source_file"]).name == "DataLibrary.cls", (
            f"extends landed on {e['target']} instead of the real definition"
        )


def test_apex_one_base_referenced_twice_stays_one_node(tmp_path: Path):
    # The base class must not fragment into a node per referencing file, which is
    # what made "what depends on this class" come back empty.
    base = _write(tmp_path / "classes/Base.cls", "public with sharing class Base {}\n")
    one = _write(tmp_path / "classes/One.cls", "public class One extends Base {}\n")
    two = _write(tmp_path / "classes/Two.cls", "public class Two extends Base {}\n")
    result = extract([base, one, two], cache_root=tmp_path)

    bases = [n for n in result["nodes"] if n["label"] == "Base"]
    assert len(bases) == 1, f"Base fragmented into {len(bases)} nodes"
    targets = {e["target"] for e in result["edges"] if e["relation"] == "extends"}
    assert targets == {bases[0]["id"]}


def test_apex_unknown_base_does_not_bind_to_an_unrelated_type(tmp_path: Path):
    # Negative control: `Queueable` is defined nowhere in the corpus, so it must
    # stay a sourceless leaf rather than absorb the same-named local variable type
    # or any other node.
    job = _write(
        tmp_path / "classes/Job.cls",
        "public with sharing class Job implements Queueable {}\n",
    )
    other = _write(tmp_path / "classes/Other.cls", "public with sharing class Other {}\n")
    result = extract([job, other], cache_root=tmp_path)

    impl = [e for e in result["edges"] if e["relation"] == "implements"]
    assert len(impl) == 1
    tgt = _node_by_id(result, impl[0]["target"])
    assert tgt is not None and tgt["label"] == "Queueable"
    assert not tgt["source_file"], "an absent type must not claim a definition file"
