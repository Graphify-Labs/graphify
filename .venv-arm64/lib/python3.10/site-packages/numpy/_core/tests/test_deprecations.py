"""
Tests related to deprecation warnings. Also a convenient place
to document how deprecations should eventually be turned into errors.

"""
import warnings
import pytest
import tempfile
import re

import numpy as np
from numpy.testing import (
    assert_raises, assert_warns, assert_, assert_array_equal, SkipTest,
    KnownFailureException, break_cycles, temppath
    )

from numpy._core._multiarray_tests import fromstring_null_term_c_api
import numpy._core._struct_ufunc_tests as struct_ufunc

try:
    import pytz
    _has_pytz = True
except ImportError:
    _has_pytz = False


class _DeprecationTestCase:
    # Just as warning: warnings uses re.match, so the start of this message
    # must match.
    message = ''
    warning_cls = DeprecationWarning

    def setup_method(self):
        self.warn_ctx = warnings.catch_warnings(record=True)
        self.log = self.warn_ctx.__enter__()

        # Do *not* ignore other DeprecationWarnings. Ignoring warnings
        # can give very confusing results because of
        # https://bugs.python.org/issue4180 and it is probably simplest to
        # try to keep the tests cleanly giving only the right warning type.
        # (While checking them set to "error" those are ignored anyway)
        # We still have them show up, because otherwise they would be raised
        warnings.filterwarnings("always", category=self.warning_cls)
        warnings.filterwarnings("always", message=self.message,
                                category=self.warning_cls)

    def teardown_method(self):
        self.warn_ctx.__exit__()

    def assert_deprecated(self, function, num=1, ignore_others=False,
                          function_fails=False,
                          exceptions=np._NoValue,
                          args=(), kwargs={}):
        """Test if DeprecationWarnings are given and raised.

        This first checks if the function when called gives `num`
        DeprecationWarnings, after that it tries to raise these
        DeprecationWarnings and compares them with `exceptions`.
        The exceptions can be different for cases where this code path
        is simply not anticipated and the exception is replaced.

        Parameters
        ----------
        function : callable
            The function to test
        num : int
            Number of DeprecationWarnings to expect. This should normally be 1.
        ignore_others : bool
            Whether warnings of the wrong type should be ignored (note that
            the message is not checked)
        function_fails : bool
            If the function would normally fail, setting this will check for
            warnings inside a try/except block.
        exceptions : Exception or tuple of Exceptions
            Exception to expect when turning the warnings into an error.
            The default checks for DeprecationWarnings. If exceptions is
            empty the function is expected to run successfully.
        args : tuple
            Arguments for `function`
        kwargs : dict
            Keyword arguments for `function`
        """
        __tracebackhide__ = True  # Hide traceback for py.test

        # reset the log
        self.log[:] = []

        if exceptions is np._NoValue:
            exceptions = (self.warning_cls,)

        try:
            function(*args, **kwargs)
        except (Exception if function_fails else tuple()):
            pass

        # just in case, clear the registry
        num_found = 0
        for warning in self.log:
            if warning.category is self.warning_cls:
                num_found += 1
            elif not ignore_others:
                raise AssertionError(
                        "expected %s but got: %s" %
                        (self.warning_cls.__name__, warning.category))
        if num is not None and num_found != num:
            msg = "%i warnings found but %i expected." % (len(self.log), num)
            lst = [str(w) for w in self.log]
            raise AssertionError("\n".join([msg] + lst))

        with warnings.catch_warnings():
            warnings.filterwarnings("error", message=self.message,
                                    category=self.warning_cls)
            try:
                function(*args, **kwargs)
                if exceptions != tuple():
                    raise AssertionError(
                            "No error raised during function call")
            except exceptions:
                if exceptions == tuple():
                    raise AssertionError(
                            "Error raised during function call")

    def assert_not_deprecated(self, function, args=(), kwargs={}):
        """Test that warnings are not raised.

        This is just a shorthand for:

        self.assert_deprecated(function, num=0, ignore_others=True,
                        exceptions=tuple(), args=args, kwargs=kwargs)
        """
        self.assert_deprecated(function, num=0, ignore_others=True,
                        exceptions=tuple(), args=args, kwargs=kwargs)


class _VisibleDeprecationTestCase(_DeprecationTestCase):
    warning_cls = np.exceptions.VisibleDeprecationWarning


class TestDTypeAttributeIsDTypeDeprecation(_DeprecationTestCase):
    # Deprecated 2021-01-05, NumPy 1.21
    message = r".*`.dtype` attribute"

    def test_deprecation_dtype_attribute_is_dtype(self):
        class dt:
            dtype = "f8"

        class vdt(np.void):
            dtype = "f,f"

        self.assert_deprecated(lambda: np.dtype(dt))
        self.assert_deprecated(lambda: np.dtype(dt()))
        self.assert_deprecated(lambda: np.dtype(vdt))
        self.assert_deprecated(lambda: np.dtype(vdt(1)))


class TestTestDeprecated:
    def test_assert_deprecated(self):
        test_case_instance = _DeprecationTestCase()
        test_case_instance.setup_method()
        assert_raises(AssertionError,
                      test_case_instance.assert_deprecated,
                      lambda: None)

        def foo():
            warnings.warn("foo", category=DeprecationWarning, stacklevel=2)

        test_case_instance.assert_deprecated(foo)
        test_case_instance.teardown_method()


class TestNonNumericConjugate(_DeprecationTestCase):
    """
    Deprecate no-op behavior of ndarray.conjugate on non-numeric dtypes,
    which conflicts with the error behavior of np.conjugate.
    """
    def test_conjugate(self):
        for a in np.array(5), np.array(5j):
            self.assert_not_deprecated(a.conjugate)
        for a in (np.array('s'), np.array('2016', 'M'),
                np.array((1, 2), [('a', int), ('b', int)])):
            self.assert_deprecated(a.conjugate)


class TestDatetimeEvent(_DeprecationTestCase):
    # 2017-08-11, 1.14.0
    def test_3_tuple(self):
        for cls in (np.datetime64, np.timedelta64):
            # two valid uses - (unit, num) and (unit, num, den, None)
            self.assert_not_deprecated(cls, args=(1, ('ms', 2)))
            self.assert_not_deprecated(cls, args=(1, ('ms', 2, 1, None)))

            # trying to use the event argument, removed in 1.7.0, is deprecated
            # it used to be a uint8
            self.assert_deprecated(cls, args=(1, ('ms', 2, 'event')))
            self.assert_deprecated(cls, args=(1, ('ms', 2, 63)))
            self.assert_deprecated(cls, args=(1, ('ms', 2, 1, 'event')))
            self.assert_deprecated(cls, args=(1, ('ms', 2, 1, 63)))


class TestBincount(_DeprecationTestCase):
    # 2017-06-01, 1.14.0
    def test_bincount_minlength(self):
        self.assert_deprecated(lambda: np.bincount([1, 2, 3], minlength=None))

    # 2024-07-29, 2.1.0
    @pytest.mark.parametrize('badlist', [[0.5, 1.2, 1.5],
                                         ['0', '1', '1']])
    def test_bincount_bad_list(self, badlist):
        self.assert_deprecated(lambda: np.bincount(badlist))


class TestGeneratorSum(_DeprecationTestCase):
    # 2018-02-25, 1.15.0
    def test_generator_sum(self):
        self.assert_deprecated(np.sum, args=((i for i in range(5)),))


class TestFromstring(_DeprecationTestCase):
    # 2017-10-19, 1.14
    def test_fromstring(self):
        self.assert_deprecated(np.fromstring, args=('\x00'*80,))


class TestFromStringAndFileInvalidData(_DeprecationTestCase):
    # 2019-06-08, 1.17.0
    # Tests should be moved to real tests when deprecation is done.
    message = "string or file could not be read to its end"

    @pytest.mark.parametrize("invalid_str", [",invalid_data", "invalid_sep"])
    def test_deprecate_unparsable_data_file(self, invalid_str):
        x = np.array([1.51, 2, 3.51, 4], dtype=float)

        with tempfile.TemporaryFile(mode="w") as f:
            x.tofile(f, sep=',', format='%.2f')
            f.write(invalid_str)

            f.seek(0)
            self.assert_deprecated(lambda: np.fromfile(f, sep=","))
            f.seek(0)
            self.assert_deprecated(lambda: np.fromfile(f, sep=",", count=5))
            # Should not raise:
            with warnings.catch_warnings():
                warnings.simplefilter("error", DeprecationWarning)
                f.seek(0)
                res = np.fromfile(f, sep=",", count=4)
                assert_array_equal(res, x)

    @pytest.mark.parametrize("invalid_str", [",invalid_data", "invalid_sep"])
    def test_deprecate_unparsable_string(self, invalid_str):
        x = np.array([1.51, 2, 3.51, 4], dtype=float)
        x_str = "1.51,2,3.51,4{}".format(invalid_str)

        self.assert_deprecated(lambda: np.fromstring(x_str, sep=","))
        self.assert_deprecated(lambda: np.fromstring(x_str, sep=",", count=5))

        # The C-level API can use not fixed size, but 0 terminated strings,
        # so test that as well:
        bytestr = x_str.encode("ascii")
        self.assert_deprecated(lambda: fromstring_null_term_c_api(bytestr))

        with assert_warns(DeprecationWarning):
            # this is slightly strange, in that fromstring leaves data
            # potentially uninitialized (would be good to error when all is
            # read, but count is larger then actual data maybe).
            res = np.fromstring(x_str, sep=",", count=5)
            assert_array_equal(res[:-1], x)

        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)

            # Should not raise:
            res = np.fromstring(x_str, sep=",", count=4)
            assert_array_equal(res, x)


class TestToString(_DeprecationTestCase):
    # 2020-03-06 1.19.0
    message = re.escape("tostring() is deprecated. Use tobytes() instead.")

    def test_tostring(self):
        arr = np.array(list(b"test\xFF"), dtype=np.uint8)
        self.assert_deprecated(arr.tostring)

    def test_tostring_matches_tobytes(self):
        arr = np.array(list(b"test\xFF"), dtype=np.uint8)
        b = arr.tobytes()
        with assert_warns(DeprecationWarning):
            s = arr.tostring()
        assert s == b


class TestDTypeCoercion(_DeprecationTestCase):
    # 2020-02-06 1.19.0
    message = "Converting .* to a dtype .*is deprecated"
    deprecated_types = [
        # The builtin scalar super types:
        np.generic, np.flexible, np.number,
        np.inexact, np.floating, np.complexfloating,
        np.integer, np.unsignedinteger, np.signedinteger,
        # character is a deprecated S1 special case:
        np.character,
    ]

    def test_dtype_coercion(self):
        for scalar_type in self.deprecated_types:
            self.assert_deprecated(np.dtype, args=(scalar_type,))

    def test_array_construction(self):
        for scalar_type in self.deprecated_types:
            self.assert_deprecated(np.array, args=([], scalar_type,))

    def test_not_deprecated(self):
        # All specific types are not deprecated:
        for group in np._core.sctypes.values():
            for scalar_type in group:
                self.assert_not_deprecated(np.dtype, args=(scalar_type,))

        for scalar_type in [type, dict, list, tuple]:
            # Typical python types are coerced to object currently:
            self.assert_not_deprecated(np.dtype, args=(scalar_type,))


class BuiltInRoundComplexDType(_DeprecationTestCase):
    # 2020-03-31 1.19.0
    deprecated_types = [np.csingle, np.cdouble, np.clongdouble]
    not_deprecated_types = [
        np.int8, np.int16, np.int32, np.int64,
        np.uint8, np.uint16, np.uint32, np.uint64,
        np.float16, np.float32, np.float64,
    ]

    def test_deprecated(self):
        for scalar_type in self.deprecated_types:
            scalar = scalar_type(0)
            self.assert_deprecated(round, args=(scalar,))
            self.assert_deprecated(round, args=(scalar, 0))
            self.assert_deprecated(round, args=(scalar,), kwargs={'ndigits': 0})

    def test_not_deprecated(self):
        for scalar_type in self.not_deprecated_types:
            scalar = scalar_type(0)
            self.assert_not_deprecated(round, args=(scalar,))
            self.assert_not_deprecated(round, args=(scalar, 0))
            self.assert_not_deprecated(round, args=(scalar,), kwargs={'ndigits': 0})


class TestIncorrectAdvancedIndexWithEmptyResult(_DeprecationTestCase):
    # 2020-05-27, NumPy 1.20.0
    message = "Out of bound index found. This was previously ignored.*"

    @pytest.mark.parametrize("index", [([3, 0],), ([0, 0], [3, 0])])
    def test_empty_subspace(self, index):
        # Test for both a single and two/multiple advanced indices. These
        # This will raise an IndexError in the future.
        arr = np.ones((2, 2, 0))
        self.assert_deprecated(arr.__getitem__, args=(index,))
        self.assert_deprecated(arr.__setitem__, args=(index, 0.))

        # for this array, the subspace is only empty after applying the slice
        arr2 = np.ones((2, 2, 1))
        index2 = (slice(0, 0),) + index
        self.assert_deprecated(arr2.__getitem__, args=(index2,))
        self.assert_deprecated(arr2.__setitem__, args=(index2, 0.))

    def test_empty_index_broadcast_not_deprecated(self):
        arr = np.ones((2, 2, 2))

        index = ([[3], [2]], [])  # broadcast to an empty result.
        self.assert_not_deprecated(arr.__getitem__, args=(index,))
        self.assert_not_deprecated(arr.__setitem__,
                                   args=(index, np.empty((2, 0, 2))))


class TestNonExactMatchDeprecation(_DeprecationTestCase):
    # 2020-04-22
    def test_non_exact_match(self):
        arr = np.array([[3, 6, 6], [4, 5, 1]])
        # misspelt mode check
        self.assert_deprecated(lambda: np.ravel_multi_index(arr, (7, 6), mode='Cilp'))
        # using completely different word with first character as R
        self.assert_deprecated(lambda: np.searchsorted(arr[0], 4, side='Random'))


class TestMatrixInOuter(_DeprecationTestCase):
    # 2020-05-13 NumPy 1.20.0
    message = (r"add.outer\(\) was passed a numpy matrix as "
               r"(first|second) argument.")

    def test_deprecated(self):
        arr = np.array([1, 2, 3])
        m = np.array([1, 2, 3]).view(np.matrix)
        self.assert_deprecated(np.add.outer, args=(m, m), num=2)
        self.assert_deprecated(np.add.outer, args=(arr, m))
        self.assert_deprecated(np.add.outer, args=(m, arr))
        self.assert_not_deprecated(np.add.outer, args=(arr, arr))


class FlatteningConcatenateUnsafeCast(_DeprecationTestCase):
    # NumPy 1.20, 2020-09-03
    message = "concatenate with `axis=None` will use same-kind casting"

    def test_deprecated(self):
        self.assert_deprecated(np.concatenate,
                args=(([0.], [1.]),),
                kwargs=dict(axis=None, out=np.empty(2, dtype=np.int64)))

    def test_not_deprecated(self):
        self.assert_not_deprecated(np.concatenate,
                args=(([0.], [1.]),),
                kwargs={'axis': None, 'out': np.empty(2, dtype=np.int64),
                        'casting': "unsafe"})

        with assert_raises(TypeError):
            # Tests should notice if the deprecation warning is given first...
            np.concatenate(([0.], [1.]), out=np.empty(2, dtype=np.int64),
                           casting="same_kind")


class TestDeprecatedUnpickleObjectScalar(_DeprecationTestCase):
    # Deprecated 2020-11-24, NumPy 1.20
    """
    Technically, it should be impossible to create numpy object scalars,
    but there was an unpickle path that would in theory allow it. That
    path is invalid and must lead to the warning.
    """
    message = "Unpickling a scalar with object dtype is deprecated."

    def test_deprecated(self):
        ctor = np._core.multiarray.scalar
        self.assert_deprecated(lambda: ctor(np.dtype("O"), 1))


class TestSingleElementSignature(_DeprecationTestCase):
    # Deprecated 2021-04-01, NumPy 1.21
    message = r"The use of a length 1"

    def test_deprecated(self):
        self.assert_deprecated(lambda: np.add(1, 2, signature="d"))
        self.assert_deprecated(lambda: np.add(1, 2, sig=(np.dtype("l"),)))


class TestCtypesGetter(_DeprecationTestCase):
    # Deprecated 2021-05-18, Numpy 1.21.0
    warning_cls = DeprecationWarning
    ctypes = np.array([1]).ctypes

    @pytest.mark.parametrize(
        "name", ["get_data", "get_shape", "get_strides", "get_as_parameter"]
    )
    def test_deprecated(self, name: str) -> None:
        func = getattr(self.ctypes, name)
        self.assert_deprecated(lambda: func())

    @pytest.mark.parametrize(
        "name", ["data", "shape", "strides", "_as_parameter_"]
    )
    def test_not_deprecated(self, name: str) -> None:
        self.assert_not_deprecated(lambda: getattr(self.ctypes, name))


PARTITION_DICT = {
    "partition method": np.arange(10).partition,
    "argpartition method": np.arange(10).argpartition,
    "partition function": lambda kth: np.partition(np.arange(10), kth),
    "argpartition function": lambda kth: np.argpartition(np.arange(10), kth),
}


@pytest.mark.parametrize("func", PARTITION_DICT.values(), ids=PARTITION_DICT)
class TestPartitionBoolIndex(_DeprecationTestCase):
    # Deprecated 2021-09-29, NumPy 1.22
    warning_cls = DeprecationWarning
    message = "Passing booleans as partition index is deprecated"

    def test_deprecated(self, func):
        self.assert_deprecated(lambda: func(True))
        self.assert_deprecated(lambda: func([False, True]))

    def test_not_deprecated(self, func):
        self.assert_not_deprecated(lambda: func(1))
        self.assert_not_deprecated(lambda: func([0, 1]))


class TestMachAr(_DeprecationTestCase):
    # Deprecated 2022-11-22, NumPy 1.25
    warning_cls = DeprecationWarning

    def test_deprecated_module(self):
        self.assert_deprecated(lambda: np._core.MachAr)


class TestQuantileInterpolationDeprecation(_DeprecationTestCase):
    # Deprecated 2021-11-08, NumPy 1.22
    @pytest.mark.parametrize("func",
        [np.percentile, np.quantile, np.nanpercentile, np.nanquantile])
    def test_deprecated(self, func):
        self.assert_deprecated(
            lambda: func([0., 1.], 0., interpolation="linear"))
        self.assert_deprecated(
            lambda: func([0., 1.], 0., interpolation="nearest"))

    @pytest.mark.parametrize("func",
            [np.percentile, np.quantile, np.nanpercentile, np.nanquantile])
    def test_both_passed(self, func):
        with warnings.catch_warnings():
            # catch the DeprecationWarning so that it does not raise:
            warnings.simplefilter("always", DeprecationWarning)
            with pytest.raises(TypeError):
                func([0., 1.], 0., interpolation="nearest", method="nearest")


class TestArrayFinalizeNone(_DeprecationTestCase):
    message = "Setting __array_finalize__ = None"

    def test_use_none_is_deprecated(self):
        # Deprecated way that ndarray itself showed nothing needs finalizing.
        class NoFinalize(np.ndarray):
            __array_finalize__ = None

        self.assert_deprecated(lambda: np.array(1).view(NoFinalize))


class TestLoadtxtParseIntsViaFloat(_DeprecationTestCase):
    # Deprecated 2022-07-03, NumPy 1.23
    # This test can be removed without replacement after the deprecation.
    # The tests:
    #   * numpy/lib/tests/test_loadtxt.py::test_integer_signs
    #   * lib/tests/test_loadtxt.py::test_implicit_cast_float_to_int_fails
    # Have a warning filter that needs to be removed.
    message = r"loadtxt\(\): Parsing an integer via a float is deprecated.*"

    @pytest.mark.parametrize("dtype", np.typecodes["AllInteger"])
    def test_deprecated_warning(self, dtype):
        with pytest.warns(DeprecationWarning, match=self.message):
            np.loadtxt(["10.5"], dtype=dtype)

    @pytest.mark.parametrize("dtype", np.typecodes["AllInteger"])
    def test_deprecated_raised(self, dtype):
        # The DeprecationWarning is chained when raised, so test manually:
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            try:
                np.loadtxt(["10.5"], dtype=dtype)
            except ValueError as e:
                assert isinstance(e.__cause__, DeprecationWarning)


class TestScalarConversion(_DeprecationTestCase):
    # 2023-01-02, 1.25.0
    def test_float_conversion(self):
        self.assert_deprecated(float, args=(np.array([3.14]),))

    def test_behaviour(self):
        b = np.array([[3.14]])
        c = np.zeros(5)
        with pytest.warns(DeprecationWarning):
            c[0] = b


class TestPyIntConversion(_DeprecationTestCase):
    message = r".*stop allowing conversion of out-of-bound.*"

    @pytest.mark.parametrize("dtype", np.typecodes["AllInteger"])
    def test_deprecated_scalar(self, dtype):
        dtype = np.dtype(dtype)
        info = np.iinfo(dtype)

        # Cover the most common creation paths (all end up in the
        # same place):
        def scalar(value, dtype):
            dtype.type(value)

        def assign(value, dtype):
            arr = np.array([0, 0, 0], dtype=dtype)
            arr[2] = value

        def create(value, dtype):
            np.array([value], dtype=dtype)

        for creation_func in [scalar, assign, create]:
            try:
                self.assert_deprecated(
                        lambda: creation_func(info.min - 1, dtype))
            except OverflowError:
                pass  # OverflowErrors always happened also before and are OK.

            try:
                self.assert_deprecated(
                        lambda: creation_func(info.max + 1, dtype))
            except OverflowError:
                pass  # OverflowErrors always happened also before and are OK.


@pytest.mark.parametrize("name", ["str", "bytes", "object"])
def test_future_scalar_attributes(name):
    # FutureWarning added 2022-11-17, NumPy 1.24,
    assert name not in dir(np)  # we may want to not add them
    with pytest.warns(FutureWarning,
            match=f"In the future .*{name}"):
        assert not hasattr(np, name)

    # Unfortunately, they are currently still valid via `np.dtype()`
    np.dtype(name)
    name in np._core.sctypeDict


# Ignore the above future attribute warning for this test.
@pytest.mark.filterwarnings("ignore:In the future:FutureWarning")
class TestRemovedGlobals:
    # Removed 2023-01-12, NumPy 1.24.0
    # Not a deprecation, but the large error was added to aid those who missed
    # the previous deprecation, and should be removed similarly to one
    # (or faster).
    @pytest.mark.parametrize("name",
            ["object", "float", "complex", "str", "int"])
    def test_attributeerror_includes_info(self, name):
        msg = f".*\n`np.{name}` was a deprecated alias for the builtin"
        with pytest.raises(AttributeError, match=msg):
            getattr(np, name)


class TestDeprecatedFinfo(_DeprecationTestCase):
    # Deprecated in NumPy 1.25, 2023-01-16
    def test_deprecated_none(self):
        self.assert_deprecated(np.finfo, args=(None,))


class TestMathAlias(_DeprecationTestCase):
    def test_deprecated_np_lib_math(self):
        self.assert_deprecated(lambda: np.lib.math)


class TestLibImports(_DeprecationTestCase):
    # Deprecated in Numpy 1.26.0, 2023-09
    def test_lib_functions_deprecation_call(self):
        from numpy.lib._utils_impl import safe_eval
        from numpy.lib._npyio_impl import recfromcsv, recfromtxt
        from numpy.lib._function_base_impl import disp
        from numpy.lib._shape_base_impl import get_array_wrap
        from numpy._core.numerictypes import maximum_sctype
        from numpy.lib.tests.test_io import TextIO
        from numpy import in1d, row_stack, trapz

        self.assert_deprecated(lambda: safe_eval("None"))

        data_gen = lambda: TextIO('A,B\n0,1\n2,3')
        kwargs = dict(delimiter=",", missing_values="N/A", names=True)
        self.assert_deprecated(lambda: recfromcsv(data_gen()))
        self.assert_deprecated(lambda: recfromtxt(data_gen(), **kwargs))

        self.assert_deprecated(lambda: disp("test"))
        self.assert_deprecated(lambda: get_array_wrap())
        self.assert_deprecated(lambda: maximum_sctype(int))

        self.assert_deprecated(lambda: in1d([1], [1]))
        self.assert_deprecated(lambda: row_stack([[]]))
        self.assert_deprecated(lambda: trapz([1], [1]))
        self.assert_deprecated(lambda: np.chararray)


class TestDeprecatedDTypeAliases(_DeprecationTestCase):

    def _check_for_warning(self, func):
        with warnings.catch_warnings(record=True) as caught_warnings:
            func()
        assert len(caught_warnings) == 1
        w = caught_warnings[0]
        assert w.category is DeprecationWarning
        assert "alias 'a' was deprecated in NumPy 2.0" in str(w.message)

    def test_a_dtype_alias(self):
        for dtype in ["a", "a10"]:
            f = lambda: np.dtype(dtype)
            self._check_for_warning(f)
            self.assert_deprecated(f)
            f = lambda: np.array(["hello", "world"]).astype("a10")
            self._check_for_warning(f)
            self.assert_deprecated(f)


class TestDeprecatedArrayWrap(_DeprecationTestCase):
    message = "__array_wrap__.*"

    def test_deprecated(self):
        class Test1:
            def __array__(self, dtype=None, copy=None):
                return np.arange(4)

            def __array_wrap__(self, arr, context=None):
                self.called = True
                return 'pass context'

        class Test2(Test1):
            def __array_wrap__(self, arr):
                self.called = True
                return 'pass'

        test1 = Test1()
        test2 = Test2()
        self.assert_deprecated(lambda: np.negative(test1))
        assert test1.called
        self.assert_deprecated(lambda: np.negative(test2))
        assert test2.called



class TestDeprecatedDTypeParenthesizedRepeatCount(_DeprecationTestCase):
    message = "Passing in a parenthesized single number"

    @pytest.mark.parametrize("string", ["(2)i,", "(3)3S,", "f,(2)f"])
    def test_parenthesized_repeat_count(self, string):
        self.assert_deprecated(np.dtype, args=(string,))


class TestDeprecatedSaveFixImports(_DeprecationTestCase):
    # Deprecated in Numpy 2.1, 2024-05
    message = "The 'fix_imports' flag is deprecated and has no effect."

    def test_deprecated(self):
        with temppath(suffix='.npy') as path:
            sample_args = (path, np.array(np.zeros((1024, 10))))
            self.assert_not_deprecated(np.save, args=sample_args)
            self.assert_deprecated(np.save, args=sample_args,
                                kwargs={'fix_imports': True})
            self.assert_deprecated(np.save, args=sample_args,
                                kwargs={'fix_imports': False})
            for allow_pickle in [True, False]:
                self.assert_not_deprecated(np.save, args=sample_args,
                                        kwargs={'allow_pickle': allow_pickle})
                self.assert_deprecated(np.save, args=sample_args,
                                    kwargs={'allow_pickle': allow_pickle,
                                            'fix_imports': True})
                self.assert_deprecated(np.save, args=sample_args,
                                    kwargs={'allow_pickle': allow_pickle,
                                            'fix_imports': False})


class TestAddNewdocUFunc(_DeprecationTestCase):
    # Deprecated in Numpy 2.2, 2024-11
    def test_deprecated(self):
        self.assert_deprecated(
            lambda: np._core.umath._add_newdoc_ufunc(
                struct_ufunc.add_triplet, "new docs"
            )
        )
