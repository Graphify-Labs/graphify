"""The ObjC field->type table must survive the id remaps (#3150).

`_resolve_objc_member_calls`' table (#2591) is the one extractor bucket keyed
BY class node id. The #1529 passes rewrote node ids, edge endpoints,
`raw_calls[].caller_nid` and `swift_extensions[].nid` — but not those keys.
The remap fires whenever the input paths carry a common absolute prefix,
i.e. always via `graphify update <dir>`, so `[self.<field> …]` receiver
typing was inert through the CLI and worked only in tests, which hand
extract() already-relative paths. The cached shard had the same split: the
portability rewrite re-anchored every id except the table keys.
"""
from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from graphify.extract import extract

try:
    import tree_sitter_objc  # noqa: F401
    HAVE_OBJC = True
except ImportError:
    HAVE_OBJC = False

FILES = {
    "src/Greeter.h": (
        "#import <Foundation/Foundation.h>\n"
        "@interface Greeter : NSObject\n- (void)greet;\n@end\n"),
    "src/Greeter.m": (
        '#import "Greeter.h"\n@implementation Greeter\n'
        '- (void)greet { NSLog(@"hi"); }\n@end\n'),
    "src/Direct.h": (
        "#import <Foundation/Foundation.h>\n#import \"Greeter.h\"\n"
        "@interface Direct : NSObject\n"
        "@property (nonatomic, strong) Greeter *greeter;\n- (void)run;\n@end\n"),
    "src/Direct.m": (
        '#import "Direct.h"\n@implementation Direct\n'
        "- (void)run { [self.greeter greet]; }\n@end\n"),
}


def _write(tmp_path):
    for name, body in FILES.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return tmp_path


def _calls(result):
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    return {(labels.get(e["source"]), labels.get(e["target"]))
            for e in result["edges"] if e.get("relation") == "calls"}


needs_objc = pytest.mark.skipif(not HAVE_OBJC, reason="tree-sitter-objc not installed")


@needs_objc
def test_receiver_typing_survives_absolute_input_paths(tmp_path):
    """The CLI shape: absolute inputs, common prefix stripped by the #1529
    remap. This is the run where #2591 emitted zero edges."""
    corpus = _write(tmp_path)
    cache = tmp_path / "out"
    with redirect_stdout(io.StringIO()):
        r = extract([(corpus / n).resolve() for n in FILES], cache_root=cache, parallel=False)
    assert ("-run", "-greet") in _calls(r), sorted(_calls(r))


@needs_objc
def test_receiver_typing_still_works_with_relative_paths(tmp_path, monkeypatch):
    """The shape the original #2591 tests used — must keep working."""
    corpus = _write(tmp_path)
    monkeypatch.chdir(corpus)
    cache = tmp_path / "out"
    with redirect_stdout(io.StringIO()):
        r = extract([Path(n) for n in FILES], cache_root=cache, parallel=False)
    assert ("-run", "-greet") in _calls(r)


@needs_objc
def test_a_cached_shard_replays_with_consistent_table_keys(tmp_path):
    """Warm-cache CLI run: the shard is written on the first pass and replayed
    on the second; the table keys must still match the node ids."""
    corpus = _write(tmp_path)
    cache = tmp_path / "out"
    paths = [(corpus / n).resolve() for n in FILES]
    with redirect_stdout(io.StringIO()):
        extract(paths, cache_root=cache, parallel=False)          # cold: writes shards
        r = extract(paths, cache_root=cache, parallel=False)      # warm: replays them
    assert ("-run", "-greet") in _calls(r), sorted(_calls(r))


def test_the_in_process_remap_rewrites_the_table_keys():
    """Unit form of the CLI-path fix: the same mapping that rewrites node ids
    must rewrite the table keys."""
    try:
        from graphify.extract import _remap_objc_field_tables
    except ImportError:  # pre-fix tree
        pytest.skip("pre-fix tree")
    per_file = [{"objc_field_types": {"path": "src/Direct.h",
                                      "tables": {"abs_slug_direct": {"greeter": "Greeter"}}}},
                {"nodes": []}]
    _remap_objc_field_tables(per_file, {"abs_slug_direct": "src_direct_direct"})
    assert per_file[0]["objc_field_types"]["tables"] == {"src_direct_direct": {"greeter": "Greeter"}}


def test_cache_portability_rewrites_the_table_keys(tmp_path):
    """Round-trip a payload through the #2257 portability rewrite: the class id
    inside the table key must follow the node id."""
    from graphify.cache import _absolutize_ids_in, _relativize_ids_in
    from graphify.extractors.base import _make_id

    root = tmp_path / "proj"
    root.mkdir()
    f = root / "Direct.m"
    f.write_text("@implementation Direct\n@end\n", encoding="utf-8")
    abs_id = _make_id(str(root)) + "_direct_direct"
    assert _relativize_ids_in is not None
    payload = {
        "nodes": [{"id": abs_id, "label": "Direct"}],
        "edges": [],
        "objc_field_types": {"path": str(f), "tables": {abs_id: {"greeter": "Greeter"}}},
    }
    _relativize_ids_in(payload, f, root)
    stored_key = next(iter(payload["objc_field_types"]["tables"]))
    assert stored_key == payload["nodes"][0]["id"], "key and id diverged on store"
    _absolutize_ids_in(payload, f, root)
    restored_key = next(iter(payload["objc_field_types"]["tables"]))
    assert restored_key == payload["nodes"][0]["id"], "key and id diverged on load"
    assert payload["objc_field_types"]["tables"][restored_key] == {"greeter": "Greeter"}
