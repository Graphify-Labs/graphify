import concurrent.futures
import copy
import itertools
import os
import string
import pickle
import sys
import tempfile

import numpy as np
import pytest

from numpy.dtypes import StringDType
from numpy._core.tests._natype import pd_NA
from numpy.testing import assert_array_equal, IS_WASM, IS_PYPY


@pytest.fixture
def string_list():
    return ["abc", "def", "ghi" * 10, "A¢☃€ 😊" * 100, "Abc" * 1000, "DEF"]


@pytest.fixture
def random_string_list():
    chars = list(string.ascii_letters + string.digits)
    chars = np.array(chars, dtype="U1")
    ret = np.random.choice(chars, size=100 * 10, replace=True)
    return ret.view("U100")


@pytest.fixture(params=[True, False])
def coerce(request):
    return request.param


@pytest.fixture(
    params=["unset", None, pd_NA, np.nan, float("nan"), "__nan__"],
    ids=["unset", "None", "pandas.NA", "np.nan", "float('nan')", "string nan"],
)
def na_object(request):
    return request.param


def get_dtype(na_object, coerce=True):
    # explicit is check for pd_NA because != with pd_NA returns pd_NA
    if na_object is pd_NA or na_object != "unset":
        return StringDType(na_object=na_object, coerce=coerce)
    else:
        return StringDType(coerce=coerce)


@pytest.fixture()
def dtype(na_object, coerce):
    return get_dtype(na_object, coerce)


# second copy for cast tests to do a cartesian product over dtypes
@pytest.fixture(params=[True, False])
def coerce2(request):
    return request.param


@pytest.fixture(
    params=["unset", None, pd_NA, np.nan, float("nan"), "__nan__"],
    ids=["unset", "None", "pandas.NA", "np.nan", "float('nan')", "string nan"],
)
def na_object2(request):
    return request.param


@pytest.fixture()
def dtype2(na_object2, coerce2):
    # explicit is check for pd_NA because != with pd_NA returns pd_NA
    if na_object2 is pd_NA or na_object2 != "unset":
        return StringDType(na_object=na_object2, coerce=coerce2)
    else:
        return StringDType(coerce=coerce2)


def test_dtype_creation():
    hashes = set()
    dt = StringDType()
    assert not hasattr(dt, "na_object") and dt.coerce is True
    hashes.add(hash(dt))

    dt = StringDType(na_object=None)
    assert dt.na_object is None and dt.coerce is True
    hashes.add(hash(dt))

    dt = StringDType(coerce=False)
    assert not hasattr(dt, "na_object") and dt.coerce is False
    hashes.add(hash(dt))

    dt = StringDType(na_object=None, coerce=False)
    assert dt.na_object is None and dt.coerce is False
    hashes.add(hash(dt))

    assert len(hashes) == 4

    dt = np.dtype("T")
    assert dt == StringDType()
    assert dt.kind == "T"
    assert dt.char == "T"

    hashes.add(hash(dt))
    assert len(hashes) == 4


def test_dtype_equality(dtype):
    assert dtype == dtype
    for ch in "SU":
        assert dtype != np.dtype(ch)
        assert dtype != np.dtype(f"{ch}8")


def test_dtype_repr(dtype):
    if not hasattr(dtype, "na_object") and dtype.coerce:
        assert repr(dtype) == "StringDType()"
    elif dtype.coerce:
        assert repr(dtype) == f"StringDType(na_object={dtype.na_object!r})"
    elif not hasattr(dtype, "na_object"):
        assert repr(dtype) == "StringDType(coerce=False)"
    else:
        assert (
            repr(dtype)
            == f"StringDType(na_object={dtype.na_object!r}, coerce=False)"
        )


def test_create_with_na(dtype):
    if not hasattr(dtype, "na_object"):
        pytest.skip("does not have an na object")
    na_val = dtype.na_object
    string_list = ["hello", na_val, "world"]
    arr = np.array(string_list, dtype=dtype)
    assert str(arr) == "[" + " ".join([repr(s) for s in string_list]) + "]"
    assert arr[1] is dtype.na_object


@pytest.mark.parametrize("i", list(range(5)))
def test_set_replace_na(i):
    # Test strings of various lengths can be set to NaN and then replaced.
    s_empty = ""
    s_short = "0123456789"
    s_medium = "abcdefghijklmnopqrstuvwxyz"
    s_long = "-=+" * 100
    strings = [s_medium, s_empty, s_short, s_medium, s_long]
    a = np.array(strings, StringDType(na_object=np.nan))
    for s in [a[i], s_medium+s_short, s_short, s_empty, s_long]:
        a[i] = np.nan
        assert np.isnan(a[i])
        a[i] = s
        assert a[i] == s
        assert_array_equal(a, strings[:i] + [s] + strings[i+1:])


def test_null_roundtripping():
    data = ["hello\0world", "ABC\0DEF\0\0"]
    arr = np.array(data, dtype="T")
    assert data[0] == arr[0]
    assert data[1] == arr[1]


def test_string_too_large_error():
    arr = np.array(["a", "b", "c"], dtype=StringDType())
    with pytest.raises(MemoryError):
        arr * (2**63 - 2)


@pytest.mark.parametrize(
    "data",
    [
        ["abc", "def", "ghi"],
        ["🤣", "📵", "😰"],
        ["🚜", "🙃", "😾"],
        ["😹", "🚠", "🚌"],
    ],
)
def test_array_creation_utf8(dtype, data):
    arr = np.array(data, dtype=dtype)
    assert str(arr) == "[" + " ".join(["'" + str(d) + "'" for d in data]) + "]"
    assert arr.dtype == dtype


@pytest.mark.parametrize(
    "data",
    [
        [1, 2, 3],
        [b"abc", b"def", b"ghi"],
        [object, object, object],
    ],
)
def test_scalars_string_conversion(data, dtype):
    try:
        str_vals = [str(d.decode('utf-8')) for d in data]
    except AttributeError:
        str_vals = [str(d) for d in data]
    if dtype.coerce:
        assert_array_equal(
            np.array(data, dtype=dtype),
            np.array(str_vals, dtype=dtype),
        )
    else:
        with pytest.raises(ValueError):
            np.array(data, dtype=dtype)


@pytest.mark.parametrize(
    ("strings"),
    [
        ["this", "is", "an", "array"],
        ["€", "", "😊"],
        ["A¢☃€ 😊", " A☃€¢😊", "☃€😊 A¢", "😊☃A¢ €"],
    ],
)
def test_self_casts(dtype, dtype2, strings):
    if hasattr(dtype, "na_object"):
        strings = strings + [dtype.na_object]
    elif hasattr(dtype2, "na_object"):
        strings = strings + [""]
    arr = np.array(strings, dtype=dtype)
    newarr = arr.astype(dtype2)

    if hasattr(dtype, "na_object") and not hasattr(dtype2, "na_object"):
        assert newarr[-1] == str(dtype.na_object)
        with pytest.raises(TypeError):
            arr.astype(dtype2, casting="safe")
    elif hasattr(dtype, "na_object") and hasattr(dtype2, "na_object"):
        assert newarr[-1] is dtype2.na_object
        arr.astype(dtype2, casting="safe")
    elif hasattr(dtype2, "na_object"):
        assert newarr[-1] == ""
        arr.astype(dtype2, casting="safe")
    else:
        arr.astype(dtype2, casting="safe")

    if hasattr(dtype, "na_object") and hasattr(dtype2, "na_object"):
        na1 = dtype.na_object
        na2 = dtype2.na_object
        if (na1 is not na2 and
             # check for pd_NA first because bool(pd_NA) is an error
             ((na1 is pd_NA or na2 is pd_NA) or
              # the second check is a NaN check, spelled this way
              # to avoid errors from math.isnan and np.isnan
              (na1 != na2 and not (na1 != na1 and na2 != na2)))):
            with pytest.raises(TypeError):
                arr[:-1] == newarr[:-1]
            return
    assert_array_equal(arr[:-1], newarr[:-1])


@pytest.mark.parametrize(
    ("strings"),
    [
        ["this", "is", "an", "array"],
        ["€", "", "😊"],
        ["A¢☃€ 😊", " A☃€¢😊", "☃€😊 A¢", "😊☃A¢ €"],
    ],
)
class TestStringLikeCasts:
    def test_unicode_casts(self, dtype, strings):
        arr = np.array(strings, dtype=np.str_).astype(dtype)
        expected = np.array(strings, dtype=dtype)
        assert_array_equal(arr, expected)

        arr_as_U8 = expected.astype("U8")
        assert_array_equal(arr_as_U8, np.array(strings, dtype="U8"))
        assert_array_equal(arr_as_U8.astype(dtype), arr)
        arr_as_U3 = expected.astype("U3")
        assert_array_equal(arr_as_U3, np.array(strings, dtype="U3"))
        assert_array_equal(
            arr_as_U3.astype(dtype),
            np.array([s[:3] for s in strings], dtype=dtype),
        )

    def test_void_casts(self, dtype, strings):
        sarr = np.array(strings, dtype=dtype)
        utf8_bytes = [s.encode("utf-8") for s in strings]
        void_dtype = f"V{max([len(s) for s in utf8_bytes])}"
        varr = np.array(utf8_bytes, dtype=void_dtype)
        assert_array_equal(varr, sarr.astype(void_dtype))
        assert_array_equal(varr.astype(dtype), sarr)

    def test_bytes_casts(self, dtype, strings):
        sarr = np.array(strings, dtype=dtype)
        try:
            utf8_bytes = [s.encode("ascii") for s in strings]
            bytes_dtype = f"S{max([len(s) for s in utf8_bytes])}"
            barr = np.array(utf8_bytes, dtype=bytes_dtype)
            assert_array_equal(barr, sarr.astype(bytes_dtype))
            assert_array_equal(barr.astype(dtype), sarr)
            if dtype.coerce:
                barr = np.array(utf8_bytes, dtype=dtype)
                assert_array_equal(barr, sarr)
                barr = np.array(utf8_bytes, dtype="O")
                assert_array_equal(barr.astype(dtype), sarr)
            else:
                with pytest.raises(ValueError):
                    np.array(utf8_bytes, dtype=dtype)
        except UnicodeEncodeError:
            with pytest.raises(UnicodeEncodeError):
                sarr.astype("S20")


def test_additional_unicode_cast(random_string_list, dtype):
    arr = np.array(random_string_list, dtype=dtype)
    # test that this short-circuits correctly
    assert_array_equal(arr, arr.astype(arr.dtype))
    # tests the casts via the comparison promoter
    assert_array_equal(arr, arr.astype(random_string_list.dtype))


def test_insert_scalar(dtype, string_list):
    """Test that inserting a scalar works."""
    arr = np.array(string_list, dtype=dtype)
    scalar_instance = "what"
    arr[1] = scalar_instance
    assert_array_equal(
        arr,
        np.array(string_list[:1] + ["what"] + string_list[2:], dtype=dtype),
    )


comparison_operators = [
    np.equal,
    np.not_equal,
    np.greater,
    np.greater_equal,
    np.less,
    np.less_equal,
]


@pytest.mark.parametrize("op", comparison_operators)
@pytest.mark.parametrize("o_dtype", [np.str_, object, StringDType()])
def test_comparisons(string_list, dtype, op, o_dtype):
    sarr = np.array(string_list, dtype=dtype)
    oarr = np.array(string_list, dtype=o_dtype)

    # test that comparison operators work
    res = op(sarr, sarr)
    ores = op(oarr, oarr)
    # test that promotion works as well
    orres = op(sarr, oarr)
    olres = op(oarr, sarr)

    assert_array_equal(res, ores)
    assert_array_equal(res, orres)
    assert_array_equal(res, olres)

    # test we get the correct answer for unequal length strings
    sarr2 = np.array([s + "2" for s in string_list], dtype=dtype)
    oarr2 = np.array([s + "2" for s in string_list], dtype=o_dtype)

    res = op(sarr, sarr2)
    ores = op(oarr, oarr2)
    olres = op(oarr, sarr2)
    orres = op(sarr, oarr2)

    assert_array_equal(res, ores)
    assert_array_equal(res, olres)
    assert_array_equal(res, orres)

    res = op(sarr2, sarr)
    ores = op(oarr2, oarr)
    olres = op(oarr2, sarr)
    orres = op(sarr2, oarr)

    assert_array_equal(res, ores)
    assert_array_equal(res, olres)
    assert_array_equal(res, orres)


def test_isnan(dtype, string_list):
    if not hasattr(dtype, "na_object"):
        pytest.skip("no na support")
    sarr = np.array(string_list + [dtype.na_object], dtype=dtype)
    is_nan = isinstance(dtype.na_object, float) and np.isnan(dtype.na_object)
    bool_errors = 0
    try:
        bool(dtype.na_object)
    except TypeError:
        bool_errors = 1
    if is_nan or bool_errors:
        # isnan is only true when na_object is a NaN
        assert_array_equal(
            np.isnan(sarr),
            np.array([0] * len(string_list) + [1], dtype=np.bool),
        )
    else:
        assert not np.any(np.isnan(sarr))


def test_pickle(dtype, string_list):
    arr = np.array(string_list, dtype=dtype)

    with tempfile.NamedTemporaryFile("wb", delete=False) as f:
        pickle.dump([arr, dtype], f)

    with open(f.name, "rb") as f:
        res = pickle.load(f)

    assert_array_equal(res[0], arr)
    assert res[1] == dtype

    os.remove(f.name)


def test_stdlib_copy(dtype, string_list):
    arr = np.array(string_list, dtype=dtype)

    assert_array_equal(copy.copy(arr), arr)
    assert_array_equal(copy.deepcopy(arr), arr)


@pytest.mark.parametrize(
    "strings",
    [
        ["left", "right", "leftovers", "righty", "up", "down"],
        [
            "left" * 10,
            "right" * 10,
            "leftovers" * 10,
            "righty" * 10,
            "up" * 10,
        ],
        ["🤣🤣", "🤣", "📵", "😰"],
        ["🚜", "🙃", "😾"],
        ["😹", "🚠", "🚌"],
        ["A¢☃€ 😊", " A☃€¢😊", "☃€😊 A¢", "😊☃A¢ €"],
    ],
)
def test_sort(dtype, strings):
    """Test that sorting matches python's internal sorting."""

    def test_sort(strings, arr_sorted):
        arr = np.array(strings, dtype=dtype)
        na_object = getattr(arr.dtype, "na_object", "")
        if na_object is None and None in strings:
            with pytest.raises(
                ValueError,
                match="Cannot compare null that is not a nan-like value",
            ):
                np.argsort(arr)
            argsorted = None
        elif na_object is pd_NA or na_object != '':
            argsorted = None
        else:
            argsorted = np.argsort(arr)
        np.random.default_rng().shuffle(arr)
        if na_object is None and None in strings:
            with pytest.raises(
                ValueError,
                match="Cannot compare null that is not a nan-like value",
            ):
                arr.sort()
        else:
            arr.sort()
            assert np.array_equal(arr, arr_sorted, equal_nan=True)
        if argsorted is not None:
            assert np.array_equal(argsorted, np.argsort(strings))


    # make a copy so we don't mutate the lists in the fixture
    strings = strings.copy()
    arr_sorted = np.array(sorted(strings), dtype=dtype)
    test_sort(strings, arr_sorted)

    if not hasattr(dtype, "na_object"):
        return

    # make sure NAs get sorted to the end of the array and string NAs get
    # sorted like normal strings
    strings.insert(0, dtype.na_object)
    strings.insert(2, dtype.na_object)
    # can't use append because doing that with NA converts
    # the result to object dtype
    if not isinstance(dtype.na_object, str):
        arr_sorted = np.array(
            arr_sorted.tolist() + [dtype.na_object, dtype.na_object],
            dtype=dtype,
        )
    else:
        arr_sorted = np.array(sorted(strings), dtype=dtype)

    test_sort(strings, arr_sorted)


@pytest.mark.parametrize(
    "strings",
    [
        ["A¢☃€ 😊", " A☃€¢😊", "☃€😊 A¢", "😊☃A¢ €"],
        ["A¢☃€ 😊", "", " ", " "],
        ["", "a", "😸", "ááðfáíóåéë"],
    ],
)
def test_nonzero(strings, na_object):
    dtype = get_dtype(na_object)
    arr = np.array(strings, dtype=dtype)
    is_nonzero = np.array(
        [i for i, item in enumerate(strings) if len(item) != 0])
    assert_array_equal(arr.nonzero()[0], is_nonzero)

    if na_object is not pd_NA and na_object == 'unset':
        return

    strings_with_na = np.array(strings + [na_object], dtype=dtype)
    is_nan = np.isnan(np.array([dtype.na_object], dtype=dtype))[0]

    if is_nan:
        assert strings_with_na.nonzero()[0][-1] == 4
    else:
        assert strings_with_na.nonzero()[0][-1] == 3

    # check that the casting to bool and nonzero give consistent results
    assert_array_equal(strings_with_na[strings_with_na.nonzero()],
                       strings_with_na[strings_with_na.astype(bool)])


def test_where(string_list, na_object):
    dtype = get_dtype(na_object)
    a = np.array(string_list, dtype=dtype)
    b = a[::-1]
    res = np.where([True, False, True, False, True, False], a, b)
    assert_array_equal(res, [a[0], b[1], a[2], b[3], a[4], b[5]])


def test_fancy_indexing(string_list):
    sarr = np.array(string_list, dtype="T")
    assert_array_equal(sarr, sarr[np.arange(sarr.shape[0])])

    inds = [
        [True, True],
        [0, 1],
        ...,
        np.array([0, 1], dtype='uint8'),
    ]

    lops = [
        ['a'*25, 'b'*25],
        ['', ''],
        ['hello', 'world'],
        ['hello', 'world'*25],
    ]

    # see gh-27003 and gh-27053
    for ind in inds:
        for lop in lops:
            a = np.array(lop, dtype="T")
            assert_array_equal(a[ind], a)
            rop = ['d'*25, 'e'*25]
            for b in [rop, np.array(rop, dtype="T")]:
                a[ind] = b
                assert_array_equal(a, b)
                assert a[0] == 'd'*25


def test_creation_functions():
    assert_array_equal(np.zeros(3, dtype="T"), ["", "", ""])
    assert_array_equal(np.empty(3, dtype="T"), ["", "", ""])

    assert np.zeros(3, dtype="T")[0] == ""
    assert np.empty(3, dtype="T")[0] == ""


def test_concatenate(string_list):
    sarr = np.array(string_list, dtype="T")
    sarr_cat = np.array(string_list + string_list, dtype="T")

    assert_array_equal(np.concatenate([sarr], axis=0), sarr)


def test_resize_method(string_list):
    sarr = np.array(string_list, dtype="T")
    if IS_PYPY:
        sarr.resize(len(string_list)+3, refcheck=False)
    else:
        sarr.resize(len(string_list)+3)
    assert_array_equal(sarr, np.array(string_list + ['']*3,  dtype="T"))


def test_create_with_copy_none(string_list):
    arr = np.array(string_list, dtype=StringDType())
    # create another stringdtype array with an arena that has a different
    # in-memory layout than the first array
    arr_rev = np.array(string_list[::-1], dtype=StringDType())

    # this should create a copy and the resulting array
    # shouldn't share an allocator or arena with arr_rev, despite
    # explicitly passing arr_rev.dtype
    arr_copy = np.array(arr, copy=None, dtype=arr_rev.dtype)
    np.testing.assert_array_equal(arr, arr_copy)
    assert arr_copy.base is None

    with pytest.raises(ValueError, match="Unable to avoid copy"):
        np.array(arr, copy=False, dtype=arr_rev.dtype)

    # because we're using arr's dtype instance, the view is safe
    arr_view = np.array(arr, copy=None, dtype=arr.dtype)
    np.testing.assert_array_equal(arr, arr)
    np.testing.assert_array_equal(arr_view[::-1], arr_rev)
    assert arr_view is arr


def test_astype_copy_false():
    orig_dt = StringDType()
    arr = np.array(["hello", "world"], dtype=StringDType())
    assert not arr.astype(StringDType(coerce=False), copy=False).dtype.coerce

    assert arr.astype(orig_dt, copy=False).dtype is orig_dt

@pytest.mark.parametrize(
    "strings",
    [
        ["left", "right", "leftovers", "righty", "up", "down"],
        ["🤣🤣", "🤣", "📵", "😰"],
        ["🚜", "🙃", "😾"],
        ["😹", "🚠", "🚌"],
        ["A¢☃€ 😊", " A☃€¢😊", "☃€😊 A¢", "😊☃A¢ €"],
    ],
)
def test_argmax(strings):
    """Test that argmax/argmin matches what python calculates."""
    arr = np.array(strings, dtype="T")
    assert np.argmax(arr) == strings.index(max(strings))
    assert np.argmin(arr) == strings.index(min(strings))


@pytest.mark.parametrize(
    "arrfunc,expected",
    [
        [np.sort, None],
        [np.nonzero, (np.array([], dtype=np.int_),)],
        [np.argmax, 0],
        [np.argmin, 0],
    ],
)
def test_arrfuncs_zeros(arrfunc, expected):
    arr = np.zeros(10, dtype="T")
    result = arrfunc(arr)
    if expected is None:
        expected = arr
    assert_array_equal(result, expected, strict=True)


@pytest.mark.parametrize(
    ("strings", "cast_answer", "any_answer", "all_answer"),
    [
        [["hello", "world"], [True, True], True, True],
        [["", ""], [False, False], False, False],
        [["hello", ""], [True, False], True, False],
        [["", "world"], [False, True], True, False],
    ],
)
def test_cast_to_bool(strings, cast_answer, any_answer, all_answer):
    sarr = np.array(strings, dtype="T")
    assert_array_equal(sarr.astype("bool"), cast_answer)

    assert np.any(sarr) == any_answer
    assert np.all(sarr) == all_answer


@pytest.mark.parametrize(
    ("strings", "cast_answer"),
    [
        [[True, True], ["True", "True"]],
        [[False, False], ["False", "False"]],
        [[True, False], ["True", "False"]],
        [[False, True], ["False", "True"]],
    ],
)
def test_cast_from_bool(strings, cast_answer):
    barr = np.array(strings, dtype=bool)
    assert_array_equal(barr.astype("T"), np.array(cast_answer, dtype="T"))


@pytest.mark.parametrize("bitsize", [8, 16, 32, 64])
@pytest.mark.parametrize("signed", [True, False])
def test_sized_integer_casts(bitsize, signed):
    idtype = f"int{bitsize}"
    if signed:
        inp = [-(2**p - 1) for p in reversed(range(bitsize - 1))]
        inp += [2**p - 1 for p in range(1, bitsize - 1)]
    else:
        idtype = "u" + idtype
        inp = [2**p - 1 for p in range(bitsize)]
    ainp = np.array(inp, dtype=idtype)
    assert_array_equal(ainp, ainp.astype("T").astype(idtype))

    # safe casting works
    ainp.astype("T", casting="safe")

    with pytest.raises(TypeError):
        ainp.astype("T").astype(idtype, casting="safe")

    oob = [str(2**bitsize), str(-(2**bitsize))]
    with pytest.raises(OverflowError):
        np.array(oob, dtype="T").astype(idtype)

    with pytest.raises(ValueError):
        np.array(["1", np.nan, "3"],
                 dtype=StringDType(na_object=np.nan)).astype(idtype)


@pytest.mark.parametrize("typename", ["byte", "short", "int", "longlong"])
@pytest.mark.parametrize("signed", ["", "u"])
def test_unsized_integer_casts(typename, signed):
    idtype = f"{signed}{typename}"

    inp = [1, 2, 3, 4]
    ainp = np.array(inp, dtype=idtype)
    assert_array_equal(ainp, ainp.astype("T").astype(idtype))


@pytest.mark.parametrize(
    "typename",
    [
        pytest.param(
            "longdouble",
            marks=pytest.mark.xfail(
                np.dtypes.LongDoubleDType() != np.dtypes.Float64DType(),
                reason="numpy lacks an ld2a implementation",
                strict=True,
            ),
        ),
        "float64",
        "float32",
        "float16",
    ],
)
def test_float_casts(typename):
    inp = [1.1, 2.8, -3.2, 2.7e4]
    ainp = np.array(inp, dtype=typename)
    assert_array_equal(ainp, ainp.astype("T").astype(typename))

    inp = [0.1]
    sres = np.array(inp, dtype=typename).astype("T")
    res = sres.astype(typename)
    assert_array_equal(np.array(inp, dtype=typename), res)
    assert sres[0] == "0.1"

    if typename == "longdouble":
        # let's not worry about platform-dependent rounding of longdouble
        return

    fi = np.finfo(typename)

    inp = [1e-324, fi.smallest_subnormal, -1e-324, -fi.smallest_subnormal]
    eres = [0, fi.smallest_subnormal, -0, -fi.smallest_subnormal]
    res = np.array(inp, dtype=typename).astype("T").astype(typename)
    assert_array_equal(eres, res)

    inp = [2e308, fi.max, -2e308, fi.min]
    eres = [np.inf, fi.max, -np.inf, fi.min]
    res = np.array(inp, dtype=typename).astype("T").astype(typename)
    assert_array_equal(eres, res)


@pytest.mark.parametrize(
    "typename",
    [
        "csingle",
        "cdouble",
        pytest.param(
            "clongdouble",
            marks=pytest.mark.xfail(
                np.dtypes.CLongDoubleDType() != np.dtypes.Complex128DType(),
                reason="numpy lacks an ld2a implementation",
                strict=True,
            ),
        ),
    ],
)
def test_cfloat_casts(typename):
    inp = [1.1 + 1.1j, 2.8 + 2.8j, -3.2 - 3.2j, 2.7e4 + 2.7e4j]
    ainp = np.array(inp, dtype=typename)
    assert_array_equal(ainp, ainp.astype("T").astype(typename))

    inp = [0.1 + 0.1j]
    sres = np.array(inp, dtype=typename).astype("T")
    res = sres.astype(typename)
    assert_array_equal(np.array(inp, dtype=typename), res)
    assert sres[0] == "(0.1+0.1j)"


def test_take(string_list):
    sarr = np.array(string_list, dtype="T")
    res = sarr.take(np.arange(len(string_list)))
    assert_array_equal(sarr, res)

    # make sure it also works for out
    out = np.empty(len(string_list), dtype="T")
    out[0] = "hello"
    res = sarr.take(np.arange(len(string_list)), out=out)
    assert res is out
    assert_array_equal(sarr, res)


@pytest.mark.parametrize("use_out", [True, False])
@pytest.mark.parametrize(
    "ufunc_name,func",
    [
        ("min", min),
        ("max", max),
    ],
)
def test_ufuncs_minmax(string_list, ufunc_name, func, use_out):
    """Test that the min/max ufuncs match Python builtin min/max behavior."""
    arr = np.array(string_list, dtype="T")
    uarr = np.array(string_list, dtype=str)
    res = np.array(func(string_list), dtype="T")
    assert_array_equal(getattr(arr, ufunc_name)(), res)

    ufunc = getattr(np, ufunc_name + "imum")

    if use_out:
        res = ufunc(arr, arr, out=arr)
    else:
        res = ufunc(arr, arr)

    assert_array_equal(uarr, res)
    assert_array_equal(getattr(arr, ufunc_name)(), func(string_list))


def test_max_regression():
    arr = np.array(['y', 'y', 'z'], dtype="T")
    assert arr.max() == 'z'


@pytest.mark.parametrize("use_out", [True, False])
@pytest.mark.parametrize(
    "other_strings",
    [
        ["abc", "def" * 500, "ghi" * 16, "🤣" * 100, "📵", "😰"],
        ["🚜", "🙃", "😾", "😹", "🚠", "🚌"],
        ["🥦", "¨", "⨯", "∰ ", "⨌ ", "⎶ "],
    ],
)
def test_ufunc_add(dtype, string_list, other_strings, use_out):
    arr1 = np.array(string_list, dtype=dtype)
    arr2 = np.array(other_strings, dtype=dtype)
    result = np.array([a + b for a, b in zip(arr1, arr2)], dtype=dtype)

    if use_out:
        res = np.add(arr1, arr2, out=arr1)
    else:
        res = np.add(arr1, arr2)

    assert_array_equal(res, result)

    if not hasattr(dtype, "na_object"):
        return

    is_nan = isinstance(dtype.na_object, float) and np.isnan(dtype.na_object)
    is_str = isinstance(dtype.na_object, str)
    bool_errors = 0
    try:
        bool(dtype.na_object)
    except TypeError:
        bool_errors = 1

    arr1 = np.array([dtype.na_object] + string_list, dtype=dtype)
    arr2 = np.array(other_strings + [dtype.na_object], dtype=dtype)

    if is_nan or bool_errors or is_str:
        res = np.add(arr1, arr2)
        assert_array_equal(res[1:-1], arr1[1:-1] + arr2[1:-1])
        if not is_str:
            assert res[0] is dtype.na_object and res[-1] is dtype.na_object
        else:
            assert res[0] == dtype.na_object + arr2[0]
            assert res[-1] == arr1[-1] + dtype.na_object
    else:
        with pytest.raises(ValueError):
            np.add(arr1, arr2)


def test_ufunc_add_reduce(dtype):
    values = ["a", "this is a long string", "c"]
    arr = np.array(values, dtype=dtype)
    out = np.empty((), dtype=dtype)

    expected = np.array("".join(values), dtype=dtype)
    assert_array_equal(np.add.reduce(arr), expected)

    np.add.reduce(arr, out=out)
    assert_array_equal(out, expected)


def test_add_promoter(string_list):
    arr = np.array(string_list, dtype=StringDType())
    lresult = np.array(["hello" + s for s in string_list], dtype=StringDType())
    rresult = np.array([s + "hello" for s in string_list], dtype=StringDType())

    for op in ["hello", np.str_("hello"), np.array(["hello"])]:
        assert_array_equal(op + arr, lresult)
        assert_array_equal(arr + op, rresult)

    # The promoter should be able to handle things if users pass `dtype=`
    res = np.add("hello", string_list, dtype=StringDType)
    assert res.dtype == StringDType()

    # The promoter should not kick in if users override the input,
    # which means arr is cast, this fails because of the unknown length.
    with pytest.raises(TypeError, match="cannot cast dtype"):
        np.add(arr, "add", signature=("U", "U", None), casting="unsafe")

    # But it must simply reject the following:
    with pytest.raises(TypeError, match=".*did not contain a loop"):
        np.add(arr, "add", signature=(None, "U", None))

    with pytest.raises(TypeError, match=".*did not contain a loop"):
        np.add("a", "b", signature=("U", "U", StringDType))


def test_add_no_legacy_promote_with_signature():
    # Possibly misplaced, but useful to test with string DType.  We check that
    # if there is clearly no loop found, a stray `dtype=` doesn't break things
    # Regression test for the bad error in gh-26735
    # (If legacy promotion is gone, this can be deleted...)
    with pytest.raises(TypeError, match=".*did not contain a loop"):
        np.add("3", 6, dtype=StringDType)


def test_add_promoter_reduce():
    # Exact TypeError could change, but ensure StringDtype doesn't match
    with pytest.raises(TypeError, match="the resolved dtypes are not"):
        np.add.reduce(np.array(["a", "b"], dtype="U"))

    # On the other hand, using `dtype=T` in the *ufunc* should work.
    np.add.reduce(np.array(["a", "b"], dtype="U"), dtype=np.dtypes.StringDType)


def test_multiply_reduce():
    # At the time of writing (NumPy 2.0) this is very limited (and rather
    # ridiculous anyway).  But it works and actually makes some sense...
    # (NumPy does not allow non-scalar initial values)
    repeats = np.array([2, 3, 4])
    val = "school-🚌"
    res = np.multiply.reduce(repeats, initial=val, dtype=np.dtypes.StringDType)
    assert res == val * np.prod(repeats)


def test_multiply_two_string_raises():
    arr = np.array(["hello", "world"], dtype="T")
    with pytest.raises(np._core._exceptions._UFuncNoLoopError):
        np.multiply(arr, arr)


@pytest.mark.parametrize("use_out", [True, False])
@pytest.mark.parametrize("other", [2, [2, 1, 3, 4, 1, 3]])
@pytest.mark.parametrize(
    "other_dtype",
    [
        None,
        "int8",
        "int16",
        "int32",
        "int64",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
        "short",
        "int",
        "intp",
        "long",
        "longlong",
        "ushort",
        "uint",
        "uintp",
        "ulong",
        "ulonglong",
    ],
)
def test_ufunc_multiply(dtype, string_list, other, other_dtype, use_out):
    """Test the two-argument ufuncs match python builtin behavior."""
    arr = np.array(string_list, dtype=dtype)
    if other_dtype is not None:
        other_dtype = np.dtype(other_dtype)
    try:
        len(other)
        result = [s * o for s, o in zip(string_list, other)]
        other = np.array(other)
        if other_dtype is not None:
            other = other.astype(other_dtype)
    except TypeError:
        if other_dtype is not None:
            other = other_dtype.type(other)
        result = [s * other for s in string_list]

    if use_out:
        arr_cache = arr.copy()
        lres = np.multiply(arr, other, out=arr)
        assert_array_equal(lres, result)
        arr[:] = arr_cache
        assert lres is arr
        arr *= other
        assert_array_equal(arr, result)
        arr[:] = arr_cache
        rres = np.multiply(other, arr, out=arr)
        assert rres is arr
        assert_array_equal(rres, result)
    else:
        lres = arr * other
        assert_array_equal(lres, result)
        rres = other * arr
        assert_array_equal(rres, result)

    if not hasattr(dtype, "na_object"):
        return

    is_nan = np.isnan(np.array([dtype.na_object], dtype=dtype))[0]
    is_str = isinstance(dtype.na_object, str)
    bool_errors = 0
    try:
        bool(dtype.na_object)
    except TypeError:
        bool_errors = 1

    arr = np.array(string_list + [dtype.na_object], dtype=dtype)

    try:
        len(other)
        other = np.append(other, 3)
        if other_dtype is not None:
            other = other.astype(other_dtype)
    except TypeError:
        pass

    if is_nan or bool_errors or is_str:
        for res in [arr * other, other * arr]:
            assert_array_equal(res[:-1], result)
            if not is_str:
                assert res[-1] is dtype.na_object
            else:
                try:
                    assert res[-1] == dtype.na_object * other[-1]
                except (IndexError, TypeError):
                    assert res[-1] == dtype.na_object * other
    else:
        with pytest.raises(TypeError):
            arr * other
        with pytest.raises(TypeError):
            other * arr


def test_findlike_promoters():
    r = "Wally"
    l = "Where's Wally?"
    s = np.int32(3)
    e = np.int8(13)
    for dtypes in [("T", "U"), ("U", "T")]:
        for function, answer in [
            (np.strings.index, 8),
            (np.strings.endswith, True),
        ]:
            assert answer == function(
                np.array(l, dtype=dtypes[0]), np.array(r, dtype=dtypes[1]), s, e
            )


def test_strip_promoter():
    arg = ["Hello!!!!", "Hello??!!"]
    strip_char = "!"
    answer = ["Hello", "Hello??"]
    for dtypes in [("T", "U"), ("U", "T")]:
        result = np.strings.strip(
            np.array(arg, dtype=dtypes[0]),
            np.array(strip_char, dtype=dtypes[1])
        )
        assert_array_equal(result, answer)
        assert result.dtype.char == "T"


def test_replace_promoter():
    arg = ["Hello, planet!", "planet, Hello!"]
    old = "planet"
    new = "world"
    answer = ["Hello, world!", "world, Hello!"]
    for dtypes in itertools.product("TU", repeat=3):
        if dtypes == ("U", "U", "U"):
            continue
        answer_arr = np.strings.replace(
            np.array(arg, dtype=dtypes[0]),
            np.array(old, dtype=dtypes[1]),
            np.array(new, dtype=dtypes[2]),
        )
        assert_array_equal(answer_arr, answer)
        assert answer_arr.dtype.char == "T"


def test_center_promoter():
    arg = ["Hello", "planet!"]
    fillchar = "/"
    for dtypes in [("T", "U"), ("U", "T")]:
        answer = np.strings.center(
            np.array(arg, dtype=dtypes[0]), 9, np.array(fillchar, dtype=dtypes[1])
        )
        assert_array_equal(answer, ["//Hello//", "/planet!/"])
        assert answer.dtype.char == "T"


DATETIME_INPUT = [
    np.datetime64("1923-04-14T12:43:12"),
    np.datetime64("1994-06-21T14:43:15"),
    np.datetime64("2001-10-15T04:10:32"),
    np.datetime64("NaT"),
    np.datetime64("1995-11-25T16:02:16"),
    np.datetime64("2005-01-04T03:14:12"),
    np.datetime64("2041-12-03T14:05:03"),
]


TIMEDELTA_INPUT = [
    np.timedelta64(12358, "s"),
    np.timedelta64(23, "s"),
    np.timedelta64(74, "s"),
    np.timedelta64("NaT"),
    np.timedelta64(23, "s"),
    np.timedelta64(73, "s"),
    np.timedelta64(7, "s"),
]


@pytest.mark.parametrize(
    "input_data, input_dtype",
    [
        (DATETIME_INPUT, "M8[s]"),
        (TIMEDELTA_INPUT, "m8[s]")
    ]
)
def test_datetime_timedelta_cast(dtype, input_data, input_dtype):

    a = np.array(input_data, dtype=input_dtype)

    has_na = hasattr(dtype, "na_object")
    is_str = isinstance(getattr(dtype, "na_object", None), str)

    if not has_na or is_str:
        a = np.delete(a, 3)

    sa = a.astype(dtype)
    ra = sa.astype(a.dtype)

    if has_na and not is_str:
        assert sa[3] is dtype.na_object
        assert np.isnat(ra[3])

    assert_array_equal(a, ra)

    if has_na and not is_str:
        # don't worry about comparing how NaT is converted
        sa = np.delete(sa, 3)
        a = np.delete(a, 3)

    if input_dtype.startswith("M"):
        assert_array_equal(sa, a.astype("U"))
    else:
        # The timedelta to unicode cast produces strings
        # that aren't round-trippable and we don't want to
        # reproduce that behavior in stringdtype
        assert_array_equal(sa, a.astype("int64").astype("U"))


def test_nat_casts():
    s = 'nat'
    all_nats = itertools.product(*zip(s.upper(), s.lower()))
    all_nats = list(map(''.join, all_nats))
    NaT_dt = np.datetime64('NaT')
    NaT_td = np.timedelta64('NaT')
    for na_object in [np._NoValue, None, np.nan, 'nat', '']:
        # numpy treats empty string and all case combinations of 'nat' as NaT
        dtype = StringDType(na_object=na_object)
        arr = np.array([''] + all_nats, dtype=dtype)
        dt_array = arr.astype('M8[s]')
        td_array = arr.astype('m8[s]')
        assert_array_equal(dt_array, NaT_dt)
        assert_array_equal(td_array, NaT_td)

        if na_object is np._NoValue:
            output_object = 'NaT'
        else:
            output_object = na_object

        for arr in [dt_array, td_array]:
            assert_array_equal(
                arr.astype(dtype),
                np.array([output_object]*arr.size, dtype=dtype))


def test_nat_conversion():
    for nat in [np.datetime64("NaT", "s"), np.timedelta64("NaT", "s")]:
        with pytest.raises(ValueError, match="string coercion is disabled"):
            np.array(["a", nat], dtype=StringDType(coerce=False))


def test_growing_strings(dtype):
    # growing a string leads to a heap allocation, this tests to make sure
    # we do that bookkeeping correctly for all possible starting cases
    data = [
        "hello",  # a short string
        "abcdefghijklmnopqestuvwxyz",  # a medium heap-allocated string
        "hello" * 200,  # a long heap-allocated string
    ]

    arr = np.array(data, dtype=dtype)
    uarr = np.array(data, dtype=str)

    for _ in range(5):
        arr = arr + arr
        uarr = uarr + uarr

    assert_array_equal(arr, uarr)


@pytest.mark.skipif(IS_WASM, reason="no threading support in wasm")
def test_threaded_access_and_mutation(dtype, random_string_list):
    # this test uses an RNG and may crash or cause deadlocks if there is a
    # threading bug
    rng = np.random.default_rng(0x4D3D3D3)

    def func(arr):
        rnd = rng.random()
        # either write to random locations in the array, compute a ufunc, or
        # re-initialize the array
        if rnd < 0.25:
            num = np.random.randint(0, arr.size)
            arr[num] = arr[num] + "hello"
        elif rnd < 0.5:
            if rnd < 0.375:
                np.add(arr, arr)
            else:
                np.add(arr, arr, out=arr)
        elif rnd < 0.75:
            if rnd < 0.875:
                np.multiply(arr, np.int64(2))
            else:
                np.multiply(arr, np.int64(2), out=arr)
        else:
            arr[:] = random_string_list

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as tpe:
        arr = np.array(random_string_list, dtype=dtype)
        futures = [tpe.submit(func, arr) for _ in range(500)]

        for f in futures:
            f.result()


UFUNC_TEST_DATA = [
    "hello" * 10,
    "Ae¢☃€ 😊" * 20,
    "entry\nwith\nnewlines",
    "entry\twith\ttabs",
]


@pytest.fixture
def string_array(dtype):
    return np.array(UFUNC_TEST_DATA, dtype=dtype)


@pytest.fixture
def unicode_array():
    return np.array(UFUNC_TEST_DATA, dtype=np.str_)


NAN_PRESERVING_FUNCTIONS = [
    "capitalize",
    "expandtabs",
    "lower",
    "lstrip",
    "rstrip",
    "splitlines",
    "strip",
    "swapcase",
    "title",
    "upper",
]

BOOL_OUTPUT_FUNCTIONS = [
    "isalnum",
    "isalpha",
    "isdigit",
    "islower",
    "isspace",
    "istitle",
    "isupper",
    "isnumeric",
    "isdecimal",
]

UNARY_FUNCTIONS = [
    "str_len",
    "capitalize",
    "expandtabs",
    "isalnum",
    "isalpha",
    "isdigit",
    "islower",
    "isspace",
    "istitle",
    "isupper",
    "lower",
    "lstrip",
    "rstrip",
    "splitlines",
    "strip",
    "swapcase",
    "title",
    "upper",
    "isnumeric",
    "isdecimal",
    "isalnum",
    "islower",
    "istitle",
    "isupper",
]

UNIMPLEMENTED_VEC_STRING_FUNCTIONS = [
    "capitalize",
    "expandtabs",
    "lower",
    "splitlines",
    "swapcase",
    "title",
    "upper",
]

ONLY_IN_NP_CHAR = [
    "join",
    "split",
    "rsplit",
    "splitlines"
]


@pytest.mark.parametrize("function_name", UNARY_FUNCTIONS)
def test_unary(string_array, unicode_array, function_name):
    if function_name in ONLY_IN_NP_CHAR:
        func = getattr(np.char, function_name)
    else:
        func = getattr(np.strings, function_name)
    dtype = string_array.dtype
    sres = func(string_array)
    ures = func(unicode_array)
    if sres.dtype == StringDType():
        ures = ures.astype(StringDType())
    assert_array_equal(sres, ures)

    if not hasattr(dtype, "na_object"):
        return

    is_nan = np.isnan(np.array([dtype.na_object], dtype=dtype))[0]
    is_str = isinstance(dtype.na_object, str)
    na_arr = np.insert(string_array, 0, dtype.na_object)

    if function_name in UNIMPLEMENTED_VEC_STRING_FUNCTIONS:
        if not is_str:
            # to avoid these errors we'd need to add NA support to _vec_string
            with pytest.raises((ValueError, TypeError)):
                func(na_arr)
        else:
            if function_name == "splitlines":
                assert func(na_arr)[0] == func(dtype.na_object)[()]
            else:
                assert func(na_arr)[0] == func(dtype.na_object)
        return
    if function_name == "str_len" and not is_str:
        # str_len always errors for any non-string null, even NA ones because
        # it has an integer result
        with pytest.raises(ValueError):
            func(na_arr)
        return
    if function_name in BOOL_OUTPUT_FUNCTIONS:
        if is_nan:
            assert func(na_arr)[0] is np.False_
        elif is_str:
            assert func(na_arr)[0] == func(dtype.na_object)
        else:
            with pytest.raises(ValueError):
                func(na_arr)
        return
    if not (is_nan or is_str):
        with pytest.raises(ValueError):
            func(na_arr)
        return
    res = func(na_arr)
    if is_nan and function_name in NAN_PRESERVING_FUNCTIONS:
        assert res[0] is dtype.na_object
    elif is_str:
        assert res[0] == func(dtype.na_object)


unicode_bug_fail = pytest.mark.xfail(
    reason="unicode output width is buggy", strict=True
)

# None means that the argument is a string array
BINARY_FUNCTIONS = [
    ("add", (None, None)),
    ("multiply", (None, 2)),
    ("mod", ("format: %s", None)),
    ("center", (None, 25)),
    ("count", (None, "A")),
    ("encode", (None, "UTF-8")),
    ("endswith", (None, "lo")),
    ("find", (None, "A")),
    ("index", (None, "e")),
    ("join", ("-", None)),
    ("ljust", (None, 12)),
    ("lstrip", (None, "A")),
    ("partition", (None, "A")),
    ("replace", (None, "A", "B")),
    ("rfind", (None, "A")),
    ("rindex", (None, "e")),
    ("rjust", (None, 12)),
    ("rsplit", (None, "A")),
    ("rstrip", (None, "A")),
    ("rpartition", (None, "A")),
    ("split", (None, "A")),
    ("strip", (None, "A")),
    ("startswith", (None, "A")),
    ("zfill", (None, 12)),
]

PASSES_THROUGH_NAN_NULLS = [
    "add",
    "center",
    "ljust",
    "multiply",
    "replace",
    "rjust",
    "strip",
    "lstrip",
    "rstrip",
    "replace"
    "zfill",
]

NULLS_ARE_FALSEY = [
    "startswith",
    "endswith",
]

NULLS_ALWAYS_ERROR = [
    "count",
    "find",
    "rfind",
]

SUPPORTS_NULLS = (
    PASSES_THROUGH_NAN_NULLS +
    NULLS_ARE_FALSEY +
    NULLS_ALWAYS_ERROR
)


def call_func(func, args, array, sanitize=True):
    if args == (None, None):
        return func(array, array)
    if args[0] is None:
        if sanitize:
            san_args = tuple(
                np.array(arg, dtype=array.dtype) if isinstance(arg, str) else
                arg for arg in args[1:]
            )
        else:
            san_args = args[1:]
        return func(array, *san_args)
    if args[1] is None:
        return func(args[0], array)
    # shouldn't ever happen
    assert 0


@pytest.mark.parametrize("function_name, args", BINARY_FUNCTIONS)
def test_binary(string_array, unicode_array, function_name, args):
    if function_name in ONLY_IN_NP_CHAR:
        func = getattr(np.char, function_name)
    else:
        func = getattr(np.strings, function_name)
    sres = call_func(func, args, string_array)
    ures = call_func(func, args, unicode_array, sanitize=False)
    if not isinstance(sres, tuple) and sres.dtype == StringDType():
        ures = ures.astype(StringDType())
    assert_array_equal(sres, ures)

    dtype = string_array.dtype
    if function_name not in SUPPORTS_NULLS or not hasattr(dtype, "na_object"):
        return

    na_arr = np.insert(string_array, 0, dtype.na_object)
    is_nan = np.isnan(np.array([dtype.na_object], dtype=dtype))[0]
    is_str = isinstance(dtype.na_object, str)
    should_error = not (is_nan or is_str)

    if (
        (function_name in NULLS_ALWAYS_ERROR and not is_str)
        or (function_name in PASSES_THROUGH_NAN_NULLS and should_error)
        or (function_name in NULLS_ARE_FALSEY and should_error)
    ):
        with pytest.raises((ValueError, TypeError)):
            call_func(func, args, na_arr)
        return

    res = call_func(func, args, na_arr)

    if is_str:
        assert res[0] == call_func(func, args, na_arr[:1])
    elif function_name in NULLS_ARE_FALSEY:
        assert res[0] is np.False_
    elif function_name in PASSES_THROUGH_NAN_NULLS:
        assert res[0] is dtype.na_object
    else:
        # shouldn't ever get here
        assert 0


@pytest.mark.parametrize("function, expected", [
    (np.strings.find, [[2, -1], [1, -1]]),
    (np.strings.startswith, [[False, False], [True, False]])])
@pytest.mark.parametrize("start, stop", [
    (1, 4),
    (np.int8(1), np.int8(4)),
    (np.array([1, 1], dtype='u2'), np.array([4, 4], dtype='u2'))])
def test_non_default_start_stop(function, start, stop, expected):
    a = np.array([["--🐍--", "--🦜--"],
                  ["-🐍---", "-🦜---"]], "T")
    indx = function(a, "🐍", start, stop)
    assert_array_equal(indx, expected)


@pytest.mark.parametrize("count", [2, np.int8(2), np.array([2, 2], 'u2')])
def test_replace_non_default_repeat(count):
    a = np.array(["🐍--", "🦜-🦜-"], "T")
    result = np.strings.replace(a, "🦜-", "🦜†", count)
    assert_array_equal(result, np.array(["🐍--", "🦜†🦜†"], "T"))


def test_strip_ljust_rjust_consistency(string_array, unicode_array):
    rjs = np.char.rjust(string_array, 1000)
    rju = np.char.rjust(unicode_array, 1000)

    ljs = np.char.ljust(string_array, 1000)
    lju = np.char.ljust(unicode_array, 1000)

    assert_array_equal(
        np.char.lstrip(rjs),
        np.char.lstrip(rju).astype(StringDType()),
    )

    assert_array_equal(
        np.char.rstrip(ljs),
        np.char.rstrip(lju).astype(StringDType()),
    )

    assert_array_equal(
        np.char.strip(ljs),
        np.char.strip(lju).astype(StringDType()),
    )

    assert_array_equal(
        np.char.strip(rjs),
        np.char.strip(rju).astype(StringDType()),
    )


def test_unset_na_coercion():
    # a dtype instance with an unset na object is compatible
    # with a dtype that has one set

    # this test uses the "add" and "equal" ufunc but all ufuncs that
    # accept more than one string argument and produce a string should
    # behave this way
    # TODO: generalize to more ufuncs
    inp = ["hello", "world"]
    arr = np.array(inp, dtype=StringDType(na_object=None))
    for op_dtype in [None, StringDType(), StringDType(coerce=False),
                     StringDType(na_object=None)]:
        if op_dtype is None:
            op = "2"
        else:
            op = np.array("2", dtype=op_dtype)
        res = arr + op
        assert_array_equal(res, ["hello2", "world2"])

    # dtype instances with distinct explicitly set NA objects are incompatible
    for op_dtype in [StringDType(na_object=pd_NA), StringDType(na_object="")]:
        op = np.array("2", dtype=op_dtype)
        with pytest.raises(TypeError):
            arr + op

    # comparisons only consider the na_object
    for op_dtype in [None, StringDType(), StringDType(coerce=True),
                     StringDType(na_object=None)]:
        if op_dtype is None:
            op = inp
        else:
            op = np.array(inp, dtype=op_dtype)
        assert_array_equal(arr, op)

    for op_dtype in [StringDType(na_object=pd_NA),
                     StringDType(na_object=np.nan)]:
        op = np.array(inp, dtype=op_dtype)
        with pytest.raises(TypeError):
            arr == op


def test_repeat(string_array):
    res = string_array.repeat(1000)
    # Create an empty array with expanded dimension, and fill it.  Then,
    # reshape it to the expected result.
    expected = np.empty_like(string_array, shape=string_array.shape + (1000,))
    expected[...] = string_array[:, np.newaxis]
    expected = expected.reshape(-1)

    assert_array_equal(res, expected, strict=True)


@pytest.mark.parametrize("tile", [1, 6, (2, 5)])
def test_accumulation(string_array, tile):
    """Accumulation is odd for StringDType but tests dtypes with references.
    """
    # Fill with mostly empty strings to not create absurdly big strings
    arr = np.zeros_like(string_array, shape=(100,))
    arr[:len(string_array)] = string_array
    arr[-len(string_array):] = string_array

    # Bloat size a bit (get above thresholds and test >1 ndim).
    arr = np.tile(string_array, tile)

    res = np.add.accumulate(arr, axis=0)
    res_obj = np.add.accumulate(arr.astype(object), axis=0)
    assert_array_equal(res, res_obj.astype(arr.dtype), strict=True)

    if arr.ndim > 1:
        res = np.add.accumulate(arr, axis=-1)
        res_obj = np.add.accumulate(arr.astype(object), axis=-1)

        assert_array_equal(res, res_obj.astype(arr.dtype), strict=True)


class TestImplementation:
    """Check that strings are stored in the arena when possible.

    This tests implementation details, so should be adjusted if
    the implementation changes.
    """

    @classmethod
    def setup_class(self):
        self.MISSING = 0x80
        self.INITIALIZED = 0x40
        self.OUTSIDE_ARENA = 0x20
        self.LONG = 0x10
        self.dtype = StringDType(na_object=np.nan)
        self.sizeofstr = self.dtype.itemsize
        sp = self.dtype.itemsize // 2  # pointer size = sizeof(size_t)
        # Below, size is not strictly correct, since it really uses
        # 7 (or 3) bytes, but good enough for the tests here.
        self.view_dtype = np.dtype([
            ('offset', f'u{sp}'),
            ('size', f'u{sp // 2}'),
            ('xsiz', f'V{sp // 2 - 1}'),
            ('size_and_flags', 'u1'),
        ] if sys.byteorder == 'little' else [
            ('size_and_flags', 'u1'),
            ('xsiz', f'V{sp // 2 - 1}'),
            ('size', f'u{sp // 2}'),
            ('offset', f'u{sp}'),
        ])
        self.s_empty = ""
        self.s_short = "01234"
        self.s_medium = "abcdefghijklmnopqrstuvwxyz"
        self.s_long = "-=+" * 100
        self.a = np.array(
            [self.s_empty, self.s_short, self.s_medium, self.s_long],
            self.dtype)

    def get_view(self, a):
        # Cannot view a StringDType as anything else directly, since
        # it has references. So, we use a stride trick hack.
        from numpy.lib._stride_tricks_impl import DummyArray
        interface = dict(a.__array_interface__)
        interface['descr'] = self.view_dtype.descr
        interface['typestr'] = self.view_dtype.str
        return np.asarray(DummyArray(interface, base=a))

    def get_flags(self, a):
        return self.get_view(a)['size_and_flags'] & 0xf0

    def is_short(self, a):
        return self.get_flags(a) == self.INITIALIZED | self.OUTSIDE_ARENA

    def is_on_heap(self, a):
        return self.get_flags(a) == (self.INITIALIZED
                                     | self.OUTSIDE_ARENA
                                     | self.LONG)

    def is_missing(self, a):
        return self.get_flags(a) & self.MISSING == self.MISSING

    def in_arena(self, a):
        return (self.get_flags(a) & (self.INITIALIZED | self.OUTSIDE_ARENA)
                == self.INITIALIZED)

    def test_setup(self):
        is_short = self.is_short(self.a)
        length = np.strings.str_len(self.a)
        assert_array_equal(is_short, (length > 0) & (length <= 15))
        assert_array_equal(self.in_arena(self.a), [False, False, True, True])
        assert_array_equal(self.is_on_heap(self.a), False)
        assert_array_equal(self.is_missing(self.a), False)
        view = self.get_view(self.a)
        sizes = np.where(is_short, view['size_and_flags'] & 0xf,
                         view['size'])
        assert_array_equal(sizes, np.strings.str_len(self.a))
        assert_array_equal(view['xsiz'][2:],
                           np.void(b'\x00' * (self.sizeofstr // 4 - 1)))
        # Check that the medium string uses only 1 byte for its length
        # in the arena, while the long string takes 8 (or 4).
        offsets = view['offset']
        assert offsets[2] == 1
        assert offsets[3] == 1 + len(self.s_medium) + self.sizeofstr // 2

    def test_empty(self):
        e = np.empty((3,), self.dtype)
        assert_array_equal(self.get_flags(e), 0)
        assert_array_equal(e, "")

    def test_zeros(self):
        z = np.zeros((2,), self.dtype)
        assert_array_equal(self.get_flags(z), 0)
        assert_array_equal(z, "")

    def test_copy(self):
        for c in [self.a.copy(), copy.copy(self.a), copy.deepcopy(self.a)]:
            assert_array_equal(self.get_flags(c), self.get_flags(self.a))
            assert_array_equal(c, self.a)
            offsets = self.get_view(c)['offset']
            assert offsets[2] == 1
            assert offsets[3] == 1 + len(self.s_medium) + self.sizeofstr // 2

    def test_arena_use_with_setting(self):
        c = np.zeros_like(self.a)
        assert_array_equal(self.get_flags(c), 0)
        c[:] = self.a
        assert_array_equal(self.get_flags(c), self.get_flags(self.a))
        assert_array_equal(c, self.a)

    def test_arena_reuse_with_setting(self):
        c = self.a.copy()
        c[:] = self.a
        assert_array_equal(self.get_flags(c), self.get_flags(self.a))
        assert_array_equal(c, self.a)

    def test_arena_reuse_after_missing(self):
        c = self.a.copy()
        c[:] = np.nan
        assert np.all(self.is_missing(c))
        # Replacing with the original strings, the arena should be reused.
        c[:] = self.a
        assert_array_equal(self.get_flags(c), self.get_flags(self.a))
        assert_array_equal(c, self.a)

    def test_arena_reuse_after_empty(self):
        c = self.a.copy()
        c[:] = ""
        assert_array_equal(c, "")
        # Replacing with the original strings, the arena should be reused.
        c[:] = self.a
        assert_array_equal(self.get_flags(c), self.get_flags(self.a))
        assert_array_equal(c, self.a)

    def test_arena_reuse_for_shorter(self):
        c = self.a.copy()
        # A string slightly shorter than the shortest in the arena
        # should be used for all strings in the arena.
        c[:] = self.s_medium[:-1]
        assert_array_equal(c, self.s_medium[:-1])
        # first empty string in original was never initialized, so
        # filling it in now leaves it initialized inside the arena.
        # second string started as a short string so it can never live
        # in the arena.
        in_arena = np.array([True, False, True, True])
        assert_array_equal(self.in_arena(c), in_arena)
        # But when a short string is replaced, it will go on the heap.
        assert_array_equal(self.is_short(c), False)
        assert_array_equal(self.is_on_heap(c), ~in_arena)
        # We can put the originals back, and they'll still fit,
        # and short strings are back as short strings
        c[:] = self.a
        assert_array_equal(c, self.a)
        assert_array_equal(self.in_arena(c), in_arena)
        assert_array_equal(self.is_short(c), self.is_short(self.a))
        assert_array_equal(self.is_on_heap(c), False)

    def test_arena_reuse_if_possible(self):
        c = self.a.copy()
        # A slightly longer string will not fit in the arena for
        # the medium string, but will fit for the longer one.
        c[:] = self.s_medium + "±"
        assert_array_equal(c, self.s_medium + "±")
        in_arena_exp = np.strings.str_len(self.a) >= len(self.s_medium) + 1
        # first entry started uninitialized and empty, so filling it leaves
        # it in the arena
        in_arena_exp[0] = True
        assert not np.all(in_arena_exp == self.in_arena(self.a))
        assert_array_equal(self.in_arena(c), in_arena_exp)
        assert_array_equal(self.is_short(c), False)
        assert_array_equal(self.is_on_heap(c), ~in_arena_exp)
        # And once outside arena, it stays outside, since offset is lost.
        # But short strings are used again.
        c[:] = self.a
        is_short_exp = self.is_short(self.a)
        assert_array_equal(c, self.a)
        assert_array_equal(self.in_arena(c), in_arena_exp)
        assert_array_equal(self.is_short(c), is_short_exp)
        assert_array_equal(self.is_on_heap(c), ~in_arena_exp & ~is_short_exp)

    def test_arena_no_reuse_after_short(self):
        c = self.a.copy()
        # If we replace a string with a short string, it cannot
        # go into the arena after because the offset is lost.
        c[:] = self.s_short
        assert_array_equal(c, self.s_short)
        assert_array_equal(self.in_arena(c), False)
        c[:] = self.a
        assert_array_equal(c, self.a)
        assert_array_equal(self.in_arena(c), False)
        assert_array_equal(self.is_on_heap(c), self.in_arena(self.a))
