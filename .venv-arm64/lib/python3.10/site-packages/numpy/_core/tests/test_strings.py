import sys
import pytest

import operator
import numpy as np

from numpy.testing import assert_array_equal, assert_raises, IS_PYPY
from numpy.testing._private.utils import requires_memory

COMPARISONS = [
    (operator.eq, np.equal, "=="),
    (operator.ne, np.not_equal, "!="),
    (operator.lt, np.less, "<"),
    (operator.le, np.less_equal, "<="),
    (operator.gt, np.greater, ">"),
    (operator.ge, np.greater_equal, ">="),
]

MAX = np.iinfo(np.int64).max

IS_PYPY_LT_7_3_16 = IS_PYPY and sys.implementation.version < (7, 3, 16)

@pytest.mark.parametrize(["op", "ufunc", "sym"], COMPARISONS)
def test_mixed_string_comparison_ufuncs_fail(op, ufunc, sym):
    arr_string = np.array(["a", "b"], dtype="S")
    arr_unicode = np.array(["a", "c"], dtype="U")

    with pytest.raises(TypeError, match="did not contain a loop"):
        ufunc(arr_string, arr_unicode)

    with pytest.raises(TypeError, match="did not contain a loop"):
        ufunc(arr_unicode, arr_string)

@pytest.mark.parametrize(["op", "ufunc", "sym"], COMPARISONS)
def test_mixed_string_comparisons_ufuncs_with_cast(op, ufunc, sym):
    arr_string = np.array(["a", "b"], dtype="S")
    arr_unicode = np.array(["a", "c"], dtype="U")

    # While there is no loop, manual casting is acceptable:
    res1 = ufunc(arr_string, arr_unicode, signature="UU->?", casting="unsafe")
    res2 = ufunc(arr_string, arr_unicode, signature="SS->?", casting="unsafe")

    expected = op(arr_string.astype("U"), arr_unicode)
    assert_array_equal(res1, expected)
    assert_array_equal(res2, expected)


@pytest.mark.parametrize(["op", "ufunc", "sym"], COMPARISONS)
@pytest.mark.parametrize("dtypes", [
        ("S2", "S2"), ("S2", "S10"),
        ("<U1", "<U1"), ("<U1", ">U1"), (">U1", ">U1"),
        ("<U1", "<U10"), ("<U1", ">U10")])
@pytest.mark.parametrize("aligned", [True, False])
def test_string_comparisons(op, ufunc, sym, dtypes, aligned):
    # ensure native byte-order for the first view to stay within unicode range
    native_dt = np.dtype(dtypes[0]).newbyteorder("=")
    arr = np.arange(2**15).view(native_dt).astype(dtypes[0])
    if not aligned:
        # Make `arr` unaligned:
        new = np.zeros(arr.nbytes + 1, dtype=np.uint8)[1:].view(dtypes[0])
        new[...] = arr
        arr = new

    arr2 = arr.astype(dtypes[1], copy=True)
    np.random.shuffle(arr2)
    arr[0] = arr2[0]  # make sure one matches

    expected = [op(d1, d2) for d1, d2 in zip(arr.tolist(), arr2.tolist())]
    assert_array_equal(op(arr, arr2), expected)
    assert_array_equal(ufunc(arr, arr2), expected)
    assert_array_equal(
        np.char.compare_chararrays(arr, arr2, sym, False), expected
    )

    expected = [op(d2, d1) for d1, d2 in zip(arr.tolist(), arr2.tolist())]
    assert_array_equal(op(arr2, arr), expected)
    assert_array_equal(ufunc(arr2, arr), expected)
    assert_array_equal(
        np.char.compare_chararrays(arr2, arr, sym, False), expected
    )


@pytest.mark.parametrize(["op", "ufunc", "sym"], COMPARISONS)
@pytest.mark.parametrize("dtypes", [
        ("S2", "S2"), ("S2", "S10"), ("<U1", "<U1"), ("<U1", ">U10")])
def test_string_comparisons_empty(op, ufunc, sym, dtypes):
    arr = np.empty((1, 0, 1, 5), dtype=dtypes[0])
    arr2 = np.empty((100, 1, 0, 1), dtype=dtypes[1])

    expected = np.empty(np.broadcast_shapes(arr.shape, arr2.shape), dtype=bool)
    assert_array_equal(op(arr, arr2), expected)
    assert_array_equal(ufunc(arr, arr2), expected)
    assert_array_equal(
        np.char.compare_chararrays(arr, arr2, sym, False), expected
    )


@pytest.mark.parametrize("str_dt", ["S", "U"])
@pytest.mark.parametrize("float_dt", np.typecodes["AllFloat"])
def test_float_to_string_cast(str_dt, float_dt):
    float_dt = np.dtype(float_dt)
    fi = np.finfo(float_dt)
    arr = np.array([np.nan, np.inf, -np.inf, fi.max, fi.min], dtype=float_dt)
    expected = ["nan", "inf", "-inf", str(fi.max), str(fi.min)]
    if float_dt.kind == "c":
        expected = [f"({r}+0j)" for r in expected]

    res = arr.astype(str_dt)
    assert_array_equal(res, np.array(expected, dtype=str_dt))


@pytest.mark.parametrize("str_dt", "US")
@pytest.mark.parametrize("size", [-1, np.iinfo(np.intc).max])
def test_string_size_dtype_errors(str_dt, size):
    if size > 0:
        size = size // np.dtype(f"{str_dt}1").itemsize + 1

    with pytest.raises(ValueError):
        np.dtype((str_dt, size))
    with pytest.raises(TypeError):
        np.dtype(f"{str_dt}{size}")


@pytest.mark.parametrize("str_dt", "US")
def test_string_size_dtype_large_repr(str_dt):
    size = np.iinfo(np.intc).max // np.dtype(f"{str_dt}1").itemsize
    size_str = str(size)

    dtype = np.dtype((str_dt, size))
    assert size_str in dtype.str
    assert size_str in str(dtype)
    assert size_str in repr(dtype)


@pytest.mark.slow
@requires_memory(2 * np.iinfo(np.intc).max)
@pytest.mark.parametrize("str_dt", "US")
def test_large_string_coercion_error(str_dt):
    very_large = np.iinfo(np.intc).max // np.dtype(f"{str_dt}1").itemsize
    try:
        large_string = "A" * (very_large + 1)
    except Exception:
        # We may not be able to create this Python string on 32bit.
        pytest.skip("python failed to create huge string")

    class MyStr:
        def __str__(self):
            return large_string

    try:
        # TypeError from NumPy, or OverflowError from 32bit Python.
        with pytest.raises((TypeError, OverflowError)):
            np.array([large_string], dtype=str_dt)

        # Same as above, but input has to be converted to a string.
        with pytest.raises((TypeError, OverflowError)):
            np.array([MyStr()], dtype=str_dt)
    except MemoryError:
        # Catch memory errors, because `requires_memory` would do so.
        raise AssertionError("Ops should raise before any large allocation.")

@pytest.mark.slow
@requires_memory(2 * np.iinfo(np.intc).max)
@pytest.mark.parametrize("str_dt", "US")
def test_large_string_addition_error(str_dt):
    very_large = np.iinfo(np.intc).max // np.dtype(f"{str_dt}1").itemsize

    a = np.array(["A" * very_large], dtype=str_dt)
    b = np.array("B", dtype=str_dt)
    try:
        with pytest.raises(TypeError):
            np.add(a, b)
        with pytest.raises(TypeError):
            np.add(a, a)
    except MemoryError:
        # Catch memory errors, because `requires_memory` would do so.
        raise AssertionError("Ops should raise before any large allocation.")


def test_large_string_cast():
    very_large = np.iinfo(np.intc).max // 4
    # Could be nice to test very large path, but it makes too many huge
    # allocations right now (need non-legacy cast loops for this).
    # a = np.array([], dtype=np.dtype(("S", very_large)))
    # assert a.astype("U").dtype.itemsize == very_large * 4

    a = np.array([], dtype=np.dtype(("S", very_large + 1)))
    # It is not perfect but OK if this raises a MemoryError during setup
    # (this happens due clunky code and/or buffer setup.)
    with pytest.raises((TypeError, MemoryError)):
        a.astype("U")


@pytest.mark.parametrize("dt", ["S", "U", "T"])
class TestMethods:

    @pytest.mark.parametrize("in1,in2,out", [
        ("", "", ""),
        ("abc", "abc", "abcabc"),
        ("12345", "12345", "1234512345"),
        ("MixedCase", "MixedCase", "MixedCaseMixedCase"),
        ("12345 \0 ", "12345 \0 ", "12345 \0 12345 \0 "),
        ("UPPER", "UPPER", "UPPERUPPER"),
        (["abc", "def"], ["hello", "world"], ["abchello", "defworld"]),
    ])
    def test_add(self, in1, in2, out, dt):
        in1 = np.array(in1, dtype=dt)
        in2 = np.array(in2, dtype=dt)
        out = np.array(out, dtype=dt)
        assert_array_equal(np.strings.add(in1, in2), out)

    @pytest.mark.parametrize("in1,in2,out", [
        ("abc", 3, "abcabcabc"),
        ("abc", 0, ""),
        ("abc", -1, ""),
        (["abc", "def"], [1, 4], ["abc", "defdefdefdef"]),
    ])
    def test_multiply(self, in1, in2, out, dt):
        in1 = np.array(in1, dtype=dt)
        out = np.array(out, dtype=dt)
        assert_array_equal(np.strings.multiply(in1, in2), out)

    def test_multiply_raises(self, dt):
        with pytest.raises(TypeError, match="unsupported type"):
            np.strings.multiply(np.array("abc", dtype=dt), 3.14)

        with pytest.raises(MemoryError):
            np.strings.multiply(np.array("abc", dtype=dt), sys.maxsize)

    @pytest.mark.parametrize("i_dt", [np.int8, np.int16, np.int32,
                                      np.int64, np.int_])
    def test_multiply_integer_dtypes(self, i_dt, dt):
        a = np.array("abc", dtype=dt)
        i = np.array(3, dtype=i_dt)
        res = np.array("abcabcabc", dtype=dt)
        assert_array_equal(np.strings.multiply(a, i), res)

    @pytest.mark.parametrize("in_,out", [
        ("", False),
        ("a", True),
        ("A", True),
        ("\n", False),
        ("abc", True),
        ("aBc123", False),
        ("abc\n", False),
        (["abc", "aBc123"], [True, False]),
    ])
    def test_isalpha(self, in_, out, dt):
        in_ = np.array(in_, dtype=dt)
        assert_array_equal(np.strings.isalpha(in_), out)

    @pytest.mark.parametrize("in_,out", [
        ('', False),
        ('a', True),
        ('A', True),
        ('\n', False),
        ('123abc456', True),
        ('a1b3c', True),
        ('aBc000 ', False),
        ('abc\n', False),
    ])
    def test_isalnum(self, in_, out, dt):
        in_ = np.array(in_, dtype=dt)
        assert_array_equal(np.strings.isalnum(in_), out)

    @pytest.mark.parametrize("in_,out", [
        ("", False),
        ("a", False),
        ("0", True),
        ("012345", True),
        ("012345a", False),
        (["a", "012345"], [False, True]),
    ])
    def test_isdigit(self, in_, out, dt):
        in_ = np.array(in_, dtype=dt)
        assert_array_equal(np.strings.isdigit(in_), out)

    @pytest.mark.parametrize("in_,out", [
        ("", False),
        ("a", False),
        ("1", False),
        (" ", True),
        ("\t", True),
        ("\r", True),
        ("\n", True),
        (" \t\r \n", True),
        (" \t\r\na", False),
        (["\t1", " \t\r \n"], [False, True])
    ])
    def test_isspace(self, in_, out, dt):
        in_ = np.array(in_, dtype=dt)
        assert_array_equal(np.strings.isspace(in_), out)

    @pytest.mark.parametrize("in_,out", [
        ('', False),
        ('a', True),
        ('A', False),
        ('\n', False),
        ('abc', True),
        ('aBc', False),
        ('abc\n', True),
    ])
    def test_islower(self, in_, out, dt):
        in_ = np.array(in_, dtype=dt)
        assert_array_equal(np.strings.islower(in_), out)

    @pytest.mark.parametrize("in_,out", [
        ('', False),
        ('a', False),
        ('A', True),
        ('\n', False),
        ('ABC', True),
        ('AbC', False),
        ('ABC\n', True),
    ])
    def test_isupper(self, in_, out, dt):
        in_ = np.array(in_, dtype=dt)
        assert_array_equal(np.strings.isupper(in_), out)

    @pytest.mark.parametrize("in_,out", [
        ('', False),
        ('a', False),
        ('A', True),
        ('\n', False),
        ('A Titlecased Line', True),
        ('A\nTitlecased Line', True),
        ('A Titlecased, Line', True),
        ('Not a capitalized String', False),
        ('Not\ta Titlecase String', False),
        ('Not--a Titlecase String', False),
        ('NOT', False),
    ])
    def test_istitle(self, in_, out, dt):
        in_ = np.array(in_, dtype=dt)
        assert_array_equal(np.strings.istitle(in_), out)

    @pytest.mark.parametrize("in_,out", [
        ("", 0),
        ("abc", 3),
        ("12345", 5),
        ("MixedCase", 9),
        ("12345 \x00 ", 8),
        ("UPPER", 5),
        (["abc", "12345 \x00 "], [3, 8]),
    ])
    def test_str_len(self, in_, out, dt):
        in_ = np.array(in_, dtype=dt)
        assert_array_equal(np.strings.str_len(in_), out)

    @pytest.mark.parametrize("a,sub,start,end,out", [
        ("abcdefghiabc", "abc", 0, None, 0),
        ("abcdefghiabc", "abc", 1, None, 9),
        ("abcdefghiabc", "def", 4, None, -1),
        ("abc", "", 0, None, 0),
        ("abc", "", 3, None, 3),
        ("abc", "", 4, None, -1),
        ("rrarrrrrrrrra", "a", 0, None, 2),
        ("rrarrrrrrrrra", "a", 4, None, 12),
        ("rrarrrrrrrrra", "a", 4, 6, -1),
        ("", "", 0, None, 0),
        ("", "", 1, 1, -1),
        ("", "", MAX, 0, -1),
        ("", "xx", 0, None, -1),
        ("", "xx", 1, 1, -1),
        ("", "xx", MAX, 0, -1),
        pytest.param(99*"a" + "b", "b", 0, None, 99,
                     id="99*a+b-b-0-None-99"),
        pytest.param(98*"a" + "ba", "ba", 0, None, 98,
                     id="98*a+ba-ba-0-None-98"),
        pytest.param(100*"a", "b", 0, None, -1,
                     id="100*a-b-0-None--1"),
        pytest.param(30000*"a" + 100*"b", 100*"b", 0, None, 30000,
                     id="30000*a+100*b-100*b-0-None-30000"),
        pytest.param(30000*"a", 100*"b", 0, None, -1,
                     id="30000*a-100*b-0-None--1"),
        pytest.param(15000*"a" + 15000*"b", 15000*"b", 0, None, 15000,
                     id="15000*a+15000*b-15000*b-0-None-15000"),
        pytest.param(15000*"a" + 15000*"b", 15000*"c", 0, None, -1,
                     id="15000*a+15000*b-15000*c-0-None--1"),
        (["abcdefghiabc", "rrarrrrrrrrra"], ["def", "arr"], [0, 3],
         None, [3, -1]),
        ("Ae¢☃€ 😊" * 2, "😊", 0, None, 6),
        ("Ae¢☃€ 😊" * 2, "😊", 7, None, 13),
        pytest.param("A" * (2 ** 17), r"[\w]+\Z", 0, None, -1,
                     id=r"A*2**17-[\w]+\Z-0-None--1"),
    ])
    def test_find(self, a, sub, start, end, out, dt):
        if "😊" in a and dt == "S":
            pytest.skip("Bytes dtype does not support non-ascii input")
        a = np.array(a, dtype=dt)
        sub = np.array(sub, dtype=dt)
        assert_array_equal(np.strings.find(a, sub, start, end), out)

    @pytest.mark.parametrize("a,sub,start,end,out", [
        ("abcdefghiabc", "abc", 0, None, 9),
        ("abcdefghiabc", "", 0, None, 12),
        ("abcdefghiabc", "abcd", 0, None, 0),
        ("abcdefghiabc", "abcz", 0, None, -1),
        ("abc", "", 0, None, 3),
        ("abc", "", 3, None, 3),
        ("abc", "", 4, None, -1),
        ("rrarrrrrrrrra", "a", 0, None, 12),
        ("rrarrrrrrrrra", "a", 4, None, 12),
        ("rrarrrrrrrrra", "a", 4, 6, -1),
        (["abcdefghiabc", "rrarrrrrrrrra"], ["abc", "a"], [0, 0],
         None, [9, 12]),
        ("Ae¢☃€ 😊" * 2, "😊", 0, None, 13),
        ("Ae¢☃€ 😊" * 2, "😊", 0, 7, 6),
    ])
    def test_rfind(self, a, sub, start, end, out, dt):
        if "😊" in a and dt == "S":
            pytest.skip("Bytes dtype does not support non-ascii input")
        a = np.array(a, dtype=dt)
        sub = np.array(sub, dtype=dt)
        assert_array_equal(np.strings.rfind(a, sub, start, end), out)

    @pytest.mark.parametrize("a,sub,start,end,out", [
        ("aaa", "a", 0, None, 3),
        ("aaa", "b", 0, None, 0),
        ("aaa", "a", 1, None, 2),
        ("aaa", "a", 10, None, 0),
        ("aaa", "a", -1, None, 1),
        ("aaa", "a", -10, None, 3),
        ("aaa", "a", 0, 1, 1),
        ("aaa", "a", 0, 10, 3),
        ("aaa", "a", 0, -1, 2),
        ("aaa", "a", 0, -10, 0),
        ("aaa", "", 1, None, 3),
        ("aaa", "", 3, None, 1),
        ("aaa", "", 10, None, 0),
        ("aaa", "", -1, None, 2),
        ("aaa", "", -10, None, 4),
        ("aaa", "aaaa", 0, None, 0),
        pytest.param(98*"a" + "ba", "ba", 0, None, 1,
                     id="98*a+ba-ba-0-None-1"),
        pytest.param(30000*"a" + 100*"b", 100*"b", 0, None, 1,
                     id="30000*a+100*b-100*b-0-None-1"),
        pytest.param(30000*"a", 100*"b", 0, None, 0,
                     id="30000*a-100*b-0-None-0"),
        pytest.param(30000*"a" + 100*"ab", "ab", 0, None, 100,
                     id="30000*a+100*ab-ab-0-None-100"),
        pytest.param(15000*"a" + 15000*"b", 15000*"b", 0, None, 1,
                     id="15000*a+15000*b-15000*b-0-None-1"),
        pytest.param(15000*"a" + 15000*"b", 15000*"c", 0, None, 0,
                     id="15000*a+15000*b-15000*c-0-None-0"),
        ("", "", 0, None, 1),
        ("", "", 1, 1, 0),
        ("", "", MAX, 0, 0),
        ("", "xx", 0, None, 0),
        ("", "xx", 1, 1, 0),
        ("", "xx", MAX, 0, 0),
        (["aaa", ""], ["a", ""], [0, 0], None, [3, 1]),
        ("Ae¢☃€ 😊" * 100, "😊", 0, None, 100),
    ])
    def test_count(self, a, sub, start, end, out, dt):
        if "😊" in a and dt == "S":
            pytest.skip("Bytes dtype does not support non-ascii input")
        a = np.array(a, dtype=dt)
        sub = np.array(sub, dtype=dt)
        assert_array_equal(np.strings.count(a, sub, start, end), out)

    @pytest.mark.parametrize("a,prefix,start,end,out", [
        ("hello", "he", 0, None, True),
        ("hello", "hello", 0, None, True),
        ("hello", "hello world", 0, None, False),
        ("hello", "", 0, None, True),
        ("hello", "ello", 0, None, False),
        ("hello", "ello", 1, None, True),
        ("hello", "o", 4, None, True),
        ("hello", "o", 5, None, False),
        ("hello", "", 5, None, True),
        ("hello", "lo", 6, None, False),
        ("helloworld", "lowo", 3, None, True),
        ("helloworld", "lowo", 3, 7, True),
        ("helloworld", "lowo", 3, 6, False),
        ("", "", 0, 1, True),
        ("", "", 0, 0, True),
        ("", "", 1, 0, False),
        ("hello", "he", 0, -1, True),
        ("hello", "he", -53, -1, True),
        ("hello", "hello", 0, -1, False),
        ("hello", "hello world", -1, -10, False),
        ("hello", "ello", -5, None, False),
        ("hello", "ello", -4, None, True),
        ("hello", "o", -2, None, False),
        ("hello", "o", -1, None, True),
        ("hello", "", -3, -3, True),
        ("hello", "lo", -9, None, False),
        (["hello", ""], ["he", ""], [0, 0], None, [True, True]),
    ])
    def test_startswith(self, a, prefix, start, end, out, dt):
        a = np.array(a, dtype=dt)
        prefix = np.array(prefix, dtype=dt)
        assert_array_equal(np.strings.startswith(a, prefix, start, end), out)

    @pytest.mark.parametrize("a,suffix,start,end,out", [
        ("hello", "lo", 0, None, True),
        ("hello", "he", 0, None, False),
        ("hello", "", 0, None, True),
        ("hello", "hello world", 0, None, False),
        ("helloworld", "worl", 0, None, False),
        ("helloworld", "worl", 3, 9, True),
        ("helloworld", "world", 3, 12, True),
        ("helloworld", "lowo", 1, 7, True),
        ("helloworld", "lowo", 2, 7, True),
        ("helloworld", "lowo", 3, 7, True),
        ("helloworld", "lowo", 4, 7, False),
        ("helloworld", "lowo", 3, 8, False),
        ("ab", "ab", 0, 1, False),
        ("ab", "ab", 0, 0, False),
        ("", "", 0, 1, True),
        ("", "", 0, 0, True),
        ("", "", 1, 0, False),
        ("hello", "lo", -2, None, True),
        ("hello", "he", -2, None, False),
        ("hello", "", -3, -3, True),
        ("hello", "hello world", -10, -2, False),
        ("helloworld", "worl", -6, None, False),
        ("helloworld", "worl", -5, -1, True),
        ("helloworld", "worl", -5, 9, True),
        ("helloworld", "world", -7, 12, True),
        ("helloworld", "lowo", -99, -3, True),
        ("helloworld", "lowo", -8, -3, True),
        ("helloworld", "lowo", -7, -3, True),
        ("helloworld", "lowo", 3, -4, False),
        ("helloworld", "lowo", -8, -2, False),
        (["hello", "helloworld"], ["lo", "worl"], [0, -6], None,
         [True, False]),
    ])
    def test_endswith(self, a, suffix, start, end, out, dt):
        a = np.array(a, dtype=dt)
        suffix = np.array(suffix, dtype=dt)
        assert_array_equal(np.strings.endswith(a, suffix, start, end), out)

    @pytest.mark.parametrize("a,chars,out", [
        ("", None, ""),
        ("   hello   ", None, "hello   "),
        ("hello", None, "hello"),
        (" \t\n\r\f\vabc \t\n\r\f\v", None, "abc \t\n\r\f\v"),
        (["   hello   ", "hello"], None, ["hello   ", "hello"]),
        ("", "", ""),
        ("", "xyz", ""),
        ("hello", "", "hello"),
        ("xyzzyhelloxyzzy", "xyz", "helloxyzzy"),
        ("hello", "xyz", "hello"),
        ("xyxz", "xyxz", ""),
        ("xyxzx", "x", "yxzx"),
        (["xyzzyhelloxyzzy", "hello"], ["xyz", "xyz"],
         ["helloxyzzy", "hello"]),
        (["ba", "ac", "baa", "bba"], "b", ["a", "ac", "aa", "a"]),
    ])
    def test_lstrip(self, a, chars, out, dt):
        a = np.array(a, dtype=dt)
        out = np.array(out, dtype=dt)
        if chars is not None:
            chars = np.array(chars, dtype=dt)
            assert_array_equal(np.strings.lstrip(a, chars), out)
        else:
            assert_array_equal(np.strings.lstrip(a), out)

    @pytest.mark.parametrize("a,chars,out", [
        ("", None, ""),
        ("   hello   ", None, "   hello"),
        ("hello", None, "hello"),
        (" \t\n\r\f\vabc \t\n\r\f\v", None, " \t\n\r\f\vabc"),
        (["   hello   ", "hello"], None, ["   hello", "hello"]),
        ("", "", ""),
        ("", "xyz", ""),
        ("hello", "", "hello"),
        (["hello    ", "abcdefghijklmnop"], None,
         ["hello", "abcdefghijklmnop"]),
        ("xyzzyhelloxyzzy", "xyz", "xyzzyhello"),
        ("hello", "xyz", "hello"),
        ("xyxz", "xyxz", ""),
        ("    ", None, ""),
        ("xyxzx", "x", "xyxz"),
        (["xyzzyhelloxyzzy", "hello"], ["xyz", "xyz"],
         ["xyzzyhello", "hello"]),
        (["ab", "ac", "aab", "abb"], "b", ["a", "ac", "aa", "a"]),
    ])
    def test_rstrip(self, a, chars, out, dt):
        a = np.array(a, dtype=dt)
        out = np.array(out, dtype=dt)
        if chars is not None:
            chars = np.array(chars, dtype=dt)
            assert_array_equal(np.strings.rstrip(a, chars), out)
        else:
            assert_array_equal(np.strings.rstrip(a), out)

    @pytest.mark.parametrize("a,chars,out", [
        ("", None, ""),
        ("   hello   ", None, "hello"),
        ("hello", None, "hello"),
        (" \t\n\r\f\vabc \t\n\r\f\v", None, "abc"),
        (["   hello   ", "hello"], None, ["hello", "hello"]),
        ("", "", ""),
        ("", "xyz", ""),
        ("hello", "", "hello"),
        ("xyzzyhelloxyzzy", "xyz", "hello"),
        ("hello", "xyz", "hello"),
        ("xyxz", "xyxz", ""),
        ("xyxzx", "x", "yxz"),
        (["xyzzyhelloxyzzy", "hello"], ["xyz", "xyz"],
         ["hello", "hello"]),
        (["bab", "ac", "baab", "bbabb"], "b", ["a", "ac", "aa", "a"]),
    ])
    def test_strip(self, a, chars, out, dt):
        a = np.array(a, dtype=dt)
        if chars is not None:
            chars = np.array(chars, dtype=dt)
        out = np.array(out, dtype=dt)
        assert_array_equal(np.strings.strip(a, chars), out)

    @pytest.mark.parametrize("buf,old,new,count,res", [
        ("", "", "", -1, ""),
        ("", "", "A", -1, "A"),
        ("", "A", "", -1, ""),
        ("", "A", "A", -1, ""),
        ("", "", "", 100, ""),
        ("", "", "A", 100, "A"),
        ("A", "", "", -1, "A"),
        ("A", "", "*", -1, "*A*"),
        ("A", "", "*1", -1, "*1A*1"),
        ("A", "", "*-#", -1, "*-#A*-#"),
        ("AA", "", "*-", -1, "*-A*-A*-"),
        ("AA", "", "*-", -1, "*-A*-A*-"),
        ("AA", "", "*-", 4, "*-A*-A*-"),
        ("AA", "", "*-", 3, "*-A*-A*-"),
        ("AA", "", "*-", 2, "*-A*-A"),
        ("AA", "", "*-", 1, "*-AA"),
        ("AA", "", "*-", 0, "AA"),
        ("A", "A", "", -1, ""),
        ("AAA", "A", "", -1, ""),
        ("AAA", "A", "", -1, ""),
        ("AAA", "A", "", 4, ""),
        ("AAA", "A", "", 3, ""),
        ("AAA", "A", "", 2, "A"),
        ("AAA", "A", "", 1, "AA"),
        ("AAA", "A", "", 0, "AAA"),
        ("AAAAAAAAAA", "A", "", -1, ""),
        ("ABACADA", "A", "", -1, "BCD"),
        ("ABACADA", "A", "", -1, "BCD"),
        ("ABACADA", "A", "", 5, "BCD"),
        ("ABACADA", "A", "", 4, "BCD"),
        ("ABACADA", "A", "", 3, "BCDA"),
        ("ABACADA", "A", "", 2, "BCADA"),
        ("ABACADA", "A", "", 1, "BACADA"),
        ("ABACADA", "A", "", 0, "ABACADA"),
        ("ABCAD", "A", "", -1, "BCD"),
        ("ABCADAA", "A", "", -1, "BCD"),
        ("BCD", "A", "", -1, "BCD"),
        ("*************", "A", "", -1, "*************"),
        ("^"+"A"*1000+"^", "A", "", 999, "^A^"),
        ("the", "the", "", -1, ""),
        ("theater", "the", "", -1, "ater"),
        ("thethe", "the", "", -1, ""),
        ("thethethethe", "the", "", -1, ""),
        ("theatheatheathea", "the", "", -1, "aaaa"),
        ("that", "the", "", -1, "that"),
        ("thaet", "the", "", -1, "thaet"),
        ("here and there", "the", "", -1, "here and re"),
        ("here and there and there", "the", "", -1, "here and re and re"),
        ("here and there and there", "the", "", 3, "here and re and re"),
        ("here and there and there", "the", "", 2, "here and re and re"),
        ("here and there and there", "the", "", 1, "here and re and there"),
        ("here and there and there", "the", "", 0, "here and there and there"),
        ("here and there and there", "the", "", -1, "here and re and re"),
        ("abc", "the", "", -1, "abc"),
        ("abcdefg", "the", "", -1, "abcdefg"),
        ("bbobob", "bob", "", -1, "bob"),
        ("bbobobXbbobob", "bob", "", -1, "bobXbob"),
        ("aaaaaaabob", "bob", "", -1, "aaaaaaa"),
        ("aaaaaaa", "bob", "", -1, "aaaaaaa"),
        ("Who goes there?", "o", "o", -1, "Who goes there?"),
        ("Who goes there?", "o", "O", -1, "WhO gOes there?"),
        ("Who goes there?", "o", "O", -1, "WhO gOes there?"),
        ("Who goes there?", "o", "O", 3, "WhO gOes there?"),
        ("Who goes there?", "o", "O", 2, "WhO gOes there?"),
        ("Who goes there?", "o", "O", 1, "WhO goes there?"),
        ("Who goes there?", "o", "O", 0, "Who goes there?"),
        ("Who goes there?", "a", "q", -1, "Who goes there?"),
        ("Who goes there?", "W", "w", -1, "who goes there?"),
        ("WWho goes there?WW", "W", "w", -1, "wwho goes there?ww"),
        ("Who goes there?", "?", "!", -1, "Who goes there!"),
        ("Who goes there??", "?", "!", -1, "Who goes there!!"),
        ("Who goes there?", ".", "!", -1, "Who goes there?"),
        ("This is a tissue", "is", "**", -1, "Th** ** a t**sue"),
        ("This is a tissue", "is", "**", -1, "Th** ** a t**sue"),
        ("This is a tissue", "is", "**", 4, "Th** ** a t**sue"),
        ("This is a tissue", "is", "**", 3, "Th** ** a t**sue"),
        ("This is a tissue", "is", "**", 2, "Th** ** a tissue"),
        ("This is a tissue", "is", "**", 1, "Th** is a tissue"),
        ("This is a tissue", "is", "**", 0, "This is a tissue"),
        ("bobob", "bob", "cob", -1, "cobob"),
        ("bobobXbobobob", "bob", "cob", -1, "cobobXcobocob"),
        ("bobob", "bot", "bot", -1, "bobob"),
        ("Reykjavik", "k", "KK", -1, "ReyKKjaviKK"),
        ("Reykjavik", "k", "KK", -1, "ReyKKjaviKK"),
        ("Reykjavik", "k", "KK", 2, "ReyKKjaviKK"),
        ("Reykjavik", "k", "KK", 1, "ReyKKjavik"),
        ("Reykjavik", "k", "KK", 0, "Reykjavik"),
        ("A.B.C.", ".", "----", -1, "A----B----C----"),
        ("Reykjavik", "q", "KK", -1, "Reykjavik"),
        ("spam, spam, eggs and spam", "spam", "ham", -1,
            "ham, ham, eggs and ham"),
        ("spam, spam, eggs and spam", "spam", "ham", -1,
            "ham, ham, eggs and ham"),
        ("spam, spam, eggs and spam", "spam", "ham", 4,
            "ham, ham, eggs and ham"),
        ("spam, spam, eggs and spam", "spam", "ham", 3,
            "ham, ham, eggs and ham"),
        ("spam, spam, eggs and spam", "spam", "ham", 2,
            "ham, ham, eggs and spam"),
        ("spam, spam, eggs and spam", "spam", "ham", 1,
            "ham, spam, eggs and spam"),
        ("spam, spam, eggs and spam", "spam", "ham", 0,
            "spam, spam, eggs and spam"),
        ("bobobob", "bobob", "bob", -1, "bobob"),
        ("bobobobXbobobob", "bobob", "bob", -1, "bobobXbobob"),
        ("BOBOBOB", "bob", "bobby", -1, "BOBOBOB"),
        ("one!two!three!", "!", "@", 1, "one@two!three!"),
        ("one!two!three!", "!", "", -1, "onetwothree"),
        ("one!two!three!", "!", "@", 2, "one@two@three!"),
        ("one!two!three!", "!", "@", 3, "one@two@three@"),
        ("one!two!three!", "!", "@", 4, "one@two@three@"),
        ("one!two!three!", "!", "@", 0, "one!two!three!"),
        ("one!two!three!", "!", "@", -1, "one@two@three@"),
        ("one!two!three!", "x", "@", -1, "one!two!three!"),
        ("one!two!three!", "x", "@", 2, "one!two!three!"),
        ("abc", "", "-", -1, "-a-b-c-"),
        ("abc", "", "-", 3, "-a-b-c"),
        ("abc", "", "-", 0, "abc"),
        ("abc", "ab", "--", 0, "abc"),
        ("abc", "xy", "--", -1, "abc"),
        (["abbc", "abbd"], "b", "z", [1, 2], ["azbc", "azzd"]),
    ])
    def test_replace(self, buf, old, new, count, res, dt):
        if "😊" in buf and dt == "S":
            pytest.skip("Bytes dtype does not support non-ascii input")
        buf = np.array(buf, dtype=dt)
        old = np.array(old, dtype=dt)
        new = np.array(new, dtype=dt)
        res = np.array(res, dtype=dt)
        assert_array_equal(np.strings.replace(buf, old, new, count), res)

    @pytest.mark.parametrize("buf,sub,start,end,res", [
        ("abcdefghiabc", "", 0, None, 0),
        ("abcdefghiabc", "def", 0, None, 3),
        ("abcdefghiabc", "abc", 0, None, 0),
        ("abcdefghiabc", "abc", 1, None, 9),
    ])
    def test_index(self, buf, sub, start, end, res, dt):
        buf = np.array(buf, dtype=dt)
        sub = np.array(sub, dtype=dt)
        assert_array_equal(np.strings.index(buf, sub, start, end), res)

    @pytest.mark.parametrize("buf,sub,start,end", [
        ("abcdefghiabc", "hib", 0, None),
        ("abcdefghiab", "abc", 1, None),
        ("abcdefghi", "ghi", 8, None),
        ("abcdefghi", "ghi", -1, None),
        ("rrarrrrrrrrra", "a", 4, 6),
    ])
    def test_index_raises(self, buf, sub, start, end, dt):
        buf = np.array(buf, dtype=dt)
        sub = np.array(sub, dtype=dt)
        with pytest.raises(ValueError, match="substring not found"):
            np.strings.index(buf, sub, start, end)

    @pytest.mark.parametrize("buf,sub,start,end,res", [
        ("abcdefghiabc", "", 0, None, 12),
        ("abcdefghiabc", "def", 0, None, 3),
        ("abcdefghiabc", "abc", 0, None, 9),
        ("abcdefghiabc", "abc", 0, -1, 0),
    ])
    def test_rindex(self, buf, sub, start, end, res, dt):
        buf = np.array(buf, dtype=dt)
        sub = np.array(sub, dtype=dt)
        assert_array_equal(np.strings.rindex(buf, sub, start, end), res)

    @pytest.mark.parametrize("buf,sub,start,end", [
        ("abcdefghiabc", "hib", 0, None),
        ("defghiabc", "def", 1, None),
        ("defghiabc", "abc", 0, -1),
        ("abcdefghi", "ghi", 0, 8),
        ("abcdefghi", "ghi", 0, -1),
        ("rrarrrrrrrrra", "a", 4, 6),
    ])
    def test_rindex_raises(self, buf, sub, start, end, dt):
        buf = np.array(buf, dtype=dt)
        sub = np.array(sub, dtype=dt)
        with pytest.raises(ValueError, match="substring not found"):
            np.strings.rindex(buf, sub, start, end)

    @pytest.mark.parametrize("buf,tabsize,res", [
        ("abc\rab\tdef\ng\thi", 8, "abc\rab      def\ng       hi"),
        ("abc\rab\tdef\ng\thi", 4, "abc\rab  def\ng   hi"),
        ("abc\r\nab\tdef\ng\thi", 8, "abc\r\nab      def\ng       hi"),
        ("abc\r\nab\tdef\ng\thi", 4, "abc\r\nab  def\ng   hi"),
        ("abc\r\nab\r\ndef\ng\r\nhi", 4, "abc\r\nab\r\ndef\ng\r\nhi"),
        (" \ta\n\tb", 1, "  a\n b"),
    ])
    def test_expandtabs(self, buf, tabsize, res, dt):
        buf = np.array(buf, dtype=dt)
        res = np.array(res, dtype=dt)
        assert_array_equal(np.strings.expandtabs(buf, tabsize), res)

    def test_expandtabs_raises_overflow(self, dt):
        with pytest.raises(OverflowError, match="new string is too long"):
            np.strings.expandtabs(np.array("\ta\n\tb", dtype=dt), sys.maxsize)
            np.strings.expandtabs(np.array("\ta\n\tb", dtype=dt), 2**61)

    FILL_ERROR = "The fill character must be exactly one character long"

    def test_center_raises_multiple_character_fill(self, dt):
        buf = np.array("abc", dtype=dt)
        fill = np.array("**", dtype=dt)
        with pytest.raises(TypeError, match=self.FILL_ERROR):
            np.strings.center(buf, 10, fill)

    def test_ljust_raises_multiple_character_fill(self, dt):
        buf = np.array("abc", dtype=dt)
        fill = np.array("**", dtype=dt)
        with pytest.raises(TypeError, match=self.FILL_ERROR):
            np.strings.ljust(buf, 10, fill)

    def test_rjust_raises_multiple_character_fill(self, dt):
        buf = np.array("abc", dtype=dt)
        fill = np.array("**", dtype=dt)
        with pytest.raises(TypeError, match=self.FILL_ERROR):
            np.strings.rjust(buf, 10, fill)

    @pytest.mark.parametrize("buf,width,fillchar,res", [
        ('abc', 10, ' ', '   abc    '),
        ('abc', 6, ' ', ' abc  '),
        ('abc', 3, ' ', 'abc'),
        ('abc', 2, ' ', 'abc'),
        ('abc', 10, '*', '***abc****'),
    ])
    def test_center(self, buf, width, fillchar, res, dt):
        buf = np.array(buf, dtype=dt)
        fillchar = np.array(fillchar, dtype=dt)
        res = np.array(res, dtype=dt)
        assert_array_equal(np.strings.center(buf, width, fillchar), res)

    @pytest.mark.parametrize("buf,width,fillchar,res", [
        ('abc', 10, ' ', 'abc       '),
        ('abc', 6, ' ', 'abc   '),
        ('abc', 3, ' ', 'abc'),
        ('abc', 2, ' ', 'abc'),
        ('abc', 10, '*', 'abc*******'),
    ])
    def test_ljust(self, buf, width, fillchar, res, dt):
        buf = np.array(buf, dtype=dt)
        fillchar = np.array(fillchar, dtype=dt)
        res = np.array(res, dtype=dt)
        assert_array_equal(np.strings.ljust(buf, width, fillchar), res)

    @pytest.mark.parametrize("buf,width,fillchar,res", [
        ('abc', 10, ' ', '       abc'),
        ('abc', 6, ' ', '   abc'),
        ('abc', 3, ' ', 'abc'),
        ('abc', 2, ' ', 'abc'),
        ('abc', 10, '*', '*******abc'),
    ])
    def test_rjust(self, buf, width, fillchar, res, dt):
        buf = np.array(buf, dtype=dt)
        fillchar = np.array(fillchar, dtype=dt)
        res = np.array(res, dtype=dt)
        assert_array_equal(np.strings.rjust(buf, width, fillchar), res)

    @pytest.mark.parametrize("buf,width,res", [
        ('123', 2, '123'),
        ('123', 3, '123'),
        ('0123', 4, '0123'),
        ('+123', 3, '+123'),
        ('+123', 4, '+123'),
        ('+123', 5, '+0123'),
        ('+0123', 5, '+0123'),
        ('-123', 3, '-123'),
        ('-123', 4, '-123'),
        ('-0123', 5, '-0123'),
        ('000', 3, '000'),
        ('34', 1, '34'),
        ('0034', 4, '0034'),
    ])
    def test_zfill(self, buf, width, res, dt):
        buf = np.array(buf, dtype=dt)
        res = np.array(res, dtype=dt)
        assert_array_equal(np.strings.zfill(buf, width), res)

    @pytest.mark.parametrize("buf,sep,res1,res2,res3", [
        ("this is the partition method", "ti", "this is the par",
            "ti", "tion method"),
        ("http://www.python.org", "://", "http", "://", "www.python.org"),
        ("http://www.python.org", "?", "http://www.python.org", "", ""),
        ("http://www.python.org", "http://", "", "http://", "www.python.org"),
        ("http://www.python.org", "org", "http://www.python.", "org", ""),
        ("http://www.python.org", ["://", "?", "http://", "org"],
            ["http", "http://www.python.org", "", "http://www.python."],
            ["://", "", "http://", "org"],
            ["www.python.org", "", "www.python.org", ""]),
        ("mississippi", "ss", "mi", "ss", "issippi"),
        ("mississippi", "i", "m", "i", "ssissippi"),
        ("mississippi", "w", "mississippi", "", ""),
    ])
    def test_partition(self, buf, sep, res1, res2, res3, dt):
        buf = np.array(buf, dtype=dt)
        sep = np.array(sep, dtype=dt)
        res1 = np.array(res1, dtype=dt)
        res2 = np.array(res2, dtype=dt)
        res3 = np.array(res3, dtype=dt)
        act1, act2, act3 = np.strings.partition(buf, sep)
        assert_array_equal(act1, res1)
        assert_array_equal(act2, res2)
        assert_array_equal(act3, res3)
        assert_array_equal(act1 + act2 + act3, buf)

    @pytest.mark.parametrize("buf,sep,res1,res2,res3", [
        ("this is the partition method", "ti", "this is the parti",
            "ti", "on method"),
        ("http://www.python.org", "://", "http", "://", "www.python.org"),
        ("http://www.python.org", "?", "", "", "http://www.python.org"),
        ("http://www.python.org", "http://", "", "http://", "www.python.org"),
        ("http://www.python.org", "org", "http://www.python.", "org", ""),
        ("http://www.python.org", ["://", "?", "http://", "org"],
            ["http", "", "", "http://www.python."],
            ["://", "", "http://", "org"],
            ["www.python.org", "http://www.python.org", "www.python.org", ""]),
        ("mississippi", "ss", "missi", "ss", "ippi"),
        ("mississippi", "i", "mississipp", "i", ""),
        ("mississippi", "w", "", "", "mississippi"),
    ])
    def test_rpartition(self, buf, sep, res1, res2, res3, dt):
        buf = np.array(buf, dtype=dt)
        sep = np.array(sep, dtype=dt)
        res1 = np.array(res1, dtype=dt)
        res2 = np.array(res2, dtype=dt)
        res3 = np.array(res3, dtype=dt)
        act1, act2, act3 = np.strings.rpartition(buf, sep)
        assert_array_equal(act1, res1)
        assert_array_equal(act2, res2)
        assert_array_equal(act3, res3)
        assert_array_equal(act1 + act2 + act3, buf)


@pytest.mark.parametrize("dt", ["U", "T"])
class TestMethodsWithUnicode:
    @pytest.mark.parametrize("in_,out", [
        ("", False),
        ("a", False),
        ("0", True),
        ("\u2460", False),  # CIRCLED DIGIT 1
        ("\xbc", False),  # VULGAR FRACTION ONE QUARTER
        ("\u0660", True),  # ARABIC_INDIC DIGIT ZERO
        ("012345", True),
        ("012345a", False),
        (["0", "a"], [True, False]),
    ])
    def test_isdecimal_unicode(self, in_, out, dt):
        buf = np.array(in_, dtype=dt)
        assert_array_equal(np.strings.isdecimal(buf), out)

    @pytest.mark.parametrize("in_,out", [
        ("", False),
        ("a", False),
        ("0", True),
        ("\u2460", True),  # CIRCLED DIGIT 1
        ("\xbc", True),  # VULGAR FRACTION ONE QUARTER
        ("\u0660", True),  # ARABIC_INDIC DIGIT ZERO
        ("012345", True),
        ("012345a", False),
        (["0", "a"], [True, False]),
    ])
    def test_isnumeric_unicode(self, in_, out, dt):
        buf = np.array(in_, dtype=dt)
        assert_array_equal(np.strings.isnumeric(buf), out)

    @pytest.mark.parametrize("buf,old,new,count,res", [
        ("...\u043c......<", "<", "&lt;", -1, "...\u043c......&lt;"),
        ("Ae¢☃€ 😊" * 2, "A", "B", -1, "Be¢☃€ 😊Be¢☃€ 😊"),
        ("Ae¢☃€ 😊" * 2, "😊", "B", -1, "Ae¢☃€ BAe¢☃€ B"),
    ])
    def test_replace_unicode(self, buf, old, new, count, res, dt):
        buf = np.array(buf, dtype=dt)
        old = np.array(old, dtype=dt)
        new = np.array(new, dtype=dt)
        res = np.array(res, dtype=dt)
        assert_array_equal(np.strings.replace(buf, old, new, count), res)

    @pytest.mark.parametrize("in_", [
        '\U00010401',
        '\U00010427',
        '\U00010429',
        '\U0001044E',
        '\U0001D7F6',
        '\U00011066',
        '\U000104A0',
        pytest.param('\U0001F107', marks=pytest.mark.xfail(
            sys.platform == 'win32' and IS_PYPY_LT_7_3_16,
            reason="PYPY bug in Py_UNICODE_ISALNUM",
            strict=True)),
    ])
    def test_isalnum_unicode(self, in_, dt):
        in_ = np.array(in_, dtype=dt)
        assert_array_equal(np.strings.isalnum(in_), True)

    @pytest.mark.parametrize("in_,out", [
        ('\u1FFc', False),
        ('\u2167', False),
        ('\U00010401', False),
        ('\U00010427', False),
        ('\U0001F40D', False),
        ('\U0001F46F', False),
        ('\u2177', True),
        pytest.param('\U00010429', True, marks=pytest.mark.xfail(
            sys.platform == 'win32' and IS_PYPY_LT_7_3_16,
            reason="PYPY bug in Py_UNICODE_ISLOWER",
            strict=True)),
        ('\U0001044E', True),
    ])
    def test_islower_unicode(self, in_, out, dt):
        in_ = np.array(in_, dtype=dt)
        assert_array_equal(np.strings.islower(in_), out)

    @pytest.mark.parametrize("in_,out", [
        ('\u1FFc', False),
        ('\u2167', True),
        ('\U00010401', True),
        ('\U00010427', True),
        ('\U0001F40D', False),
        ('\U0001F46F', False),
        ('\u2177', False),
        pytest.param('\U00010429', False, marks=pytest.mark.xfail(
            sys.platform == 'win32' and IS_PYPY_LT_7_3_16,
            reason="PYPY bug in Py_UNICODE_ISUPPER",
            strict=True)),
        ('\U0001044E', False),
    ])
    def test_isupper_unicode(self, in_, out, dt):
        in_ = np.array(in_, dtype=dt)
        assert_array_equal(np.strings.isupper(in_), out)

    @pytest.mark.parametrize("in_,out", [
        ('\u1FFc', True),
        ('Greek \u1FFcitlecases ...', True),
        pytest.param('\U00010401\U00010429', True, marks=pytest.mark.xfail(
            sys.platform == 'win32' and IS_PYPY_LT_7_3_16,
            reason="PYPY bug in Py_UNICODE_ISISTITLE",
            strict=True)),
        ('\U00010427\U0001044E', True),
        pytest.param('\U00010429', False, marks=pytest.mark.xfail(
            sys.platform == 'win32' and IS_PYPY_LT_7_3_16,
            reason="PYPY bug in Py_UNICODE_ISISTITLE",
            strict=True)),
        ('\U0001044E', False),
        ('\U0001F40D', False),
        ('\U0001F46F', False),
    ])
    def test_istitle_unicode(self, in_, out, dt):
        in_ = np.array(in_, dtype=dt)
        assert_array_equal(np.strings.istitle(in_), out)

    @pytest.mark.parametrize("buf,sub,start,end,res", [
        ("Ae¢☃€ 😊" * 2, "😊", 0, None, 6),
        ("Ae¢☃€ 😊" * 2, "😊", 7, None, 13),
    ])
    def test_index_unicode(self, buf, sub, start, end, res, dt):
        buf = np.array(buf, dtype=dt)
        sub = np.array(sub, dtype=dt)
        assert_array_equal(np.strings.index(buf, sub, start, end), res)

    def test_index_raises_unicode(self, dt):
        with pytest.raises(ValueError, match="substring not found"):
            np.strings.index("Ae¢☃€ 😊", "😀")

    @pytest.mark.parametrize("buf,res", [
        ("Ae¢☃€ \t 😊", "Ae¢☃€    😊"),
        ("\t\U0001044E", "        \U0001044E"),
    ])
    def test_expandtabs(self, buf, res, dt):
        buf = np.array(buf, dtype=dt)
        res = np.array(res, dtype=dt)
        assert_array_equal(np.strings.expandtabs(buf), res)

    @pytest.mark.parametrize("buf,width,fillchar,res", [
        ('x', 2, '\U0001044E', 'x\U0001044E'),
        ('x', 3, '\U0001044E', '\U0001044Ex\U0001044E'),
        ('x', 4, '\U0001044E', '\U0001044Ex\U0001044E\U0001044E'),
    ])
    def test_center(self, buf, width, fillchar, res, dt):
        buf = np.array(buf, dtype=dt)
        fillchar = np.array(fillchar, dtype=dt)
        res = np.array(res, dtype=dt)
        assert_array_equal(np.strings.center(buf, width, fillchar), res)

    @pytest.mark.parametrize("buf,width,fillchar,res", [
        ('x', 2, '\U0001044E', 'x\U0001044E'),
        ('x', 3, '\U0001044E', 'x\U0001044E\U0001044E'),
        ('x', 4, '\U0001044E', 'x\U0001044E\U0001044E\U0001044E'),
    ])
    def test_ljust(self, buf, width, fillchar, res, dt):
        buf = np.array(buf, dtype=dt)
        fillchar = np.array(fillchar, dtype=dt)
        res = np.array(res, dtype=dt)
        assert_array_equal(np.strings.ljust(buf, width, fillchar), res)

    @pytest.mark.parametrize("buf,width,fillchar,res", [
        ('x', 2, '\U0001044E', '\U0001044Ex'),
        ('x', 3, '\U0001044E', '\U0001044E\U0001044Ex'),
        ('x', 4, '\U0001044E', '\U0001044E\U0001044E\U0001044Ex'),
    ])
    def test_rjust(self, buf, width, fillchar, res, dt):
        buf = np.array(buf, dtype=dt)
        fillchar = np.array(fillchar, dtype=dt)
        res = np.array(res, dtype=dt)
        assert_array_equal(np.strings.rjust(buf, width, fillchar), res)

    @pytest.mark.parametrize("buf,sep,res1,res2,res3", [
        ("āāāāĀĀĀĀ", "Ă", "āāāāĀĀĀĀ", "", ""),
        ("āāāāĂĀĀĀĀ", "Ă", "āāāā", "Ă", "ĀĀĀĀ"),
        ("āāāāĂĂĀĀĀĀ", "ĂĂ", "āāāā", "ĂĂ", "ĀĀĀĀ"),
        ("𐌁𐌁𐌁𐌁𐌀𐌀𐌀𐌀", "𐌂", "𐌁𐌁𐌁𐌁𐌀𐌀𐌀𐌀", "", ""),
        ("𐌁𐌁𐌁𐌁𐌂𐌀𐌀𐌀𐌀", "𐌂", "𐌁𐌁𐌁𐌁", "𐌂", "𐌀𐌀𐌀𐌀"),
        ("𐌁𐌁𐌁𐌁𐌂𐌂𐌀𐌀𐌀𐌀", "𐌂𐌂", "𐌁𐌁𐌁𐌁", "𐌂𐌂", "𐌀𐌀𐌀𐌀"),
        ("𐌁𐌁𐌁𐌁𐌂𐌂𐌂𐌂𐌀𐌀𐌀𐌀", "𐌂𐌂𐌂𐌂", "𐌁𐌁𐌁𐌁", "𐌂𐌂𐌂𐌂", "𐌀𐌀𐌀𐌀"),
    ])
    def test_partition(self, buf, sep, res1, res2, res3, dt):
        buf = np.array(buf, dtype=dt)
        sep = np.array(sep, dtype=dt)
        res1 = np.array(res1, dtype=dt)
        res2 = np.array(res2, dtype=dt)
        res3 = np.array(res3, dtype=dt)
        act1, act2, act3 = np.strings.partition(buf, sep)
        assert_array_equal(act1, res1)
        assert_array_equal(act2, res2)
        assert_array_equal(act3, res3)
        assert_array_equal(act1 + act2 + act3, buf)

    @pytest.mark.parametrize("buf,sep,res1,res2,res3", [
        ("āāāāĀĀĀĀ", "Ă", "", "", "āāāāĀĀĀĀ"),
        ("āāāāĂĀĀĀĀ", "Ă", "āāāā", "Ă", "ĀĀĀĀ"),
        ("āāāāĂĂĀĀĀĀ", "ĂĂ", "āāāā", "ĂĂ", "ĀĀĀĀ"),
        ("𐌁𐌁𐌁𐌁𐌀𐌀𐌀𐌀", "𐌂", "", "", "𐌁𐌁𐌁𐌁𐌀𐌀𐌀𐌀"),
        ("𐌁𐌁𐌁𐌁𐌂𐌀𐌀𐌀𐌀", "𐌂", "𐌁𐌁𐌁𐌁", "𐌂", "𐌀𐌀𐌀𐌀"),
        ("𐌁𐌁𐌁𐌁𐌂𐌂𐌀𐌀𐌀𐌀", "𐌂𐌂", "𐌁𐌁𐌁𐌁", "𐌂𐌂", "𐌀𐌀𐌀𐌀"),
    ])
    def test_rpartition(self, buf, sep, res1, res2, res3, dt):
        buf = np.array(buf, dtype=dt)
        sep = np.array(sep, dtype=dt)
        res1 = np.array(res1, dtype=dt)
        res2 = np.array(res2, dtype=dt)
        res3 = np.array(res3, dtype=dt)
        act1, act2, act3 = np.strings.rpartition(buf, sep)
        assert_array_equal(act1, res1)
        assert_array_equal(act2, res2)
        assert_array_equal(act3, res3)
        assert_array_equal(act1 + act2 + act3, buf)

    @pytest.mark.parametrize("method", ["strip", "lstrip", "rstrip"])
    @pytest.mark.parametrize(
        "source,strip",
        [
            ("λμ", "μ"),
            ("λμ", "λ"),
            ("λ"*5 + "μ"*2, "μ"),
            ("λ" * 5 + "μ" * 2, "λ"),
            ("λ" * 5 + "A" + "μ" * 2, "μλ"),
            ("λμ" * 5, "μ"),
            ("λμ" * 5, "λ"),
    ])
    def test_strip_functions_unicode(self, source, strip, method, dt):
        src_array = np.array([source], dtype=dt)

        npy_func = getattr(np.strings, method)
        py_func = getattr(str, method)

        expected = np.array([py_func(source, strip)], dtype=dt)
        actual = npy_func(src_array, strip)

        assert_array_equal(actual, expected)


class TestMixedTypeMethods:
    def test_center(self):
        buf = np.array("😊", dtype="U")
        fill = np.array("*", dtype="S")
        res = np.array("*😊*", dtype="U")
        assert_array_equal(np.strings.center(buf, 3, fill), res)

        buf = np.array("s", dtype="S")
        fill = np.array("*", dtype="U")
        res = np.array("*s*", dtype="S")
        assert_array_equal(np.strings.center(buf, 3, fill), res)

        with pytest.raises(ValueError, match="'ascii' codec can't encode"):
            buf = np.array("s", dtype="S")
            fill = np.array("😊", dtype="U")
            np.strings.center(buf, 3, fill)

    def test_ljust(self):
        buf = np.array("😊", dtype="U")
        fill = np.array("*", dtype="S")
        res = np.array("😊**", dtype="U")
        assert_array_equal(np.strings.ljust(buf, 3, fill), res)

        buf = np.array("s", dtype="S")
        fill = np.array("*", dtype="U")
        res = np.array("s**", dtype="S")
        assert_array_equal(np.strings.ljust(buf, 3, fill), res)

        with pytest.raises(ValueError, match="'ascii' codec can't encode"):
            buf = np.array("s", dtype="S")
            fill = np.array("😊", dtype="U")
            np.strings.ljust(buf, 3, fill)

    def test_rjust(self):
        buf = np.array("😊", dtype="U")
        fill = np.array("*", dtype="S")
        res = np.array("**😊", dtype="U")
        assert_array_equal(np.strings.rjust(buf, 3, fill), res)

        buf = np.array("s", dtype="S")
        fill = np.array("*", dtype="U")
        res = np.array("**s", dtype="S")
        assert_array_equal(np.strings.rjust(buf, 3, fill), res)

        with pytest.raises(ValueError, match="'ascii' codec can't encode"):
            buf = np.array("s", dtype="S")
            fill = np.array("😊", dtype="U")
            np.strings.rjust(buf, 3, fill)


class TestUnicodeOnlyMethodsRaiseWithBytes:
    def test_isdecimal_raises(self):
        in_ = np.array(b"1")
        with assert_raises(TypeError):
            np.strings.isdecimal(in_)

    def test_isnumeric_bytes(self):
        in_ = np.array(b"1")
        with assert_raises(TypeError):
            np.strings.isnumeric(in_)


def check_itemsize(n_elem, dt):
    if dt == "T":
        return np.dtype(dt).itemsize
    if dt == "S":
        return n_elem
    if dt == "U":
        return n_elem * 4

@pytest.mark.parametrize("dt", ["S", "U", "T"])
class TestReplaceOnArrays:

    def test_replace_count_and_size(self, dt):
        a = np.array(["0123456789" * i for i in range(4)], dtype=dt)
        r1 = np.strings.replace(a, "5", "ABCDE")
        assert r1.dtype.itemsize == check_itemsize(3*10 + 3*4, dt)
        r1_res = np.array(["01234ABCDE6789" * i for i in range(4)], dtype=dt)
        assert_array_equal(r1, r1_res)
        r2 = np.strings.replace(a, "5", "ABCDE", 1)
        assert r2.dtype.itemsize == check_itemsize(3*10 + 4, dt)
        r3 = np.strings.replace(a, "5", "ABCDE", 0)
        assert r3.dtype.itemsize == a.dtype.itemsize
        assert_array_equal(r3, a)
        # Negative values mean to replace all.
        r4 = np.strings.replace(a, "5", "ABCDE", -1)
        assert r4.dtype.itemsize == check_itemsize(3*10 + 3*4, dt)
        assert_array_equal(r4, r1)
        # We can do count on an element-by-element basis.
        r5 = np.strings.replace(a, "5", "ABCDE", [-1, -1, -1, 1])
        assert r5.dtype.itemsize == check_itemsize(3*10 + 4, dt)
        assert_array_equal(r5, np.array(
            ["01234ABCDE6789" * i for i in range(3)]
            + ["01234ABCDE6789" + "0123456789" * 2], dtype=dt))

    def test_replace_broadcasting(self, dt):
        a = np.array("0,0,0", dtype=dt)
        r1 = np.strings.replace(a, "0", "1", np.arange(3))
        assert r1.dtype == a.dtype
        assert_array_equal(r1, np.array(["0,0,0", "1,0,0", "1,1,0"], dtype=dt))
        r2 = np.strings.replace(a, "0", [["1"], ["2"]], np.arange(1, 4))
        assert_array_equal(r2, np.array([["1,0,0", "1,1,0", "1,1,1"],
                                         ["2,0,0", "2,2,0", "2,2,2"]],
                                        dtype=dt))
        r3 = np.strings.replace(a, ["0", "0,0", "0,0,0"], "X")
        assert_array_equal(r3, np.array(["X,X,X", "X,0", "X"], dtype=dt))
