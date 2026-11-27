from pathlib import Path

import pytest

from graphify.extract import extract


@pytest.mark.parametrize("split_declaration", [False, True])
def test_same_named_go_structs_resolve_fields_in_their_own_package(
    tmp_path: Path, split_declaration: bool,
) -> None:
    (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.22\n", encoding="utf-8")
    for package in ("alpha", "beta"):
        directory = tmp_path / package
        directory.mkdir()
        declarations = (
            f"package {package}\n"
            "type Repository interface { GetByID() int }\n"
            "type Service struct { repo Repository }\n"
        )
        method = "func (s *Service) Run() int { return s.repo.GetByID() }\n"
        if split_declaration:
            (directory / "types.go").write_text(declarations, encoding="utf-8")
            (directory / "run.go").write_text(f"package {package}\n{method}", encoding="utf-8")
        else:
            (directory / "service.go").write_text(declarations + method, encoding="utf-8")

    result = extract(
        sorted(tmp_path.rglob("*.go")), root=tmp_path, cache_root=tmp_path / "cache", parallel=False,
    )
    nodes = {node["id"]: node for node in result["nodes"]}
    calls = {
        (Path(nodes[edge["source"]]["source_file"]).parent.name,
         Path(nodes[edge["target"]]["source_file"]).parent.name)
        for edge in result["edges"]
        if edge["relation"] == "calls"
        and nodes[edge["source"]]["label"] == ".Run()"
        and nodes[edge["target"]]["label"] == ".GetByID()"
    }
    assert calls == {("alpha", "alpha"), ("beta", "beta")}
