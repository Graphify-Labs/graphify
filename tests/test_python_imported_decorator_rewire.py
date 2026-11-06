"""Regression tests: imported-module decorators must not bind to unrelated local defs (#2732).

`@pytest.fixture` reaches the extractor as the bare head symbol `fixture`
(`_python_decorator_name` keeps the attribute, not the module), becomes a
sourceless `fixture` stub, and the corpus rewire then collapses that stub onto
the corpus's one top-level `def fixture()` — an unrelated helper in another
file. A test suite with many `@pytest.fixture` functions turned that helper
into the report's top God Node.

The decorator edge now records the module its symbol was imported from
(`import pytest` / `import pytest as pt` / `from pytest import fixture`), and
the rewire only moves that edge onto a definition in that module's own file.
Decorators from corpus modules (`import myhelpers` → `@myhelpers.retry`) still
link; decorators with no import evidence keep the existing behaviour.
"""
from pathlib import Path

from graphify.extract import _file_stem, _make_id, extract


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _nid(rel: str, name: str) -> str:
    return _make_id(_file_stem(Path(rel)), name)


def _deco_targets(result: dict, owner: str) -> set[str]:
    return {e["target"] for e in result["edges"]
            if e.get("relation") == "references" and e.get("context") == "decorator"
            and e.get("source") == owner}


def _run(root: Path, files: dict[str, str]) -> dict:
    paths = [_write(root, rel, text) for rel, text in files.items()]
    return extract(paths, root=root, cache_root=root / "graphify-out")


HELPER = {"tests/test_helper.py": "def fixture():\n    return 'local helper'\n"}


def test_pytest_attribute_decorator_does_not_bind_to_a_local_def(tmp_path):
    """#2732's repro: `@pytest.fixture` functions all linked to the one local
    `def fixture()` in another file."""
    r = _run(tmp_path, {
        "tests/test_a.py": "import pytest\n\n@pytest.fixture\ndef env():\n    return 1\n\n"
                           "@pytest.fixture\ndef db():\n    return 2\n",
        **HELPER,
    })
    helper = _nid("tests/test_helper.py", "fixture")
    for fn in ("env", "db"):
        targets = _deco_targets(r, _nid("tests/test_a.py", fn))
        assert targets, f"{fn}() lost its decorator edge entirely"
        assert helper not in targets, f"{fn}() still references the unrelated local fixture()"


def test_aliased_module_decorator_does_not_bind_to_a_local_def(tmp_path):
    r = _run(tmp_path, {
        "tests/test_a.py": "import pytest as pt\n\n@pt.fixture\ndef env():\n    return 1\n",
        **HELPER,
    })
    assert _nid("tests/test_helper.py", "fixture") not in _deco_targets(r, _nid("tests/test_a.py", "env"))


def test_from_imported_decorator_does_not_bind_to_a_local_def(tmp_path):
    """`from pytest import fixture` + `@fixture`: the name is pytest's, not the
    local helper's."""
    r = _run(tmp_path, {
        "tests/test_a.py": "from pytest import fixture\n\n@fixture\ndef env():\n    return 1\n",
        **HELPER,
    })
    assert _nid("tests/test_helper.py", "fixture") not in _deco_targets(r, _nid("tests/test_a.py", "env"))


def test_corpus_module_attribute_decorator_still_links(tmp_path):
    """The control: `import myhelpers` + `@myhelpers.retry` must keep binding to
    the real `retry` defined in myhelpers.py."""
    r = _run(tmp_path, {
        "myhelpers.py": "def retry(fn):\n    return fn\n",
        "app.py": "import myhelpers\n\n@myhelpers.retry\ndef load():\n    return 1\n",
    })
    assert _nid("myhelpers.py", "retry") in _deco_targets(r, _nid("app.py", "load"))


def test_corpus_from_import_decorator_still_links(tmp_path):
    r = _run(tmp_path, {
        "myhelpers.py": "def retry(fn):\n    return fn\n",
        "app.py": "from myhelpers import retry\n\n@retry\ndef load():\n    return 1\n",
    })
    assert _nid("myhelpers.py", "retry") in _deco_targets(r, _nid("app.py", "load"))


def test_dotted_corpus_module_decorator_still_links(tmp_path):
    r = _run(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/tools.py": "def retry(fn):\n    return fn\n",
        "app.py": "import pkg.tools as tools\n\n@tools.retry\ndef load():\n    return 1\n",
    })
    assert _nid("pkg/tools.py", "retry") in _deco_targets(r, _nid("app.py", "load"))


def test_decorator_from_one_module_does_not_bind_to_a_def_in_another(tmp_path):
    """`@myhelpers.retry` names myhelpers' retry; a unique `retry` that lives in
    other.py is not it."""
    r = _run(tmp_path, {
        "myhelpers.py": "def unrelated():\n    return 0\n",
        "other.py": "def retry(fn):\n    return fn\n",
        "app.py": "import myhelpers\n\n@myhelpers.retry\ndef load():\n    return 1\n",
    })
    assert _nid("other.py", "retry") not in _deco_targets(r, _nid("app.py", "load"))


def test_decorator_without_import_evidence_keeps_existing_behaviour(tmp_path):
    """No import names the decorator, so there is no module to check against:
    the unique-definition rewire still applies, exactly as before."""
    r = _run(tmp_path, {
        "decos.py": "def traced(fn):\n    return fn\n",
        "app.py": "@traced\ndef load():\n    return 1\n",
    })
    assert _nid("decos.py", "traced") in _deco_targets(r, _nid("app.py", "load"))


def test_genuine_local_users_of_the_name_still_rewire(tmp_path):
    """The pytest edges stay off the helper, but a real bare reference to the
    helper in the same corpus still reaches it (the guard is per edge, not per stub)."""
    r = _run(tmp_path, {
        "tests/test_a.py": "import pytest\n\n@pytest.fixture\ndef env():\n    return 1\n",
        "tests/test_b.py": "@fixture\ndef other():\n    return 2\n",
        **HELPER,
    })
    helper = _nid("tests/test_helper.py", "fixture")
    assert helper not in _deco_targets(r, _nid("tests/test_a.py", "env"))
    assert helper in _deco_targets(r, _nid("tests/test_b.py", "other"))


# --- review follow-ups (graphify-labs bot on #4622) ---------------------------


def test_package_reexported_decorator_still_links_to_its_definition(tmp_path):
    """`from mypkg import retry` where mypkg/__init__.py re-exports retry from
    mypkg/decorators.py: the definition lives inside the package, so the rewire
    must still reach it (the module guard accepts files within the package)."""
    r = _run(tmp_path, {
        "mypkg/__init__.py": "from .decorators import retry\n",
        "mypkg/decorators.py": "def retry(fn):\n    return fn\n",
        "app.py": "from mypkg import retry\n\n@retry\ndef load():\n    return 1\n",
    })
    assert _nid("mypkg/decorators.py", "retry") in _deco_targets(r, _nid("app.py", "load"))


def test_decorator_reached_through_an_imported_object_keeps_existing_behaviour(tmp_path):
    """`from mylib import api` + `@api.route`: `api` is an object, not a
    submodule, so the edge must not claim a fake `mylib.api` module that blocks
    the rewire v8 already made onto mylib's `route`."""
    r = _run(tmp_path, {
        "mylib.py": "def route(fn):\n    return fn\n\n\nclass Api:\n    pass\n\n\napi = Api()\n",
        "app.py": "from mylib import api\n\n@api.route\ndef load():\n    return 1\n",
    })
    assert _nid("mylib.py", "route") in _deco_targets(r, _nid("app.py", "load"))
