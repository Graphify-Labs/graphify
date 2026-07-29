"""Node-id / edge-endpoint canonicalization: no absolute-path (machine/temp
slug) leaks (#2231, #2243).

Every producer that mints ids from ``_make_id(str(absolute_path))`` must end
up canonicalized by the time ``extract()`` returns: after extraction, no node
id and no edge endpoint may contain the absolute scan-root slug for any file
that appears in the batch — on full scans AND on incremental (changed-files
only) runs.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.extract import extract, _make_id


def _real(tmp_path: Path) -> Path:
    # macOS pytest tmp dirs live under a /var -> /private/var symlink; resolve
    # so "absolute input path" and "resolved path" agree deterministically.
    return Path(os.path.realpath(tmp_path))


def _slug(root: Path) -> str:
    # The tmp-root directory name is unique per test run; an id or endpoint
    # containing it can only have been minted from the absolute path.
    return _make_id(root.name)


def _assert_no_slug(result: dict, slug: str) -> None:
    leaked_nodes = [n["id"] for n in result["nodes"] if slug in n["id"].lower()]
    assert not leaked_nodes, f"absolute-slug node ids leaked: {leaked_nodes}"
    leaked_edges = [
        (e["source"], e["target"], e["relation"])
        for e in result["edges"]
        if slug in e["source"].lower() or slug in e["target"].lower()
    ]
    assert not leaked_edges, f"absolute-slug edge endpoints leaked: {leaked_edges}"


def test_module_level_dispatch_indirect_call_source_is_canonical(tmp_path):
    """#2231: a module-TOP-LEVEL dispatch table (`HANDLERS = {'a': handle_a}`)
    records the FILE node as the raw_call caller. The emitted indirect_call
    edge's source must be the canonical file node id, not the id minted from
    the absolute input path."""
    root = _real(tmp_path)
    (root / "handlers.py").write_text("def handle_a():\n    return 1\n")
    (root / "disp.py").write_text(
        "from handlers import handle_a\n\nHANDLERS = {'a': handle_a}\n"
    )

    result = extract(
        [root / "disp.py", root / "handlers.py"], cache_root=tmp_path, root=root
    )

    indirect = [e for e in result["edges"] if e["relation"] == "indirect_call"]
    assert indirect, "module-level dispatch must emit an indirect_call edge"
    node_ids = {n["id"] for n in result["nodes"]}
    for e in indirect:
        assert e["source"] == "disp", (
            f"indirect_call source must be the canonical file node id, got {e['source']}"
        )
        assert e["source"] in node_ids, "indirect_call source must be a real node"
        assert e["target"] == "handlers_handle_a"
    _assert_no_slug(result, _slug(root))


def test_bash_source_incremental_target_canonicalizes(tmp_path):
    """#2243 (bash): `source ./b.sh` mints the target from the resolved
    absolute path. On an incremental run (only the sourcing script in the
    batch) the target_file stamp must still canonicalize it to the same id the
    full scan produces, with no tmp-root slug."""
    root = _real(tmp_path)
    (root / "a.sh").write_text("#!/bin/bash\nsource ./b.sh\nbash ./c.sh\n")
    (root / "b.sh").write_text("#!/bin/bash\nhello() { echo hi; }\n")
    (root / "c.sh").write_text("#!/bin/bash\necho run\n")

    full = extract(
        [root / "a.sh", root / "b.sh", root / "c.sh"], cache_root=tmp_path, root=root
    )
    _assert_no_slug(full, _slug(root))
    full_imports = {
        (e["source"], e["target"]) for e in full["edges"]
        if e["relation"] == "imports_from"
    }
    assert ("a", "b") in full_imports
    full_invocations = {
        (e["source"], e["target"]) for e in full["edges"]
        if e["relation"] == "calls" and e.get("context") == "script_invocation"
    }
    assert ("a_sh__entry", "c_sh__entry") in full_invocations

    # Incremental: only the CHANGED sourcing script is re-extracted; b.sh and
    # c.sh are not in the batch, so their canonical ids must be learned from
    # the target_file stamps.
    incr = extract([root / "a.sh"], cache_root=tmp_path, root=root)
    _assert_no_slug(incr, _slug(root))
    incr_imports = {
        (e["source"], e["target"]) for e in incr["edges"]
        if e["relation"] == "imports_from"
    }
    assert ("a", "b") in incr_imports, (
        f"incremental imports_from target must canonicalize; got {incr_imports}"
    )
    incr_invocations = {
        (e["source"], e["target"]) for e in incr["edges"]
        if e["relation"] == "calls" and e.get("context") == "script_invocation"
    }
    assert ("a_sh__entry", "c_sh__entry") in incr_invocations, (
        "incremental script-invocation __entry endpoint must match the entry "
        f"node id the full scan mints; got {incr_invocations}"
    )
    # The transient stamp must never ship out of extract().
    assert not any("target_file" in e for e in incr["edges"])
    assert not any("target_file" in e for e in full["edges"])


def test_extract_invariant_no_absolute_root_slug_anywhere(tmp_path):
    """General invariant: extracting a mixed corpus (python module-level
    dispatch + bash source + a normal import) from ABSOLUTE input paths leaves
    no node id and no edge endpoint containing the absolute-root slug."""
    root = _real(tmp_path)
    (root / "handlers.py").write_text("def handle_a():\n    return 1\n")
    (root / "disp.py").write_text(
        "from handlers import handle_a\n\nHANDLERS = {'a': handle_a}\n"
    )
    (root / "main.py").write_text("import handlers\n\nhandlers.handle_a()\n")
    (root / "run.sh").write_text("#!/bin/bash\nsource ./lib.sh\n./tool.sh\n")
    (root / "lib.sh").write_text("#!/bin/bash\ngreet() { echo hi; }\n")
    (root / "tool.sh").write_text("#!/bin/bash\necho tool\n")

    paths = [
        root / "disp.py", root / "handlers.py", root / "main.py",
        root / "run.sh", root / "lib.sh", root / "tool.sh",
    ]
    result = extract(paths, cache_root=tmp_path, root=root)

    slug = _slug(root)
    assert not any(slug in n["id"].lower() for n in result["nodes"]), [
        n["id"] for n in result["nodes"] if slug in n["id"].lower()
    ]
    assert not any(
        slug in ep.lower()
        for e in result["edges"]
        for ep in (e["source"], e["target"])
    ), [
        (e["source"], e["target"]) for e in result["edges"]
        if slug in e["source"].lower() or slug in e["target"].lower()
    ]
