from tempfile import NamedTemporaryFile

import pytest

import numpy as np
from numpy.testing import assert_array_equal
from numpy._core._multiarray_umath import (
    _discover_array_parameters as discover_array_params, _get_sfloat_dtype)


SF = _get_sfloat_dtype()


class TestSFloat:
    def _get_array(self, scaling, aligned=True):
        if not aligned:
            a = np.empty(3*8 + 1, dtype=np.uint8)[1:]
            a = a.view(np.float64)
            a[:] = [1., 2., 3.]
        else:
            a = np.array([1., 2., 3.])

        a *= 1./scaling  # the casting code also uses the reciprocal.
        return a.view(SF(scaling))

    def test_sfloat_rescaled(self):
        sf = SF(1.)
        sf2 = sf.scaled_by(2.)
        assert sf2.get_scaling() == 2.
        sf6 = sf2.scaled_by(3.)
        assert sf6.get_scaling() == 6.

    def test_class_discovery(self):
        # This does not test much, since we always discover the scaling as 1.
        # But most of NumPy (when writing) does not understand DType classes
        dt, _ = discover_array_params([1., 2., 3.], dtype=SF)
        assert dt == SF(1.)

    @pytest.mark.parametrize("scaling", [1., -1., 2.])
    def test_scaled_float_from_floats(self, scaling):
        a = np.array([1., 2., 3.], dtype=SF(scaling))

        assert a.dtype.get_scaling() == scaling
        assert_array_equal(scaling * a.view(np.float64), [1., 2., 3.])

    def test_repr(self):
        # Check the repr, mainly to cover the code paths:
        assert repr(SF(scaling=1.)) == "_ScaledFloatTestDType(scaling=1.0)"

    def test_dtype_name(self):
        assert SF(1.).name == "_ScaledFloatTestDType64"

    def test_sfloat_structured_dtype_printing(self):
        dt = np.dtype([("id", int), ("value", SF(0.5))])
        # repr of structured dtypes need special handling because the
        # implementation bypasses the object repr
        assert "('value', '_ScaledFloatTestDType64')" in repr(dt)

    @pytest.mark.parametrize("scaling", [1., -1., 2.])
    def test_sfloat_from_float(self, scaling):
        a = np.array([1., 2., 3.]).astype(dtype=SF(scaling))

        assert a.dtype.get_scaling() == scaling
        assert_array_equal(scaling * a.view(np.float64), [1., 2., 3.])

    @pytest.mark.parametrize("aligned", [True, False])
    @pytest.mark.parametrize("scaling", [1., -1., 2.])
    def test_sfloat_getitem(self, aligned, scaling):
        a = self._get_array(1., aligned)
        assert a.tolist() == [1., 2., 3.]

    @pytest.mark.parametrize("aligned", [True, False])
    def test_sfloat_casts(self, aligned):
        a = self._get_array(1., aligned)

        assert np.can_cast(a, SF(-1.), casting="equiv")
        assert not np.can_cast(a, SF(-1.), casting="no")
        na = a.astype(SF(-1.))
        assert_array_equal(-1 * na.view(np.float64), a.view(np.float64))

        assert np.can_cast(a, SF(2.), casting="same_kind")
        assert not np.can_cast(a, SF(2.), casting="safe")
        a2 = a.astype(SF(2.))
        assert_array_equal(2 * a2.view(np.float64), a.view(np.float64))

    @pytest.mark.parametrize("aligned", [True, False])
    def test_sfloat_cast_internal_errors(self, aligned):
        a = self._get_array(2e300, aligned)

        with pytest.raises(TypeError,
                match="error raised inside the core-loop: non-finite factor!"):
            a.astype(SF(2e-300))

    def test_sfloat_promotion(self):
        assert np.result_type(SF(2.), SF(3.)) == SF(3.)
        assert np.result_type(SF(3.), SF(2.)) == SF(3.)
        # Float64 -> SF(1.) and then promotes normally, so both of this work:
        assert np.result_type(SF(3.), np.float64) == SF(3.)
        assert np.result_type(np.float64, SF(0.5)) == SF(1.)

        # Test an undefined promotion:
        with pytest.raises(TypeError):
            np.result_type(SF(1.), np.int64)

    def test_basic_multiply(self):
        a = self._get_array(2.)
        b = self._get_array(4.)

        res = a * b
        # multiplies dtype scaling and content separately:
        assert res.dtype.get_scaling() == 8.
        expected_view = a.view(np.float64) * b.view(np.float64)
        assert_array_equal(res.view(np.float64), expected_view)

    def test_possible_and_impossible_reduce(self):
        # For reductions to work, the first and last operand must have the
        # same dtype.  For this parametric DType that is not necessarily true.
        a = self._get_array(2.)
        # Addition reduction works (as of writing requires to pass initial
        # because setting a scaled-float from the default `0` fails).
        res = np.add.reduce(a, initial=0.)
        assert res == a.astype(np.float64).sum()

        # But each multiplication changes the factor, so a reduction is not
        # possible (the relaxed version of the old refusal to handle any
        # flexible dtype).
        with pytest.raises(TypeError,
                match="the resolved dtypes are not compatible"):
            np.multiply.reduce(a)

    def test_basic_ufunc_at(self):
        float_a = np.array([1., 2., 3.])
        b = self._get_array(2.)

        float_b = b.view(np.float64).copy()
        np.multiply.at(float_b, [1, 1, 1], float_a)
        np.multiply.at(b, [1, 1, 1], float_a)

        assert_array_equal(b.view(np.float64), float_b)

    def test_basic_multiply_promotion(self):
        float_a = np.array([1., 2., 3.])
        b = self._get_array(2.)

        res1 = float_a * b
        res2 = b * float_a

        # one factor is one, so we get the factor of b:
        assert res1.dtype == res2.dtype == b.dtype
        expected_view = float_a * b.view(np.float64)
        assert_array_equal(res1.view(np.float64), expected_view)
        assert_array_equal(res2.view(np.float64), expected_view)

        # Check that promotion works when `out` is used:
        np.multiply(b, float_a, out=res2)
        with pytest.raises(TypeError):
            # The promoter accepts this (maybe it should not), but the SFloat
            # result cannot be cast to integer:
            np.multiply(b, float_a, out=np.arange(3))

    def test_basic_addition(self):
        a = self._get_array(2.)
        b = self._get_array(4.)

        res = a + b
        # addition uses the type promotion rules for the result:
        assert res.dtype == np.result_type(a.dtype, b.dtype)
        expected_view = (a.astype(res.dtype).view(np.float64) +
                         b.astype(res.dtype).view(np.float64))
        assert_array_equal(res.view(np.float64), expected_view)

    def test_addition_cast_safety(self):
        """The addition method is special for the scaled float, because it
        includes the "cast" between different factors, thus cast-safety
        is influenced by the implementation.
        """
        a = self._get_array(2.)
        b = self._get_array(-2.)
        c = self._get_array(3.)

        # sign change is "equiv":
        np.add(a, b, casting="equiv")
        with pytest.raises(TypeError):
            np.add(a, b, casting="no")

        # Different factor is "same_kind" (default) so check that "safe" fails
        with pytest.raises(TypeError):
            np.add(a, c, casting="safe")

        # Check that casting the output fails also (done by the ufunc here)
        with pytest.raises(TypeError):
            np.add(a, a, out=c, casting="safe")

    @pytest.mark.parametrize("ufunc",
            [np.logical_and, np.logical_or, np.logical_xor])
    def test_logical_ufuncs_casts_to_bool(self, ufunc):
        a = self._get_array(2.)
        a[0] = 0.  # make sure first element is considered False.

        float_equiv = a.astype(float)
        expected = ufunc(float_equiv, float_equiv)
        res = ufunc(a, a)
        assert_array_equal(res, expected)

        # also check that the same works for reductions:
        expected = ufunc.reduce(float_equiv)
        res = ufunc.reduce(a)
        assert_array_equal(res, expected)

        # The output casting does not match the bool, bool -> bool loop:
        with pytest.raises(TypeError):
            ufunc(a, a, out=np.empty(a.shape, dtype=int), casting="equiv")

    def test_wrapped_and_wrapped_reductions(self):
        a = self._get_array(2.)
        float_equiv = a.astype(float)

        expected = np.hypot(float_equiv, float_equiv)
        res = np.hypot(a, a)
        assert res.dtype == a.dtype
        res_float = res.view(np.float64) * 2
        assert_array_equal(res_float, expected)

        # Also check reduction (keepdims, due to incorrect getitem)
        res = np.hypot.reduce(a, keepdims=True)
        assert res.dtype == a.dtype
        expected = np.hypot.reduce(float_equiv, keepdims=True)
        assert res.view(np.float64) * 2 == expected

    def test_astype_class(self):
        # Very simple test that we accept `.astype()` also on the class.
        # ScaledFloat always returns the default descriptor, but it does
        # check the relevant code paths.
        arr = np.array([1., 2., 3.], dtype=object)

        res = arr.astype(SF)  # passing the class class
        expected = arr.astype(SF(1.))  # above will have discovered 1. scaling
        assert_array_equal(res.view(np.float64), expected.view(np.float64))

    def test_creation_class(self):
        # passing in a dtype class should return
        # the default descriptor
        arr1 = np.array([1., 2., 3.], dtype=SF)
        assert arr1.dtype == SF(1.)
        arr2 = np.array([1., 2., 3.], dtype=SF(1.))
        assert_array_equal(arr1.view(np.float64), arr2.view(np.float64))
        assert arr1.dtype == arr2.dtype

        assert np.empty(3, dtype=SF).dtype == SF(1.)
        assert np.empty_like(arr1, dtype=SF).dtype == SF(1.)
        assert np.zeros(3, dtype=SF).dtype == SF(1.)
        assert np.zeros_like(arr1, dtype=SF).dtype == SF(1.)

    def test_np_save_load(self):
        # this monkeypatch is needed because pickle
        # uses the repr of a type to reconstruct it
        np._ScaledFloatTestDType = SF

        arr = np.array([1.0, 2.0, 3.0], dtype=SF(1.0))

        # adapted from RoundtripTest.roundtrip in np.save tests
        with NamedTemporaryFile("wb", delete=False, suffix=".npz") as f:
            with pytest.warns(UserWarning) as record:
                np.savez(f.name, arr)

        assert len(record) == 1

        with np.load(f.name, allow_pickle=True) as data:
            larr = data["arr_0"]
        assert_array_equal(arr.view(np.float64), larr.view(np.float64))
        assert larr.dtype == arr.dtype == SF(1.0)

        del np._ScaledFloatTestDType

    def test_flatiter(self):
        arr = np.array([1.0, 2.0, 3.0], dtype=SF(1.0))

        for i, val in enumerate(arr.flat):
            assert arr[i] == val

    @pytest.mark.parametrize(
        "index", [
            [1, 2], ..., slice(None, 2, None),
            np.array([True, True, False]), np.array([0, 1])
        ], ids=["int_list", "ellipsis", "slice", "bool_array", "int_array"])
    def test_flatiter_index(self, index):
        arr = np.array([1.0, 2.0, 3.0], dtype=SF(1.0))
        np.testing.assert_array_equal(
            arr[index].view(np.float64), arr.flat[index].view(np.float64))

        arr2 = arr.copy()
        arr[index] = 5.0
        arr2.flat[index] = 5.0
        np.testing.assert_array_equal(
            arr.view(np.float64), arr2.view(np.float64))

def test_type_pickle():
    # can't actually unpickle, but we can pickle (if in namespace)
    import pickle

    np._ScaledFloatTestDType = SF

    s = pickle.dumps(SF)
    res = pickle.loads(s)
    assert res is SF

    del np._ScaledFloatTestDType


def test_is_numeric():
    assert SF._is_numeric
