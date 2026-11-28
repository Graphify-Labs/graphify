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


@pytest.mark.parametrize('suffix', ['.ts', '.tsx'])
def test_generic_tagged_templates_resolve_import_alias_and_interpolation(
    tmp_path: Path, suffix: str,
):
    tag = tmp_path / 'query.ts'
    tag.write_text(
        'export function tag<T>(parts: TemplateStringsArray, ...args: unknown[]): T { throw 0; }\n',
        encoding='utf-8',
    )
    caller = tmp_path / ('input' + suffix)
    source = '''import { tag as sql } from './query';
function parameter() { return 42; }
export function simple() { return sql<number>`count`; }
export function union() { return sql<string | null>`name`; }
export function nested() {
  return sql<
    ReadonlyArray<Promise<number>>
  > `select ${parameter()}`;
}
export function untyped() { return sql`select`; }
'''
    if suffix == '.tsx':
        source += 'export function component() { return <div />; }\n'
    caller.write_text(source, encoding='utf-8')

    result = extractor.extract(
        [tag, caller], root=tmp_path, cache_root=tmp_path / 'cache', parallel=False,
    )
    assert not result['failed_sources']
    nodes = {node['id']: node for node in result['nodes']}
    calls = {
        (
            nodes[edge['source']]['label'],
            nodes[edge['target']]['label'],
            edge['source_file'],
            edge['source_location'],
            nodes[edge['target']]['source_file'],
        )
        for edge in result['edges'] if edge['relation'] == 'calls'
    }
    assert calls == {
        ('simple()', 'tag()', caller.name, 'L3', 'query.ts'),
        ('union()', 'tag()', caller.name, 'L4', 'query.ts'),
        ('nested()', 'tag()', caller.name, 'L6', 'query.ts'),
        ('nested()', 'parameter()', caller.name, 'L8', caller.name),
        ('untyped()', 'tag()', caller.name, 'L10', 'query.ts'),
    }


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


def test_generic_tagged_templates_recover_after_misparsed_opening(tmp_path: Path):
    path = tmp_path / 'input.ts'
    path.write_text('''export function load(flag: boolean) {
  return select({ value: flag
    ? sql<unknown>`null`
    : sql<unknown>`(
        select ${parameter()}
      )`,
  });
}
export function later() {}
''', encoding='utf-8')

    result = extract_js(path)
    assert 'parse_errors' not in result
    assert {'load()', 'later()'} <= {node['label'] for node in result['nodes']}
    assert {(call['callee'], call['source_location']) for call in result['raw_calls']} == {
        ('select', 'L2'), ('sql', 'L3'), ('sql', 'L4'), ('parameter', 'L5'),
    }


def test_type_import_does_not_hide_real_dynamic_import_after_unicode(tmp_path: Path):
    path = tmp_path / 'input.ts'
    path.write_text('''const mensaje = "bicicleta eléctrica";
export function create() {
  const handler = (c: import("hono").Context<Env>) => respond(c);
  return handler;
}
export async function load() { return import("./runtime"); }
''', encoding='utf-8')
    (tmp_path / 'runtime.ts').write_text('export const value = 1;')
    result = extract_js(path)
    labels = {n['id']: n['label'] for n in result['nodes']}
    dynamic = [labels.get(e['target'], e['target']) for e in result['edges'] if e['relation'] == 'dynamic_import']
    assert 'hono' not in dynamic
    assert any('runtime' in str(target) for target in dynamic)


@pytest.mark.parametrize('newline', ['\n', '\r\n', '\r'])
@pytest.mark.parametrize('bom', [False, True])
def test_type_import_offsets_survive_newlines_and_bom(tmp_path: Path, newline: str, bom: bool):
    path = tmp_path / 'input.ts'
    source = '''const titulo = "más";
export function create() {
  const handler = (c: import("hono").Context<Env>) => respond(c);
  return handler;
}
export async function load() { return import("./runtime"); }
'''.replace('\n', newline).encode('utf-8')
    path.write_bytes((b'\xef\xbb\xbf' if bom else b'') + source)
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


def test_generic_tagged_template_repair_leaves_other_source_unchanged():
    source = (
        b'// sql<number>`comment`\n'
        b'/* sql<string | null>`block comment` */\n'
        b'const literal = "sql<number>`string`";\n'
        b'const template = `sql<number>`;\n'
        b'const compared = (a < b) > `runtime`;\n'
        b'const updated = a++<b>`runtime`;\n'
        b'const count = sql<number>`select`;\n'
    )
    normalized = extractor._normalize_ts_tag_and_import_annotations(source)
    assert normalized == source.replace(b'<number>`select`', b'        `select`')


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


def test_typed_tag_candidate_scan_has_no_catastrophic_backtracking():
    """A long identifier that never completes a typed tag must not restart the
    scan at every byte. Linear matching clears 100k bytes in well under a second;
    a super-linear (backtracking) pattern would take many seconds and blow past
    this generous absolute bound."""
    import time

    source = b'a' * 100000
    start = time.process_time()
    assert list(extractor._TS_TYPED_TAG_RE.finditer(source)) == []
    assert time.process_time() - start < 1.0
