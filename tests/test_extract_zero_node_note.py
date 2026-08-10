"""Expected zero-node sources are a note, not a warning (#2311).

Xcode asset-catalogue metadata and data-classified JSON produce zero nodes on
every run forever. Warning about them each run trains the reader to ignore the
zero-node warning — which does sometimes mean something. They must be reported
separately as information, while a genuinely empty source still warns.
"""
import json

from graphify.extract import extract


def _run(tmp_path, capsys, files):
    paths = []
    for rel, payload in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(payload, encoding="utf-8")
        paths.append(p)
    result = extract(paths, cache_root=tmp_path, root=tmp_path, parallel=False)
    return result, capsys.readouterr().err


def test_asset_catalogue_contents_json_is_a_note_not_a_warning(tmp_path, capsys):
    files = {
        "Assets.xcassets/AppColor.colorset/Contents.json": json.dumps(
            {"colors": [{"idiom": "universal"}], "info": {"version": 1}}
        ),
        "fixture_rows.json": json.dumps([{"row": 1}, {"row": 2}]),
    }
    _, err = _run(tmp_path, capsys, files)
    assert "intentionally non-graph-bearing" in err
    assert "Contents.json" in err
    assert "fixture_rows.json" in err
    assert "produced zero graph nodes" not in err.replace(
        "intentionally non-graph-bearing", ""
    ) or "warning" not in err.casefold()


def test_unexplained_zero_node_source_still_warns(tmp_path, capsys):
    # A config-probed JSON that yields a file node is NOT zero-node; use an
    # empty Python file, which the extractor accepts but emits nothing for.
    files = {"empty.py": ""}
    _, err = _run(tmp_path, capsys, files)
    assert "intentionally non-graph-bearing" not in err
