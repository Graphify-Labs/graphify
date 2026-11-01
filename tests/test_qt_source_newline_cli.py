"""INC-QML-103: explicit byte pairs retain all C#/CUDA/Metal source evidence."""
from __future__ import annotations

from copy import deepcopy
import json
import os
import subprocess
import sys

import pytest

from graphify.extract import _get_extractor
from tests.qt_source_newline_oracle import FIXTURE_NAMES, equivalent, links, node, validated_projection
from tests.test_graph_invariance import FIXTURES


@pytest.fixture(scope="module", params=[False, True], ids=["no_cluster", "clustered"])
def byte_builds(request, tmp_path_factory):
    """Build all four existing fixtures in both literal byte profiles through CLI."""
    base = tmp_path_factory.mktemp("source_newline_cli")
    results = []
    for profile, newline in (("lf", b"\n"), ("crlf", b"\r\n")):
        root = base / profile
        for relative in FIXTURE_NAMES:
            source = (FIXTURES / relative).read_bytes().replace(b"\r\n", b"\n")
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.replace(b"\n", newline))
        args = [sys.executable, "-m", "graphify", "update", str(root), "--force"]
        if not request.param:
            args.append("--no-cluster")
        run = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=120,
                             env=dict(os.environ, PYTHONIOENCODING="utf-8", GRAPHIFY_NO_TIPS="1",
                                      GRAPHIFY_NO_AUTO_REFRESH="1", PYTHONHASHSEED="0"))
        assert run.returncode == 0, (run.stdout + run.stderr)[-4000:]
        results.append((json.loads((root / "graphify-out/graph.json").read_text(encoding="utf-8")), root))
    return results


def test_req_qml022_ac02_source_byte_profiles_keep_cli_semantics(byte_builds):
    """Every physical span is checked before exact IDs, fields and topology agree."""
    (left, left_root), (right, right_root) = byte_builds
    equivalent(left, right, left_root, right_root)
    assert (left_root / "sample.cs").read_bytes().count(b"\r\n") == 0
    assert (right_root / "sample.cs").read_bytes().count(b"\r\n") > 0


@pytest.mark.parametrize("relative,count", list(zip(FIXTURE_NAMES, (1, 6, 4, 3))))
def test_req_qml022_ac02_all_direct_source_witnesses_keep_original_bytes(tmp_path, relative, count):
    """Direct producers retain all fourteen spans, including raw CUDA call proof."""
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    source = (FIXTURES / relative).read_bytes().replace(b"\r\n", b"\n")
    results = []
    for newline in (b"\n", b"\r\n"):
        path.write_bytes(source.replace(b"\n", newline))
        extractor = _get_extractor(path)
        assert extractor is not None
        result = extractor(path)
        projected, actual = validated_projection(result, tmp_path)
        assert actual == count and not result.get("error")
        if relative == "sample.cu":
            # These two direct-only witnesses are not exported graph metadata;
            # validate exact source ownership rather than claiming CLI coverage.
            (call,) = result["raw_calls"]
            proof = call["cpp_free_call"]
            raw = path.read_bytes()
            for key, expected in (
                ("span", b"dot(v, v)"),
                ("caller_span", b"float host_norm(const Vec3& v) {\n    return dot(v, v);\n}"),
            ):
                span = proof[key]
                assert raw[span["start_byte"]:span["end_byte"]].replace(b"\r\n", b"\n") == expected
            assert call["callee"] == "dot" and proof["context_kind"] == "free"
        results.append(projected)
    # Existing CUDA/Metal partial-parse diagnostics stay part of the comparison.
    assert results[0] == results[1]


@pytest.mark.parametrize("corruption", [
    "span", "consistent_span", "semantic_role", "identity_permutation",
    "relation", "endpoint", "symmetric_missing_fact", "duplicate_edge",
])
def test_req_qml022_ac06_source_newline_oracle_rejects_corruption(byte_builds, corruption):
    """Physical allowances cannot hide wrong spans, identities, roles or omissions."""
    (accepted, root), _ = byte_builds
    reference, changed = deepcopy(accepted), deepcopy(accepted)
    field = node(changed, "sample.cs", "_client", "csharp_member")
    if corruption in {"span", "consistent_span"}:
        span = field["metadata"]["csharp_member"]["span"]
        span["start_byte"] += 1
        if corruption == "consistent_span":
            span["start_column"] += 1
    elif corruption == "semantic_role":
        field["metadata"]["csharp_member"]["kind"] = "property"
    elif corruption == "identity_permutation":
        second = node(changed, "sample.cu", "host_norm()")
        replacements = {field["id"]: second["id"], second["id"]: field["id"]}

        def swap(value):
            if isinstance(value, dict):
                return {key: swap(child) for key, child in value.items()}
            if isinstance(value, list):
                return [swap(child) for child in value]
            return replacements.get(value, value) if isinstance(value, str) else value

        changed = swap(changed)
    elif corruption in {"relation", "endpoint"}:
        edge = next(edge for edge in links(changed) if edge["relation"] == "calls")
        if corruption == "relation":
            edge["relation"] = "references"
        else:
            edge["target"] = field["id"]
    elif corruption == "duplicate_edge":
        links(changed).append(deepcopy(links(changed)[0]))
    else:
        for data in (reference, changed):
            missing = node(data, "sample.cs", "_client")
            data["nodes"].remove(missing)
            links(data)[:] = [edge for edge in links(data)
                             if missing["id"] not in (edge["source"], edge["target"])]
    with pytest.raises(AssertionError):
        equivalent(reference, changed, root, root)
