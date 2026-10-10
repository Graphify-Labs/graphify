"""Python `Foo(...)` call sites also reach the `__init__` that the call runs.

v8 links a constructor call only to the class node, and call reachability does
not follow the class's `method` edge, so everything `__init__` calls was
invisible from the call site. The added edge is emitted only when the run
`__init__` is provable from the class chain's own source: every class from the
called one up to the root is undecorated, has at most one plain base that
resolves to a project class through a same-file class or an import, and binds no
`__new__` / `__init_subclass__` / non-`def` `__init__`. Anything else (external
or attribute bases, metaclasses, decorators, multiple inheritance) emits
nothing new and keeps the v8 output. A module that could replace what
construction runs in a way the graph does not model (patching `__init__`,
computed `setattr`, `sys.modules`, `globals()`, rebinding `object`, writing an
imported module's attributes, ...) is refused as a whole.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from graphify.extract import extract


def _write_tree(root: Path, files: dict[str, str]) -> list[Path]:
    paths = []
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return sorted(paths)


def _extract(root: Path, files: dict[str, str]) -> dict:
    # Keep the per-file AST cache inside the test's own directory.
    return extract(_write_tree(root, files), root=root, cache_root=root, parallel=False)


def _nid(result: dict, label: str, source_file: str) -> str:
    matches = [
        n["id"] for n in result["nodes"]
        if n.get("label") == label and n.get("source_file") == source_file
    ]
    assert len(matches) == 1, (label, source_file, matches)
    return matches[0]


def _calls(result: dict, source: str) -> list[dict]:
    return [
        e for e in result["edges"]
        if e.get("relation") == "calls" and e.get("source") == source
    ]


def _reachable(result: dict, source: str) -> set[str]:
    """Node ids reachable from `source` over `calls` / `indirect_call` edges."""
    out: dict[str, set[str]] = {}
    for e in result["edges"]:
        if e.get("relation") in ("calls", "indirect_call"):
            out.setdefault(e["source"], set()).add(e["target"])
    seen, stack = set(), [source]
    while stack:
        for nxt in out.get(stack.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def _init_targets(result: dict, source: str) -> set[str]:
    """Ids of `__init__` nodes the given caller has a `calls` edge to."""
    labels = {n["id"]: n.get("label") for n in result["nodes"]}
    return {
        e["target"] for e in _calls(result, source)
        if labels.get(e["target"]) == ".__init__()"
    }


# --- positive cases ----------------------------------------------------------


def test_direct_init_gets_constructor_edge(tmp_path):
    result = _extract(tmp_path, {
        "app.py": (
            "def helper():\n    return 1\n\n\n"
            "class Service:\n"
            "    def __init__(self):\n"
            "        self.value = helper()\n\n\n"
            "def make():\n"
            "    return Service()\n"
        ),
    })
    make = _nid(result, "make()", "app.py")
    service = _nid(result, "Service", "app.py")
    init = _nid(result, ".__init__()", "app.py")

    by_target = {e["target"]: e for e in _calls(result, make)}
    # The v8 edge to the class is kept unchanged.
    assert by_target[service]["confidence"] == "EXTRACTED"
    assert by_target[service]["context"] == "call"
    # The new edge is a derived call: INFERRED, at the call site's location.
    added = by_target[init]
    assert added["confidence"] == "INFERRED"
    assert added["confidence_score"] == 0.85
    assert added["context"] == "constructor"
    assert added["source_file"] == "app.py"
    assert added["source_location"] == by_target[service]["source_location"]


def test_single_inherited_init_same_file(tmp_path):
    result = _extract(tmp_path, {
        "app.py": (
            "class Base:\n"
            "    def __init__(self, x):\n"
            "        self.x = x\n\n\n"
            "class Child(Base):\n"
            "    def run(self):\n"
            "        return self.x\n\n\n"
            "def make():\n"
            "    return Child(1)\n"
        ),
    })
    make = _nid(result, "make()", "app.py")
    base_init = _nid(result, ".__init__()", "app.py")
    assert _init_targets(result, make) == {base_init}


def test_aliased_import_and_mixed_line_link(tmp_path):
    """`T()` from `import Target as T` proves `Target`; a shadowed receiver on
    the same line (`console` is a parameter) does not cancel the proven call."""
    result = _extract(tmp_path, {
        "models.py": (
            "class Target:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
        "use.py": (
            "from models import Target as T\n\n\n"
            "def make():\n"
            "    return T()\n\n\n"
            "def show(console):\n"
            "    console.print(T())\n"
        ),
    })
    init = _nid(result, ".__init__()", "models.py")
    assert _init_targets(result, _nid(result, "make()", "use.py")) == {init}
    assert _init_targets(result, _nid(result, "show()", "use.py")) == {init}


def test_function_local_import_proves_the_call(tmp_path):
    """A `from m import Target` inside the caller (or an enclosing function),
    before the call, is the binding Python reads there."""
    result = _extract(tmp_path, {
        "models.py": (
            "class Target:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
        "use.py": (
            "def make():\n"
            "    from models import Target\n"
            "    return Target()\n"
        ),
        "nested.py": (
            "def outer():\n"
            "    from models import Target\n\n"
            "    def inner():\n"
            "        return Target()\n"
            "    return inner\n"
        ),
    })
    init = _nid(result, ".__init__()", "models.py")
    assert _init_targets(result, _nid(result, "make()", "use.py")) == {init}
    assert _init_targets(result, _nid(result, "inner()", "nested.py")) == {init}


def test_inherited_init_across_files_via_imports(tmp_path):
    """Absolute and relative imports both count as base-resolution evidence; the
    nearest `__init__` in the chain wins; an explicit `object` base is a root."""
    result = _extract(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/base.py": (
            "class Base(object):\n"
            "    def __init__(self):\n"
            "        self.ready = True\n"
        ),
        "pkg/mid.py": (
            "from .base import Base\n\n\n"
            "class Mid(Base):\n"
            "    pass\n\n\n"
            "class Override(Base):\n"
            "    def __init__(self):\n"
            "        super().__init__()\n"
        ),
        "pkg/leaf.py": (
            "from pkg.mid import Mid, Override\n\n\n"
            "class Leaf(Mid):\n"
            "    pass\n\n\n"
            "class LeafOverride(Override):\n"
            "    pass\n"
        ),
        "pkg/use.py": (
            "from pkg.leaf import Leaf, LeafOverride\n\n\n"
            "def make():\n"
            "    return Leaf()\n\n\n"
            "def make_override():\n"
            "    return LeafOverride()\n"
        ),
    })
    base_init = _nid(result, ".__init__()", "pkg/base.py")
    override_init = _nid(result, ".__init__()", "pkg/mid.py")
    assert _init_targets(result, _nid(result, "make()", "pkg/use.py")) == {base_init}
    assert _init_targets(
        result, _nid(result, "make_override()", "pkg/use.py")
    ) == {override_init}


# --- negative / fail-closed cases ---------------------------------------------
#
# Each case defines `Target` and calls it from `make()` in use.py. v8 resolves
# every one of these calls, and the test asserts that class edge exists, so the
# missing `__init__` edge is the guard's doing and not a resolution miss.

_HELPER = "def helper():\n    return 1\n\n\n"
_TARGET = "class Target:\n    def __init__(self):\n        self.x = 1\n"

_NEGATIVE_CASES: dict[str, dict[str, str]] = {
    # No __init__ anywhere in the chain: object.__init__ runs, nothing to link.
    "no_init_in_chain": {
        "models.py": "class Base:\n    pass\n\n\nclass Target(Base):\n    pass\n",
    },
    "metaclass_with_call": {
        "models.py": (
            _HELPER
            + "class Meta(type):\n"
            "    def __call__(cls, *args, **kwargs):\n"
            "        return None\n\n\n"
            "class Target(metaclass=Meta):\n"
            "    def __init__(self):\n"
            "        helper()\n"
        ),
    },
    # The definer is plain, but a metaclass above it controls construction.
    "metaclass_above_definer": {
        "models.py": (
            _HELPER
            + "class Meta(type):\n"
            "    def __call__(cls, *args, **kwargs):\n"
            "        return None\n\n\n"
            "class Root(metaclass=Meta):\n"
            "    pass\n\n\n"
            "class Target(Root):\n"
            "    def __init__(self):\n"
            "        helper()\n"
        ),
    },
    # @dataclass generates Target.__init__; Base.__init__ never runs.
    "dataclass_decorator": {
        "models.py": (
            "from dataclasses import dataclass\n\n\n"
            "class Base:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n\n\n"
            "@dataclass\n"
            "class Target(Base):\n"
            "    y: int = 0\n"
        ),
    },
    "class_decorator": {
        "models.py": (
            "def register(cls):\n    return cls\n\n\n"
            "@register\n"
            "class Target:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
    },
    # abc.ABC is an attribute base v8 records no edge for.
    "attribute_base": {
        "models.py": (
            "import abc\n\n\n"
            "class Target(abc.ABC):\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
    },
    "subscripted_base": {
        "models.py": (
            "from typing import Generic, TypeVar\n\n"
            "T = TypeVar('T')\n\n\n"
            "class Target(Generic[T]):\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
    },
    "multiple_inheritance": {
        "models.py": (
            "class A:\n    def __init__(self):\n        self.a = 1\n\n\n"
            "class B:\n    pass\n\n\n"
            "class Target(A, B):\n    pass\n"
        ),
    },
    "new_on_class": {
        "models.py": (
            "class Target:\n"
            "    def __new__(cls):\n"
            "        return object.__new__(cls)\n\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
    },
    "new_above_definer": {
        "models.py": (
            "class Root:\n"
            "    def __new__(cls):\n"
            "        return 42\n\n\n"
            "class Target(Root):\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
    },
    "staticmethod_init": {
        "models.py": "class Target:\n    @staticmethod\n    def __init__(self):\n        self.x = 1\n",
    },
    "classmethod_init": {
        "models.py": "class Target:\n    @classmethod\n    def __init__(cls):\n        cls.x = 1\n",
    },
    "callable_instance_init": {
        "models.py": (
            "class Init:\n    def __call__(self, obj):\n        obj.x = 1\n\n\n"
            "class Target:\n    __init__ = Init()\n"
        ),
    },
    "lambda_init": {"models.py": "class Target:\n    __init__ = lambda self: None\n"},
    "assigned_init": {
        "models.py": (
            "def other_init(self):\n    self.x = 1\n\n\n"
            "class Base:\n"
            "    def __init__(self):\n"
            "        self.x = 0\n\n\n"
            "class Target(Base):\n"
            "    __init__ = other_init\n"
        ),
    },
    # A def under `if` may or may not exist at runtime.
    "conditional_init": {
        "models.py": (
            "import sys\n\n\n"
            "class Base:\n"
            "    def __init__(self):\n"
            "        self.x = 0\n\n\n"
            "class Target(Base):\n"
            "    if sys.version_info > (3,):\n"
            "        def __init__(self):\n"
            "            self.x = 1\n"
        ),
    },
    "init_patched_after_class": {
        "models.py": (
            "def other_init(self):\n    self.x = 1\n\n\n"
            "class Target:\n"
            "    def __init__(self):\n"
            "        self.x = 0\n\n\n"
            "Target.__init__ = other_init\n"
        ),
    },
    "init_subclass_on_base": {
        "models.py": (
            "class Base:\n"
            "    def __init_subclass__(cls, **kwargs):\n"
            "        cls.__init__ = lambda self: None\n\n"
            "    def __init__(self):\n"
            "        self.x = 0\n\n\n"
            "class Target(Base):\n"
            "    pass\n"
        ),
    },
    # Any `__init_subclass__` on the chain can rebind the subclass's methods.
    "init_subclass_plain": {
        "models.py": (
            "class Base:\n"
            "    def __init_subclass__(cls, **kwargs):\n"
            "        super().__init_subclass__(**kwargs)\n\n"
            "    def __init__(self):\n"
            "        self.x = 0\n\n\n"
            "class Target(Base):\n"
            "    pass\n"
        ),
    },
    # Any decorator on `__init__` can replace it; this one drops the body.
    "decorated_init": {
        "models.py": (
            _HELPER
            + "def replace(fn):\n    return lambda self: None\n\n\n"
            "class Target:\n"
            "    @replace\n"
            "    def __init__(self):\n"
            "        helper()\n"
        ),
    },
    # The second `def` replaces the first; v8 merges both bodies into one node.
    "duplicate_init": {
        "models.py": (
            _HELPER
            + "class Target:\n"
            "    def __init__(self):\n"
            "        helper()\n\n"
            "    def __init__(self):\n"
            "        pass\n"
        ),
    },
    # A function in the module can replace `__init__` before construction.
    "init_patched_in_function": {
        "models.py": (
            "class Target:\n"
            "    def __init__(self):\n"
            "        self.x = 0\n\n\n"
            "def patch():\n"
            "    Target.__init__ = lambda self: None\n"
        ),
    },
    # Every structural way to replace `__init__` after the class body ran.
    "patch_annotated": {"models.py": _TARGET + "\n\nTarget.__init__: object = lambda self: None\n"},
    "patch_parenthesized": {"models.py": _TARGET + "\n\n(Target.__init__) = lambda self: None\n"},
    "patch_tuple_target": {"models.py": _TARGET + "\n\nTarget.__init__, other = (lambda self: None), 1\n"},
    "patch_starred_target": {"models.py": _TARGET + "\n\nfirst, *Target.__init__ = 1, 2\n"},
    "patch_augmented": {"models.py": _TARGET + "\n\nTarget.__init__ += 0\n"},
    "patch_del": {"models.py": _TARGET + "\n\ndel Target.__init__\n"},
    "patch_delattr": {"models.py": _TARGET + '\n\ndelattr(Target, "__init__")\n'},
    "patch_setattr_new": {"models.py": _TARGET + "\n\nsetattr(Target, '__new__', staticmethod(lambda cls: None))\n"},
    # The base import shares its line with another import statement.
    "semicolon_base_import": {
        "widgets.py": "class Widget:\n    def __init__(self):\n        self.x = 1\n",
        "models.py": (
            "from somelib import Widget; from widgets import Widget as W\n\n\n"
            "class Target(Widget):\n"
            "    pass\n"
        ),
    },
    # The base comes through a re-export, which could rebind it.
    "base_through_reexport": {
        "pkgbase/__init__.py": "from .impl import Base\n",
        "pkgbase/impl.py": "class Base:\n    def __init__(self):\n        self.x = 1\n",
        "models.py": "from pkgbase import Base\n\n\nclass Target(Base):\n    pass\n",
    },
    # Only module-level classes qualify; here `object` is rebound in the outer
    # class body, and the nested class is exported under the module name.
    "nested_class_object_shadow": {
        "models.py": (
            "class Evil(type):\n"
            "    def __call__(cls):\n"
            "        return None\n\n\n"
            "class Base(metaclass=Evil):\n"
            "    pass\n\n\n"
            "class Outer:\n"
            "    object = Base\n\n"
            "    class Target(object):\n"
            "        def __init__(self):\n"
            "            self.x = 1\n\n\n"
            "Target = Outer.Target\n"
        ),
    },
    # `object` is the builtin only if no scope of the module binds it.
    "object_bound_in_function": {
        "models.py": (
            "def configure(object):\n    return object\n\n\n"
            "class Target(object):\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
    },
    # A function can rebind the module-level class name through `global`.
    "global_rebinding": {
        "models.py": (
            "class Target:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n\n\n"
            "def swap(factory):\n"
            "    global Target\n"
            "    Target = factory\n"
        ),
    },
    # Python 2 metaclass hook in the class body.
    "py2_metaclass_attribute": {
        "models.py": (
            "class Meta(type):\n"
            "    def __call__(cls, *args, **kwargs):\n"
            "        return None\n\n\n"
            "class Target(object):\n"
            "    __metaclass__ = Meta\n\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
    },
    # Builtin base: Enum's metaclass looks members up instead of running __init__.
    "external_enum_base": {
        "models.py": (
            "from enum import Enum\n\n\n"
            "class Target(Enum):\n"
            "    RED = 1\n\n"
            "    def __init__(self, value):\n"
            "        self.code = value\n"
        ),
    },
    # v8's inherits edge binds this base to the project's own `Widget` by label,
    # but the module imports it from an external package.
    "external_base_same_label": {
        "widgets.py": (
            "class Widget:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
        "models.py": (
            "from somelib import Widget\n\n\n"
            "class Target(Widget):\n"
            "    pass\n"
        ),
    },
    # A function-level import must not stand in for the module-level binding.
    "function_import_evidence": {
        "widgets.py": (
            "class Widget:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
        "models.py": (
            "from somelib import Widget\n\n\n"
            "def load():\n"
            "    from widgets import Widget as W\n"
            "    return W\n\n\n"
            "class Target(Widget):\n"
            "    pass\n"
        ),
    },
    "base_bound_twice": {
        "widgets.py": (
            "class Widget:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
        "models.py": (
            "try:\n"
            "    from widgets import Widget\n"
            "except ImportError:\n"
            "    pass\n"
            "from somelib import Widget\n\n\n"
            "class Target(Widget):\n"
            "    pass\n"
        ),
    },
    "star_import_can_rebind_base": {
        "models.py": (
            "class Base:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n\n\n"
            "from somelib import *\n\n\n"
            "class Target(Base):\n"
            "    pass\n"
        ),
    },
    "type_parameters": {
        "models.py": (
            "class Target[T]:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
    },
    # A manual decoration rebinds the name: `Target(...)` calls the wrapper.
    "class_name_rebound": {
        "models.py": (
            "def wrap(cls):\n    return lambda *a: None\n\n\n"
            "class Target:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n\n\n"
            "Target = wrap(Target)\n"
        ),
    },
    # A decorator anywhere on the chain can replace the class or its `__init__`.
    "decorated_ancestor": {
        "models.py": (
            "def register(cls):\n    return cls\n\n\n"
            "@register\n"
            "class Base:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n\n\n"
            "class Target(Base):\n"
            "    pass\n"
        ),
    },
    # The class name is rebound after its definition: a loop target, a later import.
    "class_name_loop_rebound": {"models.py": _TARGET + "\n\nfor Target in [Target]:\n    pass\n"},
    "class_name_reimported": {"models.py": _TARGET + "\n\nfrom somelib import Target\n"},
    # The base is imported from a project module that re-exports an external
    # class; a same-named project class must not stand in for it.
    "reexported_external_base": {
        "compat.py": "from somelib import Widget\n",
        "widgets.py": (
            "class Widget:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
        "models.py": (
            "from compat import Widget\n\n\n"
            "class Target(Widget):\n"
            "    pass\n"
        ),
    },
}


@pytest.mark.parametrize("case", sorted(_NEGATIVE_CASES))
def test_unprovable_constructor_emits_no_init_edge(tmp_path, case):
    files = dict(_NEGATIVE_CASES[case])
    files["use.py"] = (
        "from models import Target\n\n\n"
        "def make():\n"
        "    return Target()\n"
    )
    result = _extract(tmp_path, files)
    make = _nid(result, "make()", "use.py")
    target = _nid(result, "Target", "models.py")
    assert target in {e["target"] for e in _calls(result, make)}, (
        "fixture must resolve the call, or the guard is not what is tested"
    )
    assert _init_targets(result, make) == set()


# v8 binds each `Target()` below to the project class even though, at runtime,
# the name is a parameter, local, loop variable, a later module rebinding, or
# whatever a star import binds. A name bound more than once anywhere in the
# file proves no call at all, so `genuine()`, which does read the import, gets
# no edge either (except where the twice-bound name is the alias `T`).
_SHADOWED_CALLERS: dict[str, str] = {
    "parameter": "def make(Target):\n    return Target()\n",
    "local_assignment": "def make():\n    Target = dict\n    return Target()\n",
    "loop_variable": "def make(classes):\n    for Target in classes:\n        Target()\n",
    "local_import": "def make():\n    from other import Target\n    return Target()\n",
    "enclosing_function_local": (
        "def make(Target):\n"
        "    def inner():\n"
        "        return Target()\n"
        "    return inner()\n"
    ),
    "nested_function_parameter": (
        "def make():\n"
        "    def inner(Target):\n"
        "        return Target()\n"
        "    return inner\n"
    ),
    "aliased_import_parameter": (
        "from models import Target as T\n\n\n"
        "def make(T):\n    return T()\n"
    ),
    "star_import": "from other import *\n\n\ndef make():\n    return Target()\n",
    "lambda_parameter": "def make():\n    return (lambda Target: Target())(dict)\n",
    "class_body_in_function": (
        "def make(Target):\n"
        "    class Local:\n"
        "        made = Target()\n"
        "    return Local\n"
    ),
    "module_rebinding": (
        "def wrap(cls):\n    return cls\n\n\n"
        "Target = wrap(Target)\n\n\n"
        "def make():\n    return Target()\n"
    ),
}


@pytest.mark.parametrize("case", sorted(_SHADOWED_CALLERS))
def test_shadowed_call_site_emits_no_init_edge(tmp_path, case):
    result = _extract(tmp_path, {
        "models.py": (
            "class Target:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
        "use.py": (
            "from models import Target\n\n\n"
            + _SHADOWED_CALLERS[case]
            + "\n\ndef genuine():\n    return Target()\n"
        ),
    })
    make = _nid(result, "make()", "use.py")
    genuine = _nid(result, "genuine()", "use.py")
    target = _nid(result, "Target", "models.py")
    assert target in {e["target"] for e in _calls(result, make)}
    assert target in {e["target"] for e in _calls(result, genuine)}
    assert _init_targets(result, make) == set()
    # Only `T` is bound twice there; `Target` itself is bound once.
    expected = {_nid(result, ".__init__()", "models.py")} if case == "aliased_import_parameter" else set()
    assert _init_targets(result, genuine) == expected


def test_name_bound_once_proves_the_call(tmp_path):
    """The same caller file without the second binding links both calls."""
    result = _extract(tmp_path, {
        "models.py": "class Target:\n    def __init__(self):\n        self.x = 1\n",
        "use.py": (
            "from models import Target\n\n\n"
            "def make():\n    return Target()\n\n\n"
            "def genuine():\n    return Target()\n"
        ),
    })
    init = _nid(result, ".__init__()", "models.py")
    assert _init_targets(result, _nid(result, "make()", "use.py")) == {init}
    assert _init_targets(result, _nid(result, "genuine()", "use.py")) == {init}


# Each form binds `Target` a second time somewhere in the file, in a scope that
# `make()` may or may not read; the whole-file rule refuses all of them.
_SECOND_BINDINGS: dict[str, str] = {
    "default_walrus": "def configure(x=(Target := lambda: None)):\n    pass\n",
    "base_walrus": "class Wrapper((Target := object)):\n    pass\n",
    "decorator_walrus": "@(Target := (lambda f: f))\ndef decorated():\n    pass\n",
    "type_parameter": "def generic[Target]():\n    return None\n",
    "other_function_parameter": "def other(Target):\n    return Target\n",
    "lambda_parameter": "other = lambda Target: Target\n",
    "comprehension_target": "def other(xs):\n    return [Target for Target in xs]\n",
    "except_target": "def other():\n    try:\n        pass\n    except Exception as Target:\n        pass\n",
    "with_target": "def other(cm):\n    with cm as Target:\n        pass\n",
    "match_capture": "def other(x):\n    match x:\n        case Target:\n            pass\n",
    "nonlocal": "def outer():\n    Target = 1\n\n    def inner():\n        nonlocal Target\n        Target = 2\n    return inner\n",
    "global_then_del": "def other():\n    global Target\n    del Target\n",
    "import_alias": "def other():\n    import json as Target\n    return Target\n",
    "annotated_value": "def other():\n    Target: int = 1\n    return Target\n",
}


@pytest.mark.parametrize("case", sorted(_SECOND_BINDINGS))
def test_second_binding_anywhere_refuses_the_call(tmp_path, case):
    result = _extract(tmp_path, {
        "models.py": "class Target:\n    def __init__(self):\n        self.x = 1\n",
        "use.py": (
            "from models import Target\n\n\n" + _SECOND_BINDINGS[case]
            + "\n\ndef make():\n    return Target()\n"
        ),
    })
    make = _nid(result, "make()", "use.py")
    assert _nid(result, "Target", "models.py") in {e["target"] for e in _calls(result, make)}
    assert _init_targets(result, make) == set()


_MODEL = "class Model:\n    def __init__(self):\n        self.rows = []\n"


@pytest.mark.parametrize("use, linked", [
    ("import models\n\n\ndef make():\n    return models.Model()\n", True),
    ("import models as m\n\n\ndef make():\n    return m.Model()\n", True),
    ("import models\n\n\ndef make(models):\n    return models.Model()\n", False),
    ("import models\n\n\ndef make():\n    models = object()\n"
     "    return models.Model()\n", False),
    ("import models\n\nmodels = None\n\n\ndef make():\n"
     "    return models.Model()\n", False),
    # The module escapes into another name, which can write to it.
    ("import models\n\nalias = models\n\n\ndef make():\n    return models.Model()\n", False),
    ("import models\n\n\ndef register(m):\n    return m\n\n\nregister(models)\n\n\n"
     "def make():\n    return models.Model()\n", False),
    ("import models\n\n\ndef handle():\n    return models\n\n\n"
     "def make():\n    return models.Model()\n", False),
])
def test_module_receiver_must_be_the_imported_module(tmp_path, use, linked):
    """v8 resolves `models.Model()` to the class even when `models` is a
    parameter, a local, rebound, or escapes; only a plain `import` of a
    top-level module that is used only for attribute reads counts."""
    result = _extract(tmp_path, {"models.py": _MODEL, "use.py": use})
    make = _nid(result, "make()", "use.py")
    model = _nid(result, "Model", "models.py")
    assert model in {e["target"] for e in _calls(result, make)}
    expected = {_nid(result, ".__init__()", "models.py")} if linked else set()
    assert _init_targets(result, make) == expected


@pytest.mark.parametrize("use", [
    "from pkg import models\n\n\ndef make():\n    return models.Model()\n",
    "import pkg.models as models\n\n\ndef make():\n    return models.Model()\n",
])
def test_submodule_receiver_proves_nothing(tmp_path, use):
    """`pkg/__init__.py` can bind `models` to anything, and `from pkg import
    models` then returns that instead of the submodule."""
    result = _extract(tmp_path, {"pkg/__init__.py": "", "pkg/models.py": _MODEL, "use.py": use})
    make = _nid(result, "make()", "use.py")
    assert _nid(result, "Model", "pkg/models.py") in {e["target"] for e in _calls(result, make)}
    assert _init_targets(result, make) == set()


def test_case_folded_module_attribute_emits_no_init_edge(tmp_path):
    """v8 matches `config.settings()` to class `_Settings` after folding case and
    underscores; the call runs the module-level instance's `__call__`."""
    result = _extract(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/config.py": (
            "class _Settings:\n"
            "    def __init__(self):\n"
            "        self.v = 1\n\n"
            "    def __call__(self):\n"
            "        return self.v\n\n\n"
            "settings = _Settings()\n"
        ),
        "pkg/use.py": "from pkg import config\n\n\ndef make():\n    return config.settings()\n",
    })
    make = _nid(result, "make()", "pkg/use.py")
    assert _nid(result, "_Settings", "pkg/config.py") in {e["target"] for e in _calls(result, make)}
    assert _init_targets(result, make) == set()


def test_self_attribute_call_emits_no_init_edge(tmp_path):
    """v8 binds `self.Widget()` to the same-file class `Widget`, but the
    attribute holds whatever factory the instance was given."""
    result = _extract(tmp_path, {
        "m.py": (
            "class Widget:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n\n\n"
            "class Panel:\n"
            "    def __init__(self, factory=Widget):\n"
            "        self.Widget = factory\n\n"
            "    def make(self):\n"
            "        return self.Widget()\n"
        ),
    })
    make = _nid(result, ".make()", "m.py")
    assert _nid(result, "Widget", "m.py") in {e["target"] for e in _calls(result, make)}
    assert _init_targets(result, make) == set()


def test_import_in_other_function_does_not_prove_module_binding(tmp_path):
    """`make()` reads the module-level `somelib.Target`; the project import in
    `load()` is a different binding, even though v8 resolves through it."""
    result = _extract(tmp_path, {
        "models.py": (
            "class Target:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
        "use.py": (
            "from somelib import Target\n\n\n"
            "def load():\n"
            "    from models import Target\n"
            "    return Target\n\n\n"
            "def make():\n"
            "    return Target()\n"
        ),
    })
    make = _nid(result, "make()", "use.py")
    assert _nid(result, "Target", "models.py") in {e["target"] for e in _calls(result, make)}
    assert _init_targets(result, make) == set()


@pytest.mark.parametrize("files", [
    # Two import statements on one line: the project import's edge must not
    # stand in for the external binding that `Target` reads.
    {"use.py": (
        "from somelib import Target; from models import Target as T\n\n\n"
        "def make():\n    return Target()\n"
    )},
    # Imported through a re-export: the package could rebind the name.
    {"pkg/__init__.py": "from .models import Target\n",
     "use.py": "from pkg import Target\n\n\ndef make():\n    return Target()\n"},
    {"pkg/__init__.py": "from .models import Target\nTarget = lambda: None\n",
     "use.py": "from pkg import Target\n\n\ndef make():\n    return Target()\n"},
    {"pkg/__init__.py": "from .models import Target\nfrom somelib import *\n",
     "use.py": "from pkg import Target\n\n\ndef make():\n    return Target()\n"},
], ids=["semicolon_import", "reexport", "reexport_rebound", "reexport_then_star"])
def test_call_binding_must_name_the_defining_module(tmp_path, files):
    model = "pkg/models.py" if "pkg/__init__.py" in files else "models.py"
    result = _extract(tmp_path, {model: _TARGET, **files})
    make = _nid(result, "make()", "use.py")
    target = _nid(result, "Target", model)
    if not files.get("pkg/__init__.py", "").endswith("lambda: None\n"):
        assert target in {e["target"] for e in _calls(result, make)}
    assert _init_targets(result, make) == set()


@pytest.mark.parametrize("case", ["decorated_init", "duplicate_init"])
def test_replaced_init_body_is_unreachable(tmp_path, case):
    """The body that never runs (replaced by a decorator, or overwritten by a
    second `def`) must not become reachable from the constructor call."""
    files = dict(_NEGATIVE_CASES[case])
    files["use.py"] = "from models import Target\n\n\ndef make():\n    return Target()\n"
    result = _extract(tmp_path, files)
    helper = _nid(result, "helper()", "models.py")
    assert helper not in _reachable(result, _nid(result, "make()", "use.py"))


# --- standard-library module names ------------------------------------------------
#
# Built-in and frozen modules win over a local file of the same name, and for a
# script run from its own directory so can the rest of the standard library. An
# absolute import whose top-level name is a standard-library or built-in module
# (_PYTHON_STDLIB_MODULE_NAMES) proves no local class, for calls and for bases.

_STDLIB_SHADOWS = {
    "module": (
        "time.py",
        "class struct_time:\n    def __init__(self, values):\n        raise AssertionError('local initializer ran')\n",
        "import time\n\n\ndef make():\n    return time.struct_time((2026, 10, 7, 0, 0, 0, 2, 280, -1))\n",
    ),
    "from": (
        "time.py",
        "class struct_time:\n    def __init__(self, values):\n        raise AssertionError('local initializer ran')\n",
        "from time import struct_time\n\n\ndef make():\n    return struct_time((2026, 10, 7, 0, 0, 0, 2, 280, -1))\n",
    ),
    "inherited": (
        "_collections.py",
        "class deque:\n    def __init__(self):\n        raise AssertionError('local initializer ran')\n",
        "from _collections import deque\n\n\nclass Child(deque):\n    pass\n\n\ndef make():\n    return Child()\n",
    ),
}


@pytest.mark.parametrize("style", sorted(_STDLIB_SHADOWS))
def test_stdlib_module_name_proves_nothing(tmp_path, style):
    filename, model, use = _STDLIB_SHADOWS[style]
    files = {filename: model, "use.py": use}
    run = tmp_path / "run"
    _write_tree(run, files)
    runtime = subprocess.run(
        [sys.executable, "-B", "-c", "import use; use.make()"], cwd=run, capture_output=True, text=True,
    )
    assert runtime.returncode == 0, runtime.stderr  # the local initializer never runs
    result = _extract(tmp_path / "graph", files)
    make = _nid(result, "make()", "use.py")
    assert _init_targets(result, make) == set()


@pytest.mark.parametrize("use", [
    "from .time import Clock\n\n\ndef make():\n    return Clock()\n",
    "from pkg.time import Clock\n\n\ndef make():\n    return Clock()\n",
], ids=["relative", "package"])
def test_local_module_with_a_stdlib_name_inside_a_package_keeps_the_edge(tmp_path, use):
    """`pkg/time.py` reached as `.time` or `pkg.time` is the local file."""
    result = _extract(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/time.py": "class Clock:\n    def __init__(self):\n        self.t = 0\n",
        "pkg/use.py": use,
    })
    make = _nid(result, "make()", "pkg/use.py")
    assert _init_targets(result, make) == {_nid(result, ".__init__()", "pkg/time.py")}


# --- node id collisions ----------------------------------------------------------
#
# v8 mints a method id from the class id and the name with its underscores
# stripped (`__init__` and `init` both give `app_target_init`), and a module
# function from the file stem and its name (`target_init` gives the same id).
# Two definitions on one id merge into one node, calls included, so a class
# whose own id or `__init__` id another definition claims gets no marker.

_HELPER = 'def helper():\n    raise AssertionError("the other body ran")\n\n\n'
_INIT = "    def __init__(self):\n        self.ready = True\n"
# case -> (code before the class, inside it after `__init__`, after it), and
# whether v8 merges the other definition into the `__init__` node. v8 already
# gives a separate id to a plain `def` whose name collides at module or class
# level (#3302), but not to a decorated one.
_COLLIDING: dict[str, tuple[str, str, str, bool]] = {
    "staticmethod_init": ("", "\n    @staticmethod\n    def init():\n        helper()\n", "", True),
    "classmethod_init": ("", "\n    @classmethod\n    def Init(cls):\n        helper()\n", "", True),
    "property_init": ("", "\n    @property\n    def _init(self):\n        return helper()\n", "", True),
    "decorated_function_before": (
        "import functools\n\n\n@functools.cache\ndef {name}_init():\n    helper()\n\n\n", "", "", True,
    ),
    "decorated_function_after": (
        "import functools\n\n\n", "", "\n\n@functools.cache\ndef {name}_init():\n    helper()\n", True,
    ),
    "plain_function_before": ("def {name}_init():\n    helper()\n\n\n", "", "", False),
    "plain_function_after": ("", "", "\n\ndef {name}_init():\n    helper()\n", False),
    "conditional_method": ("", "\n    if True:\n        def init(self):\n            helper()\n", "", False),
    "nested_function": (
        "", "\n    def setup(self):\n        def init():\n            helper()\n        return init\n", "", False,
    ),
}


def _collision_module(case: str, inherited: bool) -> str:
    before, inside, after, _ = _COLLIDING[case]
    cls = "Base" if inherited else "Target"
    code = _HELPER + before.format(name=cls.lower()) + f"class {cls}:\n" + _INIT + inside
    code += after.format(name=cls.lower())
    if inherited:
        code += "\n\nclass Target(Base):\n    pass\n"
    return code + "\n\ndef make():\n    return Target()\n"


@pytest.mark.parametrize("inherited", [False, True], ids=["direct", "inherited"])
@pytest.mark.parametrize("case", sorted(_COLLIDING))
def test_shared_init_id_gets_no_edge(tmp_path, case, inherited):
    """Where v8 merges another definition into the `__init__` node (the same
    id, both bodies' calls), the class and its subclasses get no edge; where
    v8 keeps them apart, the edge stays. The other body is never reachable."""
    code = _collision_module(case, inherited)
    namespace: dict = {}
    exec(compile(code, "app.py", "exec"), namespace)
    assert namespace["make"]().ready  # `__init__` runs; the other body does not
    result = _extract(tmp_path, {"app.py": code})
    make = _nid(result, "make()", "app.py")
    init = "app_base_init" if inherited else "app_target_init"
    merges = _COLLIDING[case][3]
    if merges:
        helper = _nid(result, "helper()", "app.py")
        assert helper in {e["target"] for e in _calls(result, init)}  # one node, two bodies
        assert _init_targets(result, make) == set()
    else:
        assert len(_init_targets(result, make)) == 1
    assert _nid(result, "Target", "app.py") in {e["target"] for e in _calls(result, make)}
    assert _nid(result, "helper()", "app.py") not in _reachable(result, make)


def test_class_id_shared_with_a_function_keeps_the_edge(tmp_path):
    """rich's `class Group` and `def group` share `rich_console_group`. The
    function's calls land on the class node (v8's class edge already reaches
    them), but no method edge or base comes from a function, so `__init__`
    is still the class's own and the edge stays."""
    code = (
        _HELPER + "class Target:\n" + _INIT + "\n\ndef target():\n    helper()\n"
        "\n\ndef make():\n    return Target()\n"
    )
    result = _extract(tmp_path, {"app.py": code})
    make = _nid(result, "make()", "app.py")
    assert _init_targets(result, make) == {"app_target_init"}
    assert _nid(result, "helper()", "app.py") not in {e["target"] for e in _calls(result, "app_target_init")}


def test_salted_init_keeps_the_edge(tmp_path):
    """v8 gives a direct `def init` beside `__init__` its own id (#3302), so
    nothing merges and the edge stays."""
    code = _HELPER + "class Target:\n" + _INIT + "\n    def init(self):\n        helper()\n\n\ndef make():\n    return Target()\n"
    result = _extract(tmp_path, {"app.py": code})
    make = _nid(result, "make()", "app.py")
    (init,) = _init_targets(result, make)
    assert init != "app_target_init"
    assert _nid(result, "helper()", "app.py") not in _reachable(result, make)


@pytest.mark.parametrize("new", [
    "\n    @staticmethod\n    def new():\n        return None\n\n    def __new__(cls):\n        return object.__new__(cls)\n",
    "\n    def __new__(cls):\n        return object.__new__(cls)\n\n    @staticmethod\n    def new():\n        return None\n",
], ids=["new_first", "dunder_first"])
def test_new_behind_a_shared_id_still_refuses(tmp_path, new):
    """A `__new__` that shares its id with `new` is still a `__new__`: the
    class body rule refuses it by name, whichever node keeps the id."""
    code = _HELPER + "class Target:\n" + _INIT + new + "\n\ndef make():\n    return Target()\n"
    result = _extract(tmp_path, {"app.py": code})
    assert _init_targets(result, _nid(result, "make()", "app.py")) == set()


def test_method_named_new_keeps_the_edge(tmp_path):
    code = _HELPER + "class Target:\n" + _INIT + "\n    @staticmethod\n    def new():\n        helper()\n\n\ndef make():\n    return Target()\n"
    result = _extract(tmp_path, {"app.py": code})
    assert _init_targets(result, _nid(result, "make()", "app.py")) == {"app_target_init"}


def test_shared_init_id_survives_cache_and_incremental_builds(tmp_path):
    """The refusal is the stored marker, so a cached rebuild and a relink after
    an incremental build of the caller see it too."""
    from graphify.watch import _rebuild_code

    files = {
        "models.py": _HELPER + "class Target:\n" + _INIT + "\n    @staticmethod\n    def init():\n        helper()\n",
        "use.py": "from models import Target\n\n\ndef make():\n    return Target()\n",
    }
    for _ in range(2):  # the second extraction reads the AST cache
        result = _extract(tmp_path / "cached", files)
        assert _init_targets(result, _nid(result, "make()", "use.py")) == set()
    corpus = tmp_path / "corpus"
    _write_tree(corpus, files)
    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    changed = _write_tree(corpus, {"use.py": files["use.py"] + "# edited\n"})
    assert _rebuild_code(corpus, changed_paths=changed, no_cluster=True, acquire_lock=False) is True
    graph = json.loads((corpus / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    assert not [e for e in graph["links"] if e.get("context") == "constructor"]
    assert not any(n.get("_py_ctor_chain") for n in graph["nodes"])


def test_unbound_call_name_emits_no_init_edge(tmp_path):
    """`Target` is never bound in use.py (a NameError at runtime); the file-level
    import of models.py must not make the call a constructor entry."""
    result = _extract(tmp_path, {
        "models.py": (
            "def helper():\n    return 1\n\n\n"
            "class Target:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
        "use.py": "from models import helper\n\n\ndef make():\n    return Target()\n",
    })
    assert _init_targets(result, _nid(result, "make()", "use.py")) == set()


def test_import_in_another_function_emits_no_init_edge(tmp_path):
    """v8 binds `Request()` in `make()` through an import that only `load()`
    makes; in `make()` the name is unbound."""
    result = _extract(tmp_path, {
        "models.py": (
            "class Request:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
        "use.py": (
            "def load():\n"
            "    from models import Request\n"
            "    return Request\n\n\n"
            "def make():\n"
            "    return Request()\n"
        ),
    })
    make = _nid(result, "make()", "use.py")
    assert _nid(result, "Request", "models.py") in {e["target"] for e in _calls(result, make)}
    assert _init_targets(result, make) == set()


def test_builtin_named_call_emits_no_init_edge(tmp_path):
    """Unbound `Warning()` is the builtin at runtime, but v8 binds it to the
    project class `Warning` through the file-level `import models`."""
    result = _extract(tmp_path, {
        "models.py": (
            "class Warning:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
        "use.py": "import models\n\n\ndef make():\n    return Warning()\n",
    })
    make = _nid(result, "make()", "use.py")
    assert _nid(result, "Warning", "models.py") in {e["target"] for e in _calls(result, make)}
    assert _init_targets(result, make) == set()


def test_ambiguous_class_name_emits_no_init_edge(tmp_path):
    """Two project classes named `Target` and an unimported bare call: v8 binds
    nothing, so nothing is added."""
    result = _extract(tmp_path, {
        "a.py": "class Target:\n    def __init__(self):\n        self.x = 1\n",
        "b.py": "class Target:\n    def __init__(self):\n        self.x = 2\n",
        "use.py": "def make():\n    return Target()\n",
    })
    assert _init_targets(result, _nid(result, "make()", "use.py")) == set()


def test_class_reference_and_annotation_emit_no_init_edge(tmp_path):
    """Only a call expression runs `__init__`: passing, returning, or annotating
    the class adds nothing."""
    result = _extract(tmp_path, {
        "models.py": (
            "class Target:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
        "use.py": (
            "from models import Target\n\n\n"
            "def register(cls):\n    return cls\n\n\n"
            "def passes():\n"
            "    return register(Target)\n\n\n"
            "def returns():\n"
            "    return Target\n\n\n"
            "def annotated(item: Target) -> Target:\n"
            "    return item\n"
        ),
    })
    for caller in ("passes()", "returns()", "annotated()"):
        assert _init_targets(result, _nid(result, caller, "use.py")) == set(), caller


# --- module-wide allowlists ---------------------------------------------------
#
# Each module below replaces what `Target()` runs, or rebinds a name the proof
# reads, in a way the graph does not model. The module is loaded and `make()`
# called first, to show that the original `__init__` really does not run; then
# v8 must still bind the call to the class, and no constructor edge may exist.

_ORIGINAL_INIT = (
    "class Target:\n"
    "    def __init__(self):\n"
    "        raise AssertionError('original init ran')\n"
)
_RAISING_BASE = (
    "class Base:\n"
    "    def __init__(self):\n"
    "        raise AssertionError('original init ran')\n"
)
_NONE_META = (
    "class Meta(type):\n"
    "    def __call__(cls):\n"
    "        return None\n\n\n"
    "class Fake(metaclass=Meta):\n"
    "    pass\n\n\n"
    "object = Fake\n\n\n"
)
_MAKE = "\n\ndef make():\n    return Target()\n"
_SWAPS: dict[str, str] = {
    # Code run in a class body reads the class namespace first.
    "class_body_shadow": _ORIGINAL_INIT + (
        "\n\ndef make():\n"
        "    class Consumer:\n"
        "        Target = lambda: None\n"
        "        value = Target()\n"
        "    return Consumer\n"
    ),
    # `object` rebound; the base list is still the bare name.
    "object_trailing_comma": _NONE_META + (
        "class Target(object,):\n"
        "    def __init__(self):\n"
        "        raise AssertionError('original init ran')\n" + _MAKE
    ),
    "object_comment_in_bases": _NONE_META + (
        "class Target(object  # comment\n"
        "):\n"
        "    def __init__(self):\n"
        "        raise AssertionError('original init ran')\n" + _MAKE
    ),
    # `__init__` replaced through a binding target or a computed name.
    "for_target": _ORIGINAL_INIT + "\n\nfor Target.__init__ in [lambda self: None]:\n    pass\n" + _MAKE,
    "with_target": _ORIGINAL_INIT + (
        "\n\nfrom contextlib import nullcontext\n\n"
        "with nullcontext(lambda self: None) as Target.__init__:\n    pass\n" + _MAKE
    ),
    "concatenated_literal": _ORIGINAL_INIT + (
        '\n\nsetattr(Target, "__ini" "t__", lambda self: None)\n' + _MAKE
    ),
    "escaped_literal": _ORIGINAL_INIT + (
        '\n\nsetattr(Target, "__in\\x69t__", lambda self: None)\n' + _MAKE
    ),
    "computed_name": _ORIGINAL_INIT + (
        "\n\nname = '_'.join(['', '', 'init', '', ''])\n"
        "setattr(Target, name, lambda self: None)\n" + _MAKE
    ),
    "aliased_setattr": _ORIGINAL_INIT + (
        "\n\nput = setattr\nput(Target, '__in' + 'it__', lambda self: None)\n" + _MAKE
    ),
    "type_setattr": _ORIGINAL_INIT + (
        "\n\ntype.__setattr__(Target, '__in' + 'it__', lambda self: None)\n" + _MAKE
    ),
    "bases_replaced": _RAISING_BASE + (
        "\n\nclass Other:\n    def __init__(self):\n        pass\n\n\n"
        "class Target(Base):\n    pass\n\n\n"
        "Target.__bases__ = (Other,)\n" + _MAKE
    ),
    # The class name rebound through the module namespace.
    "globals_write": _ORIGINAL_INIT + "\n\nglobals()['Target'] = lambda: None\n" + _MAKE,
    "vars_write": _ORIGINAL_INIT + "\n\nvars()['Target'] = lambda: None\n" + _MAKE,
    "exec_rebind": _ORIGINAL_INIT + "\n\nexec('Target = lambda: None')\n" + _MAKE,
    "sys_modules_write": _ORIGINAL_INIT + (
        "\n\nimport sys\n\nsys.modules[__name__].Target = lambda: None\n" + _MAKE
    ),
    # Python NFKC-normalizes identifiers: this binds `Target`.
    "nfkc_identifier": _ORIGINAL_INIT + "\n\n\uff34arget = lambda: None\n" + _MAKE,
    # A slot named `__init__` shadows the inherited method.
    "slots_name_init": _RAISING_BASE + (
        "\n\nclass Target(Base):\n    __slots__ = ('__init__',)\n" + _MAKE
    ),
    "slots_built_name": _RAISING_BASE + (
        "\n\nclass Target(Base):\n    __slots__ = ('__in' + 'it__',)\n" + _MAKE
    ),
    "slots_not_literal": _RAISING_BASE + (
        "\n\nNAMES = ('__init__',)\n\n\nclass Target(Base):\n    __slots__ = NAMES\n" + _MAKE
    ),
    # The bases replaced across a line continuation.
    "bases_continuation": _RAISING_BASE + (
        "\n\nclass Other:\n    def __init__(self):\n        pass\n\n\n"
        "class Target(Base):\n    pass\n\n\n"
        "Target.\\\n__bases__ = (Other,)\n" + _MAKE
    ),
    # A walrus in a header that runs in module scope rebinds the class name.
    "default_walrus": _ORIGINAL_INIT + (
        "\n\ndef configure(x=(Target := lambda: None)):\n    pass\n" + _MAKE
    ),
    "base_walrus": _ORIGINAL_INIT + (
        "\n\nclass Wrapper((Target := type('Fake', (), {}))):\n    pass\n" + _MAKE
    ),
    # `Target` in `make` is the function's type parameter (Python 3.12 syntax).
    "type_parameter": _ORIGINAL_INIT + "\n\ndef make[Target]():\n    return Target()\n",
    # A metaclass `__prepare__` can put any name into a class body's namespace
    # without a visible binding; calls in class bodies are never proven.
    "prepare_namespace": _ORIGINAL_INIT + (
        "\n\nclass Meta(type):\n"
        "    @classmethod\n"
        "    def __prepare__(mcs, name, bases):\n"
        "        return {'Target': lambda: None}\n\n\n"
        "def make():\n"
        "    class Consumer(metaclass=Meta):\n"
        "        value = Target()\n"
        "    return Consumer.value\n"
    ),
}


def _load_module(path: Path, name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


@pytest.mark.parametrize("case", sorted(_SWAPS))
def test_module_that_swaps_construction_gets_no_init_edge(tmp_path, case):
    files = {"app.py": _SWAPS[case]}
    _write_tree(tmp_path / "run", files)
    if case != "type_parameter" or sys.version_info >= (3, 12):
        module = _load_module(tmp_path / "run" / "app.py", f"swap_{case}")
        try:
            module.make()
        except AttributeError:
            assert case.startswith("slots_"), case  # the empty slot shadows `__init__`
        except TypeError:
            assert case == "type_parameter", case  # a TypeVar is not callable
    result = _extract(tmp_path / "graph", files)
    make = _nid(result, "make()", "app.py")
    assert _nid(result, "Target", "app.py") in {e["target"] for e in _calls(result, make)}
    assert _init_targets(result, make) == set()


# A caller module that rebinds the class name in the module it imports from.
_CROSS_MODULE_SWAPS: dict[str, str] = {
    "module_attribute_write": (
        "import models\n\nmodels.Target = lambda: None\n\n\n"
        "def make():\n    return models.Target()\n"
    ),
    "setattr_on_module": (
        "import models\n\nsetattr(models, 'Target', lambda: None)\n\n\n"
        "def make():\n    return models.Target()\n"
    ),
    "module_dict_write": (
        "import models\n\nmodels.__dict__['Target'] = lambda: None\n\n\n"
        "def make():\n    return models.Target()\n"
    ),
    "function_import_after_write": (
        "import models\n\nmodels.Target = lambda: None\n\n\n"
        "def make():\n    from models import Target\n    return Target()\n"
    ),
    "bound_setattr": (
        "import models\n\nmodels.__setattr__('Target', lambda: None)\n\n\n"
        "def make():\n    return models.Target()\n"
    ),
    "alias_write": (
        "import models\n\nalias = models\nalias.Target = lambda: None\n\n\n"
        "def make():\n    return models.Target()\n"
    ),
    # The escaped module also taints a later `from models import Target`.
    "alias_write_then_from_import": (
        "import models\n\nalias = models\nalias.Target = lambda: None\n\n"
        "from models import Target\n\n\n"
        "def make():\n    return Target()\n"
    ),
}


def test_package_attribute_shadowing_its_submodule_gets_no_init_edge(tmp_path, monkeypatch):
    """`from pkg import models` returns whatever `pkg/__init__.py` bound to
    `models`, not the submodule v8 links."""
    files = {
        "pkg/__init__.py": "from types import SimpleNamespace\n\nmodels = SimpleNamespace(Target=lambda: None)\n",
        "pkg/models.py": _ORIGINAL_INIT,
        "use.py": "from pkg import models\n\n\ndef make():\n    return models.Target()\n",
    }
    run = tmp_path / "run"
    _write_tree(run, files)
    monkeypatch.syspath_prepend(str(run))
    for name in ("pkg", "pkg.models", "use"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    import importlib

    assert importlib.import_module("use").make() is None
    for name in ("pkg", "pkg.models", "use"):
        sys.modules.pop(name, None)
    result = _extract(tmp_path / "graph", files)
    make = _nid(result, "make()", "use.py")
    assert _nid(result, "Target", "pkg/models.py") in {e["target"] for e in _calls(result, make)}
    assert _init_targets(result, make) == set()


@pytest.mark.parametrize("case", sorted(_CROSS_MODULE_SWAPS))
def test_caller_that_rebinds_imported_class_gets_no_init_edge(tmp_path, case, monkeypatch):
    files = {"models.py": _ORIGINAL_INIT, "use.py": _CROSS_MODULE_SWAPS[case]}
    run = tmp_path / "run"
    _write_tree(run, files)
    monkeypatch.syspath_prepend(str(run))
    for name in ("models", "use"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    import importlib

    importlib.import_module("use").make()  # the original __init__ does not run
    for name in ("models", "use"):
        sys.modules.pop(name, None)
    result = _extract(tmp_path / "graph", files)
    make = _nid(result, "make()", "use.py")
    assert _nid(result, "Target", "models.py") in {e["target"] for e in _calls(result, make)}
    assert _init_targets(result, make) == set()


# Shapes that change construction for every module (so not run here): the
# module is refused statically.
_STATIC_REFUSALS: dict[str, str] = {
    "builtins_object": (
        "import builtins\n\n\nclass Fake:\n    pass\n\n\nbuiltins.object = Fake\n\n\n"
        "class Target(object):\n    def __init__(self):\n        self.x = 1\n" + _MAKE
    ),
    "builtins_build_class": (
        "import builtins\n\nbuiltins.__build_class__ = builtins.__build_class__\n\n\n"
        + _TARGET + _MAKE
    ),
    "dunder_builtins_subscript": (
        "__builtins__['vars'] = vars\n\n\n" + _TARGET + _MAKE
    ),
    "vars_called_through_dunder": "vars.__call__()['Target'] = None\n\n\n" + _TARGET + _MAKE,
    "vars_imported_by_name": (
        "from builtins import vars as v\n\nv()['Target'] = None\n\n\n" + _TARGET + _MAKE
    ),
    "init_passed_as_value": "import functools\n\n\n" + _TARGET + (
        "\n\nwrapped = functools.wraps(Target.__init__)\n" + _MAKE
    ),
}


@pytest.mark.parametrize("case", sorted(_STATIC_REFUSALS))
def test_module_wide_refusals(tmp_path, case):
    result = _extract(tmp_path, {"app.py": _STATIC_REFUSALS[case]})
    make = _nid(result, "make()", "app.py")
    assert _nid(result, "Target", "app.py") in {e["target"] for e in _calls(result, make)}
    assert _init_targets(result, make) == set()


# `object` bound in any scope by any form: no class in the module gets a marker.
_OBJECT_BINDINGS: dict[str, str] = {
    "parameter": "def f(object):\n    return object\n",
    "lambda_parameter": "f = lambda object: object\n",
    "for_target": "def f(items):\n    for object in items:\n        pass\n",
    "with_target": "def f(cm):\n    with cm as object:\n        pass\n",
    "except_target": "def f():\n    try:\n        pass\n    except Exception as object:\n        pass\n",
    "walrus": "def f(x):\n    return (object := x)\n",
    "global": "def f():\n    global object\n    object = int\n",
    "import": "def f():\n    from somelib import object\n    return object\n",
    "def": "def f():\n    def object():\n        pass\n",
    "class": "def f():\n    class object:\n        pass\n",
    "match_capture": "def f(x):\n    match x:\n        case object:\n            pass\n",
    "match_as": "def f(x):\n    match x:\n        case 1 | 2 as object:\n            pass\n",
    "match_star": "def f(x):\n    match x:\n        case [1, *object]:\n            pass\n",
    "comprehension_target": "def f(x):\n    return [object for object in x]\n",
    "nested_with_target": "def f(a):\n    with a as (b, object):\n        pass\n",
    "type_parameter": "def f[object]():\n    pass\n",
}


@pytest.mark.parametrize("case", sorted(_OBJECT_BINDINGS))
def test_object_bound_anywhere_blocks_markers(tmp_path, case):
    result = _extract(tmp_path, {
        "models.py": (
            _OBJECT_BINDINGS[case] + "\n\n"
            "class Target(object):\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
        "use.py": "from models import Target\n\n\ndef make():\n    return Target()\n",
    })
    make = _nid(result, "make()", "use.py")
    assert _nid(result, "Target", "models.py") in {e["target"] for e in _calls(result, make)}
    assert _init_targets(result, make) == set()
    assert not any(n.get("_py_ctor_chain") for n in result["nodes"])


def test_object_only_read_keeps_the_edge(tmp_path):
    """Reading `object` (a base, an argument, a call, an annotation) binds nothing."""
    result = _extract(tmp_path, {
        "models.py": (
            "MISSING = object()\n\n\n"
            "def check(x: object) -> bool:\n"
            "    return isinstance(x, (int, object))\n\n\n"
            "class Target(object):\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
        ),
        "use.py": "from models import Target\n\n\ndef make():\n    return Target()\n",
    })
    make = _nid(result, "make()", "use.py")
    assert _init_targets(result, make) == {_nid(result, ".__init__()", "models.py")}


def test_method_body_reads_module_name(tmp_path):
    """A method body is its own scope: `Target()` there reads the module-level
    class. (With a class attribute `Target` anywhere in the file, the name is
    bound twice and nothing is proven; see _SECOND_BINDINGS.)"""
    result = _extract(tmp_path, {
        "app.py": _ORIGINAL_INIT + (
            "\n\nclass Consumer:\n"
            "    def make(self):\n"
            "        return Target()\n"
        ),
    })
    make = _nid(result, ".make()", "app.py")
    assert _init_targets(result, make) == {_nid(result, ".__init__()", "app.py")}


def test_common_shapes_keep_the_edge(tmp_path):
    """The allowlists leave ordinary code alone: calling `__init__`, a docstring
    that names it, metadata dunder writes, `setattr` with a plain literal name,
    a local called `locals`, a module path named `globals`."""
    result = _extract(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/globals.py": "LIMIT = 1\n",
        "pkg/models.py": (
            '"""Models; `Target.__init__` takes no arguments."""\n'
            "from .globals import LIMIT\n\n\n"
            "class Base:\n"
            "    def __init__(self):\n"
            "        setattr(self, 'limit', LIMIT)\n\n\n"
            "class Target(Base):\n"
            "    def __init__(self):\n"
            '        """Calls `Base.__init__`."""\n'
            "        super().__init__()\n"
            "        Base.__init__(self)\n"
            "        self.__dict__ = dict(self.__dict__)\n\n"
            "    def report(self, frame):\n"
            "        locals = frame.f_locals\n"
            "        return sorted(locals.items())\n\n\n"
            "def helper():\n"
            "    return 1\n\n\n"
            "helper.__doc__ = 'help'\n"
        ),
        "pkg/use.py": "from pkg.models import Target\n\n\ndef make():\n    return Target()\n",
    })
    make = _nid(result, "make()", "pkg/use.py")
    assert _init_targets(result, make) == {"pkg_models_target_init"}


def test_literal_slots_keep_the_edge(tmp_path):
    result = _extract(tmp_path, {
        "app.py": (
            "class Target:\n"
            "    __slots__ = ('x', '__weakref__')\n\n"
            "    def __init__(self):\n"
            "        self.x = 1\n\n\n"
            "def make():\n"
            "    return Target()\n"
        ),
    })
    make = _nid(result, "make()", "app.py")
    assert _init_targets(result, make) == {_nid(result, ".__init__()", "app.py")}


# --- initializers that never run, and other shapes ----------------------------

_NEVER_RUNS = {
    "async_init": "    async def __init__(self):\n        helper()\n",
    "generator_init": "    def __init__(self):\n        helper()\n        yield 1\n",
    "yield_from_init": "    def __init__(self):\n        helper()\n        yield from ()\n",
    "async_generator_init": "    async def __init__(self):\n        helper()\n        yield 1\n",
    # Only a nested body is another scope: defaults and bases run in `__init__`.
    "yield_in_nested_default": (
        "    def __init__(self):\n"
        "        def nested(x=(yield 1)):\n"
        "            pass\n"
        "        helper()\n"
    ),
    "yield_in_nested_base": (
        "    def __init__(self):\n"
        "        class Nested((yield object)):\n"
        "            pass\n"
        "        helper()\n"
    ),
}


@pytest.mark.parametrize("inherited", [False, True], ids=["direct", "inherited"])
@pytest.mark.parametrize("case", sorted(_NEVER_RUNS))
def test_init_that_returns_before_its_body_gets_no_edge(tmp_path, case, inherited):
    """Construction raises TypeError before the body of an async or generator
    `__init__` runs, so its helper must not become reachable."""
    source = (
        "def helper():\n    raise AssertionError('initializer body ran')\n\n\n"
        "class Base:\n" + _NEVER_RUNS[case]
        + ("\n\nclass Target(Base):\n    pass\n" if inherited else "\n\nTarget = None\n")
        + "\n\ndef make():\n    return Target()\n"
    )
    if not inherited:
        source = source.replace("class Base:", "class Target:").replace("\n\nTarget = None\n", "")
    files = {"app.py": source}
    _write_tree(tmp_path / "run", files)
    module = _load_module(tmp_path / "run" / "app.py", f"never_{case}_{inherited}")
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # an un-awaited coroutine
        with pytest.raises(TypeError):
            module.make()
    result = _extract(tmp_path / "graph", files)
    make = _nid(result, "make()", "app.py")
    assert _nid(result, "Target", "app.py") in {e["target"] for e in _calls(result, make)}
    assert _init_targets(result, make) == set()
    assert _nid(result, "helper()", "app.py") not in _reachable(result, make)


# A binding nested in `if` / `try` / `with` / a loop / `match` may never run.
_CONDITIONAL_BINDINGS: dict[str, dict[str, str]] = {
    "type_checking_import": {
        "models.py": "class Warning:\n    def __init__(self):\n        raise AssertionError('original init ran')\n",
        "use.py": (
            "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from models import Warning\n\n\n"
            "def make():\n    return Warning()\n"
        ),
    },
    "if_false_class": {
        "use.py": (
            "if False:\n"
            "    class Warning:\n"
            "        def __init__(self):\n"
            "            raise AssertionError('original init ran')\n\n\n"
            "def make():\n    return Warning()\n"
        ),
    },
    "try_import_error": {
        "models.py": "class Target:\n    def __init__(self):\n        raise AssertionError('original init ran')\n",
        "use.py": (
            "try:\n    import missing_dependency_xyz\n    from models import Target\n"
            "except ImportError:\n    pass\n\n\n"
            "def make():\n    return Target()\n"
        ),
    },
}


@pytest.mark.parametrize("case", sorted(_CONDITIONAL_BINDINGS))
def test_conditional_binding_proves_nothing(tmp_path, case, monkeypatch):
    files = _CONDITIONAL_BINDINGS[case]
    run = tmp_path / "run"
    _write_tree(run, files)
    monkeypatch.syspath_prepend(str(run))
    for name in ("models", "use"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    import importlib

    try:
        made = importlib.import_module("use").make()
        assert type(made) is Warning  # the builtin, not the project class
    except NameError:
        assert case == "try_import_error"  # the import never ran
    for name in ("models", "use"):
        sys.modules.pop(name, None)
    result = _extract(tmp_path / "graph", files)
    make = _nid(result, "make()", "use.py")
    label = "Target" if case == "try_import_error" else "Warning"
    defined_in = "use.py" if case == "if_false_class" else "models.py"
    assert _nid(result, label, defined_in) in {e["target"] for e in _calls(result, make)}
    assert _init_targets(result, make) == set()


def test_conditional_base_import_gives_no_marker(tmp_path):
    result = _extract(tmp_path, {
        "bases.py": "class Base:\n    def __init__(self):\n        self.x = 1\n",
        "children.py": (
            "import sys\n\nif sys.version_info >= (3,):\n    from bases import Base\n\n\n"
            "class Child(Base):\n    pass\n"
        ),
        "use.py": "from children import Child\n\n\ndef make():\n    return Child()\n",
    })
    make = _nid(result, "make()", "use.py")
    assert _nid(result, "Child", "children.py") in {e["target"] for e in _calls(result, make)}
    assert _init_targets(result, make) == set()
    assert not any(n.get("_py_ctor_chain") for n in result["nodes"] if n.get("label") == "Child")


def test_nested_generator_inside_init_keeps_the_edge(tmp_path):
    """A `yield` in a function nested in `__init__` does not make `__init__` a
    generator."""
    result = _extract(tmp_path, {
        "app.py": (
            "class Target:\n"
            "    def __init__(self):\n"
            "        def numbers():\n"
            "            yield 1\n"
            "        self.numbers = numbers\n\n\n"
            "def make():\n    return Target()\n"
        ),
    })
    init = [n["id"] for n in result["nodes"] if n.get("label") == ".__init__()"]
    assert _init_targets(result, _nid(result, "make()", "app.py")) == set(init) and len(init) == 1


def test_class_level_import_does_not_prove_a_method_call(tmp_path):
    """Methods do not see their class body's names: `Target` in `make` is
    unbound (NameError), though v8 binds the call to the class."""
    result = _extract(tmp_path, {
        "models.py": "class Target:\n    def __init__(self):\n        self.x = 1\n",
        "use.py": (
            "class Consumer:\n"
            "    from models import Target\n\n"
            "    def make(self):\n"
            "        return Target()\n"
        ),
    })
    make = _nid(result, ".make()", "use.py")
    assert _nid(result, "Target", "models.py") in {e["target"] for e in _calls(result, make)}
    assert _init_targets(result, make) == set()


def test_escaped_module_in_a_chain_file_blocks_its_base(tmp_path, monkeypatch):
    """children.py lets `bases` escape and rewrites `Base` through the alias
    before importing it: `Target()` runs `Fake.__init__`."""
    files = {
        "bases.py": "class Base:\n    def __init__(self):\n        raise AssertionError('original init ran')\n",
        "children.py": (
            "import bases\n\nalias = bases\n\n\n"
            "class Fake:\n    def __init__(self):\n        pass\n\n\n"
            "alias.Base = Fake\n\nfrom bases import Base\n\n\n"
            "class Target(Base):\n    pass\n"
        ),
        "use.py": "from children import Target\n\n\ndef make():\n    return Target()\n",
    }
    run = tmp_path / "run"
    _write_tree(run, files)
    monkeypatch.syspath_prepend(str(run))
    for name in ("bases", "children", "use"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    import importlib

    assert type(importlib.import_module("use").make()).__init__.__qualname__ == "Fake.__init__"
    for name in ("bases", "children", "use"):
        sys.modules.pop(name, None)
    result = _extract(tmp_path / "graph", files)
    make = _nid(result, "make()", "use.py")
    assert _nid(result, "Target", "children.py") in {e["target"] for e in _calls(result, make)}
    assert _init_targets(result, make) == set()


# --- the analysis never costs v8 output -----------------------------------------

_BOUND_DELATTR = (
    "class Target:\n"
    "    def __init__(self):\n"
    "        self.x = 1\n"
    "    def clear(self):\n"
    "        self.__delattr__('x')\n"
    "def make():\n"
    "    t = Target()\n"
    "    t.clear()\n"
    "    return t\n"
)
# v8's extraction of _BOUND_DELATTR, recorded from upstream/v8 at 6478eb7.
_BOUND_DELATTR_V8_NODES = {
    ("use", "use.py"), ("use_make", "make()"), ("use_target", "Target"),
    ("use_target_clear", ".clear()"), ("use_target_init", ".__init__()"),
}
_BOUND_DELATTR_V8_EDGES = {
    ("use", "use_make", "contains", "EXTRACTED", "L6"),
    ("use", "use_target", "contains", "EXTRACTED", "L1"),
    ("use_make", "use_target", "calls", "EXTRACTED", "L7"),
    ("use_target", "use_target_clear", "method", "EXTRACTED", "L4"),
    ("use_target", "use_target_init", "method", "EXTRACTED", "L2"),
    ("use_make", "use_target_clear", "calls", "INFERRED", "L8"),
}

# What this change adds to a graph: the constructor edges, and the facts the
# engine stores on nodes so a later merge can link again.
_PY_FACTS = ("_py_ctor_chain", "_py_ctor_base_binding", "_py_proven_calls")


def _links(graph: dict) -> list[dict]:
    return graph.get("links", graph.get("edges", []))


def _ctor_edges(graph: dict) -> set[tuple]:
    return {
        (e["source"], e["target"], e.get("confidence"), e.get("source_location"))
        for e in _links(graph)
        if e.get("relation") == "calls" and e.get("context") == "constructor"
    }


def _without_additions(graph: dict) -> tuple[list[str], list[str]]:
    """Every node and edge, attributes included, less what this change adds.
    Community assignments are left out: added edges can move them."""
    nodes = sorted(
        json.dumps({
            k: v for k, v in n.items()
            if k not in _PY_FACTS and not k.startswith("community")
        }, sort_keys=True)
        for n in graph["nodes"]
    )
    edges = sorted(
        json.dumps(e, sort_keys=True) for e in _links(graph)
        if not (e.get("relation") == "calls" and e.get("context") == "constructor")
    )
    return nodes, edges


def _v8_shape(result: dict) -> tuple[set, set]:
    nodes = {(n["id"], n.get("label")) for n in result["nodes"]}
    edges = {
        (e["source"], e["target"], e["relation"], e.get("confidence"), e.get("source_location"))
        for e in result["edges"] if e.get("context") != "constructor"
    }
    return nodes, edges


def test_bound_dunder_delattr_keeps_the_v8_extraction(tmp_path):
    result = _extract(tmp_path, {"use.py": _BOUND_DELATTR})
    assert _v8_shape(result) == (_BOUND_DELATTR_V8_NODES, _BOUND_DELATTR_V8_EDGES)
    assert not _ctor_edges(result)
    assert not any(n.get("_py_ctor_chain") for n in result["nodes"])


def _boom(*_args, **_kwargs):
    raise RuntimeError("injected constructor-analysis failure")


_FAULT_FILES = {
    "models.py": (
        "class Alpha:\n    def __init__(self):\n        self.a = 1\n\n\n"
        "class Beta:\n    def __init__(self):\n        self.b = 1\n"
    ),
    "use_alpha.py": "from models import Alpha\n\n\ndef make_alpha():\n    return Alpha()\n",
    "use_beta.py": "from models import Beta\n\n\ndef make_beta():\n    return Beta()\n",
}
_FAULT_EDGES = {
    ("use_alpha_make_alpha", "models_alpha_init", "INFERRED", "L5"),
    ("use_beta_make_beta", "models_beta_init", "INFERRED", "L5"),
}


@pytest.mark.parametrize("where", [
    "graphify.extractors.engine._python_ctor_poison",
    "graphify.extractors.engine._python_ctor_chain",
    "graphify.extractors.engine._python_call_in_class_scope",
    "graphify.extract.link_python_constructors",
    "graphify.extract._keep_python_call_records",
])
def test_failure_inside_the_analysis_keeps_the_rest(tmp_path, monkeypatch, where):
    """Any exception in the constructor analysis drops only what it adds."""
    normal = _extract(tmp_path / "normal", _FAULT_FILES)
    assert _ctor_edges(normal) == _FAULT_EDGES
    monkeypatch.setattr(where, _boom)
    failed = _extract(tmp_path / "failed", _FAULT_FILES)
    assert _without_additions(failed) == _without_additions(normal)
    assert not _ctor_edges(failed)


def _fail_on_second_import_check(monkeypatch, record: list):
    """Wrap link_python_constructors so the second import it resolves raises:
    the first proved call site has staged its edge by then. `record` gets the
    number of imports each call resolved."""
    import graphify.extract as extract_module

    real_link = extract_module.link_python_constructors
    real_resolve = extract_module._resolve_python_module_path

    def link(*args, **kwargs):
        seen = [0]

        def resolve(*r_args, **r_kwargs):
            seen[0] += 1
            if seen[0] == 2:
                raise RuntimeError("injected failure after an edge was staged")
            return real_resolve(*r_args, **r_kwargs)

        try:
            with monkeypatch.context() as m:
                m.setattr(extract_module, "_resolve_python_module_path", resolve)
                return real_link(*args, **kwargs)
        finally:
            record.append(seen[0])

    monkeypatch.setattr(extract_module, "link_python_constructors", link)


def test_failure_after_an_edge_is_staged_commits_nothing(tmp_path, monkeypatch):
    """The pass returns its edges and extract() commits them only on success:
    a failure after the first edge is staged leaves exactly what a pass that
    fails at once leaves, which is v8's output with none of the stored facts."""
    normal = _extract(tmp_path / "normal", _FAULT_FILES)
    assert _ctor_edges(normal) == _FAULT_EDGES
    with monkeypatch.context() as m:
        record: list[int] = []
        _fail_on_second_import_check(m, record)
        failed = _extract(tmp_path / "failed", _FAULT_FILES)
        assert record == [2]
    with monkeypatch.context() as m:
        m.setattr("graphify.extract.link_python_constructors", _boom)
        at_once = _extract(tmp_path / "at_once", _FAULT_FILES)
    assert json.dumps(failed["nodes"], sort_keys=True) == json.dumps(at_once["nodes"], sort_keys=True)
    assert json.dumps(failed["edges"], sort_keys=True) == json.dumps(at_once["edges"], sort_keys=True)
    assert not any(key in n for n in failed["nodes"] for key in _PY_FACTS)
    assert _without_additions(failed) == _without_additions(normal)


def test_failed_relink_after_a_staged_edge_leaves_the_merge_alone(tmp_path, monkeypatch):
    """The same for the relink after an incremental merge: the merged graph is
    v8's merge with no constructor edge, as when the relink fails at once."""
    from graphify.watch import _rebuild_code

    graphs = {}
    for mode in ("staged", "at_once"):
        corpus = tmp_path / mode
        _write_tree(corpus, _FAULT_FILES)
        assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
        assert _ctor_edges(_graph(corpus)) == _FAULT_EDGES
        changed = _write_tree(corpus, {"use_beta.py": _FAULT_FILES["use_beta.py"] + "# edited\n"})
        with monkeypatch.context() as m:
            record: list[int] = []
            if mode == "staged":
                _fail_on_second_import_check(m, record)
            else:
                import graphify.extract as extract_module

                real_link = extract_module.link_python_constructors

                def link(nodes, edges, root, _real=real_link, _record=record):
                    _record.append(0)
                    if len(_record) == 2:  # the relink; the first is extract()'s pass
                        raise RuntimeError("injected relink failure")
                    return _real(nodes, edges, root)

                m.setattr(extract_module, "link_python_constructors", link)
            assert _rebuild_code(
                corpus, changed_paths=changed, no_cluster=True, acquire_lock=False
            ) is True
        if mode == "staged":
            # extract()'s pass over the batch resolves nothing (its class is
            # resolution context); the relink fails on its second import.
            assert record == [0, 2]
        graphs[mode] = _graph(corpus)
    assert graphs["staged"]["nodes"] == graphs["at_once"]["nodes"]
    assert graphs["staged"]["links"] == graphs["at_once"]["links"]
    assert not _ctor_edges(graphs["staged"])


def test_malformed_stored_record_proves_nothing(tmp_path):
    """A stored call record this version did not write proves no call site and
    does not stop the other call sites from linking."""
    from graphify.extract import link_python_constructors

    result = _extract(tmp_path, _FAULT_FILES)
    nodes = json.loads(json.dumps(result["nodes"]))
    edges = [e for e in result["edges"] if e.get("context") != "constructor"]
    assert {(e["source"], e["target"]) for e in link_python_constructors(nodes, edges, tmp_path)} == {
        (s, t) for s, t, _, _ in _FAULT_EDGES
    }
    alpha = next(n for n in nodes if n["id"] == "use_alpha")
    alpha["_py_proven_calls"] = [["invalid", *alpha["_py_proven_calls"][0][1:]]]
    assert [(e["source"], e["target"]) for e in link_python_constructors(nodes, edges, tmp_path)] == [
        ("use_beta_make_beta", "models_beta_init"),
    ]


def test_base_must_be_the_imported_symbol(tmp_path):
    """A base step counts only if its `inherits` edge ends on the class the
    import names, not on another class imported on the same line."""
    from graphify.extract import link_python_constructors

    result = _extract(tmp_path, _ALIAS_SWAP_FILES)
    edges = [e for e in result["edges"] if e.get("context") != "constructor"]
    assert {(e["source"], e["target"]) for e in link_python_constructors(result["nodes"], edges, tmp_path)} == {
        ("use_make", "models_base_init"),
    }
    # A base resolved to the other class of that import line links nothing.
    assert "models_parent" in {n["id"] for n in result["nodes"]}
    for e in edges:
        if e["relation"] == "inherits" and e["source"] == "children_child":
            e["target"] = "models_parent"
    assert link_python_constructors(result["nodes"], edges, tmp_path) == []


def test_stored_call_records_are_the_class_calls(tmp_path):
    """graph.json keeps only the call records a class call edge can use."""
    result = _extract(tmp_path, {
        "models.py": "def helper():\n    return 1\n\n\nclass Target:\n    def __init__(self):\n        self.x = 1\n",
        "use.py": "from models import Target, helper\n\n\ndef make():\n    helper()\n    return Target()\n",
    })
    use = next(n for n in result["nodes"] if n["id"] == "use")
    assert use["_py_proven_calls"] == [[6, "Target", "import", 1, "Target", "models"]]
    assert _ctor_edges(result) == {("use_make", "models_target_init", "INFERRED", "L6")}


def test_pair_with_an_edge_keeps_it(tmp_path):
    """A graph keeps one edge per node pair, so a constructor edge is never
    added where v8 already has an edge between the two nodes in either
    direction (here `__init__` calls the caller back)."""
    result = _extract(tmp_path, {
        "use.py": (
            "class Target:\n"
            "    def __init__(self, again=False):\n"
            "        if again:\n"
            "            make()\n\n\n"
            "def make():\n"
            "    return Target()\n"
        ),
    })
    make = _nid(result, "make()", "use.py")
    init = _nid(result, ".__init__()", "use.py")
    assert make in {e["target"] for e in _calls(result, init)}
    assert _init_targets(result, make) == set()


# --- incremental builds ----------------------------------------------------------
#
# An incremental build re-extracts only the changed files and merges them into
# the stored graph. A constructor edge depends on every class in the called
# class's chain, so each merge drops the stored constructor edges and links
# them again over the merged graph from the facts each file stored
# (relink_python_constructors). Every other node and edge stays as v8's merge
# made it, so where v8 leaves a base as a file-local stub the edge is missing,
# never wrong.

_INC_FILES = {
    "pkg/__init__.py": "",
    "pkg/base.py": (
        "def helper():\n    return 1\n\n\n"
        "class Base:\n"
        "    def __init__(self):\n"
        "        self.x = helper()\n"
    ),
    "pkg/child.py": (
        "from pkg.base import Base\n\n\n"
        "class Child(Base):\n"
        "    pass\n"
    ),
    "pkg/use.py": (
        "from pkg.child import Child\n\n\n"
        "def make():\n"
        "    return Child()\n"
    ),
}


def _graph(corpus: Path) -> dict:
    return json.loads((corpus / "graphify-out" / "graph.json").read_text(encoding="utf-8"))


def _node_edge_sets(graph: dict) -> tuple[set, set]:
    # `uses` is left out: v8 already drops the caller's INFERRED `uses` edge to
    # an unchanged class on a caller-only rebuild, independent of this change.
    nodes = {(n["id"], n.get("label"), n.get("source_file")) for n in graph["nodes"]}
    edges = {
        (e["source"], e["target"], e.get("relation"), e.get("confidence"),
         e.get("context"), e.get("source_location"))
        for e in _links(graph)
        if e.get("relation") != "uses"
    }
    return nodes, edges


def _run_extract(proj: Path, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "graphify", "extract", str(proj), "--code-only", "--no-cluster"],
        cwd=cwd, capture_output=True, text=True,
    )


def test_caller_only_incremental_rebuild_matches_full_build(tmp_path):
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    _write_tree(corpus, _INC_FILES)
    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    full = _ctor_edges(_graph(corpus))
    assert full == {("pkg_use_make", "pkg_base_base_init", "INFERRED", "L5")}

    # Edit only the caller; the class chain comes from the stored graph.
    caller = corpus / "pkg" / "use.py"
    caller.write_text(_INC_FILES["pkg/use.py"] + "\n\ndef other():\n    return 2\n",
                      encoding="utf-8")
    assert _rebuild_code(
        corpus, changed_paths=[caller], no_cluster=True, acquire_lock=False
    ) is True
    incremental = _graph(corpus)
    assert _ctor_edges(incremental) == full

    # The whole graph matches a clean full build of the edited corpus.
    clean = tmp_path / "clean"
    _write_tree(clean, {**_INC_FILES, "pkg/use.py": caller.read_text(encoding="utf-8")})
    assert _rebuild_code(clean, no_cluster=True, acquire_lock=False) is True
    assert _node_edge_sets(incremental) == _node_edge_sets(_graph(clean))

    # Removing the call removes the edge; the rebuild never keeps stale ones.
    caller.write_text("def make():\n    return 1\n", encoding="utf-8")
    assert _rebuild_code(
        corpus, changed_paths=[caller], no_cluster=True, acquire_lock=False
    ) is True
    assert _ctor_edges(_graph(corpus)) == set()


def test_incremental_rebuild_of_graph_without_marker_adds_no_edge(tmp_path):
    """Degradation contract (same as #2438): an older graph without the stored
    facts emits no constructor edge until its files are re-extracted."""
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    _write_tree(corpus, _INC_FILES)
    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    graph_path = corpus / "graphify-out" / "graph.json"
    legacy = json.loads(graph_path.read_text(encoding="utf-8"))
    assert any(n.get("_py_ctor_chain") for n in legacy["nodes"])
    for node in legacy["nodes"]:
        for key in _PY_FACTS:
            node.pop(key, None)
    legacy["links"] = [e for e in legacy["links"] if e.get("context") != "constructor"]
    graph_path.write_text(json.dumps(legacy), encoding="utf-8")

    caller = corpus / "pkg" / "use.py"
    caller.write_text(_INC_FILES["pkg/use.py"] + "\n# touched\n", encoding="utf-8")
    assert _rebuild_code(
        corpus, changed_paths=[caller], no_cluster=True, acquire_lock=False
    ) is True
    assert _ctor_edges(_graph(corpus)) == set()


# The same build with the analysis switched off, through the CLI.
_WITHOUT_ANALYSIS = (
    "import sys\n"
    "import graphify.extract\n"
    "graphify.extract.link_python_constructors = lambda *args, **kwargs: []\n"
    "sys.argv = ['graphify', *sys.argv[1:]]\n"
    "from graphify.__main__ import main\n"
    "main()\n"
)


def _no_edges(*_args, **_kwargs) -> list:
    return []


def _build(root: Path, path: str, changed: list[Path] | None, analysis: bool, monkeypatch) -> dict:
    if path.startswith("watch"):
        from graphify.watch import _rebuild_code

        with monkeypatch.context() as m:
            if not analysis:
                m.setattr("graphify.extract.link_python_constructors", _no_edges)
            assert _rebuild_code(
                root, changed_paths=changed, no_cluster=path == "watch",
                acquire_lock=False,
            ) is True
    else:
        args = ["extract", str(root), "--code-only", *(["--no-cluster"] if path == "extract" else [])]
        command = ["-m", "graphify"] if analysis else ["-c", _WITHOUT_ANALYSIS]
        run = subprocess.run(
            [sys.executable, *command, *args], cwd=root.parent, capture_output=True, text=True,
        )
        assert run.returncode == 0, run.stderr
        if changed is not None:
            assert "incremental scan" in run.stdout.lower(), run.stdout
    return _graph(root)


def _build_steps(
    tmp_path: Path, path: str, files: dict, steps: list[dict], analysis: bool, monkeypatch
) -> list[dict]:
    """A full build of `files`, then one incremental build per step. Both
    modes build in the same directory so stored ids and paths match."""
    import shutil

    root = tmp_path / "proj"
    shutil.rmtree(root, ignore_errors=True)
    _write_tree(root, files)
    graphs = [_build(root, path, None, analysis, monkeypatch)]
    for step in steps:
        changed = []
        for rel, text in step.items():
            if text is None:
                (root / rel).unlink()
            else:
                _write_tree(root, {rel: text})
            changed.append(root / rel)
        graphs.append(_build(root, path, changed, analysis, monkeypatch))
    shutil.rmtree(root)
    return graphs


_CHAIN_FILES = {
    "bases.py": "class Base:\n    def __init__(self):\n        self.b = 1\n",
    "others.py": "class Other:\n    def __init__(self):\n        self.o = 1\n",
    "children.py": "from bases import Base\n\n\nclass Child(Base):\n    pass\n",
    "use.py": "from children import Child\n\n\ndef make():\n    return Child()\n",
}
_ALIASED_FILES = {**_CHAIN_FILES, "children.py": (
    "from bases import Base as Parent\n\n\nclass Child(Parent):\n    pass\n"
)}
_EXCLUDED_ANCESTOR_FILES = {
    "bases.py": "class Base:\n    pass\n",
    "children.py": "from bases import Base\n\n\nclass Child(Base):\n    def __init__(self):\n        pass\n",
    "use.py": "from children import Child\n\n\ndef make():\n    return Child()\n",
    "other.py": "def other():\n    return 1\n",
}
_ALIAS_SWAP_FILES = {
    "models.py": (
        "class Base:\n    def __init__(self):\n        self.tag = 'Base'\n\n\n"
        "class Parent:\n    def __init__(self):\n        self.tag = 'Parent'\n"
    ),
    "children.py": (
        "from models import Base as Parent, Parent as Other\n\n\n"
        "class Child(Parent):\n    pass\n"
    ),
    "use.py": "from children import Child\n\n\ndef make():\n    return Child()\n",
}
_SAME_ID_FILES = {
    "a/__init__.py": "",
    "a/models.py": "def helper_a():\n    return 1\n\n\nclass Target:\n    def __init__(self):\n        helper_a()\n",
    "a/use.py": "from a.models import Target\n\n\ndef make_a():\n    return Target()\n",
}
_SAME_ID_ADDED = {
    "a_models.py": "def helper_b():\n    return 2\n\n\nclass Target:\n    def __init__(self):\n        helper_b()\n",
    "use_b.py": "from a_models import Target\n\n\ndef make_b():\n    return Target()\n",
}
_BASE_EDGE = {("use_make", "bases_base_init", "INFERRED", "L5")}
_CHILD_EDGE = {("use_make", "children_child_init", "INFERRED", "L5")}
_SWAP_EDGE = {("use_make", "models_base_init", "INFERRED", "L5")}

# files, edit steps (path -> new text, None deletes), constructor edges after
# the full build and after each step. A rebuilt subclass file gets its base
# resolved only among the rebuilt files (v8), so its base is a stub until a
# full build: those cases lose the edge.
_INC_SCENARIOS: dict[str, tuple[dict, list[dict], list[set] | None]] = {
    "caller_edit": (
        _INC_FILES, [{"pkg/use.py": _INC_FILES["pkg/use.py"] + "# edited\n"}],
        [{("pkg_use_make", "pkg_base_base_init", "INFERRED", "L5")}] * 2,
    ),
    "base_file_edit": (
        _CHAIN_FILES, [{"bases.py": _CHAIN_FILES["bases.py"] + "# edited\n"}], [_BASE_EDGE] * 2,
    ),
    "base_init_removed": (
        _CHAIN_FILES, [{"bases.py": "class Base:\n    pass\n"}], [_BASE_EDGE, set()],
    ),
    "init_added_to_subclass": (
        _CHAIN_FILES,
        [{"children.py": _CHAIN_FILES["children.py"] + "    def __init__(self):\n        self.c = 1\n"}],
        [_BASE_EDGE, set()],
    ),
    "subclass_base_changed": (
        _CHAIN_FILES,
        [{"children.py": "from others import Other\n\n\nclass Child(Other):\n    pass\n"}],
        [_BASE_EDGE, set()],
    ),
    "subclass_file_deleted": (_CHAIN_FILES, [{"children.py": None}], [_BASE_EDGE, set()]),
    "aliased_base_file_edit": (
        _ALIASED_FILES, [{"bases.py": _ALIASED_FILES["bases.py"] + "# edited\n"}], [_BASE_EDGE] * 2,
    ),
    "aliased_subclass_edit_then_base_edit": (
        _ALIASED_FILES,
        [
            {"children.py": _ALIASED_FILES["children.py"] + "# edited\n"},
            {"bases.py": _ALIASED_FILES["bases.py"] + "# edited\n"},
        ],
        [_BASE_EDGE, set(), set()],
    ),
    "alias_swap_subclass_edit": (
        _ALIAS_SWAP_FILES, [{"children.py": _ALIAS_SWAP_FILES["children.py"] + "# edited\n"}],
        [_SWAP_EDGE, set()],
    ),
    "reexport_to_external": (
        {
            "pkg/__init__.py": "from .old import Base\n",
            "pkg/old.py": "class Base:\n    def __init__(self):\n        self.old = 1\n",
            "children.py": "from pkg import Base\n\n\nclass Child(Base):\n    pass\n",
            "use.py": "from children import Child\n\n\ndef make():\n    return Child()\n",
        },
        [{"pkg/__init__.py": "from external import Base\n"}],
        [set(), set()],
    ),
    "new_module": (
        {"use.py": "from models import Target\n\n\ndef make():\n    return Target()\n"},
        [{"models.py": "class Target:\n    def __init__(self):\n        self.x = 1\n"}],
        [set(), set()],
    ),
    # A new package shadows the module an unchanged caller imports: Python
    # (and the resolver) take models/__init__.py, though v8 keeps the caller's
    # edges to models.py.
    "package_shadows_module_import": (
        {"models.py": _MODEL, "use.py": "from models import Model\n\n\ndef make():\n    return Model()\n"},
        [{"models/__init__.py": "class Model:\n    def __init__(self):\n        self.other = 1\n"}],
        [{("use_make", "models_model_init", "INFERRED", "L5")}, set()],
    ),
    "package_shadows_module_attribute": (
        {"models.py": _MODEL, "use.py": "import models\n\n\ndef make():\n    return models.Model()\n"},
        [{"models/__init__.py": "class Model:\n    def __init__(self):\n        self.other = 1\n"}],
        [{("use_make", "models_model_init", "INFERRED", "L5")}, set()],
    ),
    # A module added later reuses an id the stored graph already has
    # (`a_models.py` and `a/models.py` both mint `a_models_target_init`), so
    # the merged graph holds one `__init__` node with both bodies' calls.
    "same_id_module_added": (
        _SAME_ID_FILES,
        [_SAME_ID_ADDED, {"a/use.py": _SAME_ID_FILES["a/use.py"] + "# edited\n"}],
        [{("a_use_make_a", "a_models_target_init", "INFERRED", "L5")}, set(), set()],
    ),
    "ancestor_excluded": (
        _EXCLUDED_ANCESTOR_FILES,
        [{".graphifyignore": "bases.py\n", "other.py": _EXCLUDED_ANCESTOR_FILES["other.py"] + "# edited\n"}],
        [_CHILD_EDGE, set()],
    ),
    "ancestor_excluded_alone": (
        _EXCLUDED_ANCESTOR_FILES,
        [{".graphifyignore": "bases.py\n"}],
        # watch keeps an excluded file's nodes when nothing else changed (v8),
        # so the chain is still in the graph; `graphify extract` prunes them.
        None,
    ),
}
_ANCESTOR_EXCLUDED_ALONE = {"watch": [_CHILD_EDGE] * 2, "extract": [_CHILD_EDGE, set()]}


@pytest.mark.parametrize("case", sorted(_INC_SCENARIOS))
@pytest.mark.parametrize("path", ["watch", "extract"])
def test_incremental_build_keeps_every_v8_node_and_edge(tmp_path, monkeypatch, path, case):
    files, steps, expected = _INC_SCENARIOS[case]
    without = _build_steps(tmp_path, path, files, steps, False, monkeypatch)
    with_edges = _build_steps(tmp_path, path, files, steps, True, monkeypatch)
    for step, (graph, reference) in enumerate(zip(with_edges, without)):
        assert not _ctor_edges(reference)
        assert _without_additions(graph) == _without_additions(reference), step
    assert [_ctor_edges(g) for g in with_edges] == (expected or _ANCESTOR_EXCLUDED_ALONE[path])


@pytest.mark.parametrize("case", [
    "caller_edit", "base_file_edit", "base_init_removed", "subclass_base_changed", "ancestor_excluded",
])
@pytest.mark.parametrize("path", ["watch_clustered", "extract_clustered"])
def test_clustered_incremental_build_keeps_every_v8_node_and_edge(tmp_path, monkeypatch, path, case):
    files, steps, expected = _INC_SCENARIOS[case]
    without = _build_steps(tmp_path, path, files, steps, False, monkeypatch)
    with_edges = _build_steps(tmp_path, path, files, steps, True, monkeypatch)
    for step, (graph, reference) in enumerate(zip(with_edges, without)):
        assert _without_additions(graph) == _without_additions(reference), step
    assert [_ctor_edges(g) for g in with_edges] == expected


# v8's incremental graph after the alias-swap comment edit, recorded from
# upstream/v8 at 5c7b847 on both paths: Child's base is the stub `parent`.
_ALIAS_SWAP_V8_INHERITS = {("children_child", "parent")}


@pytest.mark.parametrize("path", ["watch", "extract"])
def test_incremental_base_stub_links_nothing(tmp_path, monkeypatch, path):
    """`from models import Base as Parent, Parent as Other`: a full build links
    `Child()` to `Base.__init__`, which is what runs. Rebuilding only
    children.py, v8 leaves `Child`'s base on a stub named `parent`; the edge is
    then missing, never moved to `models.Parent`."""
    steps = [{"children.py": _ALIAS_SWAP_FILES["children.py"] + "# edited\n"}]
    full, incremental = _build_steps(tmp_path, path, _ALIAS_SWAP_FILES, steps, True, monkeypatch)
    assert _ctor_edges(full) == _SWAP_EDGE
    inherits = {(e["source"], e["target"]) for e in _links(incremental) if e["relation"] == "inherits"}
    assert inherits == _ALIAS_SWAP_V8_INHERITS
    assert {n["id"] for n in incremental["nodes"] if not n.get("source_file")} >= {"parent"}
    assert _ctor_edges(incremental) == set()

    run = tmp_path / "run"
    _write_tree(run, _ALIAS_SWAP_FILES)
    monkeypatch.syspath_prepend(str(run))
    for name in ("models", "children", "use"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    import importlib

    assert importlib.import_module("use").make().tag == "Base"
    for name in ("models", "children", "use"):
        sys.modules.pop(name, None)


@pytest.mark.parametrize("edit, expected", [
    ({"bases.py": _CHAIN_FILES["bases.py"] + "# edited\n"}, _BASE_EDGE),
    ({"bases.py": "class Base:\n    pass\n"}, set()),
    ({"children.py": "from others import Other\n\n\nclass Child(Other):\n    pass\n"}, set()),
])
def test_build_merge_links_again(tmp_path, monkeypatch, edit, expected):
    """The skill's --update: extract() of the changed files, then build_merge
    into the stored graph. An unchanged caller keeps no edge to a superseded
    `__init__`, and every other node and edge is the merge's."""
    from graphify.build import build_merge

    def merged(analysis: bool) -> dict:
        import shutil

        root = tmp_path / "proj"
        shutil.rmtree(root, ignore_errors=True)
        _write_tree(root, _CHAIN_FILES)
        with monkeypatch.context() as m:
            if not analysis:
                m.setattr("graphify.extract.link_python_constructors", _no_edges)
            run = subprocess.run(
                [sys.executable, *(["-m", "graphify"] if analysis else ["-c", _WITHOUT_ANALYSIS]),
                 "extract", str(root), "--code-only", "--no-cluster"],
                cwd=tmp_path, capture_output=True, text=True,
            )
            assert run.returncode == 0, run.stderr
            if analysis:
                assert _ctor_edges(_graph(root)) == _BASE_EDGE
            changed = _write_tree(root, edit)
            new = extract(changed, cache_root=root, parallel=False)
            G = build_merge([new], graph_path=root / "graphify-out" / "graph.json", root=root)
        shutil.rmtree(root)
        return {
            "nodes": [{"id": n, **d} for n, d in G.nodes(data=True)],
            "links": [
                {**{k: v for k, v in d.items() if k not in ("_src", "_tgt")},
                 "source": d.get("_src", u), "target": d.get("_tgt", v)}
                for u, v, d in G.edges(data=True)
            ],
        }

    without, with_edges = merged(False), merged(True)
    assert _without_additions(with_edges) == _without_additions(without)
    assert _ctor_edges(with_edges) == expected
