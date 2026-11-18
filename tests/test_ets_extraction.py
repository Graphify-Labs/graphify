"""Regression test for `.ets` (ArkTS) files being silently skipped (#3752).

`.ets` is listed in ``detect.CODE_EXTENSIONS`` so it reaches the AST pass, but
the ``_DISPATCH`` table in ``extract.py`` had no ``.ets`` entry, so
``_get_extractor`` returned None and the file contributed no nodes. ArkTS is a
TypeScript derivative, so it is routed to ``extract_js`` (the tree-sitter
TypeScript/JavaScript grammar) until a dedicated grammar is available.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import _DISPATCH, _get_extractor, extract_js


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


ARKTS_SOURCE = """import { BusinessError } from '@kit.BasicServicesKit';

export interface ServiceOptions {
  name: string;
  retries?: number;
}

export type ServiceResult = { ok: boolean };

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
    assert _DISPATCH.get(".ets") is extract_js


def test_ets_extraction_yields_nodes(tmp_path):
    """An `.ets` file routed through the JS/TS grammar yields real nodes (#3752)."""
    ets = _write(tmp_path / "Index.ets", ARKTS_SOURCE)
    result = extract_js(ets)
    assert result.get("nodes")


def test_ets_uses_typescript_grammar_for_type_declarations(tmp_path):
    """ArkTS `interface`/`type` declarations must survive extraction.

    `.ets` dispatches to `extract_js`, whose JS grammar drops interface and
    type-alias declarations. Route it through the TS config so these become
    type nodes, matching the `.ts` behaviour.
    """
    ets = _write(tmp_path / "Index.ets", ARKTS_SOURCE)
    labels = [n["label"] for n in extract_js(ets)["nodes"]]

    assert any("ServiceOptions" in label for label in labels), (
        "ArkTS interface missing → .ets fell back to the JS grammar"
    )
    assert any("ServiceResult" in label for label in labels), (
        "ArkTS type alias missing → .ets fell back to the JS grammar"
    )
