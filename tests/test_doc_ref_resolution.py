"""Code citations of ADR/RFC ids resolve to the one scanned decision document (#5227)."""
from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.extract import collect_files, extract

TS = "// See ADR-0007.\nexport function example() { return 1; }\n"


def _graph(tmp_path: Path, files: dict[str, str]):
    root = tmp_path / "repo"
    for name, text in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    data = extract(collect_files(root, root=root), root=root,
                   cache_root=tmp_path / "cache", parallel=False)
    return root, build_from_json(data, root=root, dedup=False, directed=True)


def _cites(tmp_path: Path, files: dict[str, str]) -> list[tuple[str, str]]:
    root, g = _graph(tmp_path, files)
    out = []
    for a, b, e in g.edges(data=True):
        if e.get("relation") == "cites":
            sf = g.nodes[b].get("source_file") or ""
            rel = Path(sf).relative_to(root).as_posix() if sf.startswith(str(root)) else sf
            out.append((g.nodes[a]["label"], rel))
    return sorted(out)


@pytest.mark.parametrize("files, doc", [
    ({"src/a.ts": TS, "docs/decisions/0007-example.md": "# ADR-0007: Example decision\n"},
     "docs/decisions/0007-example.md"),
    ({"src/a.ts": TS, "doc/adr/0007-use-postgres.md": "# 7. Use Postgres\n"},
     "doc/adr/0007-use-postgres.md"),
    ({"src/a.ts": TS, "notes/arch.md": "# ADR 7 - Use Postgres\n"},
     "notes/arch.md"),
    ({"src/a.ts": "// per RFC-12\nexport const x = 1;\n", "rfcs/0012-thing.md": "# RFC-12: Thing\n"},
     "rfcs/0012-thing.md"),
], ids=["title-heading", "adr-tools-filename", "spaced-heading", "rfc"])
def test_citation_resolves_to_the_one_decision_document(tmp_path, files, doc):
    src = next(n for n in files if n.endswith(".ts"))
    assert _cites(tmp_path, files) == [(Path(src).name, doc)]


@pytest.mark.parametrize("files", [
    {"src/a.ts": TS, "docs/adr/0007-a.md": "# ADR-0007: A\n", "old/adr/0007-b.md": "# ADR-0007: B\n"},
    {"src/a.ts": TS, "README.md": "# Readme\n"},
    {"src/a.ts": TS, "docs/adr/0009-x.md": "# ADR-0009: X\n\nSupersedes ADR-0007.\n"},
    {"src/a.ts": TS, "docs/0007-release.md": "# Release 7\n"},
], ids=["two-claimants", "no-document", "body-mention-only", "number-outside-adr-folder"])
def test_citation_stays_a_stub_without_one_unambiguous_document(tmp_path, files):
    assert _cites(tmp_path, files) == [("a.ts", "src/a.ts")]


def test_every_citing_file_reaches_the_same_document(tmp_path):
    files = {"src/a.ts": TS, "src/b.ts": TS, "docs/adr/0007-a.md": "# ADR-0007: A\n"}
    assert _cites(tmp_path, files) == [("a.ts", "docs/adr/0007-a.md"), ("b.ts", "docs/adr/0007-a.md")]


def test_resolved_citation_stays_cites_not_implements(tmp_path):
    files = {"src/a.ts": TS, "docs/adr/0007-a.md": "# ADR-0007: A\n"}
    root, g = _graph(tmp_path, files)
    doc_nodes = {n for n, d in g.nodes(data=True)
                 if str(d.get("source_file", "")).endswith("0007-a.md")}
    touching = [e["relation"] for a, b, e in g.edges(data=True)
                if (a in doc_nodes or b in doc_nodes) and e.get("relation") != "contains"]
    assert "cites" in touching
    assert "implements" not in touching
