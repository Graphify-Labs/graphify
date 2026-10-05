"""INC-QML-44/45: shared resolved IDs cannot replace walked source owners."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
import graphify.extract as extraction
from graphify.export import to_json
from graphify.paths import load_node_link_graph
from tests.test_qt_final_incremental_parity import normalized
from tests.test_source_alias_provenance import directory_alias  # noqa: F401


SOURCE = b"def helper():\n    return 7\n\ndef caller():\n    return helper()\n"


def fixture(root, directory_alias):
    """Only actual discovered aliases share a physical source; no source is copied."""
    real = root / "real"
    real.mkdir()
    source = real / "member.py"
    source.write_bytes(SOURCE)
    first = directory_alias(root / "first", real) / source.name
    second = directory_alias(root / "second", real) / source.name
    return source, first, second


def graph(paths, root, cache):
    result = extraction.extract(paths, root=root, cache_root=cache, parallel=False)
    assert not result["failed_sources"] and not result["qml_failures"]
    return build_from_json(result, root=root, directed=True), result


def assert_owners(result, names):
    """File nodes and actual calls retain each owner's complete disjoint identity set."""
    for name in names:
        owned = {node["id"] for node in result["nodes"] if node.get("source_file") == name}
        prefix = name.removesuffix(".py").replace("/", "_")
        assert owned == {prefix, prefix + "_helper", prefix + "_caller"}
        calls = [edge for edge in result["edges"] if edge.get("source_file") == name
                 and edge.get("context") == "call"]
        assert calls and all(edge["source"] in owned and edge["target"] in owned for edge in calls)


@pytest.mark.parametrize("canonical_first", [True, False])
@pytest.mark.parametrize("relative", [True, False])
def test_req_qml020_ac02_primary_physical_owner_survives_both_batch_orders(
        tmp_path, directory_alias, monkeypatch, canonical_first, relative):
    """An appended alias cannot steal a supplied physical owner, even with relative inputs."""
    root = tmp_path.resolve()
    source, first, second = fixture(root, directory_alias)
    expected, _ = graph([source, first, second], root, root / "canonical-cache")
    paths = [source, first, second] if canonical_first else [first, second, source]
    monkeypatch.chdir(root)
    if relative:
        paths = [path.relative_to(root) for path in paths]
    actual, result = graph(paths, root, root / "ordered-cache")
    assert_owners(result, ["real/member.py", "first/member.py", "second/member.py"])
    assert normalized(actual) == normalized(expected)
    warm, _ = graph(paths, root, root / "ordered-cache")
    assert normalized(warm) == normalized(expected)
    output = root / "reloaded.json"
    assert to_json(warm, {}, str(output), force=True)
    assert normalized(load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))) == normalized(expected)
    assert source.read_bytes() == SOURCE


@pytest.mark.parametrize("reverse", [False, True])
def test_req_qml020_ac02_multiple_aliases_cannot_authorize_arbitrary_physical_target(
        tmp_path, directory_alias, reverse):
    """A shared import keeps its physical endpoint without inventing an accepted owner."""
    root = tmp_path.resolve()
    source, first, second = fixture(root, directory_alias)
    consumer = root / "consumer.py"
    consumer.write_bytes(b"import real.member\n\ndef use():\n    return real.member.helper()\n")
    paths = [consumer, second, first] if reverse else [consumer, first, second]
    actual, result = graph(paths, root, root / "cache")
    assert_owners(result, ["first/member.py", "second/member.py"])
    assert not {"real_member", "real_member_helper", "real_member_caller"} & {
        node["id"] for node in result["nodes"]}
    # Graph assembly retains its existing placeholder for a dangling import;
    # that placeholder carries no accepted source/declaration authority.
    assert actual.nodes["real_member"].get("source_file") != "real/member.py"
    imports = [edge for edge in result["edges"] if edge.get("relation") == "imports"
               and edge.get("source_file") == "consumer.py"]
    assert imports and all(edge["target"] == "real_member" for edge in imports)
    assert all(edge["target"] not in {"first_member", "second_member"} for edge in imports)
    assert not [edge for edge in result["edges"] if edge.get("source_file") == "consumer.py"
                and edge.get("context") == "call"]
    warm, _ = graph(paths, root, root / "cache")
    assert normalized(warm) == normalized(actual)
    assert source.read_bytes() == SOURCE
