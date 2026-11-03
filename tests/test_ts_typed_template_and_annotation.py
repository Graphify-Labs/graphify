"""Tree-sitter compatibility for valid TypeScript type-only syntax."""
from pathlib import Path
import importlib

import pytest

extractor = importlib.import_module('graphify.extract')
extract_js = extractor.extract_js


@pytest.mark.parametrize('suffix', ['.ts', '.tsx'])
def test_tagged_template_keeps_later_declarations_and_calls(tmp_path: Path, suffix: str):
    path = tmp_path / ('input' + suffix)
    path.write_text('''export function load() {
  const rows = sql<{ id: string; nombre: string }[]>`select id from tabla`;
  return finish(rows);
}
export function later() {}
''')
    result = extract_js(path)
    assert 'parse_errors' not in result
    assert {'load()', 'later()'} <= {node['label'] for node in result['nodes']}
    assert any(call.get('callee') == 'finish' for call in result['raw_calls'])
    assert next(n for n in result['nodes'] if n['label'] == 'later()')['source_location'] == 'L5'


def test_import_qualified_annotation_keeps_export_and_calls(tmp_path: Path):
    path = tmp_path / 'routes.ts'
    path.write_text('''export function create() {
  const handler = (c: import("hono").Context<Env>) => respond(c);
  return handler;
}
export function after() {}
''')
    result = extract_js(path)
    assert 'parse_errors' not in result
    assert {'create()', 'after()'} <= {node['label'] for node in result['nodes']}
    assert any(call.get('callee') == 'respond' for call in result['raw_calls'])
    assert not any(edge.get('relation') == 'dynamic_import' for edge in result['edges'])


def test_type_import_does_not_hide_real_dynamic_import_after_unicode(tmp_path: Path):
    path = tmp_path / 'input.ts'
    path.write_text('''const mensaje = "bicicleta eléctrica";
export function create() {
  const handler = (c: import("hono").Context<Env>) => respond(c);
  return handler;
}
export async function load() { return import("./runtime"); }
''')
    (tmp_path / 'runtime.ts').write_text('export const value = 1;')
    result = extract_js(path)
    labels = {n['id']: n['label'] for n in result['nodes']}
    dynamic = [labels.get(e['target'], e['target']) for e in result['edges'] if e['relation'] == 'dynamic_import']
    assert 'hono' not in dynamic
    assert any('runtime' in str(target) for target in dynamic)


def test_preserves_comments_strings_and_template_text():
    source = (b'// sql<{id:string}[]>`not code`\n'
              b'const s = "sql<{id:string}[]>`literal`";\n'
              b'const template = `sql<{id:string}[]> text`;\n'
              b'const rows = sql<{id:string}[]>`select`;\n')
    normalized = extractor._normalize_ts_tag_and_import_annotations(source)
    assert normalized is not None
    assert normalized.splitlines()[:3] == source.splitlines()[:3]
    assert len(normalized) == len(source)
    assert normalized.count(b'\n') == source.count(b'\n')


def test_runtime_comparison_and_dynamic_import_survive_other_errors():
    source = (b'const unrelated = ;\n'
              b'const value = a < {id: 2} > `runtime`;\n'
              b'const other = import("mod").Thing < limit;\n')
    assert extractor._normalize_ts_tag_and_import_annotations(source) is None


def test_multiline_type_preserves_offsets_and_line_numbers(tmp_path: Path):
    source = b'const rows = sql<{\n id: string;\n nombre: string\n}[]>`select`;\nexport function after() {}\n'
    normalized = extractor._normalize_ts_tag_and_import_annotations(source)
    assert normalized is not None
    assert len(normalized) == len(source)
    assert normalized.count(b'\n') == source.count(b'\n')
    path = tmp_path / 'input.ts'
    path.write_bytes(source)
    result = extract_js(path)
    assert 'parse_errors' not in result
    assert next(n for n in result['nodes'] if n['label'] == 'after()')['source_location'] == 'L5'
