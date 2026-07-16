import re
import sys
import warnings
import types
import unittest
import contextlib
from collections.abc import Callable
from typing import Any, TypeVar
from pathlib import Path

import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

AR_f8: npt.NDArray[np.float64]
AR_i8: npt.NDArray[np.int64]

bool_obj: bool
suppress_obj: np.testing.suppress_warnings
FT = TypeVar("FT", bound=Callable[..., Any])

def func() -> int: ...

def func2(
    x: npt.NDArray[np.number[Any]],
    y: npt.NDArray[np.number[Any]],
) -> npt.NDArray[np.bool]: ...

assert_type(np.testing.KnownFailureException(), np.testing.KnownFailureException)
assert_type(np.testing.IgnoreException(), np.testing.IgnoreException)

assert_type(
    np.testing.clear_and_catch_warnings(modules=[np.testing]),
    np.testing.clear_and_catch_warnings[None],
)
assert_type(
    np.testing.clear_and_catch_warnings(True),
    np.testing.clear_and_catch_warnings[list[warnings.WarningMessage]],
)
assert_type(
    np.testing.clear_and_catch_warnings(False),
    np.testing.clear_and_catch_warnings[None],
)
assert_type(
    np.testing.clear_and_catch_warnings(bool_obj),
    np.testing.clear_and_catch_warnings,
)
assert_type(
    np.testing.clear_and_catch_warnings.class_modules,
    tuple[types.ModuleType, ...],
)
assert_type(
    np.testing.clear_and_catch_warnings.modules,
    set[types.ModuleType],
)

with np.testing.clear_and_catch_warnings(True) as c1:
    assert_type(c1, list[warnings.WarningMessage])
with np.testing.clear_and_catch_warnings() as c2:
    assert_type(c2, None)

assert_type(np.testing.suppress_warnings("once"), np.testing.suppress_warnings)
assert_type(np.testing.suppress_warnings()(func), Callable[[], int])
assert_type(suppress_obj.filter(RuntimeWarning), None)
assert_type(suppress_obj.record(RuntimeWarning), list[warnings.WarningMessage])
with suppress_obj as c3:
    assert_type(c3, np.testing.suppress_warnings)

assert_type(np.testing.verbose, int)
assert_type(np.testing.IS_PYPY, bool)
assert_type(np.testing.HAS_REFCOUNT, bool)
assert_type(np.testing.HAS_LAPACK64, bool)

assert_type(np.testing.assert_(1, msg="test"), None)
assert_type(np.testing.assert_(2, msg=lambda: "test"), None)

if sys.platform == "win32" or sys.platform == "cygwin":
    assert_type(np.testing.memusage(), int)
elif sys.platform == "linux":
    assert_type(np.testing.memusage(), None | int)

assert_type(np.testing.jiffies(), int)

assert_type(np.testing.build_err_msg([0, 1, 2], "test"), str)
assert_type(np.testing.build_err_msg(range(2), "test", header="header"), str)
assert_type(np.testing.build_err_msg(np.arange(9).reshape(3, 3), "test", verbose=False), str)
assert_type(np.testing.build_err_msg("abc", "test", names=["x", "y"]), str)
assert_type(np.testing.build_err_msg([1.0, 2.0], "test", precision=5), str)

assert_type(np.testing.assert_equal({1}, {1}), None)
assert_type(np.testing.assert_equal([1, 2, 3], [1, 2, 3], err_msg="fail"), None)
assert_type(np.testing.assert_equal(1, 1.0, verbose=True), None)

assert_type(np.testing.print_assert_equal('Test XYZ of func xyz', [0, 1], [0, 1]), None)

assert_type(np.testing.assert_almost_equal(1.0, 1.1), None)
assert_type(np.testing.assert_almost_equal([1, 2, 3], [1, 2, 3], err_msg="fail"), None)
assert_type(np.testing.assert_almost_equal(1, 1.0, verbose=True), None)
assert_type(np.testing.assert_almost_equal(1, 1.0001, decimal=2), None)

assert_type(np.testing.assert_approx_equal(1.0, 1.1), None)
assert_type(np.testing.assert_approx_equal("1", "2", err_msg="fail"), None)
assert_type(np.testing.assert_approx_equal(1, 1.0, verbose=True), None)
assert_type(np.testing.assert_approx_equal(1, 1.0001, significant=2), None)

assert_type(np.testing.assert_array_compare(func2, AR_i8, AR_f8, err_msg="test"), None)
assert_type(np.testing.assert_array_compare(func2, AR_i8, AR_f8, verbose=True), None)
assert_type(np.testing.assert_array_compare(func2, AR_i8, AR_f8, header="header"), None)
assert_type(np.testing.assert_array_compare(func2, AR_i8, AR_f8, precision=np.int64()), None)
assert_type(np.testing.assert_array_compare(func2, AR_i8, AR_f8, equal_nan=False), None)
assert_type(np.testing.assert_array_compare(func2, AR_i8, AR_f8, equal_inf=True), None)

assert_type(np.testing.assert_array_equal(AR_i8, AR_f8), None)
assert_type(np.testing.assert_array_equal(AR_i8, AR_f8, err_msg="test"), None)
assert_type(np.testing.assert_array_equal(AR_i8, AR_f8, verbose=True), None)

assert_type(np.testing.assert_array_almost_equal(AR_i8, AR_f8), None)
assert_type(np.testing.assert_array_almost_equal(AR_i8, AR_f8, err_msg="test"), None)
assert_type(np.testing.assert_array_almost_equal(AR_i8, AR_f8, verbose=True), None)
assert_type(np.testing.assert_array_almost_equal(AR_i8, AR_f8, decimal=1), None)

assert_type(np.testing.assert_array_less(AR_i8, AR_f8), None)
assert_type(np.testing.assert_array_less(AR_i8, AR_f8, err_msg="test"), None)
assert_type(np.testing.assert_array_less(AR_i8, AR_f8, verbose=True), None)

assert_type(np.testing.runstring("1 + 1", {}), Any)
assert_type(np.testing.runstring("int64() + 1", {"int64": np.int64}), Any)

assert_type(np.testing.assert_string_equal("1", "1"), None)

assert_type(np.testing.rundocs(), None)
assert_type(np.testing.rundocs("test.py"), None)
assert_type(np.testing.rundocs(Path("test.py"), raise_on_error=True), None)

def func3(a: int) -> bool: ...

assert_type(
    np.testing.assert_raises(RuntimeWarning),
    unittest.case._AssertRaisesContext[RuntimeWarning],
)
assert_type(np.testing.assert_raises(RuntimeWarning, func3, 5), None)

assert_type(
    np.testing.assert_raises_regex(RuntimeWarning, r"test"),
    unittest.case._AssertRaisesContext[RuntimeWarning],
)
assert_type(np.testing.assert_raises_regex(RuntimeWarning, b"test", func3, 5), None)
assert_type(np.testing.assert_raises_regex(RuntimeWarning, re.compile(b"test"), func3, 5), None)

class Test: ...

def decorate(a: FT) -> FT:
    return a

assert_type(np.testing.decorate_methods(Test, decorate), None)
assert_type(np.testing.decorate_methods(Test, decorate, None), None)
assert_type(np.testing.decorate_methods(Test, decorate, "test"), None)
assert_type(np.testing.decorate_methods(Test, decorate, b"test"), None)
assert_type(np.testing.decorate_methods(Test, decorate, re.compile("test")), None)

assert_type(np.testing.measure("for i in range(1000): np.sqrt(i**2)"), float)
assert_type(np.testing.measure(b"for i in range(1000): np.sqrt(i**2)", times=5), float)

assert_type(np.testing.assert_allclose(AR_i8, AR_f8), None)
assert_type(np.testing.assert_allclose(AR_i8, AR_f8, rtol=0.005), None)
assert_type(np.testing.assert_allclose(AR_i8, AR_f8, atol=1), None)
assert_type(np.testing.assert_allclose(AR_i8, AR_f8, equal_nan=True), None)
assert_type(np.testing.assert_allclose(AR_i8, AR_f8, err_msg="err"), None)
assert_type(np.testing.assert_allclose(AR_i8, AR_f8, verbose=False), None)

assert_type(np.testing.assert_array_almost_equal_nulp(AR_i8, AR_f8, nulp=2), None)

assert_type(np.testing.assert_array_max_ulp(AR_i8, AR_f8, maxulp=2), npt.NDArray[Any])
assert_type(np.testing.assert_array_max_ulp(AR_i8, AR_f8, dtype=np.float32), npt.NDArray[Any])

assert_type(np.testing.assert_warns(RuntimeWarning), contextlib._GeneratorContextManager[None])
assert_type(np.testing.assert_warns(RuntimeWarning, func3, 5), bool)

def func4(a: int, b: str) -> bool: ...

assert_type(np.testing.assert_no_warnings(), contextlib._GeneratorContextManager[None])
assert_type(np.testing.assert_no_warnings(func3, 5), bool)
assert_type(np.testing.assert_no_warnings(func4, a=1, b="test"), bool)
assert_type(np.testing.assert_no_warnings(func4, 1, "test"), bool)

assert_type(np.testing.tempdir("test_dir"), contextlib._GeneratorContextManager[str])
assert_type(np.testing.tempdir(prefix=b"test"), contextlib._GeneratorContextManager[bytes])
assert_type(np.testing.tempdir("test_dir", dir=Path("here")), contextlib._GeneratorContextManager[str])

assert_type(np.testing.temppath("test_dir", text=True), contextlib._GeneratorContextManager[str])
assert_type(np.testing.temppath(prefix=b"test"), contextlib._GeneratorContextManager[bytes])
assert_type(np.testing.temppath("test_dir", dir=Path("here")), contextlib._GeneratorContextManager[str])

assert_type(np.testing.assert_no_gc_cycles(), contextlib._GeneratorContextManager[None])
assert_type(np.testing.assert_no_gc_cycles(func3, 5), None)

assert_type(np.testing.break_cycles(), None)

assert_type(np.testing.TestCase(), unittest.case.TestCase)
