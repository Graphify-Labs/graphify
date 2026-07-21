from pathlib import Path

import pytest

from graphify.build import build_from_extraction
from graphify.extract import extract


def _write(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _import_self_loops(result: dict) -> list[dict]:
    return [
        edge
        for edge in result["edges"]
        if edge.get("relation") in {"imports", "imports_from", "re_exports"}
        and edge.get("source") == edge.get("target")
    ]


def _built_import_self_loops(result: dict) -> list[tuple[str, str, dict]]:
    graph = build_from_extraction(result, directed=True)
    return [
        (edge.source, edge.target, dict(edge.attributes))
        for edge in graph.edges
        if edge.source == edge.target
        and edge.attributes.get("relation") in {"imports", "imports_from", "re_exports"}
    ]


@pytest.mark.parametrize(
    ("relative_path", "source"),
    [
        ("src/contracting/stdlib/builtins.py", "import builtins\n"),
        ("playground/services/contracting.py", "from contracting import constants\n"),
    ],
)
def test_python_external_import_matching_current_basename_has_no_self_loop(
    tmp_path: Path,
    relative_path: str,
    source: str,
) -> None:
    module = _write(tmp_path / relative_path, source)

    result = extract([module], cache_root=tmp_path, parallel=False)

    assert _import_self_loops(result) == []
    assert _built_import_self_loops(result) == []


@pytest.mark.parametrize(
    ("relative_path", "source"),
    [
        (
            "packages/compiler/src/fixture.rs",
            "mod tests { use crate::fixture::Fixture; }\n",
        ),
        (
            "packages/zk/src/poseidon.rs",
            "use ark_crypto_primitives::sponge::poseidon::{PoseidonConfig, PoseidonSponge};\n",
        ),
    ],
)
def test_rust_import_matching_current_basename_has_no_self_loop(
    tmp_path: Path,
    relative_path: str,
    source: str,
) -> None:
    module = _write(tmp_path / relative_path, source)

    result = extract([module], cache_root=tmp_path, parallel=False)

    assert _import_self_loops(result) == []
    assert _built_import_self_loops(result) == []


def test_recursive_call_self_loop_is_preserved() -> None:
    result = {
        "nodes": [
            {
                "id": "module_recurse",
                "label": "recurse()",
                "file_type": "code",
                "source_file": "module.py",
                "source_location": "L1",
                "_origin": "ast",
            }
        ],
        "edges": [
            {
                "source": "module_recurse",
                "target": "module_recurse",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "module.py",
                "source_location": "L2",
            }
        ],
    }

    graph = build_from_extraction(result, directed=True)

    assert any(
        edge.source == "module_recurse"
        and edge.target == "module_recurse"
        and edge.attributes.get("relation") == "calls"
        for edge in graph.edges
    )
