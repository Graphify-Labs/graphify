"""Execute the generated update manifest block against real detector state."""
import json
from pathlib import Path

import pytest

from graphify.detect import detect_incremental, load_manifest, save_manifest
from tools.skillgen import gen


SPLIT_HOSTS = [key for key, platform in gen.load_platforms().items()
               if any(str(a.path).replace("\\", "/").endswith("/references/update.md") for a in gen.render(platform))]


@pytest.mark.parametrize("host", SPLIT_HOSTS)
@pytest.mark.parametrize("failed_change", [False, True])
def test_update_preserves_undispatched_semantic_stamps(tmp_path, monkeypatch, host, failed_change):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "graphify-out").mkdir()
    docs = [tmp_path / f"doc{i}.md" for i in range(5)]
    for p in docs:
        p.write_text("# A real document\nUnchanged semantic content.\n", encoding="utf-8")
    save_manifest({"document": [str(p) for p in docs]}, root=tmp_path)
    before = load_manifest(root=tmp_path)
    docs[0].unlink()
    if failed_change:
        docs[1].write_text("# Changed\nThis document's extraction failed.\n", encoding="utf-8")
    incremental = detect_incremental(tmp_path)
    assert incremental["new_total"] == int(failed_change)
    assert len(incremental["deleted_files"]) == 1
    extraction_path = Path("graphify-out/.graphify_extract.json")
    extraction_path.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
    artifact = next(a for a in gen.render(gen.load_platforms()[host])
                    if str(a.path).replace("\\", "/").endswith("/references/update.md"))
    # Execute exactly the generated manifest block, including clear_semantic
    # and the raw scan corpus. INPUT_PATH is a constant fixture root here.
    block = artifact.content.split("from graphify.cli import _stamped_manifest_files", 1)[1]
    block = "from graphify.cli import _stamped_manifest_files" + block.split("print('[graphify update] Manifest saved.')", 1)[0]
    # Since #4762 the block reads the scan root from .graphify_root into INPUT_PATH
    # above this slice; provide that resolved value directly in the exec scope.
    scope = {"incremental": incremental, "new_extraction": json.loads(extraction_path.read_text(encoding="utf-8")),
             "Path": Path, "save_manifest": save_manifest, "INPUT_PATH": "."}
    exec(compile(block, str(artifact.path), "exec"), scope)
    after = load_manifest(root=tmp_path)
    assert str(docs[0]) not in after
    for p in docs[2:] if failed_change else docs[1:]:
        assert after[str(p)] == before[str(p)]
    following = detect_incremental(tmp_path)
    assert following["new_total"] == int(failed_change)
    assert following["deleted_files"] == []
    if failed_change:
        assert not after[str(docs[1])]["semantic_hash"]
