"""An aliased imported call is linked from methods and decorated functions too.

``from .a import f as g`` then ``g()``: the bare-name pass cannot match ``g`` to
``f``, so the edge comes only from the import-aware symbol facts. Those facts
walked top-level ``def`` bodies only, and a decorated function is wrapped in a
``decorated_definition`` node, so the same call inside a method, a
``@staticmethod`` or any decorated function produced no ``calls`` edge at all.
Unaliased calls were unaffected because the bare name matched the definition.
Found in requests: ``from ._types import is_prepared as _is_prepared`` called
from ``HTTPAdapter`` methods.
"""

from __future__ import annotations

from pathlib import Path

from graphify.extract import extract

TARGET = "def f():\n    return 1\n"


def _calls_to_f(tmp_path: Path, caller_source: str) -> set[str]:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "a.py").write_text(TARGET)
    (pkg / "b.py").write_text(caller_source)
    result = extract(sorted(pkg.glob("*.py")), root=tmp_path, cache_root=tmp_path / "graphify-out")
    target = next(n["id"] for n in result["nodes"] if n.get("label") == "f()")
    return {e["source"] for e in result["edges"]
            if e.get("relation") == "calls" and e.get("target") == target}


def test_aliased_call_in_a_method_is_linked(tmp_path):
    callers = _calls_to_f(tmp_path, (
        "from .a import f as g\n\n"
        "class C:\n"
        "    def use(self):\n"
        "        return g()\n"
    ))
    assert callers == {"pkg_b_c_use"}


def test_aliased_call_in_a_staticmethod_is_linked(tmp_path):
    callers = _calls_to_f(tmp_path, (
        "from .a import f as g\n\n"
        "class C:\n"
        "    @staticmethod\n"
        "    def use():\n"
        "        return g()\n"
    ))
    assert callers == {"pkg_b_c_use"}


def test_aliased_call_in_a_decorated_function_is_linked(tmp_path):
    callers = _calls_to_f(tmp_path, (
        "import functools\n"
        "from .a import f as g\n\n"
        "@functools.lru_cache\n"
        "def use():\n"
        "    return g()\n"
    ))
    assert callers == {"pkg_b_use"}


def test_aliased_call_in_a_decorated_class_method_is_linked(tmp_path):
    callers = _calls_to_f(tmp_path, (
        "import dataclasses\n"
        "from .a import f as g\n\n"
        "@dataclasses.dataclass\n"
        "class C:\n"
        "    def use(self):\n"
        "        return g()\n"
    ))
    assert callers == {"pkg_b_c_use"}


def test_control_aliased_call_in_a_plain_function_still_linked(tmp_path):
    callers = _calls_to_f(tmp_path, (
        "from .a import f as g\n\n"
        "def use():\n"
        "    return g()\n"
    ))
    assert callers == {"pkg_b_use"}

