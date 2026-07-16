import importlib
import sys
import types

import pytest

import networkx.lazy_imports as lazy


def test_lazy_import_basics():
    math = lazy._lazy_import("math")
    anything_not_real = lazy._lazy_import("anything_not_real")

    # Now test that accessing attributes does what it should
    assert math.sin(math.pi) == pytest.approx(0, 1e-6)
    # poor-mans pytest.raises for testing errors on attribute access
    try:
        anything_not_real.pi
        assert False  # Should not get here
    except ModuleNotFoundError:
        pass
    assert isinstance(anything_not_real, lazy.DelayedImportErrorModule)
    # see if it changes for second access
    try:
        anything_not_real.pi
        assert False  # Should not get here
    except ModuleNotFoundError:
        pass


def test_lazy_import_impact_on_sys_modules():
    math = lazy._lazy_import("math")
    anything_not_real = lazy._lazy_import("anything_not_real")

    assert type(math) == types.ModuleType
    assert "math" in sys.modules
    assert type(anything_not_real) == lazy.DelayedImportErrorModule
    assert "anything_not_real" not in sys.modules

    # only do this if numpy is installed
    np_test = pytest.importorskip("numpy")
    np = lazy._lazy_import("numpy")
    assert type(np) == types.ModuleType
    assert "numpy" in sys.modules

    np.pi  # trigger load of numpy

    assert type(np) == types.ModuleType
    assert "numpy" in sys.modules


def test_lazy_import_nonbuiltins():
    sp = lazy._lazy_import("scipy")
    np = lazy._lazy_import("numpy")
    if isinstance(sp, lazy.DelayedImportErrorModule):
        try:
            sp.special.erf
            assert False
        except ModuleNotFoundError:
            pass
    elif isinstance(np, lazy.DelayedImportErrorModule):
        try:
            np.sin(np.pi)
            assert False
        except ModuleNotFoundError:
            pass
    else:
        assert sp.special.erf(np.pi) == pytest.approx(1, 1e-4)


def test_lazy_attach():
    name = "mymod"
    submods = ["mysubmodule", "anothersubmodule"]
    myall = {"not_real_submod": ["some_var_or_func"]}

    locls = {
        "attach": lazy.attach,
        "name": name,
        "submods": submods,
        "myall": myall,
    }
    s = "__getattr__, __lazy_dir__, __all__ = attach(name, submods, myall)"

    exec(s, {}, locls)
    expected = {
        "attach": lazy.attach,
        "name": name,
        "submods": submods,
        "myall": myall,
        "__getattr__": None,
        "__lazy_dir__": None,
        "__all__": None,
    }
    assert locls.keys() == expected.keys()
    for k, v in expected.items():
        if v is not None:
            assert locls[k] == v
