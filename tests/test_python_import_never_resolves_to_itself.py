"""An absolute import never resolves to the module that contains it.

`_resolve_cross_file_imports` resolves `from a.b.c import X` by exact path, then by a
unique path suffix, then by a bare-stem index of the last part (`c`). For a package
outside the corpus, the bare-stem step can land on the importing file itself:
`from werkzeug.wrappers import Request as RequestBase` inside flask's own
`wrappers.py` matched `wrappers.py`, so `class Request(RequestBase)` was rewired to
inherit from itself and every use of the alias became an edge to the local class.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract

_WRAPPERS = (
    "from werkzeug.wrappers import Request as RequestBase\n"
    "\n\n"
    "class Request(RequestBase):\n"
    "    pass\n"
    "\n\n"
    "def wrap(req: RequestBase) -> RequestBase:\n"
    "    return RequestBase(req)\n"
)


def _build(tmp_path: Path, files: dict[str, str]):
    paths = []
    for name, body in {"pkg/__init__.py": "", **files}.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        paths.append(p)
    r = extract(paths, root=tmp_path, cache_root=tmp_path / "graphify-out", parallel=False)
    return {n["id"]: n for n in r["nodes"]}, r["edges"]


def test_external_base_aliased_in_a_same_named_module_is_not_a_self_loop(tmp_path):
    nodes, edges = _build(tmp_path, {"pkg/wrappers.py": _WRAPPERS})
    assert not [e for e in edges if e["source"] == e["target"]]
    inherits = [e for e in edges if e["relation"] == "inherits"]
    assert len(inherits) == 1
    base = nodes[inherits[0]["target"]]
    assert base["label"] == "RequestBase" and not base.get("source_file")


def test_uses_of_the_alias_do_not_point_at_the_local_class(tmp_path):
    nodes, edges = _build(tmp_path, {"pkg/wrappers.py": _WRAPPERS})
    local_request = next(nid for nid, n in nodes.items() if n["label"] == "Request" and n.get("source_file"))
    wrong = [e for e in edges if e["target"] == local_request and e["relation"] in ("uses", "references")]
    assert wrong == []


def test_a_real_in_repo_import_still_resolves(tmp_path):
    nodes, edges = _build(tmp_path, {
        "pkg/base.py": "class Request:\n    pass\n",
        "pkg/wrappers.py": "from pkg.base import Request as RequestBase\n\n\nclass Request(RequestBase):\n    pass\n",
    })
    inherits = [e for e in edges if e["relation"] == "inherits"]
    assert [nodes[e["target"]].get("source_file") for e in inherits] == ["pkg/base.py"]


def test_warm_rebuild_keeps_the_fix(tmp_path):
    first = _build(tmp_path, {"pkg/wrappers.py": _WRAPPERS})[1]
    warm = _build(tmp_path, {"pkg/wrappers.py": _WRAPPERS})[1]
    key = lambda e: (e["source"], e["target"], e["relation"])  # noqa: E731
    assert sorted(map(key, first)) == sorted(map(key, warm))
    assert not [e for e in warm if e["source"] == e["target"]]


def test_a_same_named_module_in_another_package_still_resolves(tmp_path):
    """The guard compares directory-qualified stems: `a/utils.py` importing from
    `b/utils.py` is a different module and must keep resolving, by exact path, by
    suffix, and through the bare-stem fallback, whichever file is listed first."""
    for i, importer in enumerate((
        "from b.utils import Helper\n",
        "from proj.b.utils import Helper\n",
        "from installed.x.utils import Helper\n",
    )):
        for b_first in (False, True):
            root = tmp_path / f"case{i}_{int(b_first)}"
            files = {
                "proj/__init__.py": "",
                "proj/a/__init__.py": "",
                "proj/b/__init__.py": "",
                "proj/b/utils.py": "class Helper:\n    pass\n",
                "proj/a/utils.py": importer + "\n\nclass Local(Helper):\n    pass\n",
            }
            paths = []
            for name, body in files.items():
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(body, encoding="utf-8")
                paths.append(p)
            if b_first:
                paths[-2], paths[-1] = paths[-1], paths[-2]
            r = extract(paths, root=root, cache_root=root / "graphify-out", parallel=False)
            nodes = {n["id"]: n for n in r["nodes"]}
            bases = [nodes[e["target"]].get("source_file") for e in r["edges"] if e["relation"] == "inherits"]
            assert bases == ["proj/b/utils.py"], (importer, b_first, bases)
