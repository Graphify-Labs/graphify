"""Regression tests: jsconfig.json / baseUrl module resolution (#2153).

`compilerOptions.baseUrl` was only ever used as the base that `paths` aliases
resolve against, so a config declaring `baseUrl` and NO `paths` produced an
empty alias map and every non-relative import died. In a Rails/webpacker
project (`jsconfig.json` with `"baseUrl": "app/javascript"`) that orphaned every
module: `import Widget from 'mods/Widget.js'` emitted no edge, so `affected`
answered nothing. `jsconfig.json` was also never probed at all — only
`tsconfig.json` — even though json_config.py already indexes it.

baseUrl is now a resolution root of last resort: tried only after every declared
alias fails to match, so existing `paths` precedence (#1269, #927, #1531) is
untouched.
"""
from pathlib import Path

from graphify.extract import _make_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _targets(result: dict) -> set[str]:
    return {e["target"] for e in result["edges"]}


def _rails_tree(tmp_path: Path, config_name: str, importer_body: str,
                base_url: str = "app/javascript", paths: str = "") -> Path:
    """A webpacker-shaped project: config at the root, modules under baseUrl."""
    paths_frag = f',\n    "paths": {{ {paths} }}' if paths else ""
    _write(tmp_path / config_name,
           '{\n  "compilerOptions": {\n'
           f'    "baseUrl": "{base_url}"{paths_frag}\n'
           '  }\n}\n')
    _write(tmp_path / base_url / "mods" / "Widget.js",
           "export default function Widget() {}\n")
    return _write(tmp_path / base_url / "packs" / "dashboard.js", importer_body)


def _widget(tmp_path: Path, base_url: str = "app/javascript") -> str:
    # The resolved import target is canonicalized to the root-relative file-node
    # id (the same id Widget.js gets as a node), not the absolute-path form
    # (#2169 canonicalizes cross-file edge targets).
    return _cid(tmp_path, tmp_path / base_url / "mods" / "Widget.js")


def _cid(tmp_path: Path, abs_path: Path) -> str:
    """Canonical root-relative file-node id of a cross-file import target (#2169)."""
    return _make_id(str(Path(abs_path).relative_to(tmp_path).with_suffix("")))


def test_jsconfig_baseurl_static_import_resolves(tmp_path):
    # The issue repro: jsconfig.json, baseUrl, NO paths.
    f = _rails_tree(tmp_path, "jsconfig.json",
                    "import Widget from 'mods/Widget.js';\n"
                    "export default Widget;\n")
    r = extract([f], cache_root=tmp_path)
    assert _widget(tmp_path) in _targets(r)


def test_jsconfig_baseurl_dynamic_import_resolves(tmp_path):
    # The issue states static AND dynamic are both affected.
    f = _rails_tree(tmp_path, "jsconfig.json",
                    "export async function load() {\n"
                    "  return import('mods/Widget.js');\n"
                    "}\n")
    r = extract([f], cache_root=tmp_path)
    assert _widget(tmp_path) in _targets(r)


def test_jsconfig_baseurl_extensionless_specifier_resolves(tmp_path):
    f = _rails_tree(tmp_path, "jsconfig.json",
                    "import Widget from 'mods/Widget';\n"
                    "export default Widget;\n")
    r = extract([f], cache_root=tmp_path)
    assert _widget(tmp_path) in _targets(r)


def test_tsconfig_baseurl_without_paths_also_resolves(tmp_path):
    # Same defect applies to tsconfig.json, not just jsconfig.json.
    f = _rails_tree(tmp_path, "tsconfig.json",
                    "import Widget from 'mods/Widget.js';\n"
                    "export default Widget;\n")
    r = extract([f], cache_root=tmp_path)
    assert _widget(tmp_path) in _targets(r)


def test_declared_paths_alias_still_wins_over_baseurl(tmp_path):
    # Guards #1269: a declared alias must not be shadowed by the baseUrl
    # fallback. "@mods/Widget.js" must resolve via paths to real/Widget.js,
    # NOT to <baseUrl>/@mods/Widget.js.
    _write(tmp_path / "jsconfig.json",
           '{\n  "compilerOptions": {\n'
           '    "baseUrl": "app/javascript",\n'
           '    "paths": { "@mods/*": ["real/*"] }\n'
           '  }\n}\n')
    # paths targets are relative to baseUrl (#1269), so "real/*" is
    # <baseUrl>/real/*.
    real = _write(tmp_path / "app/javascript" / "real" / "Widget.js",
                  "export default 1;\n")
    _write(tmp_path / "app/javascript" / "@mods" / "Widget.js", "export default 2;\n")
    f = _write(tmp_path / "app/javascript" / "packs" / "d.js",
               "import W from '@mods/Widget.js';\nexport default W;\n")
    r = extract([f], cache_root=tmp_path)
    targets = _targets(r)
    assert _cid(tmp_path, real) in targets
    assert _cid(tmp_path, tmp_path / "app/javascript" / "@mods" / "Widget.js") not in targets


def test_declared_directory_prefix_alias_still_wins(tmp_path):
    # A non-wildcard alias used as a directory prefix scores WORSE than a
    # wildcard in _match_tsconfig_alias, so a naive implicit "*" alias would
    # shadow it. The fallback must not.
    _write(tmp_path / "jsconfig.json",
           '{\n  "compilerOptions": {\n'
           '    "baseUrl": "app/javascript",\n'
           '    "paths": { "@lib": ["src/lib"] }\n'
           '  }\n}\n')
    real = _write(tmp_path / "app/javascript" / "src" / "lib" / "util.js",
                  "export default 1;\n")
    _write(tmp_path / "app/javascript" / "@lib" / "util.js", "export default 2;\n")
    f = _write(tmp_path / "app/javascript" / "packs" / "p.js",
               "import u from '@lib/util.js';\nexport default u;\n")
    r = extract([f], cache_root=tmp_path)
    assert _cid(tmp_path, real) in _targets(r)


def test_tsconfig_paths_alias_unchanged(tmp_path):
    # Pre-existing #1269 behavior, green before and after this change: a
    # tsconfig paths alias resolves relative to baseUrl.
    _write(tmp_path / "tsconfig.json",
           '{\n  "compilerOptions": {\n'
           '    "baseUrl": "./src",\n'
           '    "paths": { "@services/*": ["services/*"] }\n'
           '  }\n}\n')
    svc = _write(tmp_path / "src" / "services" / "api.ts", "export const a = 1;\n")
    f = _write(tmp_path / "src" / "app" / "main.ts",
               "import { a } from '@services/api';\nexport default a;\n")
    r = extract([f], cache_root=tmp_path)
    assert _cid(tmp_path, svc) in _targets(r)


def test_external_package_not_fabricated_under_baseurl(tmp_path):
    # baseUrl must not turn a real npm import into a phantom <baseUrl>/react
    # edge; the fallback only returns paths that exist on disk.
    _write(tmp_path / "jsconfig.json",
           '{\n  "compilerOptions": { "baseUrl": "app/javascript" }\n}\n')
    f = _write(tmp_path / "app/javascript" / "packs" / "p.js",
               "import React from 'react';\nexport default React;\n")
    r = extract([f], cache_root=tmp_path)
    assert _cid(tmp_path, tmp_path / "app/javascript" / "react") not in _targets(r)


def test_relative_import_unaffected_by_baseurl(tmp_path):
    _write(tmp_path / "jsconfig.json",
           '{\n  "compilerOptions": { "baseUrl": "app/javascript" }\n}\n')
    local = _write(tmp_path / "app/javascript" / "packs" / "Local.js",
                   "export default 1;\n")
    f = _write(tmp_path / "app/javascript" / "packs" / "main.js",
               "import L from './Local.js';\nexport default L;\n")
    r = extract([f], cache_root=tmp_path)
    assert _cid(tmp_path, local) in _targets(r)


def test_no_baseurl_declared_changes_nothing(tmp_path):
    # Without baseUrl there is no fallback root, so a bare specifier stays
    # external and must not resolve to a file under the config dir.
    _write(tmp_path / "jsconfig.json", '{\n  "compilerOptions": {}\n}\n')
    _write(tmp_path / "mods" / "Widget.js", "export default 1;\n")
    f = _write(tmp_path / "packs" / "d.js",
               "import W from 'mods/Widget.js';\nexport default W;\n")
    r = extract([f], cache_root=tmp_path)
    assert _cid(tmp_path, tmp_path / "mods" / "Widget.js") not in _targets(r)


def test_tsconfig_wins_when_both_configs_present(tmp_path):
    # tsconfig.json is the authoritative config when both exist (tsc/VS Code
    # only fall back to jsconfig.json when there is no tsconfig.json).
    _write(tmp_path / "tsconfig.json",
           '{\n  "compilerOptions": { "baseUrl": "ts_root" }\n}\n')
    _write(tmp_path / "jsconfig.json",
           '{\n  "compilerOptions": { "baseUrl": "js_root" }\n}\n')
    ts_hit = _write(tmp_path / "ts_root" / "mods" / "W.js", "export default 1;\n")
    _write(tmp_path / "js_root" / "mods" / "W.js", "export default 2;\n")
    f = _write(tmp_path / "ts_root" / "packs" / "d.js",
               "import W from 'mods/W.js';\nexport default W;\n")
    r = extract([f], cache_root=tmp_path)
    targets = _targets(r)
    assert _cid(tmp_path, ts_hit) in targets
    assert _cid(tmp_path, tmp_path / "js_root" / "mods" / "W.js") not in targets
