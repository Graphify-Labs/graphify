"""Regression test for `.ets` (ArkTS) files being silently skipped (#3752).

`.ets` is listed in ``detect.CODE_EXTENSIONS`` so it reaches the AST pass, but
the ``_DISPATCH`` table in ``extract.py`` had no ``.ets`` entry, so
``_get_extractor`` returned None and the file contributed no nodes. ArkTS is a
TypeScript derivative, so it is routed to ``extract_js`` (the tree-sitter
TypeScript/JavaScript grammar) until a dedicated grammar is available.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import _get_extractor, extract_js


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


ARKTS_SOURCE = """import { BusinessError } from '@kit.BasicServicesKit';

export function greet(name: string): string {
  return 'hi ' + name;
}

export class MyService {
  run(x: number): void {}
}
"""


def test_ets_has_an_ast_extractor(tmp_path):
    """`.ets` must resolve to an extractor, not fall through to None (#3752)."""
    ets = _write(tmp_path / "Index.ets", ARKTS_SOURCE)
    assert _get_extractor(ets) is not None


def test_ets_extraction_yields_nodes(tmp_path):
    """An `.ets` file routed through the JS/TS grammar yields real nodes (#3752)."""
    ets = _write(tmp_path / "Index.ets", ARKTS_SOURCE)
    result = extract_js(ets)
    assert result.get("nodes")
