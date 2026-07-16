""" Test functions for limits module.

"""
import types
import warnings
import numpy as np
import pytest
from numpy._core import finfo, iinfo
from numpy import half, single, double, longdouble
from numpy.testing import assert_equal, assert_, assert_raises
from numpy._core.getlimits import _discovered_machar, _float_ma

##################################################

class TestPythonFloat:
    def test_singleton(self):
        ftype = finfo(float)
        ftype2 = finfo(float)
        assert_equal(id(ftype), id(ftype2))

class TestHalf:
    def test_singleton(self):
        ftype = finfo(half)
        ftype2 = finfo(half)
        assert_equal(id(ftype), id(ftype2))

class TestSingle:
    def test_singleton(self):
        ftype = finfo(single)
        ftype2 = finfo(single)
        assert_equal(id(ftype), id(ftype2))

class TestDouble:
    def test_singleton(self):
        ftype = finfo(double)
        ftype2 = finfo(double)
        assert_equal(id(ftype), id(ftype2))

class TestLongdouble:
    def test_singleton(self):
        ftype = finfo(longdouble)
        ftype2 = finfo(longdouble)
        assert_equal(id(ftype), id(ftype2))

def assert_finfo_equal(f1, f2):
    # assert two finfo instances have the same attributes
    for attr in ('bits', 'eps', 'epsneg', 'iexp', 'machep',
                 'max', 'maxexp', 'min', 'minexp', 'negep', 'nexp',
                 'nmant', 'precision', 'resolution', 'tiny',
                 'smallest_normal', 'smallest_subnormal'):
        assert_equal(getattr(f1, attr), getattr(f2, attr),
                     f'finfo instances {f1} and {f2} differ on {attr}')

def assert_iinfo_equal(i1, i2):
    # assert two iinfo instances have the same attributes
    for attr in ('bits', 'min', 'max'):
        assert_equal(getattr(i1, attr), getattr(i2, attr),
                     f'iinfo instances {i1} and {i2} differ on {attr}')

class TestFinfo:
    def test_basic(self):
        dts = list(zip(['f2', 'f4', 'f8', 'c8', 'c16'],
                       [np.float16, np.float32, np.float64, np.complex64,
                        np.complex128]))
        for dt1, dt2 in dts:
            assert_finfo_equal(finfo(dt1), finfo(dt2))

        assert_raises(ValueError, finfo, 'i4')

    def test_regression_gh23108(self):
        # np.float32(1.0) and np.float64(1.0) have the same hash and are
        # equal under the == operator
        f1 = np.finfo(np.float32(1.0))
        f2 = np.finfo(np.float64(1.0))
        assert f1 != f2

    def test_regression_gh23867(self):
        class NonHashableWithDtype:
            __hash__ = None
            dtype = np.dtype('float32')

        x = NonHashableWithDtype()
        assert np.finfo(x) == np.finfo(x.dtype)


class TestIinfo:
    def test_basic(self):
        dts = list(zip(['i1', 'i2', 'i4', 'i8',
                   'u1', 'u2', 'u4', 'u8'],
                  [np.int8, np.int16, np.int32, np.int64,
                   np.uint8, np.uint16, np.uint32, np.uint64]))
        for dt1, dt2 in dts:
            assert_iinfo_equal(iinfo(dt1), iinfo(dt2))

        assert_raises(ValueError, iinfo, 'f4')

    def test_unsigned_max(self):
        types = np._core.sctypes['uint']
        for T in types:
            with np.errstate(over="ignore"):
                max_calculated = T(0) - T(1)
            assert_equal(iinfo(T).max, max_calculated)

class TestRepr:
    def test_iinfo_repr(self):
        expected = "iinfo(min=-32768, max=32767, dtype=int16)"
        assert_equal(repr(np.iinfo(np.int16)), expected)

    def test_finfo_repr(self):
        expected = "finfo(resolution=1e-06, min=-3.4028235e+38," + \
                   " max=3.4028235e+38, dtype=float32)"
        assert_equal(repr(np.finfo(np.float32)), expected)


def test_instances():
    # Test the finfo and iinfo results on numeric instances agree with
    # the results on the corresponding types

    for c in [int, np.int16, np.int32, np.int64]:
        class_iinfo = iinfo(c)
        instance_iinfo = iinfo(c(12))

        assert_iinfo_equal(class_iinfo, instance_iinfo)

    for c in [float, np.float16, np.float32, np.float64]:
        class_finfo = finfo(c)
        instance_finfo = finfo(c(1.2))
        assert_finfo_equal(class_finfo, instance_finfo)

    with pytest.raises(ValueError):
        iinfo(10.)

    with pytest.raises(ValueError):
        iinfo('hi')

    with pytest.raises(ValueError):
        finfo(np.int64(1))


def assert_ma_equal(discovered, ma_like):
    # Check MachAr-like objects same as calculated MachAr instances
    for key, value in discovered.__dict__.items():
        assert_equal(value, getattr(ma_like, key))
        if hasattr(value, 'shape'):
            assert_equal(value.shape, getattr(ma_like, key).shape)
            assert_equal(value.dtype, getattr(ma_like, key).dtype)


def test_known_types():
    # Test we are correctly compiling parameters for known types
    for ftype, ma_like in ((np.float16, _float_ma[16]),
                           (np.float32, _float_ma[32]),
                           (np.float64, _float_ma[64])):
        assert_ma_equal(_discovered_machar(ftype), ma_like)
    # Suppress warning for broken discovery of double double on PPC
    with np.errstate(all='ignore'):
        ld_ma = _discovered_machar(np.longdouble)
    bytes = np.dtype(np.longdouble).itemsize
    if (ld_ma.it, ld_ma.maxexp) == (63, 16384) and bytes in (12, 16):
        # 80-bit extended precision
        assert_ma_equal(ld_ma, _float_ma[80])
    elif (ld_ma.it, ld_ma.maxexp) == (112, 16384) and bytes == 16:
        # IEE 754 128-bit
        assert_ma_equal(ld_ma, _float_ma[128])


def test_subnormal_warning():
    """Test that the subnormal is zero warning is not being raised."""
    with np.errstate(all='ignore'):
        ld_ma = _discovered_machar(np.longdouble)
    bytes = np.dtype(np.longdouble).itemsize
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        if (ld_ma.it, ld_ma.maxexp) == (63, 16384) and bytes in (12, 16):
            # 80-bit extended precision
            ld_ma.smallest_subnormal
            assert len(w) == 0
        elif (ld_ma.it, ld_ma.maxexp) == (112, 16384) and bytes == 16:
            # IEE 754 128-bit
            ld_ma.smallest_subnormal
            assert len(w) == 0
        else:
            # Double double
            ld_ma.smallest_subnormal
            # This test may fail on some platforms
            assert len(w) == 0


def test_plausible_finfo():
    # Assert that finfo returns reasonable results for all types
    for ftype in np._core.sctypes['float'] + np._core.sctypes['complex']:
        info = np.finfo(ftype)
        assert_(info.nmant > 1)
        assert_(info.minexp < -1)
        assert_(info.maxexp > 1)


class TestRuntimeSubscriptable:
    def test_finfo_generic(self):
        assert isinstance(np.finfo[np.float64], types.GenericAlias)

    def test_iinfo_generic(self):
        assert isinstance(np.iinfo[np.int_], types.GenericAlias)
